"""Immutable filesystem artifacts registered only after complete verification."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import httpx
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from .jobs import Claim, claim, execute, fence, inspect_submission, jobs, submit, succeed
from .normalize import normalize_archive, verify_parquet
from .source import (
    DAY,
    DEFAULT_LIMITS,
    SYMBOL,
    VENUE,
    DatasetError,
    Limits,
    archive_name,
    download_archive,
    file_hash,
    validate_scope,
    verify_checksum,
)

SCHEMA_VERSION = 1
TRANSFORM_VERSION = "binance-spot-trades-v1"
metadata = sa.MetaData()
dataset_versions = sa.Table(
    "dataset_versions",
    metadata,
    sa.Column("dataset_version_id", sa.String(64), primary_key=True),
    sa.Column("source_sha256", sa.String(64), nullable=False),
    sa.Column("manifest_sha256", sa.String(64), nullable=False),
    sa.Column("manifest_path", sa.Text, nullable=False, unique=True),
    sa.Column("venue", sa.String(32), nullable=False),
    sa.Column("symbol", sa.String(20), nullable=False),
    sa.Column("trade_date", sa.Date, nullable=False),
    sa.Column("row_count", sa.BigInteger, nullable=False),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
)


def _json(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode()


def _build() -> dict[str, object]:
    project = Path(__file__).resolve().parents[3]
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=normal"],
                cwd=project,
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            ).stdout
        )
        lock_hash = file_hash(project / "uv.lock")
    except (OSError, subprocess.SubprocessError) as error:
        raise DatasetError("could not capture source provenance") from error
    return {"git_revision": revision, "git_dirty": dirty, "lock_sha256": lock_hash}


def _version(source_hash: str, symbol: str, trade_date: date, lock_hash: object) -> str:
    identity = {
        "source_sha256": source_hash,
        "venue": VENUE,
        "symbol": symbol,
        "trade_date": trade_date.isoformat(),
        "schema_version": SCHEMA_VERSION,
        "transform_version": TRANSFORM_VERSION,
        "lock_sha256": lock_hash,
    }
    return hashlib.sha256(_json(identity)).hexdigest()


def _relative(version: str, symbol: str, trade_date: date) -> Path:
    return (
        Path("datasets")
        / version
        / f"venue={VENUE}"
        / f"symbol={symbol}"
        / ("date=" + trade_date.isoformat())
    )


def _storage_root(path: Path) -> Path:
    resolved = path.resolve()
    text = str(resolved)
    if os.name == "nt" and not text.startswith("\\\\?\\"):
        if text.startswith("\\\\"):
            return Path("\\\\?\\UNC\\" + text[2:])
        return Path("\\\\?\\" + text)
    return resolved


def _safe_path(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        raise DatasetError("unsafe dataset artifact path")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise DatasetError("unsafe dataset artifact path")
    if not current.resolve().is_relative_to(root.resolve()):
        raise DatasetError("unsafe dataset artifact path")
    return current


def _verify_manifest(path: Path, version: str, expected_hash: str | None = None) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 1024 * 1024:
        raise DatasetError("dataset manifest integrity failure")
    if expected_hash is not None and file_hash(path) != expected_hash:
        raise DatasetError("dataset manifest integrity failure")
    try:
        manifest: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        symbol = manifest["symbol"]
        trade_date = date.fromisoformat(manifest["trade_date"])
        validate_scope(symbol, trade_date)
        quality = manifest["quality"]
        if (
            any(
                type(quality[key]) is not int or quality[key] < 0
                for key in (
                    "raw_rows",
                    "accepted_rows",
                    "duplicate_rows",
                    "conflict_rows",
                    "expanded_bytes",
                )
            )
            or quality["accepted_rows"] < 1
            or quality["conflict_rows"] != 0
            or quality["raw_rows"] != quality["accepted_rows"] + quality["duplicate_rows"]
            or quality["validation"] != "passed"
            or manifest["requested_from"] != trade_date.isoformat() + "T00:00:00Z"
            or manifest["requested_before"]
            != (trade_date + timedelta(days=1)).isoformat() + "T00:00:00Z"
            or type(manifest["build"]["git_dirty"]) is not bool
            or re.fullmatch(r"[0-9a-f]{40}", manifest["build"]["git_revision"]) is None
            or re.fullmatch(r"[0-9a-f]{64}", manifest["build"]["lock_sha256"]) is None
            or re.fullmatch(r"[0-9a-f]{64}", manifest["source"]["actual_sha256"]) is None
        ):
            raise DatasetError("dataset manifest content mismatch")
        if (
            manifest["dataset_version_id"] != version
            or manifest["venue"] != VENUE
            or manifest["schema_version"] != SCHEMA_VERSION
            or manifest["transform_version"] != TRANSFORM_VERSION
            or manifest["artifact"]["path"] != "trades.parquet"
            or _version(
                manifest["source"]["actual_sha256"],
                symbol,
                trade_date,
                manifest["build"]["lock_sha256"],
            )
            != version
            or manifest["source"]["expected_sha256"] != manifest["source"]["actual_sha256"]
            or manifest["artifact"]["sha256"] != manifest["quality"]["parquet_sha256"]
            or manifest["artifact"]["bytes"] != manifest["quality"]["parquet_bytes"]
        ):
            raise DatasetError("dataset manifest content mismatch")
        artifact = _safe_path(path.parent, Path("trades.parquet"))
        verify_parquet(artifact, manifest["quality"], symbol=symbol, trade_date=trade_date)
        return manifest
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise DatasetError("dataset artifact verification failed") from error


def inspect_version(engine: Engine, root: Path, version_id: str) -> dict[str, object] | None:
    if re.fullmatch(r"[0-9a-f]{64}", version_id) is None:
        raise DatasetError("invalid dataset version")
    try:
        with engine.connect() as connection:
            row = (
                connection.execute(
                    sa.select(dataset_versions).where(
                        dataset_versions.c.dataset_version_id == version_id
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        path = _safe_path(_storage_root(root), Path(row["manifest_path"]))
        manifest = _verify_manifest(path, version_id, row["manifest_sha256"])
        if (
            row["status"] != "published"
            or row["source_sha256"] != manifest["source"]["actual_sha256"]
            or row["row_count"] != manifest["quality"]["accepted_rows"]
            or row["venue"] != manifest["venue"]
            or row["symbol"] != manifest["symbol"]
            or row["trade_date"].isoformat() != manifest["trade_date"]
        ):
            raise DatasetError("dataset catalog integrity failure")
        return manifest
    except sa.exc.SQLAlchemyError as error:
        raise DatasetError("dataset catalog unavailable") from error


def _ingest_archive(
    engine: Engine,
    root: Path,
    archive_path: Path,
    checksum_path: Path,
    *,
    symbol: str = SYMBOL,
    trade_date: date = DAY,
    provenance: dict[str, object] | None = None,
    limits: Limits = DEFAULT_LIMITS,
    checkpoint: Callable[[str], None] | None = None,
    current: Claim,
) -> dict[str, object]:
    validate_scope(symbol, trade_date)
    if archive_path.stat().st_size > limits.compressed_bytes:
        raise DatasetError("source download exceeds size limit")
    source_hash = verify_checksum(archive_path, checksum_path, archive_name(symbol, trade_date))
    build = _build()
    version = _version(source_hash, symbol, trade_date, build["lock_sha256"])
    root = _storage_root(root)
    existing_manifest = inspect_version(engine, root, version)
    root.mkdir(parents=True, exist_ok=True)
    staging_root = _safe_path(root, Path(".staging"))
    staging_root.mkdir(exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="ingest-", dir=staging_root))
    try:
        quality: dict[str, Any] = (
            cast(dict[str, Any], existing_manifest["quality"])
            if existing_manifest is not None
            else normalize_archive(
                archive_path, staging, symbol=symbol, trade_date=trade_date, limits=limits
            )
        )
        source: dict[str, object] = dict(provenance or {"kind": "local_provider_fixture"})
        source.update(
            {
                "expected_sha256": source_hash,
                "actual_sha256": source_hash,
                "archive_bytes": archive_path.stat().st_size,
            }
        )
        source.setdefault("retrieved_at", datetime.now(UTC).isoformat().replace("+00:00", "Z"))
        manifest: dict[str, Any] = {
            "dataset_version_id": version,
            "venue": VENUE,
            "symbol": symbol,
            "trade_date": trade_date.isoformat(),
            "schema_version": SCHEMA_VERSION,
            "transform_version": TRANSFORM_VERSION,
            "source": source,
            "build": build,
            "requested_from": trade_date.isoformat() + "T00:00:00Z",
            "requested_before": (trade_date + timedelta(days=1)).isoformat() + "T00:00:00Z",
            "quality": quality,
            "artifact": {
                "path": "trades.parquet",
                "sha256": quality["parquet_sha256"],
                "bytes": quality["parquet_bytes"],
            },
        }
        if existing_manifest is None:
            (staging / "manifest.json").write_bytes(_json(manifest))
        for file in staging.iterdir():
            with file.open("r+b") as stream:
                os.fsync(stream.fileno())
        if existing_manifest is None:
            _verify_manifest(staging / "manifest.json", version)
        if checkpoint is not None:
            checkpoint("artifacts_complete")
        relative = _relative(version, symbol, trade_date)
        final = _safe_path(root, relative)
        # Preflight readback is outside all publication locks. Cooperating writers
        # only create immutable finals; a race repeats preflight rather than reading
        # a potentially large Parquet file inside a database transaction.
        for preflight in range(4):
            verified = (
                existing_manifest if preflight == 0 else inspect_version(engine, root, version)
            )
            verified_hash: str | None = None
            published = manifest
            if verified is not None:
                published = verified
                verified_hash = file_hash(final / "manifest.json")
            elif final.exists():
                published = _verify_manifest(final / "manifest.json", version)
                verified_hash = file_hash(final / "manifest.json")
            try:
                with engine.begin() as connection:
                    connection.execute(sa.text("SET LOCAL lock_timeout = '10s'"))
                    connection.execute(sa.text("SET LOCAL statement_timeout = '15s'"))
                    connection.execute(
                        sa.text("SET LOCAL idle_in_transaction_session_timeout = '15s'")
                    )
                    fence(connection, current)
                    lock = int.from_bytes(bytes.fromhex(version[:16]), "big", signed=True)
                    connection.execute(sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
                    fence(connection, current)
                    existing = (
                        connection.execute(
                            sa.select(dataset_versions).where(
                                dataset_versions.c.dataset_version_id == version
                            )
                        )
                        .mappings()
                        .one_or_none()
                    )
                    if final.exists():
                        if verified_hash is None:
                            continue
                        if file_hash(final / "manifest.json") != verified_hash:
                            raise DatasetError("dataset manifest integrity failure")
                        if existing is not None and existing["manifest_sha256"] != verified_hash:
                            raise DatasetError("dataset catalog integrity failure")
                    else:
                        if verified_hash is not None or existing is not None:
                            raise DatasetError("dataset artifact integrity failure")
                        final.parent.mkdir(parents=True, exist_ok=True)
                        _safe_path(root, relative)
                        staging.rename(final)
                        verified_hash = file_hash(final / "manifest.json")
                    if existing is None:
                        connection.execute(
                            dataset_versions.insert().values(
                                dataset_version_id=version,
                                source_sha256=source_hash,
                                manifest_sha256=verified_hash,
                                manifest_path=(relative / "manifest.json").as_posix(),
                                venue=VENUE,
                                symbol=symbol,
                                trade_date=trade_date,
                                row_count=published["quality"]["accepted_rows"],
                                status="published",
                                published_at=datetime.now(UTC),
                            )
                        )
                    succeed(connection, current, version)
                    if checkpoint is not None:
                        checkpoint("before_catalog_commit")
                if checkpoint is not None:
                    checkpoint("after_catalog_commit")
                return published
            except sa.exc.SQLAlchemyError as error:
                raise DatasetError("dataset catalog publication failed") from error
        raise DatasetError("concurrent publication did not settle")
    finally:
        # Temporary tree was generated inside the verified root; never remove final artifacts.
        if staging.exists():
            shutil.rmtree(staging)


def _ingest_day(
    engine: Engine,
    root: Path,
    *,
    symbol: str,
    trade_date: date,
    client: httpx.Client | None = None,
    limits: Limits = DEFAULT_LIMITS,
    current: Claim,
) -> dict[str, object]:
    validate_scope(symbol, trade_date)
    root = _storage_root(root)
    root.mkdir(parents=True, exist_ok=True)
    download_root = _safe_path(root, Path(".downloads"))
    download_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="source-", dir=download_root) as directory:
        destination = Path(directory)
        if client is None:
            with httpx.Client(trust_env=False, follow_redirects=False) as owned:
                archive, checksum, provenance = download_archive(
                    owned, destination, symbol=symbol, trade_date=trade_date, limits=limits
                )
        else:
            archive, checksum, provenance = download_archive(
                client, destination, symbol=symbol, trade_date=trade_date, limits=limits
            )
        return _ingest_archive(
            engine,
            root,
            archive,
            checksum,
            symbol=symbol,
            trade_date=trade_date,
            provenance=provenance,
            limits=limits,
            current=current,
        )


def ingest_archive(
    engine: Engine,
    root: Path,
    archive_path: Path,
    checksum_path: Path,
    *,
    symbol: str = SYMBOL,
    trade_date: date = DAY,
    provenance: dict[str, object] | None = None,
    limits: Limits = DEFAULT_LIMITS,
    checkpoint: Callable[[str], None] | None = None,
    resume_job_id: str | None = None,
) -> dict[str, object]:
    """Execute a local fixture inline; generic network workers cannot claim it."""
    from uuid import uuid4

    validate_scope(symbol, trade_date)
    if archive_path.stat().st_size > limits.compressed_bytes:
        raise DatasetError("source download exceeds size limit")
    digest = verify_checksum(archive_path, checksum_path, archive_name(symbol, trade_date))
    if resume_job_id is None:
        identity = submit(
            engine,
            [symbol],
            trade_date,
            trade_date + timedelta(days=1),
            "inline-" + uuid4().hex,
            source_mode="fixture",
            input_sha256=digest,
        )
        job_id = str(inspect_submission(engine, identity)["jobs"][0]["job_id"])
    else:
        job_id = resume_job_id
        with engine.connect() as connection:
            row = (
                connection.execute(sa.select(jobs).where(jobs.c.job_id == job_id))
                .mappings()
                .one_or_none()
            )
        if (
            row is None
            or row["source_mode"] != "fixture"
            or row["input_sha256"] != digest
            or row["symbol"] != symbol
            or row["trade_date"] != trade_date
        ):
            raise DatasetError("fixture resume source mismatch")
        if row["state"] == "succeeded":
            result = inspect_version(engine, root, row["result_version"])
            if result is None:
                raise DatasetError("dataset catalog integrity failure")
            return result
    current = claim(engine, job_id=job_id)
    if current is None:
        raise DatasetError("inline ingestion job is not eligible")
    return execute(
        engine,
        current,
        lambda owned: _ingest_archive(
            engine,
            root,
            archive_path,
            checksum_path,
            symbol=symbol,
            trade_date=trade_date,
            provenance=provenance,
            limits=limits,
            checkpoint=checkpoint,
            current=owned,
        ),
    )


def ingest_day(
    engine: Engine,
    root: Path,
    *,
    symbol: str,
    trade_date: date,
    client: httpx.Client | None = None,
    limits: Limits = DEFAULT_LIMITS,
    resume_job_id: str | None = None,
) -> dict[str, object]:
    """Preserve synchronous entry point while using a durable fenced job."""
    from uuid import uuid4

    validate_scope(symbol, trade_date)
    if resume_job_id is None:
        identity = submit(
            engine,
            [symbol],
            trade_date,
            trade_date + timedelta(days=1),
            "inline-" + uuid4().hex,
            source_mode="inline",
        )
        job_id = str(inspect_submission(engine, identity)["jobs"][0]["job_id"])
    else:
        job_id = resume_job_id
    while True:
        with engine.connect() as connection:
            row = (
                connection.execute(sa.select(jobs).where(jobs.c.job_id == job_id))
                .mappings()
                .one_or_none()
            )
            if (
                row is None
                or row["source_mode"] != "inline"
                or row["symbol"] != symbol
                or row["trade_date"] != trade_date
            ):
                raise DatasetError("inline resume source mismatch")
            if row["state"] == "succeeded":
                result = inspect_version(engine, root, row["result_version"])
                if result is None:
                    raise DatasetError("dataset catalog integrity failure")
                return result
            delay = (
                connection.scalar(
                    sa.select(
                        sa.extract("epoch", jobs.c.eligible_at - sa.func.clock_timestamp())
                    ).where(jobs.c.job_id == job_id)
                )
                if row["state"] == "retry_wait"
                else 0
            )
        if delay is not None and delay > 0:
            time.sleep(min(float(delay), 3600))
        current = claim(engine, job_id=job_id)
        if current is None:
            raise DatasetError("inline ingestion job is not eligible")
        try:
            return execute(
                engine,
                current,
                lambda owned: _ingest_day(
                    engine,
                    root,
                    symbol=symbol,
                    trade_date=trade_date,
                    client=client,
                    limits=limits,
                    current=owned,
                ),
            )
        except DatasetError:
            with engine.connect() as connection:
                state = connection.scalar(sa.select(jobs.c.state).where(jobs.c.job_id == job_id))
            if state != "retry_wait":
                raise


def run_claim(engine: Engine, root: Path, current: Claim) -> dict[str, object]:
    """Network worker operation, always called inside execute's heartbeat scope."""
    return _ingest_day(
        engine, root, symbol=current.symbol, trade_date=current.trade_date, current=current
    )
