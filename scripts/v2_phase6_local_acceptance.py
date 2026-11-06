"""Run retained local numerical gates through the existing Phase 3 evaluator."""

from __future__ import annotations

import _thread
import argparse
import asyncio
import hashlib
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import sqlalchemy as sa
import v2_phase3_acceptance as previous
from v2_phase4_lifecycle import OwnedJob

from marketlab.config import Settings
from marketlab.datasets.v2 import admission, core
from marketlab.datasets.v2.common import canonical_json, sha256_file
from marketlab.storage import recovery

ROOT = Path(__file__).resolve().parents[1]
OWNER = "phase6-implementation"
NONCE = "MARKETLAB_PHASE6_LOCAL_NONCE"
MEMORY = 8 * 1024**3


def write(path: Path, value: Any) -> None:
    path.write_bytes(canonical_json(core.wire(value)))


def sources() -> dict[str, str]:
    paths = sorted((ROOT / "src/marketlab").rglob("*.py"))
    paths += [
        Path(__file__).resolve(),
        ROOT / "scripts/v2_phase3_acceptance.py",
        ROOT / "scripts/v2_phase4_lifecycle.py",
        ROOT / "scripts/r4_reference.py",
        ROOT / "uv.lock",
        ROOT / "artifacts/r4/reference-workflows.json",
    ]
    return {path.relative_to(ROOT).as_posix(): sha256_file(path) for path in paths}


def containers(cfg: dict[str, Any]) -> None:
    postgres = sa.make_url(cfg["database_url"])
    redis = urlsplit(cfg["redis_url"])
    if postgres.host != "127.0.0.1" or redis.hostname != "127.0.0.1":
        raise ValueError("Actual local acceptance requires owned loopback dependencies")
    if cfg["redis_url"] != "redis://127.0.0.1:56392/0":
        raise ValueError("The retained cold gate requires the isolated owned Redis port")
    records = json.loads(
        subprocess.check_output(
            ["docker", "inspect", cfg["postgres_container_id"], cfg["redis_container_id"]],
            text=True,
            timeout=30,
        )
    )
    for record, identity, internal, external in zip(
        records,
        (cfg["postgres_container_id"], cfg["redis_container_id"]),
        ("5432/tcp", "6379/tcp"),
        (postgres.port, redis.port),
        strict=True,
    ):
        if (
            record["Id"] != identity
            or not record["State"]["Running"]
            or record["Config"]["Labels"].get("marketlab.phase6.owner") != OWNER
            or record["NetworkSettings"]["Ports"].get(internal)
            != [{"HostIp": "127.0.0.1", "HostPort": str(external)}]
        ):
            raise ValueError("Actual local dependency ownership or endpoint mismatch")


def model_calls(engine: sa.Engine) -> dict[str, int]:
    result = {}
    with engine.connect() as connection:
        for table in ("copilot_jobs", "memo_jobs", "v2_copilot_jobs", "v2_memo_jobs"):
            result[table] = int(
                core.execute(
                    connection, f"SELECT coalesce(sum(model_calls),0) FROM {table}"
                ).scalar_one()
            )
    return result


def protect_source(backup: dict[str, Any]) -> dict[str, Any]:
    root = admission.safe_root(Path(backup["root_path"]))
    files = {}
    for row in backup["local_files"]:
        path = root / row["relative_path"]
        if path.is_symlink() or path.is_junction() or not path.is_file():
            raise ValueError("Retained source backup file is unavailable")
        if path.stat().st_size != row["file_bytes"] or sha256_file(path) != row["content_sha256"]:
            raise ValueError("Retained source backup bytes changed")
        files[row["relative_path"]] = row["content_sha256"]
    return {"root": str(root), "files": files}


