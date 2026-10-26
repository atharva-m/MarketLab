"""Real PostgreSQL memo atomicity, budgets, priority, recovery and corruption."""

import asyncio
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import httpx
import pytest
import sqlalchemy as sa
from test_copilot import request
from test_copilot_integration import FakeModel
from test_copilot_integration import copilot_engine as copilot_engine
from test_memos import valid_draft
from test_research_integration import published
from test_research_integration import research_engine as research_engine

from marketlab.copilot import store as copilot_store
from marketlab.copilot.service import CopilotService
from marketlab.copilot.spec import turn
from marketlab.inference import admission
from marketlab.inference_cli import work
from marketlab.memos import store
from marketlab.memos.model import MemoModel
from marketlab.memos.service import MemoService
from marketlab.memos.spec import facts
from marketlab.research import store as research_store
from marketlab.research.spec import ResearchError

pytestmark = pytest.mark.integration


class FakeMemoModel(MemoModel):
    def __init__(self, error=None):
        self.calls = 0
        self.error = error

    async def identify(self):
        return "fake-digest"

    async def generate(self, source, pinned):
        self.calls += 1
        if self.error is not None:
            raise self.error
        value = valid_draft()
        return value, {"model_digest": "fake-digest", "response": json.dumps(value)}


async def ready(engine, tmp_path, model=None):
    research, spec = published(engine, tmp_path)
    run, _ = await research.submit(spec, "memo-run")
    await research.work(1, run)
    assert research.inspect(run)["state"] == "succeeded"
    return MemoService(research, model or FakeMemoModel()), run


def expire(engine, run):
    with engine.begin() as connection:
        connection.execute(
            store.jobs.update()
            .where(store.jobs.c.run_id == run)
            .values(lease_until=sa.func.clock_timestamp() - timedelta(seconds=1))
        )


def due(engine, run):
    with engine.begin() as connection:
        connection.execute(
            store.jobs.update()
            .where(store.jobs.c.run_id == run)
            .values(eligible_at=sa.func.clock_timestamp() - timedelta(seconds=1))
        )


@pytest.mark.asyncio
async def test_atomic_enqueue_publication_replay_and_hash_preservation(copilot_engine, tmp_path):
    memo, run = await ready(copilot_engine, tmp_path)
    numerical = memo.research.root / "research" / run
    before = {p.name: p.read_bytes() for p in numerical.iterdir() if p.is_file()}
    assert store.inspect(copilot_engine, run)["state"] == "queued"
    with ThreadPoolExecutor(2) as pool:
        assert all(replayed for _, replayed in pool.map(lambda _: memo.enqueue(run), range(2)))
    assert await memo.work(1, run) == 1
    content, manifest = memo.read(run)
    assert len(content.strip().split("\n\n")) == 3 and manifest["summary_sha256"]
    assert memo.enqueue(run) == (run, True)
    assert await memo.work(1, run) == 0 and memo.read(run)[0] == content
    assert {name: (numerical / name).read_bytes() for name in before} == before
    assert (
        memo.inspect(run)["status"] == "ready" and "response" not in memo.inspect(run)["provenance"]
    )
    await memo.research.bars.close()


@pytest.mark.asyncio
async def test_numerical_enqueue_failure_rolls_back_and_recovery_adopts(
    copilot_engine, tmp_path, monkeypatch
):
    research, spec = published(copilot_engine, tmp_path)
    run, _ = await research.submit(spec, "rollback")
    original = store.enqueue

    def reject(*args):
        raise ResearchError("injected")

    monkeypatch.setattr(store, "enqueue", reject)
    await research.work(1, run)
    with copilot_engine.connect() as connection:
        assert (
            connection.execute(
                sa.select(research_store.results).where(research_store.results.c.run_id == run)
            ).first()
            is None
        )
        assert connection.execute(sa.select(store.jobs)).first() is None
    assert research.inspect(run)["state"] == "failed"
    monkeypatch.setattr(store, "enqueue", original)
    await research.bars.close()


