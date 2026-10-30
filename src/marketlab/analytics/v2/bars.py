"""Bounded verified catalog selection and exact bars for Binance spot instruments."""

import asyncio
import heapq
import tempfile
import threading
import time
from collections import OrderedDict
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import duckdb
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import sqlalchemy as sa

from marketlab.analytics.bars import (
    EPOCH,
    BarError,
    Flight,
    timestamp,
    vwap,
)
from marketlab.analytics.bars import (
    BarService as LegacyBarService,
)
from marketlab.analytics.bars import (
    BarsRequest as LegacyBarsRequest,
)
from marketlab.analytics.bars import (
    valid_body as legacy_valid_body,
)
from marketlab.analytics.cache import CacheStatus, cache_key
from marketlab.analytics.verification import VerificationRequest, VerificationUnavailable
from marketlab.datasets.normalize import VerificationCancelled
from marketlab.datasets.v2.artifacts import verify_dataset
from marketlab.datasets.v2.common import HASH, SYMBOL, V2Error, canonical_json, safe_path, utc_text
from marketlab.datasets.v2.core import instrument, one, semantic_hash, wire
from marketlab.trades.schemas import normalize_timestamp

DEFINITION = "bars-v2"
MAX_VERSIONS = 62


def seconds(delta: timedelta) -> int:
    return delta.days * 86400 + delta.seconds


def utc(value: datetime | str, interval: int) -> datetime:
    try:
        if isinstance(value, str) and not value.endswith(("Z", "+00:00")):
            raise ValueError
        result = normalize_timestamp(value)
        if (
            result.utcoffset() != timedelta(0)
            or result.microsecond
            or seconds(result - EPOCH) % interval
        ):
            raise ValueError
        return result
    except (TypeError, ValueError, OverflowError) as error:
        raise BarError("Invalid aligned UTC bar timestamp") from error


def validate_instrument_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("binance:spot:")
        or SYMBOL.fullmatch(value.removeprefix("binance:spot:")) is None
    ):
        raise BarError("Invalid Binance spot instrument")
    return value


@dataclass(frozen=True)
class BarsRequest:
    versions: tuple[str, ...]
    instrument_id: str
    interval: str
    start: datetime
    end: datetime

    @classmethod
    def create(
        cls,
        *,
        versions: list[str] | tuple[str, ...],
        instrument_id: str,
        interval: str,
        start: datetime | str,
        end: datetime | str,
    ) -> "BarsRequest":
        try:
            identity = validate_instrument_id(instrument_id)
            step = {"1m": 60, "5m": 300}[interval]
            first, before = utc(start, step), utc(end, step)
            if (
                not isinstance(versions, (list, tuple))
                or not 1 <= len(versions) <= 5
                or any(not isinstance(v, str) or HASH.fullmatch(v) is None for v in versions)
                or len(set(versions)) != len(versions)
                or not EPOCH <= first < before <= datetime(9999, 12, 31, tzinfo=UTC)
                or seconds(before - first) > 1440 * step
                or ((before - timedelta(microseconds=1)).date() - first.date()).days >= 5
            ):
                raise ValueError
            return cls(tuple(sorted(versions)), identity, interval, first, before)
        except (ValueError, TypeError, KeyError) as error:
            raise BarError("Invalid bounded v2 bar request") from error

    @property
    def seconds(self) -> int:
        return {"1m": 60, "5m": 300}[self.interval]

    def parameters(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "interval": self.interval,
            "start": timestamp(self.start),
            "end": timestamp(self.end),
            "definition": DEFINITION,
        }


def payload(record: dict[str, Any]) -> bytes:
    return canonical_json(
        [
            utc_text(record["executed_at"]),
            *(format(record[k], ".18f") for k in ("price", "quantity", "quote_quantity")),
            record["is_buyer_maker"],
            record["is_best_match"],
        ]
    )


def _check(cancelled: threading.Event) -> None:
    if cancelled.is_set():
        raise VerificationCancelled("v2 numerical read cancelled")


