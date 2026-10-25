"""Real PostgreSQL research durability, visibility, integrity and compatibility."""

import asyncio
import hashlib
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
import sqlalchemy as sa
from test_bars import FakeRedis
from test_datasets import START as MICROS
from test_datasets import archive_files
from test_research import body

from marketlab.analytics.bars import BarService
from marketlab.analytics.cache import canonical
from marketlab.app import create_app
from marketlab.datasets import ingest_archive
from marketlab.datasets.publication import dataset_versions
from marketlab.research import store
from marketlab.research.service import ResearchService
from marketlab.research.spec import ResearchError, ResearchSpec

pytestmark = pytest.mark.integration


@pytest.fixture
def research_engine(dataset_engine):
    schema = dataset_engine.get_execution_options()["schema_translate_map"][None]
    with dataset_engine.begin() as connection:
        for name in (
            "research_submissions",
            "research_runs",
            "research_attempts",
            "research_results",
        ):
            connection.execute(
                sa.text(f'CREATE TABLE "{schema}".{name} (LIKE public.{name} INCLUDING ALL)')
            )
    return dataset_engine


def published(engine, tmp_path):
    rows = [f"{i + 1},{100 + i},1,{100 + i},{MICROS + i * 300000000},True,False" for i in range(20)]
    archive, checksum = archive_files(tmp_path / "source", rows)
    root = tmp_path / "storage"
    version = ingest_archive(engine, root, archive, checksum)["dataset_version_id"]
    spec = body()
    spec["dataset_versions"] = [version]
    bars = BarService(engine, root)
    bars.cache.client = FakeRedis()
    return ResearchService(bars), ResearchSpec.create(spec)


@pytest.mark.asyncio
async def test_submit_execute_repeat_and_immutable_read(research_engine, tmp_path):
    service, spec = published(research_engine, tmp_path)
    with research_engine.connect() as connection:
        retained = connection.execute(sa.select(dataset_versions)).mappings().all()
    run, replay = await service.submit(spec, "one")
    assert not replay and await service.submit(spec, "one") == (run, True)
    with pytest.raises(ResearchError, match="ready"):
        service.read(run, "results")
    assert await service.work(1, run) == 1
    info = service.inspect(run)
    assert info["state"] == "succeeded" and len(info["attempts"]) == 1
    result, digest = service.read(run, "results")
    assert hashlib.sha256(canonical(result)).hexdigest() == digest
    summary, first = await service.summary(run)
    assert (await service.summary(run)) == (summary, "HIT") and first == "MISS"
    other, _ = await service.submit(spec, "two")
    await service.work(1, other)
    assert service.read(other, "results") == (result, digest)
    with research_engine.connect() as connection:
        assert connection.execute(sa.select(dataset_versions)).mappings().all() == retained
    await service.bars.close()


@pytest.mark.asyncio
async def test_idempotency_conflict_and_concurrent_claim(research_engine, tmp_path):
    service, spec = published(research_engine, tmp_path)
    run, _ = await service.submit(spec, "one")
    altered = spec.body()
    altered["end"] = "2025-01-01T01:35:00Z"
    with pytest.raises(ResearchError, match="conflict"):
        await service.submit(ResearchSpec.create(altered), "one")
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: store.claim(research_engine, run), range(2)))
    assert sum(r is not None for r in results) == 1
    await service.bars.close()


@pytest.mark.asyncio
async def test_queued_claim_survives_backward_database_time_but_retry_backoff_holds(
    research_engine, tmp_path
):
    service, spec = published(research_engine, tmp_path)
    run, _ = await service.submit(spec, "one")
    # A future submission timestamp is what a backward database clock step looks like.
    with research_engine.begin() as connection:
        connection.execute(
            store.runs.update()
            .where(store.runs.c.run_id == run)
            .values(eligible_at=sa.func.clock_timestamp() + timedelta(hours=1))
        )
    current = store.claim(research_engine, run)
    assert current is not None and current.attempt == current.token == 1
    store.fail(research_engine, current, transient=True)
    assert service.inspect(run)["state"] == "retry_wait"
    assert store.claim(research_engine, run) is None
    await service.bars.close()


@pytest.mark.asyncio
async def test_three_expired_attempts_no_fourth_and_stale_fencing(research_engine, tmp_path):
    service, spec = published(research_engine, tmp_path)
    run, _ = await service.submit(spec, "one")
    first = store.claim(research_engine, run)
    for attempt in range(1, 4):
        current = first if attempt == 1 else store.claim(research_engine, run)
        assert current.attempt == attempt
        with research_engine.begin() as connection:
            connection.execute(
                store.runs.update()
                .where(store.runs.c.run_id == run)
                .values(lease_until=sa.func.clock_timestamp() - timedelta(seconds=1))
            )
        assert not store.heartbeat(research_engine, current)
    assert store.claim(research_engine, run) is None
    assert service.inspect(run)["state"] == "failed"
    with pytest.raises(ResearchError, match="ownership"):
        store.fail(research_engine, first)
    await service.bars.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["manifest", "results", "summary", "registration"])
