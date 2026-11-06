"""PostgreSQL storage intents and package registrations."""

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import inspect
from sqlalchemy.engine import Connection, Engine

from marketlab.config import Settings
from marketlab.datasets.v2 import admission
from marketlab.datasets.v2.common import V2Error, canonical_json, sha256_file
from marketlab.datasets.v2.core import execute, lock, one, transaction

from .backend import (
    Backend,
    LocalBackend,
    LocalWriter,
    ObjectConfig,
    ObjectRef,
    S3Backend,
    StreamWriter,
    backend_for,
    close_backend,
    new_prefix,
)

HEAD = "0012_v2_storage"
TABLES = ("v2_storage_packages", "v2_storage_copies", "v2_storage_objects")
OWNERS = {
    "legacy_dataset": "legacy_dataset_id",
    "v2_dataset": "v2_dataset_id",
    "legacy_research": "legacy_research_id",
    "v2_research": "v2_research_id",
    "legacy_memo": "legacy_memo_id",
    "v2_memo": "v2_memo_id",
    "upload_generation": "upload_generation_id",
    "cli_import": "cli_import_id",
}
MEMBERS = {
    "legacy_dataset": {"manifest.json", "trades.parquet"},
    "v2_dataset": {"manifest.json", "quality.json", "trades.parquet"},
    "legacy_research": {"manifest.json", "spec.json", "results.json", "summary.json"},
    "v2_research": {"manifest.json", "spec.json", "results.json", "summary.json"},
    "legacy_memo": {"manifest.json"},
    "v2_memo": {"manifest.json", "facts.json", "draft.json", "provenance.json", "memo.txt"},
}


