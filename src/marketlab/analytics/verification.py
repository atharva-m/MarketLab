"""Lazy two-process file verification sharing two compute permits with DuckDB."""

import ctypes
import multiprocessing as mp
import os
import queue
import sys
import threading
import time
from collections import deque
from collections.abc import Iterator
from concurrent.futures import CancelledError, Future, ProcessPoolExecutor, TimeoutError
from concurrent.futures.process import BrokenProcessPool
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from marketlab.datasets.normalize import VerificationCancelled
from marketlab.datasets.publication import _safe_path, _verify_manifest


class VerificationUnavailable(Exception):
    """The bounded verifier cannot accept work safely."""


class ComputeBudget:
    """A service-wide budget: file verification and SQL are never additive."""

    def __init__(self) -> None:
        self.condition = threading.Condition()
        self.active = 0
        self.peak = 0
        self.kinds = {"verification": 0, "query": 0}
        self.failed = False

    def try_acquire(self, kind: str) -> bool:
        with self.condition:
            if self.failed:
                raise VerificationUnavailable("compute workers unavailable")
            if self.active >= 2:
                return False
            self.active += 1
            self.kinds[kind] += 1
            self.peak = max(self.peak, self.active)
            return True

    def release(self, kind: str) -> None:
        with self.condition:
            if self.active <= 0 or self.kinds[kind] <= 0:
                raise RuntimeError("compute permit released twice")
            self.active -= 1
            self.kinds[kind] -= 1
            self.condition.notify_all()

    def fail_closed(self) -> None:
        with self.condition:
            self.failed = True
            self.condition.notify_all()

    @contextmanager
    def query(self, cancelled: threading.Event, timeout: float) -> Iterator[None]:
        deadline = time.monotonic() + timeout
        while not self.try_acquire("query"):
            if cancelled.is_set():
                raise VerificationCancelled("bar request cancelled")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise VerificationUnavailable("compute capacity unavailable")
            with self.condition:
                self.condition.wait(min(0.02, remaining))
        try:
            if cancelled.is_set():
                raise VerificationCancelled("bar request cancelled")
            yield
        finally:
            self.release("query")

    def snapshot(self) -> dict[str, Any]:
        with self.condition:
            return {
                "limit": 2,
                "active": self.active,
                "peak": self.peak,
                "active_by_kind": dict(self.kinds),
                "failed": self.failed,
            }


_PID_QUEUE: Any = None


def _initialize_worker(pid_queue: Any) -> None:
    """No application clients/configuration; one native CPU/IO thread per child."""
    import pyarrow as pa  # type: ignore[import-untyped]

    global _PID_QUEUE
    _PID_QUEUE = pid_queue
    for name in list(os.environ):
        if name.startswith("MARKETLAB_"):
            os.environ.pop(name, None)
    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    pid_queue.put_nowait(os.getpid())
    parent = mp.parent_process()

    def watch_parent() -> None:
        sleeper = threading.Event()
        while not sleeper.wait(0.2):
            if parent is not None and not parent.is_alive():
                # Only this owned child exits; no files/DB state were mutated.
                os._exit(1)

    threading.Thread(target=watch_parent, daemon=True).start()


def _peak_rss() -> int | None:
    try:
        if sys.platform != "win32":
            import resource

            value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            return int(value * (1 if sys.platform == "darwin" else 1024))

        class Memory(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_uint32), ("faults", ctypes.c_uint32)] + [
                (name, ctypes.c_size_t)
                for name in (
                    "peak_working",
                    "working",
                    "peak_paged",
                    "paged",
                    "peak_nonpaged",
                    "nonpaged",
                    "pagefile",
                    "peak_pagefile",
                    "private",
                )
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(Memory),
            ctypes.c_uint32,
        ]
        memory = Memory()
        memory.cb = ctypes.sizeof(memory)
        if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(memory), memory.cb):
            return int(memory.peak_working)
    except (OSError, AttributeError, ValueError):
        pass
    return None


