"""Metrics freshness, bounded labels and failure isolation from worker work."""

import json
import socket
import threading
from pathlib import Path

import httpx
import pytest
from prometheus_client import CollectorRegistry, Counter, generate_latest
from pydantic import ValidationError

from marketlab import monitoring
from marketlab.config import Settings
from marketlab.monitoring import DurableCollector, DurablePoller, export_metrics


def output(collector):
    registry = CollectorRegistry()
    registry.register(collector)
    return generate_latest(registry).decode()


def test_missing_failed_and_stale_snapshots_are_unavailable_not_zero_jobs():
    now = [100.0]
    collector = DurableCollector(lambda: now[0])
    assert "marketlab_durable_available 0.0" in output(collector)
    assert "marketlab_durable_jobs{" not in output(collector)
    collector.update((("memo", "queued", 2, 3, 1, 12.5),))
    text = output(collector)
    assert 'marketlab_durable_jobs{kind="memo",state="queued"} 2.0' in text
    assert 'marketlab_durable_attempts{kind="memo"} 3.0' in text
    assert 'marketlab_durable_retried_jobs{kind="memo"} 1.0' in text
    assert 'marketlab_durable_oldest_wait_seconds{kind="memo"} 12.5' in text
    now[0] = 115.01
    assert "marketlab_durable_available 0.0" in output(collector)
    assert "marketlab_durable_jobs{" not in output(collector)
    collector.update(())
    assert 'marketlab_durable_jobs{kind="memo",state="queued"} 0.0' in output(collector)
    collector.fail()
    assert "marketlab_durable_jobs{" not in output(collector)


@pytest.mark.parametrize(
    "row",
    [
        ("prompt text", "queued", 1, 1, 0, 0),
        ("memo", "arbitrary", 1, 1, 0, 0),
        ("memo", "queued", -1, 1, 0, 0),
        ("memo", "queued", 1, 1, 0, float("inf")),
        ("memo", "queued", 1, 1, 0, float("nan")),
    ],
)
def test_unknown_labels_and_invalid_values_are_rejected(row):
    with pytest.raises(ValueError):
        DurableCollector().update((row,))


def test_export_disabled_never_opens_server_or_database(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("disabled monitoring accessed a resource")

    monkeypatch.setattr(monitoring, "start_http_server", forbidden)
    monkeypatch.setattr(monitoring, "collector_engine", forbidden)
    with export_metrics(Settings(metrics_port=0), CollectorRegistry(), durable=True) as started:
        assert not started


def test_bind_failure_does_not_change_worker_result(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("occupied")

    monkeypatch.setattr(monitoring, "start_http_server", fail)
    result = None
    with export_metrics(Settings(metrics_port=59110), CollectorRegistry()) as started:
        assert not started
        result = {"attempted_jobs": 1}
    assert result == {"attempted_jobs": 1}


def test_export_shutdown_failure_does_not_mask_original_work_error(monkeypatch):
    class BrokenServer:
        def shutdown(self):
            raise OSError("shutdown")

    monkeypatch.setattr(monitoring, "start_http_server", lambda *a, **k: (BrokenServer(), None))
    with pytest.raises(LookupError, match="work failure"):
        with export_metrics(Settings(metrics_port=59110), CollectorRegistry()):
            raise LookupError("work failure")


def test_real_loopback_export_uses_actual_registry_and_reaps_server():
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
    registry = CollectorRegistry()
    count = Counter("r8_test_work_total", "Actual worker activity", registry=registry)
    before = {thread.ident for thread in threading.enumerate()}
    with export_metrics(Settings(metrics_port=port), registry) as started:
        assert started
        count.inc(3)
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=2) as client:
            response = client.get(f"http://127.0.0.1:{port}/metrics")
            assert "r8_test_work_total 3.0" in response.text
    assert not any(
        thread.ident not in before and "serve_forever" in thread.name
        for thread in threading.enumerate()
    )
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0


def test_background_database_failure_omits_state_and_disposes(monkeypatch):
    observed = threading.Event()

    class Engine:
        disposed = False

        def dispose(self):
            self.disposed = True

    def fail(engine):
        observed.set()
        raise OSError("database unavailable")

    monkeypatch.setattr(monitoring, "collect_jobs", fail)
    engine = Engine()
    collector = DurableCollector()
    collector.update((("research", "running", 1, 1, 0, 0.0),))
    poller = DurablePoller(engine, collector)
    poller.thread.start()
    assert observed.wait(2)
    poller.close()
    assert engine.disposed and not poller.thread.is_alive()
    assert "marketlab_durable_jobs{" not in output(collector)


@pytest.mark.parametrize("value", ["localhost", "::", "192.168.0.1"])
def test_export_bind_is_explicit_allowlist(value):
    with pytest.raises(ValidationError):
        Settings(metrics_bind=value)


def test_dashboard_queries_use_distinct_inference_targets_and_missing_data_label():
    dashboard = json.loads(Path("monitoring/grafana/dashboards/marketlab.json").read_text())
    assert dashboard["uid"] == "marketlab-r8"
    assert all(
        panel["fieldConfig"]["defaults"]["noValue"] == "Unavailable"
        for panel in dashboard["panels"]
    )
    for panel in dashboard["panels"]:
        for target in panel["targets"]:
            expr = target["expr"]
            assert " or vector(0)" not in expr
            if "marketlab_durable_jobs" in expr:
                assert "marketlab_durable_available == 1" in expr
