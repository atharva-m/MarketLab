"""Bound Parquet page declarations before invoking the Arrow data decoder."""

from collections.abc import Callable
from typing import Any, BinaryIO

from .common import V2Error

HEADER_BYTES = 64 * 1024
MAX_ITEMS = 4096
MAX_DEPTH = 16


class _Compact:
    def __init__(self, stream: BinaryIO, remaining: int) -> None:
        self.stream = stream
        self.ceiling = min(HEADER_BYTES, remaining)
        self.used = 0
        self.items = 0

    def read(self, length: int) -> bytes:
        if length < 0 or self.used + length > self.ceiling:
            raise V2Error("capacity_exceeded", "Parquet page header exceeds bound")
        value = self.stream.read(length)
        if len(value) != length:
            raise V2Error("invalid_request", "Truncated Parquet page header")
        self.used += length
        return value

    def byte(self) -> int:
        return self.read(1)[0]

    def unsigned(self) -> int:
        result = 0
        for shift in range(0, 70, 7):
            value = self.byte()
            if shift == 63 and value > 1:
                raise V2Error("invalid_request", "Parquet header integer overflow")
            result |= (value & 127) << shift
            if not value & 128:
                return result
        raise V2Error("invalid_request", "Parquet header integer overflow")

    def count(self, size: int) -> None:
        self.items += size
        if size > MAX_ITEMS or self.items > MAX_ITEMS:
            raise V2Error("capacity_exceeded", "Parquet header collection exceeds bound")

    def value(self, kind: int, depth: int, *, collection: bool = False) -> Any:
        if depth > MAX_DEPTH:
            raise V2Error("capacity_exceeded", "Parquet header nesting exceeds bound")
        if kind in (1, 2):
            if collection:
                encoded = self.byte()
                if encoded not in (1, 2):
                    raise V2Error("invalid_request", "Invalid Parquet header boolean")
                return encoded == 1
            return kind == 1
        if kind == 3:
            return self.byte()
        if kind in (4, 5, 6):
            value = self.unsigned()
            return (value >> 1) ^ -(value & 1)
        if kind == 7:
            return self.read(8)
        if kind == 8:
            return self.read(self.unsigned())
        if kind in (9, 10):
            header = self.byte()
            size = header >> 4
            if size == 15:
                size = self.unsigned()
            self.count(size)
            element = header & 15
            return [self.value(element, depth + 1, collection=True) for _ in range(size)]
        if kind == 11:
            size = self.unsigned()
            self.count(size)
            if not size:
                return []
            header = self.byte()
            return [
                (
                    self.value(header >> 4, depth + 1, collection=True),
                    self.value(header & 15, depth + 1, collection=True),
                )
                for _ in range(size)
            ]
        if kind == 12:
            return self.structure(depth + 1)
        raise V2Error("invalid_request", "Unsupported Parquet header type")

    def structure(self, depth: int = 0) -> dict[int, Any]:
        result: dict[int, Any] = {}
        previous = 0
        while True:
            header = self.byte()
            if header == 0:
                return result
            kind = header & 15
            difference = header >> 4
            if difference:
                field = previous + difference
            else:
                number = self.unsigned()
                field = (number >> 1) ^ -(number & 1)
            self.count(1)
            if field <= 0 or field in result:
                raise V2Error("invalid_request", "Invalid Parquet header field")
            previous = field
            result[field] = self.value(kind, depth)


