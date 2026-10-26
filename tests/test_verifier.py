"""Independent legacy-byte parity and complete strict native verification."""

import hashlib
import json
import threading
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import marketlab.datasets.normalize as module
from marketlab.datasets.normalize import (
    SCHEMA,
    VerificationCancelled,
    _canonical_records,
    _logical_record,
    _record_buffer,
    verify_parquet,
)
from marketlab.datasets.source import VENUE, DatasetError, file_hash

DAY = date(2025, 1, 1)
START = datetime(2025, 1, 1, tzinfo=UTC)
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def decimal(coefficient):
    with localcontext() as context:
        context.prec = 80
        return Decimal(coefficient).scaleb(-18)


def batch(coefficients=(1, 10, 100000000000, 10**18, 10**38 - 1), symbol="BTCUSDT"):
    rows = []
    for index, coefficient in enumerate(coefficients):
        rows.append(
            {
                "venue": VENUE,
                "symbol": symbol,
                "source_trade_id": index,
                "executed_at": START + timedelta(microseconds=index),
                "price": decimal(coefficient),
                "quantity": decimal(coefficient),
                "quote_quantity": decimal(coefficient),
                "is_buyer_maker": bool(index % 2),
                "is_best_match": bool((index + 1) % 2),
            }
        )
    return pa.RecordBatch.from_pylist(rows, schema=SCHEMA)


def legacy_bytes(value, symbol="BTCUSDT"):
    """Independent frozen old encoder, not the optimized production formatter."""
    result = bytearray()
    for item in value.to_pylist():
        timestamp = item["executed_at"]
        delta = timestamp - EPOCH
        micros = delta.days * 86400000000 + delta.seconds * 1000000 + delta.microseconds
        row = (
            item["source_trade_id"],
            micros,
            format(item["price"], ".18f"),
            format(item["quantity"], ".18f"),
            format(item["quote_quantity"], ".18f"),
            int(item["is_buyer_maker"]),
            int(item["is_best_match"]),
        )
        encoded = (json.dumps([VENUE, symbol, *row], separators=(",", ":")) + "\n").encode("ascii")
        assert _logical_record(row, symbol) == encoded  # Normalization writer stays unchanged.
        result.extend(encoded)
    return bytes(result)


def quality(path, value):
    timestamps = value.column(3).to_pylist()
    return {
        "parquet_sha256": file_hash(path),
        "parquet_bytes": path.stat().st_size,
        "accepted_rows": value.num_rows,
        "logical_sha256": hashlib.sha256(legacy_bytes(value)).hexdigest(),
        "observed_from": min(timestamps).isoformat().replace("+00:00", "Z") if timestamps else None,
        "observed_through": max(timestamps).isoformat().replace("+00:00", "Z")
        if timestamps
        else None,
    }


def replace(value, name, items):
    columns = list(value.columns)
    index = SCHEMA.get_field_index(name)
    columns[index] = pa.array(items, type=SCHEMA[index].type)
    return pa.RecordBatch.from_arrays(columns, schema=SCHEMA)


@settings(max_examples=50, deadline=None)
@given(st.lists(st.integers(min_value=1, max_value=10**38 - 1), min_size=1, max_size=50))
def test_native_exact_legacy_canonical_bytes(coefficients):
    value = batch(coefficients)
    assert bytes(_record_buffer(_canonical_records(value, "BTCUSDT"))) == legacy_bytes(value)


def test_decimal_input_and_record_output_offsets_and_unused_padding():
    value = batch(tuple(range(1, 25))).slice(3, 15)
    assert value.column(4).offset == 3
    records = _canonical_records(value, "BTCUSDT")
    sliced = records.slice(2, 7)
    assert bytes(_record_buffer(sliced)) == legacy_bytes(value.slice(2, 7))
    buffers = records.buffers()
    padded = pa.Array.from_buffers(
        pa.string(),
        len(records),
        [buffers[0], buffers[1], pa.py_buffer(bytes(buffers[2]) + b"NOT_LOGICAL_PADDING")],
    )
    assert bytes(_record_buffer(padded)) == legacy_bytes(value)
    assert (
        bytes(
            _record_buffer(
                pa.array(["before", "target", "after"], type=pa.large_string()).slice(1, 1)
            )
        )
        == b"target"
    )


