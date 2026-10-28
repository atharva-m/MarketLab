"""Production spawned-worker watchdog exits after active or idle parent death."""

import ctypes
import errno
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest


class OwnedProcess:
    """Query exact owned processes without Windows os.kill(pid, 0)."""

    def __init__(self, pid):
        self.pid = pid
        self.handle = None
        self.pidfd = None
        self.started = None
        if os.name == "nt":
            self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            self.kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
            self.kernel.OpenProcess.restype = ctypes.c_void_p
            self.kernel.GetExitCodeProcess.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_uint32),
            ]
            self.kernel.GetProcessTimes.argtypes = [ctypes.c_void_p] + [
                ctypes.POINTER(ctypes.c_uint64)
            ] * 4
            self.kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            self.kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            self.handle = self.kernel.OpenProcess(0x100000 | 0x1000 | 0x1, False, pid)
            assert self.handle, "Cannot inspect an owned spawned worker"
            creation, exited, kernel, user = [ctypes.c_uint64() for _ in range(4)]
            assert self.kernel.GetProcessTimes(
                self.handle,
                ctypes.byref(creation),
                ctypes.byref(exited),
                ctypes.byref(kernel),
                ctypes.byref(user),
            )
            self.started = creation.value
        else:
            self.started = self._linux_identity()
            assert self.started is not None, "Owned worker disappeared before parent death"
            if hasattr(os, "pidfd_open"):
                self.pidfd = os.pidfd_open(pid)

    def _linux_stat(self):
        try:
            return Path(f"/proc/{self.pid}/stat").read_text().rsplit(")", 1)[1].split()
        except OSError as error:
            # A process may exit after /proc/stat opens but before its read.
            # Linux reports that race as ESRCH rather than a missing path.
            if error.errno in (errno.ENOENT, errno.ESRCH):
                return None
            raise

    def _linux_identity(self):
        fields = self._linux_stat()
        return fields[19] if fields is not None else None

    def running(self):
        if self.handle is not None:
            code = ctypes.c_uint32()
            assert self.kernel.GetExitCodeProcess(self.handle, ctypes.byref(code))
            return code.value == 259
        # Check identity and state from the same read, including disappearance
        # while reading. An exited zombie has no running compute; this does not
        # promise grandchild reaping by every PID 1.
        fields = self._linux_stat()
        return fields is not None and fields[19] == self.started and fields[0] != "Z"

    def terminate(self):
        if not self.running():
            return
        if self.handle is not None:
            assert self.kernel.TerminateProcess(self.handle, 1)
            assert self.kernel.WaitForSingleObject(self.handle, 5000) == 0
        elif self.pidfd is not None and hasattr(signal, "pidfd_send_signal"):
            signal.pidfd_send_signal(self.pidfd, signal.SIGKILL)
        else:
            # Identity was captured while this exact child was alive. Never
            # signal a reused PID or another application process.
            os.kill(self.pid, signal.SIGKILL)

    def cleanup(self):
        try:
            self.terminate()
        finally:
            if self.handle is not None:
                self.kernel.CloseHandle(self.handle)
                self.handle = None
            if self.pidfd is not None:
                os.close(self.pidfd)
                self.pidfd = None


def _linux_process_probe():
    """Exercise Linux inspection on either CI platform without owning a real PID."""
    process = object.__new__(OwnedProcess)
    process.pid = 123
    process.handle = None
    process.started = "42"
    return process


@pytest.mark.parametrize("error_number", [errno.ENOENT, errno.ESRCH])
def test_owned_linux_process_disappearance_during_stat_read(monkeypatch, error_number):
    error = OSError(error_number, "Owned process exited during stat read")

    def vanished(path):
        assert path == Path("/proc/123/stat")
        raise error

    monkeypatch.setattr(Path, "read_text", vanished)
    process = _linux_process_probe()
    assert process._linux_identity() is None
    assert not process.running()


