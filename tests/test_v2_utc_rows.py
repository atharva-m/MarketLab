"""Exact UTC microseconds and control serialization across local DB timezones."""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pyarrow as pa
import pytest

from marketlab.datasets.v2.common import V2Error
from marketlab.datasets.v2.core import wire
from marketlab.datasets.v2.normalize import COLUMNS, INPUT_TYPES, python_rows


def test_wire_normalizes_datetime_preserves_date_and_exact_values() -> None:
    instant = datetime(2025, 3, 1, 0, 0, 0, 123456, tzinfo=UTC)
    local = instant.astimezone(timezone(timedelta(hours=-10)))
    assert wire(local) == wire(instant) == "2025-03-01T00:00:00.123456Z"
    assert wire(date(2025, 3, 1)) == "2025-03-01"
    assert wire({"nested": [local], "count": 2**63 - 1}) == {
        "nested": ["2025-03-01T00:00:00.123456Z"],
        "count": 2**63 - 1,
    }


@pytest.mark.parametrize(
    "instant",
    [
        datetime(1970, 1, 1, tzinfo=UTC),
        datetime(2025, 3, 1, 23, 59, 59, 999999, tzinfo=UTC),
        datetime(9999, 12, 30, 23, 59, 59, 999999, tzinfo=UTC),
    ],
)
def test_integer_microsecond_row_conversion_preserves_all_values(instant: datetime) -> None:
    row = ["10", instant, Decimal("1.25"), Decimal("2"), Decimal("2.51"), True, None]
    schema = pa.schema(
        [pa.field(name, kind) for name, kind in zip(COLUMNS, INPUT_TYPES, strict=True)]
    )
    batch = pa.RecordBatch.from_pylist([dict(zip(COLUMNS, row, strict=True))], schema=schema)
    assert python_rows(batch) == [dict(zip(COLUMNS, row, strict=True))]
    assert python_rows(batch) == batch.to_pylist()


@pytest.mark.parametrize(
    "kind",
    [pa.timestamp("ns", tz="UTC"), pa.timestamp("us"), pa.timestamp("us", tz="Asia/Kolkata")],
)
def test_timestamp_type_must_still_be_exact(kind: Any) -> None:
    batch = pa.record_batch([pa.array([1], type=kind)], names=["executed_at"])
    with pytest.raises(V2Error):
        python_rows(batch)


@pytest.mark.parametrize("micros", [None, 2**63 - 1, -(2**63)])
def test_null_or_out_of_datetime_range_rejected(micros: int | None) -> None:
    array = pa.array([micros], type=pa.int64()).cast(pa.timestamp("us", tz="UTC"))
    batch = pa.record_batch([array], names=["executed_at"])
    with pytest.raises(V2Error):
        python_rows(batch)


@pytest.mark.parametrize("micros", [-1, 0, 1, 86400000000 - 1, 86400000000])
def test_signed_microsecond_and_exact_day_boundaries(micros: int) -> None:
    from marketlab.datasets.v2.normalize import EPOCH, day_bounds, timestamp

    batch = pa.record_batch(
        [pa.array([micros], type=pa.int64()).cast(pa.timestamp("us", tz="UTC"))],
        names=["executed_at"],
    )
    instant = python_rows(batch)[0]["executed_at"]
    assert instant == EPOCH + timedelta(microseconds=micros)
    if 0 <= micros < 86400000000:
        assert timestamp(instant, "arrow_timestamp_us_utc", day_bounds(date(1970, 1, 1))) == micros
    else:
        with pytest.raises(V2Error):
            timestamp(instant, "arrow_timestamp_us_utc", day_bounds(date(1970, 1, 1)))