async def test_integrity_before_cached_summary(research_engine, tmp_path, target):
    service, spec = published(research_engine, tmp_path)
    run, _ = await service.submit(spec, "one")
    await service.work(1, run)
    await service.summary(run)
    if target == "registration":
        with research_engine.begin() as connection:
            connection.execute(
                store.results.update()
                .where(store.results.c.run_id == run)
                .values(summary_sha256="0" * 64)
            )
    else:
        path = service.root / "research" / run / (target + ".json")
        path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ResearchError, match="integrity"):
        await service.summary(run)
    await service.bars.close()


@pytest.mark.asyncio
async def test_manual_http_roundtrip_without_ollama(research_engine, tmp_path):
    service, spec = published(research_engine, tmp_path)
    app = create_app()
    app.state.research_service = service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/research/runs", json=spec.body(), headers={"Idempotency-Key": "one"}
        )
        assert response.status_code == 201
        run = response.json()["run_id"]
        assert (await client.get(f"/v1/research/runs/{run}/results")).status_code == 409
        await service.work(1, run)
        assert (await client.get(f"/v1/research/runs/{run}")).json()["state"] == "succeeded"
        assert (await client.get(f"/v1/research/runs/{run}/results")).status_code == 200
        assert (await client.get(f"/v1/research/runs/{run}/summary")).headers["X-Cache"] == "MISS"
        assert (await client.get(f"/v1/research/runs/{run}/summary")).headers["X-Cache"] == "HIT"
    await service.bars.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["success", "failure"])
async def test_lease_expiry_between_fence_and_update_rolls_back(
    research_engine, tmp_path, monkeypatch, operation
):
    service, spec = published(research_engine, tmp_path)
    run, _ = await service.submit(spec, "one")
    current = store.claim(research_engine, run)
    original = store.fence

    def expire(connection, claim):
        original(connection, claim)
        connection.execute(
            store.runs.update()
            .where(store.runs.c.run_id == run)
            .values(lease_until=sa.func.clock_timestamp() - timedelta(seconds=1))
        )

    monkeypatch.setattr(store, "fence", expire)
    with pytest.raises(ResearchError, match="ownership"):
        if operation == "failure":
            store.fail(research_engine, current)
        else:
            with research_engine.begin() as connection:
                connection.execute(
                    store.results.insert().values(
                        run_id=run,
                        manifest_sha256="a" * 64,
                        manifest_path="unused",
                        results_sha256="a" * 64,
                        summary_sha256="a" * 64,
                        registered_at=sa.func.clock_timestamp(),
                    )
                )
                store.finish(connection, current)
    info = service.inspect(run)
    assert info["state"] == "running" and info["attempts"][0]["outcome"] == "running"
    with research_engine.connect() as connection:
        assert (
            connection.execute(
                sa.select(store.results).where(store.results.c.run_id == run)
            ).first()
            is None
        )
    await service.bars.close()


@pytest.mark.asyncio
async def test_timeout_drains_actual_calculation_and_never_publishes(
    research_engine, tmp_path, monkeypatch
):
    import threading

    import marketlab.research.service as module

    service, spec = published(research_engine, tmp_path)
    run, _ = await service.submit(spec, "one")
    drained = threading.Event()

    def cooperative(spec, inputs, cancelled):
        try:
            while not cancelled.wait(0.001):
                pass
            raise ResearchError("cancelled", 503)
        finally:
            drained.set()

    monkeypatch.setattr(module, "calculate", cooperative)
    service.attempt_timeout = 0.2
    await service.work(1, run)
    assert drained.is_set()
    assert service.inspect(run)["state"] != "succeeded"
    assert not (service.root / "research" / run).exists()
    await service.bars.close()


