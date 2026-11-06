"""Explicit operator copy, verify, switch and reverse for one artifact package."""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine

from marketlab.config import Settings
from marketlab.datasets.v2 import admission
from marketlab.datasets.v2.common import V2Error, safe_path
from marketlab.datasets.v2.core import execute, lock, one, transaction

from . import store
from .backend import LocalBackend, ObjectConfig, ObjectRef, backend_for, managed_backend
from .materialize import materialize_package, without_cache

ORIGIN = {
    "legacy_dataset": ("dataset_versions", "dataset_version_id", "manifest_path"),
    "v2_dataset": ("v2_dataset_versions", "dataset_version_id", "manifest_relative_path"),
    "legacy_research": ("research_results", "run_id", "manifest_path"),
    "v2_research": ("v2_research_results", "run_id", "manifest_relative_path"),
    "legacy_memo": ("memo_results", "run_id", "manifest_path"),
    "v2_memo": ("v2_memo_results", "run_id", "relative_path"),
    "upload_generation": ("v2_upload_generations", "generation_id", "relative_path"),
    "cli_import": ("v2_canonical_imports", "import_id", "source_relative_path"),
}


@dataclass(frozen=True)
class Plan:
    owner: str
    owner_id: str
    source: store.Snapshot
    refs: tuple[ObjectRef, ...]

    def json(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "owner_id": self.owner_id,
            "package_id": str(self.source.package_id),
            "copy_id": str(self.source.copy_id) if self.source.copy_id else None,
            "members": [vars(item) for item in self.refs],
            "bytes": sum(item.length for item in self.refs),
        }


def _members(
    root: Path, owner: str, owner_id: str, row: dict[str, Any], key: str
) -> tuple[ObjectRef, ...]:
    location = safe_path(root, row[key])
    if owner in {"upload_generation", "cli_import"}:
        names = {location.name}
    else:
        names = store.MEMBERS[owner]
        if owner == "legacy_memo":
            names = names | {f"research_memo_{owner_id}.md"}
        if owner == "v2_memo":
            location = location / "manifest.json"
    files = {
        name: safe_path(root, (location.parent / name).relative_to(root).as_posix())
        for name in sorted(names)
    }
    refs = []
    for name, media, length, sha in store.describe(files, row.get("manifest_sha256")):
        path = files[name]
        ref = ObjectRef(
            "local",
            path.relative_to(root).as_posix(),
            None,
            length,
            sha,
            name,
            media,
        )
        LocalBackend(root).stat(ref)
        if name == "manifest.json" and ref.sha256 != row["manifest_sha256"]:
            raise V2Error("integrity_failure", "Legacy manifest differs from registration")
        if owner in {"upload_generation", "cli_import"} and (
            ref.sha256 != row["source_sha256"] or ref.length != row["declared_bytes"]
        ):
            raise V2Error("integrity_failure", "Legacy source differs from registration")
        refs.append(ref)
    return tuple(refs)


def plan(engine: Engine, root: Path, owner: str, owner_id: str) -> Plan:
    with engine.connect() as connection:
        admission.require(connection, root)
        source = store.snapshot(connection, owner, owner_id)
        table, column, path = ORIGIN[owner]
        row = one(connection, f"SELECT * FROM {table} WHERE {column}=:id", id=owner_id)
    if row is None:
        raise V2Error("integrity_failure", "Original artifact registration missing")
    refs = source.refs if source.refs is not None else _members(root, owner, owner_id, row, path)
    with without_cache():
        _verify_package(engine, root, owner, owner_id)
    return Plan(owner, owner_id, source, refs)