def _verify_file(payload: tuple[str, str, str, str], receiver: Any) -> dict[str, Any]:
    """Spawn-safe pure file worker. Returned manifest is independently catalog-bound by parent."""
    root, relative, version, expected_hash = payload

    def stopped() -> bool:
        try:
            return bool(receiver.poll())
        except (OSError, EOFError):
            return True

    wall, cpu = time.perf_counter(), time.process_time()
    try:
        manifest = _verify_manifest(
            _safe_path(Path(root), Path(relative)), version, expected_hash, cancelled=stopped
        )
        quality = manifest["quality"]
        return {
            "manifest": manifest,
            "record": {
                "version": version,
                "manifest_sha256": expected_hash,
                "logical_sha256": quality["logical_sha256"],
                "parquet_sha256": quality["parquet_sha256"],
                "row_count": quality["accepted_rows"],
                "pid": os.getpid(),
                "wall_seconds": time.perf_counter() - wall,
                "cpu_seconds": time.process_time() - cpu,
                "peak_rss_bytes": _peak_rss(),
                "rss_scope": "worker lifetime high-water RSS, not simultaneous total",
                "arrow_cpu_threads": 1,
                "arrow_io_threads": 1,
            },
        }
    finally:
        receiver.close()


@dataclass(frozen=True)
class VerificationRequest:
    root: str
    relative: str
    version: str
    manifest_hash: str
    identity: tuple[Any, ...]
    signature: tuple[Any, ...]

    @property
    def payload(self) -> tuple[str, str, str, str]:
        return self.root, self.relative, self.version, self.manifest_hash


@dataclass
class _Flight:
    future: Future[dict[str, Any]]
    receiver: Any
    sender: Any
    waiters: set[object] = field(default_factory=set)
    signalled: bool = False
    released: bool = False