def enabled(connection: Connection) -> bool:
    if connection.dialect.name != "postgresql":
        tables = set(inspect(connection).get_table_names())
        if tables.intersection(TABLES) or (
            "alembic_version" in tables
            and execute(
                connection,
                "SELECT version_num FROM alembic_version WHERE version_num=:head",
                head=HEAD,
            ).scalar_one_or_none()
            is not None
        ):
            raise V2Error("integrity_failure", "Managed storage requires PostgreSQL")
        return False
    mapping = connection.get_execution_options().get("schema_translate_map") or {}
    namespace = mapping.get(None)
    if namespace is not None:
        present = execute(
            connection,
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname=:namespace AND c.relname=ANY(:names)",
            namespace=namespace,
            names=[*TABLES, "alembic_version"],
        ).scalar_one()
        if not present:
            return False  # Isolated legacy schema with no migrated storage tables.
        schema = execute(connection, "SELECT current_schema()").scalar_one()
        if namespace != schema:
            raise V2Error("integrity_failure", "Storage schema namespace mismatch")
    exists = [
        execute(connection, "SELECT to_regclass(:name)", name=name).scalar_one() is not None
        for name in TABLES
    ]
    if all(exists):
        return True
    if any(exists):
        raise V2Error("integrity_failure", "Storage ledger is incomplete")
    if execute(connection, "SELECT to_regclass('alembic_version')").scalar_one() is not None:
        revision = execute(
            connection, "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
        if revision == HEAD:
            raise V2Error("integrity_failure", "Storage ledger is missing")
    return False


def current(engine: Engine) -> bool:
    with engine.connect() as connection:
        return enabled(connection)


def verify_namespace(binding: Mapping[str, Any], config: ObjectConfig | None) -> None:
    expected = (config.alias, config.fingerprint) if config is not None else (None, None)
    if (binding.get("object_alias"), binding.get("object_namespace_sha256")) != expected:
        raise V2Error("storage_denied", "Configured object storage binding does not match")


def media_schema(path: Path) -> str:
    return {
        ".json": "application/json",
        ".parquet": "application/vnd.apache.parquet",
        ".csv": "text/csv",
        ".txt": "text/plain",
    }.get(path.suffix, "application/octet-stream")


@dataclass(frozen=True)
class Snapshot:
    package_id: UUID
    copy_id: UUID | None
    refs: tuple[ObjectRef, ...] | None


def _ref(row: Mapping[str, Any]) -> ObjectRef:
    return ObjectRef(
        row["backend_alias"],
        row["object_key"],
        row["version_id"],
        row["byte_length"],
        row["sha256"],
        row["member"],
        row["media_schema"],
    )


def snapshot(connection: Connection, owner: str, owner_id: str) -> Snapshot:
    column = OWNERS[owner]
    rows = (
        execute(
            connection,
            f"SELECT p.package_id,p.legacy_local,c.copy_id,c.backend_alias AS copy_alias,"
            "r.object_alias,r.object_namespace_sha256,o.object_id,o.backend_alias,"
            "o.object_key,o.version_id,o.member,o.media_schema,o.byte_length,o.sha256,o.state "
            "FROM v2_storage_packages p LEFT JOIN v2_storage_copies c ON "
            "c.package_id=p.package_id AND c.active LEFT JOIN v2_capacity_roots r ON "
            "r.root_id=c.root_id LEFT JOIN v2_storage_objects o ON o.copy_id=c.copy_id "
            f"WHERE p.{column}=:id ORDER BY o.member",
            id=owner_id,
        )
        .mappings()
        .all()
    )
    if not rows:
        raise V2Error("integrity_failure", "Artifact package registration missing")
    first = rows[0]
    if first["copy_id"] is None:
        if first["legacy_local"] and len(rows) == 1:
            return Snapshot(first["package_id"], None, None)
        raise V2Error("integrity_failure", "Active artifact copy missing")
    if first["legacy_local"] or any(
        not row["object_id"] or row["state"] != "verified" or row["copy_id"] != first["copy_id"]
        for row in rows
    ):
        raise V2Error("integrity_failure", "Active artifact copy is incomplete")
    if first["copy_alias"] != "local":
        config = ObjectConfig.from_settings(Settings())
        verify_namespace(first, config)
        if first["copy_alias"] != first["object_alias"]:
            raise V2Error("integrity_failure", "Active artifact backend mismatch")
    return Snapshot(first["package_id"], first["copy_id"], tuple(_ref(row) for row in rows))


def get_registered(
    engine: Engine, owner: str, owner_id: str, *, root: Path | None = None
) -> tuple[ObjectRef, ...] | None:
    with engine.connect() as connection:
        if not enabled(connection):
            return None
        bound = admission.binding(connection, root)
        selected = snapshot(connection, owner, owner_id)
        if bound is None and selected.refs is not None:
            raise V2Error("integrity_failure", "Active artifact storage binding missing")
        return selected.refs


@dataclass(frozen=True)
class Intent:
    object_id: UUID
    ref: ObjectRef


@dataclass(frozen=True)
class WriteGroup:
    engine: Engine
    root: Path
    ticket: Mapping[str, Any]
    root_id: UUID
    backend: Backend
    intents: tuple[Intent, ...]

    @property
    def alias(self) -> str:
        return self.backend.alias

    @property
    def charge_id(self) -> UUID:
        return UUID(str(self.ticket["charge_id"]))

    def _set_writing(self, intent: Intent) -> None:
        with transaction(self.engine) as connection:
            _require_ticket(connection, self.ticket, self.root)
            updated = execute(
                connection,
                "UPDATE v2_storage_objects SET state='writing',updated_at=clock_timestamp() "
                "WHERE object_id=:id AND charge_id=:charge AND state='planned' RETURNING object_id",
                id=intent.object_id,
                charge=self.charge_id,
            ).scalar_one_or_none()
            if updated is None:
                raise V2Error("ownership_lost", "Storage intent already used")

    def _multipart(self, intent: Intent, upload_id: str) -> None:
        with transaction(self.engine) as connection:
            _require_ticket(connection, self.ticket, self.root)
            updated = execute(
                connection,
                "UPDATE v2_storage_objects SET multipart_id=:upload,updated_at=clock_timestamp() "
                "WHERE object_id=:id AND charge_id=:charge AND state='writing' "
                "AND multipart_id IS NULL RETURNING object_id",
                id=intent.object_id,
                charge=self.charge_id,
                upload=upload_id,
            ).scalar_one_or_none()
            if updated is None:
                raise V2Error("ownership_lost", "Storage initiation receipt rejected")

    def _verified(self, intent: Intent, ref: ObjectRef) -> Intent:
        if replace(ref, version=None) != intent.ref or (self.alias != "local" and not ref.version):
            raise V2Error("integrity_failure", "Storage write receipt mismatch")
        with transaction(self.engine) as connection:
            _require_ticket(connection, self.ticket, self.root)
            updated = execute(
                connection,
                "UPDATE v2_storage_objects SET version_id=:version,state='verified',"
                "updated_at=clock_timestamp() WHERE object_id=:id AND charge_id=:charge "
                "AND state='writing' AND version_id IS NULL RETURNING object_id",
                id=intent.object_id,
                charge=self.charge_id,
                version=ref.version,
            ).scalar_one_or_none()
            if updated is None:
                raise V2Error("ownership_lost", "Storage verification receipt rejected")
        return Intent(intent.object_id, ref)

    def write_paths(
        self, files: Mapping[str, Path], cancelled: Callable[[], bool] | None = None
    ) -> "WriteGroup":
        verified = []
        try:
            for intent in self.intents:
                self._set_writing(intent)

                def persist(upload: str, member: Intent = intent) -> None:
                    self._multipart(member, upload)

                with files[intent.ref.member].open("rb") as stream:
                    receipt = self.backend.put_new(
                        intent.ref,
                        stream,
                        multipart=persist,
                        cancelled=cancelled,
                    )
                verified.append(self._verified(intent, receipt))
            return replace(self, intents=tuple(verified))
        finally:
            close_backend(self.backend)

    def begin_stream(self, cancelled: Callable[[], bool]) -> StreamWriter:
        if len(self.intents) != 1:
            raise V2Error("integrity_failure", "Invalid source write group")
        try:
            intent = self.intents[0]
            self._set_writing(intent)
            if isinstance(self.backend, S3Backend):
                return self.backend.begin_multipart(
                    intent.ref, lambda upload: self._multipart(intent, upload), cancelled
                )
            if isinstance(self.backend, LocalBackend):
                return LocalWriter(self.backend, intent.ref, cancelled)
            raise V2Error("integrity_failure", "Invalid source backend")
        except BaseException:
            close_backend(self.backend)
            raise

    def complete_stream(self, writer: StreamWriter) -> "WriteGroup":
        try:
            return replace(self, intents=(self._verified(self.intents[0], writer.complete()),))
        finally:
            close_backend(self.backend)


def _require_ticket(
    connection: Connection, ticket: Mapping[str, Any], root: Path
) -> dict[str, Any]:
    bound = admission.require(connection, root)
    owned = one(
        connection,
        "SELECT c.* FROM v2_admission_tickets t JOIN v2_data_charges c "
        "ON t.ticket_id=c.ticket_id AND t.root_id=c.root_id "
        "WHERE t.root_id=:root AND t.ticket_id=:ticket AND t.owner=:owner "
        "AND t.state IN ('pending','active') AND c.charge_id=:charge AND c.state='reserved' "
        "FOR UPDATE OF c",
        root=bound["root_id"],
        ticket=ticket["ticket_id"],
        owner=ticket["owner"],
        charge=ticket["charge_id"],
    )
    if owned is None:
        raise V2Error("ownership_lost", "Storage reservation ownership lost")
    return owned


def begin(
    engine: Engine,
    root: Path,
    ticket: Mapping[str, Any] | None,
    job_id: str,
    token: int,
    members: Iterable[tuple[str, str, int, str]],
    *,
    alias: str | None = None,
) -> WriteGroup | None:
    if not current(engine):
        return None
    if ticket is None:
        raise V2Error("unavailable", "Managed storage requires an admission ticket")
    root = admission.safe_root(root)
    settings = Settings()
    config = ObjectConfig.from_settings(settings)
    alias = settings.storage_backend if alias is None else alias
    prefix = new_prefix(job_id, token)
    intents = tuple(
        Intent(uuid4(), ObjectRef(alias, f"{prefix}/{name}", None, length, sha, name, media))
        for name, media, length, sha in members
    )
    if not intents or len({item.ref.member for item in intents}) != len(intents):
        raise V2Error("integrity_failure", "Invalid artifact package members")
    with transaction(engine) as connection:
        lock(connection, "v2-space:" + str(root))
        verify_namespace(admission.require(connection, root), config)
        charge = _require_ticket(connection, ticket, root)
        if (
            sum(item.ref.length for item in intents) > charge["charged_bytes"]
            or one(
                connection,
                "SELECT object_id FROM v2_storage_objects WHERE charge_id=:id LIMIT 1",
                id=charge["charge_id"],
            )
            is not None
        ):
            raise V2Error("capacity_exceeded", "Artifact write exceeds its reservation")
        execute(
            connection,
            "UPDATE v2_data_charges SET backend_alias=:alias WHERE charge_id=:id",
            alias=alias,
            id=charge["charge_id"],
        )
        for intent in intents:
            _insert_intent(connection, charge["root_id"], charge["charge_id"], intent)
        admission.changed(connection, dict(ticket))
    return WriteGroup(
        engine, root, ticket, charge["root_id"], backend_for(root, alias, settings), intents
    )


def _insert_intent(connection: Connection, root: UUID, charge: UUID, intent: Intent) -> None:
    ref = intent.ref
    execute(
        connection,
        "INSERT INTO v2_storage_objects "
        "(object_id,root_id,charge_id,backend_alias,object_key,member,media_schema,"
        "byte_length,sha256,state,updated_at) VALUES "
        "(:id,:root,:charge,:alias,:key,:member,:media,:length,:sha,'planned',clock_timestamp())",
        id=intent.object_id,
        root=root,
        charge=charge,
        alias=ref.alias,
        key=ref.key,
        member=ref.member,
        media=ref.media_schema,
        length=ref.length,
        sha=ref.sha256,
    )


def prepare(
    engine: Engine,
    root: Path,
    ticket: Mapping[str, Any] | None,
    job_id: str,
    token: int,
    files: Mapping[str, Path],
    cancelled: Callable[[], bool] | None = None,
    *,
    manifest_sha256: str | None = None,
) -> WriteGroup | None:
    if not current(engine):
        return None
    group = begin(
        engine,
        root,
        ticket,
        job_id,
        token,
        describe(files, manifest_sha256),
    )
    return group.write_paths(files, cancelled) if group is not None else None


def describe(
    files: Mapping[str, Path], manifest_sha256: str | None = None
) -> tuple[tuple[str, str, int, str], ...]:
    """Bind every object to the whole verified package before recording intents."""
    descriptions = {}
    for name, path in files.items():
        if path.is_symlink() or path.is_junction() or not path.is_file():
            raise V2Error("integrity_failure", "Unsafe package member")
        descriptions[name] = (name, media_schema(path), path.stat().st_size, sha256_file(path))
    if "manifest.json" in files:
        path = files["manifest.json"]
        manifest_ref = descriptions["manifest.json"]
        if manifest_ref[2] > 1024**2 or (
            manifest_sha256 is not None and manifest_ref[3] != manifest_sha256
        ):
            raise V2Error("integrity_failure", "Verified package manifest changed")
        try:
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != manifest_ref[3]:
                raise ValueError
            manifest = json.loads(raw)
            if "artifacts" in manifest:
                declared = dict(manifest["artifacts"])
            else:
                artifact = manifest["artifact"]
                name = artifact.get("path") or artifact["name"]
                declared = {name: artifact}
            if "quality.json" in files:
                raw = canonical_json(manifest["quality"])
                declared["quality.json"] = {
                    "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            if set(declared) != files.keys() - {"manifest.json"} or any(
                (spec["bytes"], spec["sha256"]) != descriptions[name][2:]
                for name, spec in declared.items()
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError, OSError):
            raise V2Error("integrity_failure", "Verified package members changed") from None
    return tuple(descriptions.values())


def register(connection: Connection, group: WriteGroup, owner: str, owner_id: str) -> None:
    """Attach verified receipts inside the caller's existing fenced transaction."""
    column = OWNERS[owner]
    lock(connection, "v2-space:" + str(group.root))
    charge = _require_ticket(connection, group.ticket, group.root)
    if charge["root_id"] != group.root_id or charge["backend_alias"] != group.alias:
        raise V2Error("integrity_failure", "Storage registration binding mismatch")
    _verify_owner(connection, group, owner, owner_id)
    package, copy_id = uuid4(), uuid4()
    execute(
        connection,
        f"INSERT INTO v2_storage_packages (package_id,{column},legacy_local) "
        "VALUES (:package,:owner,false)",
        package=package,
        owner=owner_id,
    )
    execute(
        connection,
        "INSERT INTO v2_storage_copies VALUES (:copy,:package,:root,:alias,clock_timestamp(),true)",
        copy=copy_id,
        package=package,
        root=group.root_id,
        alias=group.alias,
    )
    attach(connection, group, copy_id)


def attach(connection: Connection, group: WriteGroup, copy_id: UUID) -> None:
    actual = (
        execute(
            connection,
            "SELECT * FROM v2_storage_objects WHERE charge_id=:charge FOR UPDATE",
            charge=group.charge_id,
        )
        .mappings()
        .all()
    )
    expected = {intent.object_id: intent.ref for intent in group.intents}
    if (
        not expected
        or len(expected) != len(group.intents)
        or len(actual) != len(expected)
        or any(
            item["state"] != "verified"
            or item["copy_id"] is not None
            or expected.get(item["object_id"]) != _ref(item)
            for item in actual
        )
    ):
        raise V2Error("integrity_failure", "Verified storage receipt set changed")
    for intent in group.intents:
        execute(
            connection,
            "UPDATE v2_storage_objects SET copy_id=:copy,updated_at=clock_timestamp() "
            "WHERE object_id=:id",
            copy=copy_id,
            id=intent.object_id,
        )
    execute(
        connection,
        "UPDATE v2_data_charges SET charged_bytes=:size,state='retained',"
        "updated_at=clock_timestamp() WHERE charge_id=:charge",
        size=sum(ref.length for ref in expected.values()),
        charge=group.charge_id,
    )
    admission.changed(connection, dict(group.ticket))


def _verify_owner(connection: Connection, group: WriteGroup, owner: str, owner_id: str) -> None:
    refs = {intent.ref.member: intent.ref for intent in group.intents}
    if owner in MEMBERS:
        table, key = {
            "legacy_dataset": ("dataset_versions", "dataset_version_id"),
            "v2_dataset": ("v2_dataset_versions", "dataset_version_id"),
            "legacy_research": ("research_results", "run_id"),
            "v2_research": ("v2_research_results", "run_id"),
            "legacy_memo": ("memo_results", "run_id"),
            "v2_memo": ("v2_memo_results", "run_id"),
        }[owner]
        row = one(connection, f"SELECT * FROM {table} WHERE {key}=:id", id=owner_id)
        required = MEMBERS[owner]
        memo_name = f"research_memo_{owner_id}.md"
        if owner == "legacy_memo":
            required = required | {memo_name}
        if (
            row is None
            or refs.keys() != required
            or refs["manifest.json"].sha256 != row["manifest_sha256"]
            or any(
                member in refs and field in row and refs[member].sha256 != row[field]
                for member, field in (
                    ("results.json", "results_sha256"),
                    ("summary.json", "summary_sha256"),
                    ("memo.txt", "memo_sha256"),
                    (memo_name, "memo_sha256"),
                    ("facts.json", "facts_sha256"),
                )
            )
        ):
            raise V2Error("integrity_failure", "Storage package owner mismatch")
        return
    table, key = (
        ("v2_upload_generations", "generation_id")
        if owner == "upload_generation"
        else ("v2_canonical_imports", "import_id")
    )
    row = one(connection, f"SELECT * FROM {table} WHERE {key}=:id", id=owner_id)
    if row is None or len(refs) != 1:
        raise V2Error("integrity_failure", "Storage source owner mismatch")
    ref = next(iter(refs.values()))
    if (
        ref.member != Path(row.get("source_relative_path") or row["relative_path"]).name
        or ref.sha256 != row["source_sha256"]
        or ref.length != row["declared_bytes"]
    ):
        raise V2Error("integrity_failure", "Storage source owner mismatch")


def register_legacy_local(connection: Connection, owner: str, owner_id: str) -> None:
    if enabled(connection):
        column = OWNERS[owner]
        execute(
            connection,
            f"INSERT INTO v2_storage_packages (package_id,{column},legacy_local) "
            f"VALUES (:id,:owner,true) ON CONFLICT ({column}) DO NOTHING",
            id=uuid4(),
            owner=owner_id,
        )