def _verify_package(engine: Engine, root: Path, owner: str, owner_id: str) -> None:
    if owner in {"legacy_dataset", "v2_dataset"}:
        from marketlab.datasets.v2.catalog import inspect_version

        inspect_version(engine, root, owner_id)
    elif owner in {"legacy_research", "v2_research", "legacy_memo", "v2_memo"}:
        from marketlab.analytics.bars import BarService
        from marketlab.memos.model import MemoModel
        from marketlab.memos.service import MemoService
        from marketlab.memos.v2.model import MemoModel as V2MemoModel
        from marketlab.memos.v2.service import MemoService as V2MemoService
        from marketlab.research.service import ResearchService
        from marketlab.research.v2.service import ResearchService as V2ResearchService

        bars = BarService(engine, root, None)
        if owner == "legacy_research":
            ResearchService(bars).read(owner_id, "results")
        elif owner == "v2_research":
            V2ResearchService(bars).read(owner_id, "results")
        elif owner == "legacy_memo":
            MemoService(
                ResearchService(bars), MemoModel("http://127.0.0.1:1", Settings().copilot_model)
            ).read(owner_id)
        else:
            V2MemoService(V2ResearchService(bars), V2MemoModel("http://127.0.0.1:1")).read(owner_id)


def _quiescent(connection: Connection, root: Path, own_ticket: str | None = None) -> dict[str, Any]:
    bound = admission.require(connection, root)
    if execute(
        connection,
        "SELECT EXISTS(SELECT 1 FROM v2_admission_tickets WHERE root_id=:id "
        "AND state<>'released' AND (CAST(:ticket AS uuid) IS NULL OR "
        "ticket_id<>CAST(:ticket AS uuid)))",
        id=bound["root_id"],
        ticket=own_ticket,
    ).scalar_one():
        raise V2Error("capacity_exceeded", "Artifact location operation requires drained writers")
    return bound


def _adopt(connection: Connection, bound: dict[str, Any], request: Plan) -> UUID:
    copy_id, charge_id = uuid4(), uuid4()
    size = sum(ref.length for ref in request.refs)
    epoch = admission._file_epoch(bound)
    for ref in request.refs:
        present = one(
            connection,
            "SELECT file_bytes,content_sha256 FROM v2_capacity_files WHERE root_id=:root "
            "AND inventory_epoch=:epoch AND relative_path=:path",
            root=bound["root_id"],
            epoch=epoch,
            path=ref.key,
        )
        if present != {"file_bytes": ref.length, "content_sha256": ref.sha256}:
            raise V2Error("integrity_failure", "Legacy artifact is outside the verified baseline")
    execute(
        connection,
        "INSERT INTO v2_data_charges (charge_id,root_id,ceiling_bytes,charged_bytes,state,"
        "created_at,updated_at) VALUES (:id,:root,:bytes,:bytes,'absorbed',"
        "clock_timestamp(),clock_timestamp())",
        id=charge_id,
        root=bound["root_id"],
        bytes=size,
    )
    execute(
        connection,
        "INSERT INTO v2_storage_copies VALUES "
        "(:copy,:package,:root,'local',clock_timestamp(),true)",
        copy=copy_id,
        package=request.source.package_id,
        root=bound["root_id"],
    )
    for ref in request.refs:
        intent = store.Intent(uuid4(), ref)
        store._insert_intent(connection, bound["root_id"], charge_id, intent)
        execute(
            connection,
            "UPDATE v2_storage_objects SET state='verified',copy_id=:copy WHERE object_id=:id",
            copy=copy_id,
            id=intent.object_id,
        )
    execute(
        connection,
        "UPDATE v2_storage_packages SET legacy_local=false WHERE package_id=:id",
        id=request.source.package_id,
    )
    return copy_id


