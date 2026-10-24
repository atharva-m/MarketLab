"""Explicit local R3 acceptance against retained R2 data and owned test services.

No downloads, artifact mutation, or production services. Evidence stays ignored.
Run with MARKETLAB_DATABASE_URL/REDIS_URL targeting the owned disposable services.
"""

import argparse
import asyncio
import hashlib
import json
import os
import platform
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import sqlalchemy as sa

from marketlab.datasets.normalize import SCHEMA
from marketlab.datasets.publication import dataset_versions

BASE = Path("artifacts/r3")
ROOT = Path("artifacts/r2/historical-storage").resolve()
SCALE = 10**18
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def save(name: str, value: object) -> None:
    BASE.mkdir(exist_ok=True)
    (BASE / name).write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


def stamp(micros: int) -> str:
    return (EPOCH + timedelta(microseconds=micros)).isoformat().replace("+00:00", "Z")


def decimal_text(value: int) -> str:
    return f"{value // SCALE}.{value % SCALE:018d}"


def rounded_vwap(quote: int, quantity: int) -> str:
    # Integer division implements a single round-half-even, independently of SQL/Decimal.
    whole, remainder = divmod(quote * SCALE, quantity)
    if remainder * 2 > quantity or (remainder * 2 == quantity and whole % 2):
        whole += 1
    return decimal_text(whole)


def bar_rows(buckets: dict[int, list[Any]], width: int) -> list[dict[str, object]]:
    return [
        {
            "start": stamp(bucket),
            "end": stamp(bucket + width),
            "open": decimal_text(row[2]),
            "high": decimal_text(row[3]),
            "low": decimal_text(row[4]),
            "close": decimal_text(row[5]),
            "base_volume": decimal_text(row[6]),
            "quote_volume": decimal_text(row[7]),
            "trade_count": row[8],
            "vwap": rounded_vwap(row[7], row[6]),
        }
        for bucket, row in sorted(buckets.items())
    ]


