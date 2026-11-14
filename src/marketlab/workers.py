"""Explicit worker identity, mode fencing and bounded operator observations."""

import json
import shutil
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy.engine import Connection, Engine

from marketlab.datasets.v2 import native_identity
from marketlab.datasets.v2.common import HASH, V2Error, canonical_json, digest, sha256_file
from marketlab.datasets.v2.core import execute, lock, one, transaction, uid, wire

CONTRACTS = {
    "ingestion": "daily-ingestion-v2",
    "research": "research-v2",
    "copilot": "copilot-request-v2",
    "memo": "memo-request-v2",
}


def enabled(connection: Connection) -> bool:
    present = bool(
        execute(
            connection,
            "SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n "
            "ON n.oid=c.relnamespace WHERE n.nspname=current_schema() "
            "AND c.relname='v2_worker_mode')",
        ).scalar_one()
    )
    if (
        not present
        and execute(connection, "SELECT to_regclass('alembic_version')").scalar_one() is not None
    ):
        revision = execute(
            connection, "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
        if revision == "0013_v2_workers":
            raise V2Error("integrity_failure", "Worker mode ledger is missing")
    return present


def mode(connection: Connection) -> dict[str, Any] | None:
    return (
        one(connection, "SELECT * FROM v2_worker_mode WHERE singleton")
        if enabled(connection)
        else None
    )


def local_root(connection: Connection) -> dict[str, Any] | None:
    identifier = connection.get_execution_options().get("worker_root_id")
    if identifier is None:
        return None
    return one(connection, "SELECT * FROM v2_worker_roots WHERE root_id=:id", id=identifier)


def stop_requested(engine: Engine) -> bool:
    stop = engine.get_execution_options().get("worker_stop_event")
    return bool(stop is not None and stop.is_set())


def bind_root(engine: Engine, root: Path, root_id: str | None) -> None:
    """Explicit physical context for intake/read services; never a job ownership grant."""
    if root_id is None:
        return
    from marketlab.db_transport import configure

    configure(engine)
    uid(root_id)
    from marketlab.datasets.v2.admission import safe_root

    root = safe_root(root)
    native = native_identity.current()
    machine = native_identity.machine_identity()

    with engine.connect() as connection:
        row = one(connection, "SELECT * FROM v2_worker_roots WHERE root_id=:id", id=root_id)
    if (
        row is None
        or not row["ready"]
        or row["local_path"] != str(root)
        or row["boot_identity"] != native["boot"]
        or row["machine_identity"] != machine
    ):
        raise V2Error("unavailable", "Provisioned physical root ownership mismatch")
    engine.update_execution_options(worker_root_id=root_id)


def guard(connection: Connection, kind: str, execution: str) -> str | None:
    """Fail before spending an attempt; registry is observation, lease remains authority."""
    current = mode(connection)
    if current is None or current["mode"] == "local":
        return None
    stop = connection.get_execution_options().get("worker_stop_event")
    if stop is not None and stop.is_set():
        raise V2Error("unavailable", "Worker is draining")
    instance = connection.get_execution_options().get("worker_instance_id")
    row = one(
        connection,
        "SELECT i.instance_id FROM v2_worker_instances i JOIN v2_worker_roots r USING(root_id) "
        "JOIN v2_worker_capabilities c USING(instance_id) WHERE i.instance_id=:id "
        "AND i.state='ready' AND r.ready AND i.boot_identity=r.boot_identity "
        "AND i.heartbeat_at>clock_timestamp()-interval '30 seconds' "
        "AND i.source_sha256=:source AND i.lock_sha256=:lock "
        "AND c.kind=:kind AND c.contract=:contract AND c.execution_sha256=:execution",
        id=instance,
        kind=kind,
        contract=CONTRACTS[kind],
        execution=execution,
        source=connection.get_execution_options().get("worker_source_sha256"),
        lock=connection.get_execution_options().get("worker_lock_sha256"),
    )
    if row is None:
        raise V2Error("unavailable", "A fresh compatible registered worker is required")
    return str(row["instance_id"])


def associate(
    connection: Connection, kind: str, identity: Any, attempt: int, instance: str | None
) -> None:
    if instance is None:
        return
    ident = "job_id" if kind in {"ingestion", "copilot"} else "run_id"
    execute(
        connection,
        f"UPDATE v2_{kind}_attempts SET worker_instance_id=:worker "
        f"WHERE {ident}=:id AND attempt_number=:attempt AND worker_instance_id IS NULL",
        worker=instance,
        id=identity,
        attempt=attempt,
    )


def require_inputs(connection: Connection, kind: str, row: dict[str, Any]) -> None:
    """Missing remote prerequisites never consume an attempt or model reservation."""
    current = mode(connection)
    if current is None or current["mode"] != "distributed":
        return
    from marketlab.storage.store import snapshot

    def dataset(identity: str) -> None:
        package = one(
            connection,
            "SELECT legacy_dataset_id,v2_dataset_id FROM v2_storage_packages "
            "WHERE legacy_dataset_id=:id OR v2_dataset_id=:id",
            id=identity,
        )
        if package is None:
            raise V2Error("unavailable", "Selected input requires explicit object registration")
        snapshot(
            connection, "v2_dataset" if package["v2_dataset_id"] else "legacy_dataset", identity
        )

    if kind == "ingestion" and row["import_id"] is not None:
        imported = one(
            connection,
            "SELECT * FROM v2_canonical_imports WHERE import_id=:id",
            id=row["import_id"],
        )
        if imported is None:
            raise V2Error("integrity_failure", "Canonical input is missing")
        browser = imported.get("transport") == "browser"
        snapshot(
            connection,
            "upload_generation" if browser else "cli_import",
            str(imported["generation_id"] if browser else imported["import_id"]),
        )
    elif kind == "research":
        for selected in execute(
            connection,
            "SELECT dataset_version_id FROM v2_research_selections WHERE submission_id=:id",
            id=row["submission_id"],
        ).scalars():
            dataset(selected)
    elif kind == "copilot":
        request = one(
            connection,
            "SELECT snapshot_json FROM v2_copilot_requests WHERE request_id=:id",
            id=row["request_id"],
        )
        assert request is not None
        for selected in json.loads(request["snapshot_json"]).get("datasets", []):
            dataset(selected["dataset_version_id"])
    elif kind == "memo":
        snapshot(connection, "v2_research", str(row["run_id"]))


def provision(engine: Engine, host: str, label: str, root_id: str, root: Path) -> dict[str, Any]:
    from marketlab.datasets.v2.admission import safe_root

    uid(host)
    uid(root_id)
    if not isinstance(label, str) or not 1 <= len(label.encode()) <= 128 or not label.isprintable():
        raise V2Error("invalid_request", "Invalid operator label")
    root = safe_root(root)
    if not root.is_dir() or len(str(root).encode()) > 4096:
        raise V2Error("invalid_request", "Worker root must be an existing safe directory")
    boot = native_identity.current()["boot"]
    machine = native_identity.machine_identity()
    with transaction(engine) as connection:
        lock(connection, "v2-worker-provision")
        old = one(connection, "SELECT * FROM v2_worker_hosts WHERE host_id=:id", id=host)
        if old is not None and old["operator_label"] != label:
            raise V2Error("revision_conflict", "Host identity already has a different label")
        execute(
            connection,
            "INSERT INTO v2_worker_hosts(host_id,operator_label) VALUES(:id,:label) "
            "ON CONFLICT DO NOTHING",
            id=host,
            label=label,
        )
        # Reject a second root on the same host: separate uncoordinated disk domains
        # must not over-admit shared physical capacity.
        old = one(
            connection,
            "SELECT * FROM v2_worker_roots WHERE host_id=:host OR machine_identity=:machine",
            host=host,
            machine=machine,
        )
        if old is not None:
            if (
                str(old["host_id"]) != host
                or str(old["root_id"]) != root_id
                or old["local_path"] != str(root)
                or old["boot_identity"] != boot
            ):
                raise V2Error("revision_conflict", "Worker root requires verified recovery")
            return cast(dict[str, Any], wire(old))
        execute(
            connection,
            "INSERT INTO v2_worker_roots(root_id,host_id,local_path,boot_identity,"
            "machine_identity,ready) "
            "VALUES(:id,:host,:path,:boot,:machine,true)",
            id=root_id,
            host=host,
            path=str(root),
            boot=boot,
            machine=machine,
        )
        return {"host_id": host, "root_id": root_id}


def switch_mode(engine: Engine, target: str, receipt: dict[str, Any]) -> dict[str, Any]:
    """Explicit quiesced activation. Evidence is operator supplied and retained externally."""
    if (
        target not in {"local", "distributed"}
        or set(receipt)
        != {
            "inventory_sha256",
            "backup_sha256",
            "intake_stopped",
            "old_workers_stopped",
            "local_available",
        }
        or any(
            not isinstance(receipt[k], str) or not HASH.fullmatch(receipt[k])
            for k in ("inventory_sha256", "backup_sha256")
        )
        or any(receipt[k] is not True for k in ("intake_stopped", "old_workers_stopped"))
    ):
        raise V2Error("invalid_request", "Verified quiescence and backup receipt required")
    from marketlab.config import Settings
    from marketlab.storage.backend import ObjectConfig
    from marketlab.storage.store import verify_namespace

    config = ObjectConfig.from_settings(Settings())
    with transaction(engine) as connection:
        lock(connection, "v2-worker-mode")
        current = one(connection, "SELECT * FROM v2_worker_mode WHERE singleton FOR UPDATE")
        if current is None:
            raise V2Error("unavailable", "Worker migration required")
        root = one(connection, "SELECT * FROM v2_capacity_roots WHERE singleton FOR UPDATE")
        if root is None or not root["ready"]:
            raise V2Error("unavailable", "Verified shared inventory required")
        inventory = json.loads(root["receipt_json"])
        if receipt["inventory_sha256"] != inventory.get("inventory_sha256"):
            raise V2Error("revision_conflict", "Mode receipt does not match the verified inventory")
        for table in (
            "v2_admission_tickets",
            "v2_storage_reservations",
            "v2_research_reservations",
        ):
            if execute(
                connection,
                f"SELECT 1 FROM {table} WHERE state NOT IN ('released','retained') LIMIT 1",
            ).first():
                raise V2Error("unavailable", "Physical writers must drain before mode changes")
        for table, physical in (
            ("v2_storage_reservations", "reserved_bytes"),
            ("v2_research_reservations", "scratch_bytes+spill_bytes"),
        ):
            if execute(
                connection,
                f"SELECT 1 FROM {table} WHERE state<>'released' AND ({physical})>0 LIMIT 1",
            ).first():
                raise V2Error(
                    "unavailable", "Unresolved physical reservations prevent mode changes"
                )
        for table in ("v2_ingestion_jobs", "v2_research_runs", "v2_copilot_jobs", "v2_memo_jobs"):
            if execute(connection, f"SELECT 1 FROM {table} WHERE state='running' LIMIT 1").first():
                raise V2Error("unavailable", "Jobs must drain before mode changes")
        if execute(
            connection, "SELECT 1 FROM v2_worker_instances WHERE state<>'stopped' LIMIT 1"
        ).first():
            raise V2Error("unavailable", "Registered workers must stop before mode changes")
        if target == "distributed":
            verify_namespace(root, config)
            if config is None:
                raise V2Error("unavailable", "Distributed mode requires object storage")
        elif receipt["local_available"] is not True:
            raise V2Error("unavailable", "Verified local availability required")
        execute(
            connection,
            "UPDATE v2_worker_mode SET mode=:mode,shared_root_id=:root WHERE singleton",
            mode=target,
            root=root["root_id"],
        )
    return {"mode": target, "receipt_sha256": digest(receipt)}


def source_identity() -> tuple[str, str]:
    from marketlab.research.v2.provenance import execution_identity

    identity = execution_identity()
    return identity["source_sha256"], identity["lock_sha256"]


def recover_root(
    engine: Engine, root_id: str, root: Path, recovery_token: str | None = None
) -> dict[str, Any]:
    """Exact owning OS proof plus full retained inventory; no remote PID inference."""
    from marketlab.datasets.v2 import native_children
    from marketlab.datasets.v2.admission import DATA_LIMIT, _files, safe_root

    uid(root_id)
    recovery_token = str(uuid4()) if recovery_token is None else str(uid(recovery_token))
    engine = engine.execution_options(worker_root_id=root_id)
    root = safe_root(root)
    native = native_identity.current()
    machine = native_identity.machine_identity()

    def space_lock(connection: Connection) -> None:
        shared = one(connection, "SELECT root_path FROM v2_capacity_roots WHERE singleton")
        if shared is None:
            raise V2Error("unavailable", "Shared accounting root required")
        lock(connection, "v2-space:" + shared["root_path"])
        lock(connection, "v2-worker-space:" + root_id)

    def snapshot(
        connection: Connection,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        return tuple(
            [dict(r) for r in execute(connection, query, id=root_id).mappings()]
            for query in (
                "SELECT * FROM v2_worker_instances WHERE root_id=:id "
                "AND state<>'stopped' ORDER BY instance_id",
                "SELECT * FROM v2_admission_tickets WHERE worker_root_id=:id "
                "AND state<>'released' ORDER BY ticket_id",
                "SELECT * FROM v2_research_reservations WHERE worker_root_id=:id "
                "AND state<>'released' ORDER BY reservation_id",
            )
        )  # type: ignore[return-value]

    with transaction(engine) as connection:
        space_lock(connection)
        lock(connection, "v2-worker-recovery:" + root_id)
        bound = one(
            connection, "SELECT * FROM v2_worker_roots WHERE root_id=:id FOR UPDATE", id=root_id
        )
        if (
            bound is None
            or bound["local_path"] != str(root)
            or bound["machine_identity"] != machine
        ):
            raise V2Error("ownership_lost", "Owning OS installation and root proof required")
        if bound["recovery_token"] is not None and str(bound["recovery_token"]) != recovery_token:
            raise V2Error("revision_conflict", "Exact pending recovery token required")
        rebooted = bound["boot_identity"] != native["boot"]
        instances, tickets, reservations = snapshot(connection)
        native_proofs: list[dict[str, Any]] = []
        for instance in instances:
            raw = instance["native_identity"]
            if raw is None:
                raise V2Error("ownership_lost", "Worker native owner is unknown")
            identity = json.loads(raw)
            native_proofs.append(identity)
            if (
                not native_identity.valid(identity)
                or identity["boot"] != bound["boot_identity"]
                or (not rebooted and not native_identity.dead(identity))
            ):
                raise V2Error("ownership_lost", "Worker native owner has not drained")
        for ticket in tickets:
            identity = json.loads(ticket["native_identity"])
            native_proofs.append(identity)
            envelope = native_children.envelope(identity)
            if (
                envelope is None
                or envelope["process"]["boot"] != bound["boot_identity"]
                or (not rebooted and not native_children.dead(identity))
            ):
                raise V2Error("ownership_lost", "Native children have not drained")
        for reservation in reservations:
            raw = reservation["materialization_native_identity"]
            if raw is None:
                owners = list(
                    execute(
                        connection,
                        "SELECT t.native_identity FROM v2_admission_tickets t "
                        "JOIN v2_data_charges c USING(ticket_id) WHERE t.worker_root_id=:root AND "
                        "(c.relative_path=:path OR (CAST(:run AS uuid) IS NOT NULL "
                        "AND t.resource_id=:run))",
                        root=root_id,
                        path=reservation["relative_root"],
                        run=reservation["run_id"],
                    ).scalars()
                )
                if not owners:
                    raise V2Error("ownership_lost", "Physical reservation owner is unknown")
            else:
                owners = [raw]
            for raw in owners:
                identity = json.loads(raw)
                native_proofs.append(identity)
                envelope = native_children.envelope(identity)
                if (
                    envelope is None
                    or envelope["process"]["boot"] != bound["boot_identity"]
                    or (not rebooted and not native_children.dead(identity))
                ):
                    raise V2Error(
                        "ownership_lost", "Physical reservation consumers have not drained"
                    )
        known = {
            r["relative_path"]: dict(r)
            for r in execute(
                connection, "SELECT * FROM v2_worker_files WHERE root_id=:id", id=root_id
            ).mappings()
        }
        coverage = [
            dict(r)
            for r in execute(
                connection,
                "SELECT 'ticket:'||t.ticket_id::text AS group_id,c.relative_path AS path,"
                "(SELECT coalesce(sum(x.charged_bytes),0) FROM v2_data_charges x "
                "WHERE x.ticket_id=t.ticket_id AND x.state IN ('reserved','retained')) AS bytes "
                "FROM v2_data_charges c JOIN v2_admission_tickets t USING(ticket_id) "
                "WHERE t.worker_root_id=:id AND c.relative_path IS NOT NULL "
                "UNION ALL SELECT 'storage:'||reservation_id::text,relative_path,"
                "reserved_bytes+retained_bytes FROM v2_storage_reservations "
                "WHERE worker_root_id=:id AND state<>'released' AND kind='scratch' "
                "UNION ALL SELECT 'research:'||reservation_id::text,relative_root,"
                "scratch_bytes+spill_bytes+output_bytes FROM "
                "v2_research_reservations WHERE worker_root_id=:id AND state<>'released'",
                id=root_id,
            ).mappings()
        ]
        recovery_epoch = bound["recovery_epoch"] + 1
        execute(
            connection,
            "UPDATE v2_worker_roots SET ready=false,recovery_token=:token,"
            "recovery_epoch=:epoch WHERE root_id=:id",
            id=root_id,
            token=recovery_token,
            epoch=recovery_epoch,
        )
    # The unready root fences new claims while all exact local bytes are hashed.
    import hashlib

    scan = hashlib.sha256()
    total = 0
    additional = 0
    entries = []
    seen: set[str] = set()
    for path, size, modified, sha in _files(root):
        scan.update(canonical_json([path, size, modified, sha]))
        total += size
        entries.append((path, size, modified, sha))
        old = known.get(path)
        if old is not None:
            seen.add(path)
            if (old["file_bytes"], old["mtime_ns"], old["content_sha256"]) != (
                size,
                modified,
                sha,
            ):
                raise V2Error("integrity_failure", "Retained local inventory changed")
    if seen != known.keys():
        raise V2Error("integrity_failure", "Retained local inventory is missing")
    # Multiple paths for a ticket are aliases into one budget. Source/output
    # physical mirrors add no logical credit. Allocate known bytes first so a
    # new sibling cannot reuse credit already consumed by retained inventory.
    budgets = {item["group_id"]: int(item["bytes"]) for item in coverage}
    consumed: dict[str, int] = {}
    for path, size, _, _ in sorted(entries, key=lambda entry: entry[0] not in known):
        matching = [
            item for item in coverage if path == item["path"] or path.startswith(item["path"] + "/")
        ]
        group = (
            max(
                matching,
                key=lambda item: (len(item["path"]), not item["group_id"].startswith("ticket:")),
            )["group_id"]
            if matching
            else None
        )
        credit = (
            min(size, max(0, budgets[group] - consumed.get(group, 0))) if group is not None else 0
        )
        if group is not None:
            consumed[group] = consumed.get(group, 0) + size
        if path not in known:
            additional += size - credit
    inventory = scan.hexdigest()
    with transaction(engine) as connection:
        space_lock(connection)
        lock(connection, "v2-worker-recovery:" + root_id)
        latest = one(
            connection, "SELECT * FROM v2_worker_roots WHERE root_id=:id FOR UPDATE", id=root_id
        )
        if (
            latest is None
            or latest["ready"]
            or str(latest["recovery_token"]) != recovery_token
            or latest["recovery_epoch"] != recovery_epoch
            or latest["boot_identity"] != bound["boot_identity"]
            or snapshot(connection) != (instances, tickets, reservations)
        ):
            raise V2Error("revision_conflict", "Recovery ownership snapshot changed")
        if not rebooted and any(not native_children.dead(proof) for proof in native_proofs):
            raise V2Error("ownership_lost", "Native death proof changed during inventory")
        shared = one(connection, "SELECT * FROM v2_capacity_roots WHERE singleton FOR UPDATE")
        if shared is None:
            raise V2Error("unavailable", "Shared accounting root required")
        used = shared["baseline_bytes"] + int(
            execute(
                connection,
                "SELECT coalesce(sum(charged_bytes),0) "
                "FROM v2_data_charges WHERE root_id=:id AND state IN ('reserved','retained')",
                id=shared["root_id"],
            ).scalar_one()
        )
        if used + additional > DATA_LIMIT:
            raise V2Error(
                "capacity_exceeded", "Conservative recovery inventory exceeds shared capacity"
            )
        if additional:
            execute(
                connection,
                "INSERT INTO v2_data_charges(charge_id,root_id,resource_id,ceiling_bytes,"
                "charged_bytes,state,created_at,updated_at) VALUES(:id,:shared,:root,:bytes,:bytes,"
                "'retained',clock_timestamp(),clock_timestamp())",
                id=uuid4(),
                shared=shared["root_id"],
                root=root_id,
                bytes=additional,
            )
        for path, size, modified, sha in entries:
            execute(
                connection,
                "INSERT INTO v2_worker_files VALUES(:id,:path,:size,:modified,:sha) "
                "ON CONFLICT DO NOTHING",
                id=root_id,
                path=path,
                size=size,
                modified=modified,
                sha=sha,
            )
        for ticket in tickets:
            identity = json.loads(ticket["native_identity"])
            if not rebooted and not native_children.dead(identity):
                raise V2Error("ownership_lost", "Native death proof changed")
            execute(
                connection,
                "UPDATE v2_admission_tickets SET state='released',physical_bytes=0,"
                "updated_at=clock_timestamp() WHERE ticket_id=:id",
                id=ticket["ticket_id"],
            )
        execute(
            connection,
            "UPDATE v2_worker_instances SET state='stopped',heartbeat_at=clock_timestamp() "
            "WHERE root_id=:id AND state<>'stopped'",
            id=root_id,
        )
        execute(
            connection,
            "UPDATE v2_worker_roots SET boot_identity=:boot,ready=true,recovery_token=NULL,"
            "updated_at=clock_timestamp() WHERE root_id=:id",
            id=root_id,
            boot=native["boot"],
        )
    return {
        "root_id": root_id,
        "inventory_sha256": inventory,
        "retained_bytes": total,
        "reboot_verified": rebooted,
        "released_tickets": len(tickets),
        "additional_retained_charge": additional,
        "recovery_token": recovery_token,
    }


def inventory_owned(engine: Engine, ticket: dict[str, Any], relative: str) -> int:
    from marketlab.datasets.v2.admission import _files
    from marketlab.datasets.v2.common import safe_path

    root = Path(ticket["root"])
    target = safe_path(root, relative)
    if not target.exists():
        return 0
    if target.is_file():
        stat = target.stat()
        entries = iter([(relative, stat.st_size, stat.st_mtime_ns, sha256_file(target))])
    else:
        entries = (
            (f"{relative}/{path}", size, modified, sha)
            for path, size, modified, sha in _files(target)
        )
    retained = 0
    for path, size, modified, sha in entries:
        with transaction(engine) as connection:
            lock(connection, "v2-space:" + str(root))
            physical = local_root(connection)
            owned = one(
                connection,
                "SELECT worker_root_id FROM v2_admission_tickets "
                "WHERE ticket_id=:id AND owner=:owner",
                id=ticket["ticket_id"],
                owner=ticket["owner"],
            )
            if physical is None or owned is None or owned["worker_root_id"] != physical["root_id"]:
                raise V2Error("ownership_lost", "Local inventory owner mismatch")
            stat = safe_path(root, path).stat()
            if (stat.st_size, stat.st_mtime_ns) != (size, modified):
                raise V2Error("integrity_failure", "Owned file changed during inventory")
            old = one(
                connection,
                "SELECT * FROM v2_worker_files WHERE root_id=:root AND relative_path=:path",
                root=physical["root_id"],
                path=path,
            )
            if old is not None:
                if (old["file_bytes"], old["mtime_ns"], old["content_sha256"]) != (
                    size,
                    modified,
                    sha,
                ):
                    raise V2Error("integrity_failure", "Retained local file changed")
            else:
                execute(
                    connection,
                    "INSERT INTO v2_worker_files VALUES(:root,:path,:size,:modified,:sha)",
                    root=physical["root_id"],
                    path=path,
                    size=size,
                    modified=modified,
                    sha=sha,
                )
                retained += size
    return retained


def audit_root(engine: Engine, root: Path) -> None:
    """Audit only this host's bytes; remote paths and PIDs are never consulted."""
    from marketlab.datasets.v2.admission import binding

    epoch: list[int] = []
    try:
        _audit_root(engine, root, epoch)
    except BaseException as error:
        # The failed snapshot has closed before borrowing a second connection.
        # A cooperating writer publishes this epoch before touching local bytes.
        if epoch:
            with engine.connect() as connection:
                current = binding(connection, root)
            if current is not None and current["epoch"] != epoch[0]:
                raise V2Error(
                    "audit_changed", "Managed local inventory changed during audit"
                ) from error
        raise


def _transferred_ingestion_space(
    connection: Connection, root_id: Any
) -> dict[str, tuple[str, int]]:
    """Find exact active tickets whose physical bytes moved to two attempt rows."""
    from marketlab.datasets.v2.ingestion_budget import (
        COMPACT_LOGICAL_BYTES,
        COMPACT_OUTPUT_BYTES,
        COMPACT_SCRATCH_BYTES,
    )

    coverage: dict[str, tuple[str, int]] = {}
    duplicate_tickets = set()
    for row in execute(
        connection,
        "SELECT t.ticket_id,t.resource_id,t.fencing_token,o.relative_path,"
        "o.reserved_bytes AS output,"
        "o.retained_bytes AS output_retained,s.reserved_bytes AS scratch,"
        "s.retained_bytes AS scratch_retained "
        "FROM v2_admission_tickets t JOIN v2_data_charges c USING(ticket_id) "
        "JOIN v2_storage_reservations o ON o.data_charge_id=c.charge_id "
        "AND o.worker_root_id=t.worker_root_id AND o.job_id=t.resource_id "
        "AND o.fencing_token=t.fencing_token AND o.kind='output' AND o.state<>'released' "
        "AND o.ceiling_bytes=:output "
        "JOIN v2_storage_reservations s ON s.worker_root_id=o.worker_root_id AND s.job_id=o.job_id "
        "AND s.fencing_token=o.fencing_token AND s.kind='scratch' AND s.state<>'released' "
        "AND s.data_charge_id IS NULL AND s.ceiling_bytes=:scratch "
        "AND right(o.relative_path,7)='/output' "
        "AND s.relative_path=left(o.relative_path,-7)||'/scratch' "
        "WHERE t.worker_root_id=:root AND t.role='ingestion' AND t.physical_bytes=0 "
        "AND t.state IN ('active','draining') AND c.root_id=t.root_id AND c.ceiling_bytes=:logical "
        "AND c.state IN ('reserved','retained')",
        root=root_id,
        output=COMPACT_OUTPUT_BYTES,
        scratch=COMPACT_SCRATCH_BYTES,
        logical=COMPACT_LOGICAL_BYTES,
    ).mappings():
        directory = row["relative_path"].removesuffix("/output")
        prefix = f"attempts-v2/{row['resource_id']}/{row['fencing_token']}/"
        suffix = directory.removeprefix(prefix)
        try:
            if not directory.startswith(prefix) or str(UUID(suffix)) != suffix:
                continue
        except ValueError:
            continue
        ticket = str(row["ticket_id"])
        if ticket in coverage:
            duplicate_tickets.add(ticket)
        coverage[ticket] = (
            directory,
            sum(row[key] for key in ("output", "output_retained", "scratch", "scratch_retained")),
        )
    return {ticket: entry for ticket, entry in coverage.items() if ticket not in duplicate_tickets}


def _audit_root(engine: Engine, root: Path, epoch: list[int]) -> None:
    from marketlab.datasets.v2 import native_children
    from marketlab.datasets.v2.admission import _files, binding

    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        bound = binding(connection, root)
        if bound is None:
            raise V2Error("unavailable", "Shared accounting root required")
        epoch.append(int(bound["epoch"]))
        physical = local_root(connection)
        if physical is None:
            raise V2Error("unavailable", "Local root required")
        files = {
            r["relative_path"]: dict(r)
            for r in execute(
                connection,
                "SELECT * FROM v2_worker_files WHERE root_id=:root",
                root=physical["root_id"],
            ).mappings()
        }
        tickets = [
            dict(r)
            for r in execute(
                connection,
                "SELECT t.*,c.relative_path,c.ceiling_bytes FROM v2_admission_tickets t "
                "JOIN v2_data_charges c USING(ticket_id) WHERE t.worker_root_id=:root "
                "AND t.state<>'released'",
                root=physical["root_id"],
            ).mappings()
        ]
        reservations = [
            dict(r)
            for r in execute(
                connection,
                "SELECT * FROM v2_research_reservations WHERE worker_root_id=:root "
                "AND state='active'",
                root=physical["root_id"],
            ).mappings()
        ]
        transferred = _transferred_ingestion_space(connection, physical["root_id"])
        seen: set[str] = set()
        totals: dict[str, int] = {}

        def managed(path: str, size: int) -> bool:
            for reservation in reservations:
                if not path.startswith(reservation["relative_root"] + "/"):
                    continue
                native = reservation["materialization_native_identity"]
                if native is not None and not native_children.alive(json.loads(native)):
                    continue
                key = str(reservation["reservation_id"])
                ceiling = sum(
                    reservation[name] for name in ("scratch_bytes", "spill_bytes", "output_bytes")
                )
                totals[key] = totals.get(key, 0) + size
                if totals[key] > ceiling:
                    raise V2Error("integrity_failure", "Local scratch exceeds reservation")
                return True
            for ticket in tickets:
                key = str(ticket["ticket_id"])
                coverage = transferred.get(key)
                ceiling = max(ticket["physical_bytes"], ticket["ceiling_bytes"])
                prefixes = [ticket["relative_path"]]
                if coverage is not None:
                    prefixes = [coverage[0]]
                    ceiling = coverage[1]
                elif ticket["role"] == "ingestion":
                    prefixes.append(
                        f"attempts-v2/{ticket['resource_id']}/{ticket['fencing_token']}"
                    )
                if not any(
                    prefix and (path == prefix or path.startswith(prefix + "/"))
                    for prefix in prefixes
                ):
                    continue
                if not native_children.alive(json.loads(ticket["native_identity"])):
                    continue
                totals[key] = totals.get(key, 0) + size
                if totals[key] > ceiling:
                    raise V2Error("integrity_failure", "Local output exceeds reservation")
                return True
            return False

        def removed(path: str) -> bool:
            return path not in files and managed(path, 0)

        for path, size, modified, _ in _files(root, hashes=False, missing=removed):
            expected = files.get(path)
            if expected is not None:
                seen.add(path)
                if (size, modified) != (expected["file_bytes"], expected["mtime_ns"]):
                    raise V2Error("integrity_failure", "Retained local bytes changed")
            elif not managed(path, size):
                raise V2Error("integrity_failure", "Unmanaged local bytes require reconciliation")
        if seen != files.keys():
            raise V2Error("integrity_failure", "Retained local bytes are missing")


@contextmanager
def lifecycle(
    engine: Engine,
    root: Path,
    kind: str,
    execution: str,
    root_id: str | None = None,
    stop: threading.Event | None = None,
) -> Iterator[None]:
    """Normal CLI lifecycle; failure stops claims, local work retains its own heartbeat."""
    from marketlab.db_transport import configure

    configure(engine)
    with engine.connect() as connection:
        current = mode(connection)
    if current is None or (current["mode"] == "local" and root_id is None):
        yield
        return
    if root_id is None:
        raise V2Error("unavailable", "Explicit provisioned worker root is required")
    uid(root_id)
    root = root.resolve()
    native = native_identity.current()
    source, lock_sha = source_identity()
    if kind not in CONTRACTS or not isinstance(execution, str) or not HASH.fullmatch(execution):
        raise V2Error("invalid_request", "Invalid worker execution capability")
    if kind == "ingestion":
        from marketlab.datasets.v2.core import execution_identity

        expected_execution = execution_identity()["execution_sha256"]
    elif kind == "research":
        expected_execution = source
    else:
        from marketlab.copilot.v2.model import execution as model_execution

        expected_execution = digest(model_execution(kind))
    if execution != expected_execution:
        raise V2Error("unavailable", "Worker execution source identity mismatch")
    instance = str(uuid4())
    if shutil.disk_usage(root).free < 50 * 1024**3:
        raise V2Error("capacity_exceeded", "Worker requires 50 GiB free space")
    with transaction(engine) as connection:
        row = one(
            connection, "SELECT * FROM v2_worker_roots WHERE root_id=:id FOR SHARE", id=root_id
        )
        if (
            row is None
            or not row["ready"]
            or row["local_path"] != str(root)
            or row["boot_identity"] != native["boot"]
        ):
            raise V2Error("unavailable", "Worker root ownership mismatch")
        if current["mode"] == "distributed":
            from marketlab.config import Settings
            from marketlab.storage.backend import ObjectConfig
            from marketlab.storage.store import verify_namespace

            shared = one(
                connection,
                "SELECT * FROM v2_capacity_roots WHERE root_id=:id",
                id=current["shared_root_id"],
            )
            if shared is None:
                raise V2Error("unavailable", "Shared root is unavailable")
            config = ObjectConfig.from_settings(Settings())
            verify_namespace(shared, config)
            if config is None:
                raise V2Error("unavailable", "Shared object storage is required")
        execute(
            connection,
            "INSERT INTO v2_worker_instances(instance_id,root_id,source_sha256,lock_sha256,"
            "boot_identity,native_identity,state) "
            "VALUES(:id,:root,:source,:lock,:boot,:native,'ready')",
            id=instance,
            root=root_id,
            source=source,
            lock=lock_sha,
            boot=native["boot"],
            native=canonical_json(native).decode(),
        )
        execute(
            connection,
            "INSERT INTO v2_worker_capabilities VALUES(:id,:kind,:contract,:execution)",
            id=instance,
            kind=kind,
            contract=CONTRACTS[kind],
            execution=execution,
        )
    original = dict(engine.get_execution_options())
    engine.update_execution_options(
        worker_instance_id=instance,
        worker_root_id=root_id,
        worker_stop_event=stop,
        worker_source_sha256=source,
        worker_lock_sha256=lock_sha,
    )
    done = threading.Event()

    def heartbeat() -> None:
        from marketlab.inference import _bounded_query

        while not done.wait(10):
            try:
                with engine.connect() as connection:
                    if done.is_set():
                        return
                    state = "draining" if stop and stop.is_set() else "ready"
                    if not _bounded_query(
                        connection,
                        (
                            "WITH changed AS (UPDATE v2_worker_instances SET "
                            "heartbeat_at=clock_timestamp(),"
                            f"state='{state}' WHERE instance_id='{instance}' AND state IN "
                            "('ready','draining') RETURNING instance_id) "
                            "SELECT EXISTS(SELECT 1 FROM changed)"
                        ).encode(),
                    ):
                        raise V2Error("unavailable", "Worker registration heartbeat lost")
            except Exception:
                if stop is not None:
                    stop.set()
                return

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        yield
    finally:
        done.set()
        thread.join(15)
        try:
            if thread.is_alive():
                raise V2Error("unavailable", "Worker heartbeat has not drained")
            from marketlab.inference import _bounded_query

            with engine.connect() as connection:
                _bounded_query(
                    connection,
                    (
                        "WITH changed AS (UPDATE v2_worker_instances SET state='stopped',"
                        f"heartbeat_at=clock_timestamp() WHERE instance_id='{instance}' "
                        "RETURNING instance_id) "
                        "SELECT EXISTS(SELECT 1 FROM changed)"
                    ).encode(),
                )
        finally:
            engine.update_execution_options(
                worker_instance_id=original.get("worker_instance_id"),
                worker_root_id=original.get("worker_root_id"),
                worker_stop_event=original.get("worker_stop_event"),
                worker_source_sha256=original.get("worker_source_sha256"),
                worker_lock_sha256=original.get("worker_lock_sha256"),
            )


def inspect_workers(engine: Engine, limit: int = 25, cursor: str | None = None) -> dict[str, Any]:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise V2Error("invalid_request", "Invalid worker page limit")
    after = uid(cursor) if cursor is not None else None
    with engine.connect() as connection:
        rows = [
            dict(r)
            for r in execute(
                connection,
                "SELECT i.*,h.host_id,h.operator_label, "
                "i.heartbeat_at>clock_timestamp()-interval '30 seconds' AS fresh "
                "FROM v2_worker_instances i JOIN v2_worker_roots r USING(root_id) "
                "JOIN v2_worker_hosts h USING(host_id) WHERE (CAST(:after AS uuid) IS NULL "
                "OR i.instance_id>:after) ORDER BY i.instance_id LIMIT :limit",
                after=after,
                limit=limit + 1,
            ).mappings()
        ]
    return {
        "items": wire(rows[:limit]),
        "next_cursor": str(rows[limit - 1]["instance_id"]) if len(rows) > limit else None,
    }


def inspect_attempts(
    engine: Engine, kind: str, limit: int = 25, cursor: str | None = None
) -> dict[str, Any]:
    if kind not in CONTRACTS or type(limit) is not int or not 1 <= limit <= 100:
        raise V2Error("invalid_request", "Invalid attempt page")
    import base64

    after, attempt = None, 0
    if cursor is not None:
        try:
            if len(cursor) > 2048:
                raise ValueError
            value = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
            if (
                value["kind"] != kind
                or type(value["attempt"]) is not int
                or not 1 <= value["attempt"] <= 3
            ):
                raise ValueError
            after, attempt = uid(value["identity"]), value["attempt"]
        except (ValueError, KeyError, TypeError) as error:
            raise V2Error("invalid_request", "Invalid attempt cursor") from error
    ident = "job_id" if kind in {"copilot", "ingestion"} else "run_id"
    with engine.connect() as connection:
        rows = [
            dict(r)
            for r in execute(
                connection,
                f"SELECT a.*,h.operator_label FROM v2_{kind}_attempts a "
                "LEFT JOIN v2_worker_instances i ON i.instance_id=a.worker_instance_id "
                "LEFT JOIN v2_worker_roots r ON r.root_id=i.root_id "
                "LEFT JOIN v2_worker_hosts h USING(host_id) "
                "WHERE CAST(:after AS uuid) IS NULL OR "
                f"(a.{ident},a.attempt_number)>(:after,:attempt) "
                f"ORDER BY a.{ident},a.attempt_number LIMIT :limit",
                after=after,
                attempt=attempt,
                limit=limit + 1,
            ).mappings()
        ]
    next_cursor = None
    if len(rows) > limit:
        row = rows[limit - 1]
        next_cursor = base64.urlsafe_b64encode(
            canonical_json(
                {"kind": kind, "identity": str(row[ident]), "attempt": row["attempt_number"]}
            )
        ).decode()
    return {"items": wire(rows[:limit]), "next_cursor": next_cursor}
