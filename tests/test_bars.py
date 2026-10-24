"""Exact analytical arithmetic, bounded execution, cache and legacy-safe HTTP tests."""

import asyncio
import copy
import hashlib
import threading
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import create_engine

from marketlab.analytics import BarError, BarService, BarsRequest
from marketlab.analytics.bars import valid_body, vwap
from marketlab.analytics.cache import (
    MAX_VALUE,
    AnalyticsMetrics,
    ResponseCache,
    cache_key,
    canonical,
)
from marketlab.app import create_app
from marketlab.datasets.normalize import SCHEMA

START = datetime(2025, 1, 1, tzinfo=UTC)
VERSION = "a" * 64


def query(interval="1m", start=START, end=None, versions=None, **kwargs):
    return BarsRequest.create(
        versions=versions or [VERSION],
        symbol="BTCUSDT",
        interval=interval,
        start=start,
        end=end or (start if isinstance(start, datetime) else START) + timedelta(minutes=5),
        **kwargs,
    )


def parquet(tmp_path, values):
    path = tmp_path / "trades.parquet"
    rows = []
    for identifier, offset, price, quantity, quote in values:
        rows.append(
            dict(
                venue="binance_spot",
                symbol="BTCUSDT",
                source_trade_id=identifier,
                executed_at=START + timedelta(microseconds=offset),
                price=Decimal(price),
                quantity=Decimal(quantity),
                quote_quantity=Decimal(quote),
                is_buyer_maker=False,
                is_best_match=True,
            )
        )
    pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), path)
    return path


def service(tmp_path, **kwargs):
    return BarService(create_engine("sqlite://"), tmp_path, **kwargs)


def calculate(tmp_path, values, request=None, **kwargs):
    reader = service(tmp_path, **kwargs)
    path = parquet(tmp_path, values)
    return reader._query(request or query(), [path], [VERSION], threading.Event())


def test_exact_bars_order_microseconds_missing_buckets_and_source_quote(tmp_path):
    body = calculate(
        tmp_path,
        [
            (10, 0, "3", "0.1", "7"),
            (2, 0, "2", "0.2", "9"),
            (1, 59_999_999, "4", "0.3", "11"),
            (3, 60_000_000, "5", "1", "5"),
            (4, 299_999_999, "6", "2", "12"),
        ],
    )
    assert body["returned_buckets"] == 3 and body["empty_buckets"] == 2
    first = body["bars"][0]
    assert first == dict(
        start="2025-01-01T00:00:00Z",
        end="2025-01-01T00:01:00Z",
        open="2.000000000000000000",
        high="4.000000000000000000",
        low="2.000000000000000000",
        close="4.000000000000000000",
        base_volume="0.600000000000000000",
        quote_volume="27.000000000000000000",
        trade_count=3,
        vwap="45.000000000000000000",
    )
    assert valid_body(body, query(), [VERSION])


def test_five_minute_direct_combines_one_minute_and_shuffled_order(tmp_path):
    values = [
        (2, 0, "2", "0.2", "0.4"),
        (1, 0, "1", "0.1", "0.1"),
        (3, 299_999_999, "3", "0.3", "0.9"),
        (4, 300_000_000, "9", "1", "9"),
    ]
    minute = calculate(tmp_path, values)
    five = calculate(tmp_path, list(reversed(values)), query("5m"))
    row = five["bars"][0]
    assert row["open"] == minute["bars"][0]["open"]
    assert row["close"] == minute["bars"][-1]["close"]
    assert row["trade_count"] == sum(bar["trade_count"] for bar in minute["bars"]) == 3
    assert Decimal(row["base_volume"]) == sum(Decimal(bar["base_volume"]) for bar in minute["bars"])
    assert Decimal(row["quote_volume"]) == sum(
        Decimal(bar["quote_volume"]) for bar in minute["bars"]
    )
    assert five == calculate(tmp_path, values, query("5m"))


@pytest.mark.parametrize(
    "quote,base,expected",
    [
        ("1", "3", "0.333333333333333333"),
        ("0.000000000000000001", "2", "0.000000000000000000"),
        ("0.000000000000000003", "2", "0.000000000000000002"),
        ("99999999999999999999", "1", "99999999999999999999.000000000000000000"),
    ],
)
def test_vwap_single_half_even_rounding(quote, base, expected):
    assert vwap(Decimal(quote), Decimal(base)) == expected


