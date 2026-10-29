"""Full v2 dataset integrity checks independent of catalog discovery."""

import hashlib
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]

from .common import (
    DEFAULT_LIMITS,
    HASH,
    Limits,
    V2Error,
    canonical_json,
    date_value,
    digest,
    parse_json,
    utc_text,
)
from .normalize import (
    COLUMNS,
    EPOCH,
    INPUT_TYPES,
    SCHEMA,
    checked_parquet,
    day_bounds,
    decimal_text,
    integer,
    logical_row,
    python_rows,
    timestamp,
)
from .source import check_cancelled, checked_hash, official_metadata


def verify_parquet(
    path: Path,
    quality: dict[str, Any],
    *,
    instrument_id: str,
    trade_date: date,
    cancelled: Callable[[], bool] | None = None,
    limits: Limits = DEFAULT_LIMITS,
) -> None:
    check_cancelled(cancelled)
    counts = [
        "raw_rows",
        "accepted_rows",
        "duplicate_rows",
        "conflict_rows",
        "parquet_bytes",
        "logical_input_bytes",
        "expanded_bytes",
    ]
    if (
        any(type(quality.get(k)) is not int or quality[k] < 0 for k in counts)
        or not 1 <= quality["accepted_rows"] <= quality["raw_rows"] <= limits.rows
        or quality["raw_rows"] != quality["accepted_rows"] + quality["duplicate_rows"]
        or quality["conflict_rows"] != 0
        or quality.get("validation") != "passed"
        or quality["logical_input_bytes"] > limits.logical_bytes
        or quality["expanded_bytes"] > limits.expanded_bytes
        or quality["parquet_bytes"] > limits.parquet_bytes
    ):
        raise V2Error("integrity_failure", "Invalid normalized quality report")
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size != quality["parquet_bytes"]
        or checked_hash(path, cancelled) != quality["parquet_sha256"]
    ):
        raise V2Error("integrity_failure", "Normalized artifact hash mismatch")
    parquet = checked_parquet(
        path,
        ["instrument_id", *COLUMNS],
        [pa.string(), *INPUT_TYPES],
        limits,
        cancelled=cancelled,
    )
    try:
        if not parquet.schema_arrow.equals(SCHEMA, check_metadata=False):
            raise V2Error("integrity_failure", "Normalized schema mismatch")
        logical = hashlib.sha256()
        logical_bytes = 0
        count = 0
        previous = -1
        low: int | None = None
        high: int | None = None
        bounds = day_bounds(trade_date)
        for batch in parquet.iter_batches(batch_size=limits.batch_rows, use_threads=False):
            check_cancelled(cancelled)
            for record in python_rows(batch):
                check_cancelled(cancelled)
                if record["instrument_id"] != instrument_id:
                    raise V2Error("integrity_failure", "Normalized instrument mismatch")
                identifier = integer(record["source_trade_id"])
                if identifier <= previous:
                    raise V2Error("integrity_failure", "Normalized identity order mismatch")
                previous = identifier
                instant = timestamp(record["executed_at"], "arrow_timestamp_us_utc", bounds)
                values = [
                    decimal_text(format(record[name], ".18f"))
                    for name in ["price", "quantity", "quote_quantity"]
                ]
                flags = [record["is_buyer_maker"], record["is_best_match"]]
                if any(v is not None and type(v) is not bool for v in flags):
                    raise V2Error("integrity_failure", "Invalid normalized flags")
                row = (identifier, instant, *values, *flags)
                encoded = logical_row(instrument_id, row)
                logical.update(encoded)
                logical_bytes += len(encoded)
                count += 1
                if count > limits.rows:
                    raise V2Error("capacity_exceeded", "Normalized row limit exceeded")
                low = instant if low is None else min(low, instant)
                high = instant if high is None else max(high, instant)
        if (
            logical_bytes > quality["logical_input_bytes"]
            or count != quality["accepted_rows"]
            or low is None
            or high is None
            or logical.hexdigest() != quality["logical_sha256"]
            or utc_text(EPOCH + timedelta(microseconds=low)) != quality["observed_from"]
            or utc_text(EPOCH + timedelta(microseconds=high)) != quality["observed_through"]
        ):
            raise V2Error("integrity_failure", "Normalized logical content mismatch")
    except V2Error:
        raise
    except (ValueError, KeyError, TypeError, pa.ArrowException) as error:
        raise V2Error("integrity_failure", "Invalid normalized content") from error
    finally:
        parquet.close()


