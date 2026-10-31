"""Owned Windows processes: contain before resume, retain handles, wait, and drain."""

from __future__ import annotations

import ctypes
import os
import subprocess
import time
from ctypes import wintypes as W
from pathlib import Path
from typing import Any


class Security(ctypes.Structure):
    _fields_ = [("length", W.DWORD), ("descriptor", W.LPVOID), ("inherit", W.BOOL)]


class Startup(ctypes.Structure):
    _fields_ = [
        ("cb", W.DWORD),
        ("reserved", W.LPWSTR),
        ("desktop", W.LPWSTR),
        ("title", W.LPWSTR),
        *[
            (name, W.DWORD)
            for name in ("x", "y", "xsize", "ysize", "xchars", "ychars", "fill", "flags")
        ],
        ("show", W.WORD),
        ("reserved_size", W.WORD),
        ("reserved_bytes", ctypes.POINTER(W.BYTE)),
        ("stdin", W.HANDLE),
        ("stdout", W.HANDLE),
        ("stderr", W.HANDLE),
    ]


class ProcessInfo(ctypes.Structure):
    _fields_ = [("process", W.HANDLE), ("thread", W.HANDLE), ("pid", W.DWORD), ("tid", W.DWORD)]


class BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_int64),
        ("job_time", ctypes.c_int64),
        ("flags", W.DWORD),
        ("minimum_working", ctypes.c_size_t),
        ("maximum_working", ctypes.c_size_t),
        ("active_limit", W.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority", W.DWORD),
        ("scheduling", W.DWORD),
    ]


class IO(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_uint64)
        for name in (
            "read_ops",
            "write_ops",
            "other_ops",
            "read_bytes",
            "write_bytes",
            "other_bytes",
        )
    ]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", BasicLimits),
        ("io", IO),
        *[
            (name, ctypes.c_size_t)
            for name in ("process_memory", "job_memory", "peak_process_memory", "peak_job_memory")
        ],
    ]


class Accounting(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_int64) for name in ("user", "kernel", "period_user", "period_kernel")
    ] + [(name, W.DWORD) for name in ("page_faults", "total", "active", "terminated")]


class Memory(ctypes.Structure):
    _fields_ = [("cb", W.DWORD), ("faults", W.DWORD)] + [
        (name, ctypes.c_size_t)
        for name in (
            "peak_working",
            "working",
            "peak_paged",
            "paged",
            "peak_nonpaged",
            "nonpaged",
            "pagefile",
            "peak_pagefile",
            "private",
        )
    ]


