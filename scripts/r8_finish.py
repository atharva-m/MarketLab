"""Fresh R8 adoption checks and owned-resource closeout; no original restarts.

Select MARKETLAB_R8_PROFILE=adoption-20261027 before invoking. Every command
requires a fresh prefix. Historical uptime failures are never reset by current
interval comparisons. Native process lifecycle remains root-orchestrator owned;
cleanup refuses active API/model/exporter ports instead of guessing PID owners.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path

import httpx
import sqlalchemy as sa
from r8_common import (
    BASE,
    PROFILE,
    Invocation,
    owned_settings,
    processes,
    resource_profile,
    validate_prefix,
)

ROOT = Path(__file__).resolve().parents[1]
MONITOR_PROJECT = "marketlab-r8-adoption-20261027-monitoring"
BROWSER_CACHE = Path(
    "C:/Users/athar/AppData/Local/Packages/OpenAI.Codex_2p2nqsd0c76g0/"
    "LocalCache/Local/ms-playwright"
)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def docker(*arguments, timeout=30):
    return subprocess.check_output(["docker", *arguments], text=True, timeout=timeout)


def inspect(identity, kind="container"):
    return json.loads(docker(kind, "inspect", identity))[0]


def one(value):
    return value[0] if isinstance(value, list) else value


def environment(settings):
    return {
        **os.environ,
        "MARKETLAB_DATABASE_URL": settings.sqlalchemy_url.render_as_string(hide_password=False),
        "MARKETLAB_DATABASE_PASSWORD": settings.sqlalchemy_url.password or "",
        "MARKETLAB_REDIS_URL": settings.redis_url.get_secret_value(),
        "MARKETLAB_STORAGE_PATH": str(settings.storage_path),
        "MARKETLAB_OLLAMA_URL": settings.ollama_url,
        "MARKETLAB_METRICS_PORT": "0",
    }


def commands(evidence, prefix, checks, env, cwd=ROOT):
    evidence.data["checks"] = []
    for name, command in checks:
        started = time.monotonic()
        log = BASE / f"{prefix}-{name}.log"
        with log.open("x", encoding="utf-8") as stream:
            result = subprocess.run(
                command, env=env, cwd=cwd, stdout=stream, stderr=stream, timeout=1800
            )
        evidence.data["checks"].append(
            {
                "name": name,
                "command": command,
                "exit_code": result.returncode,
                "seconds": time.monotonic() - started,
                "log": str(log),
            }
        )
        evidence.flush()
        if result.returncode:
            raise RuntimeError(f"Acceptance check failed: {name}")


def checks(evidence, prefix):
    settings = owned_settings()
    uv = str(ROOT / ".venv/Scripts/uv.exe")
    lead = [uv, "run", "--locked", "--offline"]
    commands(
        evidence,
        prefix,
        [
            ("lint", [*lead, "ruff", "check", "."]),
            ("format", [*lead, "ruff", "format", "--check", "."]),
            ("mypy", [*lead, "mypy"]),
            (
                "offline",
                [
                    *lead,
                    "pytest",
                    "-m",
                    "not integration",
                    "-q",
                    "--basetemp=" + str(BASE / f"{prefix}-pytest-offline"),
                ],
            ),
            (
                "integration",
                [
                    *lead,
                    "pytest",
                    "-m",
                    "integration",
                    "-q",
                    "--basetemp=" + str(BASE / f"{prefix}-pytest-integration"),
                ],
            ),
        ],
        environment(settings),
    )


def frontend(evidence, prefix):
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm or not BROWSER_CACHE.is_dir():
        raise RuntimeError("Locked npm/runtime or pristine physical browser cache unavailable")
    env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(BROWSER_CACHE), "CI": "1"}
    commands(
        evidence,
        prefix,
        [
            ("npm-ci", [npm, "ci", "--offline"]),
            *[(name, [npm, "run", name]) for name in ("typecheck", "lint", "test", "build")],
            ("browser", [npm, "run", "test:e2e"]),
        ],
        env,
        ROOT / "frontend",
    )
    evidence.data["browser_scope"] = (
        "Windows Chromium/Firefox/WebKit; physical cache process override"
    )


def load_helper(name):
    path = ROOT / "artifacts/r8" / (name + ".py")
    spec = importlib.util.spec_from_file_location("r8_finish_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_owned_api():
    saved = read(BASE / "owned-api.json")
    if saved.get("owner") != PROFILE.owner or saved.get("port") != 58009:
        raise RuntimeError("Current owned API record required")
    actual = processes().get(int(saved["pid"]))
    if actual is None:
        raise RuntimeError("Current owned API launcher absent")
    birth = actual["identity"] / 10000000 - 11644473600
    if abs(birth - datetime.fromisoformat(saved["creation_time"]).timestamp()) > 0.001:
        raise RuntimeError("Current owned API PID birth changed")


def live(evidence, prefix):
    owned_settings()
    require_owned_api()
    evidence.data["result"] = load_helper("live_legacy").run(58009)
    scenarios = read(ROOT / "artifacts/r7/retained-scenarios.json")[:5]
    from marketlab.analytics.cache import canonical

    rows = []
    with httpx.Client(
        base_url="http://127.0.0.1:58009", trust_env=False, follow_redirects=False, timeout=60
    ) as client:
        for scenario in scenarios:
            run = scenario["run_id"]
            row = {"run_id": run}
            for part in ("results", "summary", "memo"):
                response = client.get(f"/v1/research/runs/{run}/{part}")
                response.raise_for_status()
                body = response.json()
                raw = body["content"].encode() if part == "memo" else canonical(body)
                digest = hashlib.sha256(raw).hexdigest()
                expected = (
                    scenario["memo"]["memo_sha256"]
                    if part == "memo"
                    else scenario["result"][part + "_sha256"]
                )
                if digest != expected:
                    raise AssertionError("Retained API read hash mismatch")
                row[part + "_sha256"] = digest
            rows.append(row)
    if len(rows) != 5:
        raise AssertionError("Five retained scenarios required")
    evidence.data["retained_readback"] = rows


def linux(evidence, prefix):
    import verifier_acceptance as verifier

    settings = owned_settings()
    resources = {
        kind: {"id": one(read(BASE / f"owned-{kind}.json"))["Id"]} for kind in ("postgres", "redis")
    }
    verifier.BASE = BASE
    verifier.owned_settings = lambda: (settings, resources)
    verifier.linux_smoke(prefix)
    result = read(BASE / (prefix + "-linux.json"))
    if result["status"] != "passed":
        raise AssertionError("Packaged Linux acceptance failed")
    evidence.data["result"] = result


def service_identity(row):
    if "Id" not in row:
        return {
            key: row.get(key)
            for key in ("id", "name", "image", "started_at", "restart_count", "health")
        }
    return {
        "id": row["Id"],
        "name": row["Name"],
        "image": row["Image"],
        "started_at": row["State"]["StartedAt"],
        "restart_count": row["RestartCount"],
        "health": row["State"].get("Health", {}).get("Status"),
    }


def originals(evidence, prefix):
    baseline = read(BASE / "original-services-before.json")
    actual = [inspect(row["Id"]) for row in baseline]
    for before, after in zip(baseline, actual, strict=True):
        if service_identity(before) != service_identity(after):
            raise RuntimeError("Original service changed during adoption interval")
        if before["HostConfig"]["PortBindings"] != after["HostConfig"]["PortBindings"]:
            raise RuntimeError("Original service port bindings changed")
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=10) as client:
        endpoints = {}
        for name, path in (("live", "/health/live"), ("ready", "/health/ready")):
            response = client.get("http://127.0.0.1:8000" + path)
            response.raise_for_status()
            endpoints[name] = response.json()
    original_redis = next(row for row in actual if row["Name"] == "/marketlab-redis-1")
    endpoints["redis"] = docker("exec", original_redis["Id"], "redis-cli", "PING").strip()
    if endpoints["redis"] != "PONG":
        raise RuntimeError("Original Redis unavailable")
    endpoint_path = BASE / "current-interval-endpoints-before.json"
    if not endpoint_path.exists():
        with endpoint_path.open("x", encoding="utf-8") as stream:
            json.dump(endpoints, stream, indent=2)
    elif endpoints != read(endpoint_path):
        raise RuntimeError("Original endpoint bodies changed during adoption interval")
    historical = read(ROOT / "artifacts/r8/original-services-before.json")
    historical_equal = [service_identity(row) for row in actual] == [
        service_identity(row) for row in historical
    ]
    result = {
        "current_interval_services": [service_identity(row) for row in actual],
        "endpoints": endpoints,
        "current_interval_preserved": True,
        "historical_oct26_equal": historical_equal,
        "historical_limitation": (
            "Current interval does not restore historical uptime across unknown outage"
        ),
    }
    evidence.data["originals"] = result
    evidence.flush()
    return result


def owned_container(saved, actual, owner, monitoring=False):
    if any(actual[key] != saved[key] for key in ("Id", "Name", "Image")):
        raise RuntimeError("Owned container identity changed")
    labels = actual["Config"].get("Labels") or {}
    if monitoring:
        expected_project = (
            "marketlab-r8-monitoring-20261026" if owner == "r8-20261026" else MONITOR_PROJECT
        )
        if (
            labels.get("marketlab.owner") != "r8-monitoring"
            or labels.get("com.docker.compose.project") != expected_project
        ):
            raise RuntimeError("Owned monitoring project mismatch")
    elif labels.get("marketlab.r8.owner") != owner:
        raise RuntimeError("Owned container label mismatch")
    if actual["HostConfig"].get("PortBindings") != saved["HostConfig"].get("PortBindings"):
        raise RuntimeError("Owned port bindings changed")
    if actual.get("Mounts") != saved.get("Mounts"):
        raise RuntimeError("Owned storage mounts changed")
    return actual


def port_free(port):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def dump(evidence, prefix, legacy=False):
    profile = resource_profile("legacy") if legacy else PROFILE
    base = profile.base
    saved = one(read(base / "owned-postgres.json"))
    actual = owned_container(saved, inspect(saved["Id"]), profile.owner)
    private = read(base / "connection-private.json")
    url = sa.engine.make_url(private["database_url"])
    if private["owner"] != profile.owner or (url.host, url.port, url.database) != (
        "127.0.0.1",
        profile.postgres_port,
        "marketlab",
    ):
        raise RuntimeError("Owned dump connection identity mismatch")
    expected_binding = [{"HostIp": "127.0.0.1", "HostPort": str(profile.postgres_port)}]
    if actual["HostConfig"].get("PortBindings", {}).get("5432/tcp") != expected_binding:
        raise RuntimeError("Owned dump PostgreSQL loopback binding mismatch")
    started_here = not actual["State"]["Running"]
    if started_here and not legacy:
        raise RuntimeError("Fresh owned database must already be running")
    output = BASE / (prefix + "-database.dump")
    evidence.data["dump"] = {
        "scope": profile.name,
        "container_id": saved["Id"],
        "path": str(output),
        "started_owned_for_dump": started_here,
    }
    evidence.flush()
    try:
        if started_here:
            port_free(profile.postgres_port)
            docker("start", saved["Id"])
        deadline = time.monotonic() + 30
        while True:
            status = subprocess.run(
                ["docker", "exec", saved["Id"], "pg_isready", "-U", "marketlab"],
                capture_output=True,
                timeout=5,
            )
            if status.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Owned PostgreSQL did not become ready for dump")
            time.sleep(0.25)
        owned_container(saved, inspect(saved["Id"]), profile.owner)
        with output.open("xb") as stream:
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-e",
                    "PGPASSWORD",
                    saved["Id"],
                    "pg_dump",
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                    "--username",
                    url.username,
                    "--dbname",
                    url.database,
                ],
                env={**os.environ, "PGPASSWORD": url.password or ""},
                stdout=stream,
                stderr=subprocess.PIPE,
                timeout=180,
            )
        if result.returncode:
            (BASE / (prefix + "-dump-error.log")).write_bytes(result.stderr)
            raise RuntimeError("Owned database dump failed; retained stderr")
        if not output.stat().st_size:
            raise RuntimeError("Empty database dump")
        with output.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        evidence.data["dump"].update(bytes=output.stat().st_size, sha256=digest)
    finally:
        if started_here:
            current = owned_container(saved, inspect(saved["Id"]), profile.owner)
            if current["State"]["Running"]:
                docker("stop", "--time", "10", saved["Id"])
            evidence.data["dump"]["restored_owned_stopped_state"] = not inspect(saved["Id"])[
                "State"
            ]["Running"]
            evidence.flush()


def restore(evidence, prefix):
    from datetime import date, datetime

    from r5_acceptance import restore as datasets

    settings = owned_settings()
    engine = sa.create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
    snapshot_path = ROOT / "artifacts/r6/r6-ordered-catalog-final.json"
    snapshot = read(snapshot_path)["tables"]
    selected = {row["run_id"] for row in snapshot["research_results"]}
    submissions = {
        row["submission_id"] for row in snapshot["research_runs"] if row["run_id"] in selected
    }
    counts = {}
    try:
        counts["dataset_versions"] = len(datasets(engine))
        for name in ("research_results", "memo_results"):
            for row in snapshot[name]:
                if row["run_id"] not in selected:
                    continue
                path = (settings.storage_path / row["manifest_path"]).resolve()
                if not path.is_relative_to(settings.storage_path.resolve()):
                    raise RuntimeError("Retained path escaped storage")
                if hashlib.sha256(path.read_bytes()).hexdigest() != row["manifest_sha256"]:
                    raise AssertionError("Retained manifest corrupt")
                files = (
                    (("results.json", "results_sha256"), ("summary.json", "summary_sha256"))
                    if name == "research_results"
                    else ((f"research_memo_{row['run_id']}.md", "memo_sha256"),)
                )
                for filename, field in files:
                    if (
                        hashlib.sha256((path.parent / filename).read_bytes()).hexdigest()
                        != row[field]
                    ):
                        raise AssertionError("Retained immutable artifact corrupt")
        for name in (
            "research_submissions",
            "research_runs",
            "research_attempts",
            "research_results",
            "memo_jobs",
            "memo_attempts",
            "memo_results",
        ):
            table = sa.Table(name, sa.MetaData(), autoload_with=engine)
            rows = [
                dict(row)
                for row in snapshot[name]
                if (
                    row.get("run_id") in selected
                    if name != "research_submissions"
                    else row["submission_id"] in submissions
                )
            ]
            with engine.begin() as connection:
                for row in rows:
                    for column in table.columns:
                        if row.get(column.name) is not None and isinstance(
                            column.type, sa.DateTime
                        ):
                            row[column.name] = datetime.fromisoformat(row[column.name])
                        elif row.get(column.name) is not None and isinstance(column.type, sa.Date):
                            row[column.name] = date.fromisoformat(row[column.name])
                    predicates = [
                        table.c[column.name] == row[column.name] for column in table.primary_key
                    ]
                    if connection.execute(sa.select(table).where(*predicates)).first() is None:
                        connection.execute(table.insert().values(**row))
            counts[name] = len(rows)
        evidence.data.update(
            restored=counts,
            source=str(snapshot_path),
            source_sha256=hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
        )
    finally:
        engine.dispose()


def dump_verified(profile):
    expected_id = one(read(profile.base / "owned-postgres.json"))["Id"]
    for path in BASE.glob("r8-*-dump.json"):
        receipt = read(path)
        item = receipt.get("dump", {})
        if (
            receipt.get("status") != "passed"
            or item.get("scope") != profile.name
            or item.get("container_id") != expected_id
        ):
            continue
        output = Path(item["path"])
        if not output.resolve().is_relative_to(BASE.resolve()) or not output.is_file():
            continue
        with output.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() == item.get("sha256"):
                return str(path)
    raise RuntimeError("A verified full owned database dump is required before cleanup")


def consumers(kind, identity):
    return docker("ps", "--all", "--quiet", "--no-trunc", "--filter", f"{kind}={identity}").split()


def cleanup(evidence, prefix, apply=False):
    if not (BASE / "current-interval-endpoints-before.json").is_file():
        raise RuntimeError("Current interval endpoint baseline required before cleanup")
    originals(evidence, prefix)
    for port in (58009, 59109, 59110, 59111, 59112, 11441, 11443):
        port_free(port)
    scopes = (resource_profile("legacy"), PROFILE)
    planned, volumes, networks = [], {}, {}
    for profile in scopes:
        evidence.data.setdefault("dump_receipts", []).append(dump_verified(profile))
        records = [one(read(profile.base / f"owned-{kind}.json")) for kind in ("postgres", "redis")]
        monitor_record = profile.base / "owned-monitoring.json"
        if monitor_record.exists():
            records.extend(read(monitor_record))
        for saved in records:
            is_monitor = saved["Config"].get("Labels", {}).get("marketlab.owner") == "r8-monitoring"
            actual = owned_container(saved, inspect(saved["Id"]), profile.owner, is_monitor)
            planned.append((saved, actual, profile.owner, is_monitor))
            for mount in actual.get("Mounts", []):
                if mount["Type"] != "volume":
                    continue
                volume = inspect(mount["Name"], "volume")
                if volume["Mountpoint"] != mount["Source"]:
                    raise RuntimeError("Volume mount identity mismatch")
                volumes[volume["Name"]] = volume
            if is_monitor:
                project = actual["Config"]["Labels"]["com.docker.compose.project"]
                for network in actual["NetworkSettings"]["Networks"].values():
                    value = inspect(network["NetworkID"], "network")
                    if value.get("Labels", {}).get("com.docker.compose.project") != project:
                        raise RuntimeError("Monitoring network identity mismatch")
                    networks[value["Id"]] = value
    owned_ids = {row[0]["Id"] for row in planned}
    for name in volumes:
        if set(consumers("volume", name)) - owned_ids:
            raise RuntimeError("Owned volume has an unowned consumer")
    for network in networks.values():
        if set(network.get("Containers", {})) - owned_ids:
            raise RuntimeError("Owned network has an unowned consumer")
    evidence.data["cleanup"] = {
        "mode": "apply" if apply else "dry-run",
        "container_ids": sorted(owned_ids),
        "volumes": list(volumes),
        "network_ids": list(networks),
        "native_ports_free": True,
        "images": (
            "Shared/base images retained; exclusive image cleanup is a separate root operation"
        ),
    }
    evidence.flush()
    if not apply:
        return
    for saved, _, owner, monitoring in planned:
        actual = owned_container(saved, inspect(saved["Id"]), owner, monitoring)
        if actual["State"]["Running"]:
            docker("stop", "--time", "10", saved["Id"])
        docker("rm", saved["Id"])
    for name, expected in volumes.items():
        if inspect(name, "volume") != expected or consumers("volume", name):
            raise RuntimeError("Volume changed before removal")
        docker("volume", "rm", name)
    for identity, expected in networks.items():
        actual = inspect(identity, "network")
        if (
            actual["Name"] != expected["Name"]
            or actual.get("Labels") != expected.get("Labels")
            or actual.get("Containers")
        ):
            raise RuntimeError("Monitoring network changed before removal")
        docker("network", "rm", identity)
    originals(evidence, prefix)
    for profile in scopes:
        for port in (profile.postgres_port, profile.redis_port):
            port_free(port)
    for port in (53000, 59090):
        port_free(port)
    evidence.data["cleanup"]["owned_containers_volumes_networks_removed"] = True
    evidence.data["cleanup"]["scope"] = (
        "Exact old and current R8 containers/storage only; ignored evidence retained"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase",
        choices=(
            "checks",
            "frontend",
            "live",
            "linux",
            "restore",
            "originals",
            "dump",
            "legacy-dump",
            "cleanup",
        ),
    )
    parser.add_argument("--prefix", required=True, type=validate_prefix)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if PROFILE.name != "adoption-20261027":
        parser.error("Select the fixed adoption-20261027 resource profile before invocation")
    if args.apply and args.phase != "cleanup":
        parser.error("--apply is restricted to exact owned cleanup")
    with Invocation(args.prefix, "finish-" + args.phase) as evidence:
        evidence.data["helper_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        if args.phase in ("dump", "legacy-dump"):
            dump(evidence, args.prefix, legacy=args.phase == "legacy-dump")
        elif args.phase == "cleanup":
            cleanup(evidence, args.prefix, args.apply)
        else:
            globals()[args.phase](evidence, args.prefix)


if __name__ == "__main__":
    main()
