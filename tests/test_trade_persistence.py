import csv
import io
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from marketlab.trades import (
    DuplicateTradeError,
    Trade,
    TradeParseError,
    get_trade,
    import_trades_csv,
    import_trades_json,
    synthetic_trades,
)

Importer = Callable[[Engine, str], int]


def _json(records: list[dict[str, object]]) -> str:
    return json.dumps(records)


def _csv(records: list[dict[str, object]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(Trade.model_fields))
    writer.writeheader()
    writer.writerows(records)
    return output.getvalue()


@pytest.fixture(params=[(import_trades_json, _json), (import_trades_csv, _csv)])
def batch_format(request: pytest.FixtureRequest) -> tuple[Importer, Callable[..., str]]:
    return request.param


def test_empty_batch_never_connects(batch_format: tuple[Importer, Callable[..., str]]) -> None:
    importer, serialize = batch_format
    engine = Mock(spec=Engine)
    assert importer(engine, serialize([])) == 0
    assert engine.mock_calls == []


def test_invalid_batch_never_connects(batch_format: tuple[Importer, Callable[..., str]]) -> None:
    importer, serialize = batch_format
    engine = Mock(spec=Engine)
    records = [trade.model_dump(mode="json") for trade in synthetic_trades(2)]
    records[1]["price"] = "-1"
    with pytest.raises(TradeParseError) as caught:
        importer(engine, serialize(records))
    assert caught.value.record_index == 2
    assert engine.mock_calls == []


@pytest.mark.integration
def test_exact_round_trip(
    trade_engine: Engine, batch_format: tuple[Importer, Callable[..., str]]
) -> None:
    importer, serialize = batch_format
    expected = Trade(
        trade_id="SYN-Exact.Case:1",
        symbol="SYN.A",
        executed_at=datetime(
            2025, 1, 2, 23, 59, 59, 123456, tzinfo=timezone(-timedelta(hours=5, minutes=30))
        ),
        price=Decimal("999999999999.99999999"),
        quantity=Decimal("0.00000001"),
    )
    record = expected.model_dump(mode="json")
    record["executed_at"] = "2025-01-02T23:59:59.123456-05:30"
    assert importer(trade_engine, serialize([record])) == 1
    actual = get_trade(trade_engine, expected.trade_id)
    assert actual == expected
    assert actual is not None
    assert isinstance(actual.price, Decimal)
    assert isinstance(actual.quantity, Decimal)
    assert actual.executed_at.tzinfo is UTC
    assert actual.executed_at.microsecond == 123456
    assert get_trade(trade_engine, expected.trade_id.lower()) is None
    assert get_trade(trade_engine, "SYN-missing") is None
    assert get_trade(trade_engine, "' OR 1=1 --") is None


@pytest.mark.integration
@pytest.mark.parametrize("duplicate_index", [0, 1, 2])
def test_duplicate_rolls_back_entire_batch(
    trade_engine: Engine,
    batch_format: tuple[Importer, Callable[..., str]],
    duplicate_index: int,
) -> None:
    importer, serialize = batch_format
    expected = synthetic_trades(3, seed=73)
    stored = expected[duplicate_index]
    # Start with JSON to also exercise cross-format conflicts for CSV imports.
    assert import_trades_json(trade_engine, _json([stored.model_dump(mode="json")])) == 1
    records = [trade.model_dump(mode="json") for trade in expected]
    records[duplicate_index]["price"] = "1.25"
    with pytest.raises(DuplicateTradeError):
        importer(trade_engine, serialize(records))
    for trade in expected:
        assert get_trade(trade_engine, trade.trade_id) == (stored if trade == stored else None)
    # A failed transaction must leave the service usable for later imports.
    remaining = [record for record in records if record["trade_id"] != stored.trade_id]
    assert importer(trade_engine, serialize(remaining)) == 2
    assert all(get_trade(trade_engine, trade.trade_id) == trade for trade in expected)


@pytest.mark.integration
@pytest.mark.parametrize("failure", ["invalid", "duplicate"])
def test_invalid_batch_preserves_database(
    trade_engine: Engine,
    batch_format: tuple[Importer, Callable[..., str]],
    failure: str,
) -> None:
    importer, serialize = batch_format
    existing, fresh = synthetic_trades(2, seed=92)
    assert importer(trade_engine, serialize([existing.model_dump(mode="json")])) == 1
    records = [fresh.model_dump(mode="json"), fresh.model_dump(mode="json")]
    if failure == "invalid":
        records[1]["quantity"] = "0"
    with pytest.raises(TradeParseError):
        importer(trade_engine, serialize(records))
    assert get_trade(trade_engine, existing.trade_id) == existing
    assert get_trade(trade_engine, fresh.trade_id) is None
    assert importer(trade_engine, serialize([])) == 0
    assert get_trade(trade_engine, existing.trade_id) == existing


@pytest.mark.integration
@pytest.mark.parametrize("db_timezone", ["Pacific/Honolulu", "Pacific/Kiritimati"])
@pytest.mark.parametrize(
    "instant",
    [datetime(1, 1, 1, tzinfo=UTC), datetime(9999, 12, 31, 23, 59, 59, 999999, tzinfo=UTC)],
)
def test_timestamp_boundaries_and_session_timezone(
    trade_engine: Engine,
    batch_format: tuple[Importer, Callable[..., str]],
    db_timezone: str,
    instant: datetime,
) -> None:
    importer, serialize = batch_format
    expected = Trade(
        trade_id="SYN-time-boundary",
        symbol="SYN.A",
        executed_at=instant,
        price=Decimal("1"),
        quantity=Decimal("1"),
    )
    with trade_engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('TimeZone', :zone, false)"), {"zone": db_timezone}
        )
    assert importer(trade_engine, serialize([expected.model_dump(mode="json")])) == 1
    assert get_trade(trade_engine, expected.trade_id) == expected
    # A pooled connection retains the caller's original session setting after lookup.
    with trade_engine.connect() as connection:
        assert connection.execute(text("SHOW TIME ZONE")).scalar_one() == db_timezone
