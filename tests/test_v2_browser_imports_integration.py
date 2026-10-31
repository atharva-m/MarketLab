"""Actual PostgreSQL generations, quota/slot admission and durable pipeline."""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from starlette.requests import Request
from test_datasets import ROW, archive_files
from test_v2_ingestion_integration import v2_engine  # noqa: F401
from test_v2_research_integration import research_engine  # noqa: F401

from marketlab.datasets.v2 import admission, jobs, native_identity, service
from marketlab.datasets.v2.browser_imports import BrowserImports
from marketlab.datasets.v2.common import V2Error, safe_path
from marketlab.datasets.v2.core import execute
from marketlab.datasets.v2.core import lock as root_lock

pytestmark = pytest.mark.integration


@pytest.fixture
def browser_engine(research_engine, monkeypatch):  # noqa: F811
    path = Path(__file__).resolve().parents[1] / "migrations/versions/0010_v2_browser_imports.py"
    spec = importlib.util.spec_from_file_location("browser_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with research_engine.begin() as connection:
        monkeypatch.setattr(module.op, "execute", lambda sql: connection.execute(sa.text(sql)))
        module.upgrade()
    return research_engine


@pytest.fixture
def browser(browser_engine, tmp_path):
    root = tmp_path / "storage"
    admission.initialize(browser_engine, root)
    return BrowserImports(browser_engine, root)


def manifest(data):
    return {
        "schema": "canonical-trade-import-v1",
        "instrument_id": "binance:spot:BTCUSDT",
        "trade_date": "2025-03-01",
        "format": "csv",
        "timestamp_encoding": "rfc3339_utc",
        "quote_quantity_mode": "supplied",
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "source_name": "controlled-binance-fixture",
        "source_reference": None,
        "coverage_claim": "observed_only",
    }


DATA = (
    b"source_trade_id,executed_at,price,quantity,quote_quantity,is_buyer_maker,is_best_match\n"
    b"1,2025-03-01T00:00:00Z,10,2,20,true,\n"
)


def test_bound_cli_source_inventory_precedes_worker_and_replay(browser, tmp_path):
    source = tmp_path / "canonical.csv"
    source.write_bytes(DATA)
    staged = service.import_file(browser.engine, browser.root, manifest(DATA), source, "cli-source")
    admission.audit(browser.engine, browser.root)
    with browser.engine.connect() as connection:
        path, size, sha = execute(
            connection,
            "SELECT relative_path,file_bytes,content_sha256 FROM v2_capacity_files",
        ).one()
        charge = execute(connection, "SELECT charged_bytes,state FROM v2_data_charges").one()
    assert size == len(DATA) and sha == hashlib.sha256(DATA).hexdigest()
    assert charge == (len(DATA), "retained")
    assert safe_path(browser.root, path).read_bytes() == DATA
    replay = service.import_file(browser.engine, browser.root, manifest(DATA), source, "cli-source")
    assert replay["replayed"] and replay["import_id"] == staged["import_id"]
    with browser.engine.connect() as connection:
        ticket = dict(execute(connection, "SELECT * FROM v2_admission_tickets").mappings().one())
    # Re-registering an existing receipt returns zero new bytes, never a source refund.
    assert (
        admission.inventory_owned(browser.engine, {"root": str(browser.root), **ticket}, path) == 0
    )
    with browser.engine.connect() as connection:
        assert execute(connection, "SELECT charged_bytes FROM v2_data_charges").scalar_one() == len(
            DATA
        )
    assert service.work(
        browser.engine, browser.root, max_jobs=1, submission_id=staged["submission_id"]
    ) == {"attempted_jobs": 1, "succeeded_jobs": 1, "failed_jobs": 0}
    admission.audit(browser.engine, browser.root)
    completed = jobs.inspect_submission(browser.engine, staged["submission_id"])["jobs"][0]
    assert completed["state"] == "succeeded" and completed["attempt_count"] == 1
    from marketlab.datasets.v2.catalog import inspect_version

    published = inspect_version(browser.engine, browser.root, completed["result_version"])
    assert published["quality"]["accepted_rows"] == 1
    assert published["identity"]["source_sha256"] == hashlib.sha256(DATA).hexdigest()


def test_bound_cli_partial_native_write_retains_exact_source(browser, tmp_path, monkeypatch):
    source = tmp_path / "canonical.csv"
    source.write_bytes(DATA)
    original = Path.open
    prefix = DATA[:19]

    class PrefixFailure:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def write(self, data):
            assert data == DATA
            self.stream.write(prefix)
            self.stream.flush()
            os.fsync(self.stream.fileno())
            raise OSError("actual prefix persisted before write failure")

    def open_source(path, mode="r", *args, **kwargs):
        opened = original(path, mode, *args, **kwargs)
        if mode == "xb" and path.name == "source.csv":
            return PrefixFailure(opened)
        return opened

    monkeypatch.setattr(Path, "open", open_source)
    with pytest.raises(OSError, match="actual prefix persisted"):
        service.import_file(browser.engine, browser.root, manifest(DATA), source, "cli-partial")
    admission.audit(browser.engine, browser.root)
    with browser.engine.connect() as connection:
        receipt = execute(
            connection, "SELECT file_bytes,content_sha256 FROM v2_capacity_files"
        ).one()
        charge = execute(connection, "SELECT charged_bytes,state FROM v2_data_charges").one()
        retained = execute(
            connection, "SELECT retained_bytes FROM v2_storage_reservations WHERE kind='source'"
        ).scalar_one()
        state = execute(connection, "SELECT state FROM v2_admission_tickets").scalar_one()
        imported = execute(connection, "SELECT state,error_code FROM v2_canonical_imports").one()
    assert receipt == (len(prefix), hashlib.sha256(prefix).hexdigest())
    assert charge == (len(prefix), "retained") and retained == len(prefix)
    assert state == "released" and imported == ("failed", "staging_failed")


@pytest.mark.parametrize("failure", ["inventory", "accounting"])
def test_bound_cli_inventory_failure_withholds_release(browser, tmp_path, monkeypatch, failure):
    source = tmp_path / "canonical.csv"
    source.write_bytes(DATA)

    def failed_inventory(*_):
        raise V2Error("unavailable", "final reconciliation deliberately unavailable")

    if failure == "inventory":
        monkeypatch.setattr(admission, "inventory_owned", failed_inventory)
    else:
        original = service._source_account
        calls = 0

        def failed_final_accounting(connection, identity, retained):
            nonlocal calls
            calls += 1
            if calls == 2:
                failed_inventory()
            return original(connection, identity, retained)

        monkeypatch.setattr(service, "_source_account", failed_final_accounting)
    with pytest.raises(V2Error, match="final reconciliation deliberately unavailable"):
        service.import_file(browser.engine, browser.root, manifest(DATA), source, "cli-inventory")
    with browser.engine.connect() as connection:
        assert (
            execute(connection, "SELECT state FROM v2_admission_tickets").scalar_one() == "active"
        )
        assert execute(connection, "SELECT charged_bytes,state FROM v2_data_charges").one() == (
            len(DATA),
            "reserved",
        )
        assert execute(connection, "SELECT count(*) FROM v2_capacity_files").scalar_one() == (
            0 if failure == "inventory" else 1
        )
    assert next((browser.root / "staging-v2").rglob("source.csv")).read_bytes() == DATA


def request(data, token, length=None):
    sent = False

    async def receive():
        nonlocal sent
        assert not sent
        sent = True
        return {"type": "http.request", "body": data, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "PUT",
            "path": "/",
            "headers": [
                (b"content-length", str(len(data) if length is None else length).encode()),
                (b"content-type", b"application/octet-stream"),
                (b"x-upload-token", token.encode()),
            ],
        },
        receive,
    )


