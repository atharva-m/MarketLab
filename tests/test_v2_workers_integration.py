"""Actual PostgreSQL migration, worker fencing and atomic cancellation receipts."""

import asyncio
import importlib.util
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_v2_browser_imports_integration import browser_engine as browser_engine  # noqa: F401
from test_v2_copilot_integration import model_engine as model_engine  # noqa: F401
from test_v2_ingestion_integration import v2_engine as v2_engine  # noqa: F401
from test_v2_research_integration import research_engine as research_engine  # noqa: F401

from marketlab import workers
from marketlab.copilot.v2 import durable, store
from marketlab.copilot.v2.model import execution
from marketlab.datasets.v2.common import V2Error, digest
from marketlab.datasets.v2.core import execute, one

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def frozen_test_execution(monkeypatch):
    # Every request/claim pair receives one immutable, kind-specific identity,
    # as a prepared invocation does. Compatibility rejection is tested separately.
    values = {kind: execution(kind) for kind in ("copilot", "memo")}
    monkeypatch.setattr(sys.modules[__name__], "execution", lambda kind: dict(values[kind]))


def migrate(engine, revision):
    path = Path(__file__).resolve().parents[1] / f"migrations/versions/{revision}.py"
    spec = importlib.util.spec_from_file_location(revision, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with engine.begin() as connection:
        connection.execute(sa.text(module.DDL))


@pytest.fixture
def storage_engine(model_engine):  # noqa: F811
    migrate(model_engine, "0012_v2_storage")
    return model_engine


@pytest.fixture
def worker_engine(storage_engine):
    migrate(storage_engine, "0013_v2_workers")
    return storage_engine


def queued(engine, key="worker-cancellation"):
    identity, _, _ = store.create(
        engine, {"schema": "copilot-request-v2"}, {}, execution("copilot"), key
    )
    with engine.connect() as connection:
        job = one(connection, "SELECT * FROM v2_copilot_jobs WHERE request_id=:id", id=identity)
    return identity, str(job["job_id"])


def job(engine, identity):
    with engine.connect() as connection:
        return one(connection, "SELECT * FROM v2_copilot_jobs WHERE job_id=:id", id=identity)


def test_populated_forward_migration_preserves_attempt_clarification_identity_and_calls(
    storage_engine,
):
    request, identity = queued(storage_engine)
    current = durable.claim(storage_engine, "copilot", execution("copilot"), request)
    assert current is not None
    durable.reserve(
        storage_engine,
        current,
        {k: "a" * 64 for k in ("input_sha256", "schema_sha256", "prompt_sha256")},
        "b" * 64,
    )
    before = job(storage_engine, identity)
    with storage_engine.connect() as connection:
        call_before = one(
            connection, "SELECT * FROM v2_copilot_calls WHERE job_id=:id", id=identity
        )
    migrate(storage_engine, "0013_v2_workers")
    after = job(storage_engine, identity)
    assert {k: after[k] for k in before} == before
    assert after["revision"] == 0 and after["state_revision"] == 0
    assert after["cancel_requested"] is False
    with storage_engine.connect() as connection:
        attempt = one(connection, "SELECT * FROM v2_copilot_attempts WHERE job_id=:id", id=identity)
        assert attempt["worker_instance_id"] is None
        assert (
            one(connection, "SELECT * FROM v2_copilot_calls WHERE job_id=:id", id=identity)
            == call_before
        )
        assert workers.mode(connection)["mode"] == "local"
        constraints = execute(
            connection,
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid='v2_copilot_jobs'::regclass AND contype='c'",
        ).scalars()
        assert any("state_revision" in row for row in constraints)


def test_migration_rejects_unexpected_same_name_check_and_rolls_back(storage_engine):
    with storage_engine.begin() as connection:
        execute(
            connection,
            "ALTER TABLE v2_copilot_revisions DROP CONSTRAINT v2_copilot_revisions_outcome_check",
        )
        execute(
            connection,
            "ALTER TABLE v2_copilot_revisions ADD CONSTRAINT "
            "v2_copilot_revisions_outcome_check CHECK(outcome IN "
            "('submitted','needs_clarification','unsupported','failed','unexpected'))",
        )
    with pytest.raises(sa.exc.DatabaseError):
        migrate(storage_engine, "0013_v2_workers")
    with storage_engine.connect() as connection:
        assert execute(connection, "SELECT to_regclass('v2_worker_mode')").scalar_one() is None
        expression = execute(
            connection,
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid='v2_copilot_revisions'::regclass "
            "AND conname='v2_copilot_revisions_outcome_check'",
        ).scalar_one()
        assert "unexpected" in expression


def test_migration_accepts_restored_revision_check_and_preserves_unrelated_checks(storage_engine):
    with storage_engine.begin() as connection:
        execute(
            connection,
            "ALTER TABLE v2_copilot_revisions DROP CONSTRAINT v2_copilot_revisions_outcome_check",
        )
        execute(
            connection,
            "ALTER TABLE v2_copilot_revisions ADD CONSTRAINT "
            "v2_copilot_revisions_outcome_check CHECK(outcome::text=ANY(ARRAY["
            "('submitted'::varchar)::text,('needs_clarification'::varchar)::text,"
            "('unsupported'::varchar)::text,('failed'::varchar)::text]))",
        )
        before = {
            (row["table_name"], row["conname"]): row["definition"]
            for row in execute(
                connection,
                "SELECT conrelid::regclass::text AS table_name,conname,"
                "pg_get_constraintdef(oid) AS definition FROM pg_constraint "
                "WHERE connamespace=current_schema()::regnamespace AND contype='c'",
            ).mappings()
        }
    migrate(storage_engine, "0013_v2_workers")
    with storage_engine.connect() as connection:
        after = {
            (row["table_name"], row["conname"]): row["definition"]
            for row in execute(
                connection,
                "SELECT conrelid::regclass::text AS table_name,conname,"
                "pg_get_constraintdef(oid) AS definition FROM pg_constraint "
                "WHERE connamespace=current_schema()::regnamespace AND contype='c'",
            ).mappings()
        }
    changed = {
        ("v2_copilot_revisions", "v2_copilot_revisions_outcome_check"),
        ("v2_copilot_jobs", "v2_copilot_jobs_state_check"),
        ("v2_memo_jobs", "v2_memo_jobs_state_check"),
        ("v2_copilot_attempts", "v2_copilot_attempts_outcome_check"),
        ("v2_memo_attempts", "v2_memo_attempts_outcome_check"),
    }
    for key, definition in before.items():
        if key not in changed:
            assert after[key] == definition


def test_queued_cancel_replay_conflict_and_no_attempt_or_model_call(worker_engine):
    request, identity = queued(worker_engine)
    result = durable.cancel(worker_engine, "copilot", identity, 0, "cancel-one")
    assert result["state"] == "cancelled" and result["state_revision"] == 1
    replay = durable.cancel(worker_engine, "copilot", identity, 0, "cancel-one")
    assert {k: v for k, v in replay.items() if k != "replayed"} == {
        k: v for k, v in result.items() if k != "replayed"
    }
    assert replay["replayed"] is True
    with pytest.raises(V2Error):
        durable.cancel(worker_engine, "copilot", identity, 1, "cancel-one")
    assert durable.claim(worker_engine, "copilot", execution("copilot"), request) is None
    row = job(worker_engine, identity)
    assert row["attempt_count"] == row["model_calls"] == row["revision"] == 0
    assert store.inspect(worker_engine, request)["revisions"][0]["outcome"] == "cancelled"
    with worker_engine.connect() as connection:
        receipt = one(connection, "SELECT * FROM v2_operations WHERE idempotency_key='cancel-one'")
        assert str(receipt["resource_id"]) == identity
        assert receipt["protocol"] == "worker-cancellation-v1"
        assert execute(connection, "SELECT count(*) FROM v2_copilot_attempts").scalar_one() == 0


def test_stale_cancel_has_no_receipt_and_does_not_mutate(worker_engine):
    _, identity = queued(worker_engine)
    before = job(worker_engine, identity)
    with pytest.raises(V2Error) as error:
        durable.cancel(worker_engine, "copilot", identity, 1, "stale-cancel")
    assert error.value.code == "revision_conflict"
    assert job(worker_engine, identity) == before
    with worker_engine.connect() as connection:
        assert (
            one(connection, "SELECT * FROM v2_operations WHERE idempotency_key='stale-cancel'")
            is None
        )


def test_concurrent_same_receipt_is_one_atomic_cancellation(worker_engine):
    _, identity = queued(worker_engine)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: durable.cancel(
                    worker_engine, "copilot", identity, 0, "concurrent-cancel"
                ),
                range(2),
            )
        )
    assert sorted(r["replayed"] for r in results) == [False, True]
    assert job(worker_engine, identity)["state_revision"] == 1
    with worker_engine.connect() as connection:
        assert (
            execute(
                connection,
                "SELECT count(*) FROM v2_operations WHERE idempotency_key='concurrent-cancel'",
            ).scalar_one()
            == 1
        )


