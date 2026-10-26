"""Real bounded spawned verification, cancellation, coalescing and shared SQL budget."""

import asyncio
import concurrent.futures.process as stdlib
import ctypes
import multiprocessing
import multiprocessing.connection as connection
import os
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from multiprocessing.connection import wait

import pytest
import sqlalchemy as sa
from test_bars import FakeRedis, expensive_native
from test_datasets import archive_files, normalize
from verifier_helpers import crash_gate_verify, gate_verify

import marketlab.analytics.verification as module
from marketlab.analytics.bars import BarError, BarService, BarsRequest
from marketlab.analytics.verification import (
    ComputeBudget,
    VerificationPool,
    VerificationRequest,
    VerificationUnavailable,
)
from marketlab.datasets.normalize import VerificationCancelled
from marketlab.datasets.publication import _json, _version, dataset_versions
from marketlab.datasets.source import VENUE, file_hash

DAY = date(2025, 1, 1)
START = datetime(2025, 1, 1, tzinfo=UTC)


def fixtures(root, count=1):
    requests, manifests = [], []
    for index in range(count):
        archive, _ = archive_files(
            root / ("source-" + str(index)),
            [f"{index},100,1,100,1735689600000000,True,False"],
        )
        directory = root / ("version-" + str(index))
        quality = normalize(archive, directory)
        source = file_hash(archive)
        lock = "b" * 64
        version = _version(source, "BTCUSDT", DAY, lock)
        manifest = {
            "dataset_version_id": version,
            "venue": VENUE,
            "symbol": "BTCUSDT",
            "trade_date": DAY.isoformat(),
            "schema_version": 1,
            "transform_version": "binance-spot-trades-v1",
            "source": {"expected_sha256": source, "actual_sha256": source},
            "build": {"git_dirty": False, "git_revision": "a" * 40, "lock_sha256": lock},
            "requested_from": "2025-01-01T00:00:00Z",
            "requested_before": "2025-01-02T00:00:00Z",
            "quality": quality,
            "artifact": {
                "path": "trades.parquet",
                "sha256": quality["parquet_sha256"],
                "bytes": quality["parquet_bytes"],
            },
        }
        path = directory / "manifest.json"
        path.write_bytes(_json(manifest))
        requests.append(
            VerificationRequest(
                str(root),
                str(path.relative_to(root)),
                version,
                file_hash(path),
                (version,),
                (path.stat().st_size,),
            )
        )
        manifests.append(manifest)
    return requests, manifests


def wait_for(predicate, seconds=10):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("bounded spawn-test checkpoint not reached")


def entered(root, request):
    return list((root / "control").glob(request.version + ".entered-*"))


def touch(root, request, action):
    path = root / "control"
    path.mkdir(exist_ok=True)
    (path / (request.version + "." + action)).write_text(action)


@contextmanager
def gate_callers(pool, root, requests, workers=2):
    callers = ThreadPoolExecutor(workers)
    try:
        yield callers
    finally:
        # Release actual child work before joining callers, including assertion failures.
        for request in requests:
            touch(root, request, "drain")
            touch(root, request, "release")
        try:
            pool.close()
        finally:
            callers.shutdown(wait=True, cancel_futures=True)


def alive(pid):
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = ctypes.c_uint32()
        try:
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code)) and code.value == 259)
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def test_lazy_real_spawn_verifies_hashes_bounds_submissions_and_reaps(tmp_path):
    requests, manifests = fixtures(tmp_path, 5)
    pool = VerificationPool(ComputeBudget())
    assert pool.snapshot()["worker_pids"] == [] and pool.executor is None
    try:
        result = pool.verify_many(requests, threading.Event())
        assert result == {r.version: m for r, m in zip(requests, manifests, strict=True)}
        state = pool.snapshot()
        assert state["submitted"] == state["completed"] == 5
        assert state["peak_submitted"] == state["compute"]["peak"] == 2
        assert 1 <= len(state["worker_pids"]) <= 2 and state["compute"]["active"] == 0
        assert {r["logical_sha256"] for r in state["completed_records"]} == {
            m["quality"]["logical_sha256"] for m in manifests
        }
        assert all(
            r["arrow_cpu_threads"] == r["arrow_io_threads"] == 1 for r in state["completed_records"]
        )
    finally:
        pool.close()
    assert pool.snapshot()["closed"] and not any(
        alive(pid) for pid in pool.snapshot()["worker_pids"]
    )


