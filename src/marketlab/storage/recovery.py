"""Prepare a coordinated backup inventory and bind a verified isolated restore."""

import argparse
import json
from collections import defaultdict
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from typing import Any, BinaryIO, cast
from uuid import UUID, uuid4

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine

from marketlab.config import Settings
from marketlab.datasets.v2 import admission
from marketlab.datasets.v2.common import V2Error, digest, safe_path, sha256_file
from marketlab.datasets.v2.core import execute, lock, one, transaction

from . import store
from .backend import ObjectConfig, ObjectRef, S3Backend, managed_backend


class _Discard:
    def write(self, data: bytes) -> int:
        return len(data)


def _drained(connection: Connection) -> None:
    active = execute(
        connection,
        "SELECT EXISTS(SELECT 1 FROM v2_admission_tickets WHERE state<>'released') OR "
        "EXISTS(SELECT 1 FROM v2_research_reservations WHERE state='active')",
    ).scalar_one()
    if active:
        raise V2Error("capacity_exceeded", "Storage backup requires drained owned work")


def _inventory(connection: Connection) -> dict[str, Any]:
    execute(connection, "SET LOCAL TIME ZONE 'UTC'")
    _drained(connection)
    bound = admission.binding(connection)
    if bound is None or not store.enabled(connection):
        raise V2Error("integrity_failure", "Storage backup binding is missing")
    files = execute(
        connection,
        "SELECT relative_path,file_bytes,content_sha256 FROM v2_capacity_files "
        "WHERE root_id=:root AND inventory_epoch=:epoch ORDER BY relative_path",
        root=bound["root_id"],
        epoch=admission._file_epoch(bound),
    ).mappings()
    objects = execute(
        connection,
        "SELECT o.*,c.package_id,c.active,d.charged_bytes,d.state AS charge_state "
        "FROM v2_storage_objects o JOIN v2_storage_copies c USING(copy_id) "
        "JOIN v2_data_charges d USING(charge_id) WHERE o.backend_alias=:alias "
        "AND o.state='verified' ORDER BY c.copy_id,o.member",
        alias=bound["object_alias"],
    ).mappings()
    return {
        "schema": "storage-recovery-v1",
        "root_id": str(bound["root_id"]),
        "root_path": bound["root_path"],
        "object_alias": bound["object_alias"],
        "object_namespace_sha256": bound["object_namespace_sha256"],
        "epoch": bound["epoch"],
        "ledger_sha256": admission._epoch(connection),
        "local_files": [dict(row) for row in files],
        "remote_members": [
            {
                "object_id": str(row["object_id"]),
                "copy_id": str(row["copy_id"]),
                "package_id": str(row["package_id"]),
                "charge_id": str(row["charge_id"]),
                "charge_state": row["charge_state"],
                "charged_bytes": row["charged_bytes"],
                "active": row["active"],
                **vars(store._ref(row)),
            }
            for row in objects
        ],
    }


def backup_inventory(engine: Engine, root: Path) -> dict[str, Any]:
    return _backup_inventory(engine, root, Settings(), local_only=False)


def local_backup_inventory(
    engine: Engine, root: Path, settings: Settings | None = None
) -> dict[str, Any]:
    """Capture a verified local-only backup without enabling a remote storage path."""
    settings = settings if settings is not None else Settings()
    _require_local_settings(settings)
    _require_local_settings(Settings())
    with engine.connect() as connection:
        _require_local_database(connection)
    return _backup_inventory(engine, root, settings, local_only=True)


def _require_local_settings(settings: Settings) -> None:
    if settings.storage_backend != "local" or any(
        value is not None
        for value in (
            settings.storage_s3_endpoint,
            settings.storage_s3_bucket,
            settings.storage_s3_access_key,
            settings.storage_s3_secret_key,
            settings.storage_s3_session_token,
        )
    ):
        raise V2Error("storage_denied", "Local recovery requires local-only storage configuration")