def test_running_cancel_fences_publication_and_expired_reclaim_spends_no_attempt(worker_engine):
    request, identity = queued(worker_engine)
    current = durable.claim(worker_engine, "copilot", execution("copilot"), request)
    assert current is not None
    running = job(worker_engine, identity)
    assert running["state_revision"] == 1
    durable.cancel(worker_engine, "copilot", identity, 1, "running-cancel")
    cancelled = job(worker_engine, identity)
    assert cancelled["state"] == "running" and cancelled["state_revision"] == 2
    with worker_engine.begin() as connection:
        with pytest.raises(V2Error):
            durable.fence(connection, current)
    assert not durable.heartbeat(worker_engine, current)
    with worker_engine.begin() as connection:
        execute(
            connection,
            "UPDATE v2_copilot_jobs SET lease_until=clock_timestamp()-interval "
            "'1 second' WHERE job_id=:id",
            id=identity,
        )
    assert durable.claim(worker_engine, "copilot", execution("copilot"), request) is None
    final = job(worker_engine, identity)
    assert final["state"] == "cancelled" and final["attempt_count"] == 1
    assert final["model_calls"] == 0 and final["revision"] == 0
    with worker_engine.connect() as connection:
        attempt = one(connection, "SELECT * FROM v2_copilot_attempts WHERE job_id=:id", id=identity)
        assert attempt["outcome"] == "cancelled"


def test_heartbeat_does_not_change_state_revision_and_success_rejects_cancellation(worker_engine):
    request, identity = queued(worker_engine)
    current = durable.claim(worker_engine, "copilot", execution("copilot"), request)
    assert durable.heartbeat(worker_engine, current)
    assert job(worker_engine, identity)["state_revision"] == 1
    with worker_engine.begin() as connection:
        durable.complete(connection, current)
    assert job(worker_engine, identity)["state_revision"] == 2
    with pytest.raises(V2Error):
        durable.cancel(worker_engine, "copilot", identity, 2, "late-cancel")
    assert job(worker_engine, identity)["state"] == "succeeded"


def register(engine, tmp_path):
    host, root_id, instance = str(uuid4()), str(uuid4()), str(uuid4())
    source_sha, lock_sha = workers.source_identity()
    workers.provision(engine, host, "owned-test-host", root_id, tmp_path)
    with engine.begin() as connection:
        root = one(connection, "SELECT * FROM v2_worker_roots WHERE root_id=:id", id=root_id)
        execute(
            connection,
            "INSERT INTO v2_worker_instances(instance_id,root_id,source_sha256,"
            "lock_sha256,boot_identity,state) VALUES(:id,:root,:source,:lock,:boot,'ready')",
            id=instance,
            root=root_id,
            source=source_sha,
            lock=lock_sha,
            boot=root["boot_identity"],
        )
        execute(
            connection,
            "INSERT INTO v2_worker_capabilities VALUES(:id,'copilot',:contract,:sha)",
            id=instance,
            contract=workers.CONTRACTS["copilot"],
            sha=digest(execution("copilot")),
        )
        # A private test schema has no inventory binding. Provision a minimal
        # capacity row using the real initialization API rather than bypassing FK.
    from marketlab.datasets.v2.admission import initialize

    initialize(engine, tmp_path)
    with engine.begin() as connection:
        execute(
            connection,
            "UPDATE v2_worker_mode SET mode='distributed',shared_root_id="
            "(SELECT root_id FROM v2_capacity_roots WHERE singleton) WHERE singleton",
        )
    return engine.execution_options(
        worker_instance_id=instance,
        worker_root_id=root_id,
        worker_source_sha256=source_sha,
        worker_lock_sha256=lock_sha,
    ), instance


def test_distributed_missing_capability_rejected_before_attempt_and_exact_owner_associated(
    worker_engine, tmp_path
):
    request, identity = queued(worker_engine)
    registered, instance = register(worker_engine, tmp_path)
    try:
        with pytest.raises(V2Error):
            durable.claim(worker_engine, "copilot", execution("copilot"), request)
        incompatible = dict(execution("copilot"), lock_sha256="f" * 64)
        with pytest.raises(V2Error):
            durable.claim(registered, "copilot", incompatible, request)
        assert job(worker_engine, identity)["attempt_count"] == 0
        current = durable.claim(registered, "copilot", execution("copilot"), request)
        assert current is not None
        with worker_engine.connect() as connection:
            attempt = one(
                connection, "SELECT * FROM v2_copilot_attempts WHERE job_id=:id", id=identity
            )
            assert str(attempt["worker_instance_id"]) == instance
    finally:
        registered.dispose()


