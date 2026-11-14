"""Bounded Phase 7 orchestration over reviewed, operator-installed SSH adapters.

No adapters are installed or services launched by this script. The default plan
operation is offline. Execution requires an explicit frozen configuration and
``--execute``; observations are retained for independent review, not acceptance
credit by assertion. See docs/v2/phase-7-operations.md for the adapter protocol.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
HASH = re.compile(r"[0-9a-f]{64}")
TARGET = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.@-]{0,252}")
BOUNDARIES = (
    "after_claim",
    "before_model_reservation",
    "after_model_reservation",
    "during_output_upload",
    "verified_before_commit",
    "committed_before_response",
    "competing_claims",
    "worker_death",
    "lease_expiry",
    "database_partition",
    "storage_partition",
    "stale_success",
    "cancellation_publication",
)
STAGES = ("functional", "faults", "inference", "visibility")
MAX_RESPONSE = 64 * 1024
VISIBILITY_FAILURE_PHASES = {
    "compatibility_registration_missing",
    "compatibility_guard_accepted",
    "compatibility_worker_deadline",
    "compatibility_worker_failed",
}


class VisibilityProbeError(ValueError):
    def __init__(self, phase: str) -> None:
        super().__init__("Visibility probe incomplete")
        self.phase = phase


def canonical(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def read_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("Configuration or receipt must be a bounded regular file")
    return json.loads(path.read_bytes())


def identities() -> dict[str, str]:
    files = sorted((ROOT / "src/marketlab").rglob("*.py"))
    inventory = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
    }
    lock_sha = hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest()
    inventory["uv.lock"] = lock_sha
    helpers = [
        Path(__file__).resolve(),
        ROOT / "scripts/v2_phase7_faults.py",
        ROOT / "tests/s3/guarded_python.py",
        ROOT / "scripts/v2_phase4_lifecycle.py",
    ]
    helper_inventory = {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in helpers
        if path.is_file()
    }
    return {
        "source_sha256": hashlib.sha256(canonical(inventory)).hexdigest(),
        "lock_sha256": lock_sha,
        "runner_sha256": hashlib.sha256(canonical(helper_inventory)).hexdigest(),
    }


def validate_config(cfg: Any) -> None:
    if not isinstance(cfg, dict) or cfg.get("schema") != "phase7-acceptance-v1":
        raise ValueError("Frozen Phase 7 configuration required")
    if set(cfg) != {
        "schema",
        "source_sha256",
        "lock_sha256",
        "runner_sha256",
        "namespace_sha256",
        "inventory_sha256",
        "backup_sha256",
        "hosts",
        "cases",
    }:
        raise ValueError("Only allowlisted nonsecret campaign configuration is accepted")
    for key in (
        "source_sha256",
        "lock_sha256",
        "namespace_sha256",
        "inventory_sha256",
        "backup_sha256",
        "runner_sha256",
    ):
        if not isinstance(cfg.get(key), str) or not HASH.fullmatch(cfg[key]):
            raise ValueError("Frozen identity hashes required")
    hosts = cfg.get("hosts")
    if not isinstance(hosts, list) or len(hosts) != 2:
        raise ValueError("Two actual independently provisioned hosts required")
    for host in hosts:
        if set(host) != {
            "host_id",
            "actual_host",
            "container",
            "ssh_target",
            "machine_identity_sha256",
            "adapter_config_sha256",
        }:
            raise ValueError("Only allowlisted nonsecret host fields are accepted")
        UUID(host["host_id"])
        if (
            host.get("actual_host") is not True
            or host.get("container") is not False
            or not TARGET.fullmatch(host.get("ssh_target", ""))
            or host["ssh_target"].split("@")[-1] in {"localhost", "127.0.0.1", "::1"}
            or not HASH.fullmatch(host.get("machine_identity_sha256", ""))
            or not HASH.fullmatch(host.get("adapter_config_sha256", ""))
        ):
            raise ValueError("Reviewed actual-host transport and physical identity required")
    for key in ("host_id", "machine_identity_sha256", "ssh_target"):
        if hosts[0][key] == hosts[1][key]:
            raise ValueError("Two containers or aliases on one host are insufficient")
    cases = cfg.get("cases")
    if not isinstance(cases, list) or len(cases) != 24:
        raise ValueError("Exactly twenty numerical and four functional cases required")
    expected_kinds = ["research"] * 20 + [
        "official_ingestion",
        "canonical_ingestion",
        "copilot",
        "memo",
    ]
    for case, kind in zip(cases, expected_kinds, strict=True):
        if set(case) != {"kind", "input_sha256", "expected_sha256"}:
            raise ValueError("Only frozen input/output hashes are accepted")
        if (
            case.get("kind") != kind
            or not HASH.fullmatch(case.get("input_sha256", ""))
            or not HASH.fullmatch(case.get("expected_sha256", ""))
        ):
            raise ValueError("Frozen independent inputs and expected outputs required")
    if len({case["input_sha256"] for case in cases[:20]}) != 20:
        raise ValueError("Twenty independent numerical inputs required")


def plan(cfg: dict[str, Any], stage: str) -> list[dict[str, Any]]:
    validate_config(cfg)
    if stage == "functional":
        return [
            {"action": "functional", "case": case, "host_index": i % 2}
            for i, case in enumerate(cfg["cases"])
        ]
    if stage == "faults":
        return [
            {
                "action": "fault",
                "boundary": boundary,
                "repetition": repetition,
                "host_index": repetition % 2,
            }
            for boundary in BOUNDARIES
            for repetition in range(3)
        ]
    if stage == "inference":
        return [
            {"action": "inference", "scenario": scenario, "host_index": i % 2}
            for i, scenario in enumerate(
                (
                    "cross_host_contention",
                    "copilot_priority",
                    "zero_wait_budget",
                    "session_loss",
                    "nonrefundable_reservation",
                    "pinned_model_copilot",
                    "pinned_model_memo",
                    "upstream_continuation",
                )
            )
        ]
    if stage == "visibility":
        return [
            {"action": "visibility", "scenario": scenario, "host_index": i % 2}
            for i, scenario in enumerate(
                (
                    "normal_cli",
                    "drain_restart_freshness",
                    "incompatible_capability",
                    "missing_source_lock",
                    "bounded_metrics",
                    "operator_pagination",
                )
            )
        ]
    raise ValueError("Unknown acceptance stage")


def dispatch_cost(task: dict[str, Any]) -> int:
    if task["action"] == "fault":
        return 2
    if task["action"] == "inference":
        return (
            1
            if task.get("scenario")
            in {"zero_wait_budget", "pinned_model_copilot", "pinned_model_memo"}
            else 2
        )
    if task["action"] == "visibility":
        return {
            "drain_restart_freshness": 2,
            "incompatible_capability": 1,
            "missing_source_lock": 1,
        }.get(task.get("scenario"), 0)
    return 1


SSH_ALIAS = re.compile(r"[a-z0-9_][a-z0-9_.-]{0,252}")
SSH_PATH = re.compile(r"[A-Za-z0-9_./:\\-]+")
SSH_FIXED = {
    "batchmode": "yes",
    "stricthostkeychecking": "yes",
    "identitiesonly": "yes",
    "identityagent": "none",
    "globalknownhostsfile": "none",
    "forwardagent": "no",
    "updatehostkeys": "no",
    "requesttty": "no",
    "hostkeyalgorithms": "ssh-ed25519",
}
SSH_REQUIRED = {
    *SSH_FIXED,
    "hostname",
    "port",
    "user",
    "identityfile",
    "userknownhostsfile",
    "hostkeyalias",
}


def private_ssh_config(target: str) -> list[str]:
    """Opt in to an exact campaign config without executing SSH config commands."""
    raw_path = os.environ.get("MARKETLAB_PHASE7_SSH_CONFIG")
    expected = os.environ.get("MARKETLAB_PHASE7_SSH_CONFIG_SHA256")
    if raw_path is None and expected is None:
        return []
    if not raw_path or not expected or not HASH.fullmatch(expected):
        raise ValueError("Private SSH config and hash must be supplied together")
    path = Path(raw_path)
    if not SSH_PATH.fullmatch(raw_path) or not path.is_absolute() or ".." in path.parts:
        raise ValueError("Private SSH config needs an absolute, literal path")
    for item in (path, *path.parents):
        info = item.lstat()
        expected_mode = stat.S_ISREG if item == path else stat.S_ISDIR
        if (
            not expected_mode(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise ValueError("Private SSH config must be a regular file under plain directories")
    with path.open("rb") as stream:
        content = stream.read(16385)
    if len(content) > 16384 or hashlib.sha256(content).hexdigest() != expected:
        raise ValueError("Private SSH config changed or exceeds the size bound")
    normalized = content.replace(b"\r\n", b"\n")
    if any(byte not in (9, 10) and not 32 <= byte < 127 for byte in normalized):
        raise ValueError("Private SSH config requires printable ASCII settings")

    blocks: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in normalized.decode("ascii").split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 2:
            raise ValueError("Private SSH config requires simple keyword-value pairs")
        key, value = fields[0].lower(), fields[1]
        if key == "host":
            if not SSH_ALIAS.fullmatch(value) or value in blocks:
                raise ValueError("Private SSH config requires distinct explicit host aliases")
            current = blocks[value] = {}
        elif current is None or key in current or key not in SSH_REQUIRED | {"proxyjump"}:
            raise ValueError("Private SSH config contains an unreviewed or duplicate directive")
        else:
            current[key] = value
    if target not in blocks:
        raise ValueError("Requested SSH alias is absent from the private config")
    for fields in blocks.values():
        if not SSH_REQUIRED <= fields.keys() or any(
            fields[key] != value for key, value in SSH_FIXED.items()
        ):
            raise ValueError(
                "Private SSH config requires explicit key pins and strict connection settings"
            )
        for key in ("hostname", "user", "hostkeyalias"):
            if not SSH_ALIAS.fullmatch(fields[key]):
                raise ValueError("Private SSH config contains an invalid connection value")
        port = fields["port"]
        if not port.isdecimal() or len(port) > 5 or not 1 <= int(port) <= 65535:
            raise ValueError("Private SSH config contains an invalid port")
        for key in ("identityfile", "userknownhostsfile"):
            value = fields[key]
            path_value = Path(value)
            if (
                not SSH_PATH.fullmatch(value)
                or not path_value.is_absolute()
                or ".." in path_value.parts
            ):
                raise ValueError("Private SSH config requires absolute, literal key file paths")
        hop = fields.get("proxyjump")
        if hop is not None and (hop not in blocks or "proxyjump" in blocks[hop]):
            raise ValueError("Private SSH config supports one explicitly pinned jump host")
    return ["-F", str(path)]


def transport(host: dict[str, Any], request: dict[str, Any], timeout: float) -> dict[str, Any]:
    """Fixed remote command, no shell or operator-supplied executable strings."""
    command = [
        "ssh",
        *private_ssh_config(host["ssh_target"]),
        "-oBatchMode=yes",
        "-oConnectTimeout=10",
        "-oStrictHostKeyChecking=yes",
        "--",
        host["ssh_target"],
        "marketlab-v2-phase7-adapter",
    ]
    value = json.loads(bounded_process(command, canonical(request), timeout))
    if not isinstance(value, dict):
        raise ValueError("Invalid adapter response")
    return value


def handshake(cfg: dict[str, Any], host: dict[str, Any], value: dict[str, Any]) -> None:
    for key in ("host_id", "machine_identity_sha256", "adapter_config_sha256"):
        if value.get(key) != host[key]:
            raise ValueError("Observed host identity differs from the frozen host")
    for key in ("source_sha256", "lock_sha256", "runner_sha256", "namespace_sha256"):
        if value.get(key) != cfg[key]:
            raise ValueError("Observed source, lock or shared namespace differs")
    if (
        value.get("mode") != "distributed"
        or value.get("schema_revision") != "0013_v2_workers"
        or value.get("container") is not False
        or value.get("ready") is not True
        or not isinstance(value.get("boot_identity"), str)
        or not value["boot_identity"]
    ):
        raise ValueError("Actual distributed-host prerequisites are incomplete")


def validate_host_scope(config: dict[str, Any], packet: dict[str, Any]) -> None:
    allowed = packet.get("allowed_hosts")
    if not isinstance(allowed, list) or len(allowed) != 2:
        raise ValueError("Frozen two-host transport scope required")
    peers = {row["host_id"]: row for row in allowed}
    if len(peers) != 2 or config["host_id"] not in peers:
        raise ValueError("Adapter host is outside the frozen scope")
    for identifier in peers:
        UUID(identifier)
    if (
        hashlib.sha256(canonical(config)).hexdigest()
        != peers[config["host_id"]]["adapter_config_sha256"]
    ):
        raise ValueError("Reviewed adapter configuration changed")
    for name in ("fault_bindings", "model_bindings"):
        for binding in config.get(name, {}).values():
            peer = binding.get("peer")
            if peer is not None and (
                peer.get("host_id") not in peers
                or peer.get("ssh_target") != peers[peer["host_id"]]["ssh_target"]
            ):
                raise ValueError("Prepared peer transport is outside the frozen two-host scope")


def validate_observation(item: dict[str, Any], value: dict[str, Any], host_ids: set[str]) -> None:
    if item["action"] == "visibility":
        if value.get("host_id") not in host_ids:
            raise ValueError("Visibility observation has the wrong host")
        if item.get("scenario") in {"incompatible_capability", "missing_source_lock"}:
            checks = value.get("checks")
            if (
                value.get("status") != "guard_observed"
                or value.get("jobs_started") != 0
                or not isinstance(checks, list)
                or not checks
                or any(row.get("error_code") != "unavailable" for row in checks)
            ):
                raise ValueError("Actual rejected compatibility observations required")
            return
        if item.get("scenario") == "bounded_metrics":
            samples = value.get("samples")
            from marketlab.monitoring import DETAIL_LABELS, STATES

            if (
                value.get("status") != "visibility_observed"
                or value.get("jobs_started") != 0
                or not isinstance(samples, list)
                or not samples
            ):
                raise ValueError("Actual bounded metric samples required")
            allowed = {
                label for labels in DETAIL_LABELS.values() for values in labels for label in values
            }
            allowed.update(STATES)
            allowed.update(state for states in STATES.values() for state in states)
            if any(
                set(sample["labels"]) - {"kind", "state", "reason"}
                or any(label not in allowed for label in sample["labels"].values())
                for sample in samples
            ):
                raise ValueError("Metrics contain non-allowlisted labels")
            return
        if item.get("scenario") == "drain_restart_freshness":
            instances = value.get("instances")
            if (
                value.get("status") != "visibility_observed"
                or value.get("jobs_started") != 0
                or not isinstance(instances, list)
                or len(instances) != 2
                or len({row["instance_id"] for row in instances}) != 2
                or any(row["state"] != "stopped" for row in instances)
                or value.get("observed_ready") is not True
            ):
                raise ValueError("Two actual fresh CLI instances and normal drain required")
            return
        pages = value.get("pages")
        if (
            value.get("status") != "visibility_observed"
            or value.get("jobs_started") != 0
            or value.get("host_id") not in host_ids
            or not isinstance(pages, list)
            or not 1 <= len(pages) <= 100
            or any(not isinstance(page, dict) or len(page.get("items", [])) > 1 for page in pages)
            or pages[-1].get("next_cursor") is not None
        ):
            raise ValueError("Bounded actual CLI visibility observations required")
        return
    if value.get("status") != "observed" or value.get("host_id") not in host_ids:
        raise ValueError("Scenario lacks actual bounded observations")
    for key in ("jobs_started", "model_calls_before", "model_calls_after"):
        if type(value.get(key)) is not int or value[key] < 0:
            raise ValueError("Scenario accounting is missing")
    if value["model_calls_after"] < value["model_calls_before"]:
        raise ValueError("Spent model calls cannot be reset")
    if item.get("scenario") == "zero_wait_budget":
        if (
            value["jobs_started"] != 0
            or value.get("attempts") != []
            or value["model_calls_before"] != value["model_calls_after"]
            or value.get("attempts_started_while_waiting") != 0
        ):
            raise ValueError("Waiting spent a job attempt or a model call")
        return
    attempts = value.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise ValueError("Retained attempt observations required")
    jobs: dict[str, list[dict[str, Any]]] = {}
    for attempt in attempts:
        UUID(attempt["job_id"])
        UUID(attempt["worker_instance_id"])
        if (
            attempt.get("host_id") not in host_ids
            or type(attempt.get("attempt_number")) is not int
            or not 1 <= attempt["attempt_number"] <= 3
            or type(attempt.get("fencing_token")) is not int
            or attempt["fencing_token"] < 1
            or type(attempt.get("committed")) is not bool
        ):
            raise ValueError("Invalid attempt owner, fencing token or attempt bound")
        jobs.setdefault(attempt["job_id"], []).append(attempt)
    for history in jobs.values():
        history.sort(key=lambda a: a["attempt_number"])
        if (
            len({a["attempt_number"] for a in history}) != len(history)
            or any(
                b["fencing_token"] <= a["fencing_token"]
                for a, b in zip(history, history[1:], strict=False)
            )
            or sum(a["committed"] for a in history) > 1
        ):
            raise ValueError("Duplicate commit or non-increasing recovery fencing")
    if item["action"] == "functional":
        expected = item["case"]["expected_sha256"]
        if (
            len(jobs) != 1
            or sum(a["committed"] for a in attempts) != 1
            or value.get("result_sha256") != expected
            or value.get("readback_sha256") != expected
            or value.get("readback_host_id") not in host_ids - {value["host_id"]}
            or not value.get("object_version_id")
        ):
            raise ValueError("Exact cross-host versioned result readback required")
    if value.get("terminal_catalog_agree") is not True:
        raise ValueError("Terminal and catalog observations disagree")
    if value.get("unknown_native_work"):
        for resource in ("data_bytes", "physical_bytes", "slots"):
            before, after = value.get(resource + "_before"), value.get(resource + "_after")
            if type(before) is not int or type(after) is not int or after < before:
                raise ValueError("Unknown native work must retain its accounting")
    if item.get("scenario") == "zero_wait_budget" and (
        value["model_calls_before"] != value["model_calls_after"]
        or value.get("attempts_started_while_waiting") != 0
    ):
        raise ValueError("Waiting spent an attempt or a model call")


def run(
    cfg: dict[str, Any],
    stage: str,
    folder: Path,
    execute: bool,
    max_jobs: int = 62,
    max_seconds: int = 3600,
    adapter: Any = transport,
    start_index: int = 0,
    count: int | None = None,
) -> dict[str, Any]:
    if type(max_jobs) is not int or not 1 <= max_jobs <= 62:
        raise ValueError("Invocation job bound must be 1..62")
    if type(max_seconds) is not int or not 1 <= max_seconds <= 3600:
        raise ValueError("Invocation wait bound must be 1..3600 seconds")
    full_plan = plan(cfg, stage)
    if type(start_index) is not int or not 0 <= start_index < len(full_plan):
        raise ValueError("Explicit plan start index is out of bounds")
    if count is not None and (
        type(count) is not int or not 1 <= count <= 62 or start_index + count > len(full_plan)
    ):
        raise ValueError("Explicit scenario count is out of bounds")
    tasks = (
        full_plan[start_index:] if count is None else full_plan[start_index : start_index + count]
    )
    reserved_dispatches = sum(dispatch_cost(task) for task in tasks)
    if execute and reserved_dispatches > max_jobs:
        raise ValueError("Selected batch exceeds the bounded claiming-invocation budget")
    folder.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    result: dict[str, Any] = {
        "schema": "phase7-observations-v1",
        "stage": stage,
        "started_at": datetime.now(UTC).isoformat(),
        "source": identities(),
        "status": "planned",
        "acceptance": "incomplete",
        "jobs_started": 0,
        "dispatches_started": 0,
        "dispatches_planned": reserved_dispatches,
        "scenarios_observed": 0,
        "max_jobs": max_jobs,
        "max_seconds": max_seconds,
        "start_index": start_index,
        "scenario_count": len(tasks),
        "full_plan_count": len(full_plan),
    }
    (folder / "frozen-plan.json").write_bytes(
        canonical(
            {
                "config": cfg,
                "full_plan": full_plan,
                "selected_tasks": tasks,
                "start_index": start_index,
                "scenario_count": len(tasks),
            }
        )
    )
    index = 0

    def request(host: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        nonlocal index
        remaining = max_seconds - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("Invocation wait bound exhausted")
        packet = {
            **body,
            "schema": "phase7-adapter-v1",
            "request_id": str(uuid4()),
            "jobs_remaining": max_jobs - result["dispatches_started"],
            "seconds_remaining": min(1800, remaining),
            "allowed_hosts": cfg["hosts"],
            "frozen_identity": {
                key: cfg[key]
                for key in ("source_sha256", "lock_sha256", "runner_sha256", "namespace_sha256")
            },
        }
        stem = f"{index:03d}"
        index += 1
        (folder / f"{stem}-request.json").write_bytes(canonical(packet))
        response = adapter(host, packet, min(1800, remaining))
        (folder / f"{stem}-response.json").write_bytes(canonical(response))
        if response.get("request_id") != packet["request_id"]:
            raise ValueError("Adapter returned a stale response")
        return response

    try:
        if execute:
            if result["source"] != {k: cfg[k] for k in result["source"]}:
                raise ValueError("Frozen source or lock changed before execution")
            for host in cfg["hosts"]:
                handshake(cfg, host, request(host, {"action": "preflight"}))
            seen_jobs: set[str] = set()
            for task in tasks:
                if result["dispatches_started"] + dispatch_cost(task) > max_jobs:
                    raise ValueError("Invocation job bound exhausted")
                host = cfg["hosts"][task["host_index"]]
                if stage == "functional":
                    value = request(host, {**task, "action": "submit_work"})
                    if type(value.get("jobs_started")) is not int or value["jobs_started"] < 1:
                        raise ValueError("Functional adapter did not report started work")
                    result["jobs_started"] += value["jobs_started"]
                    dispatches = value.get("dispatches_started", value["jobs_started"])
                    if type(dispatches) is not int or dispatches < value["jobs_started"]:
                        raise ValueError("Functional dispatch accounting is invalid")
                    result["dispatches_started"] += dispatches
                    if result["dispatches_started"] > max_jobs:
                        raise ValueError("Adapter violated the invocation job bound")
                    other = cfg["hosts"][1 - task["host_index"]]
                    readback = request(
                        other,
                        {
                            "action": "readback",
                            "kind": task["case"]["kind"],
                            "job_id": value["attempts"][0]["job_id"],
                        },
                    )
                    value.update(
                        readback_host_id=readback["host_id"],
                        readback_sha256=readback["result_sha256"],
                    )
                else:
                    value = request(host, task)
                validate_observation(task, value, {h["host_id"] for h in cfg["hosts"]})
                if stage != "functional":
                    result["jobs_started"] += value["jobs_started"]
                    dispatches = value.get("dispatches_started", value["jobs_started"])
                    if type(dispatches) is not int or dispatches < value["jobs_started"]:
                        raise ValueError("Scenario dispatch accounting is invalid")
                    result["dispatches_started"] += dispatches
                if result["dispatches_started"] > max_jobs:
                    raise ValueError("Adapter violated the invocation job bound")
                if stage == "functional":
                    jobs = {a["job_id"] for a in value["attempts"]}
                    if jobs & seen_jobs:
                        raise ValueError("Functional cases reused a prior job")
                    seen_jobs.update(jobs)
                result["scenarios_observed"] += 1
            if identities() != result["source"]:
                raise ValueError("Executed source changed during observation")
            result["status"] = "observations_validated"
        return result
    except BaseException as error:
        # No raw transport errors, SSH targets, process output or secret-bearing
        # exception strings enter diagnostics. Original requests remain retained.
        result["status"] = "incomplete"
        result["failure_class"] = type(error).__name__
        result["remote_work_status"] = "unknown_requires_owning_host_reconciliation"
        raise
    finally:
        result["duration_seconds"] = time.monotonic() - started
        (folder / "result.json").write_bytes(canonical(result))


def machine_identity() -> str:
    """Operator must additionally verify these are actual distinct host machines."""
    if sys.platform == "win32":
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            value = str(winreg.QueryValueEx(key, "MachineGuid")[0]).encode()
    else:
        value = Path("/etc/machine-id").read_bytes().strip()
    if not value:
        raise ValueError("Machine identity unavailable")
    return hashlib.sha256(value).hexdigest()


def validate_transcript(
    cfg: dict[str, Any],
    stage: str,
    tasks: list[dict[str, Any]],
    folder: Path,
    result: dict[str, Any],
    known_jobs: set[str],
    known_requests: set[str],
) -> dict[str, str]:
    """Replay every exact local exchange; summary flags cannot create coverage."""
    maximum, seconds = result.get("max_jobs"), result.get("max_seconds")
    if (
        type(maximum) is not int
        or not 1 <= maximum <= 62
        or type(seconds) is not int
        or not 1 <= seconds <= 3600
        or result.get("dispatches_planned") != sum(dispatch_cost(task) for task in tasks)
        or sum(dispatch_cost(task) for task in tasks) > maximum
    ):
        raise ValueError("Frozen batch invocation bounds are missing or inconsistent")
    index, jobs, dispatches = 0, 0, 0
    last_seconds = min(1800, seconds)
    paths: list[Path] = []
    hashes: dict[str, str] = {}
    host_ids = {host["host_id"] for host in cfg["hosts"]}
    frozen_identity = {
        key: cfg[key]
        for key in ("source_sha256", "lock_sha256", "runner_sha256", "namespace_sha256")
    }
    metadata = {
        "schema",
        "request_id",
        "jobs_remaining",
        "seconds_remaining",
        "allowed_hosts",
        "frozen_identity",
    }

    def pair(host: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        nonlocal index, last_seconds
        prefix = f"{index:03d}"
        index += 1
        request_path, response_path = (
            folder / f"{prefix}-request.json",
            folder / f"{prefix}-response.json",
        )
        values = []
        for path in (request_path, response_path):
            if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_RESPONSE:
                raise ValueError("Bounded regular paired receipt required")
            raw = path.read_bytes()
            if len(raw) > MAX_RESPONSE:
                raise ValueError("Paired receipt exceeds the response bound")
            values.append(json.loads(raw))
            hashes[path.name] = hashlib.sha256(raw).hexdigest()
        request, response = values
        if not isinstance(request, dict) or not isinstance(response, dict):
            raise ValueError("Paired structured request/response evidence required")
        if (
            set(request) != set(body) | metadata
            or any(request.get(key) != value for key, value in body.items())
            or request.get("schema") != "phase7-adapter-v1"
            or request.get("allowed_hosts") != cfg["hosts"]
            or request.get("frozen_identity") != frozen_identity
            or request.get("jobs_remaining") != maximum - dispatches
        ):
            raise ValueError("Retained request differs from its frozen task or dispatch budget")
        identity = request.get("request_id")
        if (
            not isinstance(identity, str)
            or str(UUID(identity)) != identity
            or identity in known_requests
        ):
            raise ValueError("Request identities must be exact, unique and paired")
        remaining = request.get("seconds_remaining")
        if type(remaining) not in {int, float} or not 0 < remaining <= last_seconds:
            raise ValueError("Retained request wait bound increased or is invalid")
        last_seconds = remaining
        if response.get("request_id") != identity or response.get("host_id") != host["host_id"]:
            raise ValueError("Retained response has a stale request or wrong host identity")
        known_requests.add(identity)
        paths.extend((request_path, response_path))
        return response

    for host in cfg["hosts"]:
        handshake(cfg, host, pair(host, {"action": "preflight"}))
    for task in tasks:
        host = cfg["hosts"][task["host_index"]]
        value = pair(host, {**task, "action": "submit_work"} if stage == "functional" else task)
        started = value.get("jobs_started")
        claimed = value.get("dispatches_started", started)
        if (
            type(started) is not int
            or type(claimed) is not int
            or not 0 <= started <= claimed <= dispatch_cost(task)
            or dispatches + claimed > maximum
        ):
            raise ValueError("Retained scenario accounting exceeds its bounded dispatches")
        jobs += started
        dispatches += claimed
        if stage == "functional":
            peer = cfg["hosts"][1 - task["host_index"]]
            readback = pair(
                peer,
                {
                    "action": "readback",
                    "kind": task["case"]["kind"],
                    "job_id": value["attempts"][0]["job_id"],
                },
            )
            value = {
                **value,
                "readback_host_id": readback["host_id"],
                "readback_sha256": readback["result_sha256"],
            }
        if (
            task["action"] == "fault"
            and value.get("fault_boundary", {}).get("boundary") != task["boundary"]
        ):
            raise ValueError("Observed fault boundary differs from its planned repetition")
        validate_observation(task, value, host_ids)
        identities = {attempt["job_id"] for attempt in value.get("attempts", [])}
        if identities & known_jobs:
            raise ValueError("Independent scenarios reused a previously observed job")
        known_jobs.update(identities)
    if (
        type(result.get("jobs_started")) is not int
        or result["jobs_started"] != jobs
        or type(result.get("dispatches_started")) is not int
        or result["dispatches_started"] != dispatches
    ):
        raise ValueError("Summary counters disagree with the paired scenario evidence")
    names = {path.name for path in paths}
    for number, path in enumerate(folder.iterdir()):
        if number >= 512:
            raise ValueError("Receipt directory inventory exceeds its bound")
        if (
            path.name.endswith("-request.json") or path.name.endswith("-response.json")
        ) and path.name not in names:
            raise ValueError("Unexpected or unpaired request/response evidence")
    return hashes


def combine(cfg: dict[str, Any], stage: str, inputs: list[Path], output: Path) -> dict[str, Any]:
    """Validate disjoint source-identical batch coverage without dispatch or gate credit."""
    expected = plan(cfg, stage)
    if not 1 <= len(inputs) <= 62 or len({path.resolve() for path in inputs}) != len(inputs):
        raise ValueError("Distinct bounded retained batch folders required")
    covered: set[int] = set()
    known_jobs: set[str] = set()
    known_requests: set[str] = set()
    batches = []
    for folder in inputs:
        frozen = read_json(folder / "frozen-plan.json")
        result = read_json(folder / "result.json")
        if (
            frozen.get("config") != cfg
            or frozen.get("full_plan") != expected
            or result.get("stage") != stage
            or result.get("status") != "observations_validated"
            or result.get("source")
            != {key: cfg[key] for key in ("source_sha256", "lock_sha256", "runner_sha256")}
        ):
            raise ValueError("Batch source, configuration, stage or observed outcome differs")
        start, count = result.get("start_index"), result.get("scenario_count")
        if (
            type(start) is not int
            or type(count) is not int
            or count < 1
            or not 0 <= start < len(expected)
            or start + count > len(expected)
            or result.get("full_plan_count") != len(expected)
            or result.get("scenarios_observed") != count
            or frozen.get("start_index") != start
            or frozen.get("scenario_count") != count
            or frozen.get("selected_tasks") != expected[start : start + count]
        ):
            raise ValueError("Batch coverage differs from its frozen selected indices")
        indices = set(range(start, start + count))
        if indices & covered:
            raise ValueError("Overlapping batches cannot supply independent scenario coverage")
        if (
            type(result.get("dispatches_started")) is not int
            or type(result.get("max_jobs")) is not int
            or not 0 <= result["dispatches_started"] <= result["max_jobs"] <= 62
        ):
            raise ValueError("Batch dispatch accounting is missing or exceeds its bound")
        hashes = validate_transcript(
            cfg, stage, expected[start : start + count], folder, result, known_jobs, known_requests
        )
        # Remote fault ledgers remain separately retained; every required local
        # request/response has already been paired and independently revalidated.
        paths = [folder / "frozen-plan.json", folder / "result.json"]
        for path in paths:
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        covered.update(indices)
        batches.append(
            {
                "start_index": start,
                "scenario_count": count,
                "dispatches_started": result["dispatches_started"],
                "files": hashes,
            }
        )
    missing = sorted(set(range(len(expected))) - covered)
    value = {
        "schema": "phase7-batch-coverage-v1",
        "stage": stage,
        "status": "coverage_incomplete" if missing else "coverage_validated",
        "acceptance": "incomplete",
        "covered_indices": sorted(covered),
        "missing_indices": missing,
        "batches": batches,
        "config_sha256": hashlib.sha256(canonical(cfg)).hexdigest(),
        "observed_at": datetime.now(UTC).isoformat(),
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "coverage.json").write_bytes(canonical(value))
    return value


def cli(arguments: list[str], seconds: float) -> Any:
    """Run the normal bounded CLI using the reviewed no-dotenv bootstrap."""
    command = [
        sys.executable,
        "-I",
        "-S",
        str(ROOT / "tests/s3/guarded_python.py"),
        "--",
        "-m",
        *arguments,
    ]
    if os.name == "nt":
        return json.loads(windows_cli(command, seconds))
    return json.loads(bounded_process(command, b"", seconds, local_cli=True))


def windows_cli(command: list[str], timeout: float) -> bytes:
    """Suspend/assign/resume through the existing exact owned Windows Job."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "phase7_owned_job", ROOT / "scripts/v2_phase4_lifecycle.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    job = module.OwnedJob()
    read_fd, write_fd = os.pipe()
    output = bytearray()
    overflow = threading.Event()

    def consume() -> None:
        with os.fdopen(read_fd, "rb") as stream:
            while block := stream.read(4096):
                if len(output) + len(block) > MAX_RESPONSE:
                    overflow.set()
                    return
                output.extend(block)

    reader = threading.Thread(target=consume, daemon=True)
    try:
        with os.fdopen(write_fd, "wb") as stream:
            child = job.spawn(command, cwd=ROOT, env=dict(os.environ), output=stream)
        reader.start()
        deadline = time.monotonic() + timeout
        while child.poll() is None:
            if overflow.is_set() or time.monotonic() >= deadline:
                raise TimeoutError("Owned CLI exceeded its response/deadline bound")
            time.sleep(0.02)
        job.wait_empty(min(15, max(0.1, deadline - time.monotonic())))
        reader.join(5)
        if child.poll() != 0 or overflow.is_set() or reader.is_alive():
            raise ValueError("Owned CLI failed or did not drain bounded output")
        return bytes(output)
    finally:
        if job.active():
            # Exact Job containment includes native descendants; durable charges
            # remain for explicit owning-host reconciliation after a forced stop.
            job.terminate()
        job.close()


