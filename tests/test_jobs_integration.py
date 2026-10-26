"""Real PostgreSQL R2 ownership, idempotency, recovery and migration acceptance."""

import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import Engine
from test_datasets import ROW, archive_files

from marketlab.datasets import DatasetError, ingest_archive, inspect_version
from marketlab.datasets.jobs import (
    OwnershipLost,
    attempts,
    claim,
    execute,
    fail,
    fence,
    heartbeat,
    inspect_submission,
    jobs,
    submissions,
    submit,
    succeed,
    work,
)
from marketlab.datasets.publication import _ingest_archive, dataset_versions
from marketlab.datasets.source import TransientSourceError

pytestmark = pytest.mark.integration
JAN = date(2025, 1, 1)
FEB = date(2025, 2, 1)


def request(engine: Engine, *, days: int = 1, **kwargs) -> str:
    return submit(engine, ["BTCUSDT"], JAN, JAN + timedelta(days=days), uuid4().hex, **kwargs)


def expire(engine: Engine, job_id: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            jobs.update()
            .where(jobs.c.job_id == job_id)
            .values(lease_until=sa.func.clock_timestamp() - sa.text("INTERVAL '1 second'"))
        )


def ready(engine: Engine, job_id: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            jobs.update()
            .where(jobs.c.job_id == job_id)
            .values(eligible_at=sa.func.clock_timestamp() - sa.text("INTERVAL '1 second'"))
        )


def count_versions(engine: Engine) -> int:
    with engine.connect() as connection:
        return connection.scalar(sa.select(sa.func.count()).select_from(dataset_versions))


def test_month_expansion_canonical_idempotency_and_conflict(dataset_engine: Engine) -> None:
    first = submit(dataset_engine, ["ETHUSDT", "BTCUSDT"], JAN, FEB, "monthly")
    assert submit(dataset_engine, ["BTCUSDT", "ETHUSDT"], JAN, FEB, "monthly") == first
    state = inspect_submission(dataset_engine, first)
    assert state["total"] == 62
    assert state["succeeded"] == state["failed"] == 0
    assert not state["complete"]
    assert {(row["symbol"], row["trade_date"]) for row in state["jobs"]} == {
        (symbol, JAN + timedelta(days=offset))
        for symbol in ("BTCUSDT", "ETHUSDT")
        for offset in range(31)
    }
    with pytest.raises(DatasetError, match="conflicts"):
        submit(dataset_engine, ["BTCUSDT"], JAN, FEB, "monthly")
    assert inspect_submission(dataset_engine, first)["total"] == 62
    second = submit(dataset_engine, ["BTCUSDT", "ETHUSDT"], JAN, FEB, "monthly-recheck")
    assert second != first


def test_concurrent_same_key_has_one_durable_submission(dataset_engine: Engine) -> None:
    barrier = Barrier(2)

    def invoke() -> str:
        barrier.wait(timeout=10)
        return submit(dataset_engine, ["BTCUSDT"], JAN, FEB, "same-key")

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: invoke(), range(2)))
    assert outcomes[0] == outcomes[1]
    with dataset_engine.connect() as connection:
        assert connection.scalar(sa.select(sa.func.count()).select_from(submissions)) == 1
        assert connection.scalar(sa.select(sa.func.count()).select_from(jobs)) == 31


def test_skip_locked_claims_another_job_without_waiting(dataset_engine: Engine) -> None:
    identity = request(dataset_engine, days=2)
    state = inspect_submission(dataset_engine, identity)
    first_id = state["jobs"][0]["job_id"]
    with dataset_engine.begin() as connection:
        connection.execute(sa.select(jobs).where(jobs.c.job_id == first_id).with_for_update())
        started = time.monotonic()
        other = claim(dataset_engine, submission_id=identity)
        assert time.monotonic() - started < 5
        assert other is not None and other.job_id != first_id
    first = claim(dataset_engine, submission_id=identity)
    assert first is not None and first.job_id == first_id
    assert claim(dataset_engine, submission_id=identity) is None


def test_queued_claim_survives_backward_database_time_but_retry_backoff_holds(
    dataset_engine: Engine,
) -> None:
    identity = request(dataset_engine, days=2)
    first_id, second_id = (
        row["job_id"] for row in inspect_submission(dataset_engine, identity)["jobs"]
    )
    # A future submission timestamp is what a backward database clock step looks like.
    with dataset_engine.begin() as connection:
        connection.execute(
            jobs.update()
            .where(jobs.c.submission_id == identity)
            .values(eligible_at=sa.func.clock_timestamp() + sa.text("INTERVAL '1 hour'"))
        )
    current = claim(dataset_engine, job_id=first_id)
    assert current is not None and current.attempt == 1 and current.token == 1
    fail(dataset_engine, current, TransientSourceError("outage"))
    assert claim(dataset_engine, job_id=first_id) is None
    other = claim(dataset_engine, submission_id=identity)
    assert other is not None and other.job_id == second_id