def test_last_cancel_drains_and_new_arrival_waits_for_clean_flight(tmp_path, monkeypatch):
    requests, _ = fixtures(tmp_path)
    request = requests[0]
    monkeypatch.setattr(module, "_verify_file", gate_verify)
    pool = VerificationPool(ComputeBudget())
    cancel = threading.Event()
    with gate_callers(pool, tmp_path, requests) as callers:
        first = callers.submit(pool.verify_many, requests, cancel)
        wait_for(lambda: entered(tmp_path, request))
        cancel.set()
        wait_for(lambda: (tmp_path / "control" / (request.version + ".cancelled")).exists())
        assert not first.done() and pool.snapshot()["compute"]["active"] == 1
        second = callers.submit(pool.verify_many, requests, threading.Event())
        time.sleep(0.05)
        assert not second.done() and pool.snapshot()["submitted"] == 1
        touch(tmp_path, request, "drain")
        with pytest.raises(VerificationCancelled):
            first.result(timeout=5)
        touch(tmp_path, request, "release")
        assert request.version in second.result(timeout=10)
    state = pool.snapshot()
    assert state["submitted"] == 2 and state["completed"] == 1 and state["cancelled"] == 1
    assert state["compute"]["active"] == 0


def test_one_cancelled_waiter_does_not_cancel_shared_survivor(tmp_path, monkeypatch):
    requests, _ = fixtures(tmp_path)
    request = requests[0]
    monkeypatch.setattr(module, "_verify_file", gate_verify)
    pool = VerificationPool(ComputeBudget())
    cancel = threading.Event()
    try:
        with gate_callers(pool, tmp_path, requests) as callers:
            first = callers.submit(pool.verify_many, requests, cancel)
            wait_for(lambda: entered(tmp_path, request))
            second = callers.submit(pool.verify_many, requests, threading.Event())
            wait_for(lambda: pool.snapshot()["coalesced"] == 1)
            cancel.set()
            with pytest.raises(VerificationCancelled):
                first.result(timeout=3)
            assert not second.done() and pool.snapshot()["submitted"] == 1
            assert not (tmp_path / "control" / (request.version + ".cancelled")).exists()
            touch(tmp_path, request, "release")
            assert request.version in second.result(timeout=5)
    finally:
        pool.close()


def force_old_spawn_order(monkeypatch):
    """Test-only ordering of public submissions, never a production workaround."""
    paused, watched = threading.Event(), threading.Event()
    state = {}
    original_adjust = stdlib.ProcessPoolExecutor._adjust_process_count
    original_wait = connection.wait

    def adjust(executor):
        before = set(executor._processes)
        if len(before) == 1:
            paused.set()
            assert watched.wait(5), "manager did not enter old one-worker wait"
        result = original_adjust(executor)
        if len(before) == 1:
            created = set(executor._processes) - before
            assert len(created) == 1
            state["second_pid"] = created.pop()
        return result

    def observe(objects, timeout=None):
        caller = sys._getframe(1)
        if caller.f_code.co_name == "wait_result_broken_or_wakeup" and paused.is_set():
            manager = caller.f_locals["self"]
            if len(manager.processes) == 1:
                state["old_sentinels"] = list(caller.f_locals["worker_sentinels"])
                watched.set()  # Snapshot exists before the second spawn is allowed.
        return original_wait(objects, timeout)

    monkeypatch.setattr(stdlib.ProcessPoolExecutor, "_adjust_process_count", adjust)
    monkeypatch.setattr(connection, "wait", observe)
    return state