def bounded_process(
    command: list[str], payload: bytes, timeout: float, local_cli: bool = False
) -> bytes:
    """Bound both pipe streams while running, including a noisy remote failure."""
    with tempfile.TemporaryFile() as source:
        source.write(payload)
        source.seek(0)
        with subprocess.Popen(
            command,
            stdin=source,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=os.name != "nt",
        ) as process:
            streams = [bytearray(), bytearray()]
            exceeded = threading.Event()

            def drain(pipe: Any, target: bytearray) -> None:
                while block := pipe.read(4096):
                    if len(target) + len(block) > MAX_RESPONSE:
                        exceeded.set()
                        if os.name != "nt":
                            with suppress(ProcessLookupError):
                                os.killpg(process.pid, signal.SIGTERM)
                        else:
                            process.kill()
                        return
                    target.extend(block)

            readers = [
                threading.Thread(target=drain, args=(pipe, target), daemon=True)
                for pipe, target in zip((process.stdout, process.stderr), streams, strict=True)
            ]
            for reader in readers:
                reader.start()
            try:
                process.wait(timeout=timeout)
            except BaseException:
                if os.name != "nt":
                    with suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10 if local_cli else 1)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
                else:
                    process.kill()
                    process.wait(timeout=5)
                raise
            finally:
                for reader in readers:
                    reader.join(5)
            if exceeded.is_set() or any(reader.is_alive() for reader in readers):
                if os.name != "nt":
                    with suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                for reader in readers:
                    reader.join(5)
                raise ValueError("Command output exceeded a bounded response or failed to drain")
            if process.returncode:
                raise ValueError("Command failed; remote work requires owning-host reconciliation")
            return bytes(streams[0])


