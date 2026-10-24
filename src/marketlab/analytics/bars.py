"""Exact bars from pinned, verified historical versions, with bounded DuckDB work."""

import asyncio
import re
import tempfile
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path
from typing import Any

import duckdb
import sqlalchemy as sa
from prometheus_client import CollectorRegistry
from sqlalchemy.engine import Engine

from marketlab.datasets.publication import (
    _safe_path,
    _storage_root,
    dataset_versions,
    inspect_version,
)
from marketlab.datasets.source import DatasetError
from marketlab.trades.schemas import normalize_timestamp

from .cache import AnalyticsMetrics, CacheStatus, ResponseCache, cache_key

DEFINITION = "bars-v1"
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,19})\.[0-9]{18}\Z")
VWAP_DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,37})\.[0-9]{18}\Z")


class BarError(Exception):
    def __init__(self, detail: str, status: int = 422) -> None:
        super().__init__(detail)
        self.status = status


def timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class BarsRequest:
    versions: tuple[str, ...]
    symbol: str
    interval: str
    start: datetime
    end: datetime

    @classmethod
    def create(
        cls,
        *,
        versions: list[str] | tuple[str, ...],
        symbol: str,
        interval: str,
        start: datetime | str,
        end: datetime | str,
    ) -> "BarsRequest":
        try:
            first = normalize_timestamp(start)
            before = normalize_timestamp(end)
            if isinstance(start, str) and not (start.endswith("Z") or start.endswith("+00:00")):
                raise ValueError
            if isinstance(end, str) and not (end.endswith("Z") or end.endswith("+00:00")):
                raise ValueError
            if isinstance(start, datetime) and start.utcoffset() != timedelta(0):
                raise ValueError
            if isinstance(end, datetime) and end.utcoffset() != timedelta(0):
                raise ValueError
            step = {"1m": 60, "5m": 300}[interval]
            duration = (before - first).total_seconds()
            if (
                symbol not in {"BTCUSDT", "ETHUSDT"}
                or not 1 <= len(versions) <= 5
                or len(set(versions)) != len(versions)
                or any(re.fullmatch(r"[0-9a-f]{64}", version) is None for version in versions)
                or not datetime(2025, 1, 1, tzinfo=UTC)
                <= first
                < before
                <= datetime(2025, 2, 1, tzinfo=UTC)
                or duration > step * 1440
                or any(
                    value.microsecond or int((value - EPOCH).total_seconds()) % step
                    for value in (first, before)
                )
                or ((before - timedelta(microseconds=1)).date() - first.date()).days >= 5
            ):
                raise ValueError
            return cls(tuple(sorted(versions)), symbol, interval, first, before)
        except (ValueError, TypeError, KeyError) as error:
            raise BarError("Invalid bounded bar request") from error

    @property
    def seconds(self) -> int:
        return {"1m": 60, "5m": 300}[self.interval]

    def parameters(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "start": timestamp(self.start),
            "end": timestamp(self.end),
            "definition": DEFINITION,
        }


def vwap(quote: Decimal, base: Decimal) -> str:
    with localcontext() as context:
        context.prec = 100
        result = (quote / base).quantize(Decimal("0.000000000000000001"), rounding=ROUND_HALF_EVEN)
    return format(result, ".18f")


# All data-dependent inputs are bound, including the trusted local artifact paths.
SQL = """
WITH buckets AS (
 SELECT *, (epoch_us(executed_at) // ?) * ? AS bucket
 FROM read_parquet(?, hive_partitioning=false)
 WHERE executed_at >= ? AND executed_at < ?
)
SELECT bucket,
 arg_min(price, struct_pack(t := executed_at, id := source_trade_id)),
 max(price), min(price),
 arg_max(price, struct_pack(t := executed_at, id := source_trade_id)),
 sum(quantity), sum(quote_quantity), count(*)
FROM buckets GROUP BY bucket ORDER BY bucket
"""