@pytest.mark.parametrize("forced_spawn_order", [False, True])
def test_killed_worker_fails_closed_for_sql_until_recreation(
    tmp_path, monkeypatch, forced_spawn_order
):
    requests, _ = fixtures(tmp_path, 2)
    ordering = force_old_spawn_order(monkeypatch) if forced_spawn_order else {}
    monkeypatch.setattr(module, "_verify_file", crash_gate_verify)
    compute = ComputeBudget()
    pool = VerificationPool(compute)
    try:
        with gate_callers(pool, tmp_path, requests, workers=1) as callers:
            running = callers.submit(pool.verify_many, requests, threading.Event())
            wait_for(lambda: all(entered(tmp_path, request) for request in requests))
            pids = [
                int(entered(tmp_path, request)[0].name.rsplit("-", 1)[1]) for request in requests
            ]
            assert len(set(pids)) == 2 and all(alive(pid) for pid in pids)
            pid = ordering["second_pid"] if forced_spawn_order else pids[0]
            assert pid in pids
            if forced_spawn_order:
                assert len(ordering["old_sentinels"]) == 1
            touch(tmp_path, requests[pids.index(pid)], "crash-target")
            with pool.condition:
                assert len(pool.flights) == 2
                assert all(not flight.future.done() for flight in pool.flights.values())
            (tmp_path / "control" / "crash-arm").write_text("both workers ready")
            wait_for(
                lambda: all(
                    list((tmp_path / "control").glob(request.version + ".armed-*"))
                    for request in requests
                )
            )
            with pool.condition:
                assert all(not flight.future.done() for flight in pool.flights.values())
            assert alive(pid) and not running.done()
            owned = {child.pid: child for child in multiprocessing.active_children()}
            assert pid in owned
            exited = owned[pid].sentinel
            # Windows SIGTERM forces TerminateProcess; POSIX SIGTERM is graceful
            # and may be inherited as blocked/ignored, so use actual crash semantics.
            crash = signal.SIGTERM if os.name == "nt" else signal.SIGKILL
            killed_at = time.monotonic()
            os.kill(pid, crash)  # Exactly this known owned worker, never PID wildcard.
            # A POSIX zombie has exited but kill(pid, 0) still succeeds until the
            # executor reaps it. Observe exit now; assert actual reaping after close.
            assert wait([exited], timeout=5) == [exited]
            with pytest.raises(VerificationUnavailable):
                running.result(timeout=10)
            assert time.monotonic() - killed_at < 5
            assert pool.snapshot()["broken"] and compute.snapshot()["failed"]
            with pytest.raises(VerificationUnavailable):
                with compute.query(threading.Event(), 0.05):
                    pytest.fail("SQL reused a broken child's permit")
    finally:
        pool.close()
    assert not any(alive(pid) for pid in pool.snapshot()["worker_pids"])
    monkeypatch.undo()
    replacement = VerificationPool(ComputeBudget())
    try:
        assert requests[0].version in replacement.verify_many(requests[:1], threading.Event())
    finally:
        replacement.close()


def test_crash_gate_budget_starts_after_delayed_second_worker_readiness(tmp_path, monkeypatch):
    requests, _ = fixtures(tmp_path, 2)
    touch(tmp_path, requests[0], "crash-target")
    touch(tmp_path, requests[1], "delay-entry")
    (tmp_path / "control" / "crash-gate-seconds").write_text("0.05")
    monkeypatch.setattr(module, "_verify_file", crash_gate_verify)
    pool = VerificationPool(ComputeBudget())
    cancelled = threading.Event()
    try:
        with gate_callers(pool, tmp_path, requests, workers=1) as callers:
            running = callers.submit(pool.verify_many, requests, cancelled)
            wait_for(
                lambda: (
                    entered(tmp_path, requests[0])
                    and list((tmp_path / "control").glob(requests[1].version + ".starting-*"))
                )
            )
            time.sleep(0.15)  # Deliberate startup delay beyond the 50 ms active budget.
            assert not entered(tmp_path, requests[1]) and not running.done()
            assert not list((tmp_path / "control").glob("*.expired-*"))
            with pool.condition:
                assert all(not flight.future.done() for flight in pool.flights.values())
            touch(tmp_path, requests[1], "allow-entry")
            wait_for(lambda: all(entered(tmp_path, request) for request in requests))
            pids = [
                int(entered(tmp_path, request)[0].name.rsplit("-", 1)[1]) for request in requests
            ]
            assert len(set(pids)) == 2 and all(alive(pid) for pid in pids)
            assert not list((tmp_path / "control").glob("*.armed-*"))
            cancelled.set()
            with pytest.raises(VerificationCancelled):
                running.result(timeout=5)
            assert pool.snapshot()["compute"]["active"] == 0
    finally:
        touch(tmp_path, requests[1], "allow-entry")
        pool.close()
    assert not any(alive(pid) for pid in pool.snapshot()["worker_pids"])


