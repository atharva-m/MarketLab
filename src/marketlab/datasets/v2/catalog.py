"""Bounded legacy/v2 catalog adaptation and selected-snapshot identity checks."""

import base64
import hashlib
import json
import sqlite3
import tempfile
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq  # type: ignore[import-untyped]
from sqlalchemy.engine import Engine

from marketlab.datasets.publication import inspect_version as legacy_inspect

from .common import HASH, V2Error, canonical_json, date_value, digest, safe_path, utc_text
from .core import execute, instrument, one, wire
from .normalize import python_rows


def _offset(query: dict[str, Any], limit: int, cursor: str | None) -> int:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise V2Error("invalid_request", "Invalid page limit")
    if cursor is None:
        return 0
    try:
        if not isinstance(cursor, str) or len(cursor) > 2048:
            raise ValueError
        value = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
        if (
            not isinstance(value, dict)
            or set(value) != {"query", "offset"}
            or value["query"] != digest(query)
            or type(value["offset"]) is not int
            or not 0 <= value["offset"] <= 2**63 - 1
        ):
            raise ValueError
        return int(value["offset"])
    except (ValueError, TypeError) as error:
        raise V2Error("invalid_request", "Invalid catalog cursor") from error


def _page(
    rows: list[dict[str, Any]], query: dict[str, Any], limit: int, offset: int
) -> dict[str, Any]:
    next_cursor = None
    if len(rows) > limit:
        next_cursor = base64.urlsafe_b64encode(
            canonical_json({"query": digest(query), "offset": offset + limit})
        ).decode()
    return {"items": wire(rows[:limit]), "next_cursor": next_cursor}


def instruments(
    engine: Engine,
    *,
    identity: str | None = None,
    base: str | None = None,
    quote: str | None = None,
    limit: int = 25,
    cursor: str | None = None,
) -> dict[str, Any]:
    with engine.connect() as connection:
        if identity is not None:
            return wire(instrument(connection, identity))  # type: ignore[no-any-return]
        query = {"command": "instruments", "base": base, "quote": quote}
        offset = _offset(query, limit, cursor)
        rows = [
            dict(v)
            for v in execute(
                connection,
                "SELECT * FROM v2_instruments WHERE (CAST(:base AS text) IS NULL OR "
                "base_asset=:base)"
                "AND (CAST(:quote AS text) IS NULL OR quote_asset=:quote) "
                "ORDER BY instrument_id LIMIT "
                ":limit OFFSET :offset",
                base=base,
                quote=quote,
                limit=limit + 1,
                offset=offset,
            ).mappings()
        ]
        return _page(rows, query, limit, offset)


UNION = """
 SELECT instrument_id,trade_date,dataset_version_id,'dataset-manifest-v2' AS contract,
 source_sha256,row_count,published_at,observed_from AS observed_start,
 observed_through AS observed_end FROM v2_dataset_versions
 UNION ALL
 SELECT 'binance:spot:'||symbol,trade_date,dataset_version_id,'dataset-manifest-v1',
 source_sha256,row_count,published_at,NULL::timestamptz,NULL::timestamptz
 FROM dataset_versions WHERE venue='binance_spot'
"""


def datasets(
    engine: Engine,
    *,
    identity: str | None = None,
    first: str | None = None,
    before: str | None = None,
    limit: int = 25,
    cursor: str | None = None,
) -> dict[str, Any]:
    from_day = date_value(first) if first is not None else None
    before_day = date_value(before) if before is not None else None
    if from_day is not None and before_day is not None and from_day >= before_day:
        raise V2Error("invalid_request", "Invalid catalog date interval")
    query = {"command": "datasets", "instrument": identity, "from": first, "before": before}
    offset = _offset(query, limit, cursor)
    with engine.connect() as connection:
        if identity is not None:
            instrument(connection, identity)
        rows = [
            dict(v)
            for v in execute(
                connection,
                "SELECT c.* FROM (" + UNION + ") c JOIN v2_instruments i USING(instrument_id) "
                "WHERE (CAST(:instrument AS text) IS NULL OR c.instrument_id=:instrument) "
                "AND (CAST(:first AS date) IS NULL OR trade_date>=:first) "
                "AND (CAST(:before AS date) IS NULL OR trade_date<:before) "
                "ORDER BY instrument_id,trade_date,contract,dataset_version_id LIMIT "
                ":limit OFFSET :offset",
                instrument=identity,
                first=from_day,
                before=before_day,
                limit=limit + 1,
                offset=offset,
            ).mappings()
        ]
        return _page(rows, query, limit, offset)