class VersionReader:
    def __init__(self, engine: Engine, root: Path) -> None:
        self.engine = engine
        self.root = _storage_root(root)
        self.verified: OrderedDict[str, tuple[tuple[Any, ...], tuple[Any, ...], dict[str, Any]]] = (
            OrderedDict()
        )
        self.lock = threading.Lock()

    @staticmethod
    def signature(paths: list[Path]) -> tuple[Any, ...]:
        result: list[Any] = []
        for path in paths:
            stat = path.stat()
            if not path.is_file() or path.is_symlink():
                raise DatasetError("unsafe artifact")
            result.append((stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino))
        return tuple(result)

    def resolve(
        self, request: BarsRequest, cancelled: threading.Event
    ) -> tuple[list[Path], list[str]]:
        try:
            with self.engine.connect() as connection:
                rows = (
                    connection.execute(
                        sa.select(dataset_versions).where(
                            dataset_versions.c.dataset_version_id.in_(request.versions)
                        )
                    )
                    .mappings()
                    .all()
                )
            if len(rows) != len(request.versions):
                raise BarError("Dataset version not found", 404)
            days = []
            for row in rows:
                if (
                    row["symbol"] != request.symbol
                    or row["venue"] != "binance_spot"
                    or row["status"] != "published"
                ):
                    raise BarError("Dataset coverage mismatch", 409)
                days.append(row["trade_date"])
            expected = []
            day = request.start.date()
            while day <= (request.end - timedelta(microseconds=1)).date():
                expected.append(day)
                day += timedelta(days=1)
            if sorted(days) != expected:
                raise BarError("Dataset coverage mismatch", 409)
            paths: list[Path] = []
            versions: list[str] = []
            for row in sorted(rows, key=lambda item: item["trade_date"]):
                if cancelled.is_set():
                    raise BarError("Bar request cancelled", 503)
                version = row["dataset_version_id"]
                manifest_path = _safe_path(self.root, Path(row["manifest_path"]))
                artifact = _safe_path(
                    self.root, Path(row["manifest_path"]).parent / "trades.parquet"
                )
                signature = self.signature([manifest_path, artifact])
                identity = tuple(row.values())
                with self.lock:
                    previous = self.verified.get(version)
                if previous is None or previous[:2] != (identity, signature):
                    manifest = inspect_version(self.engine, self.root, version)
                    if manifest is None:
                        raise BarError("Dataset version not found", 404)
                    if signature != self.signature([manifest_path, artifact]):
                        raise BarError("Dataset changed during verification")
                    with self.lock:
                        self.verified[version] = (identity, signature, manifest)
                        self.verified.move_to_end(version)
                        while len(self.verified) > 128:
                            self.verified.popitem(last=False)
                paths.append(artifact)
                versions.append(version)
            return paths, versions
        except sa.exc.SQLAlchemyError as error:
            raise BarError("Dataset catalog unavailable", 503) from error
        except (DatasetError, OSError, ValueError, TypeError) as error:
            raise BarError("Dataset artifact integrity failure") from error


