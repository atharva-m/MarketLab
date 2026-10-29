"""Strict streamed v2 canonical/official normalization with disk-backed identity checks."""

import csv
import hashlib
import io
import json
import re
import sqlite3
import stat
import struct
import zipfile
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from typing import IO, Any, BinaryIO

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from .common import DEFAULT_LIMITS, Limits, V2Error, date_value, utc_text
from .source import check_cancelled, checked_hash

COLUMNS = [
    "source_trade_id",
    "executed_at",
    "price",
    "quantity",
    "quote_quantity",
    "is_buyer_maker",
    "is_best_match",
]
INPUT_TYPES = [
    pa.string(),
    pa.timestamp("us", tz="UTC"),
    *[pa.decimal128(38, 18)] * 3,
    pa.bool_(),
    pa.bool_(),
]
SCHEMA = pa.schema(
    [
        pa.field("instrument_id", pa.string(), nullable=False),
        *[
            pa.field(name, kind, nullable=name in {"is_buyer_maker", "is_best_match"})
            for name, kind in zip(COLUMNS, INPUT_TYPES, strict=True)
        ],
    ]
)
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
INTEGER = re.compile(r"(?:0|[1-9][0-9]{0,18})", re.ASCII)
DECIMAL = re.compile(r"[0-9]{1,20}(?:\.[0-9]{1,18})?", re.ASCII)
RFC3339 = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", re.ASCII)


def integer(value: object) -> int:
    if not isinstance(value, str) or INTEGER.fullmatch(value) is None or int(value) > 2**63 - 1:
        raise V2Error("invalid_request", "Invalid numeric source identifier")
    return int(value)


def decimal_text(value: object) -> str:
    if not isinstance(value, str) or DECIMAL.fullmatch(value) is None or Decimal(value) <= 0:
        raise V2Error("invalid_request", "Invalid exact decimal")
    with localcontext() as ctx:
        ctx.prec = 38
        return format(Decimal(value), ".18f")


def day_bounds(day: date) -> tuple[int, int]:
    start = datetime.combine(day, datetime.min.time(), UTC) - EPOCH
    micros = (start.days * 86400 + start.seconds) * 1000000 + start.microseconds
    return micros, micros + 86400000000