def test_actual_file_complete_hash_matches_legacy(tmp_path):
    value = batch()
    path = tmp_path / "value.parquet"
    pq.write_table(pa.Table.from_batches([value]), path)
    verify_parquet(path, quality(path, value), symbol="BTCUSDT", trade_date=DAY)


@pytest.mark.parametrize("change", ["timezone", "unit", "decimal", "boolean", "order", "nullable"])
def test_exact_schema_and_timezone_rejected(tmp_path, change):
    value = batch()
    columns, fields = list(value.columns), list(SCHEMA)
    if change == "order":
        columns.reverse()
        fields.reverse()
    else:
        index, datatype = {
            "timezone": (3, pa.timestamp("us", tz="Europe/London")),
            "unit": (3, pa.timestamp("ms", tz="UTC")),
            "decimal": (4, pa.decimal128(38, 17)),
            "boolean": (7, pa.int8()),
            "nullable": (0, pa.string()),
        }[change]
        # Alternate decimal fixture has exactly representable values at the changed scale.
        if change == "decimal":
            columns[index] = pa.array([Decimal("1")] * len(value), type=datatype)
        else:
            columns[index] = columns[index].cast(datatype, safe=False)
        fields[index] = pa.field(fields[index].name, datatype, nullable=change == "nullable")
    path = tmp_path / "schema.parquet"
    pq.write_table(pa.Table.from_arrays(columns, schema=pa.schema(fields)), path)
    with pytest.raises(DatasetError, match="schema mismatch"):
        verify_parquet(
            path,
            {"parquet_sha256": file_hash(path), "parquet_bytes": path.stat().st_size},
            symbol="BTCUSDT",
            trade_date=DAY,
        )


def test_empty_file_retains_legacy_empty_hash_and_bounds(tmp_path):
    value = batch(())
    path = tmp_path / "empty.parquet"
    pq.write_table(pa.Table.from_batches([value]), path)
    verify_parquet(path, quality(path, value), symbol="BTCUSDT", trade_date=DAY)


def test_truncated_file_rejected_after_matching_physical_hash(tmp_path):
    value = batch()
    path = tmp_path / "truncated.parquet"
    pq.write_table(pa.Table.from_batches([value]), path)
    path.write_bytes(path.read_bytes()[:-8])
    with pytest.raises(DatasetError, match="verification failed"):
        verify_parquet(
            path,
            {"parquet_sha256": file_hash(path), "parquet_bytes": path.stat().st_size},
            symbol="BTCUSDT",
            trade_date=DAY,
        )


def test_real_physical_hash_cancel_checkpoint_prevents_parse(tmp_path, monkeypatch):
    path = tmp_path / "large-input"
    path.write_bytes(b"x" * (2 * 1024 * 1024))
    expected = {"parquet_sha256": file_hash(path), "parquet_bytes": path.stat().st_size}
    checks = 0

    def cancelled():
        nonlocal checks
        checks += 1
        return checks == 3  # Initial check, first chunk, then stop before the second chunk.

    def parse(_):
        pytest.fail("cancelled physical hash reached Parquet parsing")

    monkeypatch.setattr(pq, "ParquetFile", parse)
    with pytest.raises(VerificationCancelled):
        verify_parquet(path, expected, symbol="BTCUSDT", trade_date=DAY, cancelled=cancelled)
    assert checks == 3


def test_real_native_batch_cancel_checkpoint_prevents_success(tmp_path, monkeypatch):
    value = batch()
    path = tmp_path / "value.parquet"
    pq.write_table(pa.Table.from_batches([value]), path)
    expected = quality(path, value)
    stopped = threading.Event()
    original = module._canonical_records
    encoded = []

    def cancel_after_native(batch, symbol):
        records = original(batch, symbol)
        encoded.append(bytes(_record_buffer(records)))
        stopped.set()
        return records

    monkeypatch.setattr(module, "_canonical_records", cancel_after_native)
    with pytest.raises(VerificationCancelled):
        verify_parquet(path, expected, symbol="BTCUSDT", trade_date=DAY, cancelled=stopped.is_set)
    assert encoded == [legacy_bytes(value)]