def verify_dataset(
    directory: Path,
    expected: dict[str, Any] | None = None,
    *,
    cancelled: Callable[[], bool] | None = None,
    limits: Limits = DEFAULT_LIMITS,
) -> dict[str, Any]:
    from .core import canonical_metadata, metadata_hash, semantic_hash

    check_cancelled(cancelled)
    try:
        if directory.is_symlink():
            raise V2Error("integrity_failure", "Invalid dataset directory")
        path = directory / "manifest.json"
        if path.is_symlink() or not path.is_file() or path.stat().st_size > limits.metadata_bytes:
            raise V2Error("integrity_failure", "Invalid dataset manifest")
        content = path.read_bytes()
        manifest = parse_json(content, limits.metadata_bytes)
        if (
            expected
            and expected.get("manifest_sha256")
            and hashlib.sha256(content).hexdigest() != expected["manifest_sha256"]
        ):
            raise V2Error("integrity_failure", "Registered manifest hash mismatch")
        if set(manifest) != {
            "schema",
            "dataset_version_id",
            "identity",
            "instrument",
            "metadata",
            "source",
            "build",
            "quality",
            "artifact",
        }:
            raise V2Error("integrity_failure", "Invalid dataset manifest fields")
        if any(
            not isinstance(manifest[key], dict)
            for key in [
                "identity",
                "instrument",
                "metadata",
                "source",
                "build",
                "quality",
                "artifact",
            ]
        ):
            raise V2Error("integrity_failure", "Invalid dataset manifest section")
        identity = manifest["identity"]
        instrument = manifest["instrument"]
        metadata = manifest["metadata"]
        quality = manifest["quality"]
        artifact = manifest["artifact"]
        identity_fields = {
            "source_sha256",
            "metadata_sha256",
            "instrument_semantic_sha256",
            "trade_date",
            "schema_version",
            "transform_version",
            "lock_sha256",
        }
        if set(identity) != identity_fields or manifest["schema"] != "dataset-manifest-v2":
            raise V2Error("integrity_failure", "Invalid dataset identity fields")
        for key in [
            "source_sha256",
            "metadata_sha256",
            "instrument_semantic_sha256",
            "lock_sha256",
        ]:
            if not isinstance(identity[key], str) or HASH.fullmatch(identity[key]) is None:
                raise V2Error("integrity_failure", "Invalid dataset identity hash")
        if (
            identity["schema_version"] != "spot-trades-v2"
            or identity["transform_version"] != "binance-spot-trades-v2"
            or digest(identity) != manifest["dataset_version_id"]
            or expected
            and expected.get("dataset_version_id")
            and manifest["dataset_version_id"] != expected["dataset_version_id"]
        ):
            raise V2Error("integrity_failure", "Dataset version mismatch")
        build = manifest["build"]
        if (
            set(build) != {"execution_sha256", "lock_sha256"}
            or any(not isinstance(build[k], str) or HASH.fullmatch(build[k]) is None for k in build)
            or build["lock_sha256"] != identity["lock_sha256"]
        ):
            raise V2Error("integrity_failure", "Invalid captured execution provenance")
        day = date_value(identity["trade_date"])
        instrument_id = instrument["instrument_id"]
        if (
            not isinstance(instrument_id, str)
            or not instrument_id.startswith("binance:spot:")
            or instrument.get("venue_id") != "binance"
            or instrument.get("market") != "spot"
            or semantic_hash(instrument) != identity["instrument_semantic_sha256"]
            or instrument.get("semantic_sha256") != identity["instrument_semantic_sha256"]
            or metadata["instrument_id"] != instrument_id
            or metadata["trade_date"] != identity["trade_date"]
            or metadata["source_sha256"] != identity["source_sha256"]
            or metadata_hash(metadata) != identity["metadata_sha256"]
        ):
            raise V2Error("integrity_failure", "Dataset semantic metadata mismatch")
        provenance = manifest["source"]
        if metadata.get("format") == "binance_zip":
            if metadata != official_metadata(instrument_id, day, metadata["source_sha256"]):
                raise V2Error("integrity_failure", "Invalid official metadata")
            symbol = instrument["source_symbol"]
            url = f"https://data.binance.vision/data/spot/daily/trades/{symbol}/{symbol}-trades-{day.isoformat()}.zip"
            if (
                set(provenance)
                != {
                    "kind",
                    "archive_url",
                    "checksum_url",
                    "expected_sha256",
                    "actual_sha256",
                    "retrieved_at",
                }
                or provenance["kind"] != "official_archive"
                or provenance["archive_url"] != url
                or provenance["checksum_url"] != url + ".CHECKSUM"
                or provenance["expected_sha256"] != identity["source_sha256"]
                or provenance["actual_sha256"] != identity["source_sha256"]
            ):
                raise V2Error("integrity_failure", "Invalid official source provenance")
            retrieved = provenance["retrieved_at"]
            if not isinstance(retrieved, str) or len(retrieved) > 40:
                raise V2Error("integrity_failure", "Invalid retrieval timestamp")
            instant = datetime.fromisoformat(retrieved.replace("Z", "+00:00"))
            if (
                instant.tzinfo is None
                or instant.utcoffset() != timedelta(0)
                or not retrieved.endswith(("Z", "+00:00"))
            ):
                raise V2Error("integrity_failure", "Invalid retrieval timestamp")
        else:
            canonical_metadata(metadata)
            if (
                set(provenance) != {"kind", "origin_verification", "source_sha256"}
                or provenance["kind"] != "canonical_file"
                or provenance["origin_verification"] != "operator_declared"
                or provenance["source_sha256"] != identity["source_sha256"]
            ):
                raise V2Error("integrity_failure", "Invalid canonical source provenance")
        if (
            set(artifact) != {"path", "sha256", "bytes"}
            or artifact["path"] != "trades.parquet"
            or artifact["sha256"] != quality["parquet_sha256"]
            or artifact["bytes"] != quality["parquet_bytes"]
        ):
            raise V2Error("integrity_failure", "Dataset artifact reference mismatch")
        qpath = directory / "quality.json"
        if (
            qpath.is_symlink()
            or not qpath.is_file()
            or qpath.stat().st_size > limits.metadata_bytes
            or qpath.read_bytes() != canonical_json(quality)
        ):
            raise V2Error("integrity_failure", "Dataset quality file mismatch")
        verify_parquet(
            directory / "trades.parquet",
            quality,
            instrument_id=instrument_id,
            trade_date=day,
            cancelled=cancelled,
            limits=limits,
        )
        return manifest
    except V2Error:
        raise
    except (KeyError, ValueError, TypeError, OSError, pa.ArrowException) as error:
        raise V2Error("integrity_failure", "Dataset verification failed") from error
