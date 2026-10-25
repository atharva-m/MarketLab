"""Real PostgreSQL copilot durability, fencing, clarification and atomic handoff."""

import asyncio
import copy
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import httpx
import pytest
import sqlalchemy as sa
from test_copilot import INTENT, candidate, request
from test_research_integration import published
from test_research_integration import research_engine as research_engine

from marketlab.app import create_app
from marketlab.copilot import store
from marketlab.copilot.model import Ollama
from marketlab.copilot.service import INFERENCE_LOCK, CopilotService
from marketlab.copilot.spec import turn
from marketlab.research import store as research_store
from marketlab.research.spec import ResearchError

pytestmark = pytest.mark.integration


@pytest.fixture
def copilot_engine(research_engine):
    schema = research_engine.get_execution_options()["schema_translate_map"][None]
    with research_engine.begin() as connection:
        for name in ("copilot_requests", "copilot_revisions", "copilot_jobs", "copilot_attempts"):
            connection.execute(
                sa.text(f'CREATE TABLE "{schema}".{name} (LIKE public.{name} INCLUDING ALL)')
            )
    return research_engine


class FakeModel(Ollama):
    def __init__(self, result=None, failure=None):
        self.result = candidate() if result is None else result
        self.failure = failure
        self.calls = 0
        self.digest = "fake-digest"

    async def identify(self):
        return self.digest

    async def infer(self, turns, pinned=None):
        self.calls += 1
        if self.failure:
            raise self.failure
        return copy.deepcopy(self.result), {
            "model_digest": self.digest,
            "response": json.dumps(self.result),
        }


def ready(engine, tmp_path, model=None):
    research, spec = published(engine, tmp_path)
    service = CopilotService(research, model or FakeModel())
    body = request()
    body["dataset_versions"] = list(spec.dataset_versions)
    return service, spec, body


def expire(engine, current):
    with engine.begin() as connection:
        connection.execute(
            store.jobs.update()
            .where(store.jobs.c.job_id == current.job_id)
            .values(lease_until=sa.func.clock_timestamp() - timedelta(seconds=1))
        )


def due(engine):
    with engine.begin() as connection:
        connection.execute(
            store.jobs.update()
            .where(store.jobs.c.state == "retry_wait")
            .values(eligible_at=sa.func.clock_timestamp() - timedelta(seconds=1))
        )


@pytest.mark.asyncio
async def test_end_to_end_atomic_handoff_replay_and_same_numerics(copilot_engine, tmp_path):
    service, spec, body = ready(copilot_engine, tmp_path)
    try:
        identity, revision, replayed = await service.create(body, "one")
        assert revision == 0 and not replayed
        assert await service.create(body, "one") == (identity, 0, True)
        assert await service.work(1, identity) == 1
        info = service.inspect(identity)
        assert info["outcome"] == "submitted" and info["run_id"]
        assert info["revisions"][0]["spec"] == spec.body()
        assert info["revisions"][0]["model_calls"] == 1
        assert await service.work(1, identity) == 0
        manual, _ = await service.research.submit(spec, "manual")
        assert await service.research.work(2) == 2
        for kind in ("results", "summary"):
            assert (
                service.research.read(manual, kind)[1]
                == service.research.read(info["run_id"], kind)[1]
            )
        body["text"] = "Other"
        with pytest.raises(ResearchError, match="conflict"):
            await service.create(body, "one")
    finally:
        await service.research.close()
        await service.research.bars.close()


@pytest.mark.asyncio
async def test_clarification_restart_answer_idempotency_concurrency(copilot_engine, tmp_path):
    model = FakeModel()
    service, _, body = ready(copilot_engine, tmp_path, model)
    body["context"].pop("history_start")
    model.result = candidate({n: v for n, v in INTENT.items() if n != "history_start"})
    identity, _, _ = await service.create(body, "clarify")
    await service.work(1, identity)
    assert service.inspect(identity)["outcome"] == "needs_clarification"
    answer = {
        "schema": "copilot-answer-v1",
        "expected_revision": 0,
        "text": "Use this explicit history start",
        "context": {"history_start": INTENT["history_start"]},
    }
    # Reconstructed service reads durable conversation and resumes.
    resumed = CopilotService(service.research, FakeModel())
    with ThreadPoolExecutor(2) as pool:
        values = list(
            pool.map(
                lambda _: store.answer(copilot_engine, identity, turn(answer, True), "answer"),
                range(2),
            )
        )
    assert sorted(v[2] for v in values) == [False, True]
    assert await resumed.answer(identity, answer, "answer") == (identity, 1, True)
    with pytest.raises(ResearchError, match="state conflict"):
        await resumed.answer(identity, answer, "different-key")
    await resumed.work(1, identity)
    assert resumed.inspect(identity)["outcome"] == "submitted"
    assert len(resumed.inspect(identity)["revisions"]) == 2
    await service.research.bars.close()


