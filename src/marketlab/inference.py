"""Shared, nonpreemptive inference admission for cooperating local workers."""

import asyncio
import hashlib
import select
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

from sqlalchemy.engine import Engine

from marketlab.datasets.v2.common import V2Error

INFERENCE_LOCK = int.from_bytes(
    hashlib.sha256(b"marketlab:copilot:inference-v1").digest()[:8], "big", signed=True
)
_held: ContextVar[tuple[Engine, object, Any] | None] = ContextVar(
    "inference_admission", default=None
)
_session_lock = threading.Lock()
_dispatch: ContextVar[
    tuple[Engine, threading.Event | None, Callable[[], None] | None, threading.Event] | None
] = ContextVar("inference_dispatch", default=None)


class AdmissionLost(V2Error):
    transient = True

    def __init__(self, message: str, *, dispatched: bool = False) -> None:
        super().__init__("upstream_continuation_unknown" if dispatched else "unavailable", message)


async def before_dispatch() -> None:
    value = _dispatch.get()
    if value is None:
        return
    engine, stopped, ownership, dispatched = value
    if ownership is not None:
        await asyncio.to_thread(ownership)
    if stopped is not None and stopped.is_set():
        raise V2Error("ownership_lost", "Inference work stopped")
    await validate_current(engine)
    dispatched.set()


def _bounded_query(connection: Any, query: bytes) -> bool:
    """Drive this exact libpq session with a monotonic network deadline."""
    deadline = time.monotonic() + 2
    pgconn = connection.connection.driver_connection.pgconn
    try:
        pgconn.send_query(query)
        while pgconn.flush():
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([], [pgconn.socket], [], remaining)[1]:
                raise TimeoutError("Admission send deadline")

        def receive() -> Any:
            while pgconn.is_busy():
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([pgconn.socket], [], [], remaining)[0]:
                    raise TimeoutError("Admission receive deadline")
                pgconn.consume_input()
            return pgconn.get_result()

        result = receive()
        valid = (
            result is not None
            and result.status == 2
            and result.ntuples == 1
            and result.get_value(0, 0) == b"t"
        )
        while receive() is not None:
            if time.monotonic() >= deadline:
                raise TimeoutError("Admission results deadline")
        return bool(valid)
    except BaseException:
        # libpq finish closes this socket directly; never wait on cancellation
        # over a partitioned second connection or silently reconnect the session.
        pgconn.finish()
        connection.invalidate()
        raise


async def guarded_call[T](
    engine: Engine,
    operation: Awaitable[T],
    stopped: threading.Event | None = None,
    ownership: Callable[[], None] | None = None,
) -> T:
    try:
        async with dispatch_guard(engine, stopped, ownership):
            return await operation
    finally:
        # A failed preflight must not leave a never-awaited model coroutine.
        if hasattr(operation, "close"):
            operation.close()


async def validate_current(engine: Engine) -> None:
    """Check the exact admission session without reconnecting or acquiring twice."""
    value = _held.get()
    if value is None or value[0] is not engine:
        raise AdmissionLost("Inference admission is unavailable")

    def check() -> None:
        with _session_lock:
            connection = value[2]
            if connection.closed or connection.invalidated:
                raise AdmissionLost("Inference admission session lost")
            key = INFERENCE_LOCK & ((1 << 64) - 1)
            try:
                valid = _bounded_query(
                    connection,
                    (
                        "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' "
                        "AND pid=pg_backend_pid() AND granted "
                        f"AND classid::bigint={key >> 32} "
                        f"AND objid::bigint={key & ((1 << 32) - 1)} AND objsubid=1)"
                    ).encode(),
                )
            except Exception as error:
                connection.invalidate()
                raise AdmissionLost("Inference admission session lost") from error
            if not valid:
                raise AdmissionLost("Inference admission lock lost")

    await asyncio.to_thread(check)


@asynccontextmanager
async def dispatch_guard(
    engine: Engine,
    stopped: threading.Event | None = None,
    ownership: Callable[[], None] | None = None,
) -> AsyncIterator[None]:
    """Cancel local HTTP work on session loss; upstream computation may continue."""
    await validate_current(engine)
    if stopped is not None and stopped.is_set():
        raise V2Error("ownership_lost", "Inference work stopped")
    owner = asyncio.current_task()
    dispatched = threading.Event()
    token = _dispatch.set((engine, stopped, ownership, dispatched))
    lost = asyncio.Event()
    failure: list[Exception] = []

    async def monitor() -> None:
        while True:
            await asyncio.sleep(1)
            try:
                if stopped is not None and stopped.is_set():
                    raise V2Error("ownership_lost", "Inference work stopped")
                await validate_current(engine)
            except Exception as error:
                failure.append(error)
                lost.set()
                if owner is not None:
                    owner.cancel()
                return

    monitor_task = asyncio.create_task(monitor())
    try:
        yield
    except asyncio.CancelledError:
        if lost.is_set():
            if failure and not isinstance(failure[0], AdmissionLost):
                raise failure[0] from None
            raise AdmissionLost(
                "Admission session lost; upstream continuation unknown",
                dispatched=dispatched.is_set(),
            ) from None
        raise
    finally:
        monitor_task.cancel()
        await asyncio.gather(monitor_task, return_exceptions=True)
        _dispatch.reset(token)


def held(engine: Engine) -> bool:
    value = _held.get()
    return (
        value is not None and value[:2] == (engine, asyncio.current_task()) and not value[2].closed
    )


async def release_current(engine: Engine) -> None:
    value = _held.get()
    if value is not None and held(engine):

        def close() -> None:
            with _session_lock:
                try:
                    value[2].invalidate()
                finally:
                    value[2].close()

        task = asyncio.create_task(asyncio.to_thread(close))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise


@asynccontextmanager
async def admission(engine: Engine) -> AsyncIterator[bool]:
    """Acquire before claiming work; a busy worker returns without spending budgets."""
    from marketlab.db_transport import configure

    configure(engine)
    if held(engine):
        yield True
        return

    def acquire() -> tuple[Any, bool]:
        connection = engine.connect()
        try:
            with _session_lock:
                acquired = _bounded_query(
                    connection, f"SELECT pg_try_advisory_lock({INFERENCE_LOCK})".encode()
                )
            return connection, acquired
        except BaseException:
            try:
                connection.invalidate()
            finally:
                connection.close()
            raise

    task = asyncio.create_task(asyncio.to_thread(acquire))
    connection = None
    token = None
    try:
        try:
            connection, acquired = await asyncio.shield(task)
        except asyncio.CancelledError:
            connection, _ = await task
            raise
        if acquired:
            token = _held.set((engine, asyncio.current_task(), connection))
        yield acquired
    finally:
        if token is not None:
            _held.reset(token)
        if connection is not None and not connection.closed:

            def release() -> None:
                with _session_lock:
                    try:
                        connection.invalidate()
                    finally:
                        connection.close()

            cleanup = asyncio.create_task(asyncio.to_thread(release))
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                await cleanup
                raise
