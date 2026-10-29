"""Strict bounded control inputs and shared v2 identity primitives."""

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from marketlab.datasets.source import DatasetError


class V2Error(DatasetError):
    """Allowlisted diagnostic; never expose a raw parser or database exception."""

    def __init__(self, code: str, message: str = "V2 dataset operation failed") -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class Limits:
    source_bytes: int = 4 * 1024**3
    compressed_bytes: int = 512 * 1024**2
    expanded_bytes: int = 4 * 1024**3
    logical_bytes: int = 4 * 1024**3
    rows: int = 20_000_000
    record_bytes: int = 4096
    metadata_bytes: int = 64 * 1024
    parquet_bytes: int = 4 * 1024**3
    scratch_bytes: int = 20 * 1024**3
    batch_rows: int = 16_384
    footer_bytes: int = 16 * 1024**2

    def __post_init__(self) -> None:
        if any(type(v) is not int or v <= 0 for v in vars(self).values()):
            raise V2Error("invalid_request", "Invalid ingestion limits")


DEFAULT_LIMITS = Limits()
HASH = re.compile(r"[0-9a-f]{64}", re.ASCII)
KEY = re.compile(r"[A-Za-z0-9_.-]{1,128}", re.ASCII)
SYMBOL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", re.ASCII)
ASSET = re.compile(r"[A-Z0-9][A-Z0-9._-]{0,31}", re.ASCII)
MIN_DATE = date(1970, 1, 1)
MAX_DATE = date(9999, 12, 30)


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise V2Error("invalid_request", "Duplicate JSON field")
        result[key] = value
    return result


def parse_json(raw: bytes, limit: int = 64 * 1024) -> dict[str, Any]:
    if len(raw) > limit:
        raise V2Error("invalid_request", "Control document exceeds limit")
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeError, ValueError) as error:
        raise V2Error("invalid_request", "Invalid JSON document") from error
    if not isinstance(result, dict):
        raise V2Error("invalid_request", "Expected JSON object")
    # Reject JSON NaN/Infinity even in nested unrecognized values.
    try:
        canonical_json(result)
    except (ValueError, TypeError) as error:
        raise V2Error("invalid_request", "Invalid JSON value") from error
    return result


def read_json(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        return parse_json(stream.read(64 * 1024 + 1))


def exact_fields(
    value: dict[str, Any], required: set[str], optional: set[str] | None = None
) -> None:
    try:
        if len(canonical_json(value)) > 64 * 1024:
            raise V2Error("invalid_request", "Control document exceeds limit")
    except (TypeError, ValueError) as error:
        raise V2Error("invalid_request", "Invalid control value") from error
    if not required <= value.keys() or value.keys() - required - (optional or set()):
        raise V2Error("invalid_request", "Invalid control fields")


def date_value(value: object) -> date:
    if not isinstance(value, str):
        raise V2Error("invalid_request", "Invalid UTC date")
    try:
        result = date.fromisoformat(value)
    except ValueError as error:
        raise V2Error("invalid_request", "Invalid UTC date") from error
    if result.isoformat() != value or not MIN_DATE <= result <= MAX_DATE:
        raise V2Error("invalid_request", "UTC date outside supported range")
    return result


def utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def safe_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
        raise V2Error("integrity_failure", "Invalid dataset reference")
    base = root.resolve()
    current = base
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            raise V2Error("integrity_failure", "Invalid dataset reference")
    if not current.resolve().is_relative_to(base):
        raise V2Error("integrity_failure", "Invalid dataset reference")
    text = str(current)
    if os.name == "nt" and not text.startswith("\\\\?\\"):
        if text.startswith("\\\\"):
            return Path("\\\\?\\UNC\\" + text[2:])
        return Path("\\\\?\\" + text)
    return current
