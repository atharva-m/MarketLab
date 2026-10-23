"""Pure all-or-nothing parsing of canonical in-memory JSON and CSV batches."""

import csv
import io
import json
from collections.abc import Iterable
from typing import Any

from pydantic import ValidationError

from marketlab.trades.schemas import Trade

_FIELDS = tuple(Trade.model_fields)


class TradeParseError(ValueError):
    """Invalid input, with a one-based data-record index when available."""

    def __init__(self, message: str, *, record_index: int | None = None) -> None:
        self.record_index = record_index
        prefix = f"record {record_index}: " if record_index is not None else ""
        super().__init__(prefix + message)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TradeParseError("duplicate JSON object key")
        result[key] = value
    return result


def _validate_records(records: Iterable[object]) -> tuple[Trade, ...]:
    trades: list[Trade] = []
    seen: set[str] = set()
    for index, record in enumerate(records, start=1):
        try:
            trade = Trade.model_validate(record)
        except ValidationError as error:
            raise TradeParseError("invalid trade", record_index=index) from error
        if trade.trade_id in seen:
            raise TradeParseError("duplicate trade_id", record_index=index)
        seen.add(trade.trade_id)
        trades.append(trade)
    return tuple(trades)


def parse_trades_json(payload: str) -> tuple[Trade, ...]:
    """Parse a JSON array; decimal fields must be JSON strings."""
    try:
        records = json.loads(payload, object_pairs_hook=_unique_object)
    except json.JSONDecodeError as error:
        raise TradeParseError("invalid JSON") from error
    if not isinstance(records, list):
        raise TradeParseError("JSON root must be an array")
    return _validate_records(records)


def parse_trades_csv(payload: str) -> tuple[Trade, ...]:
    """Parse CSV with exactly the canonical headers, in any order."""
    reader = csv.reader(io.StringIO(payload, newline=""), strict=True)
    try:
        headers = next(reader, None)
        if headers is None or len(headers) != len(_FIELDS) or set(headers) != set(_FIELDS):
            raise TradeParseError("CSV must contain each canonical header exactly once")
        records: list[dict[str, str]] = []
        for index, values in enumerate(reader, start=1):
            if len(values) != len(headers):
                raise TradeParseError("CSV field count does not match headers", record_index=index)
            records.append(dict(zip(headers, values, strict=True)))
    except csv.Error as error:
        raise TradeParseError("invalid CSV quoting") from error
    return _validate_records(records)