@pytest.mark.asyncio
async def test_historical_enqueue_idempotency_and_terminal_no_reset(copilot_engine, tmp_path):
    memo, run = await ready(copilot_engine, tmp_path)
    with copilot_engine.begin() as connection:
        connection.execute(store.jobs.delete().where(store.jobs.c.run_id == run))
    assert memo.enqueue(run) == (run, False)
    current = store.claim(copilot_engine, run)
    store.fail(copilot_engine, current)
    assert memo.enqueue(run) == (run, True)
    assert store.inspect(copilot_engine, run)["state"] == "failed"
    assert store.claim(copilot_engine, run) is None
    await memo.research.bars.close()


@pytest.mark.asyncio
async def test_concurrent_claim_clock_heartbeat_expiry_and_stale_fencing(copilot_engine, tmp_path):
    memo, run = await ready(copilot_engine, tmp_path)
    with copilot_engine.begin() as connection:
        connection.execute(
            store.jobs.update().values(eligible_at=sa.func.clock_timestamp() + timedelta(hours=1))
        )
    with ThreadPoolExecutor(2) as pool:
        claimed = list(pool.map(lambda _: store.claim(copilot_engine, run), range(2)))
    current = next(c for c in claimed if c is not None)
    assert sum(c is not None for c in claimed) == 1 and store.heartbeat(copilot_engine, current)
    expire(copilot_engine, run)
    other = store.claim(copilot_engine, run)
    assert other.token == current.token + 1 and not store.heartbeat(copilot_engine, current)
    for operation in (
        lambda: store.reserve_call(copilot_engine, current),
        lambda: store.checkpoint(copilot_engine, current, valid_draft(), {}),
        lambda: store.fail(copilot_engine, current),
    ):
        with pytest.raises(ResearchError, match="ownership"):
            operation()
    expire(copilot_engine, run)
    third = store.claim(copilot_engine, run)
    assert third.attempt == 3
    expire(copilot_engine, run)
    assert store.claim(copilot_engine, run) is None
    assert store.inspect(copilot_engine, run)["state"] == "failed"
    await memo.research.bars.close()


@pytest.mark.asyncio
async def test_transport_retry_budget_no_hidden_calls_and_manual_availability(
    copilot_engine, tmp_path
):
    model = FakeMemoModel(httpx.ReadError("reset"))
    memo, run = await ready(copilot_engine, tmp_path, model)
    assert await memo.work(1, run) == 1
    assert store.inspect(copilot_engine, run)["state"] == "retry_wait"
    assert store.claim(copilot_engine, run) is None
    assert memo.research.read(run, "results")[0]["schema"] == "research-results-v1"
    due(copilot_engine, run)
    assert await memo.work(1, run) == 1 and model.calls == 2
    info = store.inspect(copilot_engine, run)
    assert info["state"] == "failed" and info["model_calls"] == 2 and info["attempt_count"] == 2
    await memo.research.bars.close()


@pytest.mark.asyncio
async def test_checkpoint_third_attempt_finishes_without_new_call(copilot_engine, tmp_path):
    memo, run = await ready(copilot_engine, tmp_path)
    first = store.claim(copilot_engine, run)
    store.pin(copilot_engine, first, memo.research.execution)
    store.reserve_call(copilot_engine, first)
    expire(copilot_engine, run)
    second = store.claim(copilot_engine, run)
    store.reserve_call(copilot_engine, second)
    store.checkpoint(copilot_engine, second, valid_draft(), {"model_digest": "fake-digest"})
    expire(copilot_engine, run)
    await memo.work(1, run)
    assert memo.inspect(run)["state"] == "ready" and memo.model.calls == 0
    assert store.inspect(copilot_engine, run)["attempt_count"] == 3
    await memo.research.bars.close()