@pytest.mark.parametrize("name", SCHEMA.names)
def test_actual_null_rejected_even_with_nonnullable_declared_schema(tmp_path, monkeypatch, name):
    value = batch()
    items = value.column(SCHEMA.get_field_index(name)).to_pylist()
    items[1] = None
    value = replace(value, name, items)
    path = tmp_path / "source"
    path.write_bytes(b"fixed read-only test input")

    class Parquet:
        schema_arrow = SCHEMA

        def iter_batches(self, **kwargs):
            yield value

        def close(self):
            pass

    monkeypatch.setattr(pq, "ParquetFile", lambda _: Parquet())
    with pytest.raises(DatasetError, match="content mismatch"):
        verify_parquet(
            path,
            {"parquet_sha256": file_hash(path), "parquet_bytes": path.stat().st_size},
            symbol="BTCUSDT",
            trade_date=DAY,
        )


@pytest.mark.parametrize(
    "name,items",
    [
        ("source_trade_id", [-1, 0, 1, 2, 3]),
        ("source_trade_id", [0, 1, 1, 2, 3]),
        ("source_trade_id", [0, 2, 1, 3, 4]),
        ("source_trade_id", [-(2**63), -1, 0, 1, 2]),
        ("venue", ["bad"] * 5),
        ("symbol", ["ETHUSDT"] * 5),
        ("executed_at", [START - timedelta(microseconds=1)] * 5),
        ("executed_at", [START + timedelta(days=1)] * 5),
        ("price", [decimal(0)] * 5),
        ("quantity", [decimal(-1)] * 5),
        ("quote_quantity", [Decimal("-0.000000000000000000")] * 5),
    ],
)
def test_retained_content_rejections(tmp_path, name, items):
    value = replace(batch(), name, items)
    path = tmp_path / "bad.parquet"
    pq.write_table(pa.Table.from_batches([value]), path)
    # Content must fail before aggregate reconciliation, independently of expected quality.
    with pytest.raises(DatasetError, match="content mismatch"):
        verify_parquet(
            path,
            {"parquet_sha256": file_hash(path), "parquet_bytes": path.stat().st_size},
            symbol="BTCUSDT",
            trade_date=DAY,
        )


def test_int64_max_and_16384_row_boundary_ordering(tmp_path):
    value = batch((10**18,) * 16385)
    identifiers = list(range(16384)) + [2**63 - 1]
    value = replace(value, "source_trade_id", identifiers)
    path = tmp_path / "valid.parquet"
    pq.write_table(pa.Table.from_batches([value]), path, row_group_size=16384)
    verify_parquet(path, quality(path, value), symbol="BTCUSDT", trade_date=DAY)
    identifiers[-1] = identifiers[-2]
    invalid = replace(value, "source_trade_id", identifiers)
    pq.write_table(pa.Table.from_batches([invalid]), path, row_group_size=16384)
    with pytest.raises(DatasetError, match="content mismatch"):
        verify_parquet(
            path,
            {"parquet_sha256": file_hash(path), "parquet_bytes": path.stat().st_size},
            symbol="BTCUSDT",
            trade_date=DAY,
        )


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("accepted_rows", 999),
        ("logical_sha256", "a" * 64),
        ("observed_from", "2025-01-01T00:00:01Z"),
        ("observed_through", None),
        ("parquet_sha256", "b" * 64),
        ("parquet_bytes", 0),
    ],
)
def test_every_aggregate_hash_count_size_bounds_check_retained(tmp_path, field, replacement):
    value = batch()
    path = tmp_path / "value.parquet"
    pq.write_table(pa.Table.from_batches([value]), path)
    expected = quality(path, value)
    expected[field] = replacement
    with pytest.raises(DatasetError):
        verify_parquet(path, expected, symbol="BTCUSDT", trade_date=DAY)
