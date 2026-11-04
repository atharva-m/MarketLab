"""Own the API and unchanged Phase 5 runner in one native lifecycle group.

No scoring, model transport, retry or fixture logic lives here. The approved
frozen runner remains the sole acceptance runner. This binding only supplies
its required owned loopback API and extends native sampling to that sibling.
"""

from __future__ import annotations

import argparse
import secrets
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import v2_phase5_model_eval as evaluation
from v2_phase4_lifecycle import OwnedJob, supervisor_peak_commit

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "artifacts/v2-phase5-20261102/frontend-eval-design/score-api-program-01.py"
SAMPLE_SECONDS = 0.5
MAXIMUM_GAP = 1.0
COOPERATIVE_SECONDS = 2160
MEMORY_CEILING = 8 * 1024**3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--bound", required=True, type=Path)
    parser.add_argument("--approval", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--suite",
        required=True,
        choices=("copilot", "memo", "clarification", "faults", "grounding"),
    )
    parser.add_argument("--cohort", required=True, choices=("A", "B"))
    args = parser.parse_args()
    approved = evaluation.approval(args.approval, "score", args.bound)
    cfg = evaluation.config(args.config)
    if (
        approved.get("config_sha256") != evaluation.sha(args.config)
        or approved.get("postgres_receipt_sha256") != cfg["_private_sha256"]
        or approved.get("owned_launch_source_sha256") != evaluation.sha(Path(__file__))
        or approved.get("owned_api_source_sha256") != evaluation.sha(API)
    ):
        raise ValueError(
            "One score approval must bind exact owned launch/API source and configuration"
        )
    folder = evaluation.contained(args.output)
    folder.mkdir(parents=True, exist_ok=False)
    api_folder, score_folder = folder / "api", folder / "runner"
    nonce = secrets.token_hex(16)
    env = evaluation.environment(cfg)
    env["MARKETLAB_P5_OWNED_NONCE"] = nonce
    initial_sources = evaluation.sources()
    receipt: dict[str, Any] = {
        "schema": "phase5-owned-score-launch-v1",
        "suite": args.suite,
        "cohort": args.cohort,
        "state": "incomplete",
        "started_utc": datetime.now(UTC).isoformat(),
        "bound_sha256": evaluation.sha(args.bound),
        "approval_sha256": evaluation.sha(args.approval),
        "controller_stop_nonce": nonce,
        "source_files": initial_sources,
        "launch_source_sha256": evaluation.sha(Path(__file__)),
        "api_source_sha256": evaluation.sha(API),
        "functional": "incomplete",
        "lifecycle": "incomplete",
        "owned_sampled_resource": "incomplete",
        "forced_cleanup": False,
        "resource_scope": "API, unchanged runner/supervisor, and every inherited owned descendant",
        "external_service_model_resource": (
            "Separate observations required; Docker/model/GPU use not measured here"
        ),
        "upstream_cancellation": "Not established by API/client shutdown",
        "sample_interval_seconds": SAMPLE_SECONDS,
        "maximum_permitted_gap_seconds": MAXIMUM_GAP,
    }
    evaluation.write(folder / "execution.json", receipt)
    job = OwnedJob()
    api_child: Any = None
    runner_child: Any = None
    log_handles = []
    sampling_done = threading.Event()
    observations: list[float] = []
    sample_errors: list[str] = []
    began = time.monotonic()

    def sample() -> None:
        scheduled = time.monotonic()
        with (folder / "samples.jsonl").open("xb") as output:
            while not sampling_done.is_set():
                actual = time.monotonic()
                try:
                    output.write(
                        evaluation.canonical(
                            {
                                "planned_elapsed": scheduled - began,
                                "actual_elapsed": actual - began,
                                "active": job.active(),
                                "peak_committed_bytes": job.peak_commit(),
                            }
                        )
                    )
                    output.flush()
                    observations.append(actual)
                except BaseException as error:
                    sample_errors.append(type(error).__name__)
                scheduled += SAMPLE_SECONDS
                sampling_done.wait(max(0, scheduled - time.monotonic()))

    def launch(argv: list[str], log_name: str) -> Any:
        log = (folder / log_name).open("xb")
        log_handles.append(log)
        return job.spawn(argv, cwd=ROOT, env=env, output=log)

    def stopped() -> bool:
        marker = folder / "controller-stop.json"
        if not marker.exists():
            return False
        try:
            return bool(evaluation.read(marker) == {"nonce": nonce})
        except (OSError, ValueError):
            return False

    def stop_components() -> None:
        if score_folder.exists() and runner_child is not None and runner_child.poll() is None:
            # Frozen inside watcher uses existence; no persisted job/lease mutation.
            evaluation.write(score_folder / "controller-stop.json", {"nonce": nonce})
        if api_folder.exists() and api_child is not None and api_child.poll() is None:
            evaluation.write(api_folder / "stop.json", {"nonce": nonce})

    sampler = threading.Thread(target=sample, name="phase5-api-runner-owned-sampler")
    try:
        receipt["owned_services_before"] = {
            "postgres": evaluation.verify_container(cfg),
            "redis": evaluation.verify_redis(cfg),
        }
        sampler.start()
        api_child = launch(
            [
                sys.executable,
                "-B",
                str(API),
                "--config",
                str(args.config.resolve()),
                "--folder",
                str(api_folder),
            ],
            "api.log",
        )
        receipt["api_root"] = api_child.record()
        deadline = time.monotonic() + 60
        while not (api_folder / "ready.json").exists():
            if api_child.poll() is not None or time.monotonic() >= deadline or stopped():
                raise RuntimeError("Owned API failed to become ready")
            time.sleep(0.1)
        ready = evaluation.read(api_folder / "ready.json")
        if (
            ready.get("nonce") != nonce
            or ready.get("port") != 58185
            or ready.get("program_sha256") != evaluation.sha(API)
            or ready.get("config_sha256") != evaluation.sha(args.config)
        ):
            raise ValueError("Owned API readiness identity mismatch")
        receipt["api_ready"] = ready  # Reported child PID is not used as termination authority.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:58185/v2/capabilities", timeout=5) as response:
            if response.status != 200:
                raise RuntimeError("Owned API capability read failed")
        runner_child = launch(
            [
                sys.executable,
                "-B",
                str(ROOT / "scripts/v2_phase5_model_eval.py"),
                "score",
                "--bound",
                str(args.bound.resolve()),
                "--config",
                str(args.config.resolve()),
                "--approval",
                str(args.approval.resolve()),
                "--suite",
                args.suite,
                "--cohort",
                args.cohort,
                "--output",
                str(score_folder),
            ],
            "runner.log",
        )
        receipt["runner_root"] = runner_child.record()
        deadline = time.monotonic() + 36000
        while runner_child.poll() is None:
            if stopped() or time.monotonic() >= deadline:
                receipt["cooperative_stop_requested"] = True
                stop_components()
                break
            if api_child.poll() is not None:
                raise RuntimeError("Owned API exited during the invocation")
            time.sleep(0.1)
        runner_child.wait(COOPERATIVE_SECONDS)
        stop_components()
        api_child.wait(COOPERATIVE_SECONDS)
        job.wait_empty(30)
        receipt["api_root"], receipt["runner_root"] = api_child.record(), runner_child.record()
        inner = evaluation.read(score_folder / "result.json", 256 * 1024**2)
        api_outcome = evaluation.read(api_folder / "api-result.json")
        receipt["inner_result_sha256"] = evaluation.sha(score_folder / "result.json")
        receipt["api_result_sha256"] = evaluation.sha(api_folder / "api-result.json")
        receipt["functional"] = (
            "passed" if runner_child.returncode == 0 and inner["state"] == "passed" else "failed"
        )
        receipt["lifecycle"] = (
            "passed"
            if api_child.returncode == 0 and api_outcome["state"] == "passed" and job.active() == 0
            else "failed"
        )
        receipt["owned_services_after"] = {
            "postgres": evaluation.verify_container(cfg),
            "redis": evaluation.verify_redis(cfg),
        }
        if receipt["owned_services_after"] != receipt["owned_services_before"]:
            raise ValueError("Owned service identity changed during invocation")
    except BaseException as error:
        receipt.update(functional="failed", exception_type=type(error).__name__)
        stop_components()
        try:
            if runner_child is not None:
                runner_child.wait(COOPERATIVE_SECONDS)
            if api_child is not None:
                api_child.wait(COOPERATIVE_SECONDS)
            job.wait_empty(30)
        except (subprocess.TimeoutExpired, TimeoutError):
            receipt["forced_cleanup"] = True
            job.terminate()
        receipt["lifecycle"] = "failed"
    finally:
        if job.active():
            receipt["forced_cleanup"] = True
            job.terminate()
        receipt["final_active"] = job.active()
        receipt["owned_peak_committed_bytes"] = job.peak_commit()
        receipt["supervisor_peak_committed_bytes"] = supervisor_peak_commit()
        time.sleep(SAMPLE_SECONDS)
        sampling_done.set()
        if sampler.ident is not None:
            sampler.join(5)
        receipt["sample_count"], receipt["sample_errors"] = len(observations), sample_errors
        receipt["maximum_observed_gap_seconds"] = max(
            (b - a for a, b in zip(observations, observations[1:], strict=False)), default=0
        )
        receipt["owned_sampled_resource"] = (
            "passed"
            if len(observations) >= 2
            and not sample_errors
            and not sampler.is_alive()
            and receipt["maximum_observed_gap_seconds"] <= MAXIMUM_GAP
            and 0
            < receipt["owned_peak_committed_bytes"] + receipt["supervisor_peak_committed_bytes"]
            < MEMORY_CEILING
            else "failed"
        )
        receipt["frozen_source_unchanged"] = evaluation.sources() == initial_sources
        receipt["ownership_sources_unchanged"] = (
            evaluation.sha(Path(__file__)) == receipt["launch_source_sha256"]
            and evaluation.sha(API) == receipt["api_source_sha256"]
        )
        receipt["source_unchanged"] = (
            receipt["frozen_source_unchanged"] and receipt["ownership_sources_unchanged"]
        )
        try:
            job.close()
            receipt["owned_handles_closed"] = True
        except BaseException as error:
            receipt.update(
                owned_handles_closed=False,
                lifecycle="failed",
                handle_close_exception_type=type(error).__name__,
            )
        for log in log_handles:
            log.close()
        receipt["ended_utc"], receipt["elapsed_seconds"] = (
            datetime.now(UTC).isoformat(),
            time.monotonic() - began,
        )
        receipt["state"] = (
            "passed"
            if receipt["source_unchanged"]
            and not receipt["forced_cleanup"]
            and all(
                receipt[k] == "passed"
                for k in ("functional", "lifecycle", "owned_sampled_resource")
            )
            else "failed"
        )
        evaluation.write(folder / "result.json", receipt)
    return 0 if receipt["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
