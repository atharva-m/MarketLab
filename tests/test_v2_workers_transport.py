"""Real owned PostgreSQL response blackholes with both TCP endpoints kept open."""

import json
import select
import socket
import threading
import time

import pytest
import sqlalchemy as sa
from test_v2_workers_integration import (  # noqa: F401
    browser_engine,
    model_engine,
    research_engine,
    storage_engine,
    v2_engine,
    worker_engine,
)

from marketlab import db_transport
from marketlab.datasets.v2 import admission
from marketlab.datasets.v2.core import execute

pytestmark = pytest.mark.integration


class ResponseBlackhole:
    """Forward client traffic; consume responses silently without closing TCP."""

    def __init__(self, host, port):
        if host != "127.0.0.1" or not isinstance(port, int):
            raise ValueError("Owned loopback PostgreSQL target required")
        self.target = host, port
        self.stop = threading.Event()
        self.discard = threading.Event()
        self.dropped = threading.Event()
        self.lock = threading.Lock()
        self.channels = set()
        self.children = []
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(8)
        self.listener.settimeout(0.1)
        self.port = self.listener.getsockname()[1]
        self.thread = threading.Thread(target=self.accept, daemon=True)
        self.thread.start()

    def accept(self):
        while not self.stop.is_set():
            try:
                channel, _ = self.listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            thread = threading.Thread(target=self.forward, args=(channel,), daemon=True)
            self.children.append(thread)
            thread.start()

    def forward(self, client):
        upstream = None
        try:
            upstream = socket.create_connection(self.target, timeout=2)
            with self.lock:
                self.channels.update((client, upstream))
            for channel in (client, upstream):
                channel.setblocking(False)
            while not self.stop.is_set():
                readable, _, _ = select.select([client, upstream], [], [], 0.1)
                for source in readable:
                    block = source.recv(65536)
                    if not block:
                        return
                    if source is upstream and self.discard.is_set():
                        self.dropped.set()
                        continue
                    destination = upstream if source is client else client
                    pending = memoryview(block)
                    deadline = time.monotonic() + 2
                    while pending and not self.stop.is_set():
                        if time.monotonic() >= deadline:
                            return
                        if select.select([], [destination], [], 0.1)[1]:
                            pending = pending[destination.send(pending) :]
        except OSError:
            pass
        finally:
            with self.lock:
                self.channels.discard(client)
                if upstream is not None:
                    self.channels.discard(upstream)
            client.close()
            if upstream is not None:
                upstream.close()

    def close(self):
        self.stop.set()
        self.listener.close()
        with self.lock:
            for channel in self.channels:
                try:
                    channel.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        self.thread.join(3)
        for child in self.children:
            child.join(4)
        assert not self.thread.is_alive()
        assert all(not child.is_alive() for child in self.children)