def valid_body(body: Any, request: BarsRequest, versions: list[str]) -> bool:
    try:
        expected = request.parameters() | {
            "dataset_versions": versions,
            "expected_buckets": int((request.end - request.start).total_seconds())
            // request.seconds,
        }
        if not isinstance(body, dict) or set(body) != set(expected) | {
            "bars",
            "returned_buckets",
            "empty_buckets",
        }:
            return False
        if any(body[key] != value for key, value in expected.items()) or not isinstance(
            body["bars"], list
        ):
            return False
        count = len(body["bars"])
        if (
            type(body["returned_buckets"]) is not int
            or type(body["expected_buckets"]) is not int
            or type(body["empty_buckets"]) is not int
            or body["returned_buckets"] != count
            or body["empty_buckets"] != expected["expected_buckets"] - count
        ):
            return False
        previous: datetime | None = None
        for bar in body["bars"]:
            if (
                not isinstance(bar, dict)
                or not isinstance(bar.get("start"), str)
                or not isinstance(bar.get("end"), str)
            ):
                return False
            if set(bar) != {
                "start",
                "end",
                "open",
                "high",
                "low",
                "close",
                "base_volume",
                "quote_volume",
                "trade_count",
                "vwap",
            }:
                return False
            first = datetime.fromisoformat(bar["start"].replace("Z", "+00:00"))
            before = datetime.fromisoformat(bar["end"].replace("Z", "+00:00"))
            if (
                timestamp(first) != bar["start"]
                or timestamp(before) != bar["end"]
                or first.tzinfo != UTC
                or not request.start <= first < before <= request.end
                or before - first != timedelta(seconds=request.seconds)
                or first.microsecond
                or int((first - EPOCH).total_seconds()) % request.seconds
                or (previous is not None and first <= previous)
            ):
                return False
            if type(bar["trade_count"]) is not int or not 1 <= bar["trade_count"] <= 100_000_000:
                return False
            for key in ("open", "high", "low", "close", "base_volume", "quote_volume", "vwap"):
                if (
                    not isinstance(bar[key], str)
                    or (VWAP_DECIMAL if key == "vwap" else DECIMAL).fullmatch(bar[key]) is None
                    or Decimal(bar[key]) < 0
                ):
                    return False
            if any(
                Decimal(bar[key]) <= 0
                for key in ("open", "high", "low", "close", "base_volume", "quote_volume")
            ):
                return False
            if (
                not Decimal(bar["low"])
                <= min(Decimal(bar["open"]), Decimal(bar["close"]))
                <= max(Decimal(bar["open"]), Decimal(bar["close"]))
                <= Decimal(bar["high"])
            ):
                return False
            if bar["vwap"] != vwap(Decimal(bar["quote_volume"]), Decimal(bar["base_volume"])):
                return False
            previous = first
        return True
    except (ValueError, KeyError, TypeError, ArithmeticError):
        return False


@dataclass
class Flight:
    task: asyncio.Task[tuple[dict[str, Any], CacheStatus]]
    waiters: int = 0