@pytest.mark.parametrize(
    "state",
    ["stale", "draining", "boot_mismatch", "unready_root", "source_mismatch", "lock_mismatch"],
)
def test_stale_or_unready_registration_cannot_spend_attempt(worker_engine, tmp_path, state):
    request, identity = queued(worker_engine)
    registered, instance = register(worker_engine, tmp_path)
    with worker_engine.begin() as connection:
        if state == "stale":
            execute(
                connection,
                "UPDATE v2_worker_instances SET heartbeat_at=clock_timestamp()-"
                "interval '31 seconds' WHERE instance_id=:id",
                id=instance,
            )
        elif state == "draining":
            execute(
                connection,
                "UPDATE v2_worker_instances SET state='draining' WHERE instance_id=:id",
                id=instance,
            )
        elif state == "boot_mismatch":
            execute(
                connection,
                "UPDATE v2_worker_instances SET boot_identity='other-boot' WHERE instance_id=:id",
                id=instance,
            )
        elif state == "unready_root":
            execute(connection, "UPDATE v2_worker_roots SET ready=false")
        elif state == "source_mismatch":
            execute(
                connection,
                "UPDATE v2_worker_instances SET source_sha256=:sha WHERE instance_id=:id",
                sha="f" * 64,
                id=instance,
            )
        else:
            execute(
                connection,
                "UPDATE v2_worker_instances SET lock_sha256=:sha WHERE instance_id=:id",
                sha="f" * 64,
                id=instance,
            )
    with pytest.raises(V2Error):
        durable.claim(registered, "copilot", execution("copilot"), request)
    assert job(worker_engine, identity)["attempt_count"] == 0
    registered.dispose()


def test_host_identity_and_root_cannot_be_rebound(worker_engine, tmp_path):
    host, root = str(uuid4()), str(uuid4())
    workers.provision(worker_engine, host, "owned-host", root, tmp_path)
    workers.provision(worker_engine, host, "owned-host", root, tmp_path)
    with pytest.raises(V2Error):
        workers.provision(worker_engine, host, "changed-label", root, tmp_path)
    with pytest.raises(V2Error):
        workers.provision(worker_engine, host, "owned-host", str(uuid4()), tmp_path)


def test_worker_identity_constraints_and_legacy_revision_fk_remain_enforced(worker_engine):
    _, identity = queued(worker_engine)
    for sql in (
        "UPDATE v2_copilot_jobs SET state_revision=-1 WHERE job_id=:id",
        "UPDATE v2_copilot_jobs SET state_revision=1 WHERE job_id=:id",
        "UPDATE v2_copilot_jobs SET revision=99 WHERE job_id=:id",
    ):
        with pytest.raises(sa.exc.DatabaseError), worker_engine.begin() as connection:
            execute(connection, sql, id=identity)
    assert job(worker_engine, identity)["state_revision"] == 0


def test_cancellation_preserves_reserved_call_without_model_dispatch(worker_engine):
    request, identity = queued(worker_engine)
    current = durable.claim(worker_engine, "copilot", execution("copilot"), request)
    identities = {key: "a" * 64 for key in ("input_sha256", "schema_sha256", "prompt_sha256")}
    assert durable.reserve(worker_engine, current, identities, "b" * 64) == 1
    durable.cancel(worker_engine, "copilot", identity, 1, "charged-cancel")
    durable.fail(worker_engine, current)
    final = job(worker_engine, identity)
    assert final["state"] == "cancelled" and final["model_calls"] == 1
    with worker_engine.connect() as connection:
        call = one(connection, "SELECT * FROM v2_copilot_calls WHERE job_id=:id", id=identity)
        assert call["call_number"] == 1 and call["state"] == "reserved"


def test_distinct_root_paths_share_logical_advisory_quota_lock(worker_engine, tmp_path):
    import hashlib

    from marketlab.datasets.v2 import core

    registered, _ = register(worker_engine, tmp_path)
    with core.transaction(registered) as first, worker_engine.begin() as observer:
        core.lock(first, "v2-space:host-a-path")
        mode = workers.mode(first)
        key = int.from_bytes(
            hashlib.sha256(("v2-shared-space:" + str(mode["shared_root_id"])).encode()).digest()[
                :8
            ],
            "big",
            signed=True,
        )
        assert (
            execute(observer, "SELECT pg_try_advisory_xact_lock(:key)", key=key).scalar_one()
            is False
        )
    registered.dispose()


def test_physical_capacity_sums_only_matching_worker_root_and_retains_remote_slots(
    worker_engine, tmp_path
):
    from marketlab.datasets.v2 import capacity, core
    from marketlab.datasets.v2.common import canonical_json
    from marketlab.datasets.v2.native_identity import current

    registered, _ = register(worker_engine, tmp_path)
    host, other_root = str(uuid4()), str(uuid4())
    peer = tmp_path / "peer"
    peer.mkdir()
    # Synthetic foreign-domain ledger fixture only. The operator API must reject
    # pretending this OS is two hosts; this test measures SQL root separation,
    # without launching a second worker or claiming real-host acceptance.
    with worker_engine.begin() as connection:
        execute(
            connection,
            "INSERT INTO v2_worker_hosts(host_id,operator_label) VALUES(:id,'peer-test-host')",
            id=host,
        )
        execute(
            connection,
            "INSERT INTO v2_worker_roots "
            "(root_id,host_id,local_path,boot_identity,machine_identity,ready) "
            "VALUES(:root,:host,:path,:boot,:machine,true)",
            root=other_root,
            host=host,
            path=str(peer),
            boot=current()["boot"],
            machine="f" * 64,
        )
    other = worker_engine.execution_options(worker_root_id=other_root)
    with worker_engine.connect() as connection:
        shared = workers.mode(connection)["shared_root_id"]
    tickets = []
    for engine, physical in ((registered, 123), (other, 456)):
        ticket = str(uuid4())
        tickets.append(ticket)
        with core.transaction(engine) as connection:
            execute(
                connection,
                "INSERT INTO v2_admission_tickets "
                "(ticket_id,root_id,role,owner,native_identity,physical_bytes,state,"
                "created_at,updated_at) "
                "VALUES(:id,:root,'research',:owner,:native,:bytes,'active',"
                "clock_timestamp(),clock_timestamp())",
                id=ticket,
                root=shared,
                owner=str(uuid4()),
                native=canonical_json(current()).decode(),
                bytes=physical,
            )
    with registered.connect() as connection:
        assert capacity.outstanding(connection) == 123
    with other.connect() as connection:
        assert capacity.outstanding(connection) == 456
    with worker_engine.connect() as connection:
        assert (
            execute(
                connection, "SELECT count(*) FROM v2_admission_tickets WHERE state='active'"
            ).scalar_one()
            == 2
        )
    registered.dispose()
    other.dispose()