def inspect_version(engine: Engine, root: Path, version: str) -> dict[str, Any]:
    from .artifacts import verify_dataset

    if not isinstance(version, str) or HASH.fullmatch(version) is None:
        raise V2Error("invalid_request", "Invalid dataset version")
    with engine.connect() as connection:
        current = one(
            connection, "SELECT * FROM v2_dataset_versions WHERE dataset_version_id=:id", id=version
        )
        legacy = one(
            connection, "SELECT * FROM dataset_versions WHERE dataset_version_id=:id", id=version
        )
        if current is not None and legacy is not None:
            raise V2Error("integrity_failure", "Ambiguous dataset identity")
        if current is not None:
            instrument(connection, current["instrument_id"])
            path = safe_path(root, current["manifest_relative_path"])
            manifest = verify_dataset(
                path.parent,
                {"manifest_sha256": current["manifest_sha256"], "dataset_version_id": version},
            )
            if (
                manifest["identity"]["source_sha256"] != current["source_sha256"]
                or manifest["identity"]["instrument_semantic_sha256"] != current["semantic_sha256"]
                or manifest["instrument"]["instrument_id"] != current["instrument_id"]
                or manifest["identity"]["trade_date"] != current["trade_date"].isoformat()
                or manifest["quality"]["accepted_rows"] != current["row_count"]
                or manifest["quality"]["logical_sha256"] != current["logical_sha256"]
            ):
                raise V2Error("integrity_failure", "Dataset catalog integrity failure")
            return manifest
        if legacy is None:
            raise V2Error("not_found", "Dataset version not found")
        if legacy["venue"] != "binance_spot":
            raise V2Error("unsupported_source", "Unsupported legacy dataset source")
        instrument(connection, "binance:spot:" + legacy["symbol"])
    old = legacy_inspect(engine, root, version)
    if old is None:
        raise V2Error("not_found", "Dataset version not found")
    return {
        "schema": "dataset-manifest-v1",
        "instrument_id": "binance:spot:" + legacy["symbol"],
        "legacy_manifest": old,
    }


def _observed(value: object, day: date) -> str:
    try:
        if not isinstance(value, str):
            raise ValueError
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0) or parsed.date() != day:
            raise ValueError
        return utc_text(parsed.astimezone(UTC))
    except ValueError as error:
        raise V2Error("integrity_failure", "Invalid observed coverage metadata") from error


def coverage(
    engine: Engine, identity: str, first: str, before: str, *, root: Path
) -> dict[str, Any]:
    start, end = date_value(first), date_value(before)
    if not 1 <= (end - start).days <= 62:
        raise V2Error("invalid_request", "Coverage interval exceeds bounds")
    # Bounded day count does not imply bounded versions: explicitly page alternatives.
    days = []
    for offset in range((end - start).days):
        day = start + timedelta(days=offset)
        result = datasets(
            engine,
            identity=identity,
            first=day.isoformat(),
            before=(day + timedelta(days=1)).isoformat(),
            limit=100,
        )
        for item in result["items"]:
            if item["contract"] == "dataset-manifest-v1":
                with engine.connect() as connection:
                    row = one(
                        connection,
                        "SELECT * FROM dataset_versions WHERE dataset_version_id=:id",
                        id=item["dataset_version_id"],
                    )
                assert row is not None
                path = safe_path(root, row["manifest_path"])
                with path.open("rb") as stream:
                    raw = stream.read(1024 * 1024 + 1)
                if (
                    len(raw) > 1024 * 1024
                    or hashlib.sha256(raw).hexdigest() != row["manifest_sha256"]
                ):
                    raise V2Error("integrity_failure", "Legacy coverage metadata integrity failure")
                m = json.loads(raw)
                if (
                    m["dataset_version_id"] != row["dataset_version_id"]
                    or m["trade_date"] != day.isoformat()
                ):
                    raise V2Error("integrity_failure", "Legacy coverage metadata mismatch")
                item["observed_start"] = m["quality"]["observed_from"]
                item["observed_end"] = m["quality"]["observed_through"]
        for item in result["items"]:
            item["observed_start"] = _observed(item["observed_start"], day)
            item["observed_end"] = _observed(item["observed_end"], day)
            if item["observed_start"] > item["observed_end"]:
                raise V2Error("integrity_failure", "Invalid observed coverage interval")
        complete = result["next_cursor"] is None
        days.append(
            {
                "date": day.isoformat(),
                "versions": result["items"],
                "next_cursor": result["next_cursor"],
                "observed_bounds_complete": complete,
                "observed_start": min((v["observed_start"] for v in result["items"]), default=None)
                if complete
                else None,
                "observed_end": max((v["observed_end"] for v in result["items"]), default=None)
                if complete
                else None,
            }
        )
    return {
        "instrument_id": identity,
        "from_date": first,
        "before_date": before,
        "days": days,
        "gaps": [v["date"] for v in days if not v["versions"]],
        "coverage_claim": "observed_only",
    }