@pytest.mark.asyncio
async def test_shared_priority_capacity_does_not_consume_and_release_before_preparation(
    copilot_engine, tmp_path, monkeypatch
):
    memo, run = await ready(copilot_engine, tmp_path)
    copilot = CopilotService(memo.research, FakeModel())
    body = request()
    with copilot_engine.connect() as connection:
        version = connection.execute(sa.select(research_store.submissions.c.spec)).scalar_one()
    body["dataset_versions"] = json.loads(version)["dataset_versions"]
    request_id, _, _ = await copilot.create(body, "priority")
    async with admission(copilot_engine) as acquired:
        assert acquired
        task = asyncio.create_task(work(copilot, memo, 1))
        assert await task == 0
    assert store.inspect(copilot_engine, run)["attempt_count"] == 0
    assert copilot.inspect(request_id)["revisions"][0]["attempt_count"] == 0
    observed = []
    original_prepare = memo.research.prepare

    async def prepare(spec):
        async with admission(copilot_engine) as acquired:
            observed.append(acquired)
        return await original_prepare(spec)

    monkeypatch.setattr(memo.research, "prepare", prepare)
    assert await work(copilot, memo, 1) == 1
    assert copilot.inspect(request_id)["outcome"] == "submitted" and observed == [True]
    assert store.inspect(copilot_engine, run)["attempt_count"] == 0
    await memo.research.bars.close()


@pytest.mark.asyncio
async def test_corrupt_supplement_does_not_break_numerical_reads(copilot_engine, tmp_path):
    memo, run = await ready(copilot_engine, tmp_path)
    await memo.work(1, run)
    directory = memo.root / "research" / run / "memo"
    (directory / ("research_memo_" + run + ".md")).write_text("corrupt")
    with pytest.raises(ResearchError, match="integrity"):
        memo.read(run)
    assert memo.research.read(run, "summary")[0]["schema"] == "research-summary-v1"
    assert await memo.work(1, run) == 0
    await memo.research.bars.close()


@pytest.mark.asyncio
async def test_stale_publisher_cannot_register_or_finish(copilot_engine, tmp_path):
    memo, run = await ready(copilot_engine, tmp_path)
    old = store.claim(copilot_engine, run)
    store.pin(copilot_engine, old, memo.research.execution)
    store.checkpoint(copilot_engine, old, valid_draft(), {"model_digest": "fake-digest"})
    info = store.inspect(copilot_engine, run)
    source = facts(memo.research.read(run, "summary")[0])
    staging = memo.stage(old, info, source)
    try:
        expire(copilot_engine, run)
        current = store.claim(copilot_engine, run)
        assert current.token > old.token
        with pytest.raises(ResearchError, match="ownership"):
            memo.publish(old, staging, info)
        with pytest.raises(ResearchError, match="ownership"):
            with copilot_engine.begin() as connection:
                store.finish(connection, old, "a" * 64)
        with copilot_engine.connect() as connection:
            assert (
                connection.execute(
                    sa.select(store.results).where(store.results.c.run_id == run)
                ).first()
                is None
            )
        assert store.inspect(copilot_engine, run)["state"] == "running"
        assert not (memo.root / "research" / run / "memo").exists()
        await memo.execute(current)
        assert memo.inspect(run)["state"] == "ready" and memo.model.calls == 0
    finally:
        import shutil

        shutil.rmtree(staging)
        await memo.research.bars.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("deadline", [False, True])
@pytest.mark.asyncio
async def test_cancellation_deadline_drains_stage_and_fences_publication(
    copilot_engine, tmp_path, monkeypatch, deadline
):
    memo, run = await ready(copilot_engine, tmp_path)
    entered, release = threading.Event(), threading.Event()
    original = memo.stage

    def stage(*args):
        entered.set()
        release.wait(5)
        return original(*args)

    monkeypatch.setattr(memo, "stage", stage)
    if deadline:
        memo.attempt_timeout = 0.2
    task = asyncio.create_task(memo.work(1, run))
    for _ in range(200):
        if entered.is_set():
            break
        await asyncio.sleep(0.01)
    assert entered.is_set()
    if not deadline:
        task.cancel()
    else:
        await asyncio.sleep(0.25)
    await asyncio.sleep(0.05)
    assert not task.done()
    release.set()
    if deadline:
        assert await task == 1
    else:
        with pytest.raises(asyncio.CancelledError):
            await task
    assert store.inspect(copilot_engine, run)["state"] != "ready"
    assert not (memo.root / "research" / run / "memo").exists()
    assert memo.research.read(run, "results")[0]["schema"] == "research-results-v1"
    async with admission(copilot_engine) as acquired:
        assert acquired
    await memo.research.bars.close()


