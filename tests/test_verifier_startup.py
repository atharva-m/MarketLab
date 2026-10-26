"""Bounded public-API readiness precedes file work and drains on every exit."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import partial
from types import SimpleNamespace

import pytest
from test_verifier_pool import alive, fixtures, wait_for
from verifier_startup_helpers import draining_ready, failing_ready, gated_ready

import marketlab.analytics.verification as module
from marketlab.analytics.verification import (
    ComputeBudget,
    VerificationPool,
    VerificationUnavailable,
)
from marketlab.datasets.normalize import VerificationCancelled


def ready_entries(root):
    return list(root.glob("ready-entered-*.json"))


def release(root):
    (root / "release-readiness").write_text("release", encoding="utf-8")
    (root / "release-drain").write_text("release", encoding="utf-8")


@contextmanager
def callers(pool, root):
    executor = ThreadPoolExecutor(3)
    try:
        yield executor
    finally:
        release(root)
        try:
            pool.close()
        finally:
            executor.shutdown(wait=True, cancel_futures=True)


def assert_closed(pool):
    snapshot = pool.snapshot()
    assert snapshot["closed"] and not snapshot["starting"]
    assert snapshot["active_submitted"] == snapshot["compute"]["active"] == 0
    assert not any(alive(pid) for pid in snapshot["worker_pids"])


def test_shared_startup_has_two_distinct_ready_workers_before_any_file(tmp_path, monkeypatch):
    requests, manifests = fixtures(tmp_path, 2)
    monkeypatch.setattr(module, "_ready_worker", partial(gated_ready, str(tmp_path)))
    pool = VerificationPool(ComputeBudget())
    with callers(pool, tmp_path) as executor:
        first = executor.submit(pool.verify_many, requests[:1], threading.Event())
        second = executor.submit(pool.verify_many, requests[1:], threading.Event())
        wait_for(lambda: len(ready_entries(tmp_path)) == 2)
        snapshot = pool.snapshot()
        assert snapshot["starting"] and not snapshot["bootstrap_ready"]
        assert snapshot["bootstrap_submitted"] == snapshot["active_submitted"] == 2
        assert snapshot["bootstrap_completed"] == snapshot["submitted"] == 0
        assert snapshot["compute"]["active"] == 2
        assert not first.done() and not second.done()
        release(tmp_path)
        assert first.result(timeout=10) == {requests[0].version: manifests[0]}
        assert second.result(timeout=10) == {requests[1].version: manifests[1]}
        snapshot = pool.snapshot()
        assert snapshot["bootstrap_ready"] and not snapshot["starting"]
        assert snapshot["bootstrap_submitted"] == snapshot["bootstrap_completed"] == 2
        assert snapshot["bootstrap_failed"] == 0 and len(snapshot["worker_pids"]) == 2
        assert snapshot["submitted"] == snapshot["completed"] == 2
        assert snapshot["peak_submitted"] == snapshot["compute"]["peak"] == 2
    assert_closed(pool)


def test_canceled_startup_owner_drains_and_survivor_reuses_healthy_pool(tmp_path, monkeypatch):
    requests, manifests = fixtures(tmp_path, 2)
    monkeypatch.setattr(module, "_ready_worker", partial(gated_ready, str(tmp_path)))
    pool = VerificationPool(ComputeBudget())
    canceled = threading.Event()
    with callers(pool, tmp_path) as executor:
        first = executor.submit(pool.verify_many, requests[:1], canceled)
        wait_for(lambda: len(ready_entries(tmp_path)) == 2)
        canceled.set()
        second = executor.submit(pool.verify_many, requests[1:], threading.Event())
        time.sleep(0.05)
        assert not first.done() and not second.done()
        snapshot = pool.snapshot()
        assert snapshot["compute"]["active"] == 2 and snapshot["submitted"] == 0
        release(tmp_path)
        with pytest.raises(VerificationCancelled):
            first.result(timeout=10)
        assert second.result(timeout=10) == {requests[1].version: manifests[1]}
        snapshot = pool.snapshot()
        assert snapshot["bootstrap_ready"] and not snapshot["broken"]
        assert snapshot["bootstrap_submitted"] == snapshot["bootstrap_completed"] == 2
        assert snapshot["submitted"] == snapshot["completed"] == 1
        assert {row["version"] for row in snapshot["completed_records"]} == {requests[1].version}
    assert_closed(pool)


def test_close_aborts_readiness_drains_permits_and_dispatches_no_files(tmp_path, monkeypatch):
    requests, _ = fixtures(tmp_path)
    monkeypatch.setattr(module, "_ready_worker", partial(gated_ready, str(tmp_path)))
    pool = VerificationPool(ComputeBudget())
    with callers(pool, tmp_path) as executor:
        pending = executor.submit(pool.verify_many, requests, threading.Event())
        wait_for(lambda: len(ready_entries(tmp_path)) == 2)
        assert pool.snapshot()["compute"]["active"] == 2
        closing = executor.submit(pool.close)
        closing.result(timeout=10)
        with pytest.raises(VerificationUnavailable):
            pending.result(timeout=10)
        snapshot = pool.snapshot()
        assert snapshot["submitted"] == snapshot["completed"] == 0
        assert snapshot["bootstrap_failed"] == 2 and not snapshot["bootstrap_ready"]
    assert_closed(pool)


def test_readiness_failure_fails_closed_until_explicit_recreation(tmp_path, monkeypatch):
    requests, manifests = fixtures(tmp_path)
    monkeypatch.setattr(module, "_ready_worker", partial(failing_ready, str(tmp_path)))
    pool = VerificationPool(ComputeBudget())
    try:
        with pytest.raises(VerificationUnavailable):
            pool.verify_many(requests, threading.Event())
        snapshot = pool.snapshot()
        assert snapshot["broken"] and snapshot["compute"]["failed"]
        assert snapshot["bootstrap_submitted"] == snapshot["bootstrap_failed"] == 2
        assert snapshot["bootstrap_completed"] == snapshot["submitted"] == 0
        assert snapshot["compute"]["active"] == 0
        with pytest.raises(VerificationUnavailable):
            pool.verify_many(requests, threading.Event())
        with pytest.raises(VerificationUnavailable):
            with pool.compute.query(threading.Event(), 0.05):
                pytest.fail("SQL reused failed readiness capacity")
    finally:
        pool.close()
    assert_closed(pool)
    monkeypatch.undo()
    replacement = VerificationPool(ComputeBudget())
    try:
        assert replacement.verify_many(requests, threading.Event()) == {
            requests[0].version: manifests[0]
        }
        assert replacement.snapshot()["bootstrap_ready"]
    finally:
        replacement.close()
    assert_closed(replacement)


def test_startup_reserves_both_shared_permits_atomically(tmp_path, monkeypatch):
    requests, _ = fixtures(tmp_path)
    monkeypatch.setattr(module, "_ready_worker", partial(gated_ready, str(tmp_path)))
    pool = VerificationPool(ComputeBudget())
    with callers(pool, tmp_path) as executor:
        with pool.compute.query(threading.Event(), 0.05):
            pending = executor.submit(pool.verify_many, requests, threading.Event())
            time.sleep(0.05)
            snapshot = pool.snapshot()
            assert not snapshot["starting"] and snapshot["bootstrap_submitted"] == 0
            assert snapshot["compute"]["active"] == 1
            assert snapshot["compute"]["active_by_kind"]["query"] == 1
            assert not ready_entries(tmp_path)
        wait_for(lambda: len(ready_entries(tmp_path)) == 2)
        assert pool.snapshot()["compute"]["active"] == 2
        release(tmp_path)
        assert requests[0].version in pending.result(timeout=10)
        assert pool.snapshot()["compute"]["peak"] == 2
    assert_closed(pool)


def test_startup_decision_timeout_retains_both_permits_until_real_drain(tmp_path, monkeypatch):
    requests, _ = fixtures(tmp_path)
    monkeypatch.setattr(module, "_ready_worker", partial(draining_ready, str(tmp_path)))
    original_time = module.time
    advance = threading.Event()

    def controlled_monotonic():
        return original_time.monotonic() + (20 if advance.is_set() else 0)

    # Replace only this module's binding; stdlib subprocess/thread clocks stay real.
    monkeypatch.setattr(
        module,
        "time",
        SimpleNamespace(
            monotonic=controlled_monotonic,
            perf_counter=original_time.perf_counter,
            process_time=original_time.process_time,
            sleep=original_time.sleep,
        ),
    )
    assert time.monotonic is original_time.monotonic
    pool = VerificationPool(ComputeBudget())
    with callers(pool, tmp_path) as executor:
        pending = executor.submit(pool.verify_many, requests, threading.Event())
        wait_for(lambda: len(ready_entries(tmp_path)) == 2)
        advance.set()
        wait_for(lambda: len(list(tmp_path.glob("abort-observed-*"))) == 2)
        snapshot = pool.snapshot()
        assert snapshot["broken"] and snapshot["starting"]
        assert snapshot["compute"]["active"] == snapshot["active_submitted"] == 2
        assert snapshot["submitted"] == snapshot["bootstrap_completed"] == 0
        assert not pending.done()
        release(tmp_path)
        with pytest.raises(VerificationUnavailable):
            pending.result(timeout=10)
        snapshot = pool.snapshot()
        assert not snapshot["starting"] and snapshot["bootstrap_failed"] == 2
        assert snapshot["compute"]["active"] == snapshot["active_submitted"] == 0
    assert_closed(pool)