def crash_child(schema, root, run, phase, marker):
    """Real worker process with test-only phase instrumentation."""
    from marketlab.config import Settings

    engine = sa.create_engine(Settings().sqlalchemy_url).execution_options(
        schema_translate_map={None: schema}
    )
    bars = BarService(engine, Path(root))
    service = ResearchService(bars)
    original_fail = store.fail

    def report_failure(*args):
        import traceback

        traceback.print_exc()
        return original_fail(*args)

    store.fail = report_failure

    def stop():
        Path(marker).write_text(phase)
        while True:
            time.sleep(0.01)

    if phase == "before_stage":
        service.stage = lambda *args: stop()
    elif phase == "during_stage":

        def partial(*args):
            directory = service.root / ".staging" / ("research-crash-" + run)
            directory.mkdir(parents=True)
            (directory / "results.json").write_bytes(b"{partial")
            stop()

        service.stage = partial
    elif phase == "after_rename":

        @sa.event.listens_for(engine, "before_cursor_execute")
        def before(connection, cursor, statement, parameters, context, executemany):
            if statement.startswith("INSERT INTO") and "research_results" in statement:
                stop()
    else:
        original = service.publish

        def committed(*args):
            original(*args)
            stop()

        service.publish = committed
    asyncio.run(service.work(1, run))


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["before_stage", "during_stage", "after_rename", "after_commit"])
async def test_real_process_crash_recovery(research_engine, tmp_path, phase):
    service, spec = published(research_engine, tmp_path)
    run, _ = await service.submit(spec, "one")
    schema = research_engine.get_execution_options()["schema_translate_map"][None]
    marker = tmp_path / "phase.txt"
    process = await asyncio.to_thread(
        subprocess.Popen,
        [
            sys.executable,
            "-c",
            "import sys;sys.path.insert(0,'tests');"
            "from test_research_integration import crash_child;crash_child(*sys.argv[1:])",
            schema,
            str(service.root),
            run,
            phase,
            str(marker),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:

        def wait_marker():
            deadline = time.monotonic() + 30
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)

        await asyncio.to_thread(wait_marker)
        assert marker.exists(), (
            process.communicate(timeout=2)[1].decode()
            if process.poll() is not None
            else "phase deadline"
        )
        process.kill()
        process.wait(timeout=5)
        if phase == "after_commit":
            assert service.inspect(run)["state"] == "succeeded"
            assert await service.work(1, run) == 0
        else:
            assert service.inspect(run)["state"] == "running"
            with pytest.raises(ResearchError, match="ready"):
                service.read(run, "results")
            with research_engine.begin() as connection:
                connection.execute(
                    store.runs.update()
                    .where(store.runs.c.run_id == run)
                    .values(lease_until=sa.func.clock_timestamp() - timedelta(seconds=1))
                )
            assert await service.work(1, run) == 1
            assert service.inspect(run)["state"] == "succeeded"
            assert service.inspect(run)["attempt_count"] == 2
        service.read(run, "results")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if process.stderr:
            process.stderr.close()
        await service.bars.close()


@pytest.mark.asyncio
async def test_worker_fingerprint_mismatch_is_terminal(research_engine, tmp_path):
    service, spec = published(research_engine, tmp_path)
    run, _ = await service.submit(spec, "one")
    service._execution = {"different": "source"}
    await service.work(1, run)
    assert service.inspect(run)["state"] == "failed"
    assert service.inspect(run)["attempts"][0]["outcome"] == "permanent"
    assert not (service.root / "research" / run).exists()
    await service.bars.close()


@pytest.mark.asyncio
async def test_identical_summary_coalescing_and_waiter_cancellation(
    research_engine, tmp_path, monkeypatch
):
    service, spec = published(research_engine, tmp_path)
    run, _ = await service.submit(spec, "one")
    await service.work(1, run)
    original = service.read
    calls = []

    def slow(*args):
        calls.append(1)
        time.sleep(0.1)
        return original(*args)

    monkeypatch.setattr(service, "read", slow)
    first = asyncio.create_task(service.summary(run))
    second = asyncio.create_task(service.summary(run))
    await asyncio.sleep(0.01)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert (await second)[1] == "MISS"
    assert len(calls) == 1
    assert (await service.summary(run))[1] == "HIT"
    await service.bars.close()


@pytest.mark.asyncio
async def test_concurrent_http_submission_has_one_created_one_replayed(research_engine, tmp_path):
    service, spec = published(research_engine, tmp_path)
    app = create_app()
    app.state.research_service = service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:

        async def submit_same():
            return await client.post(
                "/v1/research/runs", json=spec.body(), headers={"Idempotency-Key": "racing-key"}
            )

        responses = await asyncio.gather(submit_same(), submit_same())
    assert sorted(r.status_code for r in responses) == [200, 201]
    assert len({r.json()["run_id"] for r in responses}) == 1
    assert sorted(r.json()["replayed"] for r in responses) == [False, True]
    with research_engine.connect() as connection:
        assert connection.scalar(sa.select(sa.func.count()).select_from(store.runs)) == 1
    await service.bars.close()