def test_synchronous_ingestion_survives_backward_database_time_after_submit(
    dataset_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from marketlab.datasets import publication

    original_submit = publication.submit
    identities = []

    def stepped_submit(*args, **kwargs) -> str:
        identity = original_submit(*args, **kwargs)
        identities.append(identity)
        with dataset_engine.begin() as connection:
            connection.execute(
                jobs.update()
                .where(jobs.c.submission_id == identity)
                .values(eligible_at=sa.func.clock_timestamp() + sa.text("INTERVAL '1 hour'"))
            )
        return identity

    monkeypatch.setattr(publication, "submit", stepped_submit)
    archive, checksum = archive_files(tmp_path / "fixture")
    result = ingest_archive(dataset_engine, tmp_path / "storage", archive, checksum)
    state = inspect_submission(dataset_engine, identities[0])
    assert state["complete"] and state["jobs"][0]["attempt_count"] == 1
    assert [item["outcome"] for item in state["jobs"][0]["attempts"]] == ["succeeded"]
    assert state["jobs"][0]["result_version"] == result["dataset_version_id"]


def test_simultaneous_workers_claim_distinct_jobs(dataset_engine: Engine) -> None:
    identity = request(dataset_engine, days=2)
    barrier = Barrier(2)

    def invoke():
        barrier.wait(timeout=10)
        return claim(dataset_engine, submission_id=identity)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: invoke(), range(2)))
    assert all(outcomes)
    assert outcomes[0].job_id != outcomes[1].job_id
    assert outcomes[0].owner != outcomes[1].owner


def test_heartbeat_uses_database_time_and_cannot_revive_expired_owner(
    dataset_engine: Engine,
) -> None:
    identity = request(dataset_engine)
    current = claim(dataset_engine, submission_id=identity)
    assert current is not None
    assert heartbeat(dataset_engine, current)
    with dataset_engine.connect() as connection:
        seconds = connection.scalar(
            sa.select(sa.extract("epoch", jobs.c.lease_until - sa.func.clock_timestamp())).where(
                jobs.c.job_id == current.job_id
            )
        )
    # The upper slack tolerates a backward database clock step after heartbeat().
    assert 55 <= seconds <= 61
    expire(dataset_engine, current.job_id)
    assert not heartbeat(dataset_engine, current)
    replacement = claim(dataset_engine, submission_id=identity)
    assert replacement is not None
    assert replacement.token == current.token + 1
    assert replacement.attempt == 2
    assert not heartbeat(dataset_engine, current)
    with pytest.raises(OwnershipLost):
        fail(dataset_engine, current, RuntimeError("private"))
    with pytest.raises(OwnershipLost), dataset_engine.begin() as connection:
        fence(connection, current)
    with pytest.raises(OwnershipLost), dataset_engine.begin() as connection:
        succeed(connection, current, "a" * 64)
    state = inspect_submission(dataset_engine, identity)["jobs"][0]
    assert state["owner"] == replacement.owner
    assert state["attempts"][0]["outcome"] == "expired"


def test_three_crashed_attempts_never_allow_fourth_execution(dataset_engine: Engine) -> None:
    identity = request(dataset_engine)
    tokens = []
    for number in range(1, 4):
        current = claim(dataset_engine, submission_id=identity)
        assert current is not None and current.attempt == number
        tokens.append(current.token)
        expire(dataset_engine, current.job_id)
    assert claim(dataset_engine, submission_id=identity) is None
    state = inspect_submission(dataset_engine, identity)["jobs"][0]
    assert state["state"] == "failed" and state["attempt_count"] == 3
    assert state["owner"] is state["lease_until"] is None
    assert [item["outcome"] for item in state["attempts"]] == ["expired"] * 3
    assert tokens == [1, 2, 3]


def test_transient_retries_have_delay_and_total_three_attempt_budget(
    dataset_engine: Engine,
) -> None:
    identity = request(dataset_engine)
    for number, expected_delay in ((1, 10), (2, 30), (3, 30)):
        current = claim(dataset_engine, submission_id=identity)
        assert current is not None and current.attempt == number
        fail(dataset_engine, current, TransientSourceError("private-network-detail"))
        state = inspect_submission(dataset_engine, identity)["jobs"][0]
        assert state["state"] == ("retry_wait" if number < 3 else "failed")
        assert "private" not in state["error"]
        with dataset_engine.connect() as connection:
            seconds = connection.scalar(
                sa.select(
                    sa.extract("epoch", jobs.c.eligible_at - sa.func.clock_timestamp())
                ).where(jobs.c.job_id == current.job_id)
            )
        # The upper slack tolerates a backward database clock step after fail().
        assert expected_delay - 2 <= seconds <= expected_delay + 1
        assert claim(dataset_engine, submission_id=identity) is None
        ready(dataset_engine, current.job_id)
    assert claim(dataset_engine, submission_id=identity) is None