def create(browser, key="create", data=DATA):
    return browser.create({"manifest": manifest(data), "content_length": len(data)}, key)


def test_migration_preserves_cli_and_requires_runtime_binding(browser_engine, tmp_path):
    with pytest.raises(V2Error, match="initialization"):
        admission.acquire(browser_engine, tmp_path, "upload", 1)
    receipt = admission.initialize(browser_engine, tmp_path)
    assert receipt["retained_bytes"] == 0
    with pytest.raises(V2Error, match="binding"):
        admission.acquire(browser_engine, tmp_path / "different", "upload", 1)


@pytest.mark.asyncio
async def test_actual_upload_finalize_replay_and_normalization(browser):
    made = create(browser)
    identity, upload = made["id"], made["upload"]
    assert create(browser)["id"] == identity
    token = upload["required_headers"]["X-Upload-Token"]
    uploaded = await browser.receive(identity, request(DATA, token))
    assert uploaded["state"] == "uploaded" and uploaded["received_bytes"] == len(DATA)
    with pytest.raises(V2Error):
        await browser.receive(identity, request(DATA, token))
    body = {"expected_revision": uploaded["revision"], "generation": upload["generation"]}
    finalized = browser.finalize(identity, body, "finalize")
    assert browser.finalize(identity, body, "finalize")["job_id"] == finalized["job_id"]
    result = service.work(
        browser.engine, browser.root, max_jobs=1, submission_id=finalized["submission_id"]
    )
    assert result["succeeded_jobs"] == 1
    status = browser.inspect(identity)
    assert status["state"] == "succeeded" and status["dataset_version_id"]
    assert "X-Upload-Token" not in str(status) and "source_relative_path" not in status
    with browser.engine.connect() as connection:
        assert execute(connection, "SELECT count(*) FROM v2_ingestion_jobs").scalar_one() == 1
        assert (
            execute(
                connection, "SELECT count(*) FROM v2_admission_tickets WHERE state<>'released'"
            ).scalar_one()
            == 0
        )


