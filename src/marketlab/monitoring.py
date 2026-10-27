"""Optional process metrics and separately polled, read-only durable job state.

Worker metrics are disabled by default. Collector scrapes only read a cached
snapshot; database operations use a separate bounded engine and background thread.
Missing/stale database state is omitted, never represented as an empty queue.
"""

import argparse
import math
import signal
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from prometheus_client import CollectorRegistry, ProcessCollector, start_http_server
from prometheus_client.core import GaugeMetricFamily, Metric
from sqlalchemy.engine import Engine

from marketlab.config import Settings

STATES = {
    "ingestion": ("queued", "running", "retry_wait", "succeeded", "failed"),
    "research": ("queued", "running", "retry_wait", "succeeded", "failed"),
    "copilot": ("queued", "running", "retry_wait", "completed", "failed"),
    "memo": ("queued", "running", "retry_wait", "ready", "failed"),
}
TABLES = {
    "ingestion": "ingestion_jobs",
    "research": "research_runs",
    "copilot": "copilot_jobs",
    "memo": "memo_jobs",
}
# Names are fixed application constants, never request-supplied SQL identifiers.
QUERY = sa.text(
    " UNION ALL ".join(
        f"SELECT '{kind}' AS kind, state, count(*) AS jobs, "
        "sum(attempt_count) AS attempts, "
        "count(*) FILTER (WHERE attempt_count > 1) AS retried, "
        "coalesce(max(CASE WHEN state IN ('queued','retry_wait') "
        "THEN greatest(0,extract(epoch FROM clock_timestamp()-created_at)) END),0) AS oldest "
        f"FROM {table} GROUP BY state"
        for kind, table in TABLES.items()
    )
)


@dataclass(frozen=True)
class JobSnapshot:
    observed: float
    values: tuple[tuple[str, str, int, int, int, float], ...]