@pytest.mark.parametrize(
    "operation,test_wait",
    [
        ("execute", None),  # Actual production 15-second limit, not a shortened surrogate.
        ("commit", 1.0),
        ("rollback", 1.0),
        ("pre_ping", 1.0),
        ("first_connect", 1.0),
    ],
)
def test_real_silent_database_response_loss_finishes_caller_and_retains_accounting(
    worker_engine,  # noqa: F811
    tmp_path,
    monkeypatch,
    operation,
    test_wait,  # noqa: F811
):
    root = tmp_path / "storage"
    admission.initialize(worker_engine, root)
    ticket = admission.acquire(worker_engine, root, "research", data_bytes=37, physical_bytes=128)
    assert ticket is not None

    def accounting():
        with worker_engine.connect() as connection:
            return dict(
                execute(
                    connection,
                    "SELECT t.state,t.physical_bytes,c.charged_bytes "
                    "FROM v2_admission_tickets t JOIN v2_data_charges c USING(ticket_id) "
                    "WHERE t.ticket_id=:id AND c.charge_id=:charge",
                    id=ticket["ticket_id"],
                    charge=ticket["charge_id"],
                )
                .mappings()
                .one()
            )

    retained = accounting()
    assert retained == {"state": "pending", "physical_bytes": 128, "charged_bytes": 37}
    assert db_transport.WAIT_SECONDS == 15.0
    if test_wait is not None:
        monkeypatch.setattr(db_transport, "WAIT_SECONDS", test_wait)
    budget = db_transport.WAIT_SECONDS
    relay = ResponseBlackhole(worker_engine.url.host, worker_engine.url.port or 5432)
    with worker_engine.connect() as connection:
        schema = execute(connection, "SELECT current_schema()").scalar_one()
    url = worker_engine.url.set(host="127.0.0.1", port=relay.port).update_query_dict(
        {"options": "-csearch_path=" + schema}
    )
    proxied = sa.create_engine(
        url,
        pool_size=1,
        max_overflow=0,
        pool_timeout=1,
        pool_pre_ping=operation == "pre_ping",
        connect_args={"connect_timeout": 1},
    )
    db_transport.configure(proxied)
    invalidated, errors, native = [], [], []
    sa.event.listen(proxied.pool, "invalidate", lambda *args: invalidated.append(True))
    connection = transaction = None
    if operation == "first_connect":
        original = proxied.dialect._get_server_version_info

        def first_query(current):
            raw = current.connection.driver_connection
            assert getattr(raw, "_marketlab_wait_bounded", False)
            native.append(raw)
            relay.discard.set()
            return original(current)

        monkeypatch.setattr(proxied.dialect, "_get_server_version_info", first_query)
    else:
        connection = proxied.connect()
        connection.exec_driver_sql("SELECT 1")
        native.append(connection.connection.driver_connection)
        assert getattr(native[0], "_marketlab_wait_bounded", False)
        if operation == "pre_ping":
            connection.close()
            connection = None
        elif operation in {"commit", "rollback"}:
            transaction = connection.get_transaction()
        relay.discard.set()
    started = threading.Event()

    def caller():
        started.set()
        try:
            if operation in {"pre_ping", "first_connect"}:
                with proxied.connect() as fresh:
                    fresh.exec_driver_sql("SELECT 1")
            elif operation == "execute":
                connection.exec_driver_sql("SELECT 1")
            elif operation == "commit":
                transaction.commit()
            else:
                transaction.rollback()
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=caller, daemon=True)
    began = time.monotonic()
    try:
        thread.start()
        assert started.wait(2) and relay.dropped.wait(4), (
            "No genuine server response was blackholed"
        )
        if operation == "execute":
            assert thread.is_alive(), "Production query exited before its real bounded wait"
            assert accounting() == retained  # No time-based release while consumer is alive.
        thread.join(budget + 4)
        exited_without_relay_close = not thread.is_alive()
        if not exited_without_relay_close:
            relay.close()  # Safe diagnostic drain before failing the bound assertion.
            thread.join(5)
        assert exited_without_relay_close, "Database caller outlived its transport deadline"
        elapsed = time.monotonic() - began
        assert elapsed < budget + 4
        if operation == "execute":
            assert elapsed >= 14.5, "The unchanged 15-second production wait was not exercised"
        assert errors and isinstance(errors[0], sa.exc.DBAPIError)
        assert native and all(raw.closed for raw in native)
        if connection is not None:
            assert connection.invalidated
        elif operation == "pre_ping":
            assert invalidated, "Pre-ping did not invalidate its dead checked-in session"
        assert accounting() == retained
        (tmp_path / "transport-observation.json").write_text(
            json.dumps(
                {
                    "operation": operation,
                    "configured_wait_seconds": budget,
                    "elapsed_monotonic_seconds": elapsed,
                    "caller_exited_before_relay_close": True,
                    "captured_native_connections_closed": all(raw.closed for raw in native),
                    "sqlalchemy_invalidation_observed": bool(connection.invalidated)
                    if connection is not None
                    else bool(invalidated),
                    "initial_dialect_failure": operation == "first_connect",
                    "retained_accounting": retained,
                    "error_class": type(errors[0]).__name__,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    finally:
        relay.close()
        thread.join(5)
        assert not thread.is_alive()
        if connection is not None:
            connection.close()
        proxied.dispose()