def _require_local_database(connection: Connection) -> None:
    bound = admission.binding(connection)
    if bound is None or not store.enabled(connection):
        raise V2Error("integrity_failure", "Local recovery storage binding is missing")
    if bound["object_alias"] is not None or bound["object_namespace_sha256"] is not None:
        raise V2Error("storage_denied", "Local recovery cannot include an object namespace")
    for table in ("v2_storage_objects", "v2_storage_copies", "v2_data_charges"):
        if execute(
            connection,
            f"SELECT EXISTS(SELECT 1 FROM {table} WHERE backend_alias<>'local')",
        ).scalar_one():
            raise V2Error("storage_denied", "Local recovery cannot include remote storage records")


def _require_local_backup(backup: dict[str, Any]) -> None:
    if (
        backup.get("object_alias") is not None
        or backup.get("object_namespace_sha256") is not None
        or backup.get("remote_members") != []
    ):
        raise V2Error("storage_denied", "Local recovery requires an entirely local backup")


def _backup_inventory(
    engine: Engine, root: Path, settings: Settings, *, local_only: bool
) -> dict[str, Any]:
    root = admission.safe_root(root)
    admission.audit(engine, root)
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        if local_only:
            _require_local_database(connection)
        bound = admission.require(connection, root)
        snapshot = _inventory(connection)
        source_database = database_identity(connection)
    config = None if local_only else ObjectConfig.from_settings(settings)
    store.verify_namespace(bound, config)
    with ExitStack() as resources:
        backend = (
            resources.enter_context(managed_backend(S3Backend.configured(config, settings)))
            if config is not None
            else None
        )
        for row in snapshot["remote_members"]:
            if backend is None:
                raise V2Error("integrity_failure", "Remote backup backend missing")
            backend.read_verified(_ref(row), cast(BinaryIO, _Discard()))
    # Recheck after every streamed read and before handing the plan to pg_dump.
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        if local_only:
            _require_local_database(connection)
        if _inventory(connection) != snapshot or database_identity(connection) != source_database:
            raise V2Error("revision_conflict", "Storage backup inventory changed")
    snapshot["source_database"] = source_database
    return {**snapshot, "inventory_sha256": digest(snapshot)}


def database_identity(connection: Connection) -> dict[str, str]:
    try:
        row = one(
            connection,
            "SELECT c.system_identifier::text AS cluster_identifier,d.oid::text AS database_oid "
            "FROM pg_control_system() c JOIN pg_database d ON d.datname=current_database()",
        )
    except Exception:
        raise V2Error("storage_denied", "PostgreSQL database identity proof unavailable") from None
    if row is None or not all(
        isinstance(value, str) and value.isascii() and value.isdecimal() for value in row.values()
    ):
        raise V2Error("integrity_failure", "Invalid PostgreSQL database identity proof")
    return {key: row[key] for key in ("cluster_identifier", "database_oid")}


def _ref(row: dict[str, Any]) -> ObjectRef:
    return ObjectRef(
        row["alias"],
        row["key"],
        row["version"],
        row["length"],
        row["sha256"],
        row["member"],
        row["media_schema"],
    )


def rebind_restore(
    engine: Engine,
    root: Path,
    backup: dict[str, Any],
    destinations: dict[str, dict[str, str]],
    settings: Settings,
) -> dict[str, str]:
    """Rebind an already restored DB and verified copies in separate owned resources."""
    return _rebind_restore(engine, root, backup, destinations, settings, local_only=False)


def local_rebind_restore(
    engine: Engine,
    root: Path,
    backup: dict[str, Any],
    settings: Settings | None = None,
) -> dict[str, str]:
    """Verify and rebind a local-only restore in a distinct owned database and root."""
    settings = settings if settings is not None else Settings()
    _require_local_settings(settings)
    _require_local_settings(Settings())
    _require_local_backup(backup)
    with engine.connect() as connection:
        _require_local_database(connection)
    return _rebind_restore(engine, root, backup, {}, settings, local_only=True)


