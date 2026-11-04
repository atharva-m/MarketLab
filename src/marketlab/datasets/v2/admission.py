"""Root-bound logical quota and native admission, separate from physical space."""

import hashlib
import json
import os
import shutil
import stat as stat_mode
from collections.abc import Iterable
from contextlib import nullcontext
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.engine import Connection, Engine

from . import native_children, native_identity
from .capacity import capacity_root
from .common import V2Error, canonical_json, digest, safe_path, sha256_file
from .core import execute, lock, one, transaction

DATA_LIMIT = 100 * 1024**3
OUTPUT_LIMIT = 4 * 1024**3 + 128 * 1024
MEMO_OUTPUT_LIMIT = 1024**2


def safe_root(root: Path) -> Path:
    absolute = root.absolute()
    for path in (absolute, *absolute.parents):
        if path.is_symlink() or path.is_junction():
            raise V2Error("integrity_failure", "Storage root contains an unsafe link")
    return capacity_root(root)


def binding(connection: Connection, root: Path | None = None) -> dict[str, Any] | None:
    if execute(connection, "SELECT to_regclass('alembic_version')").scalar_one() is not None:
        revision = execute(
            connection, "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
        if revision == "0011_v2_copilot_memos":
            for required in (
                "v2_copilot_jobs",
                "v2_copilot_calls",
                "v2_memo_jobs",
                "v2_memo_calls",
                "v2_memo_results",
            ):
                if (
                    execute(connection, "SELECT to_regclass(:name)", name=required).scalar_one()
                    is None
                ):
                    raise V2Error("integrity_failure", "Required inference ledger is missing")
    if execute(connection, "SELECT to_regclass('v2_capacity_roots')").scalar_one() is None:
        if execute(connection, "SELECT to_regclass('alembic_version')").scalar_one() is not None:
            revision = execute(
                connection, "SELECT version_num FROM alembic_version"
            ).scalar_one_or_none()
            if revision in {"0010_v2_browser_imports", "0011_v2_copilot_memos"}:
                raise V2Error("integrity_failure", "Required capacity ledger is missing")
        return None
    row = one(connection, "SELECT * FROM v2_capacity_roots WHERE singleton")
    if row is not None and root is not None and row["root_path"] != str(capacity_root(root)):
        raise V2Error("unavailable", "Storage root binding mismatch")
    return row


def require(connection: Connection, root: Path) -> dict[str, Any]:
    row = binding(connection, root)
    if row is None or not row["ready"] or row["schema_version"] != "local-capacity-v1":
        raise V2Error("unavailable", "Storage admission initialization required")
    if digest(json.loads(row["receipt_json"])) != row["receipt_sha256"]:
        raise V2Error("integrity_failure", "Storage inventory receipt mismatch")
    return row


def _epoch(connection: Connection) -> str:
    # Capture identities/counts, not wall-clock alone. Cooperating writers are
    # blocked by unready intake, and this detects catalog changes during scan.
    values = hashlib.sha256()
    for table, order in (
        ("dataset_versions", "dataset_version_id"),
        ("v2_dataset_versions", "dataset_version_id"),
        ("research_results", "run_id"),
        ("v2_research_results", "run_id"),
        ("v2_storage_reservations", "reservation_id"),
        ("v2_research_reservations", "reservation_id"),
        ("v2_memo_jobs", "run_id"),
        ("v2_memo_results", "run_id"),
        ("v2_memo_attempts", "run_id,attempt_number"),
        ("v2_memo_calls", "run_id,call_number"),
        ("v2_data_charges", "charge_id"),
    ):
        if execute(connection, "SELECT to_regclass(:name)", name=table).scalar_one():
            for item in execute(
                connection, f"SELECT row_to_json(t)::text FROM {table} t ORDER BY {order}"
            ).yield_per(100):
                values.update(canonical_json([table, item[0]]))
    return values.hexdigest()


def _files(root: Path, *, hashes: bool = True, missing: Any = None) -> Any:
    # os.walk retains one directory's entries, not an entire catalog inventory.
    def failed(error: OSError) -> None:
        if isinstance(error, FileNotFoundError) and missing is not None and error.filename:
            relative = Path(error.filename).relative_to(walk_root).as_posix()
            if missing(relative):
                return
        raise V2Error("integrity_failure", "Storage inventory directory is unreadable") from error

    for ancestor in (root, *root.parents):
        if ancestor.is_symlink() or ancestor.is_junction():
            raise V2Error("integrity_failure", "Storage root contains an unsafe link")
    walk_root = safe_path(root, "inventory-anchor").parent
    for directory, directories, names in os.walk(walk_root, followlinks=False, onerror=failed):
        for name in directories:
            if (Path(directory) / name).is_symlink() or (Path(directory) / name).is_junction():
                raise V2Error("integrity_failure", "Storage inventory contains a symlink")
        for name in names:
            path = Path(directory) / name
            relative = path.relative_to(walk_root).as_posix()
            if path.is_symlink() or path.is_junction():
                raise V2Error("integrity_failure", "Storage inventory contains an unsafe file")
            try:
                stat = path.stat()
            except FileNotFoundError:
                if missing is not None and missing(relative):
                    continue
                raise
            if not stat_mode.S_ISREG(stat.st_mode):
                raise V2Error("integrity_failure", "Storage inventory contains an unsafe file")
            safe_path(root, relative)
            yield (
                relative,
                stat.st_size,
                stat.st_mtime_ns,
                sha256_file(path) if hashes else "",
            )


def initialize(engine: Engine, root: Path) -> dict[str, Any]:
    """Explicit quiesced operator reconciliation; never silently rebind a DB."""
    root = safe_root(root)
    root.mkdir(parents=True, exist_ok=True)
    reconcile_dead(engine, root)
    with transaction(engine) as connection:
        lock(connection, "v2-space:" + str(root))
        row = binding(connection, root)
        if row is None:
            identifier = uuid4()
            execute(
                connection,
                "INSERT INTO v2_capacity_roots "
                "(root_id,singleton,root_path,schema_version,ready,created_at,updated_at) "
                "VALUES (:id,true,:path,'local-capacity-v1',false,"
                "clock_timestamp(),clock_timestamp())",
                id=identifier,
                path=str(root),
            )
            row = binding(connection, root)
        assert row is not None
        execute(
            connection,
            "UPDATE v2_capacity_roots SET ready=false,epoch=epoch+1,"
            "updated_at=clock_timestamp() WHERE root_id=:id",
            id=row["root_id"],
        )
        active = execute(
            connection,
            "SELECT count(*) FROM v2_admission_tickets WHERE root_id=:id AND state<>'released'",
            id=row["root_id"],
        ).scalar_one()
        initialization_epoch = row["epoch"] + 1
        epoch = _epoch(connection)
    if active:
        raise V2Error("capacity_exceeded", "Owned storage writers must drain before inventory")
    # Check all registered artifacts before trusting a data-byte baseline.
    from .catalog import inspect_version

    with engine.connect() as connection:
        for table in ("dataset_versions", "v2_dataset_versions"):
            for result in execute(connection, f"SELECT dataset_version_id FROM {table}").yield_per(
                100
            ):
                inspect_version(engine, root, result[0])
        for prefix in ("", "v2_"):
            table = prefix + "research_results"
            if execute(connection, "SELECT to_regclass(:table)", table=table).scalar_one() is None:
                continue
            for result in execute(connection, f"SELECT run_id FROM {table}").yield_per(100):
                identity = str(result[0])
                if prefix:
                    from marketlab.research.v2 import store as v2_store
                    from marketlab.research.v2.service import verify_directory as verify_v2

                    info = v2_store.inspect(engine, identity)
                    path = safe_path(root, f"research-v2/{identity}")
                    manifest = verify_v2(path, identity, info["fingerprint"])
                else:
                    from marketlab.research import store as legacy_store
                    from marketlab.research.service import verify_directory as verify_legacy

                    info = legacy_store.inspect(engine, identity)
                    path = safe_path(root, f"research/{identity}")
                    manifest = verify_legacy(path, identity, info["fingerprint"])
                registered = one(connection, f"SELECT * FROM {table} WHERE run_id=:id", id=identity)
                assert registered is not None
                if sha256_file(path / "manifest.json") != registered["manifest_sha256"]:
                    raise V2Error("integrity_failure", "Research manifest registration mismatch")
                for kind in ("results", "summary"):
                    if (
                        manifest["artifacts"][kind + ".json"]["sha256"]
                        != registered[kind + "_sha256"]
                    ):
                        raise V2Error(
                            "integrity_failure", "Research artifact registration mismatch"
                        )
        if execute(connection, "SELECT to_regclass('v2_memo_results')").scalar_one() is not None:
            from marketlab.memos.v2.service import verify_directory as verify_memo
            from marketlab.memos.v2.store import inspect as memo_inspect

            for result in execute(connection, "SELECT * FROM v2_memo_results").mappings():
                info = memo_inspect(engine, str(result["run_id"]))
                manifest, _ = verify_memo(
                    safe_path(root, result["relative_path"]), info, result["manifest_sha256"]
                )
                if any(
                    manifest["artifacts"][name + "." + extension]["sha256"] != result[field]
                    for name, extension, field in (
                        ("memo", "txt", "memo_sha256"),
                        ("facts", "json", "facts_sha256"),
                    )
                ):
                    raise V2Error("integrity_failure", "Memo registration mismatch")
    total, count, inventory = 0, 0, hashlib.sha256()
    for relative, size, modified, sha in _files(root):
        total += size
        count += 1
        inventory.update(canonical_json([relative, size, modified, sha]))
        with transaction(engine) as connection:
            execute(
                connection,
                "INSERT INTO v2_capacity_files VALUES (:id,:epoch,:path,:bytes,:mtime,:sha)",
                id=row["root_id"],
                epoch=initialization_epoch,
                path=relative,
                bytes=size,
                mtime=modified,
                sha=sha,
            )
    with transaction(engine) as connection:
        lock(connection, "v2-space:" + str(root))
        latest = binding(connection, root)
        if (
            latest is None
            or latest["ready"]
            or latest["epoch"] != initialization_epoch
            or _epoch(connection) != epoch
        ):
            raise V2Error("unavailable", "Storage inventory changed during reconciliation")
        for item in (
            execute(
                connection,
                "SELECT * FROM v2_capacity_files WHERE root_id=:id AND inventory_epoch=:epoch",
                id=row["root_id"],
                epoch=initialization_epoch,
            )
            .mappings()
            .yield_per(100)
        ):
            stat = safe_path(root, item["relative_path"]).stat()
            if stat.st_size != item["file_bytes"] or stat.st_mtime_ns != item["mtime_ns"]:
                raise V2Error("unavailable", "Storage inventory changed during reconciliation")
        # Existing unconsumed DATA reservations are conservative until next audit.
        pending = int(
            execute(
                connection,
                "SELECT coalesce(sum(reserved_bytes),0) FROM "
                "v2_storage_reservations WHERE state<>'released' AND kind<>'scratch'",
            ).scalar_one()
        )
        pending += int(
            execute(
                connection,
                "SELECT coalesce(sum(output_bytes),0) FROM "
                "v2_research_reservations WHERE state<>'released'",
            ).scalar_one()
        )
        receipt = {
            "schema": "local-capacity-v1",
            "root_id": str(row["root_id"]),
            "root_path": str(root),
            "file_count": count,
            "retained_bytes": total,
            "reserved_bytes": pending,
            "inventory_sha256": inventory.hexdigest(),
            "catalog_epoch": epoch,
            "epoch": latest["epoch"],
        }
        execute(
            connection,
            "UPDATE v2_data_charges SET state='absorbed' WHERE root_id=:id "
            "AND state IN ('reserved','retained')",
            id=row["root_id"],
        )
        execute(
            connection,
            "UPDATE v2_capacity_roots SET ready=true,baseline_bytes=:bytes,"
            "receipt_sha256=:sha,receipt_json=:receipt,updated_at=clock_timestamp() "
            "WHERE root_id=:id",
            id=row["root_id"],
            bytes=total + pending,
            sha=digest(receipt),
            receipt=canonical_json(receipt).decode(),
        )
    return receipt


def audit(engine: Engine, root: Path) -> None:
    """Detect changed baseline/unmanaged bytes before new work, outside row locks."""
    # Exact inventories, active-owner projection and expected_count all use one
    # repeatable-read snapshot. A legitimate inventory commit cannot change the
    # denominator halfway through this filesystem walk.
    reconcile_dead(engine, safe_root(root))
    for _ in range(3):
        try:
            with engine.connect().execution_options(isolation_level="REPEATABLE READ") as snapshot:
                with snapshot.begin():
                    _audit(engine, root, snapshot)
            return
        except V2Error as error:
            if error.code != "audit_changed":
                raise
    raise V2Error("unavailable", "Storage inventory changed during admission; retry")


def _file_epoch(row: dict[str, Any]) -> int:
    value = json.loads(row["receipt_json"])["epoch"]
    if type(value) is not int or value < 1:
        raise V2Error("integrity_failure", "Invalid storage inventory epoch")
    return value


def mark_auxiliary_path(engine: Engine, ticket: dict[str, Any] | None, relative: str) -> None:
    if ticket is None:
        return
    safe_path(Path(ticket["root"]), relative)
    with transaction(engine) as connection:
        owner = one(
            connection,
            "SELECT root_id,resource_id FROM v2_admission_tickets "
            "WHERE ticket_id=:id AND owner=:owner AND state<>'released'",
            id=ticket["ticket_id"],
            owner=ticket["owner"],
        )
        if owner is None:
            raise V2Error("ownership_lost", "Auxiliary path admission unavailable")
        execute(
            connection,
            "INSERT INTO v2_data_charges VALUES "
            "(:id,:root,:ticket,:resource,0,0,'reserved',:path,clock_timestamp(),clock_timestamp())",
            id=uuid4(),
            root=owner["root_id"],
            ticket=ticket["ticket_id"],
            resource=owner["resource_id"],
            path=relative,
        )
        changed(connection, ticket)


def changed(connection: Connection, ticket: dict[str, Any] | None) -> None:
    """Monotonic ownership epoch, in the same transaction before managed file I/O."""
    if ticket is not None:
        execute(
            connection,
            "UPDATE v2_capacity_roots SET epoch=epoch+1,"
            "updated_at=clock_timestamp() WHERE root_id=(SELECT root_id FROM "
            "v2_admission_tickets WHERE ticket_id=:id AND owner=:owner)",
            id=ticket["ticket_id"],
            owner=ticket["owner"],
        )


def reconcile_dead(engine: Engine, root: Path) -> None:
    """Inventory exact dead-owned bytes before retiring admission, without deletion."""
    with engine.connect() as connection:
        bound = binding(connection, root)
        if bound is None:
            return
        candidates = (
            execute(
                connection,
                "SELECT * FROM v2_admission_tickets WHERE root_id=:id "
                "AND state<>'released' ORDER BY created_at LIMIT 12",
                id=bound["root_id"],
            )
            .mappings()
            .all()
        )
    for candidate in candidates:
        native = json.loads(candidate["native_identity"])
        if not native_children.dead(native):
            continue  # Live, foreign, unreadable and unresolved launch retain ownership.
        parsed = native_children.envelope(native)
        assert parsed is not None
        with engine.connect() as connection:
            charge = one(
                connection,
                "SELECT charge_id,ceiling_bytes FROM v2_data_charges "
                "WHERE ticket_id=:id ORDER BY ceiling_bytes DESC,created_at LIMIT 1",
                id=candidate["ticket_id"],
            )
            paths = set(
                execute(
                    connection,
                    "SELECT relative_path FROM v2_data_charges WHERE "
                    "ticket_id=:id AND relative_path IS NOT NULL",
                    id=candidate["ticket_id"],
                ).scalars()
            )
            generation = one(
                connection,
                "SELECT * FROM v2_upload_generations WHERE ticket_id=:id",
                id=candidate["ticket_id"],
            )
        if charge is None:
            raise V2Error("integrity_failure", "Dead admission charge is missing")
        ticket = {
            "ticket_id": str(candidate["ticket_id"]),
            "charge_id": str(charge["charge_id"]),
            "owner": str(candidate["owner"]),
            "identity": parsed["process"],
            "root": str(root),
        }
        retained_source = None
        if generation is not None:
            paths.add(generation["relative_path"])
            path = safe_path(root, generation["relative_path"])
            retained_source = path.stat().st_size if path.exists() else 0
            if retained_source > generation["declared_bytes"]:
                raise V2Error("integrity_failure", "Dead upload exceeds its reserved ceiling")
        if candidate["role"] == "ingestion" and candidate["resource_id"] is not None:
            paths.add(f"attempts-v2/{candidate['resource_id']}/{candidate['fencing_token']}")
        for path in paths:
            inventory_owned(engine, ticket, path)
        with transaction(engine) as connection:
            lock(connection, "v2-space:" + str(root))
            current = one(
                connection,
                "SELECT * FROM v2_admission_tickets WHERE ticket_id=:id FOR UPDATE",
                id=candidate["ticket_id"],
            )
            if (
                current is None
                or current["native_identity"] != candidate["native_identity"]
                or current["state"] == "released"
                or not native_children.dead(json.loads(current["native_identity"]))
            ):
                continue
            if generation is not None and retained_source is not None:
                execute(
                    connection,
                    "UPDATE v2_storage_reservations SET reserved_bytes=0,"
                    "retained_bytes=:bytes,state=:state,updated_at=clock_timestamp() "
                    "WHERE reservation_id=:id",
                    bytes=retained_source,
                    state="retained" if retained_source else "released",
                    id=generation["reservation_id"],
                )
                execute(
                    connection,
                    "UPDATE v2_data_charges SET charged_bytes=:bytes,state=:state "
                    "WHERE charge_id=:id AND state IN ('reserved','retained')",
                    bytes=retained_source,
                    state="retained" if retained_source else "released",
                    id=charge["charge_id"],
                )
            # Numerical attempt leftovers keep their full conservative data/space
            # charge until separately verified reconciliation/cleanup.
            execute(
                connection,
                "UPDATE v2_admission_tickets SET state='released',physical_bytes=0,"
                "updated_at=clock_timestamp() WHERE ticket_id=:id",
                id=candidate["ticket_id"],
            )


def _audit(engine: Engine, root: Path, snapshot: Connection) -> None:
    root = safe_root(root)
    with nullcontext(snapshot) as connection:
        row = require(connection, root)
    file_epoch = _file_epoch(row)

    def removed(relative: str) -> bool:
        known = one(
            snapshot,
            "SELECT 1 FROM v2_capacity_files WHERE root_id=:id "
            "AND inventory_epoch=:epoch AND relative_path=:path",
            id=row["root_id"],
            epoch=file_epoch,
            path=relative,
        )
        if known is not None:
            return False  # Missing immutable/retained files are never transient.
        owners = execute(
            snapshot,
            "SELECT t.native_identity FROM v2_admission_tickets t "
            "JOIN v2_data_charges c USING(ticket_id) WHERE t.root_id=:id AND "
            "t.state IN ('pending','active','draining') AND ("
            "(c.relative_path IS NOT NULL AND (:path=c.relative_path OR "
            ":path LIKE c.relative_path||'/%')) OR (t.role='ingestion' AND "
            ":path LIKE 'attempts-v2/'||t.resource_id::text||'/'||t.fencing_token::text||'/%') OR "
            "(t.role='research' AND EXISTS(SELECT 1 FROM v2_research_reservations r WHERE "
            "r.run_id=t.resource_id AND r.state='active' AND :path LIKE r.relative_root||'/%')) OR "
            "(t.role='legacy' AND (:path LIKE '.staging/%' OR :path LIKE '.downloads/%'))) "
            "LIMIT 12",
            id=row["root_id"],
            path=relative,
        ).scalars()
        return any(native_children.alive(json.loads(owner)) for owner in owners)

    try:
        seen = 0
        active_bytes: dict[str, int] = {}
        for relative, size, modified, _ in _files(root, hashes=False, missing=removed):
            with nullcontext(snapshot) as connection:
                expected = one(
                    connection,
                    "SELECT file_bytes,mtime_ns FROM v2_capacity_files "
                    "WHERE root_id=:id AND inventory_epoch=:epoch AND relative_path=:path",
                    id=row["root_id"],
                    epoch=file_epoch,
                    path=relative,
                )
                if expected is not None:
                    seen += 1
                    if expected["file_bytes"] != size or expected["mtime_ns"] != modified:
                        raise V2Error("integrity_failure", "Storage baseline file changed")
                else:
                    owners = execute(
                        connection,
                        "SELECT DISTINCT t.ticket_id,t.native_identity,t.role,"
                        "t.physical_bytes,(SELECT max(ceiling_bytes) FROM v2_data_charges x "
                        "WHERE x.ticket_id=t.ticket_id) AS data_ceiling "
                        "FROM v2_admission_tickets t "
                        "JOIN v2_data_charges c USING(ticket_id) WHERE t.root_id=:id AND "
                        "t.state IN ('pending','active','draining') AND ("
                        "(c.relative_path IS NOT NULL AND (:path=c.relative_path OR "
                        ":path LIKE c.relative_path||'/%')) OR "
                        "(t.role='upload' AND EXISTS(SELECT 1 FROM v2_upload_generations g WHERE "
                        "g.ticket_id=t.ticket_id AND g.state<>'issued' "
                        "AND g.relative_path=:path)) OR "
                        "(t.role='ingestion' AND :path LIKE 'attempts-v2/'||"
                        "t.resource_id::text||'/'||t.fencing_token::text||'/%') OR "
                        "(t.role='research' AND EXISTS(SELECT 1 FROM v2_research_reservations r "
                        "WHERE r.run_id=t.resource_id AND r.state='active' "
                        "AND :path LIKE r.relative_root||'/%')) OR (t.role='legacy' AND "
                        "(:path LIKE '.staging/%' OR :path LIKE '.downloads/%'))) "
                        "ORDER BY t.ticket_id LIMIT 12",
                        id=row["root_id"],
                        path=relative,
                    ).mappings()
                    managed = False
                    for owner in owners:
                        if not native_children.alive(json.loads(owner["native_identity"])):
                            continue
                        ceiling = {
                            "upload": owner["data_ceiling"],
                            "ingestion": 20 * 1024**3 + OUTPUT_LIMIT,
                            "research": 22 * 1024**3 + 34 * 1024**2,
                            "legacy": max(owner["physical_bytes"], owner["data_ceiling"]),
                            "memo": MEMO_OUTPUT_LIMIT,
                        }[owner["role"]]
                        key = str(owner["ticket_id"])
                        if active_bytes.get(key, 0) + size <= ceiling:
                            active_bytes[key] = active_bytes.get(key, 0) + size
                            managed = True
                            break
                    if not managed:
                        raise V2Error(
                            "integrity_failure", "Unmanaged storage bytes require reconciliation"
                        )
        with nullcontext(snapshot) as connection:
            expected_count = execute(
                connection,
                "SELECT count(*) FROM v2_capacity_files WHERE "
                "root_id=:id AND inventory_epoch=:epoch",
                id=row["root_id"],
                epoch=file_epoch,
            ).scalar_one()
        if seen != expected_count:
            raise V2Error("integrity_failure", "Storage baseline file is missing")
    except BaseException as error:
        with transaction(engine) as connection:
            lock(connection, "v2-space:" + str(root))
            latest = binding(connection, root)
            if latest is not None and latest["epoch"] != row["epoch"]:
                raise V2Error("audit_changed", "Managed inventory changed during audit") from error
            execute(
                connection,
                "UPDATE v2_capacity_roots SET ready=false,updated_at=clock_timestamp() "
                "WHERE root_id=:id",
                id=row["root_id"],
            )
        raise


def acquire(
    engine: Engine,
    root: Path,
    role: str,
    data_bytes: int = 0,
    resource: str | None = None,
    physical_bytes: int = 0,
) -> dict[str, Any] | None:
    """Reserve before work-row locks. None means an unbound historical root."""
    root = safe_root(root)
    with engine.connect() as connection:
        existing = binding(connection, root)
    if existing is None:
        with engine.connect() as connection:
            if execute(connection, "SELECT to_regclass('v2_capacity_roots')").scalar_one():
                raise V2Error("unavailable", "Storage admission initialization required")
        return None
    audit(engine, root)
    identity = native_identity.current()
    ticket, charge, owner = uuid4(), uuid4(), uuid4()
    with transaction(engine) as connection:
        lock(connection, "v2-space:" + str(root))
        row = require(connection, root)
        # Recover only direct native death evidence; charges remain conservative.
        active = (
            execute(
                connection,
                "SELECT * FROM v2_admission_tickets WHERE root_id=:id AND state<>'released'",
                id=row["root_id"],
            )
            .mappings()
            .all()
        )
        for old in active:
            if native_children.dead(json.loads(old["native_identity"])):
                execute(
                    connection,
                    "UPDATE v2_admission_tickets SET state='released',"
                    "updated_at=clock_timestamp() WHERE ticket_id=:id",
                    id=old["ticket_id"],
                )
        if role not in {"upload", "ingestion", "research", "legacy", "memo"}:
            raise V2Error("invalid_request", "Unknown local admission role")
        selected = (
            "role='upload'" if role == "upload" else "role IN ('ingestion','research','legacy')"
        )
        count = execute(
            connection,
            "SELECT count(*) FROM v2_admission_tickets WHERE root_id=:id "
            "AND state<>'released' AND " + selected,
            id=row["root_id"],
        ).scalar_one()
        used = row["baseline_bytes"] + int(
            execute(
                connection,
                "SELECT coalesce(sum(charged_bytes),0) "
                "FROM v2_data_charges WHERE root_id=:id AND state IN ('reserved','retained')",
                id=row["root_id"],
            ).scalar_one()
        )
        if (
            role != "memo" and count >= (4 if role == "upload" else 8)
        ) or used + data_bytes > DATA_LIMIT:
            raise V2Error("capacity_exceeded", "Local admission capacity is unavailable")
        from .capacity import outstanding

        if shutil.disk_usage(root).free < outstanding(connection) + physical_bytes:
            raise V2Error("capacity_exceeded", "Physical admission capacity is unavailable")
        execute(
            connection,
            "INSERT INTO v2_admission_tickets VALUES "
            "(:id,:root,:role,:resource,NULL,NULL,NULL,:owner,:native,:physical,"
            "'pending',clock_timestamp(),clock_timestamp())",
            id=ticket,
            root=row["root_id"],
            role=role,
            resource=resource,
            owner=owner,
            native=canonical_json(identity).decode(),
            physical=physical_bytes,
        )
        execute(
            connection,
            "INSERT INTO v2_data_charges VALUES "
            "(:id,:root,:ticket,:resource,:bytes,:bytes,'reserved',NULL,clock_timestamp(),clock_timestamp())",
            id=charge,
            root=row["root_id"],
            ticket=ticket,
            resource=resource,
            bytes=data_bytes,
        )
        changed(connection, {"ticket_id": str(ticket), "owner": str(owner)})
    return {
        "ticket_id": str(ticket),
        "charge_id": str(charge),
        "owner": str(owner),
        "identity": identity,
        "root": str(root),
    }


def root_for(engine: Engine, *, historical: bool = False) -> Path | None:
    with engine.connect() as connection:
        translated = engine.get_execution_options().get("schema_translate_map", {}).get(None)
        if (
            translated is not None
            and execute(
                connection, "SELECT to_regclass(:name)", name=f"{translated}.v2_capacity_roots"
            ).scalar_one()
            is None
        ):
            return None
        row = binding(connection)
        if row is None:
            if (
                not historical
                and execute(connection, "SELECT to_regclass('v2_capacity_roots')").scalar_one()
            ):
                raise V2Error("unavailable", "Storage admission initialization required")
            return None
        return Path(row["root_path"])


def complete_legacy(engine: Engine, ticket: dict[str, Any] | None) -> None:
    """Register exact new immutable legacy files once after the owning call drains."""
    if ticket is None:
        return
    root = Path(ticket["root"])
    with engine.connect() as connection:
        charge = one(
            connection,
            "SELECT relative_path FROM v2_data_charges WHERE charge_id=:id",
            id=ticket["charge_id"],
        )
        row = binding(connection, root)
        if row is None:
            raise V2Error("integrity_failure", "Storage root binding disappeared")
    if charge is None or charge["relative_path"] is None:
        finish(engine, ticket)  # Uncertain failure retains its entire conservative data charge.
        return
    target = safe_path(root, charge["relative_path"])
    retained = inventory_owned(engine, ticket, charge["relative_path"]) if target.exists() else 0
    finish(engine, ticket, retained, charge["relative_path"])


def inventory_owned(engine: Engine, ticket: dict[str, Any] | None, relative: str) -> int:
    """Record exact immutable/drained file identities before an active path is retired."""
    if ticket is None:
        return 0
    root = Path(ticket["root"])
    target = safe_path(root, relative)
    if not target.exists():
        return 0
    entries: Iterable[tuple[str, int, int, str]]
    if target.is_file():
        stat = target.stat()
        entries = [(relative, stat.st_size, stat.st_mtime_ns, sha256_file(target))]
    else:
        entries = (
            (str(Path(relative) / name).replace("\\", "/"), size, modified, sha)
            for name, size, modified, sha in _files(target)
        )
    retained = 0
    for path, size, modified, sha in entries:
        with transaction(engine) as connection:
            lock(connection, "v2-space:" + str(root))
            row = binding(connection, root)
            if row is None:
                raise V2Error("integrity_failure", "Storage root binding disappeared")
            stat = safe_path(root, path).stat()
            if stat.st_size != size or stat.st_mtime_ns != modified:
                raise V2Error("integrity_failure", "Owned file changed during inventory")
            old = one(
                connection,
                "SELECT * FROM v2_capacity_files WHERE root_id=:id "
                "AND inventory_epoch=:epoch AND relative_path=:path",
                id=row["root_id"],
                epoch=_file_epoch(row),
                path=path,
            )
            if old is not None:
                if (
                    old["file_bytes"] != size
                    or old["mtime_ns"] != modified
                    or old["content_sha256"] != sha
                ):
                    raise V2Error("integrity_failure", "Retained owned file identity changed")
            else:
                execute(
                    connection,
                    "INSERT INTO v2_capacity_files VALUES "
                    "(:root,:epoch,:path,:size,:modified,:sha)",
                    root=row["root_id"],
                    epoch=_file_epoch(row),
                    path=path,
                    size=size,
                    modified=modified,
                    sha=sha,
                )
                retained += size
                execute(
                    connection,
                    "UPDATE v2_capacity_roots SET epoch=epoch+1,"
                    "updated_at=clock_timestamp() WHERE root_id=:id",
                    id=row["root_id"],
                )
    return retained


def transfer(connection: Connection, ticket: dict[str, Any] | None) -> None:
    """Under root lock atomically hand physical reservation to its existing ledger."""
    if ticket is not None:
        execute(
            connection,
            "UPDATE v2_admission_tickets SET physical_bytes=0 WHERE ticket_id=:id "
            "AND owner=:owner AND state<>'released'",
            id=ticket["ticket_id"],
            owner=ticket["owner"],
        )


def mark_path(engine: Engine, ticket: dict[str, Any] | None, relative: str) -> None:
    if ticket is None:
        return
    safe_path(Path(ticket["root"]), relative)
    with transaction(engine) as connection:
        execute(
            connection,
            "UPDATE v2_data_charges SET relative_path=:path WHERE charge_id=:id "
            "AND ticket_id=:ticket AND state='reserved'",
            path=relative,
            id=ticket["charge_id"],
            ticket=ticket["ticket_id"],
        )
        changed(connection, ticket)


def activate(
    connection: Connection,
    ticket: dict[str, Any] | None,
    resource: Any,
    attempt: int | None = None,
    token: int | None = None,
    generation: Any = None,
) -> None:
    if ticket is None:
        return
    result = execute(
        connection,
        "UPDATE v2_admission_tickets SET resource_id=:resource,"
        "generation_id=:generation,attempt_number=:attempt,fencing_token=:token,state='active',"
        "updated_at=clock_timestamp() WHERE ticket_id=:id AND owner=:owner AND state='pending' "
        "RETURNING ticket_id",
        resource=resource,
        generation=generation,
        attempt=attempt,
        token=token,
        id=ticket["ticket_id"],
        owner=ticket["owner"],
    ).first()
    if result is None:
        raise V2Error("ownership_lost", "Admission ticket is no longer available")
    changed(connection, ticket)


def finish(
    engine: Engine,
    ticket: dict[str, Any] | None,
    retained: int | None = None,
    relative: str | None = None,
) -> None:
    """Caller invokes after exact operation/threads have drained, never on timeout."""
    if ticket is None:
        return
    if not native_identity.same(ticket["identity"]):
        raise V2Error("ownership_lost", "Admission native owner mismatch")
    with transaction(engine) as connection:
        lock(connection, "v2-space:" + ticket["root"])
        row = one(
            connection,
            "SELECT * FROM v2_admission_tickets WHERE ticket_id=:id FOR UPDATE",
            id=ticket["ticket_id"],
        )
        if row is None or str(row["owner"]) != ticket["owner"]:
            raise V2Error("ownership_lost", "Admission owner mismatch")
        if row["state"] == "released":
            return
        if native_children.pending(json.loads(row["native_identity"])):
            execute(
                connection,
                "UPDATE v2_admission_tickets SET state='draining' WHERE ticket_id=:id",
                id=ticket["ticket_id"],
            )
            return  # Ambiguous child launch never releases a live/unknown native slot.
        if retained is not None:
            execute(
                connection,
                "UPDATE v2_data_charges SET charged_bytes=:bytes,state=:state,"
                "relative_path=:path,updated_at=clock_timestamp() WHERE charge_id=:id "
                "AND state IN ('reserved','retained')",
                bytes=retained,
                state="retained" if retained else "released",
                path=relative,
                id=ticket["charge_id"],
            )
        execute(
            connection,
            "UPDATE v2_admission_tickets SET state='released',physical_bytes=0,"
            "updated_at=clock_timestamp() "
            "WHERE ticket_id=:id",
            id=ticket["ticket_id"],
        )
        changed(connection, ticket)