def wait_visibility_worker(thread: threading.Thread, started: float, seconds: float) -> None:
    """Allow normal CLI drain only within the already established adapter deadline."""
    thread.join(max(0.0, started + seconds - time.monotonic()))


def remote_request(config: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    """Normal functional CLI adapter; controlled fault stages fail closed."""
    import os
    import shutil

    import sqlalchemy as sa

    from marketlab import workers
    from marketlab.config import Settings
    from marketlab.datasets.v2.common import digest
    from marketlab.datasets.v2.core import execute, one
    from marketlab.storage.backend import ObjectConfig
    from marketlab.storage.store import verify_namespace

    if os.environ.get("MARKETLAB_PHASE6_BOOTSTRAP_ACTIVE") != "guarded-python-v1":
        raise ValueError("Adapter requires isolated guarded Python startup")
    if config.get("schema") != "phase7-host-adapter-v1":
        raise ValueError("Reviewed owned-host adapter configuration required")
    UUID(config["host_id"])
    UUID(config["root_id"])
    UUID(packet["request_id"])
    if packet.get("schema") != "phase7-adapter-v1":
        raise ValueError("Invalid adapter protocol")
    validate_host_scope(config, packet)
    frozen = packet.get("frozen_identity")
    if not isinstance(frozen, dict) or identities() != {
        key: frozen.get(key) for key in identities()
    }:
        raise ValueError("Remote source, lock or helper changed before dispatch")
    seconds = packet["seconds_remaining"]
    if type(seconds) not in {int, float} or not 0 < seconds <= 1800:
        raise ValueError("Adapter time bound invalid")
    action = packet.get("action")
    if action not in {
        "preflight",
        "submit_work",
        "readback",
        "visibility",
        "fault",
        "fault_recover",
        "inference",
        "inference_recover",
    }:
        raise ValueError("Scenario adapter not implemented; actual gate remains incomplete")
    # Explicit operator-provisioned context is inherited by every ordinary CLI,
    # including submit/readback; those commands must never infer a host root.
    os.environ["MARKETLAB_WORKER_ROOT_ID"] = config["root_id"]
    settings = Settings()
    engine = sa.create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
    started = time.monotonic()

    def invoke(arguments: list[str]) -> Any:
        remaining = seconds - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("Remote invocation deadline exhausted")
        return cli(arguments, remaining)

    try:
        with engine.connect() as connection:
            execute(connection, "SET statement_timeout='15s'")
            execute(connection, "SET lock_timeout='10s'")
            execute(connection, "SET TRANSACTION READ ONLY")
            root = one(
                connection, "SELECT * FROM v2_worker_roots WHERE root_id=:id", id=config["root_id"]
            )
            current = workers.mode(connection)
            shared = one(connection, "SELECT * FROM v2_capacity_roots WHERE singleton")
            revision = execute(connection, "SELECT version_num FROM alembic_version").scalar_one()
            database = execute(connection, "SELECT current_database()").scalar_one()
        if (
            root is None
            or str(root["host_id"]) != config["host_id"]
            or current is None
            or shared is None
            or database != config.get("owned_database")
        ):
            raise ValueError("Host/root binding unavailable")
        verify_namespace(shared, ObjectConfig.from_settings(settings))
        if shared["object_namespace_sha256"] != frozen.get("namespace_sha256"):
            raise ValueError("Frozen shared namespace changed before dispatch")
        workers.bind_root(engine, settings.storage_path, config["root_id"])
        if action in {"fault", "fault_recover", "inference", "inference_recover"}:
            import importlib.util

            helper = ROOT / "scripts/v2_phase7_faults.py"
            if not helper.is_file() or helper.is_symlink():
                raise ValueError("Reviewed owned fault adapter is unavailable")
            spec = importlib.util.spec_from_file_location("phase7_fault_adapter", helper)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module.execute(config, packet)
        if action == "preflight":
            return {
                "request_id": packet["request_id"],
                "host_id": config["host_id"],
                **identities(),
                "adapter_config_sha256": digest(config),
                "machine_identity_sha256": machine_identity(),
                "namespace_sha256": shared["object_namespace_sha256"],
                "mode": current["mode"],
                "schema_revision": revision,
                "boot_identity": root["boot_identity"],
                "container": Path("/.dockerenv").exists() or Path("/run/.containerenv").exists(),
                "ready": bool(
                    root["ready"] and shutil.disk_usage(settings.storage_path).free >= 50 * 1024**3
                ),
            }
        if action == "visibility":
            scenario = packet.get("scenario")
            cost = dispatch_cost({"action": "visibility", "scenario": scenario})
            if type(packet.get("jobs_remaining")) is not int or packet["jobs_remaining"] < cost:
                raise ValueError("Visibility claiming-invocation budget is exhausted")
            if scenario == "bounded_metrics":
                from prometheus_client import CollectorRegistry

                from marketlab import monitoring

                registry = CollectorRegistry()
                collector = monitoring.DurableCollector()
                collector.update(
                    monitoring.collect_jobs(engine), monitoring.collect_worker_details(engine)
                )
                registry.register(collector)
                samples = [
                    {"name": sample.name, "labels": sample.labels, "value": sample.value}
                    for metric in registry.collect()
                    for sample in metric.samples
                ]
                return {
                    "request_id": packet["request_id"],
                    "status": "visibility_observed",
                    "host_id": config["host_id"],
                    "jobs_started": 0,
                    "dispatches_started": 0,
                    "samples": samples,
                }
            if scenario == "drain_restart_freshness":
                from marketlab.datasets.v2.core import wire

                with engine.connect() as connection:
                    previous = set(
                        execute(
                            connection,
                            "SELECT instance_id FROM v2_worker_instances WHERE root_id=:id",
                            id=config["root_id"],
                        ).scalars()
                    )
                observed_ready = False
                for _ in range(2):
                    completed = threading.Event()
                    errors: list[BaseException] = []

                    def worker(
                        worker_errors: list[BaseException] = errors,
                        worker_completed: threading.Event = completed,
                    ) -> None:
                        try:
                            invoke(
                                [
                                    "marketlab.research_cli",
                                    "v2",
                                    "worker",
                                    "--max-runs",
                                    "1",
                                    "--run",
                                    str(uuid4()),
                                    "--wait-seconds",
                                    "1",
                                    "--worker-root",
                                    config["root_id"],
                                ]
                            )
                        except BaseException as error:
                            worker_errors.append(error)
                        finally:
                            worker_completed.set()

                    thread = threading.Thread(target=worker)
                    thread.start()
                    while not completed.wait(0.05):
                        with engine.connect() as connection:
                            observed_ready |= execute(
                                connection,
                                "SELECT EXISTS(SELECT 1 FROM "
                                "v2_worker_instances WHERE root_id=:id AND state='ready' "
                                "AND heartbeat_at>clock_timestamp()-interval '30 seconds')",
                                id=config["root_id"],
                            ).scalar_one()
                    thread.join(5)
                    if errors:
                        raise ValueError("Normal bounded CLI lifecycle failed") from errors[0]
                with engine.connect() as connection:
                    instances = [
                        dict(row)
                        for row in execute(
                            connection,
                            "SELECT instance_id,state,source_sha256,lock_sha256,"
                            "registered_at,heartbeat_at "
                            "FROM v2_worker_instances WHERE root_id=:id",
                            id=config["root_id"],
                        ).mappings()
                        if row["instance_id"] not in previous
                    ]
                return wire(
                    {
                        "request_id": packet["request_id"],
                        "status": "visibility_observed",
                        "host_id": config["host_id"],
                        "jobs_started": 0,
                        "dispatches_started": 2,
                        "instances": instances,
                        "observed_ready": observed_ready,
                    }
                )
            if scenario in {"incompatible_capability", "missing_source_lock"}:
                from marketlab.datasets.v2.common import V2Error

                with engine.connect() as connection:
                    previous = set(
                        execute(
                            connection,
                            "SELECT instance_id FROM v2_worker_instances WHERE root_id=:id",
                            id=config["root_id"],
                        ).scalars()
                    )
                completed = threading.Event()
                errors = []

                def compatible_worker() -> None:
                    try:
                        invoke(
                            [
                                "marketlab.research_cli",
                                "v2",
                                "worker",
                                "--max-runs",
                                "1",
                                "--run",
                                str(uuid4()),
                                "--wait-seconds",
                                "2",
                                "--worker-root",
                                config["root_id"],
                            ]
                        )
                    except BaseException as error:
                        errors.append(error)
                    finally:
                        completed.set()

                thread = threading.Thread(target=compatible_worker)
                thread.start()
                instance = None
                while not completed.wait(0.02):
                    with engine.connect() as connection:
                        candidates = [
                            dict(row)
                            for row in execute(
                                connection,
                                "SELECT i.*,c.execution_sha256 FROM v2_worker_instances i "
                                "JOIN v2_worker_capabilities c USING(instance_id) "
                                "WHERE i.root_id=:id AND i.state='ready' AND c.kind='research'",
                                id=config["root_id"],
                            ).mappings()
                            if row["instance_id"] not in previous
                        ]
                    if candidates:
                        instance = candidates[0]
                        break
                checks = []
                try:
                    if instance is None:
                        raise VisibilityProbeError("compatibility_registration_missing")
                    options = {
                        "worker_instance_id": str(instance["instance_id"]),
                        "worker_root_id": config["root_id"],
                        "worker_source_sha256": instance["source_sha256"],
                        "worker_lock_sha256": instance["lock_sha256"],
                    }
                    variants = [
                        {**options, "worker_source_sha256": "f" * 64},
                        {**options, "worker_lock_sha256": "f" * 64},
                    ]
                    if scenario == "incompatible_capability":
                        variants = [options]
                    for variant in variants:
                        with engine.connect().execution_options(**variant) as connection:
                            try:
                                workers.guard(
                                    connection,
                                    "memo" if scenario == "incompatible_capability" else "research",
                                    instance["execution_sha256"],
                                )
                            except V2Error as error:
                                checks.append(
                                    {
                                        "error_code": error.code,
                                        "instance_id": str(instance["instance_id"]),
                                        "source_sha256": variant["worker_source_sha256"],
                                        "lock_sha256": variant["worker_lock_sha256"],
                                    }
                                )
                            else:
                                raise VisibilityProbeError("compatibility_guard_accepted")
                finally:
                    wait_visibility_worker(thread, started, seconds)
                if thread.is_alive():
                    raise VisibilityProbeError("compatibility_worker_deadline")
                if errors:
                    raise VisibilityProbeError("compatibility_worker_failed")
                return {
                    "request_id": packet["request_id"],
                    "status": "guard_observed",
                    "host_id": config["host_id"],
                    "jobs_started": 0,
                    "dispatches_started": 1,
                    "checks": checks,
                }
            if scenario not in {"normal_cli", "operator_pagination"}:
                raise ValueError("Controlled visibility lifecycle/metrics probe not implemented")
            pages = []
            cursor = None
            for _ in range(100):
                args = ["marketlab.dataset_cli", "v2", "workers", "--limit", "1"]
                if cursor is not None:
                    args += ["--cursor", cursor]
                page = invoke(args)
                if len(page["items"]) > 1:
                    raise ValueError("Worker pagination exceeded its bound")
                pages.append(page)
                cursor = page["next_cursor"]
                if cursor is None:
                    break
            if cursor is not None:
                raise ValueError("Worker pagination observation exceeds bounded campaign")
            return {
                "request_id": packet["request_id"],
                "status": "visibility_observed",
                "host_id": config["host_id"],
                "jobs_started": 0,
                "dispatches_started": 0,
                "pages": pages,
                "scenario": packet["scenario"],
            }
        before_calls = 0
        with engine.connect() as connection:
            for table in ("copilot_jobs", "memo_jobs", "v2_copilot_jobs", "v2_memo_jobs"):
                before_calls += execute(
                    connection, f"SELECT coalesce(sum(model_calls),0) FROM {table}"
                ).scalar_one()
        kind = packet.get("kind", packet.get("case", {}).get("kind"))
        if kind not in {"research", "official_ingestion", "canonical_ingestion", "copilot", "memo"}:
            raise ValueError("Unsupported functional kind")
        jobs_started = 0
        if action == "submit_work":
            if kind in {"copilot", "memo"} and (
                config.get("allow_model_dispatch") is not True
                or config.get("owned_model_url") != settings.ollama_url
            ):
                raise ValueError("Explicit owned pinned-model dispatch binding required")
            if (
                type(packet.get("jobs_remaining")) is not int
                or not 1 <= packet["jobs_remaining"] <= 62
            ):
                raise ValueError("Adapter job budget exhausted")
            case = packet["case"]
            inputs = config.get("inputs", {})
            binding = inputs[case["input_sha256"]]
            path = Path(binding["input_path"])
            if (
                path.is_symlink()
                or not path.is_file()
                or path.stat().st_size > 65536
                or hashlib.sha256(path.read_bytes()).hexdigest() != case["input_sha256"]
            ):
                raise ValueError("Reviewed functional input changed")
            key = "phase7." + packet["request_id"]
            if kind == "research":
                submitted = invoke(
                    ["marketlab.research_cli", "v2", "submit", "--spec", str(path), "--key", key]
                )
                identity = submitted["id"]
                invoke(
                    [
                        "marketlab.research_cli",
                        "v2",
                        "worker",
                        "--max-runs",
                        "1",
                        "--run",
                        identity,
                        "--wait-seconds",
                        "0",
                        "--worker-root",
                        config["root_id"],
                    ]
                )
            elif kind in {"official_ingestion", "canonical_ingestion"}:
                if kind == "official_ingestion":
                    args = ["submit", "--request", str(path), "--key", key]
                else:
                    source = Path(binding["source_path"])
                    manifest = read_json(path)
                    # Stream the source hash; never load a multi-GiB fixture into memory.
                    from marketlab.datasets.v2.common import sha256_file

                    if source.is_symlink() or sha256_file(source) != manifest["source_sha256"]:
                        raise ValueError("Canonical source input changed")
                    args = ["import", "--manifest", str(path), "--file", str(source), "--key", key]
                submitted = invoke(["marketlab.dataset_cli", "v2", *args])
                submission = submitted["submission_id"]
                invoke(
                    [
                        "marketlab.dataset_cli",
                        "v2",
                        "worker",
                        "--max-jobs",
                        "1",
                        "--submission",
                        submission,
                        "--wait-seconds",
                        "0",
                        "--worker-root",
                        config["root_id"],
                    ]
                )
                with engine.connect() as connection:
                    rows = list(
                        execute(
                            connection,
                            "SELECT job_id FROM v2_ingestion_jobs WHERE submission_id=:id",
                            id=submission,
                        ).scalars()
                    )
                if len(rows) != 1:
                    raise ValueError("Functional ingestion case must contain exactly one job")
                identity = str(rows[0])
            elif kind == "copilot":
                submitted = invoke(
                    ["marketlab.copilot_cli", "v2", "create", "--request", str(path), "--key", key]
                )
                request_id = submitted["request_id"]
                invoke(
                    [
                        "marketlab.copilot_cli",
                        "v2",
                        "worker",
                        "--max-jobs",
                        "1",
                        "--request",
                        request_id,
                        "--wait-seconds",
                        "0",
                        "--worker-root",
                        config["root_id"],
                    ]
                )
                with engine.connect() as connection:
                    identity = str(
                        execute(
                            connection,
                            "SELECT job_id FROM v2_copilot_jobs WHERE request_id=:id "
                            "ORDER BY revision DESC LIMIT 1",
                            id=request_id,
                        ).scalar_one()
                    )
            else:
                identity = str(UUID(read_json(path)["run_id"]))
                invoke(["marketlab.memo_cli", "v2", "enqueue", "--run", identity, "--key", key])
                invoke(
                    [
                        "marketlab.memo_cli",
                        "v2",
                        "worker",
                        "--max-jobs",
                        "1",
                        "--run",
                        identity,
                        "--wait-seconds",
                        "0",
                        "--worker-root",
                        config["root_id"],
                    ]
                )
            jobs_started = 1
        else:
            identity = str(UUID(packet["job_id"]))
        ledger_kind = "ingestion" if kind in {"official_ingestion", "canonical_ingestion"} else kind
        ident = "job_id" if ledger_kind in {"ingestion", "copilot"} else "run_id"
        table = "v2_research_runs" if ledger_kind == "research" else f"v2_{ledger_kind}_jobs"
        with engine.connect() as connection:
            row = one(connection, f"SELECT * FROM {table} WHERE {ident}=:id", id=identity)
        if row is None or row["state"] != "succeeded":
            raise ValueError("Functional job is not a verified terminal success")
        if ledger_kind == "research":
            content = invoke(["marketlab.research_cli", "v2", "results", "--run", identity])
            package_column, package_id = "v2_research_id", identity
        elif ledger_kind == "ingestion":
            package_column, package_id = "v2_dataset_id", row["result_version"]
            content = invoke(["marketlab.dataset_cli", "v2", "inspect", "--version", package_id])
        elif ledger_kind == "memo":
            value = invoke(["marketlab.memo_cli", "v2", "read", "--run", identity])
            content = value["memo"]
            package_column, package_id = "v2_memo_id", identity
        else:
            value = invoke(
                ["marketlab.copilot_cli", "v2", "inspect", "--request", str(row["request_id"])]
            )
            if value["outcome"] != "submitted" or not value["run_id"]:
                raise ValueError("Functional copilot must commit its validated numerical handoff")
            content = {
                "outcome": value["outcome"],
                "interpretation": value["revisions"][-1]["interpretation"],
                "spec": value["revisions"][-1]["spec"],
            }
            # Verify selected source objects from the opposite host through the
            # normal catalog reader. Copilot output itself is durable DB content.
            selected = [
                entry["dataset_version_id"] for entry in value["snapshot"].get("datasets", [])
            ]
            if not selected:
                raise ValueError("Copilot selected-source references unavailable")
            package_column, package_id = "v2_dataset_id", selected[0]
            for version in selected:
                invoke(["marketlab.dataset_cli", "v2", "inspect", "--version", version])
        sha = digest(content)
        with engine.connect() as connection:
            attempts = [
                dict(a)
                for a in execute(
                    connection,
                    f"SELECT a.{ident} AS job_id,a.worker_instance_id,r.host_id,a.attempt_number,"
                    "a.fencing_token,(a.outcome='succeeded') AS committed "
                    f"FROM v2_{ledger_kind}_attempts a "
                    "JOIN v2_worker_instances i ON i.instance_id=a.worker_instance_id "
                    "JOIN v2_worker_roots r USING(root_id) "
                    f"WHERE a.{ident}=:id ORDER BY attempt_number",
                    id=identity,
                ).mappings()
            ]
            objects = [
                dict(o)
                for o in execute(
                    connection,
                    "SELECT o.version_id FROM v2_storage_packages p "
                    "JOIN v2_storage_copies c USING(package_id) "
                    "JOIN v2_storage_objects o USING(copy_id) "
                    f"WHERE p.{package_column}=:id AND c.active "
                    "AND o.state='verified' AND o.backend_alias<>'local'",
                    id=package_id,
                ).mappings()
            ]
        if row is None or row["state"] != "succeeded" or not objects:
            raise ValueError("Numerical terminal/catalog/versioned object agreement unavailable")
        if action == "readback":
            return {
                "request_id": packet["request_id"],
                "host_id": config["host_id"],
                "result_sha256": sha,
            }
        from marketlab.datasets.v2.core import wire

        after_calls = 0
        with engine.connect() as connection:
            for table in ("copilot_jobs", "memo_jobs", "v2_copilot_jobs", "v2_memo_jobs"):
                after_calls += execute(
                    connection, f"SELECT coalesce(sum(model_calls),0) FROM {table}"
                ).scalar_one()
        if ledger_kind in {"research", "ingestion"} and before_calls != after_calls:
            raise ValueError("Numerical observation spent model calls")
        return wire(
            {
                "request_id": packet["request_id"],
                "status": "observed",
                "host_id": config["host_id"],
                "jobs_started": jobs_started,
                "dispatches_started": jobs_started,
                "attempts": attempts,
                "result_sha256": sha,
                "object_version_id": objects[0]["version_id"],
                "model_calls_before": before_calls,
                "model_calls_after": after_calls,
                "terminal_catalog_agree": True,
            }
        )
    finally:
        engine.dispose()


def main() -> int:
    if sys.argv[1:2] == ["--adapter-config"]:
        try:
            if len(sys.argv) != 3:
                raise ValueError("Adapter configuration argument required")
            packet = json.loads(sys.stdin.buffer.read(MAX_RESPONSE + 1))
            value = remote_request(read_json(Path(sys.argv[2])), packet)
            sys.stdout.buffer.write(canonical(value))
            return 0
        except Exception as error:
            result = {"status": "incomplete", "acceptance": "incomplete"}
            if isinstance(error, VisibilityProbeError) and error.phase in VISIBILITY_FAILURE_PHASES:
                result["phase"] = error.phase
            sys.stdout.buffer.write(canonical(result))
            return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-jobs", type=int, default=62)
    parser.add_argument("--max-seconds", type=int, default=3600)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--count", type=int)
    parser.add_argument("--combine", nargs="+", type=Path, metavar="BATCH_FOLDER")
    args = parser.parse_args()
    try:
        if args.combine:
            if args.execute:
                raise ValueError("Coverage combination never dispatches work")
            value = combine(read_json(args.config), args.stage, args.combine, args.output)
            print(json.dumps({"status": value["status"], "acceptance": "incomplete"}))
            return 0 if not value["missing_indices"] else 1
        value = run(
            read_json(args.config),
            args.stage,
            args.output,
            args.execute,
            args.max_jobs,
            args.max_seconds,
            start_index=args.start_index,
            count=args.count,
        )
        print(json.dumps({"status": value["status"], "acceptance": "incomplete"}))
        return 0
    except Exception:
        print('{"status":"incomplete","acceptance":"incomplete"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