class DurableCollector:
    """Bounded-cardinality metrics, including explicit freshness/availability."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.lock = threading.Lock()
        self.snapshot: JobSnapshot | None = None
        self.available = False

    def update(self, values: tuple[tuple[str, str, int, int, int, float], ...]) -> None:
        if any(kind not in STATES or state not in STATES[kind] for kind, state, *_ in values):
            raise ValueError("unknown durable metric label")
        if any(
            count < 0 or attempts < 0 or retried < 0 or oldest < 0 or not math.isfinite(oldest)
            for _, _, count, attempts, retried, oldest in values
        ):
            raise ValueError("invalid durable metric value")
        with self.lock:
            self.snapshot = JobSnapshot(self.clock(), values)
            self.available = True

    def fail(self) -> None:
        with self.lock:
            self.available = False

    def collect(self) -> Iterator[Metric]:
        with self.lock:
            snapshot, available = self.snapshot, self.available
        age = max(0.0, self.clock() - snapshot.observed) if snapshot else None
        fresh = available and age is not None and age <= 15.0
        status = GaugeMetricFamily("marketlab_durable_available", "Fresh durable job snapshot")
        status.add_metric([], int(fresh))
        yield status
        if age is not None:
            observed = GaugeMetricFamily(
                "marketlab_durable_snapshot_age_seconds", "Age of last successful job snapshot"
            )
            observed.add_metric([], age)
            yield observed
        if not fresh or snapshot is None:
            return
        jobs = GaugeMetricFamily(
            "marketlab_durable_jobs", "Current durable jobs", labels=["kind", "state"]
        )
        attempts = GaugeMetricFamily(
            "marketlab_durable_attempts", "Current accumulated durable attempts", labels=["kind"]
        )
        retried = GaugeMetricFamily(
            "marketlab_durable_retried_jobs", "Jobs with more than one attempt", labels=["kind"]
        )
        oldest = GaugeMetricFamily(
            "marketlab_durable_oldest_wait_seconds", "Oldest queued/retry age", labels=["kind"]
        )
        counts = {(kind, state): count for kind, state, count, *_ in snapshot.values}
        for kind, states in STATES.items():
            for state in states:
                jobs.add_metric([kind, state], counts.get((kind, state), 0))
            rows = [row for row in snapshot.values if row[0] == kind]
            attempts.add_metric([kind], sum(row[3] for row in rows))
            retried.add_metric([kind], sum(row[4] for row in rows))
            oldest.add_metric([kind], max((row[5] for row in rows), default=0.0))
        yield jobs
        yield attempts
        yield retried
        yield oldest


def collect_jobs(engine: Engine) -> tuple[tuple[str, str, int, int, int, float], ...]:
    """Use a read-only transaction with deadlines independent of worker connections."""
    with engine.begin() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        connection.exec_driver_sql("SET LOCAL statement_timeout = '1000ms'")
        connection.exec_driver_sql("SET LOCAL lock_timeout = '250ms'")
        return tuple(
            (
                str(row.kind),
                str(row.state),
                int(row.jobs),
                int(row.attempts),
                int(row.retried),
                float(row.oldest),
            )
            for row in connection.execute(QUERY)
        )


def collector_engine(settings: Settings) -> Engine:
    # No shared pool with API/worker/heartbeat; every operation has a finite bound.
    inherited_options = settings.sqlalchemy_url.query.get("options", "")
    if not isinstance(inherited_options, str):
        raise ValueError("database options must be one string")
    return sa.create_engine(
        settings.sqlalchemy_url,
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.2,
        connect_args={
            "connect_timeout": 2,
            "options": inherited_options + " -c default_transaction_read_only=on "
            "-c statement_timeout=1000 -c lock_timeout=250 "
            "-c idle_in_transaction_session_timeout=2000",
        },
    )


class DurablePoller:
    def __init__(self, engine: Engine, collector: DurableCollector) -> None:
        self.engine, self.collector = engine, collector
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, name="marketlab-metrics", daemon=True)

    def run(self) -> None:
        try:
            while not self.stop.is_set():
                try:
                    self.collector.update(collect_jobs(self.engine))
                except Exception:
                    self.collector.fail()
                self.stop.wait(5.0)
        finally:
            self.collector.fail()
            self.engine.dispose()

    def close(self) -> None:
        self.stop.set()
        self.thread.join(timeout=5.0)
        # A pathological driver/OS stall must not block successful worker exit.
        # The daemon retains its own engine and disposes it when the call returns.
        self.collector.fail()


@contextmanager
def export_metrics(
    settings: Settings, registry: CollectorRegistry, *, durable: bool = False
) -> Iterator[bool]:
    """Best-effort optional lifecycle; exporter errors cannot fail normal work."""
    server: Any = None
    server_thread: threading.Thread | None = None
    poller: DurablePoller | None = None
    if settings.metrics_port:
        try:
            ProcessCollector(registry=registry)
            if durable:
                collector = DurableCollector()
                registry.register(collector)
                poller = DurablePoller(collector_engine(settings), collector)
                poller.thread.start()
            server, server_thread = start_http_server(
                settings.metrics_port, addr=settings.metrics_bind, registry=registry
            )
        except Exception:
            # No stderr noise, credentials or altered CLI return contract.
            pass
    try:
        yield server is not None
    finally:
        if server is not None:
            try:
                server.shutdown()
                server.server_close()
                if server_thread is not None:
                    server_thread.join(timeout=2.0)
            except Exception:
                pass
        if poller is not None:
            try:
                poller.close()
            except Exception:
                pass


def main() -> int:
    """Run an explicitly enabled collector; no worker launch or job mutation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, type=int)
    arguments = parser.parse_args()
    if not 1 <= arguments.port <= 65535:
        parser.error("port must be between 1 and 65535")
    settings = Settings(metrics_port=arguments.port)
    stopped = threading.Event()
    previous = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
    try:
        for number in previous:
            signal.signal(number, lambda signum, frame: stopped.set())
        with export_metrics(settings, CollectorRegistry(), durable=True) as started:
            if not started:
                print("Monitoring exporter unavailable", file=sys.stderr)
                return 1
            stopped.wait()
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