def numeric_bounds(path: Path, cancelled: threading.Event) -> tuple[int, int]:
    """Call only after full hash/content verification proved strictly sorted IDs."""
    with pq.ParquetFile(path) as parquet:
        if parquet.metadata.num_rows <= 0:
            raise BarError("Empty dataset artifact")
        _check(cancelled)
        first = (
            next(parquet.iter_batches(batch_size=1, columns=["source_trade_id"], row_groups=[0]))
            .column(0)[0]
            .as_py()
        )
        last: Any = None
        for batch in parquet.iter_batches(
            batch_size=16_384,
            columns=["source_trade_id"],
            row_groups=[parquet.num_row_groups - 1],
            use_threads=False,
        ):
            _check(cancelled)
            if batch.num_rows:
                last = batch.column(0)[-1].as_py()
        if last is None:
            raise BarError("Invalid dataset identity bounds")
        return int(first), int(last)


def overlapping_groups(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group inclusive overlapping ID ranges, independently for each instrument."""
    groups: list[list[dict[str, Any]]] = []
    for identity in sorted({r["instrument_id"] for r in rows}):
        current: list[dict[str, Any]] = []
        high = -1
        for row in sorted(
            (r for r in rows if r["instrument_id"] == identity), key=lambda r: r["id_bounds"]
        ):
            low, upper = row["id_bounds"]
            if current and low > high:
                if len(current) > 1:
                    groups.append(current)
                current = []
            current.append(row)
            high = max(high, upper)
        if len(current) > 1:
            groups.append(current)
    return groups


def _records(path: Path, batch_rows: int, cancelled: threading.Event) -> Generator[dict[str, Any]]:
    columns = [
        "source_trade_id",
        "executed_at",
        "price",
        "quantity",
        "quote_quantity",
        "is_buyer_maker",
        "is_best_match",
    ]
    with pq.ParquetFile(path) as parquet:
        for batch in parquet.iter_batches(
            batch_size=batch_rows, columns=columns, use_threads=False
        ):
            _check(cancelled)
            yield from batch.to_pylist()


def check_overlaps(rows: list[dict[str, Any]], cancelled: threading.Event) -> None:
    """Bound aggregate merge buffers to 16,384 rows, exact compare equal numeric IDs."""
    for group in overlapping_groups(rows):
        batch_rows = max(1, 16_384 // len(group))
        streams = [_records(r["path"], batch_rows, cancelled) for r in group]
        heap: list[tuple[int, int, dict[str, Any]]] = []
        try:
            for index, stream in enumerate(streams):
                record = next(stream, None)
                if record is not None:
                    heapq.heappush(heap, (int(record["source_trade_id"]), index, record))
            previous_id: int | None = None
            previous_payload: bytes | None = None
            while heap:
                _check(cancelled)
                identifier, index, record = heapq.heappop(heap)
                if identifier == previous_id:
                    if payload(record) != previous_payload:
                        raise BarError("Selected trade identities conflict", 409)
                else:
                    previous_id, previous_payload = identifier, payload(record)
                following = next(streams[index], None)
                if following is not None:
                    heapq.heappush(heap, (int(following["source_trade_id"]), index, following))
        finally:
            for stream in streams:
                stream.close()


def valid_body(
    body: Any, request: BarsRequest, versions: list[str], metadata: dict[str, Any]
) -> bool:
    if not isinstance(body, dict):
        return False
    fixed = {
        "schema": DEFINITION,
        "definition": DEFINITION,
        "instrument_id": request.instrument_id,
        "instrument": metadata,
        "units": {
            "price": metadata["quote_asset"],
            "quote_volume": metadata["quote_asset"],
            "base_volume": metadata["base_asset"],
        },
        "coverage_claim": "observed_only",
    }
    if any(body.get(key) != value for key, value in fixed.items()):
        return False
    projected = {k: v for k, v in body.items() if k not in fixed}
    projected.update(symbol=request.instrument_id, definition="bars-v1")
    legacy = LegacyBarsRequest(
        request.versions, request.instrument_id, request.interval, request.start, request.end
    )
    return legacy_valid_body(projected, legacy, versions)


SQL = """
WITH buckets AS (
 SELECT CAST(source_trade_id AS BIGINT) AS numeric_id, executed_at,price,quantity,quote_quantity,
 (epoch_us(executed_at) // ?) * ? AS bucket
 FROM read_parquet(?, hive_partitioning=false, union_by_name=true)
 WHERE executed_at >= ? AND executed_at < ?
)
SELECT bucket,
 arg_min(price, struct_pack(t := executed_at, id := numeric_id)),
 max(price), min(price), arg_max(price, struct_pack(t := executed_at, id := numeric_id)),
 sum(quantity), sum(quote_quantity), count(*)
FROM buckets GROUP BY bucket ORDER BY bucket
"""


class BarService:
    """Versioned adapter sharing legacy service admission, compute, cache and lifecycle."""

    def __init__(self, base: LegacyBarService) -> None:
        self.base = base
        self.engine, self.root = base.reader.engine, base.reader.root
        self.verified: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self.lock = threading.Lock()
        self.flights: dict[str, Flight] = {}
        self.retiring: set[asyncio.Task[tuple[dict[str, Any], CacheStatus]]] = set()
        self.closed = False
        self.preparation_timeout = 1800.0

    def _catalog(self, versions: tuple[str, ...]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with self.engine.connect() as connection:
            for version in versions:
                current = one(
                    connection,
                    "SELECT * FROM v2_dataset_versions WHERE dataset_version_id=:id",
                    id=version,
                )
                legacy = one(
                    connection,
                    "SELECT * FROM dataset_versions WHERE dataset_version_id=:id",
                    id=version,
                )
                if current is not None and legacy is not None:
                    raise BarError("Ambiguous dataset identity")
                row = current if current is not None else legacy
                if row is None:
                    raise BarError("Dataset version not found", 404)
                identity = current["instrument_id"] if current else "binance:spot:" + row["symbol"]
                metadata = instrument(connection, identity)
                if semantic_hash(metadata) != metadata["semantic_sha256"]:
                    raise BarError("Instrument semantic metadata mismatch")
                if current:
                    if current["semantic_sha256"] != metadata["semantic_sha256"]:
                        raise BarError("Dataset semantic metadata mismatch")
                    relative = current["manifest_relative_path"]
                else:
                    if row["venue"] != "binance_spot" or row["status"] != "published":
                        raise BarError("Unsupported dataset source")
                    relative = row["manifest_path"]
                manifest_path = safe_path(self.root, relative)
                path = safe_path(self.root, str(Path(relative).parent / "trades.parquet"))
                files = [manifest_path, path]
                if current:
                    files.append(safe_path(self.root, str(Path(relative).parent / "quality.json")))
                rows.append(
                    {
                        **row,
                        "instrument_id": identity,
                        "metadata": wire(metadata),
                        "semantic_sha256": metadata["semantic_sha256"],
                        "contract": "dataset-manifest-v2" if current else "dataset-manifest-v1",
                        "manifest_path": manifest_path,
                        "path": path,
                        "signature": self.base.reader.signature(files),
                        "catalog_identity": tuple(row.items()),
                    }
                )
        return sorted(rows, key=lambda r: (r["instrument_id"], r["trade_date"]))

    def resolve_selection(
        self,
        instrument_ids: tuple[str, ...] | list[str],
        versions: tuple[str, ...] | list[str],
        start: datetime,
        end: datetime,
        cancelled: threading.Event,
    ) -> list[dict[str, Any]]:
        try:
            if (
                not isinstance(instrument_ids, (list, tuple))
                or not isinstance(versions, (list, tuple))
                or not 1 <= len(instrument_ids) <= 2
                or len(set(instrument_ids)) != len(instrument_ids)
                or not 1 <= len(versions) <= MAX_VERSIONS
                or len(set(versions)) != len(versions)
                or any(not isinstance(v, str) or HASH.fullmatch(v) is None for v in versions)
            ):
                raise BarError("Invalid dataset selection")
            for identity in instrument_ids:
                validate_instrument_id(identity)
            first, before = utc(start, 60), utc(end, 60)
            if not EPOCH <= first < before <= datetime(9999, 12, 31, tzinfo=UTC):
                raise BarError("Invalid selected history")
            day_count = ((before - timedelta(microseconds=1)).date() - first.date()).days + 1
            if day_count * len(instrument_ids) > 62:
                raise BarError("Dataset selection exceeds 62 partitions", 409)
            expected = {
                (identity, first.date() + timedelta(days=n))
                for identity in instrument_ids
                for n in range(day_count)
            }
            rows = self._catalog(tuple(versions))
            actual = [(r["instrument_id"], r["trade_date"]) for r in rows]
            if len(set(actual)) != len(actual) or set(actual) != expected:
                raise BarError("Registered coverage is incomplete or ambiguous", 409)
            if len({r["metadata"]["quote_asset"] for r in rows}) != 1:
                raise BarError("Cross-instrument quote assets must match", 409)
            missing_legacy = []
            for row in rows:
                _check(cancelled)
                with self.lock:
                    cached = self.verified.get(row["dataset_version_id"])
                if cached and (cached["catalog_identity"], cached["signature"]) == (
                    row["catalog_identity"],
                    row["signature"],
                ):
                    row.update(manifest=cached["manifest"], id_bounds=cached["id_bounds"])
                elif row["contract"] == "dataset-manifest-v1":
                    missing_legacy.append(
                        VerificationRequest(
                            str(self.root),
                            str(row["manifest_path"].relative_to(self.root)),
                            row["dataset_version_id"],
                            row["manifest_sha256"],
                            row["catalog_identity"],
                            row["signature"],
                        )
                    )
            manifests = {}
            # The native verifier accepts at most five partitions per call.
            # Research can select 62, while sharing that unchanged bounded pool.
            for offset in range(0, len(missing_legacy), 5):
                _check(cancelled)
                manifests.update(
                    self.base.reader.verifier.verify_many(
                        missing_legacy[offset : offset + 5], cancelled
                    )
                )
            for row in rows:
                _check(cancelled)
                if "manifest" not in row:
                    if row["contract"] == "dataset-manifest-v1":
                        manifest = manifests[row["dataset_version_id"]]
                        if (
                            manifest["source"]["actual_sha256"] != row["source_sha256"]
                            or manifest["quality"]["accepted_rows"] != row["row_count"]
                            or manifest["symbol"] != row["symbol"]
                            or manifest["venue"] != row["venue"]
                            or manifest["trade_date"] != row["trade_date"].isoformat()
                        ):
                            raise BarError("Dataset catalog integrity failure")
                    else:
                        with self.base.reader.compute.query(cancelled, self.base.admission_timeout):
                            manifest = verify_dataset(
                                row["manifest_path"].parent,
                                {
                                    "dataset_version_id": row["dataset_version_id"],
                                    "manifest_sha256": row["manifest_sha256"],
                                },
                                cancelled=cancelled.is_set,
                            )
                        if (
                            manifest["identity"]["source_sha256"] != row["source_sha256"]
                            or manifest["identity"]["instrument_semantic_sha256"]
                            != row["semantic_sha256"]
                            or manifest["instrument"]["instrument_id"] != row["instrument_id"]
                            or manifest["identity"]["trade_date"] != row["trade_date"].isoformat()
                            or manifest["quality"]["accepted_rows"] != row["row_count"]
                            or manifest["quality"]["logical_sha256"] != row["logical_sha256"]
                        ):
                            raise BarError("Dataset catalog integrity failure")
                    row["manifest"] = manifest
                    with self.base.reader.compute.query(cancelled, self.base.admission_timeout):
                        row["id_bounds"] = numeric_bounds(row["path"], cancelled)
            current = self._catalog(tuple(versions))
            for row, now in zip(rows, current, strict=True):
                if (row["catalog_identity"], row["signature"]) != (
                    now["catalog_identity"],
                    now["signature"],
                ):
                    raise BarError("Dataset changed during verification")
            with self.base.reader.compute.query(cancelled, self.base.admission_timeout):
                check_overlaps(rows, cancelled)
            _check(cancelled)
            with self.lock:
                for row in rows:
                    self.verified[row["dataset_version_id"]] = dict(row)
                    self.verified.move_to_end(row["dataset_version_id"])
                while len(self.verified) > 128:
                    self.verified.popitem(last=False)
            return rows
        except BarError:
            raise
        except (VerificationCancelled, VerificationUnavailable) as error:
            raise BarError("Dataset verification unavailable", 503) from error
        except sa.exc.SQLAlchemyError as error:
            raise BarError("Dataset catalog unavailable", 503) from error
        except (V2Error, OSError, ValueError, TypeError, KeyError) as error:
            raise BarError("Dataset artifact integrity failure") from error

    async def prepare_selection(
        self,
        instrument_ids: tuple[str, ...] | list[str],
        versions: tuple[str, ...] | list[str],
        start: datetime,
        end: datetime,
        cancelled: threading.Event,
    ) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            await self.base._thread(
                lambda: self.resolve_selection(instrument_ids, versions, start, end, cancelled),
                cancelled,
            ),
        )

    def _query(
        self,
        request: BarsRequest,
        rows: list[dict[str, Any]],
        cancelled: threading.Event,
        scratch_root: Path | None = None,
    ) -> dict[str, Any]:
        try:
            return self._bounded_query(request, rows, cancelled, scratch_root)
        except (VerificationCancelled, VerificationUnavailable) as error:
            self.base.metrics.overload.inc()
            raise BarError("Bar query capacity unavailable", 503) from error

    def _bounded_query(
        self,
        request: BarsRequest,
        rows: list[dict[str, Any]],
        cancelled: threading.Event,
        scratch_root: Path | None = None,
    ) -> dict[str, Any]:
        with self.base.reader.compute.query(cancelled, self.base.admission_timeout):
            paths = [r["path"] for r in rows]
            versions = [r["dataset_version_id"] for r in rows]
            metadata = rows[0]["metadata"]
            with tempfile.TemporaryDirectory(prefix="v2-bars-", dir=scratch_root) as temporary:
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
                try:
                    connection.execute("SET allowed_paths = ?", [[str(p) for p in paths]])
                    connection.execute("SET enable_external_access = false")
                except BaseException:
                    connection.close()
                    raise
                finished, deadline = threading.Event(), threading.Event()
                started = time.monotonic()

                def watch() -> None:
                    while not finished.wait(0.01):
                        if (
                            cancelled.is_set()
                            or time.monotonic() - started >= self.base.query_timeout
                        ):
                            deadline.set()
                            connection.interrupt()

                watcher = threading.Thread(target=watch, daemon=True)
                watcher.start()
                try:
                    micros = request.seconds * 1_000_000
                    result = connection.execute(
                        SQL, [micros, micros, [str(p) for p in paths], request.start, request.end]
                    ).fetchall()
                    if deadline.is_set() or cancelled.is_set():
                        raise BarError("Bar query timed out", 504)
                    bars = []
                    for bucket, opened, high, low, closed, base, quote, count in result:
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
                    expected = seconds(request.end - request.start) // request.seconds
                    body = request.parameters() | {
                        "schema": DEFINITION,
                        "instrument": metadata,
                        "units": {
                            "price": metadata["quote_asset"],
                            "quote_volume": metadata["quote_asset"],
                            "base_volume": metadata["base_asset"],
                        },
                        "coverage_claim": "observed_only",
                        "dataset_versions": versions,
                        "expected_buckets": expected,
                        "returned_buckets": len(bars),
                        "empty_buckets": expected - len(bars),
                        "bars": bars,
                    }
                    if not valid_body(body, request, versions, metadata):
                        raise BarError("Bar arithmetic exceeds supported precision")
                    return body
                except duckdb.Error as error:
                    if deadline.is_set() or cancelled.is_set():
                        raise BarError("Bar query timed out", 504) from error
                    raise BarError("Bar query failed integrity or resource limits") from error
                finally:
                    finished.set()
                    watcher.join()
                    connection.close()
                    self.base.metrics.duration.observe(time.monotonic() - started)

    async def read_prepared(
        self,
        request: BarsRequest,
        rows: list[dict[str, Any]],
        cancelled: threading.Event | None = None,
        *,
        scratch_root: Path | None = None,
    ) -> tuple[dict[str, Any], CacheStatus]:
        request = BarsRequest.create(
            versions=request.versions,
            instrument_id=request.instrument_id,
            interval=request.interval,
            start=request.start,
            end=request.end,
        )
        selected = [r for r in rows if r["dataset_version_id"] in request.versions]
        expected_days = {
            (request.start.date() + timedelta(days=n))
            for n in range(
                ((request.end - timedelta(microseconds=1)).date() - request.start.date()).days + 1
            )
        }
        if (
            len(selected) != len(request.versions)
            or {r["trade_date"] for r in selected} != expected_days
            or any(r["instrument_id"] != request.instrument_id for r in selected)
        ):
            raise BarError("Prepared bar selection mismatch", 409)
        stop = cancelled or threading.Event()

        def check_binding() -> None:
            _check(stop)
            current = self._catalog(tuple(r["dataset_version_id"] for r in selected))
            for previous, now in zip(selected, current, strict=True):
                if (previous["catalog_identity"], previous["signature"]) != (
                    now["catalog_identity"],
                    now["signature"],
                ):
                    raise BarError("Prepared dataset changed after verification")

        await self.base._thread(check_binding, stop)
        metadata = selected[0]["metadata"]
        versions = [r["dataset_version_id"] for r in selected]
        key = cache_key(
            "bars",
            [
                {
                    "version": r["dataset_version_id"],
                    "manifest": r["manifest_sha256"],
                    "semantic": r["semantic_sha256"],
                }
                for r in selected
            ],
            request.parameters() | {"metadata": metadata},
        )

        def validator(value: Any) -> bool:
            return valid_body(value, request, versions, metadata)

        body, available = await self.base.cache.get(key, validator)
        if body is not None:
            return body, "HIT"
        body = await self.base._thread(
            lambda: self._query(request, selected, stop, scratch_root), stop
        )
        stored = available and await self.base.cache.put(key, body, "bars", validator=validator)
        return body, "MISS" if stored else "BYPASS"

    async def _read(self, request: BarsRequest) -> tuple[dict[str, Any], CacheStatus]:
        from marketlab.research.v2.capacity import release, reserve

        try:
            await asyncio.wait_for(self.base.capacity.acquire(), self.base.admission_timeout)
        except TimeoutError as error:
            raise BarError("Bar query capacity unavailable", 503) from error
        reservation = None
        stop = threading.Event()
        self.base.metrics.active.inc()
        try:
            async with asyncio.timeout(self.preparation_timeout):
                reservation = await self.base._thread(
                    lambda: reserve(self.engine, self.root, purpose="preparation"), stop
                )
                rows = await self.prepare_selection(
                    (request.instrument_id,), request.versions, request.start, request.end, stop
                )
                return await self.read_prepared(
                    request, rows, stop, scratch_root=Path(reservation["path"])
                )
        except TimeoutError as error:
            raise BarError("Bar preparation deadline exceeded", 504) from error
        finally:
            try:
                if reservation is not None:
                    await asyncio.to_thread(
                        release, self.engine, self.root, reservation, success=True
                    )
            finally:
                self.base.metrics.active.dec()
                self.base.capacity.release()

    async def read(self, request: BarsRequest) -> tuple[dict[str, Any], CacheStatus]:
        request = BarsRequest.create(
            versions=request.versions,
            instrument_id=request.instrument_id,
            interval=request.interval,
            start=request.start,
            end=request.end,
        )
        if self.closed or self.base.closed:
            raise BarError("Bar service closed", 503)
        key = cache_key("bars", request.versions, request.parameters())
        flight = self.flights.get(key)
        if flight is None:
            if len(self.flights) >= 128:
                raise BarError("Bar query capacity unavailable", 503)
            flight = Flight(asyncio.create_task(self._read(request)))
            self.flights[key] = flight
        else:
            self.base.metrics.coalesced.inc()
        flight.waiters += 1
        try:
            value = await asyncio.shield(flight.task)
            self.base.metrics.outcomes.labels(value[1]).inc()
            return value
        finally:
            flight.waiters -= 1
            if flight.waiters == 0:
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
        self.closed = True
        tasks = [f.task for f in self.flights.values()] + list(self.retiring)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
