"""Physical reservations for owned materializations on the bound storage volume."""

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.engine import Connection, Engine

from marketlab.datasets.v2 import admission, native_children, native_identity
from marketlab.datasets.v2.capacity import SCRATCH, outstanding
from marketlab.datasets.v2.common import V2Error, canonical_json, safe_path
from marketlab.datasets.v2.core import execute, lock, one, transaction


def _changed(connection: Connection, root: Path) -> None:
    if execute(connection, "SELECT to_regclass('v2_capacity_roots')").scalar_one() is not None:
        execute(
            connection,
            "UPDATE v2_capacity_roots SET epoch=epoch+1,updated_at=clock_timestamp() "
            "WHERE root_path=:root AND ready",
            root=str(root),
        )


def _available(connection: Connection, root: Path, amount: int) -> None:
    if shutil.disk_usage(root).free < outstanding(connection) + amount:
        raise V2Error("capacity_exceeded", "Insufficient artifact materialization capacity")


@dataclass(frozen=True)
class MaterializationSpace:
    engine: Engine
    root: Path
    identifier: UUID
    owner: UUID
    native: str

    @property
    def relative(self) -> str:
        return f".materializations/{self.identifier}"

    @property
    def path(self) -> Path:
        parent = self.root / ".materializations"
        if parent.is_symlink() or parent.is_junction():
            raise V2Error("integrity_failure", "Unsafe materialization directory")
        path = safe_path(self.root, self.relative)
        if path.is_junction():
            raise V2Error("integrity_failure", "Unsafe materialization directory")
        return path

    def grow(self, amount: int) -> None:
        with transaction(self.engine) as connection:
            lock(connection, "v2-space:" + str(self.root))
            _available(connection, self.root, amount)
            grown = execute(
                connection,
                "UPDATE v2_research_reservations SET scratch_bytes=scratch_bytes+:amount,"
                "updated_at=clock_timestamp() WHERE reservation_id=:id AND owner=:owner "
                "AND relative_root=:path AND state='active' AND materialization_native_identity="
                ":native AND scratch_bytes+:amount<=:limit "
                "RETURNING reservation_id",
                id=self.identifier,
                owner=self.owner,
                path=self.relative,
                native=self.native,
                amount=amount,
                limit=SCRATCH,
            ).scalar_one_or_none()
            if grown is None:
                raise V2Error("integrity_failure", "Materialization reservation ownership lost")
            _changed(connection, self.root)

    def close(self) -> None:
        parsed = native_children.envelope(json.loads(self.native))
        if parsed is None or not native_identity.same(parsed["process"]):
            raise V2Error("integrity_failure", "Materialization native owner mismatch")
        with self.engine.connect() as connection:
            owned = execute(
                connection,
                "SELECT 1 FROM v2_research_reservations WHERE reservation_id=:id AND "
                "owner=:owner AND relative_root=:path AND state='active' AND "
                "materialization_native_identity=:native",
                id=self.identifier,
                owner=self.owner,
                path=self.relative,
                native=self.native,
            ).scalar_one_or_none()
        if owned is None:
            raise V2Error("integrity_failure", "Materialization reservation ownership lost")
        self._remove_and_release()

    def _remove_and_release(self) -> None:
        path = self.path
        try:
            if path.exists():
                shutil.rmtree(path)
        except FileNotFoundError:
            pass
        except OSError as error:
            raise V2Error("unavailable", "Materialization cleanup did not drain") from error
        if path.exists():
            raise V2Error("integrity_failure", "Materialization cleanup incomplete")
        with transaction(self.engine) as connection:
            lock(connection, "v2-space:" + str(self.root))
            released = execute(
                connection,
                "UPDATE v2_research_reservations SET state='released',scratch_bytes=0,"
                "updated_at=clock_timestamp(),released_at=clock_timestamp() "
                "WHERE reservation_id=:id AND owner=:owner AND relative_root=:path "
                "AND state='active' AND materialization_native_identity=:native "
                "RETURNING reservation_id",
                id=self.identifier,
                owner=self.owner,
                path=self.relative,
                native=self.native,
            ).scalar_one_or_none()
            if released is None:
                raise V2Error("integrity_failure", "Materialization reservation ownership lost")
            _changed(connection, self.root)


