"""Regression evidence for error, source compatibility and fenced publication review."""

# ruff: noqa: F811

import asyncio
import copy
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from test_v2_ingestion_integration import canonical_input, v2_engine  # noqa: F401
from test_v2_research import body
from test_v2_research_integration import fixture_version, research_engine  # noqa: F401

from marketlab.analytics.bars import BarError, BarService
from marketlab.app import create_app
from marketlab.datasets.v2 import capacity as shared_capacity
from marketlab.datasets.v2 import core
from marketlab.datasets.v2 import service as ingestion
from marketlab.datasets.v2.common import V2Error, sha256_file
from marketlab.datasets.v2.core import one
from marketlab.research.v2 import capacity, store
from marketlab.research.v2.errors import transient
from marketlab.research.v2.numerics import calculate
from marketlab.research.v2.service import ResearchService, verify_directory
from marketlab.research.v2.spec import ResearchSpec


@pytest.mark.parametrize(
    "status,code,retry",
    [
        (422, "invalid_request", False),
        (409, "coverage_gap", False),
        (503, "unavailable", True),
        (504, "deadline_exceeded", True),
    ],
)
@pytest.mark.parametrize("endpoint", ["submit", "bars"])
async def test_bar_errors_are_safe_http_and_narrow_retry(status, code, retry, endpoint):
    app = create_app()
    secret = "private C:/secrets/trade.csv SELECT password FROM credentials"

    async def failed(*args, **kwargs):
        raise BarError(secret, status)

    app.state.v2_research_service = SimpleNamespace(
        submit=failed, bars=SimpleNamespace(read=failed)
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        if endpoint == "submit":
            response = await client.post(
                "/v2/research/runs", json=body(), headers={"Idempotency-Key": "review-errors"}
            )
        else:
            response = await client.get(
                "/v2/bars",
                params={
                    "instrument_id": "binance:spot:SOLUSDT",
                    "version": "a" * 64,
                    "interval": "5m",
                    "start": "2025-03-01T00:00:00Z",
                    "end": "2025-03-01T00:05:00Z",
                },
            )
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert secret not in response.text and "password" not in response.text
    assert transient(BarError(secret, status)) is retry


async def test_deep_json_rejected_as_safe_validation_before_service_dispatch():
    app = create_app()
    # A bounded body can still exceed the JSON decoder's nesting depth.
    raw = b'{"extra":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}"
    with pytest.raises(V2Error):
        ResearchSpec.parse(raw)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        response = await client.post(
            "/v2/research/runs",
            content=raw,
            headers={"content-type": "application/json", "Idempotency-Key": "deep-json"},
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.parametrize("fraction", ["0000001", "0000000", "0000000001"])
def test_submicrosecond_research_timestamp_is_never_silently_truncated(fraction):
    request = body()
    request["start"] = f"2025-03-01T01:00:00.{fraction}Z"
    with pytest.raises(V2Error):
        ResearchSpec.create(request)


def prepared_spec(version):
    request = body()
    request.update(instrument_ids=["binance:spot:BTCUSDT"], dataset_versions=[version])
    return ResearchSpec.create(request)


@pytest.mark.integration
@pytest.mark.parametrize(
    "status,state,code",
    [
        (422, "failed", "invalid_request"),
        (409, "failed", "coverage_gap"),
        (503, "retry_wait", "unavailable"),
        (504, "retry_wait", "deadline_exceeded"),
    ],
)
async def test_actual_worker_bar_error_records_only_transient_retries(
    research_engine, tmp_path, monkeypatch, status, state, code
):
    root = tmp_path / "storage"
    version = fixture_version(research_engine, root, tmp_path)
    base = BarService(research_engine, root, None)
    research = ResearchService(base)
    try:
        run, _ = await research.submit(prepared_spec(version), "review-worker-error")

        async def failed(*args, **kwargs):
            raise BarError("private SQL and filename must never persist", status)

        monkeypatch.setattr(research, "prepare", failed)
        assert await research.work(1, run) == 1
        actual = research.inspect(run)
        assert actual["state"] == state
        assert actual["attempt_count"] == 1 and actual["error_code"] == code
        assert actual["attempts"][0]["outcome"] == (
            "transient" if state == "retry_wait" else "permanent"
        )
        assert "private" not in str(actual)
    finally:
        await research.close()
        await base.close()


@pytest.mark.integration
async def test_docs_only_git_provenance_change_keeps_source_compatible(research_engine, tmp_path):
    root = tmp_path / "storage"
    version = fixture_version(research_engine, root, tmp_path)
    base = BarService(research_engine, root, None)
    original = ResearchService(base)
    changed = ResearchService(base)
    try:
        run, _ = await original.submit(prepared_spec(version), "docs-provenance")
        pinned = original.inspect(run)["fingerprint"]["execution"]
        # Simulate docs-only checkout provenance; source/lock/protocol remain exact.
        changed._execution = dict(pinned, git_dirty=not pinned["git_dirty"], git_revision="f" * 40)
        assert await changed.work(1, run) == 1
        actual = changed.inspect(run)
        assert actual["state"] == "succeeded" and actual["attempt_count"] == 1
        assert actual["fingerprint"]["execution"] == pinned
        result, _ = changed.read(run, "results")
        assert result["profiles"]["binance:spot:BTCUSDT"]["coverage"]["observed"] == 8
    finally:
        await changed.close()
        await original.close()
        await base.close()


@pytest.mark.integration
@pytest.mark.parametrize("field", ["source_sha256", "lock_sha256"])
async def test_incompatible_source_or_lock_skipped_without_attempt(
    research_engine, tmp_path, field
):
    root = tmp_path / "storage"
    version = fixture_version(research_engine, root, tmp_path)
    base = BarService(research_engine, root, None)
    research = ResearchService(base)
    try:
        run, _ = await research.submit(prepared_spec(version), "incompatible-source")
        pinned = research.inspect(run)["fingerprint"]["execution"]
        changed = dict(pinned, **{field: "0" * 64 if pinned[field] != "0" * 64 else "1" * 64})
        assert store.claim(research_engine, changed, run) is None
        actual = research.inspect(run)
        assert actual["state"] == "queued" and actual["attempt_count"] == 0
        assert actual["attempts"] == [] and actual["fencing_token"] == 0
    finally:
        await research.close()
        await base.close()


def artifact_hashes(path):
    return {str(p.relative_to(path)): sha256_file(p) for p in path.rglob("*") if p.is_file()}


async def staged_run(engine, root, tmp_path):
    version = fixture_version(engine, root, tmp_path)
    base = BarService(engine, root, None)
    research = ResearchService(base)
    spec = prepared_spec(version)
    run, _ = await research.submit(spec, "publication-review")
    current = store.claim(engine, research.execution, run)
    assert current is not None
    fingerprint = research.inspect(run)["fingerprint"]
    reservation = capacity.reserve(engine, root, run, "attempt")
    rows, inputs = await research.prepare(
        spec, current.lost, reservation, fingerprint["instruments"]
    )
    result, summary = calculate(spec, inputs, fingerprint["instruments"], current.lost)
    staging = research.stage(current, spec, fingerprint, result, summary, reservation["path"])
    return base, research, spec, current, fingerprint, reservation, staging, result, summary


@pytest.mark.integration
async def test_self_consistent_divergent_orphan_rejected_before_registration(
    research_engine, tmp_path
):
    root = tmp_path / "storage"
    (
        base,
        research,
        spec,
        current,
        fingerprint,
        reservation,
        staging,
        result,
        summary,
    ) = await staged_run(research_engine, root, tmp_path)
    try:
        divergent = copy.deepcopy(result)
        divergent["profiles"]["binance:spot:BTCUSDT"]["coverage"]["observed"] += 1
        orphan = research.stage(current, spec, fingerprint, divergent, summary, reservation["path"])
        final = root / "research-v2" / current.run_id
        final.parent.mkdir(parents=True, exist_ok=True)
        orphan.rename(final)
        # Its own manifest hashes verify; deterministic comparison must still reject it.
        verify_directory(final, current.run_id, fingerprint)
        before = artifact_hashes(root)
        with pytest.raises(V2Error, match="orphan differs"):
            research.publish(current, staging, fingerprint)
        assert artifact_hashes(root) == before
        with research_engine.connect() as connection:
            assert (
                one(
                    connection,
                    "SELECT * FROM v2_research_results WHERE run_id=:id",
                    id=current.run_id,
                )
                is None
            )
        assert research.inspect(current.run_id)["state"] == "running"
    finally:
        capacity.release(research_engine, root, reservation)
        await research.close()
        await base.close()


@pytest.mark.integration
async def test_cancellation_immediately_pre_rename_prevents_all_filesystem_publication(
    research_engine, tmp_path, monkeypatch
):
    import marketlab.research.v2.service as module

    root = tmp_path / "storage"
    base, research, _, current, fingerprint, reservation, staging, _, _ = await staged_run(
        research_engine, root, tmp_path
    )
    try:
        final = root / "research-v2" / current.run_id
        final.parent.mkdir(parents=True, exist_ok=True)
        before = artifact_hashes(root)
        original_signature = module.signature
        cancelled = []

        def cancel_at_last_pretransaction_checkpoint(path: Path):
            result = original_signature(path)
            if not cancelled:
                revision = research.inspect(current.run_id)["revision"]
                cancelled.append(
                    store.cancel(research_engine, current.run_id, revision, "win-before-rename")
                )
            return result

        monkeypatch.setattr(module, "signature", cancel_at_last_pretransaction_checkpoint)
        with pytest.raises(V2Error):
            research.publish(current, staging, fingerprint)
        assert cancelled and cancelled[0]["cancel_requested"]
        assert not final.exists() and staging.exists()
        assert artifact_hashes(root) == before
        with research_engine.connect() as connection:
            assert (
                one(
                    connection,
                    "SELECT * FROM v2_research_results WHERE run_id=:id",
                    id=current.run_id,
                )
                is None
            )
        assert research.inspect(current.run_id)["cancel_requested"]
    finally:
        capacity.release(research_engine, root, reservation)
        await research.close()
        await base.close()


@pytest.mark.integration
@pytest.mark.parametrize("research_first", [False, True])
def test_simultaneous_ingestion_research_admission_blocks_then_rejects(
    research_engine, tmp_path, monkeypatch, research_first
):
    """Controlled-capacity race; this does not establish actual machine capacity."""
    root = tmp_path / "shared-capacity"
    root.mkdir()
    research_root = Path("\\\\?\\" + str(root.resolve())) if os.name == "nt" else root
    source, manifest = canonical_input(tmp_path)
    declared = source.stat().st_size
    ceiling = shared_capacity.SCRATCH + shared_capacity.SPILL + shared_capacity.OUTPUT

    def controlled_disk_usage(_):
        retained = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
        return SimpleNamespace(free=ceiling + declared - 1 - retained)

    monkeypatch.setattr(shared_capacity.shutil, "disk_usage", controlled_disk_usage)
    first_locked, second_entered, allow_commit = (threading.Event() for _ in range(3))
    second_pid = []
    values, failures = {}, {}
    original_lock = core.lock

    def observed_capacity_lock(connection, namespace):
        name = threading.current_thread().name
        if namespace.startswith("v2-space:") and name == "review-capacity-second":
            second_pid.append(core.execute(connection, "SELECT pg_backend_pid()").scalar_one())
            second_entered.set()
        original_lock(connection, namespace)
        if namespace.startswith("v2-space:") and name == "review-capacity-first":
            first_locked.set()
            if not allow_commit.wait(10):
                raise RuntimeError("Timed out waiting for controlled commit")

    monkeypatch.setattr(shared_capacity, "lock", observed_capacity_lock)
    monkeypatch.setattr(ingestion, "lock", observed_capacity_lock)

    def research_admission():
        return shared_capacity.reserve(research_engine, research_root)

    def ingestion_admission():
        return ingestion.import_file(research_engine, root, manifest, source, "concurrent-import")

    first_call = research_admission if research_first else ingestion_admission
    second_call = ingestion_admission if research_first else research_admission

    def invoke(label, operation):
        try:
            values[label] = operation()
        except Exception as error:
            failures[label] = error

    first = threading.Thread(
        target=invoke, args=("first", first_call), name="review-capacity-first"
    )
    second = threading.Thread(
        target=invoke, args=("second", second_call), name="review-capacity-second"
    )
    try:
        first.start()
        assert first_locked.wait(3), "First admission never acquired its capacity lock"
        second.start()
        assert second_entered.wait(3), "Second admission never attempted the shared lock"
        deadline = time.monotonic() + 3
        blocked = False
        while time.monotonic() < deadline:
            with research_engine.connect() as connection:
                waiting = core.execute(
                    connection,
                    "SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid",
                    pid=second_pid[0],
                ).scalar_one_or_none()
            if waiting == "Lock":
                blocked = True
                break
            if "second" in values or "second" in failures:
                break
            time.sleep(0.01)
        assert blocked, "Second admission did not block on the common PostgreSQL lock"
        assert "second" not in values and "second" not in failures
        allow_commit.set()
        first.join(5)
        second.join(5)
        assert not first.is_alive() and not second.is_alive()
        assert "first" in values and "first" not in failures
        assert "second" not in values
        assert isinstance(failures.get("second"), V2Error)
        assert failures["second"].code == "capacity_exceeded"
    finally:
        allow_commit.set()
        if first.ident is not None:
            first.join(5)
        if second.ident is not None:
            second.join(5)
        if research_first and "first" in values:
            shared_capacity.release(research_engine, research_root, values["first"])


@pytest.mark.integration
def test_retained_research_charge_blocks_native_import_until_verified_release(
    research_engine, tmp_path, monkeypatch
):
    """Use a controlled low-free-space fixture with real reservation ownership."""
    root = tmp_path / "retained-capacity"
    root.mkdir()
    source, manifest = canonical_input(tmp_path)
    declared = source.stat().st_size
    ceiling = shared_capacity.SCRATCH + shared_capacity.SPILL + shared_capacity.OUTPUT

    def controlled_disk_usage(_):
        retained = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
        return SimpleNamespace(free=ceiling + declared - 1 - retained)

    monkeypatch.setattr(shared_capacity.shutil, "disk_usage", controlled_disk_usage)
    reservation = shared_capacity.reserve(research_engine, root)
    (reservation["path"] / "failed-attempt.bin").write_bytes(b"retained")
    shared_capacity.release(research_engine, root, reservation, success=False)
    with pytest.raises(V2Error) as blocked:
        ingestion.import_file(research_engine, root, manifest, source, "blocked-import")
    assert blocked.value.code == "capacity_exceeded"
    assert (reservation["path"] / "failed-attempt.bin").exists()
    with research_engine.connect() as connection:
        retained = one(
            connection,
            "SELECT * FROM v2_research_reservations WHERE reservation_id=:id",
            id=reservation["reservation_id"],
        )
    assert retained["state"] == "retained"
    assert retained["scratch_bytes"] + retained["spill_bytes"] + retained["output_bytes"] == ceiling
    shared_capacity.release(research_engine, root, reservation)
    assert not reservation["path"].exists()
    with research_engine.connect() as connection:
        released = one(
            connection,
            "SELECT * FROM v2_research_reservations WHERE reservation_id=:id",
            id=reservation["reservation_id"],
        )
    assert released["state"] == "released"
    assert released["scratch_bytes"] == released["spill_bytes"] == released["output_bytes"] == 0
    admitted = ingestion.import_file(research_engine, root, manifest, source, "after-release")
    assert ingestion.inspect_import(research_engine, admitted["import_id"])["state"] == "queued"


async def test_worker_stop_event_drains_active_attempt_and_prevents_new_claims(
    tmp_path, monkeypatch
):
    from sqlalchemy import create_engine

    base = BarService(create_engine("sqlite://"), tmp_path, None)
    research = ResearchService(base)
    research._execution = {"source_sha256": "a" * 64}
    stop = threading.Event()
    started, drain = asyncio.Event(), asyncio.Event()
    claims = []
    finished = []
    current = SimpleNamespace(run_id="controlled-active")

    def claim(*args, **kwargs):
        claims.append(True)
        return current

    async def execute(claimed):
        assert claimed is current
        started.set()
        await drain.wait()
        finished.append(True)

    monkeypatch.setattr(store, "claim", claim)
    monkeypatch.setattr(research, "execute", execute)
    try:
        worker = asyncio.create_task(research.work(2, stop_event=stop))
        await asyncio.wait_for(started.wait(), 2)
        stop.set()
        await asyncio.sleep(0)
        assert not worker.done() and finished == []
        drain.set()
        assert await asyncio.wait_for(worker, 2) == 1
        assert claims == [True] and finished == [True]
        # A preexisting stop request must not claim even the first job.
        assert await research.work(2, stop_event=stop) == 0
        assert claims == [True]
    finally:
        drain.set()
        await research.close()
        await base.close()