def supervisor_peak_commit() -> int:
    """Measure this bootstrap's own lifetime peak committed memory without a PID query."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = W.HANDLE
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [W.HANDLE, ctypes.POINTER(Memory), W.DWORD]
    info = Memory()
    info.cb = ctypes.sizeof(info)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(info), info.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    if not info.peak_pagefile:
        raise OSError("Supervisor peak committed memory is unavailable")
    return int(info.peak_pagefile)


class OwnedJob:
    """A private non-breakaway group containing only roots created by this object."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("Phase 4 local acceptance requires Windows Job containment")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.handle: Any = None
        self.children: list[OwnedChild] = []
        k = self.kernel
        k.CreateJobObjectW.argtypes = [W.LPVOID, W.LPCWSTR]
        k.CreateJobObjectW.restype = W.HANDLE
        k.SetInformationJobObject.argtypes = [W.HANDLE, ctypes.c_int, W.LPVOID, W.DWORD]
        k.QueryInformationJobObject.argtypes = [
            W.HANDLE,
            ctypes.c_int,
            W.LPVOID,
            W.DWORD,
            ctypes.POINTER(W.DWORD),
        ]
        k.AssignProcessToJobObject.argtypes = [W.HANDLE, W.HANDLE]
        k.TerminateJobObject.argtypes = [W.HANDLE, W.UINT]
        k.CreateProcessW.argtypes = [
            W.LPCWSTR,
            W.LPWSTR,
            W.LPVOID,
            W.LPVOID,
            W.BOOL,
            W.DWORD,
            W.LPVOID,
            W.LPCWSTR,
            ctypes.POINTER(Startup),
            ctypes.POINTER(ProcessInfo),
        ]
        k.ResumeThread.argtypes = [W.HANDLE]
        k.ResumeThread.restype = W.DWORD
        k.TerminateProcess.argtypes = [W.HANDLE, W.UINT]
        k.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
        k.WaitForSingleObject.restype = W.DWORD
        k.GetExitCodeProcess.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD)]
        k.GetProcessTimes.argtypes = [W.HANDLE, *([ctypes.POINTER(W.FILETIME)] * 4)]
        k.CloseHandle.argtypes = [W.HANDLE]
        k.CreateFileW.argtypes = [
            W.LPCWSTR,
            W.DWORD,
            W.DWORD,
            ctypes.POINTER(Security),
            W.DWORD,
            W.DWORD,
            W.HANDLE,
        ]
        k.CreateFileW.restype = W.HANDLE
        self.handle = k.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE; no breakaway.
        if not k.SetInformationJobObject(
            self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def _query(self, kind: int, info: Any) -> Any:
        if not self.handle:
            raise OSError("Owned Job is closed")
        used = W.DWORD()
        if not self.kernel.QueryInformationJobObject(
            self.handle, kind, ctypes.byref(info), ctypes.sizeof(info), ctypes.byref(used)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if used.value != ctypes.sizeof(info):
            raise OSError("Malformed Job accounting response")
        return info

    def active(self) -> int:
        return int(self._query(1, Accounting()).active)

    def peak_commit(self) -> int:
        return int(self._query(9, ExtendedLimits()).peak_job_memory)

    def spawn(self, argv: list[str], *, cwd: Path, env: dict[str, str], output: Any) -> OwnedChild:
        import msvcrt

        if not argv or not Path(argv[0]).is_absolute() or not Path(argv[0]).is_file():
            raise ValueError("Owned launch requires an absolute executable file")
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
        environment = ctypes.create_unicode_buffer(
            "\0".join(
                f"{key}={value}"
                for key, value in sorted(env.items(), key=lambda item: item[0].upper())
            )
            + "\0\0"
        )
        startup = Startup()
        startup.cb = ctypes.sizeof(startup)
        startup.flags = 0x100
        info = ProcessInfo()
        security = Security(ctypes.sizeof(Security), None, True)
        nul = self.kernel.CreateFileW("NUL", 0x80000000, 3, ctypes.byref(security), 3, 0x80, None)
        if not nul or nul == W.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        out_handle = msvcrt.get_osfhandle(output.fileno())
        inherited = os.get_handle_inheritable(out_handle)
        resumed = False
        child = None
        try:
            os.set_handle_inheritable(out_handle, True)
            startup.stdin, startup.stdout, startup.stderr = nul, out_handle, out_handle
            flags = 0x4 | 0x08000000 | 0x400  # SUSPENDED | NO_WINDOW | UNICODE_ENVIRONMENT
            if not self.kernel.CreateProcessW(
                argv[0],
                command,
                None,
                None,
                True,
                flags,
                environment,
                str(cwd),
                ctypes.byref(startup),
                ctypes.byref(info),
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            if not self.kernel.AssignProcessToJobObject(self.handle, info.process):
                raise ctypes.WinError(ctypes.get_last_error())
            child = OwnedChild(self, info.process, int(info.pid), argv)
            self.children.append(child)
            if self.kernel.ResumeThread(info.thread) != 1:
                raise OSError("Owned process could not resume")
            resumed = True
            return child
        finally:
            os.set_handle_inheritable(out_handle, inherited)
            self._close_handle(nul)
            if info.thread:
                self._close_handle(info.thread)
            if info.process and not resumed:
                if not self.kernel.TerminateProcess(info.process, 91):
                    raise ctypes.WinError(ctypes.get_last_error())
                if self.kernel.WaitForSingleObject(info.process, 15000) != 0:
                    raise TimeoutError("Unstarted owned process did not terminate")
                if child is None:
                    self._close_handle(info.process)

    def wait_empty(self, timeout: float = 30) -> None:
        deadline = time.monotonic() + timeout
        while self.active():
            if time.monotonic() >= deadline:
                raise TimeoutError("Owned Job did not drain")
            time.sleep(0.05)

    def terminate(self) -> None:
        if not self.kernel.TerminateJobObject(self.handle, 91):
            raise ctypes.WinError(ctypes.get_last_error())
        self.wait_empty(15)

    def _close_handle(self, handle: Any) -> None:
        if not self.kernel.CloseHandle(handle):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        errors = []
        for child in self.children:
            if child.handle:
                try:
                    self._close_handle(child.handle)
                    child.handle = None
                except OSError as error:
                    errors.append(error)
        if self.handle:
            try:
                self._close_handle(self.handle)
                self.handle = None
            except OSError as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup("Owned handle close failed", errors)


class OwnedChild:
    def __init__(self, job: OwnedJob, handle: Any, pid: int, argv: list[str]) -> None:
        self.job, self.handle, self.pid, self.argv = job, handle, pid, argv
        self.returncode: int | None = None
        creation, exit_time, kernel, user = (W.FILETIME() for _ in range(4))
        if not job.kernel.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        self.birth = (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)

    def poll(self) -> int | None:
        if self.returncode is not None:
            return self.returncode
        result = self.job.kernel.WaitForSingleObject(self.handle, 0)
        if result == 258:
            return None
        if result != 0:
            raise OSError("Owned process wait failed")
        code = W.DWORD()
        if not self.job.kernel.GetExitCodeProcess(self.handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.returncode = int(code.value)
        return self.returncode

    def wait(self, timeout: float = 30) -> int:
        deadline = time.monotonic() + timeout
        while self.poll() is None:
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(self.argv, timeout)
            time.sleep(0.05)
        return int(self.returncode)

    def record(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "birth": str(self.birth),
            "argv": self.argv,
            "exit_code": self.poll(),
        }