def _rebind_restore(
    engine: Engine,
    root: Path,
    backup: dict[str, Any],
    destinations: dict[str, dict[str, str]],
    settings: Settings,
    *,
    local_only: bool,
) -> dict[str, str]:
    root = admission.safe_root(root)
    original = {key: value for key, value in backup.items() if key != "inventory_sha256"}
    inventory = {key: value for key, value in original.items() if key != "source_database"}
    identity = original.get("source_database")
    valid_identity = (
        isinstance(identity, dict)
        and identity.keys() == {"cluster_identifier", "database_oid"}
        and all(
            isinstance(identity[key], str)
            and 0 < len(identity[key]) <= limit
            and identity[key].isascii()
            and identity[key].isdecimal()
            for key, limit in (("cluster_identifier", 20), ("database_oid", 10))
        )
    )
    if (
        not valid_identity
        or backup.get("inventory_sha256") != digest(original)
        or inventory.get("schema") != "storage-recovery-v1"
        or root == admission.safe_root(Path(inventory["root_path"]))
    ):
        raise V2Error("integrity_failure", "Invalid isolated restore inventory")
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        if local_only:
            _require_local_database(connection)
        target_database = database_identity(connection)
        if target_database == original.get("source_database"):
            raise V2Error("integrity_failure", "Restore target is the original database")
        if _inventory(connection) != inventory:
            raise V2Error("integrity_failure", "Database restore differs from backup inventory")
    old_alias = inventory["object_alias"]
    config = None if local_only else ObjectConfig.from_settings(settings)
    if (old_alias is None) != (config is None) or (
        config is not None
        and (
            config.alias == old_alias or config.fingerprint == inventory["object_namespace_sha256"]
        )
    ):
        raise V2Error("integrity_failure", "Restore requires a distinct object namespace and alias")
    for row in inventory["local_files"]:
        path = safe_path(root, row["relative_path"])
        if (
            not path.is_file()
            or path.is_junction()
            or path.stat().st_size != row["file_bytes"]
            or sha256_file(path) != row["content_sha256"]
        ):
            raise V2Error("integrity_failure", "Restored local file differs")
    expected = {row["object_id"] for row in inventory["remote_members"]}
    if destinations.keys() != expected:
        raise V2Error("integrity_failure", "Restored object receipt set differs")
    copies: dict[str, list[tuple[dict[str, Any], ObjectRef]]] = defaultdict(list)
    if config is not None:
        with engine.connect() as connection:
            if execute(
                connection,
                "SELECT EXISTS(SELECT 1 FROM v2_storage_objects WHERE backend_alias=:alias)",
                alias=config.alias,
            ).scalar_one():
                raise V2Error("integrity_failure", "Restore destination alias was already used")
        with managed_backend(S3Backend.configured(config, settings)) as backend:
            backend.require_versioning()
            for row in inventory["remote_members"]:
                location = destinations[row["object_id"]]
                if location.keys() != {"key", "version"}:
                    raise V2Error("integrity_failure", "Invalid restored object receipt")
                ref = replace(
                    _ref(row), alias=config.alias, key=location["key"], version=location["version"]
                )
                backend.read_verified(ref, cast(BinaryIO, _Discard()))
                copies[row["copy_id"]].append((row, ref))
    receipt: dict[str, str] = {}
    with transaction(engine) as connection:
        lock(connection, "v2-space:" + inventory["root_path"])
        if local_only:
            _require_local_database(connection)
        if (
            _inventory(connection) != inventory
            or database_identity(connection) != target_database
            or target_database == original.get("source_database")
        ):
            raise V2Error("revision_conflict", "Restore inventory changed")
        for old_copy, entries in copies.items():
            receipt[old_copy] = _attach_copy(connection, inventory["root_id"], old_copy, entries)
        execute(
            connection,
            "UPDATE v2_capacity_roots SET root_path=:path,object_alias=:alias,"
            "object_namespace_sha256=:sha,ready=false,epoch=epoch+1,"
            "updated_at=clock_timestamp() WHERE root_id=:root",
            path=str(root),
            alias=config.alias if config is not None else None,
            sha=config.fingerprint if config is not None else None,
            root=inventory["root_id"],
        )
    # Rebuild the local inventory and normal-reader proofs against the restored bytes.
    if local_only:
        _require_local_settings(Settings())
    admission.initialize(engine, root)
    return receipt