def test_concurrent_create_claim_and_queued_clock_regression(copilot_engine):
    body = turn(request())
    with ThreadPoolExecutor(8) as pool:
        values = list(pool.map(lambda _: store.create(copilot_engine, body, "same"), range(8)))
    assert len({v[0] for v in values}) == 1
    assert sum(not v[2] for v in values) == 1
    with copilot_engine.begin() as connection:
        connection.execute(
            store.jobs.update().values(eligible_at=sa.func.clock_timestamp() + timedelta(days=1))
        )
    with ThreadPoolExecutor(4) as pool:
        claims = list(pool.map(lambda _: store.claim(copilot_engine), range(4)))
    assert len([c for c in claims if c is not None]) == 1


def test_heartbeat_stale_fencing_attempt_and_call_cap(copilot_engine):
    identity, _, _ = store.create(copilot_engine, turn(request()), "lease")
    first = store.claim(copilot_engine, identity)
    assert store.heartbeat(copilot_engine, first)
    store.reserve_call(copilot_engine, first)
    expire(copilot_engine, first)
    assert not store.heartbeat(copilot_engine, first)
    second = store.claim(copilot_engine, identity)
    assert second.attempt == 2 and second.token > first.token
    for operation in [
        lambda: store.fail(copilot_engine, first),
        lambda: store.reserve_call(copilot_engine, first),
        lambda: store.checkpoint(copilot_engine, first, candidate(), {}),
        lambda: store.finish(copilot_engine, first, "unsupported", []),
    ]:
        with pytest.raises(ResearchError, match="ownership"):
            operation()
    store.reserve_call(copilot_engine, second)
    with pytest.raises(ResearchError, match="budget"):
        store.reserve_call(copilot_engine, second)
    expire(copilot_engine, second)
    third = store.claim(copilot_engine, identity)
    assert third.attempt == 3
    expire(copilot_engine, third)
    assert store.claim(copilot_engine, identity) is None
    info = store.inspect(copilot_engine, identity)
    assert info["outcome"] == "failed" and info["revisions"][0]["model_calls"] == 2
    assert len(info["revisions"][0]["attempts"]) == 3


@pytest.mark.asyncio
async def test_two_model_calls_then_recovery_cannot_dispatch_third(copilot_engine, tmp_path):
    model = FakeModel(failure=TimeoutError())
    service, _, body = ready(copilot_engine, tmp_path, model)
    identity, _, _ = await service.create(body, "calls")
    for _ in range(3):
        await service.work(1, identity)
        due(copilot_engine)
    assert model.calls == 2
    assert service.inspect(identity)["outcome"] == "failed"
    await service.research.bars.close()


@pytest.mark.asyncio
async def test_checkpoint_recovery_without_another_model_call(copilot_engine, tmp_path):
    service, spec, body = ready(copilot_engine, tmp_path)
    identity, _, _ = await service.create(body, "checkpoint")
    current = store.claim(copilot_engine, identity)
    store.reserve_call(copilot_engine, current)
    store.checkpoint(
        copilot_engine, current, candidate(), {"execution": service.research.execution}
    )
    expire(copilot_engine, current)
    await service.work(1, identity)
    assert service.model.calls == 0
    assert service.inspect(identity)["outcome"] == "submitted"
    await service.research.bars.close()


@pytest.mark.asyncio
async def test_pinned_digest_survives_timeout_and_rejects_tag_swap(copilot_engine, tmp_path):
    model = FakeModel(failure=TimeoutError())
    service, _, body = ready(copilot_engine, tmp_path, model)
    identity, _, _ = await service.create(body, "digest")
    await service.work(1, identity)
    assert service.inspect(identity)["revisions"][0]["provenance"]["model_digest"] == "fake-digest"
    model.digest = "changed"
    model.failure = None
    due(copilot_engine)
    await service.work(1, identity)
    assert model.calls == 1 and service.inspect(identity)["outcome"] == "failed"
    await service.research.bars.close()


@pytest.mark.asyncio
async def test_atomic_rollback_visibility_and_manual_key_collision(copilot_engine, tmp_path):
    service, spec, body = ready(copilot_engine, tmp_path)
    identity, _, _ = await service.create(body, "rollback")
    current = store.claim(copilot_engine, identity)
    fingerprint = await service.research.prepare(spec)
    with pytest.raises(RuntimeError):
        with copilot_engine.begin() as connection:
            run = store.complete(connection, current, "submitted", [], spec.body(), fingerprint)
            with copilot_engine.connect() as other:
                assert (
                    other.scalar(
                        sa.select(research_store.runs.c.run_id).where(
                            research_store.runs.c.run_id == run
                        )
                    )
                    is None
                )
            raise RuntimeError("rollback")
    assert service.inspect(identity)["run_id"] is None
    with copilot_engine.connect() as connection:
        assert connection.scalar(sa.select(sa.func.count()).select_from(research_store.runs)) == 0
    manual, _ = await service.research.submit(spec, "copilot." + identity)
    with pytest.raises(ResearchError, match="key conflict"):
        store.finish(copilot_engine, current, "submitted", [], spec.body(), fingerprint)
    assert service.inspect(identity)["run_id"] is None
    assert service.research.inspect(manual)["state"] == "queued"
    await service.research.bars.close()