def test_bounded_operator_pages_include_registered_attempt_owner(worker_engine, tmp_path):
    request, _ = queued(worker_engine)
    registered, instance = register(worker_engine, tmp_path)
    assert durable.claim(registered, "copilot", execution("copilot"), request) is not None
    page = workers.inspect_workers(worker_engine, limit=1)
    assert len(page["items"]) == 1 and str(page["items"][0]["instance_id"]) == instance
    attempts = workers.inspect_attempts(worker_engine, "copilot", limit=1)
    assert len(attempts["items"]) == 1
    assert attempts["items"][0]["operator_label"] == "owned-test-host"
    for limit in (0, 101, True):
        with pytest.raises(V2Error):
            workers.inspect_workers(worker_engine, limit)
    with pytest.raises(V2Error):
        workers.inspect_attempts(worker_engine, "copilot", cursor="malformed")
    registered.dispose()


def test_memo_cancellation_preserves_numerical_record_and_has_independent_receipt(worker_engine):
    from marketlab.memos.v2 import store as memos

    # Constraint-valid SQL fixture, not numerical acceptance evidence. No fake
    # model response, artifact or succeeded runtime dispatch is manufactured.
    run, submission = str(uuid4()), str(uuid4())
    with worker_engine.begin() as connection:
        execute(
            connection,
            "INSERT INTO v2_research_submissions VALUES "
            "(:id,'memo-fixture',:sha,'{}','research-spec-v2','{}',:sha,:sha,:sha,clock_timestamp())",
            id=submission,
            sha="a" * 64,
        )
        execute(
            connection,
            "INSERT INTO v2_research_runs VALUES "
            "(:run,:submission,'succeeded',0,0,0,NULL,NULL,clock_timestamp(),false,:run,NULL,"
            "clock_timestamp(),clock_timestamp())",
            run=run,
            submission=submission,
        )
        execute(
            connection,
            "INSERT INTO v2_research_results VALUES "
            "(:run,:path,:sha,:sha,:sha,1,1,clock_timestamp())",
            run=run,
            path=f"research-v2/{run}/manifest.json",
            sha="b" * 64,
        )
        numerical = one(connection, "SELECT * FROM v2_research_results WHERE run_id=:id", id=run)
        memos.register(connection, run, numerical, {}, execution("memo"))
    result = durable.cancel(worker_engine, "memo", run, 0, "memo-cancel")
    assert result["state"] == "cancelled" and result["state_revision"] == 1
    replay = durable.cancel(worker_engine, "memo", run, 0, "memo-cancel")
    assert replay["replayed"] is True
    with worker_engine.connect() as connection:
        assert (
            one(connection, "SELECT * FROM v2_research_results WHERE run_id=:id", id=run)
            == numerical
        )
        assert (
            one(connection, "SELECT * FROM v2_research_runs WHERE run_id=:id", id=run)["state"]
            == "succeeded"
        )
        assert (
            execute(
                connection, "SELECT model_calls FROM v2_memo_jobs WHERE run_id=:id", id=run
            ).scalar_one()
            == 0
        )
        assert execute(connection, "SELECT count(*) FROM v2_memo_attempts").scalar_one() == 0
        assert (
            one(connection, "SELECT * FROM v2_operations WHERE idempotency_key='memo-cancel'")[
                "operation"
            ]
            == "memo_cancel"
        )


async def test_real_admission_contention_spends_no_waiting_attempt_or_call(worker_engine):
    from marketlab import inference

    request, identity = queued(worker_engine)
    before = job(worker_engine, identity)
    async with inference.admission(worker_engine) as acquired:
        assert acquired

        async def contender():
            async with inference.admission(worker_engine) as waiting:
                assert waiting is False
                return None

        assert await asyncio.wait_for(asyncio.create_task(contender()), 5) is None
        await inference.validate_current(worker_engine)
    assert job(worker_engine, identity) == before
    assert durable.claim(worker_engine, "copilot", execution("copilot"), request) is not None


async def test_real_admission_session_loss_cancels_and_drains_local_fake_model(worker_engine):
    from marketlab import inference

    request, identity = queued(worker_engine)
    started, drained = asyncio.Event(), asyncio.Event()

    async def local_model_request():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            # Represents local HTTP consumer drain; says nothing about upstream
            # token generation. No model endpoint is contacted by this test.
            drained.set()

    async with inference.admission(worker_engine) as acquired:
        assert acquired
        current = durable.claim(worker_engine, "copilot", execution("copilot"), request)
        assert current is not None
        durable.reserve(
            worker_engine,
            current,
            {k: "a" * 64 for k in ("input_sha256", "schema_sha256", "prompt_sha256")},
            "b" * 64,
        )
        session = inference._held.get()[2]
        backend = session.connection.driver_connection.info.backend_pid

        async def lose_session():
            await started.wait()
            with worker_engine.begin() as connection:
                assert execute(
                    connection, "SELECT pg_terminate_backend(:pid)", pid=backend
                ).scalar_one()

        killer = asyncio.create_task(lose_session())
        with pytest.raises(V2Error) as error:
            await asyncio.wait_for(inference.guarded_call(worker_engine, local_model_request()), 6)
        assert error.value.code == "unavailable"
        assert drained.is_set()
        await killer
    durable.fail(worker_engine, current, transient=True)
    final = job(worker_engine, identity)
    assert final["model_calls"] == 1 and final["attempt_count"] == 1
    assert final["state"] == "retry_wait"
    with worker_engine.connect() as connection:
        call = one(connection, "SELECT * FROM v2_copilot_calls WHERE job_id=:id", id=identity)
        assert call["call_number"] == 1