class BarService:
    def __init__(
        self,
        engine: Engine,
        root: Path,
        redis_url: str | None = None,
        *,
        registry: CollectorRegistry | None = None,
        query_timeout: float = 60,
        admission_timeout: float = 1,
    ) -> None:
        self.reader = VersionReader(engine, root)
        self.metrics = AnalyticsMetrics(registry)
        self.cache = ResponseCache(redis_url, self.metrics)
        self.query_timeout = query_timeout
        self.admission_timeout = admission_timeout
        self.capacity = asyncio.Semaphore(2)
        self.flights: dict[str, Flight] = {}
        self.retiring: set[asyncio.Task[tuple[dict[str, Any], CacheStatus]]] = set()

    async def _thread(self, operation: Any, cancelled: threading.Event) -> Any:
        task = asyncio.create_task(asyncio.to_thread(operation))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled.set()
            # Do not release the expensive slot while native work is still running.
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    cancelled.set()
                except Exception:
                    break
            if not task.cancelled():
                task.exception()
            raise

    def _query(
        self,
        request: BarsRequest,
        paths: list[Path],
        versions: list[str],
        cancelled: threading.Event,
    ) -> dict[str, Any]:
        started = time.monotonic()
        deadline = threading.Event()
        with tempfile.TemporaryDirectory(prefix="marketlab-bars-") as temporary:
            connection = duckdb.connect(
                config={
                    "threads": "1",
                    "memory_limit": "512MiB",
                    "temp_directory": temporary,
                    "max_temp_directory_size": "2GiB",
                    "allow_unsigned_extensions": "false",
                    "autoinstall_known_extensions": "false",
                    "autoload_known_extensions": "false",
                }
            )
            connection.execute("SET allowed_paths = ?", [[str(path) for path in paths]])
            connection.execute("SET enable_external_access = false")
            finished = threading.Event()

            def monitor() -> None:
                while not finished.wait(0.01):
                    if cancelled.is_set() or time.monotonic() - started >= self.query_timeout:
                        deadline.set()
                        connection.interrupt()

            watcher = threading.Thread(target=monitor, daemon=True)
            watcher.start()
            try:
                micros = request.seconds * 1_000_000
                rows = connection.execute(
                    SQL, [micros, micros, [str(path) for path in paths], request.start, request.end]
                ).fetchall()
                if deadline.is_set() or cancelled.is_set():
                    raise BarError("Bar query timed out", 504)
                bars = []
                for bucket, opened, high, low, closed, base, quote, count in rows:
                    first = EPOCH + timedelta(microseconds=bucket)
                    bars.append(
                        {
                            "start": timestamp(first),
                            "end": timestamp(first + timedelta(seconds=request.seconds)),
                            "open": format(opened, ".18f"),
                            "high": format(high, ".18f"),
                            "low": format(low, ".18f"),
                            "close": format(closed, ".18f"),
                            "base_volume": format(base, ".18f"),
                            "quote_volume": format(quote, ".18f"),
                            "trade_count": count,
                            "vwap": vwap(quote, base),
                        }
                    )
                expected = int((request.end - request.start).total_seconds()) // request.seconds
                body = request.parameters() | {
                    "dataset_versions": versions,
                    "expected_buckets": expected,
                    "returned_buckets": len(bars),
                    "empty_buckets": expected - len(bars),
                    "bars": bars,
                }
                if not valid_body(body, request, versions):
                    raise BarError("Bar arithmetic exceeds supported precision")
                return body
            except duckdb.Error as error:
                if deadline.is_set() or cancelled.is_set():
                    self.metrics.timeouts.inc()
                    raise BarError("Bar query timed out", 504) from error
                raise BarError("Bar query failed integrity or resource limits") from error
            finally:
                finished.set()
                watcher.join()
                connection.close()
                self.metrics.duration.observe(time.monotonic() - started)

    async def _read(self, request: BarsRequest) -> tuple[dict[str, Any], CacheStatus]:
        try:
            await asyncio.wait_for(self.capacity.acquire(), self.admission_timeout)
        except TimeoutError as error:
            self.metrics.overload.inc()
            raise BarError("Bar query capacity unavailable", 503) from error
        self.metrics.active.inc()
        cancelled = threading.Event()
        try:
            paths, versions = await self._thread(
                lambda: self.reader.resolve(request, cancelled), cancelled
            )
            key = cache_key(
                "bars", {"versions": versions, "definition": DEFINITION}, request.parameters()
            )
            body, available = await self.cache.get(
                key, lambda value: valid_body(value, request, versions)
            )
            if body is not None:
                return body, "HIT"
            body = await self._thread(
                lambda: self._query(request, paths, versions, cancelled), cancelled
            )
            stored = available and await self.cache.put(key, body, "bars")
            return body, "MISS" if stored else "BYPASS"
        finally:
            self.metrics.active.dec()
            self.capacity.release()

    async def read(self, request: BarsRequest) -> tuple[dict[str, Any], CacheStatus]:
        # Validate even manually constructed dataclasses before touching a database.
        request = BarsRequest.create(
            versions=request.versions,
            symbol=request.symbol,
            interval=request.interval,
            start=request.start,
            end=request.end,
        )
        key = cache_key("bars", request.versions, request.parameters())
        flight = self.flights.get(key)
        if flight is None:
            if len(self.flights) >= 128:
                self.metrics.overload.inc()
                raise BarError("Bar query capacity unavailable", 503)
            flight = Flight(asyncio.create_task(self._read(request)))
            self.flights[key] = flight
        else:
            self.metrics.coalesced.inc()
        flight.waiters += 1
        try:
            result = await asyncio.shield(flight.task)
            self.metrics.outcomes.labels(result[1]).inc()
            return result
        finally:
            flight.waiters -= 1
            if flight.waiters == 0:
                # New callers must never join work whose last waiter cancelled.
                if self.flights.get(key) is flight:
                    del self.flights[key]
                if not flight.task.done():
                    self.retiring.add(flight.task)
                    flight.task.add_done_callback(self.retiring.discard)
                    flight.task.cancel()
                    try:
                        await asyncio.shield(flight.task)
                    except (asyncio.CancelledError, Exception):
                        pass

    async def close(self) -> None:
        tasks = [flight.task for flight in self.flights.values()] + list(self.retiring)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.cache.close()