@pytest.mark.parametrize(
    "error", [DatasetError("bad-secret-row"), RuntimeError("secret"), OSError("secret-path")]
)
def test_permanent_and_unknown_failures_do_not_retry(
    dataset_engine: Engine, error: Exception
) -> None:
    identity = request(dataset_engine)
    current = claim(dataset_engine, submission_id=identity)
    fail(dataset_engine, current, error)
    state = inspect_submission(dataset_engine, identity)["jobs"][0]
    assert state["state"] == "failed" and state["attempt_count"] == 1
    assert state["error"] == "historical ingestion failed"
    assert state["attempts"][0]["outcome"] == "permanent"
    assert claim(dataset_engine, submission_id=identity) is None


def test_retry_after_delay_is_retained(dataset_engine: Engine) -> None:
    identity = request(dataset_engine)
    current = claim(dataset_engine, submission_id=identity)
    fail(dataset_engine, current, TransientSourceError("outage", 120))
    with dataset_engine.connect() as connection:
        seconds = connection.scalar(
            sa.select(sa.extract("epoch", jobs.c.eligible_at - sa.func.clock_timestamp())).where(
                jobs.c.job_id == current.job_id
            )
        )
    # The upper slack tolerates a backward database clock step after fail().
    assert 118 <= seconds <= 121


def test_incompatible_execution_contract_is_not_claimed(dataset_engine: Engine) -> None:
    identity = request(dataset_engine)
    with dataset_engine.begin() as connection:
        connection.execute(
            submissions.update()
            .where(submissions.c.submission_id == identity)
            .values(execution_contract="future-contract")
        )
    assert claim(dataset_engine, submission_id=identity) is None
    assert inspect_submission(dataset_engine, identity)["jobs"][0]["attempt_count"] == 0


def test_fixture_jobs_never_fall_back_to_network_and_resume_checks_hash(
    dataset_engine: Engine, tmp_path: Path
) -> None:
    archive, checksum = archive_files(tmp_path / "fixture")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    identity = request(dataset_engine, source_mode="fixture", input_sha256=digest)
    job_id = inspect_submission(dataset_engine, identity)["jobs"][0]["job_id"]
    assert claim(dataset_engine, submission_id=identity) is None
    first = claim(dataset_engine, job_id=job_id)
    expire(dataset_engine, job_id)
    assert claim(dataset_engine, submission_id=identity) is None
    result = ingest_archive(
        dataset_engine, tmp_path / "storage", archive, checksum, resume_job_id=job_id
    )
    assert inspect_submission(dataset_engine, identity)["complete"]
    assert inspect_submission(dataset_engine, identity)["jobs"][0]["attempt_count"] == 2
    assert not heartbeat(dataset_engine, first)
    assert (
        ingest_archive(
            dataset_engine, tmp_path / "storage", archive, checksum, resume_job_id=job_id
        )
        == result
    )
    changed, changed_checksum = archive_files(tmp_path / "changed", [ROW.replace("True", "False")])
    with pytest.raises(DatasetError, match="source mismatch"):
        ingest_archive(
            dataset_engine, tmp_path / "storage", changed, changed_checksum, resume_job_id=job_id
        )
    assert count_versions(dataset_engine) == 1


def test_stale_worker_cannot_publish_after_reclaim(dataset_engine: Engine, tmp_path: Path) -> None:
    archive, checksum = archive_files(tmp_path / "fixture")
    identity = request(dataset_engine)
    old = claim(dataset_engine, submission_id=identity)
    expire(dataset_engine, old.job_id)
    current = claim(dataset_engine, submission_id=identity)
    with pytest.raises(OwnershipLost):
        _ingest_archive(dataset_engine, tmp_path / "storage", archive, checksum, current=old)
    assert count_versions(dataset_engine) == 0
    assert inspect_submission(dataset_engine, identity)["jobs"][0]["owner"] == current.owner
    result = _ingest_archive(
        dataset_engine, tmp_path / "storage", archive, checksum, current=current
    )
    assert inspect_submission(dataset_engine, identity)["complete"]
    assert (
        inspect_version(dataset_engine, tmp_path / "storage", result["dataset_version_id"])
        == result
    )


def test_lost_heartbeat_flag_blocks_publication_even_before_lease_expiry(
    dataset_engine: Engine, tmp_path: Path
) -> None:
    archive, checksum = archive_files(tmp_path / "fixture")
    identity = request(dataset_engine)
    current = claim(dataset_engine, submission_id=identity)
    current.lost.set()
    with pytest.raises(OwnershipLost):
        _ingest_archive(dataset_engine, tmp_path / "storage", archive, checksum, current=current)
    assert count_versions(dataset_engine) == 0


