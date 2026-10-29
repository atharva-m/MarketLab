"""Versioned requests, registry and idempotent control transactions."""

import base64
import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from .common import (
    ASSET,
    HASH,
    KEY,
    SYMBOL,
    V2Error,
    canonical_json,
    date_value,
    digest,
    exact_fields,
    sha256_file,
)

PROTOCOL = "daily-ingestion-v2"
TRANSFORM = "binance-spot-trades-v2"
SEMANTIC = (
    "instrument_id",
    "venue_id",
    "market",
    "source_symbol",
    "base_asset",
    "quote_asset",
    "trade_id_order",
    "adapter",
)


def wire(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: wire(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [wire(v) for v in value]
    return value


def uid(value: object) -> UUID:
    try:
        result = UUID(str(value))
    except ValueError as error:
        raise V2Error("invalid_request", "Invalid resource identifier") from error
    if str(result) != value:
        raise V2Error("invalid_request", "Invalid resource identifier")
    return result


@contextmanager
def transaction(engine: Engine) -> Iterator[Connection]:
    with engine.begin() as connection:
        connection.execute(sa.text("SET LOCAL lock_timeout = '10s'"))
        connection.execute(sa.text("SET LOCAL statement_timeout = '15s'"))
        connection.execute(sa.text("SET LOCAL idle_in_transaction_session_timeout = '15s'"))
        yield connection


def lock(connection: Connection, namespace: str) -> None:
    key = int.from_bytes(hashlib.sha256(namespace.encode()).digest()[:8], "big", signed=True)
    connection.execute(sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def execute(connection: Connection, query: str, **values: Any) -> Any:
    return connection.execute(sa.text(query), values)


def one(connection: Connection, query: str, **values: Any) -> dict[str, Any] | None:
    row = execute(connection, query, **values).mappings().one_or_none()
    return None if row is None else dict(row)


def operation(
    connection: Connection, name: str, key: str, request: object
) -> dict[str, Any] | None:
    if not isinstance(key, str) or KEY.fullmatch(key) is None:
        raise V2Error("invalid_request", "Invalid operation key")
    lock(connection, f"v2-operation:{name}:{PROTOCOL}:{key}")
    old = one(
        connection,
        "SELECT * FROM v2_operations WHERE operation=:name AND protocol=:protocol "
        "AND idempotency_key=:key",
        name=name,
        protocol=PROTOCOL,
        key=key,
    )
    if old is None:
        return None
    if old["request_sha256"] != digest(request):
        raise V2Error("idempotency_conflict", "Operation key conflicts with existing request")
    return dict(old["response_json"], replayed=True)


def save_operation(
    connection: Connection, name: str, key: str, request: object, response: dict[str, Any]
) -> dict[str, Any]:
    execute(
        connection,
        "INSERT INTO v2_operations VALUES (:name,:protocol,:key,:sha,NULL,"
        "CAST(:response AS jsonb),clock_timestamp())",
        name=name,
        protocol=PROTOCOL,
        key=key,
        sha=digest(request),
        response=canonical_json(wire(response)).decode(),
    )
    return wire(dict(response, replayed=False))  # type: ignore[no-any-return]


def semantic_hash(instrument: dict[str, Any]) -> str:
    return digest({field: instrument[field] for field in SEMANTIC})


def registry_request(request: dict[str, Any]) -> dict[str, Any]:
    exact_fields(request, set(SEMANTIC) - {"instrument_id"} | {"display_name"})
    if (
        request["venue_id"] != "binance"
        or request["market"] != "spot"
        or request["trade_id_order"] != "numeric"
        or request["adapter"] != "binance_daily"
    ):
        raise V2Error("unsupported_source", "Only Binance spot instruments are supported")
    for field, pattern in (
        ("source_symbol", SYMBOL),
        ("base_asset", ASSET),
        ("quote_asset", ASSET),
    ):
        if not isinstance(request[field], str) or pattern.fullmatch(request[field]) is None:
            raise V2Error("invalid_request", "Invalid instrument metadata")
    name = request["display_name"]
    if (
        not isinstance(name, str)
        or not 1 <= len(name) <= 80
        or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in name)
    ):
        raise V2Error("invalid_request", "Invalid display label")
    result = dict(request, instrument_id=f"binance:spot:{request['source_symbol']}")
    result["semantic_sha256"] = semantic_hash(result)
    return result


def instrument(connection: Connection, identity: str, *, enabled: bool = False) -> dict[str, Any]:
    result = one(
        connection,
        "SELECT * FROM v2_instruments WHERE instrument_id=:id" + (" FOR SHARE" if enabled else ""),
        id=identity,
    )
    if result is None:
        raise V2Error("not_found", "Instrument not registered")
    if semantic_hash(result) != result["semantic_sha256"]:
        raise V2Error("integrity_failure", "Registry metadata integrity failure")
    if enabled and not result["enabled"]:
        raise V2Error("unsupported_source", "Instrument is disabled for new imports")
    return result


def add_instrument(engine: Engine, request: dict[str, Any], key: str) -> dict[str, Any]:
    value = registry_request(request)
    with transaction(engine) as connection:
        old = operation(connection, "instrument-add", key, request)
        if old is not None:
            return old
        lock(connection, "v2-registry:" + value["instrument_id"])
        found = one(
            connection,
            "SELECT * FROM v2_instruments WHERE instrument_id=:id",
            id=value["instrument_id"],
        )
        if found is not None:
            if found["semantic_sha256"] != value["semantic_sha256"]:
                raise V2Error("idempotency_conflict", "Instrument semantics conflict")
        else:
            execute(
                connection,
                "INSERT INTO v2_instruments (instrument_id,venue_id,market,source_symbol,"
                "base_asset,quote_asset,display_name,trade_id_order,adapter,semantic_sha256,"
                "enabled,revision,created_at,updated_at) VALUES "
                "(:instrument_id,:venue_id,:market,:source_symbol,:base_asset,:quote_asset,"
                ":display_name,:trade_id_order,:adapter,:semantic_sha256,true,0,"
                "clock_timestamp(),clock_timestamp())",
                **value,
            )
        result = instrument(connection, value["instrument_id"])
        return save_operation(connection, "instrument-add", key, request, result)


def update_instrument(
    engine: Engine, identity: str, request: dict[str, Any], key: str
) -> dict[str, Any]:
    exact_fields(request, {"expected_revision"}, {"display_name", "enabled"})
    if (
        type(request["expected_revision"]) is not int
        or request["expected_revision"] < 0
        or not ({"display_name", "enabled"} & request.keys())
        or ("enabled" in request and type(request["enabled"]) is not bool)
    ):
        raise V2Error("invalid_request", "Invalid registry update")
    body = dict(request, instrument_id=identity)
    with transaction(engine) as connection:
        old = operation(connection, "instrument-update", key, body)
        if old is not None:
            return old
        current = one(
            connection,
            "SELECT * FROM v2_instruments WHERE instrument_id=:id FOR UPDATE",
            id=identity,
        )
        if current is None:
            raise V2Error("not_found", "Instrument not registered")
        if current["revision"] != request["expected_revision"]:
            raise V2Error("revision_conflict", "Registry revision is stale")
        trial = {field: current[field] for field in set(SEMANTIC) - {"instrument_id"}}
        trial["display_name"] = request.get("display_name", current["display_name"])
        registry_request(trial)
        execute(
            connection,
            "UPDATE v2_instruments SET display_name=:name,enabled=:enabled,"
            "revision=revision+1,updated_at=clock_timestamp() WHERE instrument_id=:id",
            id=identity,
            name=trial["display_name"],
            enabled=request.get("enabled", current["enabled"]),
        )
        return save_operation(
            connection, "instrument-update", key, body, instrument(connection, identity)
        )


def execution_identity() -> dict[str, str]:
    project = Path(__file__).resolve().parents[4]
    paths = sorted((project / "src/marketlab/datasets").rglob("*.py"))
    paths += [project / "src/marketlab/dataset_cli.py", project / "uv.lock"]
    inventory = {p.relative_to(project).as_posix(): sha256_file(p) for p in paths}
    return {"execution_sha256": digest(inventory), "lock_sha256": inventory["uv.lock"]}


def metadata_hash(metadata: dict[str, Any]) -> str:
    return digest(
        {k: v for k, v in metadata.items() if k not in {"source_name", "source_reference"}}
    )


def canonical_metadata(value: dict[str, Any]) -> dict[str, Any]:
    exact_fields(
        value,
        {
            "schema",
            "instrument_id",
            "trade_date",
            "format",
            "timestamp_encoding",
            "quote_quantity_mode",
            "source_sha256",
            "source_name",
            "source_reference",
            "coverage_claim",
        },
    )
    if (
        value["schema"] != "canonical-trade-import-v1"
        or not isinstance(value["instrument_id"], str)
        or not value["instrument_id"].startswith("binance:spot:")
        or value["quote_quantity_mode"] != "supplied"
        or value["coverage_claim"] != "observed_only"
    ):
        raise V2Error("unsupported_source", "Only supplied-quote Binance spot files are supported")
    day = date_value(value["trade_date"])
    if day > datetime.now(UTC).date():
        raise V2Error("invalid_request", "Future trade dates are unsupported")
    encodings = {
        "csv": {"rfc3339_utc", "unix_seconds", "unix_milliseconds", "unix_microseconds"},
        "parquet": {"arrow_timestamp_us_utc"},
    }
    if (
        not isinstance(value["format"], str)
        or not isinstance(value["timestamp_encoding"], str)
        or value["format"] not in encodings
        or value["timestamp_encoding"] not in encodings[value["format"]]
    ):
        raise V2Error("invalid_request", "Invalid canonical file encoding")
    if (
        not isinstance(value["source_sha256"], str)
        or HASH.fullmatch(value["source_sha256"]) is None
    ):
        raise V2Error("invalid_request", "Invalid source hash")
    for name, bound in (("source_name", 128), ("source_reference", 2048)):
        text = value[name]
        if text is None and name == "source_reference":
            continue
        if not isinstance(text, str) or not 1 <= len(text) <= bound or not text.isprintable():
            raise V2Error("invalid_request", "Invalid source provenance")
    return value


def official_request(request: dict[str, Any]) -> tuple[list[str], date, date]:
    exact_fields(request, {"schema", "adapter", "instrument_ids", "from_date", "before_date"})
    ids = request["instrument_ids"]
    if request["schema"] != PROTOCOL or request["adapter"] != "binance_daily":
        raise V2Error("unsupported_source", "Unsupported ingestion contract")
    if (
        not isinstance(ids, list)
        or not 1 <= len(ids) <= 2
        or any(not isinstance(v, str) or not v.startswith("binance:spot:") for v in ids)
        or len(set(ids)) != len(ids)
    ):
        raise V2Error("invalid_request", "Invalid instrument selection")
    first = date_value(request["from_date"])
    # 9999-12-31 is permitted only as the exclusive endpoint.
    before_text = request["before_date"]
    before = date(9999, 12, 31) if before_text == "9999-12-31" else date_value(before_text)
    if not first < before <= datetime.now(UTC).date() or (before - first).days * len(ids) > 62:
        raise V2Error("invalid_request", "Invalid or excessive ingestion range")
    return sorted(ids), first, before


def page(
    rows: list[dict[str, Any]], query: dict[str, Any], limit: int = 25, cursor: str | None = None
) -> dict[str, Any]:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise V2Error("invalid_request", "Invalid page limit")
    offset = 0
    if cursor is not None:
        try:
            if len(cursor) > 2048:
                raise ValueError
            decoded = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
            if (
                decoded["query"] != digest(query)
                or type(decoded["offset"]) is not int
                or decoded["offset"] < 0
            ):
                raise ValueError
            offset = decoded["offset"]
        except (ValueError, KeyError, TypeError) as error:
            raise V2Error("invalid_request", "Invalid page cursor") from error
    items = rows[offset : offset + limit]
    next_cursor = None
    if offset + limit < len(rows):
        next_cursor = base64.urlsafe_b64encode(
            canonical_json({"query": digest(query), "offset": offset + limit})
        ).decode()
    return {"items": wire(items), "next_cursor": next_cursor}