def _attach_copy(
    connection: Connection,
    root: str,
    old_copy: str,
    entries: list[tuple[dict[str, Any], ObjectRef]],
) -> str:
    first, first_ref = entries[0]
    size = sum(ref.length for _, ref in entries)
    old_charge = first["charge_id"]
    if any(
        row["charge_id"] != old_charge
        or row["charge_state"] != "retained"
        or row["charged_bytes"] != size
        for row, _ in entries
    ):
        raise V2Error("integrity_failure", "Restored copy has inconsistent charge coverage")
    if execute(
        connection,
        "SELECT count(*) FROM v2_storage_objects WHERE charge_id=:charge",
        charge=old_charge,
    ).scalar_one() != len(entries):
        raise V2Error("integrity_failure", "Restored copy does not cover its charge")
    copy, charge = uuid4(), uuid4()
    execute(
        connection,
        "INSERT INTO v2_data_charges (charge_id,root_id,ceiling_bytes,charged_bytes,state,"
        "created_at,updated_at,backend_alias) VALUES (:id,:root,:bytes,:bytes,'retained',"
        "clock_timestamp(),clock_timestamp(),:alias)",
        id=charge,
        root=root,
        bytes=size,
        alias=first_ref.alias,
    )
    execute(
        connection,
        "UPDATE v2_storage_copies SET active=false WHERE copy_id=:copy",
        copy=old_copy,
    )
    execute(
        connection,
        "INSERT INTO v2_storage_copies VALUES "
        "(:copy,:package,:root,:alias,clock_timestamp(),:active)",
        copy=copy,
        package=first["package_id"],
        root=root,
        alias=first_ref.alias,
        active=first["active"],
    )
    for _, ref in entries:
        object_id = uuid4()
        store._insert_intent(
            connection, UUID(root), charge, store.Intent(object_id, replace(ref, version=None))
        )
        execute(
            connection,
            "UPDATE v2_storage_objects SET version_id=:version,state='verified',copy_id=:copy "
            "WHERE object_id=:id",
            version=ref.version,
            copy=copy,
            id=object_id,
        )
    replaced = one(
        connection,
        "UPDATE v2_data_charges SET state='released',charged_bytes=0,updated_at=clock_timestamp() "
        "WHERE charge_id=:charge AND state='retained' AND charged_bytes=:bytes RETURNING charge_id",
        charge=old_charge,
        bytes=size,
    )
    if replaced is None:
        raise V2Error("integrity_failure", "Restore charge transfer failed")
    return str(copy)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "backup-inventory",
            "rebind-restore",
            "local-backup-inventory",
            "local-rebind-restore",
        ),
    )
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--destinations", type=Path)
    parser.add_argument("--owned-restore", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    engine = create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
    try:
        if args.action == "backup-inventory":
            output = backup_inventory(engine, settings.storage_path)
        elif args.action == "local-backup-inventory":
            output = local_backup_inventory(engine, settings.storage_path, settings)
        elif args.action == "local-rebind-restore":
            if not (args.backup and args.owned_restore) or args.destinations is not None:
                parser.error("local-rebind-restore requires --owned-restore and --backup")
            backup = json.loads(args.backup.read_bytes())
            output = local_rebind_restore(engine, settings.storage_path, backup, settings)
        else:
            if not (args.backup and args.destinations and args.owned_restore):
                parser.error("rebind-restore requires --owned-restore, --backup and --destinations")
            backup = json.loads(args.backup.read_bytes())
            destinations = json.loads(args.destinations.read_bytes())
            output = rebind_restore(engine, settings.storage_path, backup, destinations, settings)
        print(json.dumps(output, sort_keys=True))
    except V2Error as error:
        parser.exit(1, f"{error.code}: {error}\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