@pytest.mark.asyncio
async def test_wrong_hash_generation_retained_and_renewal_is_new(browser):
    made = create(browser)
    token = made["upload"]["required_headers"]["X-Upload-Token"]
    with pytest.raises(V2Error):
        await browser.receive(made["id"], request(b"x" * len(DATA), token))
    failed = browser.inspect(made["id"])
    assert failed["state"] == "upload_failed"
    renewed = browser.renew(made["id"], {"expected_revision": failed["revision"]}, "renew")
    assert renewed["upload"]["generation"] != made["upload"]["generation"]
    with browser.engine.connect() as connection:
        rows = (
            execute(connection, "SELECT * FROM v2_storage_reservations ORDER BY created_at")
            .mappings()
            .all()
        )
        assert len(rows) == 2 and rows[0]["retained_bytes"] == len(DATA)
        assert rows[1]["reserved_bytes"] == len(DATA)


def test_staged_slots_and_cancel_release_without_refunding_bytes(browser):
    made = [create(browser, f"slot-{i}") for i in range(4)]
    with pytest.raises(V2Error, match="capacity"):
        create(browser, "fifth")
    browser.cancel(made[0]["id"], {"expected_revision": 0}, "cancel")
    assert create(browser, "after-cancel")["state"] == "awaiting_upload"


def test_running_slot_pressure_spends_no_numerical_attempt(browser):
    tickets = [admission.acquire(browser.engine, browser.root, "research") for _ in range(8)]
    submitted = jobs.submit(
        browser.engine,
        {
            "schema": "daily-ingestion-v2",
            "adapter": "binance_daily",
            "instrument_ids": ["binance:spot:BTCUSDT"],
            "from_date": "2025-03-01",
            "before_date": "2025-03-02",
        },
        "pressure",
    )
    assert jobs.claim(browser.engine, submitted["submission_id"]) is None
    assert (
        jobs.inspect_submission(browser.engine, submitted["submission_id"])["jobs"][0][
            "attempt_count"
        ]
        == 0
    )
    for ticket in tickets:
        admission.finish(browser.engine, ticket, 0)


def test_existing_retained_bytes_count_in_root_baseline(browser_engine, tmp_path):
    root = tmp_path / "storage"
    root.mkdir()
    (root / "retained-failed-source").write_bytes(b"x" * 12345)
    receipt = admission.initialize(browser_engine, root)
    assert receipt["retained_bytes"] == 12345
    with browser_engine.connect() as connection:
        assert (
            execute(connection, "SELECT baseline_bytes FROM v2_capacity_roots").scalar_one()
            == 12345
        )


def test_unmanaged_write_marks_unready_and_blocks_new_intake(browser):
    (browser.root / "unmanaged").write_bytes(b"unaccounted")
    with pytest.raises(V2Error, match="Unmanaged"):
        create(browser)
    with browser.engine.connect() as connection:
        assert not execute(connection, "SELECT ready FROM v2_capacity_roots").scalar_one()
        assert execute(connection, "SELECT count(*) FROM v2_canonical_imports").scalar_one() == 0
    admission.initialize(browser.engine, browser.root)
    assert create(browser)["state"] == "awaiting_upload"


def test_changed_or_missing_baseline_never_continues_with_stale_receipt(browser_engine, tmp_path):
    root = tmp_path / "storage"
    root.mkdir()
    retained = root / "historical-file"
    retained.write_bytes(b"retained")
    admission.initialize(browser_engine, root)
    retained.unlink()
    with pytest.raises(V2Error, match="missing"):
        admission.acquire(browser_engine, root, "upload", 1)
    with browser_engine.connect() as connection:
        assert not execute(connection, "SELECT ready FROM v2_capacity_roots").scalar_one()


def test_initialization_with_live_writer_keeps_readiness_closed(browser):
    ticket = admission.acquire(browser.engine, browser.root, "research")
    with pytest.raises(V2Error, match="drain"):
        admission.initialize(browser.engine, browser.root)
    with browser.engine.connect() as connection:
        assert not execute(connection, "SELECT ready FROM v2_capacity_roots").scalar_one()
    admission.finish(browser.engine, ticket, 0)
    admission.initialize(browser.engine, browser.root)