def reference_partition(record: dict[str, Any]) -> dict[str, object]:
    """Validate full retained content and aggregate using Python scaled integers."""
    started = time.perf_counter()
    version = record["dataset_version_id"]
    path = ROOT / record["manifest_path"]
    assert path.resolve().is_relative_to(ROOT) and not path.is_symlink()
    assert digest(path) == record["manifest_sha256"]
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["dataset_version_id"] == version
    assert manifest["symbol"] == record["symbol"]
    assert manifest["trade_date"] == record["trade_date"]
    assert manifest["venue"] == record["venue"] == "binance_spot"
    assert manifest["schema_version"] == 1
    assert manifest["transform_version"] == "binance-spot-trades-v1"
    assert manifest["source"]["actual_sha256"] == record["source_sha256"]
    assert manifest["source"]["expected_sha256"] == record["source_sha256"]
    identity = {
        "source_sha256": record["source_sha256"],
        "venue": record["venue"],
        "symbol": record["symbol"],
        "trade_date": record["trade_date"],
        "schema_version": manifest["schema_version"],
        "transform_version": manifest["transform_version"],
        "lock_sha256": manifest["build"]["lock_sha256"],
    }
    assert hashlib.sha256(canonical(identity) + b"\n").hexdigest() == version
    artifact = path.parent / manifest["artifact"]["path"]
    assert manifest["artifact"]["path"] == "trades.parquet"
    assert not artifact.is_symlink() and artifact.resolve().is_relative_to(ROOT)
    assert artifact.stat().st_size == manifest["artifact"]["bytes"]
    assert digest(artifact) == manifest["artifact"]["sha256"]
    quality = manifest["quality"]
    assert manifest["artifact"]["sha256"] == quality["parquet_sha256"]
    assert manifest["artifact"]["bytes"] == quality["parquet_bytes"]
    assert quality["validation"] == "passed" and quality["conflict_rows"] == 0
    assert quality["raw_rows"] == quality["accepted_rows"] + quality["duplicate_rows"]
    beginning = datetime.combine(date.fromisoformat(record["trade_date"]), datetime.min.time(), UTC)
    first_micro = int((beginning - EPOCH).total_seconds()) * 1_000_000
    assert manifest["requested_from"] == stamp(first_micro)
    assert manifest["requested_before"] == stamp(first_micro + 86_400_000_000)
    minute: dict[int, list[Any]] = {}
    five: dict[int, list[Any]] = {}
    logical = hashlib.sha256()
    count = 0
    previous = -1
    observed_min = first_micro + 86_400_000_000
    observed_max = first_micro
    prefix = '["binance_spot","' + record["symbol"] + '",'
    with pq.ParquetFile(artifact) as parquet:
        assert parquet.schema_arrow == SCHEMA
        assert parquet.metadata.num_rows == record["row_count"] == quality["accepted_rows"]
        for batch in parquet.iter_batches(batch_size=16_384):
            columns = []
            for field, column in zip(batch.schema, batch.columns, strict=True):
                assert column.null_count == 0
                if field.name == "executed_at":
                    column = column.cast(pa.int64())
                elif field.name in {"price", "quantity", "quote_quantity"}:
                    column = column.cast(pa.string())
                columns.append(column.to_pylist())
            for venue, symbol, identifier, micros, p, q, quote, maker, best in zip(
                *columns, strict=True
            ):
                assert venue == "binance_spot" and symbol == record["symbol"]
                assert type(identifier) is int and identifier > previous
                assert type(micros) is int and first_micro <= micros < first_micro + 86_400_000_000
                assert type(maker) is bool and type(best) is bool
                price = int(p.replace(".", ""))
                quantity = int(q.replace(".", ""))
                quoted = int(quote.replace(".", ""))
                assert price > 0 and quantity > 0 and quoted > 0
                logical.update(
                    (
                        f'{prefix}{identifier},{micros},"{p}","{q}","{quote}",'
                        f"{int(maker)},{int(best)}]\n"
                    ).encode("ascii")
                )
                key = (micros, identifier)
                for width, buckets in ((60_000_000, minute), (300_000_000, five)):
                    bucket = micros // width * width
                    row = buckets.get(bucket)
                    if row is None:
                        buckets[bucket] = [
                            key,
                            key,
                            price,
                            price,
                            price,
                            price,
                            quantity,
                            quoted,
                            1,
                        ]
                    else:
                        if key < row[0]:
                            row[0], row[2] = key, price
                        if key > row[1]:
                            row[1], row[5] = key, price
                        row[3] = max(row[3], price)
                        row[4] = min(row[4], price)
                        row[6] += quantity
                        row[7] += quoted
                        row[8] += 1
                previous = identifier
                observed_min = min(observed_min, micros)
                observed_max = max(observed_max, micros)
                count += 1
    assert count == record["row_count"]
    assert logical.hexdigest() == quality["logical_sha256"]
    assert stamp(observed_min) == quality["observed_from"]
    assert stamp(observed_max) == quality["observed_through"]
    one, five_rows = bar_rows(minute, 60_000_000), bar_rows(five, 300_000_000)
    # Combine 1m output independently to check direct 5m consistency.
    for item in five_rows:
        constituents = [bar for bar in one if item["start"] <= bar["start"] < item["end"]]
        assert constituents[0]["open"] == item["open"]
        assert constituents[-1]["close"] == item["close"]
        for key in ("base_volume", "quote_volume"):
            assert sum(int(str(bar[key]).replace(".", "")) for bar in constituents) == int(
                str(item[key]).replace(".", "")
            )
        assert sum(int(bar["trade_count"]) for bar in constituents) == item["trade_count"]
        assert max(int(str(bar["high"]).replace(".", "")) for bar in constituents) == int(
            str(item["high"]).replace(".", "")
        )
        assert min(int(str(bar["low"]).replace(".", "")) for bar in constituents) == int(
            str(item["low"]).replace(".", "")
        )
    result = {
        "version": version,
        "symbol": record["symbol"],
        "date": record["trade_date"],
        "rows": count,
        "manifest_sha256": record["manifest_sha256"],
        "artifact_sha256": manifest["artifact"]["sha256"],
        "logical_sha256": logical.hexdigest(),
        "one": one,
        "five": five_rows,
        "reference_seconds": time.perf_counter() - started,
    }
    save(f"reference-{version}.json", result)
    return {key: value for key, value in result.items() if key not in {"one", "five"}}


def records() -> list[dict[str, Any]]:
    value = json.loads(Path("artifacts/r2/catalog-final.json").read_text(encoding="utf-8"))
    result = value["catalog"]
    assert len(result) == 62 and sum(item["row_count"] for item in result) == 230_311_900
    return result


def prepare() -> None:
    engine = sa.create_engine(
        os.environ["MARKETLAB_DATABASE_URL"], connect_args={"connect_timeout": 5}
    )
    summaries = []
    # Two bounded independent scanners; immutable source artifact paths are read only.
    with ProcessPoolExecutor(max_workers=2) as pool:
        for item, result in zip(records(), pool.map(reference_partition, records()), strict=True):
            restored = dict(item)
            restored["trade_date"] = date.fromisoformat(item["trade_date"])
            restored["published_at"] = datetime.fromisoformat(item["published_at"])
            with engine.begin() as connection:
                found = connection.scalar(
                    sa.select(dataset_versions.c.manifest_sha256).where(
                        dataset_versions.c.dataset_version_id == item["dataset_version_id"]
                    )
                )
                if found is None:
                    connection.execute(sa.insert(dataset_versions).values(**restored))
                else:
                    assert found == item["manifest_sha256"]
            summaries.append(result)
            save("reference-progress.json", summaries)
            print(json.dumps(result), flush=True)
    engine.dispose()
    save("reference-complete.json", {"partitions": summaries, "rows": 230_311_900})


