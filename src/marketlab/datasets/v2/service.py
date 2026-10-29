"""Owned local staging and immutable fenced v2 publication."""

import os
import shutil
import stat
import threading
import time
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.engine import Connection, Engine

from . import jobs
from .common import (
    DEFAULT_LIMITS,
    KEY,
    Limits,
    V2Error,
    canonical_json,
    date_value,
    digest,
    safe_path,
    sha256_file,
)
from .core import (
    PROTOCOL,
    TRANSFORM,
    canonical_metadata,
    execute,
    execution_identity,
    instrument,
    lock,
    metadata_hash,
    one,
    operation,
    save_operation,
    transaction,
    uid,
    wire,
)


def _reserve(
    connection: Connection,
    root: Path,
    relative: str,
    ceiling: int,
    kind: str,
    *,
    import_id: Any = None,
    job: dict[str, Any] | None = None,
) -> None:
    lock(connection, "v2-space:" + str(root.resolve()))
    outstanding = execute(
        connection,
        "SELECT coalesce(sum(reserved_bytes),0) FROM v2_storage_reservations WHERE "
        "state<>'released'",
    ).scalar_one()
    if shutil.disk_usage(root).free < int(outstanding) + ceiling:
        raise V2Error("capacity_exceeded", "Insufficient reserved staging capacity")
    execute(
        connection,
        "INSERT INTO v2_storage_reservations VALUES (:id,:import_id,:job,:token,:kind,"
        ":ceiling,0,:ceiling,'reserved',:path,clock_timestamp(),clock_timestamp())",
        id=uuid4(),
        import_id=import_id,
        job=None if job is None else job["job_id"],
        token=None if job is None else job["fencing_token"],
        kind=kind,
        ceiling=ceiling,
        path=relative,
    )


def _source_account(connection: Connection, import_id: Any, retained: int) -> None:
    execute(
        connection,
        "UPDATE v2_storage_reservations SET "
        "retained_bytes=:bytes,reserved_bytes=ceiling_bytes-:bytes,"
        "updated_at=clock_timestamp() WHERE import_id=:id AND kind='source'",
        id=import_id,
        bytes=retained,
    )


def inspect_import(engine: Engine, import_id: str) -> dict[str, Any]:
    identity = uid(import_id)
    with engine.connect() as connection:
        result = one(
            connection, "SELECT * FROM v2_canonical_imports WHERE import_id=:id", id=identity
        )
        if result is None:
            raise V2Error("not_found", "Canonical import not found")
        result.pop("source_relative_path", None)
        result.pop("staging_owner", None)
        return wire(result)  # type: ignore[no-any-return]


def expire_staging(engine: Engine, root: Path) -> int:
    count = 0
    with transaction(engine) as connection:
        rows = execute(
            connection,
            "SELECT * FROM v2_canonical_imports WHERE state='staging' AND "
            "staging_lease_until<=clock_timestamp() ORDER BY import_id LIMIT 62 FOR "
            "UPDATE SKIP LOCKED",
        ).mappings()
        for row in rows:
            path = safe_path(root, row["source_relative_path"])
            retained = min(row["declared_bytes"], path.stat().st_size if path.is_file() else 0)
            _source_account(connection, row["import_id"], retained)
            execute(
                connection,
                "UPDATE v2_canonical_imports SET state='failed',revision=revision+1,"
                "error_code='staging_expired',received_bytes=:bytes,staging_owner=NULL,"
                "staging_lease_until=NULL,updated_at=clock_timestamp() WHERE import_id=:id",
                id=row["import_id"],
                bytes=retained,
            )
            count += 1
    return count


