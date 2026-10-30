"""Exact worker ownership, Windows launcher handling and failure-path native drain."""

import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def control():
    return load(
        "phase3_process_control_test",
        Path(__file__).resolve().parents[1] / "scripts/v2_phase3_processes.py",
    )


def command_values(tmp_path):
    command = [
        sys.executable,
        str(tmp_path / "script.py"),
        "crash-child",
        "--config",
        str(tmp_path / "config.json"),
        "--plan",
        str(tmp_path / "plan.json"),
        "--invocation",
        "p3-owned",
    ]
    allowed = {str(Path(sys.executable).resolve())}
    return command, allowed


def test_native_descendants_bind_parent_creation_and_reject_reused_launcher(control):
    rows = {
        10: {"parent": 1, "identity": 100},
        11: {"parent": 10, "identity": 101},
        12: {"parent": 11, "identity": 102},
        13: {"parent": 10, "identity": 99},
        20: {"parent": 1, "identity": 200},
    }
    assert set(control.descendants(rows, {10: 100})) == {10, 11, 12}
    assert not control.descendants(rows, {10: 99})


@pytest.mark.parametrize("change", ["plan", "script", "config", "invocation", "executable"])
def test_exact_command_plan_proof_refuses_foreign_values(control, tmp_path, change):
    expected, allowed = command_values(tmp_path)
    actual = {"argv": list(expected), "executable": sys.executable}
    assert control.matching(actual, expected, allowed)
    if change == "executable":
        actual["executable"] = str(tmp_path / "foreign.exe")
    else:
        actual["argv"][{"script": 1, "config": 4, "plan": 6, "invocation": 8}[change]] = "foreign"
    assert not control.matching(actual, expected, allowed)


@pytest.mark.parametrize("foreign", [False, True])
def test_cleanup_only_verified_command_and_birth_descendants_worker_before_launcher(
    control, tmp_path, monkeypatch, foreign
):
    expected, allowed = command_values(tmp_path)
    rows = {
        10: {"parent": 1, "identity": 100},
        11: {"parent": 10, "identity": 101},
        99: {"parent": 1, "identity": 900},
    }
    if foreign:
        rows[12] = {"parent": 10, "identity": 102}

    def inspect(pid, birth):
        argv = list(expected)
        if pid == 12:
            argv[6] = "foreign-plan.json"
        return {**rows[pid], "pid": pid, "argv": argv, "executable": sys.executable}

    killed = []

    def terminate(pid, birth):
        assert rows[pid]["identity"] == birth
        killed.append(pid)
        rows.pop(pid)

    monkeypatch.setattr(control, "inventory", lambda: dict(rows))
    monkeypatch.setattr(control, "command", inspect)
    monkeypatch.setattr(control, "terminate", terminate)
    process = SimpleNamespace(pid=10, wait=lambda timeout: None)
    if foreign:
        with pytest.raises(RuntimeError, match="preserved"):
            control.cleanup(process, 100, expected, allowed, {11: 101})
        assert 12 in rows
    else:
        assert len(control.cleanup(process, 100, expected, allowed, {11: 101})) == 2
    assert killed == [11, 10] and 99 in rows


@pytest.mark.asyncio
@pytest.mark.parametrize("wrong_hash", [False, True])
async def test_actual_venv_launcher_worker_marker_and_failure_cleanup(control, wrong_hash):
    project = (await asyncio.to_thread(Path(__file__).resolve)).parents[1]
    harness = load("phase3_process_probe_harness", project / "scripts/v2_phase3_acceptance.py")
    case = harness.BASE / ("process-probe-" + uuid4().hex)
    case.mkdir(parents=True)
    plan = {
        "boundary": "probe",
        "marker": str(case / "marker.json"),
        "run_id": "process-only-no-database",
    }
    command, prepared, allowed, plan_hash = harness.boundary_plan(
        case / "unused-private-config.json", case, plan, "p3-process-probe", "process-probe-child"
    )
    if wrong_hash:
        with pytest.raises(RuntimeError, match="plan mismatch"):
            await control.run(command, prepared, case, allowed, harness.save, "0" * 64)
    else:
        marker = await control.run(command, prepared, case, allowed, harness.save, plan_hash)
        assert marker["boundary"] == "probe" and marker["plan_sha256"] == plan_hash
    receipt = json.loads((case / "process-control.json").read_bytes())
    assert receipt["launcher_reaped"]
    assert receipt["status"] == ("failed" if wrong_hash else "passed")
    assert receipt["terminated_exact"]
    after = control.inventory()
    assert not any(
        after.get(r["pid"], {}).get("identity") == r["identity"]
        for r in receipt["terminated_exact"]
    )
    assert all(r["argv"][6] == str(case / "plan.json") for r in receipt["terminated_exact"])
    if os.name == "nt" and not wrong_hash:
        # The assertion deliberately accommodates both the two-process venv shim
        # and a direct interpreter while requiring exact proof of the real PID.
        assert marker["pid"] == receipt["worker"]["pid"]


