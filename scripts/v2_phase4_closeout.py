"""Finite Phase 4 inventory, preservation, verified backup, and owned cleanup.

Run each command explicitly. Inspection never cancels work. Backup never removes
resources. Cleanup requires a completed backup and rechecks its exact targets.
Historical queued work and model results remain data, not execution requests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa

try:
    from .v2_phase4_snapshot import compare, snapshot
except ImportError:  # Direct execution from scripts/.
    from v2_phase4_snapshot import compare, snapshot

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
OLD = ARTIFACTS / "v2-phase4-20261030"
OWNER = "v2-phase4-20261030"
LABEL = "marketlab.v2phase4.owner"
PG_ID = "bf0d897b0106e45b7c2291d6e1376976fc2f91986a0d465984648ef5130ef7f6"
DEFAULT_CONFIG = OLD / "connection-actual-private.json"
CONTAINER_KEYS = (
    "Id",
    "Name",
    "Image",
    "Labels",
    "Mounts",
    "HostBindings",
    "Running",
    "StartedAt",
    "RestartCount",
    "NetworkMode",
    "Entrypoint",
    "Cmd",
)
WORK_TABLES = (
    "v2_ingestion_jobs",
    "v2_research_runs",
    "ingestion_jobs",
    "research_runs",
    "v2_canonical_imports",
    "v2_upload_generations",
    "v2_admission_tickets",
    "memo_jobs",
    "copilot_jobs",
)
VOLUME_HASH_CODE = """
import hashlib,json,os,stat
from pathlib import Path
root=Path('/source');rows=[]
def failed(error): raise error
for directory,dirs,files in os.walk(root,onerror=failed,followlinks=False):
 for name in dirs:
  assert not (Path(directory)/name).is_symlink(),'Linked source directory'
 for name in sorted(files):
  p=Path(directory)/name
  assert not p.is_symlink() and stat.S_ISREG(p.lstat().st_mode),'Nonregular source file'
  with p.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
  rows.append({'path':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':digest})
print(json.dumps(sorted(rows,key=lambda x:x['path'])))
"""
VOLUME_COPY_CODE = """
import os,shutil,stat
from pathlib import Path
root=Path('/source');out=Path('/export')
assert out.is_dir() and not any(out.iterdir()),'Export must be a fresh empty directory'
def failed(error): raise error
for directory,dirs,files in os.walk(root,onerror=failed,followlinks=False):
 target=out/Path(directory).relative_to(root)
 target.mkdir(parents=True,exist_ok=True)
 for name in dirs:
  assert not (Path(directory)/name).is_symlink(),'Linked source directory'
 for name in files:
  source=Path(directory)/name
  assert not source.is_symlink() and stat.S_ISREG(source.lstat().st_mode),'Nonregular source'
  shutil.copyfile(source,target/name)
"""


def need(condition: Any, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def utc() -> str:
    return datetime.now(UTC).isoformat()


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_artifact(path: Path | str) -> Path:
    value = Path(path).absolute()
    need(value.resolve().is_relative_to(ARTIFACTS.resolve()), "Path escapes artifacts")
    need(value.resolve() != ARTIFACTS.resolve(), "Artifacts root is not a file target")
    for part in (value, *value.parents):
        need(not part.is_symlink() and not part.is_junction(), "Linked artifact path")
        if part == ROOT:
            break
    return value.resolve()


def read(path: Path | str) -> Any:
    return json.loads(safe_artifact(path).read_text(encoding="utf-8-sig"))


def save(path: Path, value: Any, *, replace: bool = False) -> None:
    path = safe_artifact(path)
    if replace:
        temporary = path.with_suffix(".tmp")
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, default=str)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    else:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, default=str)
            stream.write("\n")


def output_folder(path: Path) -> Path:
    folder = safe_artifact(path)
    folder.mkdir(parents=True, exist_ok=False)
    return folder


def docker(*args: str, timeout: int = 60, stdin: Any = None, stdout: Any = None) -> bytes:
    result = subprocess.run(
        ["docker", *args],
        stdin=stdin,
        stdout=stdout or subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    detail = (result.stderr or b"").decode(errors="replace")[-2000:].strip()
    need(result.returncode == 0, f"Docker {args[0]} failed (exit {result.returncode}): {detail}")
    return result.stdout or b""


def docker_json(*args: str) -> Any:
    return json.loads(docker(*args))


def container(identifier: str) -> dict[str, Any]:
    raw = docker_json("inspect", identifier)[0]
    # Exclude environment values and other credential-bearing configuration.
    return {
        "Id": raw["Id"],
        "Name": raw["Name"],
        "Image": raw["Image"],
        "Labels": raw["Config"].get("Labels") or {},
        "Mounts": raw["Mounts"],
        "HostBindings": raw["HostConfig"]["PortBindings"],
        "Running": raw["State"]["Running"],
        "StartedAt": raw["State"]["StartedAt"],
        "ExitCode": raw["State"]["ExitCode"],
        "RestartCount": raw["RestartCount"],
        "NetworkMode": raw["HostConfig"]["NetworkMode"],
        "Entrypoint": raw["Config"]["Entrypoint"],
        "Cmd": raw["Config"]["Cmd"],
    }


def originals() -> list[dict[str, Any]]:
    return read(ARTIFACTS / "v2-phase3-20261029" / "services-before.json")["services"]


def resource_inventory() -> dict[str, Any]:
    ids = docker("ps", "-aq", "--no-trunc", "--filter", f"label={LABEL}={OWNER}").decode().split()
    rows = [container(identifier) for identifier in sorted(ids)]
    protected = originals()
    need(not set(ids) & {row["Id"] for row in protected}, "Protected container selected")
    need(any(row["Id"] == PG_ID for row in rows), "Exact isolated PostgreSQL is missing")
    for row in rows:
        need(row["Labels"].get(LABEL) == OWNER, "Container ownership mismatch")
        need(row["Name"].startswith("/marketlab-v2p4-"), "Unexpected owned container name")
    volumes = docker("volume", "ls", "-q", "--filter", f"label={LABEL}={OWNER}").decode().split()
    volume_rows = [docker_json("volume", "inspect", name)[0] for name in sorted(volumes)]
    networks = (
        docker("network", "ls", "-q", "--no-trunc", "--filter", f"label={LABEL}={OWNER}")
        .decode()
        .split()
    )
    network_rows = [
        docker_json("network", "inspect", identifier)[0] for identifier in sorted(networks)
    ]
    for row in network_rows:
        need(set(row.get("Containers", {})) <= set(ids), "Foreign network attachment")
    image_ids = set(
        docker("image", "ls", "-q", "--no-trunc", "--filter", f"label={LABEL}={OWNER}")
        .decode()
        .split()
    )
    images = []
    for identifier in sorted(image_ids):
        raw = docker_json("image", "inspect", identifier)[0]
        images.append(
            {
                "Id": raw["Id"],
                "RepoTags": sorted(raw.get("RepoTags") or []),
                "Labels": raw["Config"].get("Labels") or {},
            }
        )
    result = {
        "containers": rows,
        "volumes": volume_rows,
        "networks": network_rows,
        "images": images,
    }
    validate_resources(result, protected)
    return result


def validate_resources(resources: dict[str, Any], protected: list[dict[str, Any]]) -> None:
    ids = {row["Id"] for row in resources["containers"]}
    need(not ids & {row["Id"] for row in protected}, "Protected container selected")
    protected_volumes = {
        mount["Name"] for row in protected for mount in row["Mounts"] if mount["Type"] == "volume"
    }
    need(
        not {row["Name"] for row in resources["volumes"]} & protected_volumes,
        "Protected volume selected",
    )
    need(
        not {row["Id"] for row in resources["images"]} & {row["Image"] for row in protected},
        "Protected image selected",
    )
    for kind in ("containers", "volumes", "networks", "images"):
        for row in resources[kind]:
            need(row.get("Labels", {}).get(LABEL) == OWNER, f"{kind} ownership mismatch")
    for network in resources["networks"]:
        need(set(network.get("Containers", {})) <= ids, "Foreign network attachment")
    selected_volumes = {row["Name"] for row in resources["volumes"]}
    for row in resources["containers"]:
        need(
            all(
                mount["Name"] in selected_volumes
                for mount in row["Mounts"]
                if mount["Type"] == "volume"
            ),
            "Unowned attached volume",
        )


def same_resources(saved: dict[str, Any], current: dict[str, Any]) -> None:
    for kind, key in (
        ("containers", "Id"),
        ("volumes", "Name"),
        ("networks", "Id"),
        ("images", "Id"),
    ):
        left = {row[key]: row for row in saved[kind]}
        right = {row[key]: row for row in current[kind]}
        need(left.keys() == right.keys(), f"{kind} inventory changed")
        for identifier, row in left.items():
            if kind == "containers":
                need(
                    all(row[field] == right[identifier][field] for field in CONTAINER_KEYS),
                    "Container identity/lifecycle changed",
                )
            elif kind == "networks":
                need(
                    all(
                        row[field] == right[identifier][field]
                        for field in ("Id", "Name", "Labels", "Containers")
                    ),
                    "Network identity/attachments changed",
                )
            else:
                need(row == right[identifier], f"{kind} identity changed")


def database_url(config_path: Path) -> sa.engine.URL:
    config = read(config_path)
    need(config.get("owner") == OWNER, "Private configuration ownership mismatch")
    pg = container(PG_ID)
    need(
        pg["Name"] == "/marketlab-v2p4-pg" and pg["Labels"].get(LABEL) == OWNER,
        "Wrong PostgreSQL target",
    )
    url = sa.engine.make_url(config["database_url"])
    bindings = pg["HostBindings"].get("5432/tcp", [])
    need(
        url.host == "127.0.0.1"
        and any(
            binding["HostIp"] == "127.0.0.1" and str(url.port) == binding["HostPort"]
            for binding in bindings
        ),
        "Database URL does not target owned PostgreSQL",
    )
    return url.set(database="postgres")


def database_names(url: sa.engine.URL) -> list[str]:
    engine = sa.create_engine(url)
    try:
        with engine.connect() as connection:
            connection.execute(sa.text("SET TRANSACTION READ ONLY"))
            names = list(
                connection.execute(
                    sa.text(
                        "SELECT datname FROM pg_database WHERE NOT datistemplate AND "
                        "datname<>'postgres' ORDER BY datname"
                    )
                ).scalars()
            )
    finally:
        engine.dispose()
    need(
        all(re.fullmatch(r"[a-z][a-z0-9_]{0,62}", name) for name in names),
        "Unsupported owned database identifier",
    )
    return names


def work_inventory(url: sa.engine.URL, names: list[str]) -> list[dict[str, Any]]:
    rows = []
    for name in names:
        engine = sa.create_engine(url.set(database=name))
        try:
            with engine.connect() as connection:
                connection.execute(sa.text("SET TRANSACTION READ ONLY"))
                tables = set(
                    connection.execute(
                        sa.text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                    ).scalars()
                )
                states = {}
                blockers = []
                for table in WORK_TABLES:
                    if table not in tables:
                        continue
                    states[table] = [
                        list(row)
                        for row in connection.execute(
                            sa.text(
                                f"SELECT state,count(*) FROM {table} GROUP BY state ORDER BY state"
                            )
                        )
                    ]
                    columns = set(
                        connection.execute(
                            sa.text(
                                "SELECT column_name FROM information_schema.columns WHERE "
                                "table_schema='public' AND table_name=:table"
                            ),
                            {"table": table},
                        ).scalars()
                    )
                    active = (
                        "state<>'released'"
                        if table == "v2_admission_tickets"
                        else "state IN ('running','staging','uploading','claimed')"
                    )
                    owners = (
                        []
                        if table == "v2_admission_tickets"
                        else [
                            f"{column} IS NOT NULL"
                            for column in (
                                "owner",
                                "lease_until",
                                "staging_owner",
                                "staging_lease_until",
                            )
                            if column in columns
                        ]
                    )
                    predicate = " OR ".join([active, *owners])
                    count = connection.execute(
                        sa.text(f"SELECT count(*) FROM {table} WHERE {predicate}")
                    ).scalar_one()
                    if count:
                        blockers.append({"table": table, "active_or_owned_rows": count})
                transactions = connection.execute(
                    sa.text(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                        "AND pid<>pg_backend_pid() AND (xact_start IS NOT NULL OR state<>'idle')"
                    )
                ).scalar_one()
                if transactions:
                    blockers.append({"other_active_database_sessions": transactions})
                revision = (
                    connection.execute(
                        sa.text("SELECT version_num FROM alembic_version")
                    ).scalar_one_or_none()
                    if "alembic_version" in tables
                    else None
                )
                rows.append(
                    {"database": name, "revision": revision, "states": states, "blockers": blockers}
                )
        finally:
            engine.dispose()
    return rows


def require_quiescent(url: sa.engine.URL, names: list[str]) -> list[dict[str, Any]]:
    rows = work_inventory(url, names)
    need(
        not any(row["blockers"] for row in rows),
        "Current owned work/transactions must drain; inspect report identifies rows",
    )
    return rows


def preserve(folder: Path, name: str) -> dict[str, Any]:
    protected = read(ARTIFACTS / "v2-phase3-20261029" / "protected-before.json")["files"]
    hashes = [
        {
            "path": row["path"],
            "match": (ROOT / row["path"]).is_file() and sha(ROOT / row["path"]) == row["sha256"],
        }
        for row in protected
    ]
    services = []
    for baseline in originals():
        raw = docker_json("inspect", baseline["Id"])[0]
        fields = {key: raw[key] for key in ("Id", "Name", "Image", "RestartCount", "Mounts")}
        fields.update(
            started_at=raw["State"]["StartedAt"],
            running=raw["State"]["Running"],
            health=raw["State"].get("Health", {}).get("Status"),
            Ports=raw["NetworkSettings"]["Ports"],
            compose_project=(raw["Config"].get("Labels") or {}).get("com.docker.compose.project"),
            compose_service=(raw["Config"].get("Labels") or {}).get("com.docker.compose.service"),
        )
        differences = [key for key, value in baseline.items() if fields.get(key) != value]
        image_present = (
            docker_json("image", "inspect", baseline["Image"])[0]["Id"] == baseline["Image"]
        )
        services.append(
            {"id": baseline["Id"], "differences": differences, "image_present": image_present}
        )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    endpoints = []
    for endpoint in ("/health/live", "/health/ready"):
        with opener.open("http://127.0.0.1:8000" + endpoint, timeout=10) as response:
            endpoints.append({"path": endpoint, "status": response.status})
    passed = (
        len(hashes) == 287
        and len(services) == 5
        and all(row["match"] for row in hashes)
        and all(not row["differences"] and row["image_present"] for row in services)
        and all(row["status"] == 200 for row in endpoints)
    )
    result = {
        "utc": utc(),
        "protected": hashes,
        "original_services": services,
        "endpoints": endpoints,
        "passed": passed,
        "limitation": "Point observations; no continuous uptime claim",
    }
    save(folder / f"{name}.json", result)
    need(passed, "Protected/original preservation check failed")
    return result


def inspect(config: Path, folder: Path) -> dict[str, Any]:
    resources = resource_inventory()
    url = database_url(config)
    names = database_names(url)
    result = {
        "schema": "phase4-completion-inventory-v1",
        "owner": OWNER,
        "utc": utc(),
        "resources": resources,
        "databases": names,
        "work": work_inventory(url, names),
        "historical_policy": "Retain queued work/model history; no worker or model execution "
        "follows from this inventory",
    }
    save(folder / "inventory.json", result)
    preserve(folder, "preservation")
    return result


def reconcile(config: Path, name: str, job_id: str, folder: Path) -> dict[str, Any]:
    """Cancel one explicitly selected queued job through the existing service."""
    from marketlab.datasets.v2.jobs import cancel

    url = database_url(config)
    need(name in database_names(url), "Selected database is not in the owned inventory")
    identity = str(uuid.UUID(job_id))
    engine = sa.create_engine(url.set(database=name))
    try:
        with engine.connect() as connection:
            job = (
                connection.execute(
                    sa.text(
                        "SELECT state,revision,attempt_count FROM v2_ingestion_jobs "
                        "WHERE job_id=:id"
                    ),
                    {"id": identity},
                )
                .mappings()
                .one()
            )
            need(
                job["state"] in ("queued", "retry_wait", "cancelled"),
                "Only an explicitly selected non-running queued job may be reconciled",
            )
            # Cancellation must never forgive retained source or failure charges.
            before = list(
                connection.execute(
                    sa.text(
                        "SELECT row_to_json(t)::text FROM v2_storage_reservations t "
                        "ORDER BY reservation_id"
                    )
                ).scalars()
            )
        outcome = cancel(engine, identity, job["revision"], "phase4-closeout-" + uuid.uuid4().hex)
        with engine.connect() as connection:
            after = list(
                connection.execute(
                    sa.text(
                        "SELECT row_to_json(t)::text FROM v2_storage_reservations t "
                        "ORDER BY reservation_id"
                    )
                ).scalars()
            )
        need(before == after, "Cancellation changed retained storage reservations")
        need(
            outcome["state"] == "cancelled" and outcome["attempt_count"] == job["attempt_count"],
            "Cancellation did not preserve the selected job attempt history",
        )
        result = {
            "owner": OWNER,
            "utc": utc(),
            "state": "passed",
            "database": name,
            "job_id": identity,
            "job_state": outcome["state"],
            "attempt_count": outcome["attempt_count"],
            "reservations_unchanged": True,
        }
        save(folder / "reconciliation.json", result)
        return result
    finally:
        engine.dispose()


def file_inventory(root: Path) -> list[dict[str, Any]]:
    root = safe_artifact(root)
    need(root.is_dir(), "Export directory missing")
    rows = []

    def failed(error: OSError) -> None:
        raise error

    for directory, directories, files in os.walk(root, onerror=failed, followlinks=False):
        for item in directories:
            safe_artifact(Path(directory) / item)
        for item in sorted(files):
            path = safe_artifact(Path(directory) / item)
            need(path.is_file(), "Nonregular exported file")
            rows.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha(path),
                }
            )
    return sorted(rows, key=lambda row: row["path"])


def volume_inventory(image: str, volume: str) -> list[dict[str, Any]]:
    name = "marketlab-v2p4-closeout-check-" + uuid.uuid4().hex[:12]
    output = docker(
        "run",
        "--rm",
        "--name",
        name,
        "--label",
        f"{LABEL}={OWNER}",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--mount",
        f"type=volume,source={volume},target=/source,readonly",
        "--entrypoint",
        "python",
        image,
        "-B",
        "-c",
        VOLUME_HASH_CODE,
        timeout=900,
    )
    return json.loads(output)


def export_packages(resources: dict[str, Any], folder: Path) -> list[dict[str, Any]]:
    exports = []
    for row in resources["containers"]:
        if not row["Name"].startswith("/marketlab-v2p4-package"):
            continue
        need(not row["Running"], "Stop owned package containers cooperatively before backup")
        mounts = [
            mount
            for mount in row["Mounts"]
            if mount["Type"] == "volume" and mount["Destination"] == "/data/marketlab"
        ]
        need(len(mounts) == 1, "Package data mount is ambiguous")
        volume = mounts[0]["Name"]
        before = volume_inventory(row["Image"], volume)
        destination = folder / row["Name"].lstrip("/")
        destination.mkdir()
        # Docker's archive endpoint could not see the stopped package's data
        # mount. Export the exact verified volume through a read-only mount;
        # only this fresh contained host destination is writable.
        docker(
            "run",
            "--rm",
            "--name",
            "marketlab-v2p4-closeout-export-" + uuid.uuid4().hex[:12],
            "--label",
            f"{LABEL}={OWNER}",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--mount",
            f"type=volume,source={volume},target=/source,readonly",
            "--mount",
            f"type=bind,source={safe_artifact(destination)},target=/export",
            "--entrypoint",
            "python",
            row["Image"],
            "-B",
            "-c",
            VOLUME_COPY_CODE,
            timeout=900,
        )
        exported = file_inventory(destination)
        need(
            before == exported == volume_inventory(row["Image"], volume),
            "Package volume export changed or differs",
        )
        exports.append(
            {
                "container": row["Id"],
                "image": row["Image"],
                "volume": volume,
                "directory": str(destination),
                "files": exported,
            }
        )
    return exports


def engine_snapshot(url: sa.engine.URL) -> dict[str, Any]:
    engine = sa.create_engine(url)
    try:
        return snapshot(engine)
    finally:
        engine.dispose()


def backup(config: Path, inventory_path: Path, folder: Path) -> dict[str, Any]:
    inventory = read(inventory_path)
    need(
        inventory["schema"] == "phase4-completion-inventory-v1" and inventory["owner"] == OWNER,
        "Invalid owned inventory",
    )
    same_resources(inventory["resources"], resource_inventory())
    need(
        all(
            not row["Running"]
            for row in inventory["resources"]["containers"]
            if row["Name"].startswith("/marketlab-v2p4-package")
        ),
        "Owned package APIs must stop before final inventory/backup",
    )
    url = database_url(config)
    names = database_names(url)
    need(names == inventory["databases"], "Database inventory changed")
    quiescent = require_quiescent(url, names)
    preserve(folder, "preservation-before")
    record = {
        "schema": "phase4-completion-backup-v1",
        "owner": OWNER,
        "started_utc": utc(),
        "state": "running",
        "inventory": str(inventory_path.resolve()),
        "inventory_sha256": sha(inventory_path),
        "source_databases": names,
        "work_before": quiescent,
        "databases": [],
        "exports": [],
    }
    save(folder / "receipt.json", record)
    try:
        for index, name in enumerate(names):
            require_quiescent(url, [name])
            before = engine_snapshot(url.set(database=name))
            before_path = folder / f"database-{index}-before.json"
            save(before_path, before)
            dump = folder / f"{name}.dump"
            with dump.open("xb") as target:
                docker(
                    "exec",
                    PG_ID,
                    "pg_dump",
                    "-U",
                    "marketlab",
                    "-Fc",
                    "--no-owner",
                    "--no-acl",
                    name,
                    stdout=target,
                    timeout=900,
                )
            digest = sha(dump)
            restored_name = f"p4c_{uuid.uuid4().hex[:12]}_{index}"
            docker("exec", PG_ID, "createdb", "-U", "marketlab", restored_name)
            admin = sa.create_engine(url, isolation_level="AUTOCOMMIT")
            try:
                metadata = json.dumps(
                    {
                        "owner": OWNER,
                        "kind": "phase4-final-restore",
                        "source_database": name,
                        "source_dump_sha256": digest,
                    },
                    sort_keys=True,
                )
                with admin.connect() as connection:
                    connection.exec_driver_sql(
                        "COMMENT ON DATABASE "
                        + admin.dialect.identifier_preparer.quote(restored_name)
                        + " IS '"
                        + metadata.replace("'", "''")
                        + "'"
                    )
            finally:
                admin.dispose()
            with dump.open("rb") as source:
                docker(
                    "exec",
                    "-i",
                    PG_ID,
                    "pg_restore",
                    "-U",
                    "marketlab",
                    "-d",
                    restored_name,
                    "--no-owner",
                    "--no-acl",
                    "--exit-on-error",
                    stdin=source,
                    timeout=900,
                )
            restored = sa.create_engine(url.set(database=restored_name))
            try:
                after = snapshot(restored)
                normalizations = compare(before, after, restored)
            finally:
                restored.dispose()
            need(
                engine_snapshot(url.set(database=name)) == before,
                "Source database changed during dump/restore",
            )
            restored_path = folder / f"database-{index}-restored.json"
            save(restored_path, after)
            record["databases"].append(
                {
                    "source": name,
                    "restore": restored_name,
                    "dump": str(dump),
                    "dump_sha256": digest,
                    "before": str(before_path),
                    "restored": str(restored_path),
                    "constraint_normalizations": normalizations,
                }
            )
            save(folder / "receipt.json", record, replace=True)
        record["exports"] = export_packages(inventory["resources"], folder)
        expected = set(names) | {row["restore"] for row in record["databases"]}
        need(set(database_names(url)) == expected, "Database inventory changed during backup")
        require_quiescent(url, sorted(expected))
        same_resources(inventory["resources"], resource_inventory())
        preserve(folder, "preservation-after")
        record.update(state="passed", ended_utc=utc(), backup_verification_passed=True)
    except BaseException as error:
        record.update(state="failed", ended_utc=utc(), error_type=type(error).__name__)
        raise
    finally:
        save(folder / "receipt.json", record, replace=True)
    return record


def validate_backup(
    record: dict[str, Any], inventory: dict[str, Any], inventory_path: Path
) -> None:
    need(
        record.get("schema") == "phase4-completion-backup-v1"
        and record.get("owner") == OWNER
        and record.get("state") == "passed"
        and record.get("backup_verification_passed") is True,
        "Verified backup is required",
    )
    need(record["inventory_sha256"] == sha(inventory_path), "Backup inventory changed")
    need(record["source_databases"] == inventory["databases"], "Backup source inventory differs")
    need(
        len(record["databases"]) == len(inventory["databases"])
        and {row["source"] for row in record["databases"]} == set(inventory["databases"]),
        "Backup omits or duplicates a source database",
    )
    for row in record["databases"]:
        need(sha(safe_artifact(row["dump"])) == row["dump_sha256"], "Retained dump changed")
    package_rows = {
        row["Id"]: row
        for row in inventory["resources"]["containers"]
        if row["Name"].startswith("/marketlab-v2p4-package")
    }
    packages = set(package_rows)
    need(
        {row["container"] for row in record["exports"]} == packages
        and len(record["exports"]) == len(packages),
        "Package export coverage differs",
    )
    for export in record["exports"]:
        package = package_rows[export["container"]]
        mounts = [
            mount
            for mount in package["Mounts"]
            if mount["Type"] == "volume" and mount.get("Destination") == "/data/marketlab"
        ]
        need(
            len(mounts) == 1
            and export["volume"] == mounts[0]["Name"]
            and export["image"] == package["Image"],
            "Package export source binding differs",
        )


def cleanup(config: Path, inventory_path: Path, backup_path: Path, folder: Path) -> dict[str, Any]:
    inventory = read(inventory_path)
    verified = read(backup_path)
    validate_backup(verified, inventory, inventory_path)
    resources = resource_inventory()
    same_resources(inventory["resources"], resources)
    url = database_url(config)
    names = set(inventory["databases"]) | {row["restore"] for row in verified["databases"]}
    need(set(database_names(url)) == names, "Database inventory changed since backup")
    require_quiescent(url, sorted(names))
    for row in verified["databases"]:
        need(
            engine_snapshot(url.set(database=row["source"])) == read(row["before"]),
            "Source changed since backup",
        )
        need(
            engine_snapshot(url.set(database=row["restore"])) == read(row["restored"]),
            "Verified restore changed",
        )
    for export in verified["exports"]:
        need(
            file_inventory(Path(export["directory"]))
            == export["files"]
            == volume_inventory(export["image"], export["volume"]),
            "Export or source volume changed",
        )
    preserve(folder, "preservation-before")
    # Check every attachment, including unlabeled containers, before deletion.
    all_ids = docker("ps", "-aq", "--no-trunc").decode().split()
    all_rows = [container(identifier) for identifier in all_ids]
    validate_attachment_users(resources, all_rows)
    record = {
        "schema": "phase4-completion-cleanup-v1",
        "owner": OWNER,
        "state": "running",
        "started_utc": utc(),
        "backup": str(backup_path.resolve()),
        "backup_sha256": sha(backup_path),
        "targets": resources,
        "removed": [],
    }
    save(folder / "receipt.json", record)
    try:
        for row in resources["containers"]:
            current = container(row["Id"])
            need(
                all(current[key] == row[key] for key in CONTAINER_KEYS),
                "Container changed before removal",
            )
            if row["Running"]:
                docker("stop", "--time", "30", row["Id"], timeout=60)
                stopped = container(row["Id"])
                need(
                    not stopped["Running"]
                    and all(stopped[key] == row[key] for key in CONTAINER_KEYS if key != "Running"),
                    "Unexpected container lifecycle during stop",
                )
                need(stopped["ExitCode"] == 0, "Owned container did not exit cooperatively")
            docker("rm", row["Id"])
            record["removed"].append({"container": row["Id"]})
            save(folder / "receipt.json", record, replace=True)
        for row in resources["volumes"]:
            need(
                docker_json("volume", "inspect", row["Name"])[0] == row,
                "Volume changed before removal",
            )
            docker("volume", "rm", row["Name"])
            record["removed"].append({"volume": row["Name"]})
        for row in resources["networks"]:
            current = docker_json("network", "inspect", row["Id"])[0]
            need(
                all(current[key] == row[key] for key in ("Id", "Name", "Labels"))
                and not current.get("Containers"),
                "Network changed or is still attached",
            )
            docker("network", "rm", row["Id"])
            record["removed"].append({"network": row["Id"]})
        for row in resources["images"]:
            current = docker_json("image", "inspect", row["Id"])[0]
            need(
                sorted(current.get("RepoTags") or []) == row["RepoTags"]
                and (current["Config"].get("Labels") or {}).get(LABEL) == OWNER,
                "Owned image changed",
            )
            for tag in row["RepoTags"]:
                docker("image", "rm", tag)
            if not row["RepoTags"]:
                docker("image", "rm", row["Id"])
            record["removed"].append({"image": row["Id"]})
        need(
            not docker("ps", "-aq", "--filter", f"label={LABEL}={OWNER}").strip(),
            "Owned containers remain",
        )
        preserve(folder, "preservation-after")
        record.update(state="passed", ended_utc=utc(), host_data_evidence_dumps_retained=True)
    except BaseException as error:
        record.update(state="failed", ended_utc=utc(), error_type=type(error).__name__)
        raise
    finally:
        save(folder / "receipt.json", record, replace=True)
    return record


def validate_attachment_users(resources: dict[str, Any], all_rows: list[dict[str, Any]]) -> None:
    ids = {row["Id"] for row in resources["containers"]}
    for volume in resources["volumes"]:
        attached = {
            row["Id"]
            for row in all_rows
            if any(mount.get("Name") == volume["Name"] for mount in row["Mounts"])
        }
        need(attached <= ids, "Owned volume has a foreign attachment")
    for image in resources["images"]:
        need(
            {row["Id"] for row in all_rows if row["Image"] == image["Id"]} <= ids,
            "Owned image has a foreign user",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "preserve", "reconcile", "backup", "cleanup"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, required=True, help="New artifacts directory")
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--database")
    parser.add_argument("--cancel-job")
    args = parser.parse_args()
    if args.action in ("backup", "cleanup") and args.inventory is None:
        parser.error("--inventory is required")
    if args.action == "cleanup" and args.backup is None:
        parser.error("--backup is required")
    if args.action == "reconcile" and (args.database is None or args.cancel_job is None):
        parser.error("--database and --cancel-job are required for explicit reconciliation")
    folder = output_folder(args.output)
    if args.action == "inspect":
        result = inspect(args.config, folder)
    elif args.action == "preserve":
        result = preserve(folder, "preservation")
    elif args.action == "reconcile":
        result = reconcile(args.config, args.database, args.cancel_job, folder)
    elif args.action == "backup":
        result = backup(args.config, args.inventory, folder)
    else:
        result = cleanup(args.config, args.inventory, args.backup, folder)
    print(
        json.dumps(
            {"action": args.action, "state": result.get("state", "passed"), "output": str(folder)}
        )
    )


if __name__ == "__main__":
    main()