def test_decimal_sum_overflow_fails_without_float_fallback(tmp_path):
    with pytest.raises(BarError, match="limits"):
        calculate(
            tmp_path,
            [(1, 0, "1", "99999999999999999999", "1"), (2, 1, "1", "99999999999999999999", "1")],
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"interval": "2m"},
        {"start": "2025-01-01"},
        {"start": "2025-01-01T00:00:00-01:00"},
        {"start": START + timedelta(microseconds=1)},
        {"end": START},
        {"end": START + timedelta(days=2)},
        {"versions": [VERSION, VERSION]},
        {"versions": ["../bad"]},
        {"versions": ["a" * 64] * 6},
        {"start": "2024-12-31T23:59:00Z"},
        {
            "interval": "5m",
            "start": START + timedelta(minutes=5),
            "end": START + timedelta(days=5, minutes=5),
        },
    ],
)
def test_request_validation_before_work(changes):
    with pytest.raises(BarError):
        query(**changes)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda b: b.update(symbol="ETHUSDT"),
        lambda b: b.update(dataset_versions=["b" * 64]),
        lambda b: b.update(empty_buckets=-1),
        lambda b: b["bars"][0].update(vwap="NaN"),
        lambda b: b["bars"][0].update(open=1.0),
        lambda b: b["bars"][0].update(trade_count=True),
        lambda b: b["bars"].append(copy.deepcopy(b["bars"][0])),
    ],
)
def test_cached_body_binding_and_schema(tmp_path, mutation):
    body = calculate(tmp_path, [(1, 0, "1", "1", "1")])
    mutation(body)
    assert not valid_body(body, query(), [VERSION])


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.calls = 0
        self.down = False
        self.expiries = []

    async def get(self, key):
        self.calls += 1
        if self.down:
            raise RedisConnectionError("private")
        return self.values.get(key)

    async def set(self, key, payload, ex):
        self.calls += 1
        if self.down:
            raise RedisConnectionError("private")
        self.values[key] = payload
        self.expiries.append(ex)
        return True

    async def getrange(self, key, start, end):
        value = await self.get(key)
        return (value or b"")[start : end + 1]

    async def aclose(self):
        pass


def cache(clock=lambda: 1, jitter=lambda low, high: low):
    instance = ResponseCache(None, AnalyticsMetrics(), clock=clock, jitter=jitter)
    instance.client = FakeRedis()
    return instance


@pytest.mark.asyncio
async def test_cache_ttls_schema_envelope_and_version_identity():
    instance = cache()
    key = cache_key("bars", [VERSION], {"interval": "1m"})
    body = {"completed": "fixture"}
    summary = cache_key("summary", {"run_id": "run-1", "schema": "summary-v1"}, {})

    def summary_validator(candidate):
        return candidate == body

    assert await instance.put(key, body, "bars")
    assert instance.client.expiries[-1] == 810
    assert (await instance.get(key, lambda candidate: candidate == body))[0] == body
    assert await instance.put(summary, body, "summary", validator=summary_validator)
    assert (await instance.get(summary, summary_validator))[0] == body
    assert not await instance.put(
        summary, {"state": "running"}, "summary", validator=summary_validator
    )
    assert not await instance.put(summary, body, "summary")
    assert summary != cache_key("summary", {"run_id": "run-2", "schema": "summary-v1"}, {})
    assert summary != cache_key("summary", {"run_id": "run-1", "schema": "summary-v2"}, {})
    assert instance.client.expiries[-1] == 3240
    assert key != cache_key("bars", ["b" * 64], {"interval": "1m"})
    assert key != cache_key("bars", [VERSION], {"interval": "5m"})
    instance.client.values[key] = b'{"schema":"cache-v1"}'
    assert (await instance.get(key, lambda candidate: True))[0] is None
    assert (await instance.get(summary, lambda candidate: False))[0] is None
    upper = cache(jitter=lambda low, high: high)
    await upper.put("bars", body, "bars")
    await upper.put(summary, body, "summary", validator=summary_validator)
    assert upper.client.expiries == [990, 3960]


@pytest.mark.asyncio
async def test_cache_value_cap_includes_exact_whole_envelope():
    instance = cache()
    base = {"x": ""}
    overhead = len(
        canonical(
            {
                "schema": "cache-v1",
                "key": "k",
                "body": base,
                "sha256": hashlib.sha256(canonical(base)).hexdigest(),
            }
        )
    )
    assert await instance.put("k", {"x": "a" * (MAX_VALUE - overhead)}, "bars")
    assert len(instance.client.values["k"]) == MAX_VALUE
    assert not await instance.put("k", {"x": "a" * (MAX_VALUE - overhead + 1)}, "bars")


@pytest.mark.asyncio
async def test_cache_failure_circuit_and_controlled_recovery():
    now = [10.0]
    instance = cache(clock=lambda: now[0])
    instance.client.down = True
    for _ in range(3):
        assert await instance.get("k", lambda value: True) == (None, False)
    assert instance.client.calls == 3 and instance.open_until == 20
    for _ in range(3):
        assert await instance.get("k", lambda value: True) == (None, False)
    assert instance.client.calls == 3
    now[0] = 20
    instance.client.down = False
    assert await instance.get("k", lambda value: True) == (None, True)
    assert instance.open_until == 0