def validate_selection(
    engine: Engine, root: Path, identity: str, versions: list[str]
) -> dict[str, Any]:
    if not 1 <= len(versions) <= 62 or len(set(versions)) != len(versions):
        raise V2Error("invalid_request", "Invalid dataset selection")
    selection_root = safe_path(root, "selection-v2")
    selection_root.mkdir(parents=True, exist_ok=True)
    days: set[str] = set()
    rows = 0
    with tempfile.TemporaryDirectory(dir=selection_root) as folder:
        database = Path(folder) / "identities.sqlite"
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("PRAGMA temp_store=FILE")
            connection.execute("PRAGMA cache_size=-8192")
            connection.execute(
                "CREATE TABLE identities(id INTEGER PRIMARY KEY,payload BLOB NOT NULL)"
            )
            for version in versions:
                manifest = inspect_version(engine, root, version)
                legacy = manifest["schema"] == "dataset-manifest-v1"
                if legacy:
                    m = manifest["legacy_manifest"]
                    current_identity, day = manifest["instrument_id"], m["trade_date"]
                    with engine.connect() as c:
                        registered = one(
                            c,
                            "SELECT manifest_path FROM dataset_versions WHERE "
                            "dataset_version_id=:id",
                            id=version,
                        )
                    assert registered is not None
                    path = safe_path(root, registered["manifest_path"]).parent / "trades.parquet"
                else:
                    m = manifest
                    current_identity, day = (
                        m["instrument"]["instrument_id"],
                        m["identity"]["trade_date"],
                    )
                    path = safe_path(root, f"datasets-v2/{version}/trades.parquet")
                if current_identity != identity or day in days:
                    raise V2Error("revision_conflict", "Instrument/day alternatives conflict")
                days.add(day)
                for batch in pq.ParquetFile(path).iter_batches(batch_size=16_384):
                    for record in python_rows(batch):
                        identifier = int(record["source_trade_id"])
                        payload = canonical_json(
                            [
                                utc_text(record["executed_at"]),
                                *(
                                    format(record[k], ".18f")
                                    for k in ("price", "quantity", "quote_quantity")
                                ),
                                record["is_buyer_maker"],
                                record["is_best_match"],
                            ]
                        )
                        old = connection.execute(
                            "SELECT payload FROM identities WHERE id=?", (identifier,)
                        ).fetchone()
                        if old is not None and old[0] != payload:
                            raise V2Error("revision_conflict", "Selected trade identities conflict")
                        if old is None:
                            connection.execute(
                                "INSERT INTO identities VALUES (?,?)", (identifier, payload)
                            )
                        rows += 1
                    if database.stat().st_size > 20 * 1024**3:
                        raise V2Error("capacity_exceeded", "Selection scratch exceeds limit")
            connection.commit()
    return {"instrument_id": identity, "versions": versions, "verified_rows": rows}