@pytest.mark.parametrize("error_number", [errno.EACCES, errno.EPERM, errno.EIO])
def test_owned_linux_process_inspection_errors_propagate(monkeypatch, error_number):
    error = OSError(error_number, "Cannot inspect owned process")

    def unreadable(path):
        assert path == Path("/proc/123/stat")
        raise error

    monkeypatch.setattr(Path, "read_text", unreadable)
    process = _linux_process_probe()
    for inspect in [process._linux_identity, process.running]:
        with pytest.raises(OSError) as caught:
            inspect()
        assert caught.value is error


@pytest.mark.parametrize(
    ("state", "started", "running"), [("S", "42", True), ("Z", "42", False), ("S", "43", False)]
)
def test_owned_linux_process_uses_one_identity_and_state_snapshot(
    monkeypatch, state, started, running
):
    reads = []

    def stat(path):
        reads.append(path)
        # /proc's comm may itself contain parentheses; starttime is field 22.
        return "123 (owned (worker)) " + " ".join([state, *(["0"] * 18), started])

    monkeypatch.setattr(Path, "read_text", stat)
    assert _linux_process_probe().running() is running
    assert reads == [Path("/proc/123/stat")]


@pytest.mark.parametrize("mode", ["active", "idle"])
def test_spawned_workers_stop_after_owned_parent_death(tmp_path, mode):
    helper = Path(__file__).with_name("verifier_parent_death_helper.py")
    log_path = tmp_path / "controller.log"
    owned = []
    controller = None
    process = None
    evidence = {"mode": mode, "status": "running"}
    try:
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, str(helper), str(tmp_path), mode],
                stdout=log,
                stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        deadline = time.monotonic() + 25
        ready = tmp_path / "ready.json"
        while not ready.exists():
            identity_path = tmp_path / "controller.json"
            if controller is None and identity_path.exists():
                identity = json.loads(identity_path.read_text(encoding="utf-8"))
                if identity["controller_pid"] != process.pid:
                    assert os.name == "nt" and identity["launcher_parent_pid"] == process.pid
                controller = OwnedProcess(identity["controller_pid"])
            assert process.poll() is None, log_path.read_text(encoding="utf-8")
            assert time.monotonic() < deadline, log_path.read_text(encoding="utf-8")
            time.sleep(0.02)
        report = json.loads(ready.read_text(encoding="utf-8"))
        if report["controller_pid"] != process.pid:
            # Windows venv Python can redirect to an actual interpreter child.
            assert os.name == "nt" and report["launcher_parent_pid"] == process.pid
        if controller is None:
            controller = OwnedProcess(report["controller_pid"])
        assert controller.pid == report["controller_pid"]
        snapshot = report["snapshot"]
        assert snapshot["configured_max_workers"] == 2 and snapshot["start_method"] == "spawn"
        assert len(snapshot["worker_pids"]) == 2
        assert {record["pid"] for record in report["entered"]} == set(snapshot["worker_pids"])
        assert {record["version"] for record in report["entered"]} == {"a" * 64, "b" * 64}
        assert snapshot["active_submitted"] == (2 if mode == "active" else 0)
        owned = [OwnedProcess(pid) for pid in snapshot["worker_pids"]]
        assert all(worker.running() for worker in owned)
        began = time.monotonic()
        controller.terminate()  # Exact recorded controller handle, no tree kill.
        process.wait(timeout=5)
        while any(worker.running() for worker in owned):
            assert time.monotonic() - began < 8, "Owned verifier child survived parent death"
            time.sleep(0.02)
        evidence.update(
            status="passed",
            controller_pid=report["controller_pid"],
            launcher_pid=process.pid,
            controller_creation_identity=controller.started,
            worker_pids=snapshot["worker_pids"],
            entered=report["entered"],
            worker_creation_identities=[worker.started for worker in owned],
            stopped_seconds=time.monotonic() - began,
            method=(
                "Production initializer/watchdog; controlled task establishes active/idle state"
            ),
        )
        print(json.dumps(evidence), flush=True)
    except BaseException as error:
        evidence.update(status="failed", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        if controller is not None:
            controller.cleanup()
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        for worker in owned:
            worker.cleanup()
        (tmp_path / "parent-death-result.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )
