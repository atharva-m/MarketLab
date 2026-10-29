"""Bounded official Binance daily sources for registered spot instruments."""

import hashlib
import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from marketlab.datasets.source import retry_after_seconds

from .common import DEFAULT_LIMITS, MAX_DATE, MIN_DATE, SYMBOL, Limits, V2Error


class TransientSourceError(V2Error):
    transient = True

    def __init__(self, retry_after: int = 0) -> None:
        super().__init__("source_unavailable", "Official source temporarily unavailable")
        self.retry_after = min(3600, max(0, retry_after))


def check_cancelled(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        raise V2Error("cancelled", "Dataset operation cancelled")


def checked_hash(path: Path, cancelled: Callable[[], bool] | None = None) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            check_cancelled(cancelled)
            block = stream.read(1024 * 1024)
            if not block:
                return result.hexdigest()
            result.update(block)


def official_metadata(instrument_id: str, trade_date: date, source_sha256: str) -> dict[str, Any]:
    return dict(
        schema="binance-daily-source-v2",
        instrument_id=instrument_id,
        trade_date=trade_date.isoformat(),
        format="binance_zip",
        timestamp_encoding="unix_milliseconds"
        if trade_date < date(2025, 1, 1)
        else "unix_microseconds",
        quote_quantity_mode="supplied",
        source_sha256=source_sha256,
        coverage_claim="observed_only",
    )


def download_official(
    directory: Path,
    instrument: dict[str, Any],
    trade_date: date,
    *,
    cancelled: Callable[[], bool] | None = None,
    limits: Limits = DEFAULT_LIMITS,
) -> dict[str, Any]:
    symbol = instrument.get("source_symbol")
    if (
        not isinstance(symbol, str)
        or SYMBOL.fullmatch(symbol) is None
        or instrument.get("instrument_id") != f"binance:spot:{symbol}"
        or instrument.get("venue_id", "binance") != "binance"
        or instrument.get("market", "spot") != "spot"
        or type(trade_date) is not date
        or not MIN_DATE <= trade_date <= MAX_DATE
        or trade_date >= datetime.now(UTC).date()
    ):
        raise V2Error("invalid_request", "Unsupported official source selection")
    check_cancelled(cancelled)
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink():
        raise V2Error("integrity_failure", "Invalid source directory")
    name = f"{symbol}-trades-{trade_date.isoformat()}.zip"
    url = f"https://data.binance.vision/data/spot/daily/trades/{symbol}/{name}"
    archive = directory / name
    checksum = directory / (name + ".CHECKSUM")
    try:
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=30.0) as client:
            for remote, destination, ceiling in [
                (url + ".CHECKSUM", checksum, 4096),
                (url, archive, limits.compressed_bytes),
            ]:
                check_cancelled(cancelled)
                with client.stream("GET", remote) as response:
                    if response.status_code in {408, 429} or response.status_code >= 500:
                        raise TransientSourceError(
                            retry_after_seconds(response.headers.get("retry-after", "0"))
                        )
                    if response.status_code != 200:
                        raise V2Error("source_unavailable", "Official daily source unavailable")
                    if response.headers.get("content-encoding", "identity") != "identity":
                        raise V2Error("integrity_failure", "Unsupported source encoding")
                    declared = response.headers.get("content-length")
                    if declared is not None and (
                        not declared.isascii() or not declared.isdigit() or int(declared) > ceiling
                    ):
                        raise V2Error("capacity_exceeded", "Official source exceeds byte limit")
                    total = 0
                    with destination.open("xb") as output:
                        for chunk in response.iter_raw(64 * 1024):
                            check_cancelled(cancelled)
                            total += len(chunk)
                            if total > ceiling:
                                raise V2Error(
                                    "capacity_exceeded", "Official source exceeds byte limit"
                                )
                            output.write(chunk)
                    if declared is not None and total != int(declared):
                        raise V2Error("integrity_failure", "Incomplete official source")
        match = re.fullmatch(
            r"([0-9a-fA-F]{64})[ \t]+\*?([^\s]+)", checksum.read_text(encoding="ascii").strip()
        )
        actual = checked_hash(archive, cancelled)
        if match is None or match[2] != name or match[1].lower() != actual:
            raise V2Error("integrity_failure", "Official checksum mismatch")
    except httpx.HTTPError as error:
        raise TransientSourceError() from error
    except (OSError, UnicodeError) as error:
        raise V2Error("integrity_failure", "Official staging failed") from error
    return dict(
        source_path=archive,
        source_sha256=actual,
        metadata=official_metadata(str(instrument["instrument_id"]), trade_date, actual),
        provenance=dict(
            kind="official_archive",
            archive_url=url,
            checksum_url=url + ".CHECKSUM",
            expected_sha256=actual,
            actual_sha256=actual,
            retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        ),
    )