@pytest.mark.asyncio
async def test_coalescing_waiter_cancellation_and_failure_release(tmp_path, monkeypatch):
    reader = service(tmp_path)
    gate = asyncio.Event()
    calls = []

    async def work(request):
        calls.append(request)
        await gate.wait()
        return {"ok": True}, "BYPASS"

    monkeypatch.setattr(reader, "_read", work)
    tasks = [asyncio.create_task(reader.read(query())) for _ in range(10)]
    await asyncio.sleep(0.02)
    tasks[0].cancel()
    with pytest.raises(asyncio.CancelledError):
        await tasks[0]
    gate.set()
    assert await asyncio.gather(*tasks[1:]) == [({"ok": True}, "BYPASS")] * 9
    assert len(calls) == 1 and not reader.flights

    async def failure(request):
        raise BarError("safe")

    monkeypatch.setattr(reader, "_read", failure)
    with pytest.raises(BarError):
        await reader.read(query())
    assert not reader.flights
    await reader.close()


@pytest.mark.asyncio
async def test_expensive_verification_admission_and_cancellation_release(tmp_path, monkeypatch):
    reader = service(tmp_path, admission_timeout=0.02)
    entered = threading.Event()
    stop = threading.Event()
    active = [0, 0]
    lock = threading.Lock()

    def resolve(request, cancelled):
        with lock:
            active[0] += 1
            active[1] = max(active)
        entered.set()
        try:
            while not stop.wait(0.002) and not cancelled.is_set():
                pass
            raise BarError("safe")
        finally:
            with lock:
                active[0] -= 1

    monkeypatch.setattr(reader.reader, "resolve", resolve)
    tasks = [
        asyncio.create_task(reader.read(query(end=START + timedelta(minutes=n)))) for n in (1, 2)
    ]
    await asyncio.to_thread(entered.wait, 1)
    await asyncio.sleep(0.01)
    with pytest.raises(BarError, match="capacity"):
        await reader.read(query(end=START + timedelta(minutes=3)))
    tasks[0].cancel()
    with pytest.raises(asyncio.CancelledError):
        await tasks[0]
    stop.set()
    await asyncio.gather(tasks[1], return_exceptions=True)
    assert active == [0, 2]
    assert reader.capacity._value == 2
    await reader.close()


def expensive_native(monkeypatch):
    import marketlab.analytics.bars as module

    monkeypatch.setattr(module, "SQL", "SELECT sum(sin(i)) FROM range(1000000000) t(i)")
    # Supply a fixed expensive template without parameters to isolate native cancellation.
    real_connect = module.duckdb.connect
    directories = []
    closed = []
    started = threading.Event()

    class Connection:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def execute(self, sql, parameters=None):
            if sql.startswith("SET") and parameters:
                self.wrapped.execute(sql, parameters)
            else:
                if sql.startswith("SELECT"):
                    started.set()
                self.wrapped.execute(sql)
            return self

        def fetchall(self):
            return self.wrapped.fetchall()

        def interrupt(self):
            self.wrapped.interrupt()

        def close(self):
            self.wrapped.close()
            closed.append(True)

    def connect(**kwargs):
        directories.append(Path(kwargs["config"]["temp_directory"]))
        return Connection(real_connect(**kwargs))

    monkeypatch.setattr(module.duckdb, "connect", connect)
    return directories, closed, started


def test_native_query_deadline_interrupts_and_cleans_temporary_directory(tmp_path, monkeypatch):
    directories, closed, _ = expensive_native(monkeypatch)
    reader = service(tmp_path, query_timeout=0.02)
    path = parquet(tmp_path, [(1, 0, "1", "1", "1")])
    started = time.monotonic()
    with pytest.raises(BarError, match="timed out"):
        reader._query(query(), [path], [VERSION], threading.Event())
    assert time.monotonic() - started < 2
    assert closed == [True] and directories and all(not path.exists() for path in directories)