def test_publication_and_success_are_atomic_on_rollback(
    dataset_engine: Engine, tmp_path: Path
) -> None:
    archive, checksum = archive_files(tmp_path / "fixture")
    identity = request(dataset_engine)
    current = claim(dataset_engine, submission_id=identity)

    def stop(phase: str) -> None:
        if phase == "before_catalog_commit":
            assert count_versions(dataset_engine) == 0
            assert inspect_submission(dataset_engine, identity)["jobs"][0]["state"] == "running"
            raise RuntimeError("injected rollback")

    with pytest.raises(RuntimeError, match="injected"):
        _ingest_archive(
            dataset_engine,
            tmp_path / "storage",
            archive,
            checksum,
            current=current,
            checkpoint=stop,
        )
    assert count_versions(dataset_engine) == 0
    assert inspect_submission(dataset_engine, identity)["jobs"][0]["state"] == "running"
    result = _ingest_archive(
        dataset_engine, tmp_path / "storage", archive, checksum, current=current
    )
    assert count_versions(dataset_engine) == 1
    state = inspect_submission(dataset_engine, identity)["jobs"][0]
    assert state["state"] == "succeeded" and state["result_version"] == result["dataset_version_id"]
    assert state["attempts"][0]["outcome"] == "succeeded"


def test_worker_respects_max_jobs_and_continues_after_recorded_failure(
    dataset_engine: Engine,
) -> None:
    identity = request(dataset_engine, days=3)
    calls = []

    def invalid(current):
        calls.append(current.job_id)
        raise DatasetError("invalid source")

    assert work(dataset_engine, invalid, max_jobs=2, submission_id=identity) == 2
    assert len(calls) == 2
    state = inspect_submission(dataset_engine, identity)
    assert state["failed"] == 2 and not state["complete"]
    assert [row["state"] for row in state["jobs"]] == ["failed", "failed", "queued"]


PROCESS = r"""
import json, os, sys, time
from pathlib import Path
import sqlalchemy as sa
from marketlab.datasets.jobs import claim
from marketlab.datasets.publication import _ingest_archive
config = json.loads(Path(sys.argv[1]).read_text())
engine = sa.create_engine(config['url']).execution_options(
    schema_translate_map={None: config['schema']})
current = claim(engine, job_id=config['job_id'])
def checkpoint(phase):
    if phase == config['phase']:
        Path(config['signal']).write_text(phase)
        while True:
            time.sleep(1)
if config['phase'] == 'claimed':
    checkpoint('claimed')
if config['phase'] == 'during_staging':
    import marketlab.datasets.publication as publication
    original = publication.normalize_archive
    def pause(archive, staging, **kwargs):
        (staging / 'partial-owned').write_text('incomplete')
        checkpoint('during_staging')
        return original(archive, staging, **kwargs)
    publication.normalize_archive = pause
_ingest_archive(engine, Path(config['root']), Path(config['archive']),
    Path(config['checksum']), current=current, checkpoint=checkpoint)
"""