def import_file(
    engine: Engine,
    root: Path,
    metadata: dict[str, Any],
    source: Path,
    key: str,
    *,
    limits: Limits = DEFAULT_LIMITS,
) -> dict[str, Any]:
    metadata = canonical_metadata(metadata)
    # Replay is bound to retained source metadata, never the original caller path.
    with transaction(engine) as connection:
        if not isinstance(key, str) or KEY.fullmatch(key) is None:
            raise V2Error("invalid_request", "Invalid operation key")
        lock(connection, f"v2-operation:import:{PROTOCOL}:{key}")
        old = one(
            connection,
            "SELECT response_json FROM v2_operations WHERE operation='import' "
            "AND protocol=:protocol AND idempotency_key=:key",
            protocol=PROTOCOL,
            key=key,
        )
        if old is not None:
            prior = one(
                connection,
                "SELECT declared_bytes FROM v2_canonical_imports WHERE import_id=:id",
                id=uid(old["response_json"]["import_id"]),
            )
            if prior is None:
                raise V2Error("integrity_failure", "Import operation reference is missing")
            replay = operation(
                connection,
                "import",
                key,
                {"manifest": metadata, "content_length": prior["declared_bytes"]},
            )
            assert replay is not None
            replay["status"] = inspect_import(engine, replay["import_id"])
            return replay
    if source.is_symlink() or not source.is_file():
        raise V2Error("invalid_request", "Canonical input must be a regular file")
    declared = source.stat().st_size
    if not 1 <= declared <= limits.source_bytes:
        raise V2Error("invalid_request", "Canonical input exceeds size limit")
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    request = {"manifest": metadata, "content_length": declared}
    iid, generation, owner = uuid4(), uuid4(), uuid4()
    relative = f"staging-v2/{iid}/{generation}/source.{metadata['format']}"
    with transaction(engine) as connection:
        replay = operation(connection, "import", key, request)
        if replay is not None:
            replay["status"] = inspect_import(engine, replay["import_id"])
            return replay
        current = instrument(connection, metadata["instrument_id"], enabled=True)
        execute(
            connection,
            "INSERT INTO v2_canonical_imports (import_id,instrument_id,semantic_sha256,trade_date,"
            "metadata_json,metadata_sha256,source_sha256,format,declared_bytes,received_bytes,"
            "generation_id,source_relative_path,state,revision,staging_owner,staging_lease_until,"
            "created_at,updated_at) VALUES (:id,:instrument,:semantic,:day,CAST(:metadata "
            "AS jsonb),"
            ":metadata_sha,:source_sha,:format,:declared,0,:generation,:path,'staging',0,:owner,"
            "clock_timestamp()+interval '60 seconds',clock_timestamp(),clock_timestamp())",
            id=iid,
            instrument=current["instrument_id"],
            semantic=current["semantic_sha256"],
            day=date_value(metadata["trade_date"]),
            metadata=canonical_json(metadata).decode(),
            metadata_sha=metadata_hash(metadata),
            source_sha=metadata["source_sha256"],
            format=metadata["format"],
            declared=declared,
            generation=generation,
            path=relative,
            owner=owner,
        )
        _reserve(connection, root, relative, declared, "source", import_id=iid)
        initial = {"import_id": str(iid), "state": "staging", "revision": 0}
        save_operation(connection, "import", key, request, initial)
    target = safe_path(root, relative)
    lost = threading.Event()
    done = threading.Event()

    def renew() -> None:
        while not done.wait(10):
            try:
                with transaction(engine) as connection:
                    renewed = execute(
                        connection,
                        "UPDATE v2_canonical_imports SET "
                        "staging_lease_until=clock_timestamp()+interval '60 seconds'"
                        "WHERE import_id=:id AND state='staging' AND staging_owner=:owner "
                        "AND staging_lease_until>clock_timestamp() RETURNING import_id",
                        id=iid,
                        owner=owner,
                    ).first()
                    if renewed is None:
                        lost.set()
                        return
            except Exception:
                lost.set()
                return

    renewer = threading.Thread(target=renew, daemon=True)
    renewer.start()
    received = 0
    try:
        target.parent.mkdir(parents=True, exist_ok=False)
        descriptor = os.open(
            source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        )
        incoming = os.fdopen(descriptor, "rb")
        with incoming, target.open("xb") as outgoing:
            if source.is_symlink() or not stat.S_ISREG(os.fstat(incoming.fileno()).st_mode):
                raise V2Error("invalid_request", "Canonical input must remain a regular file")
            while chunk := incoming.read(1024 * 1024):
                if lost.is_set():
                    raise V2Error("ownership_lost", "Canonical staging ownership lost")
                if received + len(chunk) > declared:
                    raise V2Error("integrity_failure", "Canonical input length changed")
                outgoing.write(chunk)
                received += len(chunk)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        if received != declared or sha256_file(target) != metadata["source_sha256"]:
            raise V2Error("integrity_failure", "Canonical source hash or length mismatch")
        with transaction(engine) as connection:
            stage = one(
                connection,
                "SELECT *,staging_lease_until>clock_timestamp() AS live FROM v2_canonical_imports "
                "WHERE import_id=:id FOR UPDATE",
                id=iid,
            )
            if (
                stage is None
                or stage["state"] != "staging"
                or stage["staging_owner"] != owner
                or not stage["live"]
            ):
                raise V2Error("ownership_lost", "Canonical staging ownership lost")
            day = date_value(metadata["trade_date"])
            sid, jids = jobs.create_submission(
                connection,
                request,
                [metadata["instrument_id"]],
                day,
                day + timedelta(days=1),
                import_id=iid,
            )
            execute(
                connection,
                "UPDATE v2_canonical_imports SET state='queued',revision=revision+1,"
                "received_bytes=:bytes,submission_id=:submission,staging_owner=NULL,"
                "staging_lease_until=NULL,updated_at=clock_timestamp() WHERE import_id=:id",
                id=iid,
                bytes=received,
                submission=sid,
            )
            _source_account(connection, iid, received)
            result = {
                "import_id": str(iid),
                "submission_id": str(sid),
                "job_id": str(jids[0]),
                "state": "queued",
                "revision": 1,
            }
            execute(
                connection,
                "UPDATE v2_operations SET response_json=CAST(:response AS jsonb) WHERE "
                "operation='import'"
                "AND protocol=:protocol AND idempotency_key=:key",
                response=canonical_json(result).decode(),
                protocol=PROTOCOL,
                key=key,
            )
            return dict(result, replayed=False)
    except Exception:
        with transaction(engine) as connection:
            stage = one(
                connection,
                "SELECT * FROM v2_canonical_imports WHERE import_id=:id FOR UPDATE",
                id=iid,
            )
            if (
                stage is not None
                and stage["state"] == "staging"
                and stage["staging_owner"] == owner
            ):
                _source_account(connection, iid, received)
                execute(
                    connection,
                    "UPDATE v2_canonical_imports SET state='failed',revision=revision+1,"
                    "error_code='staging_failed',received_bytes=:bytes,staging_owner=NULL,"
                    "staging_lease_until=NULL,updated_at=clock_timestamp() WHERE import_id=:id",
                    id=iid,
                    bytes=received,
                )
        raise
    finally:
        done.set()
        renewer.join(timeout=15)