def test_actual_bound_root_legacy_ingestion_is_charged_and_replay_not_double_charged(
    browser, tmp_path
):
    from marketlab.datasets import ingest_archive

    with browser.engine.begin() as connection:
        for table in ("ingestion_submissions", "ingestion_jobs", "ingestion_attempts"):
            connection.exec_driver_sql(f"CREATE TABLE {table} (LIKE public.{table} INCLUDING ALL)")
    archive, checksum = archive_files(tmp_path / "legacy-input", [ROW, ROW])
    first = ingest_archive(browser.engine, browser.root, archive, checksum)
    second = ingest_archive(browser.engine, browser.root, archive, checksum)
    assert first == second
    with browser.engine.connect() as connection:
        charges = execute(
            connection, "SELECT charged_bytes,state FROM v2_data_charges ORDER BY created_at"
        ).fetchall()
        assert charges[0][0] > 0 and charges[0][1] == "retained"
        assert charges[1][0] == 0 and charges[1][1] == "released"
    admission.audit(browser.engine, browser.root)


def test_expired_unclaimed_slots_allow_explicit_renewal(browser):
    created = [create(browser, f"expired-{i}") for i in range(4)]
    with browser.engine.begin() as connection:
        execute(
            connection,
            "UPDATE v2_upload_generations SET expires_at=clock_timestamp()-interval '1 second'",
        )
    renewed = browser.renew(created[0]["id"], {"expected_revision": 0}, "renew-expired")
    assert renewed["upload"]["generation"] != created[0]["upload"]["generation"]
    with browser.engine.connect() as connection:
        assert (
            execute(
                connection, "SELECT count(*) FROM v2_admission_tickets WHERE state<>'released'"
            ).scalar_one()
            == 4
        )
        old = execute(
            connection,
            "SELECT state,reserved_bytes,retained_bytes FROM v2_storage_reservations "
            "ORDER BY created_at LIMIT 1",
        ).one()
        assert old == ("released", 0, 0)


@pytest.mark.asyncio
async def test_partial_native_write_failure_charges_actual_drained_file(browser, monkeypatch):
    made = create(browser)
    real_open = Path.open

    class PartialWriter:
        def __init__(self, stream):
            self.stream = stream

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def write(self, data):
            self.stream.write(data[:17])
            self.stream.flush()
            raise OSError("controlled partial write")

    def opening(path, mode="r", *args, **kwargs):
        stream = real_open(path, mode, *args, **kwargs)
        return PartialWriter(stream) if mode == "xb" and path.name == "source.csv" else stream

    monkeypatch.setattr(Path, "open", opening)
    with pytest.raises(OSError):
        await browser.receive(
            made["id"], request(DATA, made["upload"]["required_headers"]["X-Upload-Token"])
        )
    with browser.engine.connect() as connection:
        assert execute(connection, "SELECT charged_bytes FROM v2_data_charges").scalar_one() == 17
        assert (
            execute(connection, "SELECT retained_bytes FROM v2_storage_reservations").scalar_one()
            == 17
        )
        assert (
            execute(
                connection, "SELECT count(*) FROM v2_admission_tickets WHERE state<>'released'"
            ).scalar_one()
            == 0
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "recover_cancel", [False, True], ids=["request-cancel", "lease-recover-cancel"]
)
async def test_receiver_cancellation_keeps_ticket_until_native_write_drains(
    browser, monkeypatch, recover_cancel
):
    import asyncio

    made = create(browser)
    started, released = threading.Event(), threading.Event()
    real_open = Path.open

    class PausedWriter:
        def __init__(self, stream):
            self.stream = stream

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def write(self, data):
            started.set()
            assert released.wait(10)
            return self.stream.write(data)

    def opening(path, mode="r", *args, **kwargs):
        stream = real_open(path, mode, *args, **kwargs)
        return PausedWriter(stream) if mode == "xb" and path.name == "source.csv" else stream

    monkeypatch.setattr(Path, "open", opening)
    task = asyncio.create_task(
        browser.receive(
            made["id"], request(DATA, made["upload"]["required_headers"]["X-Upload-Token"])
        )
    )
    assert await asyncio.to_thread(started.wait, 3)
    if recover_cancel:
        with browser.engine.begin() as connection:
            execute(
                connection,
                "UPDATE v2_canonical_imports SET staging_lease_until="
                "clock_timestamp()-interval '1 second' WHERE import_id=:id",
                id=made["id"],
            )
            execute(
                connection,
                "UPDATE v2_upload_generations SET lease_until="
                "clock_timestamp()-interval '1 second' WHERE import_id=:id",
                id=made["id"],
            )
        recovered = browser.inspect(made["id"])
        assert recovered["state"] == "upload_failed"
        browser.cancel(made["id"], {"expected_revision": recovered["revision"]}, "cancel-recovered")
    else:
        task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    with browser.engine.connect() as connection:
        assert (
            execute(
                connection, "SELECT count(*) FROM v2_admission_tickets WHERE state<>'released'"
            ).scalar_one()
            == 1
        )
        assert execute(
            connection, "SELECT reserved_bytes FROM v2_storage_reservations"
        ).scalar_one() == len(DATA)
    released.set()
    with pytest.raises(V2Error if recover_cancel else asyncio.CancelledError):
        await task
    with browser.engine.connect() as connection:
        assert (
            execute(
                connection, "SELECT count(*) FROM v2_admission_tickets WHERE state<>'released'"
            ).scalar_one()
            == 0
        )
        assert execute(connection, "SELECT charged_bytes FROM v2_data_charges").scalar_one() == len(
            DATA
        )


