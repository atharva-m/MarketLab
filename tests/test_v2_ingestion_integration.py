"""Real PostgreSQL v2 durable transitions in private disposable schemas."""

import importlib.util
import os
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from marketlab.config import Settings
from marketlab.datasets.v2 import core, jobs, service
from marketlab.datasets.v2.common import V2Error, sha256_file

pytestmark = pytest.mark.integration


@pytest.fixture
def v2_engine() -> Iterator[Engine]:
    if "MARKETLAB_DATABASE_URL" not in os.environ:
        pytest.skip("requires owned PostgreSQL")
    settings = Settings()
    base = sa.create_engine(settings.sqlalchemy_url)
    schema = "test_v2_" + uuid4().hex
    with base.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    engine = sa.create_engine(
        settings.sqlalchemy_url, connect_args={"options": f"-c search_path={schema}"}
    )
    spec = importlib.util.spec_from_file_location(
        "v2_migration",
        Path(__file__).resolve().parents[1] / "migrations/versions/0008_v2_ingestion.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(module.DDL)
            connection.exec_driver_sql(
                "CREATE TABLE dataset_versions (LIKE public.dataset_versions INCLUDING ALL)"
            )
        yield engine
    finally:
        engine.dispose()
        with base.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


def body() -> dict[str, Any]:
    return dict(
        schema="daily-ingestion-v2",
        adapter="binance_daily",
        instrument_ids=["binance:spot:BTCUSDT"],
        from_date="2025-02-01",
        before_date="2025-02-02",
    )


def test_submit_replay_conflict_and_claim_concurrency(v2_engine: Engine) -> None:
    result = jobs.submit(v2_engine, body(), "key")
    assert jobs.submit(v2_engine, body(), "key")["submission_id"] == result["submission_id"]
    changed = dict(body(), from_date="2025-02-02", before_date="2025-02-03")
    with pytest.raises(V2Error):
        jobs.submit(v2_engine, changed, "key")
    claimed = []

    def claim() -> None:
        claimed.append(jobs.claim(v2_engine, result["submission_id"]))

    threads = [threading.Thread(target=claim) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len([x for x in claimed if x is not None]) == 1


def test_expiry_fencing_attempt_budget(v2_engine: Engine) -> None:
    result = jobs.submit(v2_engine, body(), "budget")
    first = jobs.claim(v2_engine, result["submission_id"])
    assert first
    current = first
    for count in (2, 3):
        with v2_engine.begin() as c:
            c.execute(
                sa.text(
                    "UPDATE v2_ingestion_jobs SET lease_until=clock_timestamp()-interval "
                    "'1 second' WHERE job_id=:id"
                ),
                {"id": current["job_id"]},
            )
        current = jobs.claim(v2_engine, result["submission_id"])
        assert current
        assert (
            current["attempt_count"] == count and current["fencing_token"] > first["fencing_token"]
        )
        assert not jobs.heartbeat(v2_engine, first)
    with v2_engine.begin() as c:
        c.execute(
            sa.text(
                "UPDATE v2_ingestion_jobs SET lease_until=clock_timestamp()-interval '1 "
                "second' WHERE job_id=:id"
            ),
            {"id": current["job_id"]},
        )
    assert jobs.claim(v2_engine, result["submission_id"]) is None
    assert (
        jobs.inspect_submission(v2_engine, result["submission_id"])["jobs"][0]["state"] == "failed"
    )


def test_cancel_replay_and_running_fence(v2_engine: Engine) -> None:
    result = jobs.submit(v2_engine, body(), "cancel")
    claimed = jobs.claim(v2_engine, result["submission_id"])
    assert claimed
    response = jobs.cancel(v2_engine, str(claimed["job_id"]), claimed["revision"], "cancel-key")
    assert response["cancel_requested"]
    assert jobs.cancel(v2_engine, str(claimed["job_id"]), claimed["revision"], "cancel-key")[
        "replayed"
    ]
    with pytest.raises(V2Error):
        with core.transaction(v2_engine) as c:
            jobs.fence(c, claimed)
    jobs.fail(v2_engine, claimed, V2Error("cancelled"))
    assert (
        jobs.inspect_submission(v2_engine, result["submission_id"])["jobs"][0]["state"]
        == "cancelled"
    )


def test_registry_label_disable_and_replay(v2_engine: Engine) -> None:
    identity = "binance:spot:BTCUSDT"
    updated = core.update_instrument(
        v2_engine, identity, {"expected_revision": 0, "display_name": "Bitcoin"}, "label"
    )
    assert updated["revision"] == 1
    with pytest.raises(V2Error):
        core.update_instrument(
            v2_engine, identity, {"expected_revision": 0, "enabled": False}, "stale"
        )
    core.update_instrument(
        v2_engine, identity, {"expected_revision": 1, "enabled": False}, "disable"
    )
    with pytest.raises(V2Error):
        jobs.submit(v2_engine, body(), "disabled")


def test_canonical_copy_enqueue_replay_without_input(v2_engine: Engine, tmp_path: Path) -> None:
    source = tmp_path / "in.csv"
    source.write_text("x", encoding="utf-8")
    metadata = dict(
        schema="canonical-trade-import-v1",
        instrument_id="binance:spot:BTCUSDT",
        trade_date="2025-03-01",
        format="csv",
        timestamp_encoding="rfc3339_utc",
        quote_quantity_mode="supplied",
        source_sha256=sha256_file(source),
        source_name="reference",
        source_reference=None,
        coverage_claim="observed_only",
    )
    result = service.import_file(v2_engine, tmp_path / "store", metadata, source, "import")
    source.unlink()
    replay = service.import_file(v2_engine, tmp_path / "store", metadata, source, "import")
    assert replay["job_id"] == result["job_id"] and replay["replayed"]
    assert service.inspect_import(v2_engine, result["import_id"])["state"] == "queued"
    job = jobs.claim(v2_engine, result["submission_id"])
    assert job
    assert job["import_id"] == core.uid(result["import_id"])


def test_reservation_null_fence_rejected(v2_engine: Engine, tmp_path: Path) -> None:
    result = jobs.submit(v2_engine, body(), "reserve")
    job = jobs.claim(v2_engine, result["submission_id"])
    assert job
    with pytest.raises(sa.exc.IntegrityError):
        with v2_engine.begin() as c:
            c.execute(
                sa.text(
                    "INSERT INTO v2_storage_reservations VALUES "
                    "(:id,NULL,:job,NULL,'output',1,0,1,'reserved','x',clock_timestamp(),clock_timestamp())"
                ),
                {"id": uuid4(), "job": job["job_id"]},
            )


def canonical_input(
    tmp_path: Path, *, price: str = "2", identifier: str = "2"
) -> tuple[Path, dict[str, Any]]:
    source = tmp_path / (uuid4().hex + ".csv")
    source.write_text(
        "source_trade_id,executed_at,price,quantity,quote_quantity,is_buyer_maker,is_best_match\n"
        f"{identifier},2025-03-01T00:00:00.000001Z,{price},1,2.01,true,\n",
        encoding="utf-8",
    )
    return source, dict(
        schema="canonical-trade-import-v1",
        instrument_id="binance:spot:BTCUSDT",
        trade_date="2025-03-01",
        format="csv",
        timestamp_encoding="rfc3339_utc",
        quote_quantity_mode="supplied",
        source_sha256=sha256_file(source),
        source_name="reference",
        source_reference=None,
        coverage_claim="observed_only",
    )


def test_claim_does_not_steal_committed_heartbeat(
    v2_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, metadata = canonical_input(tmp_path)
    result = service.import_file(v2_engine, tmp_path / "store", metadata, source, "race")
    current = jobs.claim(v2_engine, result["submission_id"])
    assert current is not None
    with v2_engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE v2_ingestion_jobs SET lease_until=clock_timestamp()+interval '1 second' "
                "WHERE job_id=:id"
            ),
            {"id": current["job_id"]},
        )
    heartbeat_connection = v2_engine.connect()
    heartbeat_transaction = heartbeat_connection.begin()
    heartbeat_connection.execute(
        sa.text(
            "UPDATE v2_ingestion_jobs SET lease_until=clock_timestamp()+interval '60 seconds' "
            "WHERE job_id=:id AND lease_until>clock_timestamp()"
        ),
        {"id": current["job_id"]},
    )
    # The old committed tuple expires while a valid heartbeat update is uncommitted.
    time.sleep(1.1)
    original = jobs.one
    observed = []

    def interleave(connection: Any, query: str, **values: Any) -> Any:
        value = original(connection, query, **values)
        if query.startswith("SELECT i.import_id") and value is not None:
            observed.append(value)
            heartbeat_transaction.commit()
        return value

    monkeypatch.setattr(jobs, "one", interleave)
    try:
        assert jobs.claim(v2_engine, result["submission_id"]) is None
        assert observed
        assert jobs.heartbeat(v2_engine, current)
        assert (
            jobs.inspect_submission(v2_engine, result["submission_id"])["jobs"][0]["attempt_count"]
            == 1
        )
    finally:
        if heartbeat_transaction.is_active:
            heartbeat_transaction.rollback()
        heartbeat_connection.close()


def test_publish_readback_reuse_alternative_and_corruption(
    v2_engine: Engine, tmp_path: Path
) -> None:
    from marketlab.datasets.v2 import catalog

    root = tmp_path / "store"
    source, metadata = canonical_input(tmp_path)
    initial = service.import_file(v2_engine, root, metadata, source, "original")
    claimed = jobs.claim(v2_engine, initial["submission_id"])
    assert claimed is not None
    service.run_claim(v2_engine, root, claimed)
    first_job = jobs.inspect_submission(v2_engine, initial["submission_id"])["jobs"][0]
    version = first_job["result_version"]
    verified = catalog.inspect_version(v2_engine, root, version)
    assert verified["quality"]["accepted_rows"] == 1
    repeated = service.import_file(v2_engine, root, metadata, source, "same-source")
    assert (
        service.work(v2_engine, root, submission_id=repeated["submission_id"])["succeeded_jobs"]
        == 1
    )
    assert (
        jobs.inspect_submission(v2_engine, repeated["submission_id"])["jobs"][0]["result_version"]
        == version
    )
    changed_source, changed_metadata = canonical_input(tmp_path, price="3")
    alternative = service.import_file(
        v2_engine, root, changed_metadata, changed_source, "correction"
    )
    assert (
        service.work(v2_engine, root, submission_id=alternative["submission_id"])["succeeded_jobs"]
        == 1
    )
    new_version = jobs.inspect_submission(v2_engine, alternative["submission_id"])["jobs"][0][
        "result_version"
    ]
    assert new_version != version
    assert catalog.inspect_version(v2_engine, root, version) == verified
    listing = catalog.datasets(v2_engine, limit=1)
    assert len(listing["items"]) == 1 and listing["next_cursor"]
    assert catalog.instruments(v2_engine)["items"]
    coverage = catalog.coverage(
        v2_engine, "binance:spot:BTCUSDT", "2025-03-01", "2025-03-03", root=root
    )
    assert len(coverage["days"][0]["versions"]) == 2
    assert coverage["days"][0]["observed_start"] == "2025-03-01T00:00:00.000001Z"
    assert coverage["gaps"] == ["2025-03-02"]
    with pytest.raises(V2Error):
        catalog.validate_selection(v2_engine, root, "binance:spot:BTCUSDT", [version, new_version])
    (root / "datasets-v2" / version / "trades.parquet").write_bytes(b"corrupt")
    with pytest.raises(V2Error):
        catalog.inspect_version(v2_engine, root, version)


def test_cross_day_conflict_and_instrument_isolation(v2_engine: Engine, tmp_path: Path) -> None:
    from marketlab.datasets.v2 import catalog

    root = tmp_path / "store"
    published = []
    for day in ("2025-03-01", "2025-03-02"):
        source, metadata = canonical_input(tmp_path)
        source.write_text(source.read_text().replace("2025-03-01", day), encoding="utf-8")
        metadata.update(trade_date=day, source_sha256=sha256_file(source))
        result = service.import_file(v2_engine, root, metadata, source, "day-" + day)
        assert (
            service.work(v2_engine, root, submission_id=result["submission_id"])["succeeded_jobs"]
            == 1
        )
        published.append(
            jobs.inspect_submission(v2_engine, result["submission_id"])["jobs"][0]["result_version"]
        )
    with pytest.raises(V2Error, match="identities conflict"):
        catalog.validate_selection(v2_engine, root, "binance:spot:BTCUSDT", published)
    assert list((root / "selection-v2").iterdir()) == []
    assert (
        catalog.validate_selection(v2_engine, root, "binance:spot:BTCUSDT", published[:1])[
            "verified_rows"
        ]
        == 1
    )
    assert list((root / "selection-v2").iterdir()) == []
    core.add_instrument(
        v2_engine,
        dict(
            venue_id="binance",
            market="spot",
            source_symbol="SOLUSDT",
            base_asset="SOL",
            quote_asset="USDT",
            display_name="SOL/USDT",
            trade_id_order="numeric",
            adapter="binance_daily",
        ),
        "sol",
    )
    source, metadata = canonical_input(tmp_path)
    metadata["instrument_id"] = "binance:spot:SOLUSDT"
    result = service.import_file(v2_engine, root, metadata, source, "sol-source")
    assert (
        service.work(v2_engine, root, submission_id=result["submission_id"])["succeeded_jobs"] == 1
    )
    assert (
        catalog.datasets(v2_engine, identity="binance:spot:SOLUSDT")["items"][0]["instrument_id"]
        == metadata["instrument_id"]
    )


def test_cancellation_before_publication(
    v2_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from marketlab.datasets.v2 import artifacts

    source, metadata = canonical_input(tmp_path)
    root = tmp_path / "store"
    result = service.import_file(v2_engine, root, metadata, source, "cancel-before-publish")
    current = jobs.claim(v2_engine, result["submission_id"])
    assert current is not None
    original = artifacts.verify_dataset

    def cancel_after_verification(*args: Any, **kwargs: Any) -> Any:
        verified = original(*args, **kwargs)
        status = jobs.inspect_submission(v2_engine, result["submission_id"])["jobs"][0]
        jobs.cancel(v2_engine, status["job_id"], status["revision"], "cancel-accepted")
        return verified

    monkeypatch.setattr(artifacts, "verify_dataset", cancel_after_verification)
    with pytest.raises(V2Error):
        service.run_claim(v2_engine, root, current)
    assert (
        jobs.inspect_submission(v2_engine, result["submission_id"])["jobs"][0]["state"]
        == "cancelled"
    )
    with v2_engine.connect() as connection:
        assert (
            connection.execute(sa.text("SELECT count(*) FROM v2_dataset_versions")).scalar_one()
            == 0
        )


def test_divergent_self_consistent_orphan_rejected(
    v2_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json
    from decimal import Decimal

    import pyarrow as pa
    import pyarrow.parquet as pq

    from marketlab.datasets.v2 import artifacts
    from marketlab.datasets.v2.common import canonical_json, digest

    root = tmp_path / "store"
    source, metadata = canonical_input(tmp_path)
    first = service.import_file(v2_engine, root, metadata, source, "orphan-first")
    claimed = jobs.claim(v2_engine, first["submission_id"])
    assert claimed is not None
    original_finish = jobs.finish

    def rollback_success(*args: Any, **kwargs: Any) -> None:
        if args[2] == "succeeded":
            raise V2Error("injected_rollback")
        original_finish(*args, **kwargs)

    monkeypatch.setattr(jobs, "finish", rollback_success)
    with pytest.raises(V2Error):
        service.run_claim(v2_engine, root, claimed)
    monkeypatch.setattr(jobs, "finish", original_finish)
    orphan = next((root / "datasets-v2").iterdir())
    manifest = json.loads((orphan / "manifest.json").read_text())
    table = pq.read_table(orphan / "trades.parquet")
    row = table.to_pylist()[0]
    row["price"] = Decimal("3")
    pq.write_table(pa.Table.from_pylist([row], schema=table.schema), orphan / "trades.parquet")
    q = manifest["quality"]
    q["logical_sha256"] = digest(
        [
            metadata["instrument_id"],
            "2",
            "2025-03-01T00:00:00.000001Z",
            "3.000000000000000000",
            "1.000000000000000000",
            "2.010000000000000000",
            True,
            None,
        ]
    )
    q["parquet_sha256"] = sha256_file(orphan / "trades.parquet")
    q["parquet_bytes"] = (orphan / "trades.parquet").stat().st_size
    manifest["artifact"].update(sha256=q["parquet_sha256"], bytes=q["parquet_bytes"])
    (orphan / "quality.json").write_bytes(canonical_json(q))
    (orphan / "manifest.json").write_bytes(canonical_json(manifest))
    artifacts.verify_dataset(orphan)
    later = service.import_file(v2_engine, root, metadata, source, "orphan-later")
    current = jobs.claim(v2_engine, later["submission_id"])
    assert current is not None
    with pytest.raises(V2Error, match="differs from verified source"):
        service.run_claim(v2_engine, root, current)
    with v2_engine.connect() as connection:
        assert (
            connection.execute(sa.text("SELECT count(*) FROM v2_dataset_versions")).scalar_one()
            == 0
        )


def test_exact_operation_key_length(v2_engine: Engine) -> None:
    assert jobs.submit(v2_engine, body(), "k" * 128)["child_count"] == 1
    with pytest.raises(V2Error):
        jobs.submit(v2_engine, body(), "k" * 129)


def test_publication_wins_concurrent_cancellation(
    v2_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, metadata = canonical_input(tmp_path)
    root = tmp_path / "store"
    result = service.import_file(v2_engine, root, metadata, source, "publish-wins")
    claimed = jobs.claim(v2_engine, result["submission_id"])
    assert claimed is not None
    publishing, release, cancel_started = threading.Event(), threading.Event(), threading.Event()
    original = jobs.finish
    failures: list[Exception] = []
    cancel_codes: list[str] = []

    def hold_success(*args: Any, **kwargs: Any) -> None:
        if args[2] == "succeeded":
            publishing.set()
            assert release.wait(5)
        original(*args, **kwargs)

    def publish() -> None:
        try:
            service.run_claim(v2_engine, root, claimed)
        except Exception as error:
            failures.append(error)

    def cancel() -> None:
        cancel_started.set()
        try:
            jobs.cancel(v2_engine, str(claimed["job_id"]), claimed["revision"], "competing-cancel")
        except V2Error as error:
            cancel_codes.append(error.code)

    monkeypatch.setattr(jobs, "finish", hold_success)
    publisher = threading.Thread(target=publish)
    publisher.start()
    try:
        assert publishing.wait(5)
        canceller = threading.Thread(target=cancel)
        canceller.start()
        assert cancel_started.wait(5)
        time.sleep(0.1)
        assert canceller.is_alive()
        release.set()
        publisher.join(10)
        canceller.join(10)
        assert not publisher.is_alive() and not canceller.is_alive()
        assert not failures and cancel_codes == ["revision_conflict"]
        assert (
            jobs.inspect_submission(v2_engine, result["submission_id"])["jobs"][0]["state"]
            == "succeeded"
        )
    finally:
        release.set()
        publisher.join(10)


def test_non_utc_registry_job_import_coverage_and_cli(v2_engine: Engine, tmp_path: Path) -> None:
    import json
    import subprocess
    import sys

    from marketlab.datasets.v2 import catalog

    with v2_engine.connect() as connection:
        schema = connection.execute(sa.text("SHOW search_path")).scalar_one()
    options = f"-c search_path={schema} -c timezone=Pacific/Honolulu"
    engine = sa.create_engine(v2_engine.url, connect_args={"options": options})
    source, metadata = canonical_input(tmp_path)
    root = tmp_path / "store"
    metadata_path = tmp_path / "manifest.json"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    env = dict(
        os.environ,
        MARKETLAB_DATABASE_URL=v2_engine.url.render_as_string(hide_password=False),
        MARKETLAB_STORAGE_PATH=str(root),
        PGOPTIONS=options,
    )

    def cli(arguments: list[str]) -> dict[str, Any]:
        completed = subprocess.run(
            [sys.executable, "-m", "marketlab.dataset_cli", "v2", *arguments],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert completed.returncode == 0, completed.stderr
        return json.loads(completed.stdout)

    try:
        with engine.connect() as connection:
            registry = core.instrument(connection, "binance:spot:BTCUSDT")
        assert core.wire(registry)["created_at"].endswith("Z")
        staged = cli(
            [
                "import",
                "--manifest",
                str(metadata_path),
                "--file",
                str(source),
                "--key",
                "nonutc-cli",
            ]
        )
        source.unlink()
        assert cli(
            [
                "import",
                "--manifest",
                str(metadata_path),
                "--file",
                str(source),
                "--key",
                "nonutc-cli",
            ]
        )["replayed"]
        cli(["worker", "--max-jobs", "1", "--submission", staged["submission_id"]])
        status = jobs.inspect_submission(engine, staged["submission_id"])
        job = status["jobs"][0]
        assert job["state"] == "succeeded"
        assert status["submission"]["created_at"].endswith("Z")
        assert all(job[name].endswith("Z") for name in ["created_at", "updated_at", "eligible_at"])
        assert job["attempts"][0]["started_at"].endswith("Z")
        assert service.inspect_import(engine, staged["import_id"])["created_at"].endswith("Z")
        report = catalog.coverage(
            engine, "binance:spot:BTCUSDT", "2025-03-01", "2025-03-02", root=root
        )
        assert report["days"][0]["observed_start"] == "2025-03-01T00:00:00.000001Z"
        manifest = catalog.inspect_version(engine, root, job["result_version"])
        assert manifest["instrument"]["created_at"].endswith("Z")
        assert manifest["quality"]["observed_from"] == "2025-03-01T00:00:00.000001Z"
    finally:
        engine.dispose()


def test_previous_execution_queue_not_claimed(v2_engine: Engine) -> None:
    result = jobs.submit(v2_engine, body(), "previous-build")
    with v2_engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE v2_ingestion_submissions SET execution_sha256=:old WHERE submission_id=:id"
            ),
            {
                "old": "ff7621986d66a93f2d25a6c31e2d838cba0949ddb59b5d52841590787e77929d",
                "id": core.uid(result["submission_id"]),
            },
        )
    assert jobs.claim(v2_engine, result["submission_id"]) is None
    report = jobs.inspect_submission(v2_engine, result["submission_id"])
    assert not report["execution_compatible"]
    assert report["jobs"][0]["state"] == "queued" and report["jobs"][0]["attempt_count"] == 0
