"""Finite Phase 4 actual-browser acceptance with one owned Windows Job."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from v2_phase4_lifecycle import OwnedJob, supervisor_peak_commit
from v2_phase4_service import load_config, require_ready

ROOT = Path(__file__).resolve().parents[1]
EARLIER = ROOT / "artifacts/v2-phase4-20261030"
OUTPUT = ROOT / "artifacts/v2-phase4-completion-20261031"
CEILING = 8 * 1024**3
SAMPLE_SECONDS = 5.0
RUN_SECONDS = 7200


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path: Path, body: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(body, indent=2, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


def sources() -> dict[str, str]:
    paths = [
        ROOT / name
        for name in json.loads(
            (EARLIER / "runtime-reviewed-freeze-04-cli-inventory.json").read_text()
        )["files"]
    ]
    paths.extend((ROOT / "scripts").glob("v2_phase4_*.py"))
    paths.append(ROOT / "scripts/v2_phase4_browser.mjs")
    return {path.relative_to(ROOT).as_posix(): sha(path) for path in sorted(set(paths))}


def owned_services() -> list[dict[str, Any]]:
    expected = json.loads((EARLIER / "owned-resources.json").read_text())
    actual = json.loads(
        subprocess.check_output(
            ["docker", "inspect", *[row["Id"] for row in expected]], text=True, timeout=20
        )
    )
    if len(actual) != len(expected) or len(actual) != 2:
        raise ValueError("Expected exactly the owned PostgreSQL and Redis containers")
    for old, now in zip(expected, actual, strict=True):
        if (
            any(old[key] != now[key] for key in ("Id", "Name", "Image", "Mounts"))
            or now["Config"]["Labels"] != old["Labels"]
            or now["NetworkSettings"]["Ports"] != old["Ports"]
            or not now["State"]["Running"]
        ):
            raise ValueError("Owned service identity/configuration changed")
    return [
        {
            "id": row["Id"],
            "name": row["Name"],
            "image": row["Image"],
            "started_at": row["State"]["StartedAt"],
        }
        for row in actual
    ]


def memory_bytes(text: str) -> int:
    value = text.split("/")[0].strip()
    units = {
        "B": 1,
        "kB": 1000,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "KiB": 1024,
        "MiB": 1024**2,
        "GiB": 1024**3,
    }
    for unit in sorted(units, key=len, reverse=True):
        if value.endswith(unit):
            result = int(float(value[: -len(unit)].strip()) * units[unit])
            if result <= 0:
                raise ValueError("Required service memory is not positive")
            return result
    raise ValueError("Unknown Docker memory unit")


def service_sample(services: list[dict[str, Any]]) -> dict[str, Any]:
    output = subprocess.check_output(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
            *[row["id"] for row in services],
        ],
        text=True,
        timeout=20,
    )
    rows = [json.loads(line) for line in output.splitlines() if line.strip()]
    values = {}
    for service in services:
        matching = [row for row in rows if service["id"].startswith(row["ID"])]
        if len(matching) != 1:
            raise ValueError("Required service memory sample missing or ambiguous")
        values[service["id"]] = memory_bytes(matching[0]["MemUsage"])
    return {"utc": datetime.now(UTC).isoformat(), "monotonic": time.monotonic(), "bytes": values}


def make_boundary(folder: Path, source: dict[str, Any]) -> dict[str, Any]:
    """Source-derived transport fixture only; never normalized or published."""
    inputs = folder / "inputs"
    inputs.mkdir()
    exact, over = inputs / "transport-4gib.csv", inputs / "transport-overlimit.csv"
    with Path(source["file_path"]).open("rb") as stream:
        chunk = stream.read(1024**2)
    if not chunk:
        raise ValueError("Verified source prefix is empty")
    hasher = hashlib.sha256()
    remaining = 4 * 1024**3
    with exact.open("xb") as stream:
        while remaining:
            part = chunk[:remaining]
            stream.write(part)
            hasher.update(part)
            remaining -= len(part)
        stream.flush()
        os.fsync(stream.fileno())
    # The client rejects this file on length before hashing or upload.
    with over.open("xb") as stream:
        stream.truncate(4 * 1024**3 + 1)
    metadata = dict(
        source["metadata"],
        source_sha256=hasher.hexdigest(),
        source_name="retained-source-transport-boundary-fixture",
        source_reference=(
            "Repeated verified SOL CSV prefix; transport fixture only; not normalized/published"
        ),
    )
    value = {
        "file_path": str(exact),
        "over_file_path": str(over),
        "sha256": hasher.hexdigest(),
        "metadata": metadata,
        "bytes": exact.stat().st_size,
        "derivation": {
            "source_sha256": source["sha256"],
            "prefix_sha256": hashlib.sha256(chunk).hexdigest(),
            "prefix_bytes": len(chunk),
        },
        "canonical_validity_claimed": False,
        "normalized_or_published": False,
    }
    if sha(exact) != value["sha256"]:
        raise ValueError("Independent boundary fixture file hash differs")
    write(inputs / "fixture.json", value)
    return value


def prepare(args: Any) -> dict[str, Any]:
    folder = args.output.resolve()
    if folder.parent != OUTPUT.resolve() or folder.exists():
        raise ValueError(
            "Use a fresh invocation immediately inside the completion artifacts directory"
        )
    for parent in (folder.parent, *folder.parent.parents):
        if parent.is_symlink() or parent.is_junction():
            raise ValueError("Output path contains an unsafe link")
    cfg = load_config(args.config.resolve())
    require_ready(cfg)
    frozen = json.loads((EARLIER / "runtime-reviewed-freeze-04-cli-inventory.json").read_text())
    changes = {
        name: {"before": expected, "after": sha(ROOT / name)}
        for name, expected in frozen["files"].items()
        if sha(ROOT / name) != expected
    }
    if changes and (
        set(changes) != {"frontend/vite.config.ts"}
        or changes["frontend/vite.config.ts"]["after"] != args.vite_sha256
    ):
        raise ValueError(
            "Only the explicitly pinned Vite timeout correction may differ from source04"
        )
    services = owned_services()
    for port in (55175, 55176):
        with socket.socket() as connection:
            connection.bind(("127.0.0.1", port))
    original = json.loads(args.campaign.read_text())
    for source in original["canonical"]:
        path = Path(source["file_path"])
        if path.stat().st_size != source["bytes"] or sha(path) != source["sha256"]:
            raise ValueError("Retained canonical input differs")
    plan = dict(original, mode=args.mode)
    plan["official_by_engine"] = {
        engine: {
            "instrument_ids": ["binance:spot:SOLUSDT"],
            "from_date": "2025-03-01",
            "before_date": "2025-03-02",
            "children": 1,
        }
        for engine in original["engines"]
    }
    if args.mode == "boundary":
        plan["engines"] = ["chromium"]
    folder.mkdir(parents=True)
    if args.mode == "boundary":
        plan["boundary"] = make_boundary(folder, original["canonical"][0])
    python = Path(sys.executable).resolve()
    node = shutil.which("node")
    if node is None:
        raise ValueError("Installed locked frontend runtime is unavailable")
    browser_cache = args.browser_cache.resolve()
    if not browser_cache.is_dir():
        raise ValueError("Explicit installed browser cache is unavailable")
    record = {
        "schema": "phase4-completion-plan-v1",
        "mode": args.mode,
        "started_utc": datetime.now(UTC).isoformat(),
        "sources": sources(),
        "source04_reuse": {
            "unchanged_files": len(frozen["files"]) - len(changes),
            "forward_changes": changes,
            "classification": (
                "Vite incoming-request timeout only; affected frontend/boundary checks required"
            )
            if changes
            else "Exact source04 application reuse",
        },
        "original_campaign_sha256": sha(args.campaign),
        "private_config_sha256": sha(args.config),
        "services": services,
        "python": str(python),
        "node": node,
        "browser_cache": str(browser_cache),
        "service_sample_seconds": SAMPLE_SECONDS,
        "deadline_seconds": RUN_SECONDS,
        "shutdown_seconds": 60,
        "resource_ceiling_bytes": CEILING,
        "resource_metric": (
            "Owned Job peak committed bytes + bootstrap peak committed bytes + sum of each named "
            "service sampled maximum; non-simultaneous mixed envelope, not RSS/whole-host peak"
        ),
        "source_input_paths": {
            "campaign": str(args.campaign.resolve()),
            "config": str(args.config.resolve()),
        },
    }
    write(folder / "plan.json", plan)
    record["plan_sha256"] = sha(folder / "plan.json")
    write(folder / "execution.json", record)
    return record


def wait_ready(process: subprocess.Popen[Any], ready: Path, url: str | None = None) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Owned service exited before readiness")
        if ready.exists():
            if url is None:
                return
            try:
                with urllib.request.urlopen(url, timeout=3) as response:
                    if response.status == 200:
                        return
            except OSError:
                pass
        time.sleep(0.2)
    raise TimeoutError("Owned service readiness deadline exceeded")


def inside(args: Any) -> int:
    folder = args.output.resolve()
    execution = json.loads((folder / "execution.json").read_text())
    env = dict(
        os.environ,
        MARKETLAB_PHASE4_TEST="1",
        PYTHONPATH=str(ROOT / "src"),
        MARKETLAB_PHASE4_PYTHON=execution["python"],
        PLAYWRIGHT_BROWSERS_PATH=execution["browser_cache"],
    )
    nonce = env["MARKETLAB_PHASE4_RUN_NONCE"]
    processes: list[tuple[str, subprocess.Popen[Any], Any]] = []
    samples, sample_errors = [], []
    finished = threading.Event()
    result: dict[str, Any] = {"functional": "incomplete", "lifecycle": "incomplete"}

    def collect() -> None:
        while not finished.is_set():
            began = time.monotonic()
            try:
                samples.append(service_sample(execution["services"]))
            except Exception as error:
                sample_errors.append(
                    {"utc": datetime.now(UTC).isoformat(), "error_type": type(error).__name__}
                )
            if finished.wait(max(0, SAMPLE_SECONDS - (time.monotonic() - began))):
                return

    # Complete baseline before starting any application work.
    samples.append(service_sample(execution["services"]))
    sampler = threading.Thread(target=collect)
    sampler.start()

    def launch(role: str, argv: list[str]) -> subprocess.Popen[Any]:
        output = (folder / f"{role}.log").open("xb")
        try:
            process = subprocess.Popen(
                argv,
                cwd=ROOT,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=output,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except BaseException:
            output.close()
            raise
        processes.append((role, process, output))
        return process

    try:
        api = launch(
            "api",
            [
                execution["python"],
                str(ROOT / "scripts/v2_phase4_service.py"),
                "api",
                "--config",
                str(args.config.resolve()),
                "--folder",
                str(folder / "api"),
            ],
        )
        wait_ready(api, folder / "api/ready.json", "http://127.0.0.1:55176/health/ready")
        ui = launch(
            "ui",
            [
                execution["node"],
                str(ROOT / "scripts/v2_phase4_browser.mjs"),
                "ui",
                str(folder / "plan.json"),
                str(folder),
                str(args.config.resolve()),
            ],
        )
        wait_ready(ui, folder / "ui-ready.json")
        controller = launch(
            "controller",
            [
                execution["node"],
                str(ROOT / "scripts/v2_phase4_browser.mjs"),
                "browser",
                str(folder / "plan.json"),
                str(folder),
                str(args.config.resolve()),
            ],
        )
        code = controller.wait(timeout=RUN_SECONDS - 120)
        browser = json.loads((folder / "browser.json").read_text())
        result["functional"] = "passed" if code == 0 and browser["status"] == "passed" else "failed"
    except BaseException as error:
        result.update(functional="failed", error_type=type(error).__name__)
    finally:
        cleanup_errors = []
        for path in (
            folder / "controller-stop.json",
            folder / "ui-stop.json",
            folder / "api/stop.json",
        ):
            try:
                if path.parent.exists():
                    write(path, {"nonce": nonce})
            except OSError as error:
                cleanup_errors.append(type(error).__name__)
        exits = []
        for role, process, output in reversed(processes):
            try:
                exits.append(
                    {"role": role, "pid": process.pid, "exit_code": process.wait(timeout=60)}
                )
            except subprocess.TimeoutExpired:
                cleanup_errors.append(f"{role} did not stop cooperatively")
            finally:
                output.close()
        finished.set()
        sampler.join(timeout=25)
        if sampler.is_alive():
            cleanup_errors.append("Service sampler failed to join")
        try:
            samples.append(service_sample(execution["services"]))
        except Exception as error:
            sample_errors.append({"error_type": type(error).__name__})
        result.update(
            lifecycle="passed"
            if not cleanup_errors
            and all(
                row["exit_code"] in ({0, 1} if row["role"] == "controller" else {0})
                for row in exits
            )
            else "failed",
            exits=exits,
            cleanup_errors=cleanup_errors,
            service_samples=samples,
            service_sample_errors=sample_errors,
        )
        write(folder / "inside.json", result)
    return 0 if result["functional"] == result["lifecycle"] == "passed" else 1


def bootstrap(args: Any) -> int:
    execution = prepare(args)
    folder = args.output.resolve()
    env = dict(
        os.environ, MARKETLAB_PHASE4_RUN_NONCE=secrets.token_hex(24), PYTHONPATH=str(ROOT / "src")
    )
    job = OwnedJob()
    receipt: dict[str, Any] = {
        "schema": "phase4-completion-result-v1",
        "mode": args.mode,
        "functional": "incomplete",
        "lifecycle": "incomplete",
        "resource": "incomplete",
        "execution_sha256": sha(folder / "execution.json"),
        "forced_cleanup": False,
    }
    try:
        with (folder / "runner.log").open("xb") as output:
            child = job.spawn(
                [
                    execution["python"],
                    str(Path(__file__).resolve()),
                    args.mode,
                    "--inside",
                    "--config",
                    str(args.config.resolve()),
                    "--campaign",
                    str(args.campaign.resolve()),
                    "--output",
                    str(folder),
                    "--browser-cache",
                    execution["browser_cache"],
                ],
                cwd=ROOT,
                env=env,
                output=output,
            )
            receipt["runner"] = child.record()
            receipt["initial_job_active"] = job.active()
            try:
                child.wait(RUN_SECONDS)
                job.wait_empty(60)
            except (subprocess.TimeoutExpired, TimeoutError):
                write(folder / "controller-stop.json", {"nonce": env["MARKETLAB_PHASE4_RUN_NONCE"]})
                receipt["forced_cleanup"] = True
                job.terminate()
            receipt["runner"] = child.record()
        peak = job.peak_commit()
        receipt["final_job_active"] = job.active()
        receipt["job_peak_committed_bytes"] = peak
        receipt["bootstrap_peak_committed_bytes"] = supervisor_peak_commit()
        if (folder / "inside.json").exists():
            inner = json.loads((folder / "inside.json").read_text())
            receipt["functional"] = inner["functional"]
            receipt["lifecycle"] = inner["lifecycle"]
            maxima = {
                service["id"]: max(
                    sample["bytes"][service["id"]] for sample in inner["service_samples"]
                )
                for service in execution["services"]
            }
            envelope = peak + receipt["bootstrap_peak_committed_bytes"] + sum(maxima.values())
            receipt.update(
                service_sampled_maxima=maxima,
                resource_envelope_bytes=envelope,
                resource_metric=execution["resource_metric"],
            )
            receipt["resource"] = (
                "passed"
                if (
                    peak > 0
                    and not inner["service_sample_errors"]
                    and envelope < CEILING
                    and owned_services() == execution["services"]
                )
                else "failed"
            )
        if (
            receipt["forced_cleanup"]
            or receipt["runner"]["exit_code"] not in {0, 1}
            or job.active() != 0
        ):
            receipt["lifecycle"] = "failed"
        receipt["source_unchanged"] = sources() == execution["sources"]
        receipt["state"] = (
            "passed"
            if (
                all(receipt[key] == "passed" for key in ("functional", "lifecycle", "resource"))
                and receipt["source_unchanged"]
            )
            else "failed"
        )
    except BaseException as error:
        receipt.update(state="failed", error_type=type(error).__name__)
        raise
    finally:
        try:
            if job.active():
                receipt["forced_cleanup"] = True
                job.terminate()
            receipt.setdefault("job_peak_committed_bytes", job.peak_commit())
            receipt["final_job_active"] = job.active()
        finally:
            try:
                job.close()
                receipt["owned_handles_closed"] = True
            except BaseException as error:
                receipt.update(
                    state="failed",
                    lifecycle="failed",
                    owned_handles_closed=False,
                    handle_close_error=type(error).__name__,
                )
                raise
            finally:
                receipt["finished_utc"] = datetime.now(UTC).isoformat()
                write(folder / "receipt.json", receipt)
    print(
        json.dumps(
            {
                key: receipt.get(key)
                for key in (
                    "state",
                    "mode",
                    "functional",
                    "lifecycle",
                    "resource",
                    "resource_envelope_bytes",
                )
            }
        )
    )
    return 0 if receipt["state"] == "passed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("actual", "boundary", "smoke"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--browser-cache", type=Path, required=True)
    parser.add_argument("--vite-sha256", help="Explicit reviewed Vite timeout correction hash")
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    return inside(args) if args.inside else bootstrap(args)


if __name__ == "__main__":
    raise SystemExit(main())