def _job_reservations(engine: Engine, root: Path, current: dict[str, Any], relative: str) -> None:
    with transaction(engine) as connection:
        jobs.fence(connection, current)
        _reserve(
            connection, root, relative + "/output", 4 * 1024**3 + 128 * 1024, "output", job=current
        )
        _reserve(connection, root, relative + "/scratch", 20 * 1024**3, "scratch", job=current)


def _reconcile(
    connection: Connection,
    current: dict[str, Any],
    kind: str,
    retained: int,
    path: str | None = None,
) -> None:
    execute(
        connection,
        "UPDATE v2_storage_reservations SET "
        "reserved_bytes=0,retained_bytes=:bytes,state='retained',"
        "relative_path=coalesce(:path,relative_path),updated_at=clock_timestamp() WHERE "
        "job_id=:job "
        "AND fencing_token=:token AND kind=:kind",
        job=current["job_id"],
        token=current["fencing_token"],
        kind=kind,
        bytes=retained,
        path=path,
    )


def run_claim(engine: Engine, root: Path, current: dict[str, Any]) -> dict[str, Any]:
    from .artifacts import verify_dataset
    from .normalize import normalize_source
    from .source import download_official

    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    relative = f"attempts-v2/{current['job_id']}/{current['fencing_token']}/{uuid4()}"
    attempt = safe_path(root, relative)
    output = attempt / "output"
    done, lost = threading.Event(), threading.Event()

    def renew() -> None:
        while not done.wait(10):
            try:
                if not jobs.heartbeat(engine, current):
                    lost.set()
                    return
            except Exception:
                lost.set()
                return

    renewer = threading.Thread(target=renew, daemon=True)
    renewer.start()
    try:
        _job_reservations(engine, root, current, relative)
        attempt.mkdir(parents=True, exist_ok=False)
        snapshot = current["instrument_snapshot"]
        if current["source_mode"] == "official":
            source = download_official(
                attempt / "source", snapshot, current["trade_date"], cancelled=lost.is_set
            )
        else:
            with engine.connect() as connection:
                imported = one(
                    connection,
                    "SELECT * FROM v2_canonical_imports WHERE import_id=:id",
                    id=current["import_id"],
                )
            assert imported is not None
            raw = safe_path(root, imported["source_relative_path"])
            if (
                not raw.is_file()
                or raw.stat().st_size != imported["declared_bytes"]
                or sha256_file(raw) != imported["source_sha256"]
            ):
                raise V2Error("integrity_failure", "Staged canonical source integrity failure")
            source = {
                "source_path": raw,
                "source_sha256": imported["source_sha256"],
                "metadata": imported["metadata_json"],
                "provenance": {
                    "kind": "canonical_file",
                    "origin_verification": "operator_declared",
                    "source_sha256": imported["source_sha256"],
                },
            }
        if lost.is_set():
            raise V2Error("ownership_lost", "Ingestion ownership lost")
        quality = normalize_source(
            source["source_path"],
            output,
            metadata=source["metadata"],
            instrument=snapshot,
            cancelled=lost.is_set,
        )
        identity = {
            "source_sha256": source["source_sha256"],
            "metadata_sha256": metadata_hash(source["metadata"]),
            "instrument_semantic_sha256": current["semantic_sha256"],
            "trade_date": current["trade_date"].isoformat(),
            "schema_version": "spot-trades-v2",
            "transform_version": TRANSFORM,
            "lock_sha256": execution_identity()["lock_sha256"],
        }
        version = digest(identity)
        manifest = {
            "schema": "dataset-manifest-v2",
            "dataset_version_id": version,
            "identity": identity,
            "instrument": snapshot,
            "metadata": source["metadata"],
            "source": source["provenance"],
            "build": execution_identity(),
            "quality": quality,
            "artifact": {
                "path": "trades.parquet",
                "sha256": quality["parquet_sha256"],
                "bytes": quality["parquet_bytes"],
            },
        }
        for filename, value in (("quality.json", quality), ("manifest.json", manifest)):
            content = canonical_json(value)
            if len(content) > 64 * 1024:
                raise V2Error("integrity_failure", "Dataset metadata exceeds limit")
            with (output / filename).open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        verify_dataset(output, cancelled=lost.is_set)
        final_relative = f"datasets-v2/{version}"
        final = safe_path(root, final_relative)
        final.parent.mkdir(parents=True, exist_ok=True)
        # Preverification loop handles a concurrently-created winner outside DB locks.
        for _ in range(4):
            existing_hash = None
            if final.exists():
                found = verify_dataset(final, cancelled=lost.is_set)
                if found["dataset_version_id"] != version:
                    raise V2Error("integrity_failure", "Existing dataset identity mismatch")
                for field in (
                    "raw_rows",
                    "accepted_rows",
                    "duplicate_rows",
                    "conflict_rows",
                    "logical_sha256",
                    "observed_from",
                    "observed_through",
                ):
                    if found["quality"][field] != quality[field]:
                        raise V2Error(
                            "integrity_failure", "Existing dataset differs from verified source"
                        )
                existing_hash = sha256_file(final / "manifest.json")
            retry = False
            with transaction(engine) as connection:
                job = jobs.fence(connection, current)
                lock(connection, "v2-version:" + version)
                catalog = one(
                    connection,
                    "SELECT * FROM v2_dataset_versions WHERE dataset_version_id=:id",
                    id=version,
                )
                if final.exists() and existing_hash is None:
                    retry = True
                else:
                    if final.exists():
                        if sha256_file(final / "manifest.json") != existing_hash:
                            raise V2Error("integrity_failure", "Dataset changed after verification")
                        if catalog is not None and catalog["manifest_sha256"] != existing_hash:
                            raise V2Error(
                                "integrity_failure", "Registered manifest integrity failure"
                            )
                    elif catalog is not None:
                        raise V2Error("integrity_failure", "Registered dataset is missing")
                    else:
                        output.rename(final)
                    jobs.fence(connection, current)
                    winning_quality = found["quality"] if existing_hash is not None else quality
                    if catalog is None:
                        execute(
                            connection,
                            "INSERT INTO v2_dataset_versions VALUES "
                            "(:id,:instrument,:semantic,:day,"
                            ":source,:metadata,:logical,:manifest,'spot-trades-v2',:transform,:lock,:path,"
                            ":rows,:first,:last,clock_timestamp())",
                            id=version,
                            instrument=current["instrument_id"],
                            semantic=current["semantic_sha256"],
                            day=current["trade_date"],
                            source=identity["source_sha256"],
                            metadata=identity["metadata_sha256"],
                            logical=winning_quality["logical_sha256"],
                            manifest=sha256_file(final / "manifest.json"),
                            transform=TRANSFORM,
                            lock=identity["lock_sha256"],
                            path=final_relative + "/manifest.json",
                            rows=winning_quality["accepted_rows"],
                            first=winning_quality["observed_from"],
                            last=winning_quality["observed_through"],
                        )
                    jobs.finish(connection, job, "succeeded", "succeeded", version=version)
                    retained = sum(p.stat().st_size for p in final.iterdir() if p.is_file())
                    # A reused winner is charged by its original successful reservation.
                    _reconcile(
                        connection,
                        current,
                        "output",
                        retained if existing_hash is None else 0,
                        final_relative if existing_hash is None else None,
                    )
                    source_bytes = sum(p.stat().st_size for p in attempt.rglob("*") if p.is_file())
                    _reconcile(connection, current, "scratch", source_bytes)
                    return manifest if existing_hash is None else found
            if not retry:
                break
        raise V2Error("integrity_failure", "Concurrent publication did not settle")
    except Exception as error:
        jobs.fail(engine, current, error)
        raise
    finally:
        done.set()
        renewer.join(timeout=15)


def work(
    engine: Engine,
    root: Path,
    *,
    max_jobs: int = 1,
    submission_id: str | None = None,
    wait_seconds: int = 0,
    stop_event: threading.Event | None = None,
) -> dict[str, int]:
    if (
        type(max_jobs) is not int
        or not 1 <= max_jobs <= 62
        or type(wait_seconds) is not int
        or not 0 <= wait_seconds <= 3600
    ):
        raise V2Error("invalid_request", "Invalid worker bounds")
    end = time.monotonic() + wait_seconds
    attempted = succeeded = failed = 0
    stop = stop_event or threading.Event()
    expire_staging(engine, root)
    while attempted < max_jobs and not stop.is_set():
        current = jobs.claim(engine, submission_id)
        if current is None:
            if time.monotonic() >= end:
                break
            stop.wait(min(0.25, max(0.0, end - time.monotonic())))
            continue
        attempted += 1
        try:
            run_claim(engine, root, current)
            succeeded += 1
        except Exception:
            failed += 1
    return {"attempted_jobs": attempted, "succeeded_jobs": succeeded, "failed_jobs": failed}