async def test_service_admission_loss_after_reservation_blocks_post_and_retains_retry(
    worker_engine, tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from marketlab import inference
    from marketlab.copilot.v2.model import DIGEST
    from marketlab.copilot.v2.service import CopilotService

    request, identity = queued(worker_engine)

    class LocalModel:
        timeout = 10
        posts = 0

        def prepare(self, snapshot, turns):
            return {key: "a" * 64 for key in ("input_sha256", "schema_sha256", "prompt_sha256")}

        async def identify(self):
            return DIGEST

        async def interpret(self, *args, **kwargs):
            self.posts += 1
            raise AssertionError("Model POST must not start after admission loss")

    model = LocalModel()
    service = CopilotService(SimpleNamespace(engine=worker_engine, root=tmp_path), model)
    service._execution = execution("copilot")
    original = durable.reserve

    def reserve_then_lose(*args):
        number = original(*args)
        backend = inference._held.get()[2].connection.driver_connection.info.backend_pid
        with worker_engine.begin() as connection:
            assert execute(
                connection, "SELECT pg_terminate_backend(:pid)", pid=backend
            ).scalar_one()
        return number

    monkeypatch.setattr(durable, "reserve", reserve_then_lose)
    async with inference.admission(worker_engine) as acquired:
        assert acquired
        current = durable.claim(worker_engine, "copilot", execution("copilot"), request)
        await asyncio.wait_for(service.execute(current), 6)
    final = job(worker_engine, identity)
    assert model.posts == 0
    assert final["model_calls"] == 1 and final["attempt_count"] == 1
    assert final["state"] == "retry_wait"


@pytest.mark.parametrize("owner", ["unknown", "live", "foreign_machine"])
def test_recovery_refuses_unknown_live_or_foreign_ownership(worker_engine, tmp_path, owner):
    from marketlab.datasets.v2 import native_identity
    from marketlab.datasets.v2.common import canonical_json

    registered, instance = register(worker_engine, tmp_path)
    root = registered.get_execution_options()["worker_root_id"]
    with worker_engine.begin() as connection:
        if owner == "live":
            execute(
                connection,
                "UPDATE v2_worker_instances SET native_identity=:native WHERE instance_id=:id",
                native=canonical_json(native_identity.current()).decode(),
                id=instance,
            )
        elif owner == "foreign_machine":
            execute(
                connection,
                "UPDATE v2_worker_roots SET machine_identity=:machine WHERE root_id=:id",
                machine="f" * 64,
                id=root,
            )
    with pytest.raises(V2Error):
        workers.recover_root(registered, root, tmp_path)
    with worker_engine.connect() as connection:
        assert (
            one(
                connection,
                "SELECT state FROM v2_worker_instances WHERE instance_id=:id",
                id=instance,
            )["state"]
            == "ready"
        )
        assert (
            one(connection, "SELECT ready FROM v2_worker_roots WHERE root_id=:id", id=root)["ready"]
            is True
        )
    registered.dispose()


def test_actual_dead_owner_recovery_inventories_output_and_keeps_conservative_charges(
    worker_engine, tmp_path
):
    from marketlab.datasets.v2 import core, native_identity
    from marketlab.datasets.v2.common import canonical_json, sha256_file

    registered, instance = register(worker_engine, tmp_path)
    root = registered.get_execution_options()["worker_root_id"]
    native = native_identity.current()
    child = subprocess.Popen(
        [
            native["executable"],
            "-I",
            "-S",
            "-c",
            "import sys; print('ready', flush=True); sys.stdin.buffer.read(1)",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    ticket = str(uuid4())
    try:
        assert child.stdout.readline().strip() == b"ready"
        identity = native_identity.child(child.pid)
        output = tmp_path / "orphan-output.bin"
        output.write_bytes(b"retained native output")
        with core.transaction(registered) as connection:
            shared = workers.mode(connection)["shared_root_id"]
            execute(
                connection,
                "UPDATE v2_worker_instances SET native_identity=:native WHERE instance_id=:id",
                native=canonical_json(identity).decode(),
                id=instance,
            )
            execute(
                connection,
                "INSERT INTO v2_admission_tickets "
                "(ticket_id,root_id,role,owner,native_identity,physical_bytes,state,"
                "created_at,updated_at) "
                "VALUES(:id,:root,'research',:owner,:native,100,'active',clock_timestamp(),clock_timestamp())",
                id=ticket,
                root=shared,
                owner=str(uuid4()),
                native=canonical_json(identity).decode(),
            )
            execute(
                connection,
                "INSERT INTO v2_data_charges "
                "(charge_id,root_id,ticket_id,ceiling_bytes,charged_bytes,state,"
                "created_at,updated_at) "
                "VALUES(:id,:root,:ticket,100,100,'retained',clock_timestamp(),clock_timestamp())",
                id=str(uuid4()),
                root=shared,
                ticket=ticket,
            )
        child.stdin.write(b"x")
        child.stdin.flush()
        assert child.wait(timeout=5) == 0
        assert native_identity.dead(identity)
        recovered = workers.recover_root(registered, root, tmp_path)
        assert recovered["released_tickets"] == 1
        assert recovered["retained_bytes"] == output.stat().st_size
        with registered.connect() as connection:
            retained = one(connection, "SELECT * FROM v2_worker_files WHERE root_id=:id", id=root)
            assert retained["content_sha256"] == sha256_file(output)
            assert (
                one(
                    connection, "SELECT * FROM v2_admission_tickets WHERE ticket_id=:id", id=ticket
                )["state"]
                == "released"
            )
            assert (
                execute(
                    connection,
                    "SELECT sum(charged_bytes) FROM v2_data_charges WHERE state='retained'",
                ).scalar_one()
                == 100 + output.stat().st_size
            )
        workers.recover_root(registered, root, tmp_path)
        output.write_bytes(b"corrupted retained output")
        with pytest.raises(V2Error):
            workers.recover_root(registered, root, tmp_path)
        with registered.connect() as connection:
            assert (
                execute(
                    connection,
                    "SELECT sum(charged_bytes) FROM v2_data_charges WHERE state='retained'",
                ).scalar_one()
                == 100 + retained["file_bytes"]
            )
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
        child.stdin.close()
        child.stdout.close()
        registered.dispose()


def test_nonworker_root_context_enables_own_root_but_cannot_claim(worker_engine, tmp_path):
    registered, _ = register(worker_engine, tmp_path)
    root = registered.get_execution_options()["worker_root_id"]
    consumer = worker_engine.execution_options()
    workers.bind_root(consumer, tmp_path, root)
    with consumer.connect() as connection:
        assert str(workers.local_root(connection)["root_id"]) == root
        with pytest.raises(V2Error):
            workers.guard(connection, "copilot", digest(execution("copilot")))
    with pytest.raises(V2Error):
        workers.bind_root(consumer, tmp_path / "wrong", root)
    consumer.dispose()
    registered.dispose()


@pytest.mark.parametrize("loss", ["session", "lease", "cancel", "stop"])
async def test_actual_chat_post_rechecks_admission_and_job_owner_after_identify(
    worker_engine, loss
):
    import threading

    import httpx

    from marketlab import inference
    from marketlab.copilot.model import Ollama

    request, identity = queued(worker_engine)
    stopped = threading.Event()
    methods = []

    def endpoint(request):
        methods.append(request.method)
        return httpx.Response(200, json={"models": []})

    async with inference.admission(worker_engine) as acquired:
        assert acquired
        current = durable.claim(worker_engine, "copilot", execution("copilot"), request)
        durable.reserve(
            worker_engine,
            current,
            {k: "a" * 64 for k in ("input_sha256", "schema_sha256", "prompt_sha256")},
            "b" * 64,
        )
        async with httpx.AsyncClient(
            base_url="http://unused", transport=httpx.MockTransport(endpoint), trust_env=False
        ) as client:
            model = Ollama("http://unused", "unused")

            async def operation():
                await model.bounded(client, "GET", "/api/tags")
                if loss == "stop":
                    stopped.set()
                elif loss == "cancel":
                    durable.cancel(worker_engine, "copilot", identity, 1, "dispatch-cancel")
                else:
                    with worker_engine.begin() as connection:
                        if loss == "session":
                            backend = inference._held.get()[
                                2
                            ].connection.driver_connection.info.backend_pid
                            execute(connection, "SELECT pg_terminate_backend(:pid)", pid=backend)
                        else:
                            execute(
                                connection,
                                "UPDATE v2_copilot_jobs SET lease_until=clock_timestamp()-"
                                "interval '1 second' WHERE job_id=:id",
                                id=identity,
                            )
                await model.bounded(client, "POST", "/api/chat", json={})

            def ownership():
                with worker_engine.begin() as connection:
                    durable.fence(connection, current)

            with pytest.raises(V2Error):
                await asyncio.wait_for(
                    inference.guarded_call(worker_engine, operation(), stopped, ownership), 6
                )
    assert methods == ["GET"]
    assert job(worker_engine, identity)["model_calls"] == 1


def test_actual_metrics_snapshot_is_bounded_and_stale_is_unavailable(worker_engine, tmp_path):
    from prometheus_client import CollectorRegistry, generate_latest

    from marketlab import monitoring

    registered, _ = register(worker_engine, tmp_path)
    clock = [0.0]
    collector = monitoring.DurableCollector(clock=lambda: clock[0])
    collector.update(
        monitoring.collect_jobs(worker_engine), monitoring.collect_worker_details(worker_engine)
    )
    registry = CollectorRegistry()
    registry.register(collector)
    fresh = generate_latest(registry).decode()
    assert "marketlab_v2_workers_available 1.0" in fresh
    assert str(tmp_path) not in fresh and "owned-test-host" not in fresh
    assert len(fresh.encode()) <= 65536
    for metric in registry.collect():
        for sample in metric.samples:
            assert set(sample.labels) <= {"kind", "state", "reason"}
    clock[0] = 16.0
    stale = generate_latest(registry).decode()
    assert "marketlab_v2_workers_available 0.0" in stale
    assert "marketlab_durable_jobs{" not in stale
    registered.dispose()


@pytest.mark.parametrize("known_name,new_name", [("a.bin", "b.bin"), ("z.bin", "a.bin")])
def test_recovery_known_bytes_consume_shared_ticket_prefix_budget(
    worker_engine, tmp_path, monkeypatch, known_name, new_name
):
    from marketlab.datasets.v2 import core, native_children, native_identity
    from marketlab.datasets.v2.common import canonical_json, sha256_file

    registered, instance = register(worker_engine, tmp_path)
    root_id = registered.get_execution_options()["worker_root_id"]
    folder = tmp_path / "owned"
    folder.mkdir()
    known, later = folder / known_name, folder / new_name
    known.write_bytes(b"aaa")
    later.write_bytes(b"bbb")
    ticket = str(uuid4())
    identity = native_identity.current()
    with core.transaction(registered) as connection:
        shared = workers.mode(connection)["shared_root_id"]
        execute(
            connection,
            "UPDATE v2_worker_instances SET native_identity=:native WHERE instance_id=:id",
            native=canonical_json(identity).decode(),
            id=instance,
        )
        execute(
            connection,
            "INSERT INTO v2_admission_tickets "
            "(ticket_id,root_id,role,owner,native_identity,physical_bytes,state,"
            "created_at,updated_at) "
            "VALUES(:id,:root,'research',:owner,:native,4,'active',clock_timestamp(),clock_timestamp())",
            id=ticket,
            root=shared,
            owner=str(uuid4()),
            native=canonical_json(identity).decode(),
        )
        for prefix, budget in (("owned", 4), ("owned/" + new_name, 0)):
            execute(
                connection,
                "INSERT INTO v2_data_charges "
                "(charge_id,root_id,ticket_id,ceiling_bytes,charged_bytes,state,relative_path,"
                "created_at,updated_at) VALUES(:id,:root,:ticket,:bytes,:bytes,'retained',:path,"
                "clock_timestamp(),clock_timestamp())",
                id=str(uuid4()),
                root=shared,
                ticket=ticket,
                bytes=budget,
                path=prefix,
            )
        stat = known.stat()
        execute(
            connection,
            "INSERT INTO v2_worker_files VALUES(:id,:path,3,:mtime,:sha)",
            id=root_id,
            path="owned/" + known_name,
            mtime=stat.st_mtime_ns,
            sha=sha256_file(known),
        )
    # Real OS death is exercised separately above. Controlled native-death proof
    # isolates the accounting regression, using actual PostgreSQL transactions.
    monkeypatch.setattr(native_identity, "dead", lambda value: True)
    monkeypatch.setattr(native_children, "dead", lambda value: True)
    workers.recover_root(registered, root_id, tmp_path)
    with worker_engine.connect() as connection:
        total = execute(
            connection,
            "SELECT sum(charged_bytes) FROM v2_data_charges WHERE state IN ('retained','reserved')",
        ).scalar_one()
        assert total == 6  # 3 known + 3 new exceeds the single four-byte budget by two.
        extra = execute(
            connection,
            "SELECT sum(charged_bytes) FROM v2_data_charges "
            "WHERE resource_id=:id AND ticket_id IS NULL",
            id=root_id,
        ).scalar_one()
        assert extra == 2
    registered.dispose()


def test_recovery_output_reservation_mirror_cannot_duplicate_logical_credit(
    worker_engine, tmp_path, monkeypatch
):
    from test_v2_ingestion_integration import body

    from marketlab.datasets.v2 import core, jobs, native_children, native_identity
    from marketlab.datasets.v2.common import canonical_json

    registered, instance = register(worker_engine, tmp_path)
    submitted = jobs.submit(registered, body(), "recovery-output-mirror")
    with worker_engine.connect() as connection:
        job_id = execute(
            connection,
            "SELECT job_id FROM v2_ingestion_jobs WHERE submission_id=:id",
            id=submitted["submission_id"],
        ).scalar_one()
    root_id = registered.get_execution_options()["worker_root_id"]
    folder = tmp_path / "owned"
    folder.mkdir()
    (folder / "a.bin").write_bytes(b"aaa")
    (folder / "b.bin").write_bytes(b"bbb")
    ticket, charge = str(uuid4()), str(uuid4())
    identity = native_identity.current()
    with core.transaction(registered) as connection:
        shared = workers.mode(connection)["shared_root_id"]
        execute(
            connection,
            "UPDATE v2_worker_instances SET native_identity=:native WHERE instance_id=:id",
            native=canonical_json(identity).decode(),
            id=instance,
        )
        execute(
            connection,
            "INSERT INTO v2_admission_tickets "
            "(ticket_id,root_id,role,owner,native_identity,physical_bytes,state,"
            "created_at,updated_at) "
            "VALUES(:id,:root,'ingestion',:owner,:native,0,'active',clock_timestamp(),clock_timestamp())",
            id=ticket,
            root=shared,
            owner=str(uuid4()),
            native=canonical_json(identity).decode(),
        )
        execute(
            connection,
            "INSERT INTO v2_data_charges "
            "(charge_id,root_id,ticket_id,ceiling_bytes,charged_bytes,state,relative_path,"
            "created_at,updated_at) "
            "VALUES(:id,:root,:ticket,4,4,'retained','owned',clock_timestamp(),clock_timestamp())",
            id=charge,
            root=shared,
            ticket=ticket,
        )
        execute(
            connection,
            "INSERT INTO v2_storage_reservations "
            "(reservation_id,job_id,fencing_token,kind,reserved_bytes,retained_bytes,ceiling_bytes,"
            "state,relative_path,created_at,updated_at,data_charge_id) "
            "VALUES(:id,:job,1,'output',4,0,4,'reserved','owned',clock_timestamp(),clock_timestamp(),:charge)",
            id=str(uuid4()),
            job=job_id,
            charge=charge,
        )
    # Explicit synthetic death proof isolates credit mirroring; actual native
    # death and output inventory are covered by the separate owned-child test.
    monkeypatch.setattr(native_identity, "dead", lambda value: True)
    monkeypatch.setattr(native_children, "dead", lambda value: True)
    workers.recover_root(registered, root_id, tmp_path)
    with worker_engine.connect() as connection:
        assert (
            execute(
                connection,
                "SELECT sum(charged_bytes) FROM v2_data_charges "
                "WHERE state IN ('retained','reserved')",
            ).scalar_one()
            == 6
        )
        assert (
            execute(
                connection,
                "SELECT sum(charged_bytes) FROM v2_data_charges "
                "WHERE resource_id=:id AND ticket_id IS NULL",
                id=root_id,
            ).scalar_one()
            == 2
        )
    registered.dispose()


def test_provision_same_actual_machine_cannot_be_aliased_as_another_host(worker_engine, tmp_path):
    first, second = tmp_path / "first-root", tmp_path / "second-root"
    first.mkdir()
    second.mkdir()
    host, root, alias_host, alias_root = (str(uuid4()) for _ in range(4))
    workers.provision(worker_engine, host, "actual-owned-machine", root, first)
    with worker_engine.connect() as connection:
        before = one(connection, "SELECT * FROM v2_worker_roots WHERE root_id=:id", id=root)
    with pytest.raises(V2Error) as error:
        workers.provision(worker_engine, alias_host, "different-operator-uuid", alias_root, second)
    assert error.value.code == "revision_conflict"
    with worker_engine.connect() as connection:
        assert execute(connection, "SELECT count(*) FROM v2_worker_hosts").scalar_one() == 1
        assert execute(connection, "SELECT count(*) FROM v2_worker_roots").scalar_one() == 1
        assert one(connection, "SELECT * FROM v2_worker_roots WHERE root_id=:id", id=root) == before
        assert (
            one(connection, "SELECT * FROM v2_worker_hosts WHERE host_id=:id", id=alias_host)
            is None
        )
        assert (
            one(connection, "SELECT * FROM v2_worker_roots WHERE root_id=:id", id=alias_root)
            is None
        )


def audit_writer(engine, root, sequence):
    """Commit genuine live ownership and epoch before the controlled file write."""
    from marketlab.datasets.v2 import admission, core, native_identity
    from marketlab.datasets.v2.common import canonical_json

    ticket, owner, charge = str(uuid4()), str(uuid4()), str(uuid4())
    prefix = f"live-writer-{sequence}"
    # Acquiring the ordinary shared/physical locks here also proves the audit
    # does not hold these database locks across its paused filesystem walk.
    with core.transaction(engine) as connection:
        core.lock(connection, "v2-space:" + str(root))
        shared = workers.mode(connection)["shared_root_id"]
        execute(
            connection,
            "INSERT INTO v2_admission_tickets "
            "(ticket_id,root_id,role,owner,native_identity,physical_bytes,state,"
            "created_at,updated_at) "
            "VALUES(:id,:root,'research',:owner,:native,64,'active',clock_timestamp(),clock_timestamp())",
            id=ticket,
            root=shared,
            owner=owner,
            native=canonical_json(native_identity.current()).decode(),
        )
        execute(
            connection,
            "INSERT INTO v2_data_charges "
            "(charge_id,root_id,ticket_id,ceiling_bytes,charged_bytes,state,relative_path,"
            "created_at,updated_at) "
            "VALUES(:id,:root,:ticket,64,64,'reserved',:path,clock_timestamp(),clock_timestamp())",
            id=charge,
            root=shared,
            ticket=ticket,
            path=prefix,
        )
        admission.changed(connection, {"ticket_id": ticket, "owner": owner})
    directory = root / prefix
    directory.mkdir()
    (directory / "output.bin").write_bytes(b"legitimate live output")


def test_distributed_audit_retries_live_writer_committed_after_its_snapshot(
    worker_engine, tmp_path, monkeypatch
):
    from marketlab.datasets.v2 import admission

    registered, _ = register(worker_engine, tmp_path)
    original_files, original_audit = admission._files, workers.audit_root
    walks, observed_errors = [], []

    def interleave(root, **kwargs):
        walks.append(True)
        if len(walks) == 1:
            audit_writer(registered, root, 1)
        yield from original_files(root, **kwargs)

    def observe_real_audit(*args, **kwargs):
        try:
            return original_audit(*args, **kwargs)
        except V2Error as error:
            observed_errors.append(error.code)
            raise

    monkeypatch.setattr(admission, "_files", interleave)
    monkeypatch.setattr(workers, "audit_root", observe_real_audit)
    admission.audit(registered, tmp_path)
    assert len(walks) == 2 and observed_errors == ["audit_changed"]
    assert (tmp_path / "live-writer-1/output.bin").read_bytes() == b"legitimate live output"
    with worker_engine.connect() as connection:
        assert (
            execute(
                connection, "SELECT count(*) FROM v2_admission_tickets WHERE state='active'"
            ).scalar_one()
            == 1
        )
        assert (
            execute(connection, "SELECT sum(charged_bytes) FROM v2_data_charges").scalar_one() == 64
        )
    registered.dispose()


def test_distributed_audit_stable_unmanaged_bytes_remain_integrity_failure(worker_engine, tmp_path):
    from marketlab.datasets.v2 import admission

    registered, _ = register(worker_engine, tmp_path)
    (tmp_path / "unmanaged.bin").write_bytes(b"not covered by any owner")
    with worker_engine.connect() as connection:
        epoch = execute(
            connection, "SELECT epoch FROM v2_capacity_roots WHERE singleton"
        ).scalar_one()
    with pytest.raises(V2Error) as error:
        admission.audit(registered, tmp_path)
    assert error.value.code == "integrity_failure"
    with worker_engine.connect() as connection:
        assert (
            execute(connection, "SELECT epoch FROM v2_capacity_roots WHERE singleton").scalar_one()
            == epoch
        )
    assert (tmp_path / "unmanaged.bin").read_bytes() == b"not covered by any owner"
    registered.dispose()


def test_distributed_audit_three_genuine_epoch_changes_end_bounded_unavailable(
    worker_engine, tmp_path, monkeypatch
):
    from marketlab.datasets.v2 import admission

    registered, _ = register(worker_engine, tmp_path)
    original = admission._files
    walks = []

    def interleave(root, **kwargs):
        walks.append(True)
        audit_writer(registered, root, len(walks))
        yield from original(root, **kwargs)

    monkeypatch.setattr(admission, "_files", interleave)
    with pytest.raises(V2Error) as error:
        admission.audit(registered, tmp_path)
    assert error.value.code == "unavailable" and len(walks) == 3
    with worker_engine.connect() as connection:
        assert (
            execute(
                connection, "SELECT count(*) FROM v2_admission_tickets WHERE state='active'"
            ).scalar_one()
            == 3
        )
        assert (
            execute(connection, "SELECT sum(charged_bytes) FROM v2_data_charges").scalar_one()
            == 192
        )
    assert len(list(tmp_path.glob("live-writer-*/output.bin"))) == 3
    registered.dispose()


def memo_cancel_fixture(engine):
    """Constraint-valid numerical rows for cancellation SQL, not acceptance credit."""
    from marketlab.memos.v2 import store as memos

    run, submission = str(uuid4()), str(uuid4())
    with engine.begin() as connection:
        execute(
            connection,
            "INSERT INTO v2_research_submissions VALUES "
            "(:id,'cancel-noop-memo',:sha,'{}','research-spec-v2','{}',:sha,:sha,:sha,clock_timestamp())",
            id=submission,
            sha="a" * 64,
        )
        execute(
            connection,
            "INSERT INTO v2_research_runs VALUES "
            "(:run,:submission,'succeeded',0,0,0,NULL,NULL,clock_timestamp(),false,:run,NULL,"
            "clock_timestamp(),clock_timestamp())",
            run=run,
            submission=submission,
        )
        execute(
            connection,
            "INSERT INTO v2_research_results VALUES "
            "(:run,:path,:sha,:sha,:sha,1,1,clock_timestamp())",
            run=run,
            path=f"research-v2/{run}/manifest.json",
            sha="b" * 64,
        )
        numerical = one(connection, "SELECT * FROM v2_research_results WHERE run_id=:id", id=run)
        memos.register(connection, run, numerical, {}, execution("memo"))
    return run


def cancellation_evidence(engine, kind, identity):
    from marketlab.datasets.v2.common import canonical_json
    from marketlab.datasets.v2.core import wire

    prefix, ident = durable.table(kind)
    with engine.connect() as connection:
        row = one(connection, f"SELECT * FROM {prefix}_jobs WHERE {ident}=:id", id=identity)
        value = {"job": row}
        for suffix, order in (("attempts", "attempt_number"), ("calls", "call_number")):
            value[suffix] = [
                dict(item)
                for item in execute(
                    connection,
                    f"SELECT * FROM {prefix}_{suffix} WHERE {ident}=:id ORDER BY {order}",
                    id=identity,
                ).mappings()
            ]
        value["operations"] = [
            dict(item)
            for item in execute(
                connection,
                "SELECT * FROM v2_operations WHERE operation=:operation AND resource_id=:id "
                "ORDER BY idempotency_key",
                operation=kind + "_cancel",
                id=identity,
            ).mappings()
        ]
        for table, order in (
            ("v2_admission_tickets", "ticket_id"),
            ("v2_data_charges", "charge_id"),
            ("v2_storage_reservations", "reservation_id"),
            ("v2_research_reservations", "reservation_id"),
        ):
            value[table] = [
                dict(item)
                for item in execute(
                    connection, f"SELECT * FROM {table} ORDER BY {order}"
                ).mappings()
            ]
        if kind == "copilot":
            value["request"] = one(
                connection,
                "SELECT * FROM v2_copilot_requests WHERE request_id=:id",
                id=row["request_id"],
            )
            value["revisions"] = [
                dict(item)
                for item in execute(
                    connection,
                    "SELECT * FROM v2_copilot_revisions WHERE request_id=:id ORDER BY revision",
                    id=row["request_id"],
                ).mappings()
            ]
        else:
            value["numerical_run"] = one(
                connection, "SELECT * FROM v2_research_runs WHERE run_id=:id", id=identity
            )
            value["numerical_result"] = one(
                connection, "SELECT * FROM v2_research_results WHERE run_id=:id", id=identity
            )
    return canonical_json(wire(value))


@pytest.mark.parametrize("kind", ["copilot", "memo"])
@pytest.mark.parametrize("target_state", ["running", "cancelled"])
def test_fresh_cancel_key_conflicts_after_request_and_original_receipt_remains_immutable(
    worker_engine, kind, target_state
):
    from marketlab.copilot.v2.model import DIGEST

    if kind == "copilot":
        target, identity = queued(worker_engine, "cancel-noop-copilot")
    else:
        target = identity = memo_cancel_fixture(worker_engine)
    current = durable.claim(worker_engine, kind, execution(kind), target)
    assert current is not None
    durable.reserve(
        worker_engine,
        current,
        {name: "a" * 64 for name in ("input_sha256", "schema_sha256", "prompt_sha256")},
        DIGEST,
    )
    first = durable.cancel(worker_engine, kind, identity, 1, "original-cancel")
    assert first["state"] == "running" and first["state_revision"] == 2
    if target_state == "cancelled":
        durable.fail(worker_engine, current)
    prefix, ident = durable.table(kind)
    with worker_engine.connect() as connection:
        row = one(connection, f"SELECT * FROM {prefix}_jobs WHERE {ident}=:id", id=identity)
    assert row["state"] == target_state and row["cancel_requested"]
    assert row["state_revision"] == (2 if target_state == "running" else 3)
    before = cancellation_evidence(worker_engine, kind, identity)
    replay = durable.cancel(worker_engine, kind, identity, 1, "original-cancel")
    assert replay == {**first, "replayed": True}
    assert cancellation_evidence(worker_engine, kind, identity) == before
    with pytest.raises(V2Error) as error:
        durable.cancel(worker_engine, kind, identity, row["state_revision"], "fresh-cancel")
    assert error.value.code == "revision_conflict"
    assert cancellation_evidence(worker_engine, kind, identity) == before
    assert durable.cancel(worker_engine, kind, identity, 1, "original-cancel") == replay
    assert cancellation_evidence(worker_engine, kind, identity) == before
    with worker_engine.connect() as connection:
        assert (
            execute(
                connection, f"SELECT model_calls FROM {prefix}_jobs WHERE {ident}=:id", id=identity
            ).scalar_one()
            == 1
        )
        assert execute(connection, "SELECT count(*) FROM v2_operations").scalar_one() == 1
        assert (
            one(connection, "SELECT * FROM v2_operations WHERE idempotency_key='fresh-cancel'")
            is None
        )
