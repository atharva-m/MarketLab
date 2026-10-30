"""Exact equivalence of independent UTC timestamp decoding and original oracle outputs."""

import importlib.util
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest


@pytest.fixture
def harness():
    path = Path(__file__).resolve().parents[1] / "scripts/v2_phase3_acceptance.py"
    specification = importlib.util.spec_from_file_location("phase3_oracle_timestamp_test", path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def table():
    first = datetime(2025, 3, 1, tzinfo=UTC)
    # Same microsecond with numeric 2/10 IDs, minute and five-minute edges,
    # and both day boundaries are intentionally supplied out of order.
    instants = [
        first + timedelta(microseconds=1),
        first + timedelta(microseconds=1),
        first - timedelta(microseconds=1),
        first + timedelta(minutes=1) - timedelta(microseconds=1),
        first + timedelta(minutes=1),
        first + timedelta(minutes=5) - timedelta(microseconds=1),
        first + timedelta(minutes=5),
        first + timedelta(days=1) - timedelta(microseconds=1),
        first + timedelta(days=1),
    ]
    identifiers = ["10", "2", "1", "3", "4", "5", "6", "7", "8"]
    schema = pa.schema(
        [
            pa.field("source_trade_id", pa.string()),
            pa.field("executed_at", pa.timestamp("us", tz="UTC")),
            *[pa.field(k, pa.decimal128(38, 18)) for k in ("price", "quantity", "quote_quantity")],
            pa.field("is_buyer_maker", pa.bool_()),
            pa.field("is_best_match", pa.bool_()),
        ]
    )
    return pa.Table.from_pylist(
        [
            {
                "source_trade_id": identifier,
                "executed_at": instant,
                "price": Decimal(str(index + 1) + ".123456789012345678"),
                "quantity": Decimal("0.000000010000000001"),
                "quote_quantity": Decimal("1.000000000000000009"),
                "is_buyer_maker": True,
                "is_best_match": None,
            }
            for index, (identifier, instant) in enumerate(zip(identifiers, instants, strict=True))
        ],
        schema=schema,
    )


def test_all_timestamp_and_decimal_values_equal_original_arrow_conversion(harness):
    for batch in table().to_batches(max_chunksize=3):
        original = batch.to_pylist()
        converted = list(harness.oracle_rows(batch))
        assert converted == original
        assert all(
            type(r["executed_at"]) is datetime and r["executed_at"].tzinfo is UTC for r in converted
        )
        assert all(
            r["executed_at"].microsecond == o["executed_at"].microsecond
            for r, o in zip(converted, original, strict=True)
        )


@pytest.mark.parametrize(
    "first_offset,end_offset",
    [
        (timedelta(0), timedelta(days=1)),
        (timedelta(minutes=1), timedelta(minutes=5)),
        (timedelta(microseconds=1), timedelta(minutes=5, microseconds=1)),
    ],
)
def test_full_1m_5m_outputs_equal_original_with_ties_boundaries_and_filtering(
    harness, tmp_path, monkeypatch, first_offset, end_offset
):
    path = tmp_path / "bounded.parquet"
    pq.write_table(table(), path, row_group_size=3)
    first = datetime(2025, 3, 1, tzinfo=UTC)
    optimized = harness.oracle_bars(path, first + first_offset, first + end_offset)
    monkeypatch.setattr(harness, "oracle_rows", lambda batch: batch.to_pylist())
    original = harness.oracle_bars(path, first + first_offset, first + end_offset)
    assert optimized == original
    assert set(optimized) == {"1m", "5m"}
    if first_offset == timedelta(0):
        assert sum(b["trade_count"] for b in optimized["1m"]) == 7
        # ID 2 opens and ID 10 closes the exact timestamp tie before the later row.
        assert optimized["1m"][0]["open"] == "2.123456789012345678"


@pytest.mark.parametrize(
    "kind",
    [
        pa.timestamp("ms", tz="UTC"),
        pa.timestamp("us"),
        pa.timestamp("us", tz="Europe/London"),
        pa.int64(),
    ],
)
def test_oracle_rejects_noncanonical_timestamp_types(harness, kind):
    batch = pa.record_batch([pa.array([0], type=kind)], names=["executed_at"])
    with pytest.raises(ValueError, match="exact UTC microsecond"):
        list(harness.oracle_rows(batch))


def test_oracle_rejects_null_timestamp(harness):
    batch = pa.record_batch(
        [pa.array([None], type=pa.timestamp("us", tz="UTC"))], names=["executed_at"]
    )
    with pytest.raises(ValueError, match="non-null"):
        list(harness.oracle_rows(batch))
