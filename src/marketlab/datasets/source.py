"""Bounded official daily archive acquisition, independent of synthetic trades."""

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

VENUE = "binance_spot"
DAY = date(2025, 1, 1)
SYMBOL = "BTCUSDT"


class DatasetError(Exception):
    """Safe public diagnostic for ingestion/publication failures."""


@dataclass(frozen=True)
class Limits:
    compressed_bytes: int = 512 * 1024**2
    expanded_bytes: int = 4 * 1024**3
    rows: int = 20_000_000
    line_bytes: int = 4096

    def __post_init__(self) -> None:
        if any(type(value) is not int or value < 1 for value in vars(self).values()):
            raise DatasetError("invalid ingestion limits")


DEFAULT_LIMITS = Limits()


def validate_scope(symbol: str, trade_date: date) -> None:
    if symbol != SYMBOL or trade_date != DAY or type(trade_date) is not date:
        raise DatasetError("unsupported historical symbol or date")


def archive_name(symbol: str, trade_date: date) -> str:
    validate_scope(symbol, trade_date)
    return f"{symbol}-trades-{trade_date.isoformat()}.zip"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksum(archive: Path, checksum: Path, expected_name: str) -> str:
    if not checksum.is_file() or checksum.stat().st_size > 4096:
        raise DatasetError("invalid source checksum")
    try:
        content = checksum.read_text(encoding="ascii").strip()
    except (UnicodeError, OSError) as error:
        raise DatasetError("invalid source checksum") from error
    match = re.fullmatch(r"([0-9a-fA-F]{64})[ \t]+\*?([^\s]+)", content)
    if match is None or match[2] != expected_name:
        raise DatasetError("invalid source checksum")
    expected = match[1].lower()
    actual = file_hash(archive)
    if expected != actual:
        raise DatasetError("source checksum mismatch")
    return actual


def download_archive(
    client: httpx.Client,
    destination_dir: Path,
    *,
    symbol: str,
    trade_date: date,
    limits: Limits = DEFAULT_LIMITS,
) -> tuple[Path, Path, dict[str, object]]:
    name = archive_name(symbol, trade_date)
    url = f"https://data.binance.vision/data/spot/daily/trades/{symbol}/{name}"
    destination_dir.mkdir(parents=True, exist_ok=True)
    archive = destination_dir / name
    checksum = destination_dir / (name + ".CHECKSUM")
    try:
        for remote, local, cap in (
            (url + ".CHECKSUM", checksum, 4096),
            (url, archive, limits.compressed_bytes),
        ):
            with client.stream(
                "GET", remote, timeout=httpx.Timeout(30.0), follow_redirects=False
            ) as response:
                if response.status_code != 200:
                    raise DatasetError(f"historical source returned HTTP {response.status_code}")
                # Do not transparently decode HTTP compression around ZIP/checksum content.
                if response.headers.get("content-encoding", "identity") != "identity":
                    raise DatasetError("unsupported source content encoding")
                total = 0
                with local.open("xb") as stream:
                    for chunk in response.iter_bytes(64 * 1024):
                        total += len(chunk)
                        if total > cap:
                            raise DatasetError("source download exceeds size limit")
                        stream.write(chunk)
                declared = response.headers.get("content-length")
                if declared is not None and (not declared.isdigit() or int(declared) != total):
                    raise DatasetError("incomplete source download")
        digest = verify_checksum(archive, checksum, name)
    except httpx.HTTPError as error:
        raise DatasetError("historical source request failed") from error
    return (
        archive,
        checksum,
        {
            "kind": "official_archive",
            "archive_url": url,
            "checksum_url": url + ".CHECKSUM",
            "retrieved_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "expected_sha256": digest,
            "actual_sha256": digest,
        },
    )