def reserve_space(
    engine: Engine,
    root: Path,
    amount: int,
    *,
    allow_unready: bool = False,
    children_pending: bool = False,
) -> MaterializationSpace:
    if not 0 <= amount <= SCRATCH:
        raise V2Error("capacity_exceeded", "Invalid artifact materialization reservation")
    root = admission.safe_root(root)
    identity = native_children.envelope(native_identity.current())
    if identity is None:
        raise V2Error("unavailable", "Materialization native identity unavailable")
    identity["children_pending"] = children_pending
    space = MaterializationSpace(engine, root, uuid4(), uuid4(), canonical_json(identity).decode())
    # Persist exclusive ownership and charge before creating even the directory.
    with transaction(engine) as connection:
        lock(connection, "v2-space:" + str(root))
        bound = admission.binding(connection, root)
        if bound is not None and not bound["ready"] and not allow_unready:
            raise V2Error("unavailable", "Artifact storage is not ready")
        if amount:
            _available(connection, root, amount)
        execute(
            connection,
            "INSERT INTO v2_research_reservations (reservation_id,run_id,owner,purpose,state,"
            "scratch_bytes,spill_bytes,output_bytes,relative_root,created_at,updated_at,released_at,"
            "materialization_native_identity) VALUES "
            "(:id,NULL,:owner,'preparation','active',:amount,0,0,:path,"
            "clock_timestamp(),clock_timestamp(),NULL,:native)",
            id=space.identifier,
            owner=space.owner,
            amount=amount,
            path=space.relative,
            native=space.native,
        )
        _changed(connection, root)
    # An uncertain directory creation retains its reservation for reconciliation.
    space.path.mkdir(mode=0o700, parents=True, exist_ok=False)
    return space


def reclaim_dead(engine: Engine, root: Path, reservation_id: UUID) -> dict[str, str]:
    """Reclaim one exact, non-authoritative directory on explicit operator request."""
    root = admission.safe_root(root)
    relative = f".materializations/{reservation_id}"
    with transaction(engine) as connection:
        lock(connection, "v2-space:" + str(root))
        bound = admission.binding(connection, root)
        if bound is None:
            raise V2Error("unavailable", "Materialization recovery requires bound storage")
        if execute(
            connection,
            "SELECT EXISTS(SELECT 1 FROM v2_admission_tickets WHERE root_id=:root "
            "AND state<>'released')",
            root=bound["root_id"],
        ).scalar_one():
            raise V2Error("capacity_exceeded", "Materialization recovery requires drained writers")
        row = one(
            connection,
            "SELECT owner,state,materialization_native_identity FROM v2_research_reservations "
            "WHERE reservation_id=:id AND relative_root=:path AND purpose='preparation' "
            "AND run_id IS NULL AND spill_bytes=0 AND output_bytes=0",
            id=reservation_id,
            path=relative,
        )
        if row is None or row["materialization_native_identity"] is None:
            raise V2Error("not_found", "Owned materialization reservation missing")
        if execute(
            connection,
            "SELECT EXISTS(SELECT 1 FROM v2_storage_objects WHERE root_id=:root "
            "AND backend_alias='local' AND (object_key=:path OR object_key LIKE :path||'/%'))",
            root=bound["root_id"],
            path=relative,
        ).scalar_one():
            raise V2Error("integrity_failure", "Materialization location is referenced")
    raw = row["materialization_native_identity"]
    space = MaterializationSpace(engine, root, reservation_id, row["owner"], raw)
    if row["state"] == "released" and not space.path.exists():
        return {"reservation_id": str(reservation_id), "state": "released"}
    try:
        identity = json.loads(raw)
    except (ValueError, RecursionError):
        identity = None
    if (
        row["state"] != "active"
        or not isinstance(identity, dict)
        or not native_children.dead(identity)
    ):
        raise V2Error("ownership_lost", "Materialization native owner or reader is unresolved")
    with transaction(engine) as connection:
        lock(connection, "v2-space:" + str(root))
        current = one(
            connection,
            "SELECT owner,state,materialization_native_identity FROM v2_research_reservations "
            "WHERE reservation_id=:id AND relative_root=:path AND purpose='preparation' "
            "AND run_id IS NULL AND spill_bytes=0 AND output_bytes=0 FOR UPDATE",
            id=reservation_id,
            path=relative,
        )
        if current != row or not native_children.dead(identity):
            raise V2Error("ownership_lost", "Materialization recovery ownership changed")
    space._remove_and_release()
    return {"reservation_id": str(reservation_id), "state": "released"}