@pytest.mark.asyncio
async def test_native_caller_cancellation_finishes_work_before_releasing_capacity(
    tmp_path, monkeypatch
):
    directories, closed, started = expensive_native(monkeypatch)
    reader = service(tmp_path)
    path = parquet(tmp_path, [(1, 0, "1", "1", "1")])
    monkeypatch.setattr(reader.reader, "resolve", lambda request, cancelled: ([path], [VERSION]))
    task = asyncio.create_task(reader.read(query()))
    assert await asyncio.to_thread(started.wait, 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed == [True] and directories and all(not path.exists() for path in directories)
    assert reader.capacity._value == 2
    await reader.close()


def test_http_invalid_input_before_database_and_additive_openapi():
    app = create_app()
    app.state.bar_service = Mock()
    with TestClient(app) as client:
        response = client.get(
            "/v1/bars",
            params={
                "version": "../bad",
                "symbol": "BTCUSDT",
                "interval": "1m",
                "start": "2025-01-01T00:00:00Z",
                "end": "2025-01-02T00:00:00Z",
            },
        )
        assert response.status_code == 422
        spec = client.get("/openapi.json").json()
        assert "/trades" in spec["paths"] and "/v1/bars" in spec["paths"]


@pytest.mark.asyncio
async def test_cancelled_flight_detached_before_thread_cleanup_and_new_read_succeeds(
    tmp_path, monkeypatch
):
    reader = service(tmp_path)
    cleaning = asyncio.Event()
    release = asyncio.Event()
    calls = [0]

    async def work(request):
        calls[0] += 1
        if calls[0] == 1:
            try:
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                await release.wait()
        return {"ok": True}, "BYPASS"

    monkeypatch.setattr(reader, "_read", work)
    first = asyncio.create_task(reader.read(query()))
    await asyncio.sleep(0.01)
    first.cancel()
    await cleaning.wait()
    second = asyncio.create_task(reader.read(query()))
    assert await second == ({"ok": True}, "BYPASS")
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert calls == [2] and not reader.flights
    await reader.close()


@pytest.mark.parametrize("value", [42, None, [], {}, False])
@pytest.mark.parametrize("field", ["start", "end"])
def test_malformed_cached_timestamp_is_a_miss(tmp_path, field, value):
    body = calculate(tmp_path, [(1, 0, "1", "1", "1")])
    body["bars"][0][field] = value
    assert not valid_body(body, query(), [VERSION])


@pytest.mark.asyncio
async def test_cache_oversized_transport_is_bounded_to_cap_plus_one():
    instance = cache()
    received = []

    class OversizedRedis(FakeRedis):
        async def getrange(self, key, start, end):
            received.append((start, end))
            return b"a" * (end - start + 1)

        async def get(self, key):
            raise AssertionError("Unbounded GET is forbidden")

    instance.client = OversizedRedis()
    assert await instance.get("large", lambda body: True) == (None, True)
    assert received == [(0, MAX_VALUE)]


@pytest.mark.asyncio
async def test_one_recovery_probe_and_stale_completion_cannot_close_new_circuit():
    now = [10.0]
    instance = cache(clock=lambda: now[0])
    old_generation = await instance._enter()
    instance.client.down = True
    for _ in range(3):
        await instance.get("key", lambda value: True)
    await instance._finish(True, old_generation)
    assert instance.open_until == 20
    now[0] = 20
    started = asyncio.Event()
    release = asyncio.Event()

    async def probe():
        started.set()
        await release.wait()
        return b""

    first = asyncio.create_task(instance._command(probe))
    await started.wait()
    assert await instance._command(probe) == (False, None)
    release.set()
    assert await first == (True, b"")
    assert instance.open_until == 0


@pytest.mark.asyncio
async def test_redis_deadline_has_no_retry_and_put_failure_preserves_computed_body(
    tmp_path, monkeypatch
):
    instance = cache()
    calls = [0]

    async def blocked():
        calls[0] += 1
        await asyncio.sleep(5)

    started = time.monotonic()
    assert await instance._command(blocked) == (False, None)
    assert calls == [1] and time.monotonic() - started < 0.5
    reader = service(tmp_path)
    path = parquet(tmp_path, [(1, 0, "1", "1", "1")])
    monkeypatch.setattr(reader.reader, "resolve", lambda request, cancelled: ([path], [VERSION]))
    fake = FakeRedis()

    async def failed_set(key, payload, ex):
        raise RedisConnectionError("do not leak")

    fake.set = failed_set
    reader.cache.client = fake
    body, status = await reader.read(query())
    assert status == "BYPASS" and body["bars"][0]["trade_count"] == 1
    assert reader.capacity._value == 2
    await reader.close()


def test_vwap_preserves_valid_large_source_quote_base_ratio(tmp_path):
    body = calculate(tmp_path, [(1, 0, "1", "0.000000000000000001", "99999999999999999999")])
    assert body["bars"][0]["vwap"] == "99999999999999999999000000000000000000.000000000000000000"
    assert valid_body(body, query(), [VERSION])
    from marketlab.analytics.schemas import BarResponse

    assert BarResponse.model_validate(body).bars[0].vwap == body["bars"][0]["vwap"]


def test_async_redis_retry_policy_and_timeouts_are_explicit():
    from redis.asyncio.retry import Retry

    instance = ResponseCache("redis://127.0.0.1:1/0", AnalyticsMetrics())
    settings = instance.client.connection_pool.connection_kwargs
    assert isinstance(settings["retry"], Retry)
    assert settings["retry"].get_retries() == 0
    assert settings["socket_timeout"] == settings["socket_connect_timeout"] == 0.1
