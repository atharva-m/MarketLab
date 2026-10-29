"""Ordinary Parquet page structural limits precede Arrow data decoding."""

import io
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from marketlab.datasets.v2.common import DEFAULT_LIMITS, V2Error
from marketlab.datasets.v2.normalize import COLUMNS, INPUT_TYPES, checked_parquet
from marketlab.datasets.v2.parquet_bounds import _Compact, validate_pages


@pytest.mark.parametrize("version", ["1.0", "2.0"])
@pytest.mark.parametrize("dictionary", [False, True])
@pytest.mark.parametrize("compression", [None, "zstd"])
def test_valid_page_encodings(
    version: str, dictionary: bool, compression: str | None, tmp_path: Path
) -> None:
    row = [
        "2",
        datetime(2025, 3, 1, tzinfo=UTC),
        Decimal("1.25"),
        Decimal("2"),
        Decimal("2.51"),
        True,
        None,
    ]
    schema = pa.schema([pa.field(n, t) for n, t in zip(COLUMNS, INPUT_TYPES, strict=True)])
    path = tmp_path / "valid.parquet"
    pq.write_table(
        pa.Table.from_pylist([dict(zip(COLUMNS, row, strict=True))], schema=schema),
        path,
        compression=compression,
        use_dictionary=dictionary,
        data_page_version=version,
    )
    parquet = checked_parquet(path, COLUMNS, INPUT_TYPES, DEFAULT_LIMITS)
    try:
        assert parquet.read().num_rows == 1
    finally:
        parquet.close()


def test_page_declared_size_rejected_before_data_decode(tmp_path: Path) -> None:
    # Small ordinary structural fixture: page says64bytes, column declares16.
    # Compact field headers: type0, uncompressed64, compressed0, stop.
    path = tmp_path / "declarations.bin"
    path.write_bytes(b"PAR1" + bytes([0x15, 0, 0x15, 0x80, 1, 0x15, 0, 0]))
    column = SimpleNamespace(
        data_page_offset=4,
        dictionary_page_offset=None,
        total_compressed_size=8,
        total_uncompressed_size=16,
        num_values=1,
        compression="UNCOMPRESSED",
    )
    group = SimpleNamespace(
        num_columns=1, num_rows=1, total_byte_size=16, column=lambda index: column
    )
    metadata = SimpleNamespace(num_rows=1, num_row_groups=1, row_group=lambda index: group)
    with pytest.raises(V2Error):
        validate_pages(path, metadata, path.stat().st_size, 64)


def test_compact_header_bounds() -> None:
    with pytest.raises(V2Error):
        _Compact(io.BytesIO(bytes([0x18, 0xFF, 0xFF, 0xFF, 0x7F])), 5).structure()
    with pytest.raises(V2Error):
        _Compact(io.BytesIO(bytes([0x15]) + bytes([0xFF]) * 11), 12).structure()
    with pytest.raises(V2Error):
        _Compact(io.BytesIO(bytes([0x1C]) * 20), 20).structure()


def test_retained_resource_regression_rejected_in_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = Path(__file__).resolve().parents[1] / "artifacts/v2-phase2-20261028/page-forged.parquet"
    if not path.exists():
        pytest.skip("local retained resource fixture is intentionally excluded from Git")
    calls = []

    def decode_forbidden(*args: Any, **kwargs: Any) -> Any:
        calls.append(True)
        raise AssertionError("decoder must not be reached")

    monkeypatch.setattr(pq.ParquetFile, "iter_batches", decode_forbidden)
    with pytest.raises(V2Error) as error:
        checked_parquet(path, COLUMNS, INPUT_TYPES, DEFAULT_LIMITS)
    assert error.value.__cause__ is None
    assert not calls


@pytest.mark.parametrize("column_rows,total_rows", [(2, 1), (1, 2)])
def test_flat_column_and_footer_count_consistency(
    tmp_path: Path, column_rows: int, total_rows: int
) -> None:
    row = [
        "2",
        datetime(2025, 3, 1, tzinfo=UTC),
        Decimal("1"),
        Decimal("1"),
        Decimal("1"),
        True,
        None,
    ]
    schema = pa.schema([pa.field(n, t) for n, t in zip(COLUMNS, INPUT_TYPES, strict=True)])
    path = tmp_path / "counts.parquet"
    pq.write_table(
        pa.Table.from_pylist([dict(zip(COLUMNS, row, strict=True))], schema=schema), path
    )
    with pq.ParquetFile(path) as original:
        group = original.metadata.row_group(0)
        columns = []
        for index in range(group.num_columns):
            column = group.column(index)
            columns.append(
                SimpleNamespace(
                    data_page_offset=column.data_page_offset,
                    dictionary_page_offset=column.dictionary_page_offset,
                    total_compressed_size=column.total_compressed_size,
                    total_uncompressed_size=column.total_uncompressed_size,
                    num_values=column_rows,
                    compression=column.compression,
                )
            )
        altered_group = SimpleNamespace(
            num_columns=group.num_columns,
            num_rows=1,
            total_byte_size=group.total_byte_size,
            column=lambda index: columns[index],
        )
        metadata = SimpleNamespace(
            num_row_groups=1, num_rows=total_rows, row_group=lambda index: altered_group
        )
        with pytest.raises(V2Error):
            validate_pages(path, metadata, path.stat().st_size, 64 * 1024**2)


def test_page_scan_cancellation_between_headers(tmp_path: Path) -> None:
    row = [
        "2",
        datetime(2025, 3, 1, tzinfo=UTC),
        Decimal("1"),
        Decimal("1"),
        Decimal("1"),
        True,
        None,
    ]
    schema = pa.schema([pa.field(n, t) for n, t in zip(COLUMNS, INPUT_TYPES, strict=True)])
    path = tmp_path / "cancel.parquet"
    pq.write_table(
        pa.Table.from_pylist([dict(zip(COLUMNS, row, strict=True))], schema=schema), path
    )
    calls = []

    def cancelled() -> bool:
        calls.append(True)
        return len(calls) > 4

    with pytest.raises(V2Error) as error:
        checked_parquet(path, COLUMNS, INPUT_TYPES, DEFAULT_LIMITS, cancelled=cancelled)
    assert error.value.code == "cancelled" and len(calls) > 4
