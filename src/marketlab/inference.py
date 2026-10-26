"""Shared, nonpreemptive inference admission for cooperating local workers."""

import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Engine

INFERENCE_LOCK = int.from_bytes(
    hashlib.sha256(b"marketlab:copilot:inference-v1").digest()[:8], "big", signed=True
)
_held: ContextVar[tuple[Engine, object, Any] | None] = ContextVar(
    "inference_admission", default=None
)


def held(engine: Engine) -> bool:
    value = _held.get()
    return (
        value is not None and value[:2] == (engine, asyncio.current_task()) and not value[2].closed
    )


async def release_current(engine: Engine) -> None:
    value = _held.get()
    if value is not None and held(engine):

        def close() -> None:
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
    if held(engine):
        yield True
        return

    def acquire() -> tuple[Any, bool]:
        connection = engine.connect()
        try:
            acquired = bool(
                connection.scalar(sa.select(sa.func.pg_try_advisory_lock(INFERENCE_LOCK)))
            )
            connection.commit()
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
