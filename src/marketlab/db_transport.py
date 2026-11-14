"""Finite client waits for explicitly configured synchronous worker connections."""

import threading
from types import MethodType
from typing import Any
from weakref import WeakSet

import psycopg
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

from marketlab.datasets.v2.common import V2Error

WAIT_SECONDS = 15.0
_lock = threading.Lock()
_configured: WeakSet[QueuePool] = WeakSet()


def _bind(connection: Any, *_unused: Any) -> None:
    if not isinstance(connection, psycopg.Connection):
        raise V2Error("unavailable", "Synchronous psycopg worker transport required")
    if getattr(connection, "_marketlab_wait_bounded", False):
        return
    original = connection.wait

    def wait(
        owned: Any, generator: Any, interval: float = 0.1, timeout: float | None = None
    ) -> Any:
        limit = WAIT_SECONDS if timeout is None else min(WAIT_SECONDS, timeout)
        try:
            return original(generator, interval=interval, timeout=limit)
        except psycopg.errors._WaitTimeout as error:
            # Finish the same libpq object on its executing thread. Never race
            # another query with a socket-number-based or cross-thread close.
            owned.pgconn.finish()
            raise psycopg.errors.ConnectionFailure(
                "Worker database transport deadline exceeded"
            ) from error

    target: Any = connection
    target.wait = MethodType(wait, connection)
    target._marketlab_wait_bounded = True


def configure(engine: Engine) -> None:
    """Install before worker I/O; no pool disposal or old-session substitution."""
    pool = engine.pool
    with _lock:
        if pool in _configured:
            return
        if not isinstance(pool, QueuePool) or engine.dialect.driver != "psycopg":
            raise V2Error("unavailable", "Worker transport requires a synchronous psycopg pool")
        if pool.checkedout() or (pool.checkedin() and pool._pre_ping):
            raise V2Error("unavailable", "Configure a fresh worker engine before database use")
        # first_connect precedes dialect initialization; connect covers later
        # sessions before pre-ping; checkout covers existing non-ping sessions.
        event.listen(pool, "first_connect", _bind, insert=True)
        event.listen(pool, "connect", _bind, insert=True)
        event.listen(pool, "checkout", _bind)
        _configured.add(pool)