@pytest.mark.asyncio
async def test_active_memo_is_not_preempted_and_workers_do_not_overlap(copilot_engine, tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()

    class PausedModel(FakeMemoModel):
        async def generate(self, source, pinned):
            entered.set()
            await release.wait()
            return await super().generate(source, pinned)

    memo, run = await ready(copilot_engine, tmp_path, PausedModel())
    first = asyncio.create_task(memo.work(1, run))
    await asyncio.wait_for(entered.wait(), 5)
    copilot = CopilotService(memo.research, FakeModel())
    identity, _, _ = copilot_store.create(copilot_engine, turn(request()), "late-priority")
    assert await work(copilot, memo, 1) == 0
    assert copilot.inspect(identity)["state"] == "queued" and not first.done()
    assert copilot.model.calls == 0
    release.set()
    assert await first == 1 and memo.inspect(run)["state"] == "ready"
    assert await work(copilot, memo, 1) == 1 and copilot.model.calls == 1
    await memo.research.bars.close()


@pytest.mark.parametrize("phase", ["before", "renamed", "committed"])
async def test_real_process_termination_and_orphan_recovery(copilot_engine, tmp_path, phase):
    memo, run = await ready(copilot_engine, tmp_path)
    schema = copilot_engine.get_execution_options()["schema_translate_map"][None]
    marker = tmp_path / "killed-phase"
    code = """
import asyncio, json, time
from pathlib import Path
import sqlalchemy as sa
from marketlab.config import Settings
from marketlab.analytics.bars import BarService
from marketlab.research.service import ResearchService
from marketlab.memos.service import MemoService
from marketlab.memos.model import MemoModel
from marketlab.memos import store
settings=Settings()
engine=sa.create_engine(settings.sqlalchemy_url).execution_options(schema_translate_map={None:SCHEMA})
bars=BarService(engine,Path(ROOT))
service=MemoService(ResearchService(bars),MemoModel('http://unused','unused'))
current=store.claim(engine,RUN)
store.pin(engine,current,service.research.execution)
value={'schema':'memo-draft-v1','paragraphs': [
 {'claim':c,'wording':'standard'} for c in ['scope','findings','limitations']]}
store.checkpoint(engine,current,value,{'model_digest':'fake-digest'})
def stop():
 Path(MARKER).write_text(PHASE)
 while True: time.sleep(1)
original=service.publish
def publication(*args):
 if PHASE=='before': stop()
 original(*args)
 if PHASE=='committed': stop()
service.publish=publication
if PHASE=='renamed':
 @sa.event.listens_for(engine,'before_cursor_execute')
 def intercept(connection,cursor,statement,parameters,context,executemany):
  if statement.startswith('INSERT INTO') and 'memo_results' in statement: stop()
asyncio.run(service.execute(current))
"""
    prefix = "\n".join(
        name + "=" + repr(value)
        for name, value in {
            "SCHEMA": schema,
            "ROOT": str(memo.root),
            "RUN": run,
            "MARKER": str(marker),
            "PHASE": phase,
        }.items()
    )
    process = await asyncio.to_thread(
        subprocess.Popen,
        [sys.executable, "-c", prefix + "\n" + code],
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        for _ in range(500):
            if marker.exists() or process.poll() is not None:
                break
            await asyncio.sleep(0.02)
        assert marker.exists(), process.communicate(timeout=5)
        process.terminate()
        process.communicate(timeout=10)
        if phase != "committed":
            assert store.inspect(copilot_engine, run)["state"] == "running"
            expire(copilot_engine, run)
            assert await memo.work(1, run) == 1
        else:
            assert await memo.work(1, run) == 0
        assert memo.read(run)[0].startswith("AI-generated") and memo.model.calls == 0
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=10)
        await memo.research.bars.close()