def copy(engine: Engine, root: Path, request: Plan, alias: str) -> dict[str, Any]:
    root = admission.safe_root(root)
    if not request.refs:
        raise V2Error("integrity_failure", "Artifact copy has no members")
    size = sum(item.length for item in request.refs)
    ticket = admission.acquire(
        engine, root, "legacy", size, physical_bytes=size if alias == "local" else 0
    )
    if ticket is None:
        raise V2Error("unavailable", "Storage copy requires initialized admission")
    try:
        with engine.connect() as connection:
            _quiescent(connection, root, ticket["ticket_id"])
        implicit = lambda: safe_path(root, request.refs[0].key).parent  # noqa: E731
        with (
            without_cache(),
            materialize_package(engine, root, request.source.refs, implicit) as directory,
        ):
            group = store.begin(
                engine,
                root,
                ticket,
                str(uuid4()),
                0,
                ((ref.member, ref.media_schema, ref.length, ref.sha256) for ref in request.refs),
                alias=alias,
            )
            if group is None:
                raise V2Error("unavailable", "Storage schema is required")
            group = group.write_paths({ref.member: directory / ref.member for ref in request.refs})
        copy_id = uuid4()
        with transaction(engine) as connection:
            lock(connection, "v2-space:" + str(root))
            bound = _quiescent(connection, root, ticket["ticket_id"])
            if store.snapshot(connection, request.owner, request.owner_id) != request.source:
                raise V2Error("revision_conflict", "Artifact source mapping changed")
            store._verify_owner(connection, group, request.owner, request.owner_id)
            source_id = request.source.copy_id or _adopt(connection, bound, request)
            execute(
                connection,
                "INSERT INTO v2_storage_copies VALUES "
                "(:copy,:package,:root,:alias,clock_timestamp(),false)",
                copy=copy_id,
                package=request.source.package_id,
                root=bound["root_id"],
                alias=alias,
            )
            store.attach(connection, group, copy_id)
        return {
            "owner": request.owner,
            "owner_id": request.owner_id,
            "source_copy_id": str(source_id),
            "target_copy_id": str(copy_id),
            "members": [vars(intent.ref) for intent in group.intents],
        }
    finally:
        admission.finish(engine, ticket, 0)


def _copy_refs(connection: Connection, package_id: UUID, copy_id: UUID) -> tuple[ObjectRef, ...]:
    result = (
        execute(
            connection,
            "SELECT o.* FROM v2_storage_objects o JOIN v2_storage_copies c USING(copy_id) "
            "WHERE c.package_id=:package AND c.copy_id=:copy AND o.state='verified' "
            "ORDER BY o.member",
            package=package_id,
            copy=copy_id,
        )
        .mappings()
        .all()
    )
    if not result:
        raise V2Error("integrity_failure", "Target copy is incomplete")
    return tuple(store._ref(row) for row in result)


class _Discard:
    def write(self, content: bytes) -> int:
        return len(content)


def switch(
    engine: Engine, root: Path, owner: str, owner_id: str, source: UUID, target: UUID
) -> None:
    from typing import BinaryIO

    root = admission.safe_root(root)
    if source == target:
        raise V2Error("invalid_request", "Source and target copies must differ")
    with engine.connect() as connection:
        bound = _quiescent(connection, root)
        selected = store.snapshot(connection, owner, owner_id)
        if selected.copy_id != source or selected.refs is None:
            raise V2Error("revision_conflict", "Artifact source mapping changed")
        refs = _copy_refs(connection, selected.package_id, target)
    _verify_backend(bound, refs)
    identities = {(ref.member, ref.sha256, ref.length, ref.media_schema) for ref in selected.refs}
    if identities != {(ref.member, ref.sha256, ref.length, ref.media_schema) for ref in refs}:
        raise V2Error("integrity_failure", "Target copy differs from source identity")
    for ref in refs:
        with managed_backend(backend_for(root, ref.alias)) as backend:
            backend.read_verified(ref, cast(BinaryIO, _Discard()))
    with transaction(engine) as connection:
        lock(connection, "v2-space:" + str(root))
        _quiescent(connection, root)
        if (
            store.snapshot(connection, owner, owner_id) != selected
            or _copy_refs(connection, selected.package_id, target) != refs
        ):
            raise V2Error("revision_conflict", "Artifact location mapping changed")
        execute(
            connection, "UPDATE v2_storage_copies SET active=false WHERE copy_id=:id", id=source
        )
        execute(connection, "UPDATE v2_storage_copies SET active=true WHERE copy_id=:id", id=target)


def _verify_backend(bound: dict[str, Any], refs: tuple[ObjectRef, ...]) -> None:
    aliases = {ref.alias for ref in refs}
    if aliases == {"local"}:
        return
    store.verify_namespace(bound, ObjectConfig.from_settings(Settings()))
    if aliases != {bound["object_alias"]}:
        raise V2Error("integrity_failure", "Historical object namespace is not configured")