def timestamp(value: object, encoding: str, bounds: tuple[int, int]) -> int:
    try:
        if encoding == "arrow_timestamp_us_utc":
            if (
                not isinstance(value, datetime)
                or value.tzinfo is None
                or value.utcoffset() != timedelta(0)
            ):
                raise ValueError
            delta = value - EPOCH
            result = (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds
        elif encoding == "rfc3339_utc":
            if not isinstance(value, str) or RFC3339.fullmatch(value) is None:
                raise ValueError
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            delta = parsed - EPOCH
            result = (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds
        else:
            scale = {
                "unix_seconds": 1000000,
                "unix_milliseconds": 1000,
                "unix_microseconds": 1,
            }.get(encoding)
            if scale is None:
                raise ValueError
            result = integer(value) * scale
    except (ValueError, OverflowError, TypeError) as error:
        raise V2Error("invalid_request", "Invalid exact UTC timestamp") from error
    if not bounds[0] <= result < bounds[1]:
        raise V2Error("invalid_request", "Timestamp outside declared UTC day")
    return result


def logical_row(instrument_id: str, row: tuple[Any, ...]) -> bytes:
    value = [
        instrument_id,
        str(row[0]),
        utc_text(EPOCH + timedelta(microseconds=row[1])),
        row[2],
        row[3],
        row[4],
        None if row[5] is None else bool(row[5]),
        None if row[6] is None else bool(row[6]),
    ]
    return (json.dumps(value, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")


def python_rows(batch: Any) -> list[dict[str, Any]]:
    """Preserve UTC microseconds without optional per-scalar timezone imports."""
    position = batch.schema.get_field_index("executed_at")
    if position < 0 or batch.schema.field(position).type != pa.timestamp("us", tz="UTC"):
        raise V2Error("invalid_request", "Exact UTC microsecond timestamp required")
    instants = batch.column(position).cast(pa.int64()).to_pylist()
    records: list[dict[str, Any]] = batch.remove_column(position).to_pylist()
    for record, micros in zip(records, instants, strict=True):
        if type(micros) is not int:
            raise V2Error("invalid_request", "Null timestamp is unsupported")
        try:
            record["executed_at"] = EPOCH + timedelta(microseconds=micros)
        except OverflowError as error:
            raise V2Error("invalid_request", "Timestamp outside datetime range") from error
    return records


def checked_parquet(
    path: Path,
    names: list[str],
    types: list[Any],
    limits: Limits,
    *,
    cancelled: Callable[[], bool] | None = None,
) -> Any:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limits.source_bytes:
        raise V2Error("capacity_exceeded", "Parquet source exceeds byte limit")
    size = path.stat().st_size
    if size < 12:
        raise V2Error("invalid_request", "Invalid Parquet footer")
    with path.open("rb") as stream:
        if stream.read(4) != b"PAR1":
            raise V2Error("invalid_request", "Invalid Parquet header")
        stream.seek(-8, 2)
        trailer = stream.read(8)
    footer = struct.unpack("<I", trailer[:4])[0]
    if trailer[4:] != b"PAR1" or footer > limits.footer_bytes or footer > size - 12:
        raise V2Error("capacity_exceeded", "Invalid or oversized Parquet footer")
    parquet = pq.ParquetFile(
        path,
        memory_map=False,
        pre_buffer=False,
        thrift_string_size_limit=limits.footer_bytes,
        thrift_container_size_limit=100000,
    )
    try:
        schema = parquet.schema_arrow
        if (
            len(schema.names) != len(names)
            or set(schema.names) != set(names)
            or len(set(schema.names)) != len(names)
        ):
            raise V2Error("invalid_request", "Invalid Parquet columns")
        for name, kind in zip(names, types, strict=True):
            if schema.field(name).type != kind:
                raise V2Error("invalid_request", "Invalid Parquet logical type")
        if parquet.metadata.num_rows > limits.rows:
            raise V2Error("capacity_exceeded", "Parquet record limit exceeded")
        total = 0
        for index in range(parquet.metadata.num_row_groups):
            check_cancelled(cancelled)
            group = parquet.metadata.row_group(index)
            if group.total_byte_size > min(64 * 1024**2, limits.scratch_bytes):
                raise V2Error("capacity_exceeded", "Parquet row group exceeds allocation limit")
            total += group.total_byte_size
            if total > limits.expanded_bytes:
                raise V2Error("capacity_exceeded", "Parquet decoded size limit exceeded")
            for col in range(group.num_columns):
                if group.column(col).file_path:
                    raise V2Error("invalid_request", "External Parquet references unsupported")
        from .parquet_bounds import validate_pages

        validate_pages(
            path,
            parquet.metadata,
            size - footer - 8,
            min(64 * 1024**2, limits.scratch_bytes),
            max_rows=limits.rows,
            cancelled=cancelled,
        )
        return parquet
    except BaseException:
        parquet.close()
        raise


def _csv_fields(line: bytes, *, bom: bool = False) -> list[str]:
    try:
        value = line.decode("utf-8-sig" if bom else "utf-8")
        parsed = list(csv.reader(io.StringIO(value), strict=True))
        if len(parsed) != 1 or any("\r" in item or "\n" in item for item in parsed[0]):
            raise ValueError
        return parsed[0]
    except (UnicodeError, csv.Error, ValueError) as error:
        raise V2Error("invalid_request", "Invalid canonical CSV record") from error


def _lines(
    stream: IO[bytes], limits: Limits, cancelled: Callable[[], bool] | None, stats: dict[str, int]
) -> Iterator[bytes]:
    total = 0
    while True:
        check_cancelled(cancelled)
        line = stream.readline(limits.record_bytes + 1)
        if not line:
            return
        total += len(line)
        stats["expanded_bytes"] = total
        if len(line) > limits.record_bytes or total > limits.expanded_bytes:
            raise V2Error("capacity_exceeded", "CSV input limit exceeded")
        yield line


def _csv_records(
    stream: IO[bytes],
    official: bool,
    limits: Limits,
    cancelled: Callable[[], bool] | None,
    stats: dict[str, int],
) -> Iterator[list[str]]:
    lines = _lines(stream, limits, cancelled, stats)
    if official:
        for line in lines:
            fields = _csv_fields(line)
            if len(fields) != 7:
                raise V2Error("invalid_request", "Invalid official CSV columns")
            yield [fields[0], fields[4], fields[1], fields[2], fields[3], fields[5], fields[6]]
    else:
        try:
            header = _csv_fields(next(lines), bom=True)
        except StopIteration as error:
            raise V2Error("invalid_request", "Empty canonical source") from error
        if len(header) != 7 or set(header) != set(COLUMNS):
            raise V2Error("invalid_request", "Invalid canonical CSV header")
        positions = [header.index(name) for name in COLUMNS]
        for line in lines:
            fields = _csv_fields(line)
            if len(fields) != 7:
                raise V2Error("invalid_request", "Invalid canonical CSV columns")
            yield [fields[pos] for pos in positions]


def _source_records(
    source: Path,
    metadata: dict[str, Any],
    limits: Limits,
    cancelled: Callable[[], bool] | None,
    stats: dict[str, int],
) -> Iterator[list[Any]]:
    kind = metadata["format"]
    if kind == "parquet":
        parquet = checked_parquet(source, COLUMNS, INPUT_TYPES, limits, cancelled=cancelled)
        try:
            for batch in parquet.iter_batches(
                batch_size=limits.batch_rows, columns=COLUMNS, use_threads=False
            ):
                check_cancelled(cancelled)
                stats["expanded_bytes"] = stats.get("expanded_bytes", 0) + batch.nbytes
                if stats["expanded_bytes"] > limits.expanded_bytes:
                    raise V2Error("capacity_exceeded", "Decoded Parquet buffer limit exceeded")
                for record in python_rows(batch):
                    yield [record[name] for name in COLUMNS]
        finally:
            parquet.close()
    elif kind == "csv":
        with source.open("rb") as stream:
            yield from _csv_records(stream, False, limits, cancelled, stats)
    elif kind == "binance_zip":
        checksum = source.with_name(source.name + ".CHECKSUM")
        if checksum.is_symlink() or not checksum.is_file() or checksum.stat().st_size > 4096:
            raise V2Error("integrity_failure", "Missing official checksum evidence")
        match = re.fullmatch(
            r"([0-9a-fA-F]{64})[ \t]+\*?([^\s]+)", checksum.read_text(encoding="ascii").strip()
        )
        if (
            match is None
            or match[2] != source.name
            or match[1].lower() != metadata["source_sha256"]
        ):
            raise V2Error("integrity_failure", "Official checksum mismatch")
        with zipfile.ZipFile(source) as archive:
            members = archive.infolist()
            if len(members) != 1:
                raise V2Error("invalid_request", "Archive must have one CSV member")
            member = members[0]
            mode = member.external_attr >> 16
            expected = source.name.removesuffix(".zip") + ".csv"
            if (
                member.filename != expected
                or member.is_dir()
                or member.flag_bits & 1
                or stat.S_IFMT(mode) not in {0, stat.S_IFREG}
                or member.file_size > limits.expanded_bytes
            ):
                raise V2Error("invalid_request", "Unsafe or oversized official archive member")
            with archive.open(member) as stream:
                yield from _csv_records(stream, True, limits, cancelled, stats)
    else:
        raise V2Error("invalid_request", "Unsupported normalization format")


class _CappedFile:
    def __init__(self, stream: BinaryIO, ceiling: int) -> None:
        self.stream = stream
        self.ceiling = ceiling

    @property
    def closed(self) -> bool:
        return self.stream.closed

    def writable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.stream.tell()

    def flush(self) -> None:
        self.stream.flush()

    def write(self, data: bytes) -> int:
        if self.tell() + len(data) > self.ceiling:
            raise V2Error("capacity_exceeded", "Normalized output exceeds byte limit")
        return self.stream.write(data)


def normalize_source(
    source: Path,
    output: Path,
    *,
    metadata: dict[str, Any],
    instrument: dict[str, Any],
    cancelled: Callable[[], bool] | None = None,
    limits: Limits = DEFAULT_LIMITS,
) -> dict[str, Any]:
    """Normalize only verified input bytes, sorting/deduplicating on disk."""
    from .common import canonical_json, exact_fields
    from .core import canonical_metadata
    from .source import official_metadata

    check_cancelled(cancelled)
    day = date_value(metadata.get("trade_date"))
    instrument_id = instrument.get("instrument_id")
    if (
        not isinstance(instrument_id, str)
        or not instrument_id.startswith("binance:spot:")
        or metadata.get("instrument_id") != instrument_id
        or metadata.get("quote_quantity_mode") != "supplied"
        or metadata.get("coverage_claim") != "observed_only"
    ):
        raise V2Error("invalid_request", "Invalid normalization metadata")
    official = metadata.get("format") == "binance_zip"
    if official:
        exact_fields(
            metadata,
            {
                "schema",
                "instrument_id",
                "trade_date",
                "format",
                "timestamp_encoding",
                "quote_quantity_mode",
                "source_sha256",
                "coverage_claim",
            },
        )
        if metadata != official_metadata(instrument_id, day, metadata["source_sha256"]):
            raise V2Error("invalid_request", "Invalid official source metadata")
        expected_name = f"{instrument['source_symbol']}-trades-{day.isoformat()}.zip"
        if source.name != expected_name:
            raise V2Error("invalid_request", "Incorrect official source basename")
    else:
        canonical_metadata(metadata)
    if len(canonical_json(metadata)) > limits.metadata_bytes:
        raise V2Error("capacity_exceeded", "Normalization metadata exceeds limit")
    if (
        source.is_symlink()
        or not source.is_file()
        or source.stat().st_size > (limits.compressed_bytes if official else limits.source_bytes)
    ):
        raise V2Error("capacity_exceeded", "Source exceeds byte limit")
    if checked_hash(source, cancelled) != metadata["source_sha256"]:
        raise V2Error("integrity_failure", "Normalization source hash mismatch")
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink():
        raise V2Error("integrity_failure", "Invalid normalization output")
    parquet_path = output / "trades.parquet"
    database_path = output / "normalize.sqlite"
    if database_path.exists() or parquet_path.exists():
        raise V2Error("integrity_failure", "Normalization output already exists")
    database = sqlite3.connect(database_path)
    raw = duplicates = logical_input = 0
    low: int | None = None
    high: int | None = None
    bounds = day_bounds(day)
    cursor: sqlite3.Cursor | None = None
    try:
        database.execute("PRAGMA journal_mode=OFF")
        database.execute("PRAGMA synchronous=OFF")
        database.execute("PRAGMA temp_store=FILE")
        database.execute("PRAGMA cache_size=-8192")
        database.execute(f"PRAGMA max_page_count={max(1, limits.scratch_bytes // 4096)}")
        database.execute(
            "CREATE TABLE records (id INTEGER PRIMARY KEY,ts INTEGER,p TEXT,q TEXT,v TEXT,"
            "maker INTEGER,best INTEGER)"
        )
        stats: dict[str, int] = {"expanded_bytes": 0}
        for fields in _source_records(source, metadata, limits, cancelled, stats):
            check_cancelled(cancelled)
            raw += 1
            if raw > limits.rows:
                raise V2Error("capacity_exceeded", "Input record limit exceeded")
            identifier = integer(fields[0])
            instant = timestamp(fields[1], metadata["timestamp_encoding"], bounds)
            decimals = [
                decimal_text(format(v, ".18f") if isinstance(v, Decimal) else v)
                for v in fields[2:5]
            ]
            flags = []
            for value in fields[5:]:
                if metadata["format"] == "parquet":
                    if value is not None and type(value) is not bool:
                        raise V2Error("invalid_request", "Invalid nullable flag")
                    flags.append(None if value is None else int(value))
                else:
                    allowed = (
                        {"True": 1, "False": 0} if official else {"true": 1, "false": 0, "": None}
                    )
                    if not isinstance(value, str) or value not in allowed:
                        raise V2Error("invalid_request", "Invalid boolean flag")
                    flags.append(allowed[value])
            row = (identifier, instant, *decimals, *flags)
            logical_input += len(logical_row(instrument_id, row))
            if logical_input > limits.logical_bytes:
                raise V2Error("capacity_exceeded", "Decoded logical byte limit exceeded")
            try:
                database.execute("INSERT INTO records VALUES (?,?,?,?,?,?,?)", row)
            except sqlite3.IntegrityError as error:
                if (
                    database.execute("SELECT * FROM records WHERE id=?", (identifier,)).fetchone()
                    != row
                ):
                    raise V2Error("invalid_request", "Conflicting source trade identity") from error
                duplicates += 1
            low = instant if low is None else min(low, instant)
            high = instant if high is None else max(high, instant)
        if raw == 0:
            raise V2Error("invalid_request", "Source contains no trades")
        database.commit()
        logical = hashlib.sha256()
        accepted = 0
        cursor = database.execute("SELECT * FROM records ORDER BY id")
        with parquet_path.open("xb") as raw_output:
            sink = _CappedFile(raw_output, limits.parquet_bytes)
            with pq.ParquetWriter(sink, SCHEMA, compression="zstd") as writer:
                while batch := cursor.fetchmany(limits.batch_rows):
                    check_cancelled(cancelled)
                    records = []
                    for row in batch:
                        logical.update(logical_row(instrument_id, row))
                        records.append(
                            dict(
                                zip(
                                    ["instrument_id", *COLUMNS],
                                    [
                                        instrument_id,
                                        str(row[0]),
                                        EPOCH + timedelta(microseconds=row[1]),
                                        *[Decimal(v) for v in row[2:5]],
                                        *[None if v is None else bool(v) for v in row[5:]],
                                    ],
                                    strict=True,
                                )
                            )
                        )
                    writer.write_table(
                        pa.Table.from_pylist(records, schema=SCHEMA),
                        row_group_size=limits.batch_rows,
                    )
                    accepted += len(batch)
        assert low is not None and high is not None
        expanded_bytes = stats["expanded_bytes"]
        return dict(
            raw_rows=raw,
            accepted_rows=accepted,
            duplicate_rows=duplicates,
            conflict_rows=0,
            expanded_bytes=expanded_bytes,
            logical_input_bytes=logical_input,
            observed_from=utc_text(EPOCH + timedelta(microseconds=low)),
            observed_through=utc_text(EPOCH + timedelta(microseconds=high)),
            logical_sha256=logical.hexdigest(),
            parquet_sha256=checked_hash(parquet_path, cancelled),
            parquet_bytes=parquet_path.stat().st_size,
            validation="passed",
            coverage_note="Observed bounds do not establish gap-free exchange coverage.",
        )
    except (
        sqlite3.Error,
        pa.ArrowException,
        zipfile.BadZipFile,
        RuntimeError,
        EOFError,
        ValueError,
        TypeError,
        UnicodeError,
        OSError,
    ) as error:
        raise V2Error("invalid_request", "Invalid source or normalization artifact") from error
    finally:
        if cursor is not None:
            cursor.close()
        database.close()
        database_path.unlink(missing_ok=True)