def test_coverage_exact_window_alternative_bound(browser_engine, tmp_path):
    from marketlab.datasets.v2.catalog import coverage

    with browser_engine.begin() as connection:
        execute(
            connection,
            "INSERT INTO v2_dataset_versions SELECT lpad(to_hex(i),64,'0'),"
            "instrument_id,semantic_sha256,DATE '2025-03-01',repeat('a',64),repeat('b',64),"
            "repeat('c',64),repeat('d',64),'spot-trades-v2','binance-spot-trades-v2',repeat('e',64),"
            "'datasets-v2/'||i||'/manifest.json',1,TIMESTAMPTZ '2025-03-01 00:00:00+00',"
            "TIMESTAMPTZ '2025-03-01 00:00:00+00',clock_timestamp() FROM v2_instruments,"
            "generate_series(1,1000) i WHERE instrument_id='binance:spot:BTCUSDT'",
        )
    result = coverage(
        browser_engine, "binance:spot:BTCUSDT", "2025-03-01", "2025-03-02", root=tmp_path
    )
    day = result["days"][0]
    assert len(day["versions"]) == 100 and day["next_cursor"]
    assert not day["observed_bounds_complete"] and day["observed_start"] is None
    with browser_engine.begin() as connection:
        execute(
            connection,
            "INSERT INTO v2_dataset_versions SELECT repeat('f',64),instrument_id,"
            "semantic_sha256,DATE '2025-03-01',repeat('a',64),repeat('b',64),repeat('c',64),"
            "repeat('d',64),'spot-trades-v2','binance-spot-trades-v2',repeat('e',64),'extra/manifest.json',"
            "1,TIMESTAMPTZ '2025-03-01 00:00:00+00',TIMESTAMPTZ '2025-03-01 00:00:00+00',"
            "clock_timestamp() FROM v2_instruments WHERE instrument_id='binance:spot:BTCUSDT'",
        )
    with pytest.raises(V2Error) as error:
        coverage(browser_engine, "binance:spot:BTCUSDT", "2025-03-01", "2025-03-02", root=tmp_path)
    assert error.value.code == "coverage_too_dense"


def test_corrupt_receipt_fails_closed(browser):
    with browser.engine.begin() as connection:
        execute(connection, "UPDATE v2_capacity_roots SET receipt_sha256=repeat('0',64)")
    with pytest.raises(V2Error, match="receipt"):
        create(browser)


def test_lower_quota_fixture_exact_boundary_and_one_over(browser, monkeypatch):
    # Controlled fixture ceiling, separate from actual 100 GiB resource acceptance.
    monkeypatch.setattr(admission, "DATA_LIMIT", len(DATA))
    first = create(browser)
    with pytest.raises(V2Error, match="capacity"):
        create(browser, "one-over")
    browser.cancel(first["id"], {"expected_revision": 0}, "quota-cancel")
    assert create(browser, "after-drain")["state"] == "awaiting_upload"


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["extra-file", "grow-file"])
async def test_completed_managed_path_cannot_hide_unaccounted_growth(browser, mutation):
    made = create(browser)
    uploaded = await browser.receive(
        made["id"], request(DATA, made["upload"]["required_headers"]["X-Upload-Token"])
    )
    finalized = browser.finalize(
        made["id"],
        {"expected_revision": uploaded["revision"], "generation": made["upload"]["generation"]},
        "finalize-audit",
    )
    service.work(browser.engine, browser.root, max_jobs=1, submission_id=finalized["submission_id"])
    with browser.engine.connect() as connection:
        relative = execute(
            connection, "SELECT manifest_relative_path FROM v2_dataset_versions"
        ).scalar_one()
    directory = safe_path(browser.root, relative).parent
    if mutation == "extra-file":
        (directory / "unmanaged.extra").write_bytes(b"hidden bytes")
    else:
        with (directory / "trades.parquet").open("ab") as outgoing:
            outgoing.write(b"hidden growth")
    with pytest.raises(V2Error):
        create(browser, "after-hidden-growth")
    with browser.engine.connect() as connection:
        assert not execute(connection, "SELECT ready FROM v2_capacity_roots").scalar_one()
        assert execute(connection, "SELECT count(*) FROM v2_canonical_imports").scalar_one() == 1