@pytest.mark.parametrize(
    "phase", ["claimed", "during_staging", "before_catalog_commit", "after_catalog_commit"]
)
def test_killed_process_recovers_without_incomplete_visibility(
    dataset_engine: Engine, tmp_path: Path, phase: str
) -> None:
    archive, checksum = archive_files(tmp_path / "fixture")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    identity = request(dataset_engine, source_mode="fixture", input_sha256=digest)
    job_id = inspect_submission(dataset_engine, identity)["jobs"][0]["job_id"]
    signal = tmp_path / "reached.txt"
    root = tmp_path / "storage"
    config = {
        "url": dataset_engine.url.render_as_string(hide_password=False),
        "schema": dataset_engine.get_execution_options()["schema_translate_map"][None],
        "job_id": job_id,
        "phase": phase,
        "signal": str(signal),
        "root": str(root),
        "archive": str(archive),
        "checksum": str(checksum),
    }
    configuration = tmp_path / "process.json"
    configuration.write_text(json.dumps(config))
    process = subprocess.Popen(
        [sys.executable, "-c", PROCESS, str(configuration)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 20
        while not signal.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if not signal.exists():
            stdout, stderr = process.communicate(timeout=5)
            pytest.fail(f"worker did not reach checkpoint: {stdout!r}, {stderr!r}")
        state = inspect_submission(dataset_engine, identity)["jobs"][0]
        assert state["state"] == ("succeeded" if phase == "after_catalog_commit" else "running")
        assert count_versions(dataset_engine) == (1 if phase == "after_catalog_commit" else 0)
        process.kill()
        process.communicate(timeout=10)
        if phase != "after_catalog_commit":
            expire(dataset_engine, job_id)
        result = ingest_archive(dataset_engine, root, archive, checksum, resume_job_id=job_id)
        assert inspect_submission(dataset_engine, identity)["complete"]
        assert count_versions(dataset_engine) == 1
        state = inspect_submission(dataset_engine, identity)["jobs"][0]
        assert state["attempt_count"] == (1 if phase == "after_catalog_commit" else 2)
        assert inspect_version(dataset_engine, root, result["dataset_version_id"]) == result
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)
        configuration.unlink(missing_ok=True)


def migration_module(name: str):
    location = Path(__file__).resolve().parents[1] / "migrations" / "versions" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, location)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_real_migration_preserves_populated_r1_and_constraints(dataset_engine: Engine) -> None:
    schema = "test_r2_upgrade_" + uuid4().hex
    with dataset_engine.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    try:
        with dataset_engine.begin() as connection:
            connection = connection.execution_options(schema_translate_map={None: schema})
            connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration_module("0002_trades").upgrade()
                migration_module("0003_dataset_versions").upgrade()
                connection.execute(
                    sa.text(
                        "INSERT INTO trades VALUES ('old','SYN','2025-01-01T00:00:00Z',1.25,2.5)"
                    )
                )
                connection.execute(
                    sa.text(
                        "INSERT INTO dataset_versions VALUES (:version,:source,:manifest,"
                        "'old-manifest','binance_spot','BTCUSDT','2025-01-01',7,"
                        "'published',CURRENT_TIMESTAMP)"
                    ),
                    {"version": "a" * 64, "source": "b" * 64, "manifest": "c" * 64},
                )
                old_trade = connection.execute(sa.text("SELECT * FROM trades")).one()
                old_catalog = connection.execute(sa.text("SELECT * FROM dataset_versions")).one()
                migration_module("0004_ingestion_jobs").upgrade()
                assert connection.execute(sa.text("SELECT * FROM trades")).one() == old_trade
                assert (
                    connection.execute(sa.text("SELECT * FROM dataset_versions")).one()
                    == old_catalog
                )
                foreign_keys = connection.execute(
                    sa.text(
                        "SELECT count(*) FROM pg_constraint WHERE "
                        "connamespace = CAST(:namespace AS regnamespace) AND contype = 'f'"
                    ),
                    {"namespace": schema},
                ).scalar_one()
                assert foreign_keys == 3
                submission_id, job_id = str(uuid4()), str(uuid4())
                now = sa.func.clock_timestamp()
                connection.execute(
                    submissions.insert().values(
                        submission_id=submission_id,
                        idempotency_key="constraints",
                        request_sha256="d" * 64,
                        symbols='["BTCUSDT"]',
                        start_date=JAN,
                        before_date=JAN + timedelta(days=1),
                        execution_contract="daily-ingestion-v1",
                        created_at=now,
                    )
                )
                connection.execute(
                    jobs.insert().values(
                        job_id=job_id,
                        submission_id=submission_id,
                        venue="binance_spot",
                        symbol="BTCUSDT",
                        trade_date=JAN,
                        source_mode="official",
                        state="queued",
                        attempt_count=0,
                        fencing_token=0,
                        eligible_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                )
                for invalid in [
                    {"attempt_count": 4},
                    {"fencing_token": -1},
                    {"state": "running"},
                    {"state": "unknown"},
                    {"owner": "unexpected-owner"},
                    {"state": "succeeded"},
                    {"state": "succeeded", "result_version": "f" * 64},
                    {"submission_id": str(uuid4())},
                    {"symbol": "XRPUSDT"},
                    {"source_mode": "fixture"},
                    {"source_mode": "other"},
                ]:
                    with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
                        connection.execute(
                            jobs.update().where(jobs.c.job_id == job_id).values(**invalid)
                        )
                attempt_values = dict(
                    job_id=job_id,
                    attempt_number=1,
                    fencing_token=1,
                    owner=str(uuid4()),
                    started_at=now,
                    outcome="running",
                )
                for invalid in [
                    {"job_id": str(uuid4())},
                    {"attempt_number": 0},
                    {"fencing_token": 0},
                    {"outcome": "unknown"},
                    {"outcome": "expired"},
                ]:
                    with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
                        connection.execute(attempts.insert().values(attempt_values | invalid))
                migration_module("0004_ingestion_jobs").downgrade()
                assert connection.execute(sa.text("SELECT * FROM trades")).one() == old_trade
                assert (
                    connection.execute(sa.text("SELECT * FROM dataset_versions")).one()
                    == old_catalog
                )
    finally:
        with dataset_engine.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))