def _integer(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 2**31 - 1:
        raise V2Error("invalid_request", "Invalid Parquet page size or count")
    return value


def validate_pages(
    path: Any,
    metadata: Any,
    footer_start: int,
    ceiling: int,
    *,
    max_rows: int = 20_000_000,
    cancelled: Callable[[], bool] | None = None,
) -> None:
    """Scan small headers only; data bodies are skipped without allocation."""

    def check_cancelled() -> None:
        if cancelled is not None and cancelled():
            raise V2Error("cancelled", "Parquet validation cancelled")

    check_cancelled()
    if type(metadata.num_rows) is not int or not 0 <= metadata.num_rows <= max_rows:
        raise V2Error("capacity_exceeded", "Parquet metadata row count invalid")
    group_rows = 0
    intervals: list[tuple[int, int]] = []
    with path.open("rb") as stream:
        for group_number in range(metadata.num_row_groups):
            check_cancelled()
            group = metadata.row_group(group_number)
            if type(group.num_rows) is not int or group.num_rows < 0:
                raise V2Error("invalid_request", "Parquet group row count invalid")
            group_rows += group.num_rows
            if group_rows > max_rows or group_rows > metadata.num_rows:
                raise V2Error("capacity_exceeded", "Parquet group row count exceeds bound")
            group_uncompressed = 0
            for number in range(group.num_columns):
                check_cancelled()
                column = group.column(number)
                if column.num_values != group.num_rows:
                    raise V2Error("invalid_request", "Parquet flat column row count mismatch")
                first = column.data_page_offset
                dictionary = column.dictionary_page_offset
                if dictionary is not None:
                    first = min(first, dictionary)
                length = column.total_compressed_size
                declared = column.total_uncompressed_size
                if (
                    first < 4
                    or length <= 0
                    or declared < 0
                    or declared > ceiling
                    or first + length > footer_start
                ):
                    raise V2Error("capacity_exceeded", "Parquet column bounds invalid")
                end = first + length
                intervals.append((first, end))
                stream.seek(first)
                decoded = values = pages = 0
                seen_data = seen_dictionary = False
                while stream.tell() < end:
                    check_cancelled()
                    page_start = stream.tell()
                    reader = _Compact(stream, end - page_start)
                    header = reader.structure()
                    if not {1, 2, 3} <= header.keys():
                        raise V2Error("invalid_request", "Incomplete Parquet page header")
                    page_type = _integer(header[1])
                    uncompressed = _integer(header[2])
                    compressed = _integer(header[3])
                    pages += 1
                    decoded += reader.used + uncompressed
                    if (
                        uncompressed > ceiling
                        or compressed > ceiling
                        or decoded > declared
                        or stream.tell() + compressed > end
                        or pages > column.num_values + 2
                    ):
                        raise V2Error("capacity_exceeded", "Parquet page allocation bound exceeded")
                    if column.compression == "UNCOMPRESSED" and compressed != uncompressed:
                        raise V2Error("invalid_request", "Parquet page compression mismatch")
                    if page_type == 2:
                        details = header.get(7)
                        if (
                            seen_data
                            or seen_dictionary
                            or not isinstance(details, dict)
                            or not {1, 2} <= details.keys()
                            or _integer(details[1]) > column.num_values
                            or details[2] not in (0, 2)
                        ):
                            raise V2Error("invalid_request", "Invalid Parquet dictionary page")
                        seen_dictionary = True
                    elif page_type in (0, 3):
                        details = header.get(5 if page_type == 0 else 8)
                        if not isinstance(details, dict) or 1 not in details:
                            raise V2Error("invalid_request", "Invalid Parquet data page")
                        count = _integer(details[1])
                        if count <= 0:
                            raise V2Error("invalid_request", "Empty Parquet data page")
                        values += count
                        if values > column.num_values:
                            raise V2Error("invalid_request", "Parquet page value count mismatch")
                        if page_type == 3:
                            if not {1, 2, 3, 4, 5, 6} <= details.keys():
                                raise V2Error("invalid_request", "Incomplete Parquet V2 page")
                            if (
                                _integer(details[2]) > count
                                or _integer(details[3]) > group.num_rows
                                or _integer(details[5]) + _integer(details[6]) > compressed
                                or _integer(details[5]) + _integer(details[6]) > uncompressed
                                or (details.get(7, True) is False and compressed != uncompressed)
                            ):
                                raise V2Error("invalid_request", "Parquet V2 page bounds invalid")
                        encodings = (0, 2, 3, 4, 5, 6, 7, 8, 9)
                        if page_type == 0:
                            if (
                                not {1, 2, 3, 4} <= details.keys()
                                or _integer(details[2]) not in encodings
                                or _integer(details[3]) not in (3, 4)
                                or _integer(details[4]) not in (3, 4)
                            ):
                                raise V2Error("invalid_request", "Invalid Parquet V1 encoding")
                        elif (
                            _integer(details[4]) not in encodings
                            or type(details.get(7, True)) is not bool
                        ):
                            raise V2Error("invalid_request", "Invalid Parquet V2 encoding")
                        seen_data = True
                    else:
                        raise V2Error("invalid_request", "Unsupported Parquet page kind")
                    stream.seek(compressed, 1)
                if stream.tell() != end or decoded != declared or values != column.num_values:
                    raise V2Error("invalid_request", "Parquet column page totals mismatch")
                group_uncompressed += decoded
            if group_uncompressed != group.total_byte_size:
                raise V2Error("invalid_request", "Parquet row group page totals mismatch")
    if group_rows != metadata.num_rows:
        raise V2Error("invalid_request", "Parquet total row count mismatch")
    check_cancelled()
    intervals.sort()
    if any(left[1] > right[0] for left, right in zip(intervals, intervals[1:], strict=False)):
        raise V2Error("invalid_request", "Overlapping Parquet column pages")