def test_live_ticket_prefix_is_bounded_by_its_reserved_ceiling(browser):
    made = create(browser)
    generation = browser.claim(
        made["id"], str(len(DATA)), made["upload"]["required_headers"]["X-Upload-Token"]
    )
    path = safe_path(browser.root, generation["relative_path"])
    path.parent.mkdir(parents=True)
    path.write_bytes(b"x" * (len(DATA) + 1))
    with pytest.raises(V2Error):
        admission.audit(browser.engine, browser.root)
    with browser.engine.connect() as connection:
        assert not execute(connection, "SELECT ready FROM v2_capacity_roots").scalar_one()


def test_renewal_never_waits_for_root_lock_while_holding_import(browser, monkeypatch):
    made = create(browser)
    with browser.engine.begin() as connection:
        execute(
            connection,
            "UPDATE v2_upload_generations SET expires_at=clock_timestamp()-interval '1 second'",
        )
    generation_entered, root_held = threading.Event(), threading.Event()
    original = browser._generation

    def handoff(*args, **kwargs):
        generation_entered.set()
        assert root_held.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(browser, "_generation", handoff)

    def root_then_import():
        assert generation_entered.wait(5)
        with browser.engine.begin() as connection:
            root_lock(connection, "v2-space:" + str(browser.root))
            root_held.set()
            execute(
                connection,
                "SELECT import_id FROM v2_canonical_imports WHERE import_id=:id FOR UPDATE",
                id=made["id"],
            )

    with ThreadPoolExecutor(2) as pool:
        renewed = pool.submit(
            browser.renew, made["id"], {"expected_revision": 0}, "contended-renewal"
        )
        observer = pool.submit(root_then_import)
        assert renewed.result(timeout=10)["state"] == "awaiting_upload"
        observer.result(timeout=10)


def test_audit_snapshot_tolerates_concurrent_legitimate_inventory_commit(browser, monkeypatch):
    ticket = admission.acquire(browser.engine, browser.root, "upload", 32)
    admission.mark_path(browser.engine, ticket, "owned-completion")
    path = browser.root / "owned-completion"
    path.write_bytes(b"managed")
    original = admission._files
    completed = False

    def scanning(root, **kwargs):
        nonlocal completed
        for item in original(root, **kwargs):
            yield item
            if kwargs.get("hashes") is False and not completed:
                completed = True
                admission.inventory_owned(browser.engine, ticket, "owned-completion")
                admission.finish(browser.engine, ticket, len(b"managed"), "owned-completion")

    monkeypatch.setattr(admission, "_files", scanning)
    admission.audit(browser.engine, browser.root)
    with browser.engine.connect() as connection:
        assert execute(connection, "SELECT ready FROM v2_capacity_roots").scalar_one()


def test_audit_snapshot_tolerates_owned_scratch_disappearing(browser, monkeypatch):
    ticket = admission.acquire(browser.engine, browser.root, "research", 0)
    admission.mark_path(browser.engine, ticket, "owned-scratch")
    path = browser.root / "owned-scratch"
    path.mkdir()
    (path / "spill").write_bytes(b"transient")
    original = admission._files

    def scanning(root, **kwargs):
        if kwargs.get("hashes") is False:
            (path / "spill").unlink()
            assert kwargs["missing"]("owned-scratch/spill")
            yield from original(root, **kwargs)
        else:
            yield from original(root, **kwargs)

    monkeypatch.setattr(admission, "_files", scanning)
    admission.audit(browser.engine, browser.root)
    admission.finish(browser.engine, ticket, 0)