@pytest.mark.asyncio
async def test_inference_admission_and_cancellation_release(copilot_engine, tmp_path):
    service, _, body = ready(copilot_engine, tmp_path)
    identity, _, _ = await service.create(body, "admission")
    with copilot_engine.connect() as connection:
        connection.execute(sa.select(sa.func.pg_advisory_lock(INFERENCE_LOCK)))
        connection.commit()
        await service.work(1, identity)
        assert service.inspect(identity)["state"] == "retry_wait"
        assert service.model.calls == 0
        connection.execute(sa.select(sa.func.pg_advisory_unlock(INFERENCE_LOCK)))
        connection.commit()
    due(copilot_engine)
    await service.work(1, identity)
    assert service.inspect(identity)["outcome"] == "submitted"
    await service.research.bars.close()


@pytest.mark.asyncio
async def test_http_and_cli_creation_inspection(copilot_engine, tmp_path):
    service, _, body = ready(copilot_engine, tmp_path)
    app = create_app()
    app.state.copilot_service = service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            "/v1/copilot/requests", json=body, headers={"Idempotency-Key": "http"}
        )
        assert r.status_code == 201
        identity = r.json()["request_id"]
        assert (await client.get("/v1/copilot/requests/" + identity)).json()["state"] == "queued"
        assert (
            await client.post(
                "/v1/copilot/requests", json=body, headers={"Idempotency-Key": "http"}
            )
        ).status_code == 200
    # CLI inspect is real subprocess against isolated schema through PGOPTIONS.
    schema = copilot_engine.get_execution_options()["schema_translate_map"][None]
    env = {**os.environ, "PGOPTIONS": "-c search_path=" + schema + ",public"}
    result = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "marketlab.copilot_cli", "inspect", "--request", identity],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0 and json.loads(result.stdout)["request_id"] == identity
    await service.research.bars.close()


@pytest.mark.parametrize("phase", ["before", "during", "after"])
@pytest.mark.asyncio
async def test_real_process_death_around_handoff(copilot_engine, tmp_path, phase):
    service, spec, body = ready(copilot_engine, tmp_path)
    identity, _, _ = await service.create(body, "kill-" + phase)
    current = store.claim(copilot_engine, identity)
    fingerprint = await service.research.prepare(spec)
    payload = tmp_path / "payload.json"
    payload.write_text(
        json.dumps(
            {
                "claim": {
                    "job_id": current.job_id,
                    "request_id": identity,
                    "revision": 0,
                    "owner": current.owner,
                    "token": current.token,
                    "attempt": current.attempt,
                },
                "spec": spec.body(),
                "fingerprint": fingerprint,
            }
        ),
        encoding="utf-8",
    )
    marker = tmp_path / "marker"
    script = tmp_path / "crash.py"
    schema = copilot_engine.get_execution_options()["schema_translate_map"][None]
    script.write_text(
        """import json,os,time,sys
from pathlib import Path
from sqlalchemy import create_engine
from marketlab.copilot import store
p=json.loads(Path(sys.argv[1]).read_text())
e=create_engine(os.environ['MARKETLAB_DATABASE_URL']).execution_options(schema_translate_map={None:sys.argv[4]})
c=store.Claim(**p['claim'])
phase=sys.argv[3]
if phase=='before':
 Path(sys.argv[2]).write_text('before')
 time.sleep(60)
with e.begin() as connection:
 store.complete(connection,c,'submitted',[],p['spec'],p['fingerprint'])
 if phase=='during':
  Path(sys.argv[2]).write_text('during')
  time.sleep(60)
Path(sys.argv[2]).write_text('after')
time.sleep(60)
""",
        encoding="utf-8",
    )
    process = await asyncio.to_thread(
        subprocess.Popen,
        [sys.executable, str(script), str(payload), str(marker), phase, schema],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        for _ in range(200):
            if marker.exists() or process.poll() is not None:
                break
            await asyncio.sleep(0.05)
        assert marker.exists(), (
            process.stderr.read().decode() if process.poll() is not None else "no marker"
        )
    finally:
        process.kill()
        await asyncio.to_thread(process.wait, timeout=10)
    info = service.inspect(identity)
    if phase == "after":
        assert info["outcome"] == "submitted" and info["run_id"]
    else:
        assert info["run_id"] is None
        expire(copilot_engine, current)
        recovered = store.claim(copilot_engine, identity)
        store.finish(copilot_engine, recovered, "submitted", [], spec.body(), fingerprint)
    with copilot_engine.connect() as connection:
        assert connection.scalar(sa.select(sa.func.count()).select_from(research_store.runs)) == 1
    await service.research.bars.close()


def test_actual_fresh_populated_migration_and_constraints(copilot_engine):
    from uuid import uuid4

    schema = "r5_migration_" + uuid4().hex
    base = copilot_engine.engine
    with base.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    env = {**os.environ, "PGOPTIONS": "-c search_path=" + schema}
    try:
        for target in ("0005_research", "head"):
            outcome = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", target],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert outcome.returncode == 0, outcome.stderr
            if target != "head":
                with base.begin() as connection:
                    connection.execute(
                        sa.text(f'''INSERT INTO "{schema}".trades
                        (trade_id,symbol,price,quantity,executed_at)
                        VALUES ('r5-keep','BTCUSDT',1,1,'2025-01-01T00:00:00Z')''')
                    )
        with base.connect() as connection:
            assert connection.scalar(sa.text(f'SELECT count(*) FROM "{schema}".trades')) == 1
            assert (
                connection.scalar(sa.text(f'SELECT version_num FROM "{schema}".alembic_version'))
                == "0006_copilot"
            )
            count = connection.scalar(
                sa.text("""SELECT count(*) FROM pg_constraint c
                JOIN pg_namespace n ON n.oid=c.connamespace
                WHERE n.nspname=:schema AND c.contype='f'
                AND c.conrelid::regclass::text LIKE '%copilot%' """),
                {"schema": schema},
            )
            assert count == 4
        isolated = base.execution_options(schema_translate_map={None: schema})
        identity, _, _ = store.create(isolated, turn(request()), "constraints")
        with pytest.raises(sa.exc.IntegrityError):
            with isolated.begin() as connection:
                connection.execute(
                    store.requests.update()
                    .where(store.requests.c.request_id == identity)
                    .values(run_id="0" * 36)
                )
        with pytest.raises(sa.exc.IntegrityError):
            with isolated.begin() as connection:
                connection.execute(store.jobs.update().values(model_calls=3))
    finally:
        with base.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))