def catalog_reader(root, requests, manifests):
    engine = sa.create_engine("sqlite:///" + str(root / "catalog.sqlite"))
    dataset_versions.create(engine)
    with engine.begin() as connection:
        for request, manifest in zip(requests, manifests, strict=True):
            connection.execute(
                dataset_versions.insert().values(
                    dataset_version_id=request.version,
                    source_sha256=manifest["source"]["actual_sha256"],
                    manifest_sha256=request.manifest_hash,
                    manifest_path=request.relative,
                    venue=VENUE,
                    symbol="BTCUSDT",
                    trade_date=DAY,
                    row_count=manifest["quality"]["accepted_rows"],
                    status="published",
                    published_at=START,
                )
            )
    return engine


def bars_request(version):
    return BarsRequest.create(
        versions=[version],
        symbol="BTCUSDT",
        interval="1m",
        start=START,
        end=START + timedelta(minutes=5),
    )


def test_actual_native_sql_and_spawned_verifiers_share_two_permits(tmp_path, monkeypatch):
    requests, _ = fixtures(tmp_path, 3)
    monkeypatch.setattr(module, "_verify_file", gate_verify)
    directories, closed, sql_started = expensive_native(monkeypatch)
    engine = sa.create_engine("sqlite://")
    service = BarService(engine, tmp_path, query_timeout=0.5, admission_timeout=0.05)
    pool = service.reader.verifier
    try:
        with gate_callers(pool, tmp_path, requests, workers=3) as callers:
            first = callers.submit(pool.verify_many, requests[:2], threading.Event())
            wait_for(lambda: all(entered(tmp_path, request) for request in requests[:2]))
            with pytest.raises(BarError, match="capacity"):
                service._query(bars_request(requests[0].version), [], [], threading.Event())
            assert not sql_started.is_set()
            touch(tmp_path, requests[0], "release")
            wait_for(lambda: pool.snapshot()["completed"] == 1)
            sql = callers.submit(
                service._query, bars_request(requests[0].version), [], [], threading.Event()
            )
            assert sql_started.wait(3)
            assert pool.snapshot()["compute"]["active_by_kind"] == {
                "verification": 1,
                "query": 1,
            }
            third = callers.submit(pool.verify_many, requests[2:], threading.Event())
            time.sleep(0.05)
            assert pool.snapshot()["submitted"] == 2 and not entered(tmp_path, requests[2])
            with pytest.raises(BarError, match="timed out"):
                sql.result(timeout=3)
            wait_for(lambda: entered(tmp_path, requests[2]))
            for request in requests[1:]:
                touch(tmp_path, request, "release")
            assert len(first.result(timeout=5)) == 2 and len(third.result(timeout=5)) == 1
            assert pool.snapshot()["compute"]["peak"] == 2
            assert pool.snapshot()["compute"]["active"] == 0
        assert closed == [True] and directories and all(not path.exists() for path in directories)
    finally:
        pool.close()
        engine.dispose()


@pytest.mark.parametrize("mutation", ["catalog", "manifest", "parquet"])
@pytest.mark.asyncio
async def test_parent_rechecks_catalog_and_files_after_actual_child(
    tmp_path, monkeypatch, mutation
):
    requests, manifests = fixtures(tmp_path)
    engine = catalog_reader(tmp_path, requests, manifests)
    service = BarService(engine, tmp_path)
    service.cache.client = FakeRedis()
    original = service.reader.verifier.verify_many

    def verify_then_mutate(pending, cancelled):
        result = original(pending, cancelled)
        if mutation == "catalog":
            with engine.begin() as connection:
                connection.execute(dataset_versions.update().values(row_count=999))
        else:
            path = tmp_path / requests[0].relative
            if mutation == "parquet":
                path = path.parent / "trades.parquet"
            with path.open("ab") as stream:
                stream.write(b"changed after child verification")
        return result

    monkeypatch.setattr(service.reader.verifier, "verify_many", verify_then_mutate)
    try:
        with pytest.raises(BarError, match="changed during verification"):
            await service.read(bars_request(requests[0].version))
        assert service.reader.verifier.snapshot()["completed"] == 1
        assert not service.reader.verified and service.capacity._value == 2
    finally:
        await service.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_outer_deadline_drains_spawned_work_before_capacity_and_cache(tmp_path, monkeypatch):
    requests, manifests = fixtures(tmp_path)
    request = requests[0]
    engine = catalog_reader(tmp_path, requests, manifests)
    monkeypatch.setattr(module, "_verify_file", gate_verify)
    service = BarService(engine, tmp_path)
    service.cache.client = FakeRedis()
    deadline = asyncio.Event()

    async def bounded_read():
        # Establish actual child entry first, then expire a real asyncio deadline.
        async with asyncio.timeout(None) as timeout:
            reading = asyncio.create_task(service.read(bars_request(request.version)))
            await asyncio.to_thread(wait_for, lambda: entered(tmp_path, request))
            deadline.set()
            timeout.reschedule(asyncio.get_running_loop().time() + 0.01)
            await reading

    task = asyncio.create_task(bounded_read())
    try:
        await asyncio.wait_for(deadline.wait(), 10)
        await asyncio.to_thread(
            wait_for, lambda: (tmp_path / "control" / (request.version + ".cancelled")).exists()
        )
        assert not task.done() and service.capacity._value == 1
        assert service.reader.verifier.snapshot()["compute"]["active"] == 1
        touch(tmp_path, request, "drain")
        with pytest.raises(TimeoutError):
            await task
        assert not service.reader.verified and service.capacity._value == 2
        assert service.reader.verifier.snapshot()["compute"]["active"] == 0
    finally:
        touch(tmp_path, request, "drain")
        touch(tmp_path, request, "release")
        await service.close()
        await asyncio.gather(task, return_exceptions=True)
        engine.dispose()


