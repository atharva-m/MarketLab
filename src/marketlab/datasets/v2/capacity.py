"""Common ingestion/research physical admission and owned scratch reservations."""

import os
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.engine import Connection, Engine

from marketlab.datasets.v2.common import V2Error, safe_path
from marketlab.datasets.v2.core import execute, lock, one, transaction

SCRATCH = 20 * 1024**3
SPILL = 2 * 1024**3
OUTPUT = 34 * 1024**2


def capacity_root(root: Path) -> Path:
    """Unify legacy Windows extended paths with the configured Phase 2 root."""
    text = str(root.resolve())
    if os.name == "nt" and text.startswith("\\\\?\\UNC\\"):
        text = "\\\\" + text[8:]
    elif os.name == "nt" and text.startswith("\\\\?\\"):
        text = text[4:]
    return Path(text).resolve()


def outstanding(connection: Connection) -> int:
    old = int(
        execute(
            connection,
            "SELECT coalesce(sum(reserved_bytes),0) FROM "
            "v2_storage_reservations WHERE state<>'released'",
        ).scalar_one()
    )
    present = execute(connection, "SELECT to_regclass('v2_research_reservations')").scalar_one()
    if present is None:
        version_table = execute(
            connection,
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n "
            "ON n.oid=c.relnamespace WHERE n.nspname=current_schema() "
            "AND c.relname='alembic_version'",
        ).scalar_one()
        revision = (
            execute(connection, "SELECT version_num FROM alembic_version").scalar_one_or_none()
            if version_table
            else None
        )
        if revision == "0009_v2_research":
            raise V2Error("integrity_failure", "Research capacity ledger is missing")
        return old
    return old + int(
        execute(
            connection,
            "SELECT coalesce(sum(scratch_bytes+spill_bytes+output_bytes),0) "
            "FROM v2_research_reservations WHERE state<>'released'",
        ).scalar_one()
    )


def reserve(
    engine: Engine, root: Path, run_id: str | None = None, purpose: str = "preparation"
) -> dict[str, Any]:
    root = capacity_root(root)
    root.mkdir(parents=True, exist_ok=True)
    identifier, owner = uuid4(), uuid4()
    relative = f"research-v2-scratch/{identifier}"
    with transaction(engine) as connection:
        lock(connection, "v2-space:" + str(root))
        if shutil.disk_usage(root).free < outstanding(connection) + SCRATCH + SPILL + OUTPUT:
            raise V2Error("capacity_exceeded", "Insufficient reserved numerical capacity")
        execute(
            connection,
            "INSERT INTO v2_research_reservations VALUES "
            "(:id,:run,:owner,:purpose,'active',:scratch,:spill,:output,:path,"
            "clock_timestamp(),clock_timestamp(),NULL)",
            id=identifier,
            run=run_id,
            owner=owner,
            purpose=purpose,
            scratch=SCRATCH,
            spill=SPILL,
            output=OUTPUT,
            path=relative,
        )
    path = safe_path(root, relative)
    path.mkdir(parents=True, exist_ok=False)
    return {
        "reservation_id": str(identifier),
        "owner": str(owner),
        "relative_path": relative,
        "path": path,
    }


def release(engine: Engine, root: Path, reservation: dict[str, Any], success: bool = True) -> None:
    """Release only after exact owned transient tree removal; failures retain the charge."""
    root = capacity_root(root)
    relative = reservation["relative_path"]
    if relative != f"research-v2-scratch/{reservation['reservation_id']}":
        raise V2Error("integrity_failure", "Numerical reservation ownership mismatch")
    path = safe_path(root, relative)
    with engine.connect() as connection:
        row = one(
            connection,
            "SELECT * FROM v2_research_reservations WHERE reservation_id=:id",
            id=reservation["reservation_id"],
        )
    if row is None or str(row["owner"]) != reservation["owner"] or row["relative_root"] != relative:
        raise V2Error("integrity_failure", "Numerical reservation ownership mismatch")
    if row["state"] == "released":
        return
    if not success:
        with transaction(engine) as connection:
            lock(connection, "v2-space:" + str(root.resolve()))
            execute(
                connection,
                "UPDATE v2_research_reservations SET state='retained',"
                "updated_at=clock_timestamp() WHERE reservation_id=:id",
                id=reservation["reservation_id"],
            )
        return
    if path.exists():
        shutil.rmtree(path)
    if path.exists():
        raise V2Error("integrity_failure", "Numerical scratch cleanup incomplete")
    with transaction(engine) as connection:
        lock(connection, "v2-space:" + str(root.resolve()))
        execute(
            connection,
            "UPDATE v2_research_reservations SET state='released',scratch_bytes=0,"
            "spill_bytes=0,output_bytes=0,released_at=clock_timestamp(),"
            "updated_at=clock_timestamp() "
            "WHERE reservation_id=:id AND owner=:owner",
            id=reservation["reservation_id"],
            owner=reservation["owner"],
        )