@pytest.mark.asyncio
async def test_cancel_during_session_lock_acquisition_releases_physical_lock(
    copilot_engine, tmp_path, monkeypatch
):
    import threading

    from sqlalchemy.engine import Connection

    service, _, body = ready(copilot_engine, tmp_path)
    identity, _, _ = await service.create(body, "cancel-lock")
    current = store.claim(copilot_engine, identity)
    original = Connection.scalar
    entered, release = threading.Event(), threading.Event()

    def delayed(connection, statement, *args, **kwargs):
        result = original(connection, statement, *args, **kwargs)
        if "pg_try_advisory_lock" in str(statement):
            entered.set()
            release.wait(5)
        return result

    monkeypatch.setattr(Connection, "scalar", delayed)
    task = asyncio.create_task(service.infer(current, [body], None))
    for _ in range(100):
        if entered.is_set():
            break
        await asyncio.sleep(0.01)
    assert entered.is_set()
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    monkeypatch.setattr(Connection, "scalar", original)
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    independent = create_engine(copilot_engine.url, poolclass=NullPool)
    with independent.connect() as connection:
        assert connection.scalar(sa.select(sa.func.pg_try_advisory_lock(INFERENCE_LOCK)))
        connection.execute(sa.select(sa.func.pg_advisory_unlock(INFERENCE_LOCK)))
    independent.dispose()
    await service.research.bars.close()


def test_mutation_expiry_between_fence_and_final_update_rolls_back(copilot_engine, monkeypatch):
    identity, _, _ = store.create(copilot_engine, turn(request()), "near-expiry")
    current = store.claim(copilot_engine, identity)
    original = store.fence

    def expiring(connection, claim):
        original(connection, claim)
        connection.execute(
            store.jobs.update()
            .where(store.jobs.c.job_id == claim.job_id)
            .values(lease_until=sa.func.clock_timestamp() - timedelta(seconds=1))
        )

    monkeypatch.setattr(store, "fence", expiring)
    for operation in (
        lambda: store.fail(copilot_engine, current),
        lambda: store.checkpoint(copilot_engine, current, candidate(), {}),
    ):
        with pytest.raises(ResearchError, match="ownership"):
            operation()
    info = store.inspect(copilot_engine, identity)
    assert info["outcome"] is None and info["revisions"][0]["interpretation"] is None
    assert info["revisions"][0]["attempts"][0]["outcome"] == "running"
    current.lost.set()
    assert not store.heartbeat(copilot_engine, current)