class VerificationPool:
    def __init__(self, compute: ComputeBudget) -> None:
        self.compute = compute
        self.context = mp.get_context("spawn")
        self.condition = threading.Condition(threading.RLock())
        self.executor: ProcessPoolExecutor | None = None
        self.pid_queue: Any = None
        self.flights: dict[VerificationRequest, _Flight] = {}
        self.worker_pids: set[int] = set()
        self.closed = False
        self.broken = False
        self.submitted = self.completed = self.failed = self.cancelled = self.coalesced = 0
        self.peak_submitted = 0
        self.records: deque[dict[str, Any]] = deque(maxlen=128)

    def _pids(self) -> None:
        if self.pid_queue is not None:
            while True:
                try:
                    self.worker_pids.add(self.pid_queue.get_nowait())
                except (queue.Empty, OSError, EOFError, ValueError):
                    break

    def _executor(self) -> ProcessPoolExecutor:
        if self.executor is None:
            self.pid_queue = self.context.Queue(maxsize=2)
            self.executor = ProcessPoolExecutor(
                max_workers=2,
                mp_context=self.context,
                initializer=_initialize_worker,
                initargs=(self.pid_queue,),
            )
        return self.executor

    @staticmethod
    def _signal(flight: _Flight) -> None:
        if not flight.signalled and not flight.future.done():
            flight.signalled = True
            try:
                flight.sender.send_bytes(b"cancel")
            except (OSError, EOFError):
                pass
            flight.future.cancel()

    def _finished(self, request: VerificationRequest, flight: _Flight) -> None:
        with self.condition:
            if not flight.released:
                flight.released = True
                if not flight.future.cancelled() and isinstance(
                    flight.future.exception(), BrokenProcessPool
                ):
                    # Futures fail before stdlib finishes reaping sibling workers.
                    # Prevent every new expensive operation until close/recreation.
                    self.broken = True
                    self.compute.fail_closed()
                self.compute.release("verification")
                flight.receiver.close()
                flight.sender.close()
                if flight.future.cancelled():
                    self.cancelled += 1
                else:
                    error = flight.future.exception()
                    if error is None:
                        report = flight.future.result()["record"]
                        self.records.append(report)
                        self.worker_pids.add(report["pid"])
                        self.completed += 1
                    elif isinstance(error, VerificationCancelled):
                        self.cancelled += 1
                    else:
                        self.failed += 1
                        if isinstance(error, BrokenProcessPool):
                            self.broken = True
                if not flight.waiters:
                    self.flights.pop(request, None)
                self.condition.notify_all()

    def _finish_request(self, request: VerificationRequest) -> None:
        with self.condition:
            flight = self.flights.get(request)
            if flight is not None:
                self._finished(request, flight)

    def _attach(self, request: VerificationRequest, token: object) -> _Flight | None:
        existing = self.flights.get(request)
        if existing is not None:
            if existing.signalled:
                return None
            existing.waiters.add(token)
            self.coalesced += 1
            return existing
        if not self.compute.try_acquire("verification"):
            return None
        receiver = sender = None
        try:
            receiver, sender = self.context.Pipe(duplex=False)
            future = self._executor().submit(_verify_file, request.payload, receiver)
            flight = _Flight(future, receiver, sender, {token})
            self.flights[request] = flight
            self.submitted += 1
            self.peak_submitted = max(
                self.peak_submitted, sum(not item.future.done() for item in self.flights.values())
            )
            future.add_done_callback(lambda _: self._finish_request(request))
            return flight
        except BaseException:
            self.compute.release("verification")
            if receiver is not None:
                receiver.close()
            if sender is not None:
                sender.close()
            self.broken = True
            self.compute.fail_closed()
            raise

    def _detach(self, request: VerificationRequest, flight: _Flight, token: object) -> bool:
        flight.waiters.discard(token)
        if not flight.waiters:
            if flight.future.done():
                if flight.released:
                    self.flights.pop(request, None)
            else:
                self._signal(flight)
                return True
        return False

    def verify_many(
        self, requests: list[VerificationRequest], cancelled: threading.Event
    ) -> dict[str, Any]:
        if len(requests) > 5:
            raise VerificationUnavailable("verification batch exceeds limit")
        token = object()
        pending = list(requests)
        attached: dict[VerificationRequest, _Flight] = {}
        result: dict[str, Any] = {}
        try:
            while pending or attached:
                if cancelled.is_set():
                    raise VerificationCancelled("bar request cancelled")
                with self.condition:
                    self._pids()
                    if self.closed or self.broken:
                        raise VerificationUnavailable("verification worker unavailable")
                    for request in list(pending):
                        flight = self._attach(request, token)
                        if flight is not None:
                            attached[request] = flight
                            pending.remove(request)
                    done = [
                        (request, flight)
                        for request, flight in attached.items()
                        if flight.future.done()
                    ]
                for request, flight in done:
                    report = flight.future.result()
                    if cancelled.is_set():
                        raise VerificationCancelled("bar request cancelled")
                    result[request.version] = report["manifest"]
                    with self.condition:
                        self._detach(request, flight, token)
                    del attached[request]
                if not done:
                    with self.condition:
                        self.condition.wait(0.02)
            return result
        except CancelledError as error:
            raise VerificationCancelled("bar request cancelled") from error
        except BrokenProcessPool as error:
            with self.condition:
                self.broken = True
                self.compute.fail_closed()
            raise VerificationUnavailable("verification worker failed") from error
        finally:
            exclusive: list[Future[dict[str, Any]]] = []
            with self.condition:
                for request, flight in attached.items():
                    if self._detach(request, flight, token):
                        exclusive.append(flight.future)
            # A shared survivor retains its own compute permit; exclusive canceled
            # work must really finish before its owner's expensive slot returns.
            for future in exclusive:
                while not future.done():
                    try:
                        future.result(timeout=0.05)
                    except TimeoutError:
                        continue
                    except Exception:
                        break

    def snapshot(self) -> dict[str, Any]:
        with self.condition:
            self._pids()
            return {
                "configured_max_workers": 2,
                "start_method": "spawn",
                "active_submitted": sum(
                    not flight.future.done() for flight in self.flights.values()
                ),
                "peak_submitted": self.peak_submitted,
                "submitted": self.submitted,
                "completed": self.completed,
                "failed": self.failed,
                "cancelled": self.cancelled,
                "coalesced": self.coalesced,
                "worker_pids": sorted(self.worker_pids),
                "completed_records": list(self.records),
                "closed": self.closed,
                "broken": self.broken,
                "compute": self.compute.snapshot(),
            }

    def close(self) -> None:
        with self.condition:
            self.closed = True
            for flight in list(self.flights.values()):
                self._signal(flight)
            self.condition.notify_all()
            executor = self.executor
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)
        with self.condition:
            self._pids()
            if self.pid_queue is not None:
                self.pid_queue.close()
                self.pid_queue.join_thread()
                self.pid_queue = None
            self.flights.clear()
            self.executor = None
