"""Exact worker ownership, Windows launcher handling and failure-path native drain."""

import asyncio
import ctypes
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


def native_command_buffer(control, text):
    payload = text.encode("utf-16-le")
    header = ctypes.sizeof(control.WindowsUnicodeString)
    buffer = ctypes.create_string_buffer(header + len(payload) + 2)
    value = control.WindowsUnicodeString.from_buffer(buffer)
    value.length = len(payload)
    value.maximum_length = len(payload) + 2
    value.buffer = ctypes.addressof(buffer) + header
    ctypes.memmove(value.buffer, payload, len(payload))
    return buffer


def test_bounded_native_command_response_preserves_unicode_and_windows_limit(control):
    for text in ['"C:\\owned path\\python.exe" "\u03a9 plan.json"', "x" * 32766]:
        buffer = native_command_buffer(control, text)
        assert control.windows_command_text(buffer, ctypes.sizeof(buffer)) == text


@pytest.mark.parametrize(
    "invalid",
    [
        "short_header",
        "oversize_response",
        "empty",
        "odd_length",
        "odd_maximum",
        "length_exceeds_maximum",
        "null_pointer",
        "header_pointer",
        "outside_pointer",
        "misaligned_pointer",
        "truncated_payload",
        "embedded_null",
        "invalid_utf16",
    ],
)
def test_native_command_response_rejects_invalid_bounds_before_dereference(control, invalid):
    text = "owned\0command" if invalid == "embedded_null" else "owned command"
    buffer = native_command_buffer(control, text)
    value = control.WindowsUnicodeString.from_buffer(buffer)
    returned = ctypes.sizeof(buffer)
    if invalid == "short_header":
        returned = ctypes.sizeof(control.WindowsUnicodeString) - 1
    elif invalid == "oversize_response":
        returned += 1
    elif invalid == "empty":
        value.length = 0
    elif invalid == "odd_length":
        value.length -= 1
    elif invalid == "odd_maximum":
        value.maximum_length -= 1
    elif invalid == "length_exceeds_maximum":
        value.maximum_length = value.length - 2
    elif invalid == "null_pointer":
        value.buffer = None
    elif invalid == "header_pointer":
        value.buffer = ctypes.addressof(buffer)
    elif invalid == "outside_pointer":
        value.buffer = ctypes.addressof(buffer) + ctypes.sizeof(buffer)
    elif invalid == "misaligned_pointer":
        value.buffer += 1
    elif invalid == "truncated_payload":
        returned -= 2
    elif invalid == "invalid_utf16":
        ctypes.memmove(value.buffer, b"\x00\xd8", 2)
    with pytest.raises((OSError, UnicodeDecodeError)):
        control.windows_command_text(buffer, returned)


@pytest.mark.parametrize(
    "failure",
    [
        None,
        "open",
        "birth_read",
        "birth_before",
        "unsupported",
        "access_denied",
        "insufficient_buffer",
        "bounds",
        "image",
        "image_empty",
        "image_truncated",
        "birth_after",
        "argv",
    ],
)
def test_native_command_handle_exact_birth_and_failures_close_handle(control, monkeypatch, failure):
    calls = []
    birth_reads = []

    def open_process(rights, inherit, pid):
        assert (rights, inherit, pid) == (0x1000, False, 123)
        return None if failure == "open" else 456

    def process_times(handle, created, *unused):
        assert handle == 456
        birth_reads.append(1)
        if failure == "birth_read":
            return False
        created._obj.dwLowDateTime = (
            101
            if failure == "birth_before" or (failure == "birth_after" and len(birth_reads) == 2)
            else 100
        )
        return True

    def query(handle, kind, buffer, size, returned):
        assert handle == 456 and kind == 60 and size <= 65600
        if failure in {"unsupported", "access_denied", "insufficient_buffer"}:
            return {
                "unsupported": -1073741821,
                "access_denied": -1073741790,
                "insufficient_buffer": -1073741820,
            }[failure]
        payload = '"owned python.exe" owned-plan'.encode("utf-16-le")
        header = ctypes.sizeof(control.WindowsUnicodeString)
        value = control.WindowsUnicodeString.from_buffer(buffer)
        value.length = len(payload)
        value.maximum_length = len(payload) + 2
        value.buffer = ctypes.addressof(buffer) + header
        ctypes.memmove(value.buffer, payload, len(payload))
        returned._obj.value = size + 1 if failure == "bounds" else header + len(payload) + 2
        return 0

    def image(handle, flags, buffer, size):
        assert (handle, flags) == (456, 0)
        if failure == "image":
            return False
        buffer.value = "owned python.exe"
        size._obj.value = (
            0
            if failure == "image_empty"
            else len(buffer)
            if failure == "image_truncated"
            else len(buffer.value)
        )
        return True

    kernel = SimpleNamespace(
        OpenProcess=open_process,
        CloseHandle=lambda handle: calls.append(handle),
        GetProcessTimes=process_times,
        QueryFullProcessImageNameW=image,
    )
    native = SimpleNamespace(NtQueryInformationProcess=query)
    monkeypatch.setattr(
        control.ctypes,
        "WinDLL",
        lambda name, **kwargs: kernel if name == "kernel32" else native,
        raising=False,
    )

    def argv(text):
        if failure == "argv":
            raise OSError("Controlled command-line parser failure")
        return ["owned python.exe", "owned-plan"]

    monkeypatch.setattr(control, "windows_argv", argv)
    if failure:
        with pytest.raises((OSError, RuntimeError)):
            control.windows_command(123, 100)
    else:
        assert control.windows_command(123, 100) == (
            ["owned python.exe", "owned-plan"],
            "owned python.exe",
        )
        assert len(birth_reads) == 2
    assert calls == ([] if failure == "open" else [456])


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
async def test_actual_venv_launcher_worker_marker_and_failure_cleanup(
    control, wrong_hash, monkeypatch
):
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
    monkeypatch.setattr(
        control.subprocess,
        "check_output",
        lambda *args, **kwargs: pytest.fail("Exact native identity must not spawn a query shell"),
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