def delete_unreferenced(engine: Engine, root: Path, object_id: UUID) -> None:
    """Retire a positively verified, unattached generation on a drained owned stack."""
    root = admission.safe_root(root)
    with transaction(engine) as connection:
        lock(connection, "v2-space:" + str(root))
        bound = _quiescent(connection, root)
        row = one(
            connection,
            "SELECT o.* FROM v2_storage_objects o JOIN v2_data_charges d USING(charge_id) "
            "JOIN v2_admission_tickets t ON t.ticket_id=d.ticket_id WHERE o.object_id=:id "
            "AND o.root_id=:root AND o.copy_id IS NULL AND o.state='verified' "
            "AND t.state='released' FOR UPDATE OF o",
            id=object_id,
            root=bound["root_id"],
        )
        if row is None:
            raise V2Error("integrity_failure", "Object is referenced or its retirement is unproved")
        ref = store._ref(row)
        _verify_backend(bound, (ref,))
        execute(
            connection,
            "UPDATE v2_storage_objects SET state='retiring' WHERE object_id=:id",
            id=object_id,
        )
        execute(
            connection,
            "UPDATE v2_capacity_roots SET ready=false,epoch=epoch+1 WHERE root_id=:id",
            id=bound["root_id"],
        )
    with managed_backend(backend_for(root, ref.alias)) as backend:
        backend.delete_unreferenced(ref)
    with transaction(engine) as connection:
        lock(connection, "v2-space:" + str(root))
        changed = one(
            connection,
            "UPDATE v2_storage_objects SET state='retired',updated_at=clock_timestamp() "
            "WHERE object_id=:id AND copy_id IS NULL AND state='retiring' RETURNING charge_id",
            id=object_id,
        )
        if changed is None:
            raise V2Error("integrity_failure", "Storage retirement intent changed")
        execute(
            connection,
            "UPDATE v2_data_charges SET charged_bytes=0,state='released',"
            "updated_at=clock_timestamp() WHERE charge_id=:charge AND NOT EXISTS "
            "(SELECT 1 FROM v2_storage_objects WHERE charge_id=:charge AND state<>'retired')",
            charge=changed["charge_id"],
        )
    admission.initialize(engine, root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "dry-run",
            "copy",
            "switch",
            "reverse",
            "delete-unreferenced",
            "reclaim-materialization",
        ),
    )
    parser.add_argument("owner", choices=sorted(store.OWNERS), nargs="?")
    parser.add_argument("owner_id", nargs="?")
    parser.add_argument("--backend")
    parser.add_argument("--source-copy", type=UUID)
    parser.add_argument("--target-copy", type=UUID)
    parser.add_argument("--object-id", type=UUID)
    parser.add_argument("--reservation-id", type=UUID)
    args = parser.parse_args()
    settings = Settings()
    root = admission.safe_root(settings.storage_path)
    engine = create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
    try:
        if args.action == "reclaim-materialization":
            from .materialize_space import reclaim_dead

            if not args.reservation_id:
                parser.error("--reservation-id is required for reclaim-materialization")
            print(json.dumps(reclaim_dead(engine, root, args.reservation_id), sort_keys=True))
        elif args.action == "delete-unreferenced":
            if not args.object_id:
                parser.error("--object-id is required for delete-unreferenced")
            delete_unreferenced(engine, root, args.object_id)
        elif not args.owner or not args.owner_id:
            parser.error("owner and owner_id are required")
        elif args.action == "dry-run":
            print(json.dumps(plan(engine, root, args.owner, args.owner_id).json(), sort_keys=True))
        elif args.action == "copy":
            if not args.backend:
                parser.error("--backend is required for copy")
            request = plan(engine, root, args.owner, args.owner_id)
            print(json.dumps(copy(engine, root, request, args.backend), sort_keys=True))
        else:
            if not args.source_copy or not args.target_copy:
                parser.error("--source-copy and --target-copy are required")
            source, target = args.source_copy, args.target_copy
            if args.action == "reverse":
                source, target = target, source
            switch(engine, root, args.owner, args.owner_id, source, target)
    except V2Error as error:
        parser.exit(1, f"{error.code}: {error}\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