def test_real_publication_lock_timeout_is_transient_and_retryable(
    dataset_engine: Engine, tmp_path: Path
) -> None:
    from marketlab.datasets.publication import _build, _version

    archive, checksum = archive_files(tmp_path / "fixture")
    source_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    version = _version(source_hash, "BTCUSDT", JAN, _build()["lock_sha256"])
    lock = int.from_bytes(bytes.fromhex(version[:16]), "big", signed=True)
    identity = request(dataset_engine)
    current = claim(dataset_engine, submission_id=identity)
    with dataset_engine.begin() as blocker:
        blocker.execute(sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
        with pytest.raises(DatasetError, match="publication failed") as caught:
            execute(
                dataset_engine,
                current,
                lambda owned: _ingest_archive(
                    dataset_engine, tmp_path / "storage", archive, checksum, current=owned
                ),
            )
    assert getattr(caught.value.__cause__.orig, "sqlstate", None) == "55P03"
    state = inspect_submission(dataset_engine, identity)["jobs"][0]
    assert state["state"] == "retry_wait"
    assert state["attempts"][0]["outcome"] == "transient"
    assert count_versions(dataset_engine) == 0
    ready(dataset_engine, current.job_id)
    replacement = claim(dataset_engine, submission_id=identity)
    _ingest_archive(dataset_engine, tmp_path / "storage", archive, checksum, current=replacement)
    assert inspect_submission(dataset_engine, identity)["complete"]


def test_synchronous_supplied_client_cannot_be_stolen_by_network_worker(
    dataset_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    from marketlab.datasets import ingest_day, publication

    archive, checksum = archive_files(tmp_path / "fixture")
    original_submit = publication.submit
    checked = []

    def competing_submit(*args, **kwargs):
        identity = original_submit(*args, **kwargs)
        assert kwargs["source_mode"] == "inline"
        assert claim(dataset_engine, submission_id=identity) is None
        checked.append(identity)
        return identity

    def response(request: httpx.Request) -> httpx.Response:
        body = (
            checksum.read_bytes()
            if request.url.path.endswith(".CHECKSUM")
            else archive.read_bytes()
        )
        return httpx.Response(200, content=body)

    monkeypatch.setattr(publication, "submit", competing_submit)
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        result = ingest_day(
            dataset_engine, tmp_path / "storage", symbol="BTCUSDT", trade_date=JAN, client=client
        )
    assert len(checked) == 1
    assert inspect_submission(dataset_engine, checked[0])["complete"]
    assert result["quality"]["accepted_rows"] == 1


def test_graceful_stop_finishes_current_publication_and_leaves_next_job_queued(
    dataset_engine: Engine, tmp_path: Path
) -> None:
    import threading

    archive, checksum = archive_files(tmp_path / "fixture")
    identity = request(dataset_engine, days=2)
    stop = threading.Event()

    def finish_and_stop(current):
        result = _ingest_archive(
            dataset_engine, tmp_path / "storage", archive, checksum, current=current
        )
        stop.set()
        return result

    assert (
        work(dataset_engine, finish_and_stop, max_jobs=2, submission_id=identity, stop_event=stop)
        == 1
    )
    state = inspect_submission(dataset_engine, identity)
    assert state["succeeded"] == 1 and not state["complete"]
    assert [row["state"] for row in state["jobs"]] == ["succeeded", "queued"]


def test_background_heartbeat_renews_during_operation(
    dataset_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    from marketlab.datasets import jobs as job_module

    archive, checksum = archive_files(tmp_path / "fixture")
    identity = request(dataset_engine)
    current = claim(dataset_engine, submission_id=identity)
    monkeypatch.setattr(job_module, "HEARTBEAT_SECONDS", 0.02)
    with dataset_engine.begin() as connection:
        connection.execute(
            jobs.update()
            .where(jobs.c.job_id == current.job_id)
            .values(lease_until=sa.func.clock_timestamp() + sa.text("INTERVAL '2 seconds'"))
        )

    def long_operation(owned):
        deadline = time.monotonic() + 2
        seconds = 0
        while seconds < 50 and time.monotonic() < deadline:
            threading.Event().wait(0.02)
            with dataset_engine.connect() as connection:
                seconds = connection.scalar(
                    sa.select(
                        sa.extract("epoch", jobs.c.lease_until - sa.func.clock_timestamp())
                    ).where(jobs.c.job_id == current.job_id)
                )
        assert seconds > 50
        return _ingest_archive(
            dataset_engine, tmp_path / "storage", archive, checksum, current=owned
        )

    execute(dataset_engine, current, long_operation)
    assert inspect_submission(dataset_engine, identity)["complete"]


def test_failed_background_renewal_prevents_publication(
    dataset_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from marketlab.datasets import jobs as job_module

    archive, checksum = archive_files(tmp_path / "fixture")
    identity = request(dataset_engine)
    current = claim(dataset_engine, submission_id=identity)
    monkeypatch.setattr(job_module, "HEARTBEAT_SECONDS", 0.02)
    monkeypatch.setattr(job_module, "heartbeat", lambda engine, owned: False)

    def long_operation(owned):
        assert owned.lost.wait(2)
        return _ingest_archive(
            dataset_engine, tmp_path / "storage", archive, checksum, current=owned
        )

    with pytest.raises(OwnershipLost):
        execute(dataset_engine, current, long_operation)
    assert count_versions(dataset_engine) == 0
    assert inspect_submission(dataset_engine, identity)["jobs"][0]["state"] == "running"


def test_synchronous_transient_source_retries_same_durable_job_then_succeeds(
    dataset_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    from marketlab.datasets import ingest_day, publication

    archive, checksum = archive_files(tmp_path / "fixture")
    calls = []
    sleeps = []

    def response(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(503)
        body = (
            checksum.read_bytes()
            if request.url.path.endswith(".CHECKSUM")
            else archive.read_bytes()
        )
        return httpx.Response(200, content=body)

    def advance_eligibility(delay: float) -> None:
        sleeps.append(delay)
        with dataset_engine.begin() as connection:
            connection.execute(
                jobs.update()
                .where(jobs.c.state == "retry_wait")
                .values(eligible_at=sa.func.clock_timestamp() - sa.text("INTERVAL '1 second'"))
            )

    # Keep the retry wait local: POSIX subprocess provenance reads also use
    # the shared stdlib time.sleep for their own millisecond polling.
    monkeypatch.setattr(publication, "time", SimpleNamespace(sleep=advance_eligibility))
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        result = ingest_day(
            dataset_engine, tmp_path / "storage", symbol="BTCUSDT", trade_date=JAN, client=client
        )
    assert len(calls) == 3 and len(sleeps) == 1
    assert 8 <= sleeps[0] <= 10
    with dataset_engine.connect() as connection:
        identity = connection.scalar(sa.select(submissions.c.submission_id))
    state = inspect_submission(dataset_engine, identity)
    assert state["complete"] and state["total"] == 1
    assert state["jobs"][0]["attempt_count"] == 2
    assert [item["outcome"] for item in state["jobs"][0]["attempts"]] == ["transient", "succeeded"]
    assert state["jobs"][0]["result_version"] == result["dataset_version_id"]


def test_synchronous_retry_rechecks_database_time_that_trails_host_sleep(
    dataset_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    from marketlab.datasets import ingest_day, publication

    archive, checksum = archive_files(tmp_path / "fixture")
    calls = []
    sleeps = []

    def response(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(503)
        body = (
            checksum.read_bytes()
            if request.url.path.endswith(".CHECKSUM")
            else archive.read_bytes()
        )
        return httpx.Response(200, content=body)

    def trailing_database_time(delay: float) -> None:
        # The first host wait ends before database time reaches retry eligibility.
        sleeps.append(delay)
        if len(sleeps) > 1:
            with dataset_engine.begin() as connection:
                connection.execute(
                    jobs.update()
                    .where(jobs.c.state == "retry_wait")
                    .values(eligible_at=sa.func.clock_timestamp() - sa.text("INTERVAL '1 second'"))
                )

    monkeypatch.setattr(publication, "time", SimpleNamespace(sleep=trailing_database_time))
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        result = ingest_day(
            dataset_engine, tmp_path / "storage", symbol="BTCUSDT", trade_date=JAN, client=client
        )
    assert len(calls) == 3 and len(sleeps) == 2
    assert 8 <= sleeps[0] <= 11 and 8 <= sleeps[1] <= 11
    with dataset_engine.connect() as connection:
        identity = connection.scalar(sa.select(submissions.c.submission_id))
    state = inspect_submission(dataset_engine, identity)["jobs"][0]
    assert state["attempt_count"] == state["fencing_token"] == 2
    assert [item["outcome"] for item in state["attempts"]] == ["transient", "succeeded"]
    assert state["result_version"] == result["dataset_version_id"]


def test_synchronous_retry_recheck_is_bounded(
    dataset_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    from marketlab.datasets import ingest_day, publication

    sleeps = []
    monkeypatch.setattr(publication, "time", SimpleNamespace(sleep=sleeps.append))
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as client,
        pytest.raises(DatasetError, match="not eligible"),
    ):
        ingest_day(
            dataset_engine, tmp_path / "storage", symbol="BTCUSDT", trade_date=JAN, client=client
        )
    assert len(sleeps) == 4
    with dataset_engine.connect() as connection:
        identity = connection.scalar(sa.select(submissions.c.submission_id))
    state = inspect_submission(dataset_engine, identity)["jobs"][0]
    assert state["state"] == "retry_wait" and state["attempt_count"] == 1


def test_synchronous_resume_of_unexpired_owner_is_not_eligible(
    dataset_engine: Engine, tmp_path: Path
) -> None:
    from marketlab.datasets import ingest_day

    identity = request(dataset_engine, source_mode="inline")
    job_id = inspect_submission(dataset_engine, identity)["jobs"][0]["job_id"]
    assert claim(dataset_engine, job_id=job_id) is not None
    with pytest.raises(DatasetError, match="not eligible"):
        ingest_day(dataset_engine, tmp_path, symbol="BTCUSDT", trade_date=JAN, resume_job_id=job_id)
    assert inspect_submission(dataset_engine, identity)["jobs"][0]["attempt_count"] == 1


@pytest.mark.parametrize(
    "mode,symbol,day",
    [
        ("official", "BTCUSDT", JAN),
        ("fixture", "BTCUSDT", JAN),
        ("inline", "ETHUSDT", JAN),
        ("inline", "BTCUSDT", date(2025, 1, 2)),
    ],
)
def test_synchronous_resume_rejects_source_mode_symbol_and_day_mismatches(
    dataset_engine: Engine, tmp_path: Path, mode: str, symbol: str, day: date
) -> None:
    from marketlab.datasets import ingest_day

    identity = request(
        dataset_engine,
        source_mode=mode,
        **({"input_sha256": "a" * 64} if mode == "fixture" else {}),
    )
    job_id = inspect_submission(dataset_engine, identity)["jobs"][0]["job_id"]
    with pytest.raises(DatasetError, match="resume source mismatch"):
        ingest_day(dataset_engine, tmp_path, symbol=symbol, trade_date=day, resume_job_id=job_id)
    assert inspect_submission(dataset_engine, identity)["jobs"][0]["attempt_count"] == 0


def test_synchronous_resume_recovers_expired_inline_job_and_reuses_success(
    dataset_engine: Engine, tmp_path: Path
) -> None:
    import httpx

    from marketlab.datasets import ingest_day

    archive, checksum = archive_files(tmp_path / "fixture")
    identity = request(dataset_engine, source_mode="inline")
    job_id = inspect_submission(dataset_engine, identity)["jobs"][0]["job_id"]
    first = claim(dataset_engine, job_id=job_id)
    expire(dataset_engine, job_id)
    assert claim(dataset_engine, submission_id=identity) is None
    calls = []

    def response(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        body = (
            checksum.read_bytes()
            if request.url.path.endswith(".CHECKSUM")
            else archive.read_bytes()
        )
        return httpx.Response(200, content=body)

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        result = ingest_day(
            dataset_engine,
            tmp_path / "storage",
            symbol="BTCUSDT",
            trade_date=JAN,
            client=client,
            resume_job_id=job_id,
        )
        again = ingest_day(
            dataset_engine,
            tmp_path / "storage",
            symbol="BTCUSDT",
            trade_date=JAN,
            client=client,
            resume_job_id=job_id,
        )
    assert result == again and len(calls) == 2
    assert not heartbeat(dataset_engine, first)
    state = inspect_submission(dataset_engine, identity)["jobs"][0]
    assert state["attempt_count"] == 2
    assert [item["outcome"] for item in state["attempts"]] == ["expired", "succeeded"]


def test_synchronous_resume_rejects_unknown_job(dataset_engine: Engine, tmp_path: Path) -> None:
    from marketlab.datasets import ingest_day

    with pytest.raises(DatasetError, match="resume source mismatch"):
        ingest_day(
            dataset_engine, tmp_path, symbol="BTCUSDT", trade_date=JAN, resume_job_id=str(uuid4())
        )


def test_renewal_loss_after_final_fence_rolls_back_catalog_and_success(
    dataset_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from marketlab.datasets import publication

    archive, checksum = archive_files(tmp_path / "fixture")
    identity = request(dataset_engine)
    current = claim(dataset_engine, submission_id=identity)
    original_succeed = publication.succeed

    def lose_then_succeed(connection, owned, version):
        owned.lost.set()
        return original_succeed(connection, owned, version)

    monkeypatch.setattr(publication, "succeed", lose_then_succeed)
    with pytest.raises(OwnershipLost):
        _ingest_archive(dataset_engine, tmp_path / "storage", archive, checksum, current=current)
    assert count_versions(dataset_engine) == 0
    state = inspect_submission(dataset_engine, identity)["jobs"][0]
    assert state["state"] == "running" and state["result_version"] is None
    expire(dataset_engine, current.job_id)
    replacement = claim(dataset_engine, submission_id=identity)
    monkeypatch.setattr(publication, "succeed", original_succeed)
    _ingest_archive(dataset_engine, tmp_path / "storage", archive, checksum, current=replacement)
    assert count_versions(dataset_engine) == 1
    assert inspect_submission(dataset_engine, identity)["complete"]