@pytest.mark.parametrize(
    "race", ["vanished", "changed_birth", "live_unverified", "termination_race"]
)
def test_cleanup_continues_after_inspection_or_birth_race(control, tmp_path, monkeypatch, race):
    expected, allowed = command_values(tmp_path)
    rows = {
        10: {"parent": 1, "identity": 100},
        11: {"parent": 10, "identity": 101},
        12: {"parent": 10, "identity": 102},
    }
    killed = []

    def inspect(pid, birth):
        if pid == 11 and race != "termination_race":
            if race == "vanished":
                rows.pop(pid)
            elif race == "changed_birth":
                rows[pid] = {"parent": 99, "identity": 999}
            raise RuntimeError("Controlled inspection race")
        return {**rows[pid], "pid": pid, "argv": list(expected), "executable": sys.executable}

    def terminate(pid, birth):
        if pid == 11 and race == "termination_race":
            rows[pid] = {"parent": 99, "identity": 999}
            raise RuntimeError("Controlled birth change before termination")
        assert rows[pid]["identity"] == birth
        killed.append(pid)
        rows.pop(pid)

    monkeypatch.setattr(control, "inventory", lambda: dict(rows))
    monkeypatch.setattr(control, "command", inspect)
    monkeypatch.setattr(control, "terminate", terminate)
    monkeypatch.setattr(control, "UNVERIFIED_DRAIN_SECONDS", 0)
    diagnostics = {}
    process = SimpleNamespace(pid=10, wait=lambda timeout: None)
    if race == "live_unverified":
        with pytest.raises(RuntimeError, match="preserved"):
            control.cleanup(process, 100, expected, allowed, {11: 101}, diagnostics)
        assert diagnostics["unmatched_observed"][0]["pid"] == 11
    else:
        control.cleanup(process, 100, expected, allowed, {11: 101}, diagnostics)
        assert diagnostics["skipped_before_cleanup"][0]["pid"] == 11
    assert set(killed) == {10, 12} and 11 not in killed
    if race in {"changed_birth", "termination_race"}:
        assert rows[11]["identity"] == 999


@pytest.mark.asyncio
@pytest.mark.parametrize("expires", [True, False])
async def test_unknown_launcher_birth_waits_exact_handle_bootstrap_fuse_without_kill(
    control, tmp_path, monkeypatch, expires
):
    waits = []

    class Process:
        pid = 123
        returncode = None

        def wait(self, timeout):
            waits.append(timeout)
            if not expires:
                raise control.subprocess.TimeoutExpired("owned-bootstrap", timeout)
            self.returncode = 72
            return self.returncode

        def poll(self):
            return self.returncode

    process = Process()
    monkeypatch.setattr(control.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(control, "inventory", lambda: {})
    monkeypatch.setattr(
        control, "terminate", lambda *args: pytest.fail("Unknown birth must not be killed")
    )

    def save(path, value):
        path.write_text(json.dumps(value))

    with pytest.raises(
        RuntimeError, match="creation identity unavailable" if expires else "bootstrap fuse"
    ):
        await control.run([sys.executable], {}, tmp_path, set(), save, "plan-hash")
    assert waits == [75]
    record = json.loads((tmp_path / "process-control.json").read_bytes())
    assert record["unknown_launcher_birth"] and record["bootstrap_fuse_exit"] is expires
    if expires:
        assert record["launcher_reaped"] and record["bootstrap_exit_code"] == 72
    else:
        assert record["unverified_launcher_pid"] == 123