async def month() -> None:
    from marketlab.analytics import BarService, BarsRequest

    engine = sa.create_engine(
        os.environ["MARKETLAB_DATABASE_URL"], connect_args={"connect_timeout": 5}
    )
    service = BarService(engine, ROOT, redis_url=os.environ["MARKETLAB_REDIS_URL"])
    checkpoint = BASE / "month-progress.json"
    evidence = json.loads(checkpoint.read_text()) if checkpoint.exists() else []
    completed = {item["version"] for item in evidence}
    limit = asyncio.Semaphore(2)
    wall_start = time.perf_counter()

    async def check_partition(item: dict[str, Any]) -> None:
        async with limit:
            version = item["dataset_version_id"]
            reference = json.loads((BASE / f"reference-{version}.json").read_text())
            start = datetime.combine(
                date.fromisoformat(item["trade_date"]), datetime.min.time(), UTC
            )
            result = {"version": version, "symbol": item["symbol"], "date": item["trade_date"]}
            result["acceptance_phase"] = "two-concurrent-resume"
            for interval, expected in (("1m", reference["one"]), ("5m", reference["five"])):
                request = BarsRequest.create(
                    versions=[version],
                    symbol=item["symbol"],
                    interval=interval,
                    start=start,
                    end=start + timedelta(days=1),
                )
                query_start = time.perf_counter()
                body, status = await service.read(request)
                assert body["bars"] == expected
                assert sum(bar["trade_count"] for bar in body["bars"]) == item["row_count"]
                repeated, repeated_status = await service.read(request)
                assert repeated == body and repeated_status == "HIT"
                result[interval] = {
                    "bars": len(expected),
                    "sha256": hashlib.sha256(canonical(body)).hexdigest(),
                    "cold_status": status,
                    "warm_status": repeated_status,
                    "cold_and_warm_seconds": time.perf_counter() - query_start,
                }
            evidence.append(result)
            save("month-progress.json", evidence)
            print(json.dumps(result), flush=True)

    try:
        await asyncio.gather(
            *(
                check_partition(item)
                for item in records()
                if item["dataset_version_id"] not in completed
            )
        )
        assert len(evidence) == 62
        # Both symbols: five-day aggregation and a midnight crossing must match daily slices.
        cross = []
        for symbol in ("BTCUSDT", "ETHUSDT"):
            selected = [item for item in records() if item["symbol"] == symbol][:5]
            beginning = datetime(2025, 1, 1, tzinfo=UTC)
            expected = []
            for item in selected:
                expected.extend(
                    json.loads((BASE / f"reference-{item['dataset_version_id']}.json").read_text())[
                        "five"
                    ]
                )
            request = BarsRequest.create(
                versions=[item["dataset_version_id"] for item in reversed(selected)],
                symbol=symbol,
                interval="5m",
                start=beginning,
                end=beginning + timedelta(days=5),
            )
            body, status = await service.read(request)
            assert body["bars"] == expected
            cross.append(
                {
                    "symbol": symbol,
                    "days": 5,
                    "bars": len(expected),
                    "status": status,
                    "sha256": hashlib.sha256(canonical(body)).hexdigest(),
                }
            )
            request = BarsRequest.create(
                versions=[item["dataset_version_id"] for item in selected[:2]],
                symbol=symbol,
                interval="1m",
                start=beginning + timedelta(hours=23, minutes=55),
                end=beginning + timedelta(days=1, minutes=5),
            )
            body, status = await service.read(request)
            expected = []
            for item in selected[:2]:
                expected.extend(
                    json.loads((BASE / f"reference-{item['dataset_version_id']}.json").read_text())[
                        "one"
                    ]
                )
            expected = [
                bar
                for bar in expected
                if "2025-01-01T23:55:00Z" <= bar["start"] < "2025-01-02T00:05:00Z"
            ]
            assert body["bars"] == expected
            cross.append({"symbol": symbol, "cross_midnight_bars": len(expected), "status": status})
        retained_integrity = []
        for item in records():
            manifest_path = ROOT / item["manifest_path"]
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            assert digest(manifest_path) == item["manifest_sha256"]
            assert digest(manifest_path.parent / "trades.parquet") == manifest["artifact"]["sha256"]
            retained_integrity.append({"version": item["dataset_version_id"], "unchanged": True})
        save(
            "month-complete.json",
            {
                "partitions": evidence,
                "rows": 230_311_900,
                "cross_day": cross,
                "wall_seconds": time.perf_counter() - wall_start,
                "platform": platform.platform(),
                "python": platform.python_version(),
                "peak_memory": "not measured",
                "retained_artifact_integrity_after_reads": retained_integrity,
            },
        )
    finally:
        await service.close()
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "month"))
    args = parser.parse_args()
    BASE.mkdir(exist_ok=True)
    if args.phase == "prepare":
        prepare()
    else:
        asyncio.run(month())


if __name__ == "__main__":
    main()
