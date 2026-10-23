import csv
import io
import json
import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from marketlab.trades import (
    Trade,
    TradeParseError,
    parse_trades_csv,
    parse_trades_json,
    synthetic_trades,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "trades"
_HEADERS = "trade_id,symbol,executed_at,price,quantity"


@pytest.fixture
def record() -> dict[str, str]:
    return {
        "trade_id": "SYN-1",
        "symbol": "SYN.A",
        "executed_at": "2025-01-02T09:30:00.123456-05:00",
        "price": "123.12345678",
        "quantity": "0.00000001",
    }


def _csv(records: list[dict[str, object]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=_HEADERS.split(","))
    writer.writeheader()
    writer.writerows(records)
    return output.getvalue()


def test_golden_synthetic_inputs_match_both_parsers() -> None:
    expected = synthetic_trades(3, seed=42)
    from_json = parse_trades_json((_FIXTURES / "valid.json").read_text(encoding="utf-8"))
    from_csv = parse_trades_csv((_FIXTURES / "valid.csv").read_text(encoding="utf-8"))
    assert from_json == from_csv == expected
    assert expected[0].price == Decimal("146.92")
    assert expected[0].quantity == Decimal("0.410")


def test_exact_values_utc_normalization_and_json_round_trip(record: dict[str, str]) -> None:
    trade = Trade.model_validate(record)
    assert trade.executed_at == datetime(2025, 1, 2, 14, 30, 0, 123456, tzinfo=UTC)
    assert trade.executed_at.tzinfo is UTC
    assert trade.price == Decimal("123.12345678")
    assert trade.quantity == Decimal("0.00000001")
    assert Trade.model_validate_json(trade.model_dump_json()) == trade
    assert isinstance(trade.model_dump(mode="json")["price"], str)
    with pytest.raises(ValidationError):
        trade.price = Decimal("1")


def test_native_decimal_and_aware_datetime_are_accepted(record: dict[str, str]) -> None:
    trade = Trade.model_validate(
        {
            **record,
            "executed_at": datetime(2025, 1, 2, tzinfo=timezone(timedelta(hours=2))),
            "price": Decimal("999999999999.99999999"),
        }
    )
    assert trade.price == Decimal("999999999999.99999999")
    assert trade.executed_at == datetime(2025, 1, 1, 22, tzinfo=UTC)


@pytest.mark.parametrize("field", ["price", "quantity"])
@pytest.mark.parametrize(
    "value",
    [
        "0",
        "-1",
        "NaN",
        "Infinity",
        "-Infinity",
        "1e2",
        "1,000",
        " 1",
        "1 ",
        "+1",
        ".1",
        "1.",
        "01",
        "١",
        "1.000000001",
        "1000000000000",
        "",
        None,
        1,
        1.5,
        True,
        False,
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-1"),
        Decimal("0"),
        Decimal("0.000000001"),
        Decimal("1.000000000"),
        Decimal("1000000000000"),
    ],
)
def test_decimal_contract_rejects_invalid_or_lossy_values(
    record: dict[str, str], field: str, value: object
) -> None:
    with pytest.raises(ValidationError):
        Trade.model_validate({**record, field: value})


@pytest.mark.parametrize(
    "value",
    [
        "2025-01-02",
        "2025-01-02T14:30:00",
        "2025-01-02 14:30:00Z",
        "2025-01-02T14:30:00.1234567Z",
        "2025-02-30T14:30:00Z",
        "2025-01-02T14:30:60Z",
        "2025-01-02T14:30:00+24:00",
        "2025-01-02T14:30:00+01:60",
        "2025-01-02T14:30:00-00:99",
        "0001-01-01T00:00:00+01:00",
        "9999-12-31T23:59:59-01:00",
        "not-a-time",
        "",
        0,
        1735828200,
        None,
        datetime(2025, 1, 2),
    ],
)
def test_timestamp_contract_rejects_naive_invalid_and_overflow_values(
    record: dict[str, str], value: object
) -> None:
    with pytest.raises(ValidationError):
        Trade.model_validate({**record, "executed_at": value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("trade_id", ""),
        ("trade_id", " has-space"),
        ("trade_id", "x" * 65),
        ("trade_id", 1),
        ("trade_id", "id\n"),
        ("symbol", "syn"),
        ("symbol", "SYN A"),
        ("symbol", "ＡＢＣ"),
        ("symbol", "A" * 21),
        ("symbol", ""),
    ],
)
def test_identifier_contract_rejects_ambiguous_values(
    record: dict[str, str], field: str, value: object
) -> None:
    with pytest.raises(ValidationError):
        Trade.model_validate({**record, field: value})


@pytest.mark.parametrize("field", ["trade_id", "symbol", "executed_at", "price", "quantity"])
def test_all_fields_are_required(record: dict[str, str], field: str) -> None:
    del record[field]
    with pytest.raises(ValidationError):
        Trade.model_validate(record)


def test_unknown_fields_are_rejected(record: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        Trade.model_validate({**record, "provider": "unrecognized"})


@pytest.mark.parametrize("payload", ["", "[", "[] trailing", "{}", "null", "1", '"text"'])
def test_json_rejects_invalid_syntax_and_root(payload: str) -> None:
    with pytest.raises(TradeParseError):
        parse_trades_json(payload)


def test_json_rejects_duplicate_keys_before_data_is_lost(record: dict[str, str]) -> None:
    encoded = json.dumps(record).replace('"price":', '"price":"1", "price":')
    with pytest.raises(TradeParseError, match="duplicate JSON object key"):
        parse_trades_json(f"[{encoded}]")


@pytest.mark.parametrize("invalid_record", [None, [], 1, "text", {"trade_id": "missing"}])
def test_json_rejects_invalid_records_with_their_index(
    record: dict[str, str], invalid_record: object
) -> None:
    with pytest.raises(TradeParseError) as caught:
        parse_trades_json(json.dumps([record, invalid_record]))
    assert caught.value.record_index == 2
    assert isinstance(caught.value.__cause__, ValidationError)


def test_json_numbers_do_not_silently_lose_decimal_precision(record: dict[str, str]) -> None:
    with pytest.raises(TradeParseError):
        parse_trades_json(json.dumps([{**record, "price": 123.12345678}]))


@pytest.mark.parametrize("offset", ["+00:99", "-00:60", "+24:00", "-24:00"])
@pytest.mark.parametrize("parser", [parse_trades_json, parse_trades_csv])
def test_parsers_reject_invalid_timezone_offsets(
    record: dict[str, str], offset: str, parser: Callable[[str], tuple[Trade, ...]]
) -> None:
    records = [{**record, "executed_at": f"2025-01-02T14:30:00{offset}"}]
    payload = json.dumps(records) if parser is parse_trades_json else _csv(records)
    with pytest.raises(TradeParseError) as caught:
        parser(payload)
    assert caught.value.record_index == 1
    assert isinstance(caught.value.__cause__, ValidationError)


@pytest.mark.parametrize("parser", [parse_trades_json, parse_trades_csv])
def test_batch_duplicate_ids_are_rejected(
    record: dict[str, str], parser: Callable[[str], tuple[Trade, ...]]
) -> None:
    records = [record, {**record, "price": "1"}]
    payload = json.dumps(records) if parser is parse_trades_json else _csv(records)
    with pytest.raises(TradeParseError, match="duplicate trade_id") as caught:
        parser(payload)
    assert caught.value.record_index == 2


def test_csv_accepts_reordered_headers_quotes_and_crlf(record: dict[str, str]) -> None:
    headers = list(reversed(record))
    payload = ",".join(headers) + "\r\n" + ",".join(f'"{record[h]}"' for h in headers) + "\r\n"
    assert parse_trades_csv(payload) == (Trade.model_validate(record),)


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "\n",
        "trade_id,symbol",
        _HEADERS + ",extra",
        _HEADERS.replace("symbol", "trade_id"),
        _HEADERS.replace("quantity", "Quantity"),
        _HEADERS + "\n\n",
        _HEADERS + "\na,b",
        _HEADERS + "\na,b,c,d,e,f",
        _HEADERS + '\n"unterminated',
    ],
)
def test_csv_rejects_invalid_headers_rows_and_quoting(payload: str) -> None:
    with pytest.raises(TradeParseError):
        parse_trades_csv(payload)


def test_csv_uses_schema_validation_and_reports_record_index(record: dict[str, str]) -> None:
    with pytest.raises(TradeParseError) as caught:
        parse_trades_csv(_csv([record, {**record, "trade_id": "second", "quantity": "-1"}]))
    assert caught.value.record_index == 2
    assert isinstance(caught.value.__cause__, ValidationError)


def test_empty_batches_are_valid() -> None:
    assert parse_trades_json("[]") == ()
    assert parse_trades_csv(_HEADERS) == ()
    assert synthetic_trades(0) == ()


def test_synthetic_trades_are_repeatable_without_mutating_global_rng() -> None:
    global_state = random.getstate()
    trades = synthetic_trades(100, seed=42)
    assert trades == synthetic_trades(100, seed=42)
    assert trades[:3] == synthetic_trades(3, seed=42)
    assert trades != synthetic_trades(100, seed=43)
    assert random.getstate() == global_state
    assert len({trade.trade_id for trade in trades}) == len(trades)
    assert all(a.executed_at < b.executed_at for a, b in zip(trades, trades[1:], strict=False))


def test_synthetic_values_are_independent_of_decimal_context() -> None:
    expected = synthetic_trades(3, seed=42)
    with localcontext() as context:
        context.prec = 2
        assert synthetic_trades(3, seed=42) == expected


@pytest.mark.parametrize(
    ("count", "seed"), [(-1, 0), (True, 0), (1.5, 0), (1, -1), (1, True), (1, 2**32)]
)
def test_synthetic_inputs_are_validated(count: int, seed: int) -> None:
    with pytest.raises(ValueError):
        synthetic_trades(count, seed=seed)


@given(
    price=st.integers(min_value=1, max_value=999_999_999_999_999_999_99),
    quantity=st.integers(min_value=1, max_value=999_999_999_999_999_999_99),
    offset_minutes=st.integers(min_value=-1439, max_value=1439),
)
def test_parsers_preserve_exact_values_and_instants(
    price: int, quantity: int, offset_minutes: int
) -> None:
    def decimal_text(units: int) -> str:
        whole, fraction = divmod(units, 100_000_000)
        return f"{whole}.{fraction:08d}"

    instant = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    record = {
        "trade_id": "PROPERTY-1",
        "symbol": "SYN.A",
        "executed_at": instant.astimezone(timezone(timedelta(minutes=offset_minutes))).isoformat(),
        "price": decimal_text(price),
        "quantity": decimal_text(quantity),
    }
    (json_trade,) = parse_trades_json(json.dumps([record]))
    (csv_trade,) = parse_trades_csv(_csv([record]))
    assert json_trade == csv_trade
    assert json_trade.price == Decimal(record["price"])
    assert json_trade.quantity == Decimal(record["quantity"])
    assert json_trade.executed_at == instant