@pytest.mark.asyncio
async def test_successful_child_cancel_race_installs_no_cache_and_releases_after_drain(
    tmp_path, monkeypatch
):
    requests, manifests = fixtures(tmp_path)
    engine = catalog_reader(tmp_path, requests, manifests)
    service = BarService(engine, tmp_path)
    service.cache.client = FakeRedis()
    entered_post, release = threading.Event(), threading.Event()
    original = service.reader.signature
    calls = 0

    def signature(paths):
        nonlocal calls
        value = original(paths)
        calls += 1
        if calls == 2:
            entered_post.set()
            release.wait(5)
        return value

    monkeypatch.setattr(service.reader, "signature", signature)
    request = BarsRequest.create(
        versions=[requests[0].version],
        symbol="BTCUSDT",
        interval="1m",
        start=START,
        end=START + timedelta(minutes=5),
    )
    task = asyncio.create_task(service.read(request))
    try:
        assert await asyncio.to_thread(entered_post.wait, 10)
        assert service.reader.verifier.snapshot()["completed"] == 1
        task.cancel()
        await asyncio.sleep(0.05)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not service.reader.verified and service.capacity._value == 2
    finally:
        release.set()
        await service.close()
        await asyncio.gather(task, return_exceptions=True)
        engine.dispose()


@pytest.mark.asyncio
async def test_close_cancellation_drains_active_child_and_closes_cache(tmp_path, monkeypatch):
    requests, manifests = fixtures(tmp_path)
    request = requests[0]
    engine = catalog_reader(tmp_path, requests, manifests)
    monkeypatch.setattr(module, "_verify_file", gate_verify)
    service = BarService(engine, tmp_path)
    fake = FakeRedis()
    closed = []

    async def close_cache():
        closed.append(True)

    fake.aclose = close_cache
    service.cache.client = fake
    query = BarsRequest.create(
        versions=[request.version],
        symbol="BTCUSDT",
        interval="1m",
        start=START,
        end=START + timedelta(minutes=5),
    )
    reading = asyncio.create_task(service.read(query))
    closing = None
    try:
        await asyncio.to_thread(wait_for, lambda: entered(tmp_path, request))
        closing = asyncio.create_task(service.close())
        await asyncio.to_thread(
            wait_for, lambda: (tmp_path / "control" / (request.version + ".cancelled")).exists()
        )
        closing.cancel()
        await asyncio.sleep(0.02)
        closing.cancel()
        await asyncio.sleep(0.02)
        assert not closing.done() and not closed
        touch(tmp_path, request, "drain")
        with pytest.raises(asyncio.CancelledError):
            await closing
        await asyncio.gather(reading, return_exceptions=True)
        snapshot = service.reader.verifier.snapshot()
        assert snapshot["closed"] and snapshot["compute"]["active"] == 0 and closed == [True]
        assert not any(alive(pid) for pid in snapshot["worker_pids"])
        assert not service.reader.verified
    finally:
        touch(tmp_path, request, "drain")
        touch(tmp_path, request, "release")
        await service.close()
        await asyncio.gather(reading, *([closing] if closing else []), return_exceptions=True)
        engine.dispose()