async def actual(cfg: dict[str, Any], folder: Path) -> dict[str, Any]:
    recovery._require_local_settings(Settings())
    containers(cfg)
    reference = ROOT / "artifacts/r4/reference-workflows.json"
    if sha256_file(reference) != cfg["reference_sha256"]:
        raise ValueError("Reviewed numerical reference changed")
    backup_path = Path(cfg["source_backup"])
    if sha256_file(backup_path) != cfg["source_backup_sha256"]:
        raise ValueError("Reviewed local source receipt changed")
    backup = json.loads(await asyncio.to_thread(backup_path.read_bytes))
    root = admission.safe_root(Path(cfg["storage_path"]))
    if root == admission.safe_root(Path(backup["root_path"])):
        raise ValueError("Numerical acceptance must use the copied owned root")
    engine = sa.create_engine(cfg["database_url"])
    try:
        with engine.connect() as connection:
            recovery._require_local_database(connection)
            bound = admission.require(connection, root)
            identity = recovery.database_identity(connection)
        if identity == backup["source_database"]:
            raise ValueError("Numerical acceptance cannot mutate the retained source database")
        initial = sources()
        before_calls = model_calls(engine)
        write(folder / "source-before.json", protect_source(backup))
        write(
            folder / "preflight.json",
            {
                "source_files": initial,
                "source_backup_sha256": cfg["source_backup_sha256"],
                "target_database": identity,
                "target_root_id": str(bound["root_id"]),
                "model_calls": before_calls,
            },
        )
        # Reuse exact existing requests, reference values, native lifecycle
        # assertions and the cold all-62 time bound without changing the evaluator.
        invocation = hashlib.sha256(str(folder).encode()).hexdigest()[:16]
        scenarios, cold = (
            folder / ("scenarios-" + invocation),
            folder / ("cold-all62-" + invocation),
        )
        scenarios.mkdir()
        cold.mkdir()
        results = await previous.legacy(cfg, scenarios, cold=False)
        write(scenarios / "result.json", results)
        cold_result = await previous.legacy(cfg, cold, cold=True)
        write(cold / "result.json", cold_result)
        if model_calls(engine) != before_calls:
            raise AssertionError("Numerical acceptance dispatched model work")
        # Normal source readers have drained before inventory/backup.
        final_backup = recovery.local_backup_inventory(engine, root)
        actual_files = {
            (relative, length, sha) for relative, length, _, sha in admission._files(root)
        }
        expected_files = {
            (row["relative_path"], row["file_bytes"], row["content_sha256"])
            for row in final_backup["local_files"]
        }
        if actual_files != expected_files:
            raise AssertionError("Final local backup inventory is incomplete or changed")
        write(folder / "target-backup-inventory.json", final_backup)
        after = protect_source(backup)
        write(folder / "source-after.json", after)
        if (
            after != json.loads((folder / "source-before.json").read_bytes())
            or sources() != initial
        ):
            raise AssertionError("Source or retained input bytes changed")
        containers(cfg)
        return {
            "functional": "passed",
            "scenarios": results,
            "cold_all62": cold_result,
            "model_calls": before_calls,
            "target_backup_sha256": sha256_file(folder / "target-backup-inventory.json"),
        }
    finally:
        engine.dispose()


def inside(args: argparse.Namespace) -> int:
    folder = args.output.resolve()
    if os.environ.get(NONCE) != args.nonce:
        raise ValueError("Owned runner launch identity mismatch")
    cfg = json.loads(args.config.read_bytes())
    if cfg["owner"] != OWNER:
        raise ValueError("Unexpected actual acceptance owner")
    result: dict[str, Any] = {"functional": "failed", "started_utc": datetime.now(UTC).isoformat()}
    done = threading.Event()

    def stop() -> None:
        while not done.wait(0.2):
            path = folder / "stop.json"
            try:
                requested = path.exists() and json.loads(path.read_bytes()) == {"nonce": args.nonce}
            except (OSError, ValueError):
                requested = False
            if requested:
                _thread.interrupt_main()
                return

    watcher = threading.Thread(target=stop, daemon=True)
    watcher.start()
    try:
        result.update(asyncio.run(actual(cfg, folder)))
        return 0
    except BaseException as error:
        result["error_type"] = type(error).__name__
        raise
    finally:
        done.set()
        watcher.join(5)
        result["ended_utc"] = datetime.now(UTC).isoformat()
        write(folder / "functional-result.json", result)


def bootstrap(args: argparse.Namespace) -> int:
    folder = args.output.resolve()
    if folder.exists():
        raise ValueError("Acceptance evidence directory already exists")
    folder.mkdir(parents=True)
    nonce, job = secrets.token_hex(24), OwnedJob()
    receipt: dict[str, Any] = {
        "functional": "failed",
        "lifecycle": "failed",
        "sampled_resources": "failed",
        "forced_cleanup": False,
        "samples": [],
        "config_sha256": sha256_file(args.config),
        "source_files": sources(),
    }
    start, previous_sample = time.monotonic(), time.monotonic()
    try:
        with (folder / "runner.txt").open("xb") as output:
            child = job.spawn(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--inside",
                    "--config",
                    str(args.config.resolve()),
                    "--output",
                    str(folder),
                    "--nonce",
                    nonce,
                ],
                cwd=ROOT,
                env={**os.environ, NONCE: nonce},
                output=output,
            )
            write(folder / "launch.json", {"nonce": nonce, "root": child.record()})
            while child.poll() is None:
                now = time.monotonic()
                peak = job.peak_commit()
                receipt["samples"].append(
                    {
                        "elapsed_seconds": now - start,
                        "peak_commit_bytes": peak,
                        "active": job.active(),
                    }
                )
                if now - previous_sample > 1 or peak > MEMORY or now - start > 7200:
                    write(folder / "stop.json", {"nonce": nonce})
                    cooperative_deadline = time.monotonic() + 120
                    while child.poll() is None and time.monotonic() < cooperative_deadline:
                        threading.Event().wait(0.5)
                    raise RuntimeError("Actual local runner resource or deadline gate failed")
                previous_sample = now
                threading.Event().wait(0.5)
            job.wait_empty(30)
            receipt["root"] = child.record()
            receipt["lifecycle"] = "passed"
            receipt["sampled_resources"] = "passed"
            if child.poll() == 0:
                receipt["functional"] = "passed"
    finally:
        if job.active():
            receipt["forced_cleanup"] = True
            job.terminate()
        job.close()
        receipt["elapsed_seconds"] = time.monotonic() - start
        write(folder / "result.json", receipt)
    return (
        0
        if all(receipt[key] == "passed" for key in ("functional", "lifecycle", "sampled_resources"))
        else 1
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--nonce", help=argparse.SUPPRESS)
    args = parser.parse_args()
    return inside(args) if args.inside else bootstrap(args)


if __name__ == "__main__":
    raise SystemExit(main())
