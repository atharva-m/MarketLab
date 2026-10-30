"""Exact owned crash-worker control, including the Windows venv launcher shim."""

import asyncio
import ctypes
import hashlib
import importlib.util
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

_INVENTORY: Any = None
UNVERIFIED_DRAIN_SECONDS = 5.0
BOOTSTRAP_FUSE_HEADROOM_SECONDS = 75


def inventory() -> dict[int, dict[str, Any]]:
    """Reuse the retained R8 native parent/birth inventory, without broad command reads."""
    global _INVENTORY
    if _INVENTORY is None:
        spec = importlib.util.spec_from_file_location(
            "phase3_retained_process_inventory", Path(__file__).with_name("r8_common.py")
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        import sys

        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _INVENTORY = module.processes
    return _INVENTORY()


def descendants(
    rows: dict[int, dict[str, Any]], roots: dict[int, Any]
) -> dict[int, dict[str, Any]]:
    selected = {pid for pid, birth in roots.items() if rows.get(pid, {}).get("identity") == birth}
    while True:
        expanded = selected | {
            pid
            for pid, row in rows.items()
            if row["parent"] in selected
            and int(row["identity"]) >= int(rows[row["parent"]]["identity"])
        }
        if expanded == selected:
            return {pid: rows[pid] for pid in selected}
        selected = expanded


def windows_argv(text: str) -> list[str]:
    from ctypes import wintypes

    shell = ctypes.WinDLL("shell32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel.LocalFree.argtypes = [wintypes.HLOCAL]
    count = ctypes.c_int()
    pointer = shell.CommandLineToArgvW(text, ctypes.byref(count))
    if not pointer:
        raise OSError("Owned command line unavailable")
    try:
        return [pointer[index] for index in range(count.value)]
    finally:
        kernel.LocalFree(pointer)


def command(pid: int, birth: Any) -> dict[str, Any]:
    before = inventory().get(pid)
    if before is None or before["identity"] != birth:
        raise RuntimeError("Owned process birth changed before command inspection")
    if os.name == "nt":
        # Only this already ancestry/birth-checked PID is queried; unrelated
        # command lines and environments are never enumerated or recorded.
        code = (
            f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId = {int(pid)}'; "
            "if($null -ne $p){$p | Select-Object "
            "ProcessId,ParentProcessId,ExecutablePath,CommandLine "
            "| ConvertTo-Json -Compress}"
        )
        raw = subprocess.check_output(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", code],
            text=True,
            timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        data = json.loads(raw)
        argv = windows_argv(data["CommandLine"])
        executable = data["ExecutablePath"]
    else:
        argv = [
            v.decode()
            for v in (Path("/proc") / str(pid) / "cmdline").read_bytes().split(b"\0")
            if v
        ]
        executable = str((Path("/proc") / str(pid) / "exe").resolve())
    after = inventory().get(pid)
    if after is None or after["identity"] != birth or after["parent"] != before["parent"]:
        raise RuntimeError("Owned process changed during command inspection")
    return {**after, "pid": pid, "argv": argv, "executable": executable}


def matching(actual: dict[str, Any], expected: list[str], allowed_executables: set[str]) -> bool:
    if len(actual["argv"]) != len(expected):
        return False
    # Match exact argument tokens; only executable/path spelling is normalized.
    paths = {0, 1, 4, 6}
    for offset, (left, right) in enumerate(zip(actual["argv"], expected, strict=True)):
        if offset in paths:
            if Path(left).resolve() != Path(right).resolve():
                return False
        elif left != right:
            return False
    return Path(actual["executable"]).resolve() in {Path(v).resolve() for v in allowed_executables}


def terminate(pid: int, birth: Any) -> None:
    current = inventory().get(pid)
    if current is None:
        return
    if current["identity"] != birth:
        raise RuntimeError("Refuse termination of reused owned PID")
    if os.name == "nt":
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [
            ctypes.POINTER(wintypes.FILETIME)
        ] * 4
        kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000 | 0x100000 | 1, False, pid)
        if not handle:
            raise OSError("Owned process handle unavailable")
        try:
            created, exited, cpu, user = (wintypes.FILETIME() for _ in range(4))
            if not kernel.GetProcessTimes(
                handle,
                ctypes.byref(created),
                ctypes.byref(exited),
                ctypes.byref(cpu),
                ctypes.byref(user),
            ):
                raise OSError("Owned process creation time unavailable")
            actual = (created.dwHighDateTime << 32) | created.dwLowDateTime
            if actual != birth:
                raise RuntimeError("Refuse termination of changed process handle")
            if (
                not kernel.TerminateProcess(handle, 91)
                or kernel.WaitForSingleObject(handle, 15000) != 0
            ):
                raise OSError("Exact owned process termination failed")
        finally:
            kernel.CloseHandle(handle)
    else:
        import signal

        os.kill(pid, signal.SIGKILL)


def cleanup(
    process: subprocess.Popen[Any],
    launcher_birth: Any,
    expected: list[str],
    allowed_executables: set[str],
    trusted: dict[int, Any],
    diagnostics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    roots = {process.pid: launcher_birth, **trusted}
    observed = descendants(inventory(), roots)
    owned = []
    untrusted = []
    skipped = []
    for pid, row in observed.items():
        try:
            data = command(pid, row["identity"])
        except Exception as error:
            current = inventory().get(pid)
            if current is None or current["identity"] != row["identity"]:
                skipped.append(
                    {
                        "pid": pid,
                        "birth": row["identity"],
                        "reason": "vanished" if current is None else "changed_birth",
                    }
                )
                continue
            untrusted.append(
                {
                    **row,
                    "pid": pid,
                    "executable": None,
                    "argv": [],
                    "inspection_error_type": type(error).__name__,
                }
            )
            continue
        if not matching(data, expected, allowed_executables):
            untrusted.append(data)
            continue
        owned.append(data)

    # Kill verified interpreter descendants before the launcher can orphan them.
    def depth(row: dict[str, Any]) -> int:
        count = 0
        parent = row["parent"]
        while parent in observed:
            count += 1
            parent = observed[parent]["parent"]
        return count

    terminated = []
    termination_errors = []
    for row in sorted(owned, key=depth, reverse=True):
        try:
            terminate(row["pid"], row["identity"])
        except Exception as error:
            current = inventory().get(row["pid"])
            if current is None or current["identity"] != row["identity"]:
                skipped.append(
                    {
                        "pid": row["pid"],
                        "birth": row["identity"],
                        "reason": "vanished" if current is None else "changed_birth",
                    }
                )
            else:
                termination_errors.append(
                    {
                        "pid": row["pid"],
                        "birth": row["identity"],
                        "error_type": type(error).__name__,
                    }
                )
            continue
        terminated.append(row)
    if diagnostics is not None:
        diagnostics["skipped_before_cleanup"] = skipped
        diagnostics["termination_errors"] = termination_errors
        diagnostics["unmatched_observed"] = [
            {k: r[k] for k in ("pid", "identity", "parent", "executable")}
            | {
                "argv_sha256": hashlib.sha256(json.dumps(r["argv"]).encode()).hexdigest(),
                "inspection_error_type": r.get("inspection_error_type"),
            }
            for r in untrusted
        ]
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired as error:
        if diagnostics is not None:
            diagnostics["unverified_launcher_still_running"] = process.pid
        raise RuntimeError("Live unverified launcher preserved after verified cleanup") from error
    deadline = time.monotonic() + UNVERIFIED_DRAIN_SECONDS
    while untrusted and time.monotonic() < deadline:
        current = inventory()
        if not any(current.get(r["pid"], {}).get("identity") == r["identity"] for r in untrusted):
            break
        time.sleep(0.05)
    after = inventory()
    if any(after.get(r["pid"], {}).get("identity") == r["identity"] for r in owned):
        raise RuntimeError("Owned interpreter remained after exact cleanup")
    if any(after.get(r["pid"], {}).get("identity") == r["identity"] for r in untrusted):
        raise RuntimeError(
            "Unexpected descendant command preserved; verified owned processes drained"
        )
    if diagnostics is not None:
        diagnostics["unmatched_naturally_drained"] = bool(untrusted)
        diagnostics["remaining_owned"] = []
    return terminated


async def run(
    expected: list[str],
    plan: dict[str, Any],
    case: Path,
    allowed_executables: set[str],
    save: Any,
    plan_hash: str,
) -> dict[str, Any]:
    trusted: dict[int, Any] = {}
    process = None
    launcher_birth = None
    record: dict[str, Any] = {
        "status": "running",
        "expected_argv": expected,
        "plan_sha256": plan_hash,
    }
    try:
        with (
            (case / "child-stdout.log").open("xb") as output,
            (case / "child-stderr.log").open("xb") as errors,
        ):
            process = await asyncio.to_thread(
                subprocess.Popen,
                expected,
                stdout=output,
                stderr=errors,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            initial = inventory().get(process.pid)
            if initial is None:
                raise RuntimeError("Launcher creation identity unavailable")
            launcher_birth = initial["identity"]
            record["launcher"] = {"pid": process.pid, "birth": launcher_birth}
            save(case / "process-control.json", record)
            ready_path = Path(plan["ready"])
            deadline = time.monotonic() + 1800
            while not await asyncio.to_thread(ready_path.exists):
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("Owned worker did not reach readiness gate")
                await asyncio.to_thread(time.sleep, 0.05)
            ready = json.loads(await asyncio.to_thread(ready_path.read_bytes))
            tree = descendants(inventory(), {process.pid: launcher_birth})
            pid = ready["pid"]
            if (
                pid not in tree
                or tree[pid]["identity"] != ready["birth"]
                or ready["plan_sha256"] != plan_hash
            ):
                raise RuntimeError("Ready worker ancestry/birth/plan mismatch")
            worker = command(pid, ready["birth"])
            if not matching(worker, expected, allowed_executables):
                raise RuntimeError("Ready worker command or plan mismatch")
            trusted[pid] = ready["birth"]
            record["worker"] = worker
            save(
                Path(plan["start"]), {"pid": pid, "birth": ready["birth"], "plan_sha256": plan_hash}
            )
            marker_path = Path(plan["marker"])
            while not await asyncio.to_thread(marker_path.exists):
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("Owned worker did not reach native boundary")
                await asyncio.to_thread(time.sleep, 0.2)
            marker = json.loads(await asyncio.to_thread(marker_path.read_bytes))
            if (
                marker["pid"] != pid
                or marker["birth"] != ready["birth"]
                or marker["plan_sha256"] != plan_hash
            ):
                raise RuntimeError("Boundary marker process or plan mismatch")
            if marker["boundary"] != plan["boundary"]:
                raise RuntimeError("Boundary marker mismatch")
            current = command(pid, ready["birth"])
            if not matching(current, expected, allowed_executables):
                raise RuntimeError("Boundary worker command changed")
            record.update(status="passed", marker=marker)
            return marker
    except BaseException as error:
        record.update(status="failed", error_type=type(error).__name__)
        raise
    finally:
        try:
            if process is not None and launcher_birth is not None:
                record["terminated_exact"] = await asyncio.to_thread(
                    cleanup, process, launcher_birth, expected, allowed_executables, trusted, record
                )
                record["launcher_reaped"] = process.poll() is not None
            elif process is not None:
                # The child cannot claim before readiness/start authorization.
                # Without a birth proof, wait on our exact Popen handle for its
                # 60s bootstrap fuse plus headroom; never guess or kill a PID.
                record["unknown_launcher_birth"] = True
                try:
                    record["bootstrap_exit_code"] = await asyncio.to_thread(
                        process.wait, BOOTSTRAP_FUSE_HEADROOM_SECONDS
                    )
                except subprocess.TimeoutExpired as error:
                    record.update(bootstrap_fuse_exit=False, unverified_launcher_pid=process.pid)
                    raise RuntimeError("Unknown-birth launcher exceeded bootstrap fuse") from error
                record.update(bootstrap_fuse_exit=True, launcher_reaped=process.poll() is not None)
        except BaseException as error:
            record.update(status="failed", cleanup_error_type=type(error).__name__)
            raise
        finally:
            save(case / "process-control.json", record)