def test_audit_retries_new_upload_ownership_before_any_inventory_commit(browser, monkeypatch):
    original = admission._files
    started = []

    def scanning(root, **kwargs):
        if kwargs.get("hashes") is False and not started:
            started.append(None)  # Recursive admission audit sees the original empty root.
            made = create(browser, "concurrent-new-owner")
            generation = browser.claim(
                made["id"], str(len(DATA)), made["upload"]["required_headers"]["X-Upload-Token"]
            )
            path = safe_path(browser.root, generation["relative_path"])
            path.parent.mkdir(parents=True)
            path.write_bytes(b"partial")
            started[0] = generation
        yield from original(root, **kwargs)

    monkeypatch.setattr(admission, "_files", scanning)
    admission.audit(browser.engine, browser.root)
    with browser.engine.connect() as connection:
        assert execute(connection, "SELECT ready FROM v2_capacity_roots").scalar_one()
        assert execute(connection, "SELECT count(*) FROM v2_capacity_files").scalar_one() == 0
    generation = started[0]
    browser._failed(generation, 7)
    browser._drained_source(generation, 7)
    admission.finish(browser.engine, generation["ticket"], 7, generation["relative_path"])


def test_physical_handoff_is_counted_in_one_statement_snapshot(browser, monkeypatch):
    from marketlab.datasets.v2 import capacity

    made = create(browser)
    browser.cancel(made["id"], {"expected_revision": 0}, "handoff-retire-empty")
    ticket = admission.acquire(
        browser.engine, browser.root, "upload", len(DATA), physical_bytes=len(DATA)
    )
    original = capacity.execute
    gate = int.from_bytes(uuid4().bytes[:8], "big", signed=True)
    reader_pid = []

    def observing(connection, statement, **values):
        if "sum(reserved_bytes)" in statement:
            # A volatile advisory wait fixes the statement's MVCC snapshot
            # before the other connection transfers ticket -> source budget.
            statement += " + (SELECT 0::bigint FROM pg_advisory_xact_lock(:test_gate))"
            values["test_gate"] = gate
        return original(connection, statement, **values)

    monkeypatch.setattr(capacity, "execute", observing)

    def read_budget():
        with browser.engine.begin() as connection:
            reader_pid.append(execute(connection, "SELECT pg_backend_pid()").scalar_one())
            return capacity.outstanding(connection)

    with ThreadPoolExecutor(1) as pool:
        with browser.engine.begin() as blocker:
            execute(blocker, "SELECT pg_advisory_xact_lock(:key)", key=gate)
            future = pool.submit(read_budget)
            deadline = time.monotonic() + 5
            while True:
                with browser.engine.connect() as observer:
                    waiting = (
                        bool(reader_pid)
                        and execute(
                            observer,
                            "SELECT wait_event_type='Lock' FROM pg_stat_activity WHERE pid=:pid",
                            pid=reader_pid[0],
                        ).scalar_one()
                    )
                if waiting:
                    break
                assert time.monotonic() < deadline
                time.sleep(0.01)
            with browser.engine.begin() as transfer:
                execute(
                    transfer,
                    "UPDATE v2_admission_tickets SET physical_bytes=0 WHERE ticket_id=:id",
                    id=ticket["ticket_id"],
                )
                execute(
                    transfer,
                    "INSERT INTO v2_storage_reservations VALUES "
                    "(:id,:import_id,NULL,NULL,'source',:bytes,0,:bytes,'reserved','test-handoff-source',"
                    "clock_timestamp(),clock_timestamp())",
                    id=uuid4(),
                    import_id=made["id"],
                    bytes=len(DATA),
                )
        assert future.result(timeout=5) == len(DATA)
    admission.finish(browser.engine, ticket, 0)


_DEAD_UPLOAD = r"""
import json, os, sys, threading
from pathlib import Path
import sqlalchemy as sa
from marketlab.datasets.v2.browser_imports import BrowserImports
from marketlab.datasets.v2.common import safe_path
from marketlab.datasets.v2.native_identity import current
config = json.loads(Path(sys.argv[1]).read_text())
engine = sa.create_engine(config['url'],
                         connect_args={'options':'-c search_path='+config['schema']})
service = BrowserImports(engine, Path(config['root']))
made = service.create(config['body'], 'native-dead-owner')
generation = service.claim(made['id'], str(config['body']['content_length']),
                           made['upload']['required_headers']['X-Upload-Token'])
target = safe_path(Path(config['root']), generation['relative_path'])
target.parent.mkdir(parents=True)
with target.open('xb') as output:
    output.write(b'x'*31)
    output.flush()
    os.fsync(output.fileno())
Path(config['ready']).write_text(json.dumps({'id':made['id'], 'identity':current()}))
threading.Event().wait(120)
"""


@pytest.mark.asyncio
async def test_native_dead_partial_upload_reconciles_then_renews_after_real_lease(
    browser, tmp_path
):
    import asyncio

    ready, config = tmp_path / "dead-ready.json", tmp_path / "dead-private.json"
    with browser.engine.connect() as connection:
        schema = execute(connection, "SELECT current_schema()").scalar_one()
    config.write_text(
        json.dumps(
            {
                "url": browser.engine.url.render_as_string(hide_password=False),
                "schema": schema,
                "root": str(browser.root),
                "ready": str(ready),
                "body": {"manifest": manifest(DATA), "content_length": len(DATA)},
            }
        )
    )
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path))
    process = await asyncio.to_thread(
        subprocess.Popen,
        [native_identity.current()["executable"], "-c", _DEAD_UPLOAD, str(config)],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 15
        while not ready.exists():
            assert process.poll() is None and time.monotonic() < deadline
            await asyncio.sleep(0.02)
        observed = json.loads(ready.read_text())
        assert native_identity.child(process.pid) == observed["identity"]
        process.kill()
        process.wait(timeout=10)
        assert native_identity.dead(observed["identity"])
        receipt = admission.initialize(browser.engine, browser.root)
        assert receipt["retained_bytes"] == 31
        with browser.engine.connect() as connection:
            assert (
                execute(
                    connection, "SELECT count(*) FROM v2_admission_tickets WHERE state<>'released'"
                ).scalar_one()
                == 0
            )
            assert (
                execute(
                    connection, "SELECT retained_bytes FROM v2_storage_reservations"
                ).scalar_one()
                == 31
            )
        deadline = time.monotonic() + 70
        while True:
            status = browser.inspect(observed["id"])
            if status["state"] == "upload_failed":
                break
            assert time.monotonic() < deadline
            await asyncio.sleep(0.1)
        renewed = browser.renew(
            observed["id"], {"expected_revision": status["revision"]}, "native-renew"
        )
        uploaded = await browser.receive(
            observed["id"], request(DATA, renewed["upload"]["required_headers"]["X-Upload-Token"])
        )
        assert uploaded["state"] == "uploaded"
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)


def test_migrated_missing_capacity_ledger_fails_closed(browser_engine, tmp_path):
    with browser_engine.begin() as connection:
        execute(connection, "CREATE TABLE alembic_version(version_num varchar(32) PRIMARY KEY)")
        execute(connection, "INSERT INTO alembic_version VALUES ('0010_v2_browser_imports')")
        execute(connection, "DROP TABLE v2_capacity_roots CASCADE")
    with pytest.raises(V2Error, match="missing"):
        admission.acquire(browser_engine, tmp_path, "upload", 1)


def test_concurrent_initialization_activates_only_current_inventory_epoch(
    browser_engine, tmp_path, monkeypatch
):
    original = admission._files
    barrier = threading.Barrier(2)

    def scanning(root, **kwargs):
        barrier.wait(timeout=5)
        yield from original(root, **kwargs)

    monkeypatch.setattr(admission, "_files", scanning)
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(admission.initialize, browser_engine, tmp_path) for _ in range(2)]
        results = []
        for future in futures:
            try:
                results.append(future.result())
            except V2Error:
                results.append(None)
    assert sum(value is not None for value in results) == 1
    with browser_engine.connect() as connection:
        row = execute(connection, "SELECT ready,epoch FROM v2_capacity_roots").one()
    assert row == (True, 2)


@pytest.mark.asyncio
async def test_bound_legacy_dataset_bars_persist_verifier_children_before_dispatch(
    browser, tmp_path
):
    import json

    from marketlab.analytics.bars import BarService as LegacyBars
    from marketlab.analytics.v2 import BarService, BarsRequest
    from marketlab.datasets import ingest_archive

    with browser.engine.begin() as connection:
        for table in ("ingestion_submissions", "ingestion_jobs", "ingestion_attempts"):
            connection.exec_driver_sql(f"CREATE TABLE {table} (LIKE public.{table} INCLUDING ALL)")
    archive, checksum = archive_files(tmp_path / "legacy-child-input", [ROW])
    result = ingest_archive(browser.engine, browser.root, archive, checksum)
    base = LegacyBars(browser.engine, browser.root)
    bars = BarService(base)
    try:
        value, _ = await bars.read(
            BarsRequest.create(
                versions=[result["dataset_version_id"]],
                instrument_id="binance:spot:BTCUSDT",
                interval="5m",
                start="2025-01-01T00:00:00Z",
                end="2025-01-01T00:05:00Z",
            )
        )
        assert value["returned_buckets"] == 1
    finally:
        await bars.close()
        await base.close()
    with browser.engine.connect() as connection:
        records = execute(
            connection,
            "SELECT native_identity,state FROM v2_admission_tickets WHERE role='research'",
        ).fetchall()
    assert records and all(row[1] == "released" for row in records)
    assert any(len(json.loads(row[0]).get("children", [])) == 2 for row in records)
    assert all(not json.loads(row[0]).get("children_pending", False) for row in records)
