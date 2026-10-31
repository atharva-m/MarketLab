"""Bounded local native-process birth checks for conservative admission recovery."""

import ctypes
import hashlib
import json
import os
import platform
import re
from pathlib import Path
from typing import Any

from .common import V2Error, canonical_json


def _linux_text(path: str) -> str:
    with Path(path).open("r", encoding="ascii") as stream:
        value = stream.read(4097)
    if len(value) > 4096:
        raise OSError("Native proc identity exceeds its bound")
    return value.strip()


def _linux_stat(value: str, expected_pid: int) -> tuple[int, str]:
    left, right = value.find("("), value.rfind(")")
    if left < 1 or right <= left or value[:left].strip() != str(expected_pid):
        raise OSError("Native proc PID identity mismatch")
    fields = value[right + 2 :].split()
    if (
        len(fields) < 20
        or not re.fullmatch(r"[A-Za-z]", fields[0])
        or not re.fullmatch(r"[0-9]{1,10}", fields[1])
        or not re.fullmatch(r"[1-9][0-9]{0,19}", fields[19])
        or int(fields[19]) >= 2**64
    ):
        raise OSError("Native proc birth identity malformed")
    return int(fields[1]), fields[19]


def _linux_host_boot() -> tuple[str, str]:
    boot = _linux_text("/proc/sys/kernel/random/boot_id")
    if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", boot):
        raise OSError("Native boot identity malformed")
    if boot.replace("-", "") == "0" * 32:
        raise OSError("Native boot identity unavailable")
    namespace = os.readlink("/proc/self/ns/pid")
    if (
        not re.fullmatch(r"pid:\[[1-9][0-9]{0,19}\]", namespace)
        or int(namespace[5:-1]) >= 2**64
        or namespace != os.readlink("/proc/1/ns/pid")
    ):
        raise OSError("Native proc PID namespace mismatch")
    _linux_stat(_linux_text("/proc/self/stat"), os.getpid())
    _, birth = _linux_stat(_linux_text("/proc/1/stat"), 1)
    try:
        machine = _linux_text("/etc/machine-id")
    except OSError:
        machine = ""
    machine_id = machine.lower() if re.fullmatch(r"[0-9a-fA-F]{32}", machine) else None
    identity = {
        "schema": "marketlab-linux-process-domain-v1",
        "boot_id": boot,
        "pid_namespace": namespace,
        "namespace_init_birth": birth,
        "machine_id": machine_id,
    }
    return hashlib.sha256(canonical_json(identity)).hexdigest()[:32], boot


def _host_boot() -> tuple[str, str]:
    if os.name == "nt":
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            host = str(winreg.QueryValueEx(key, "MachineGuid")[0])
        buffer = ctypes.create_string_buffer(64)
        length = ctypes.c_ulong()
        status = ctypes.windll.ntdll.NtQuerySystemInformation(
            90, buffer, len(buffer), ctypes.byref(length)
        )
        if status != 0 or length.value < 16:
            raise OSError("Native boot identity unavailable")
        return host, bytes(buffer.raw[:16]).hex()
    return _linux_host_boot()


def _process(pid: int) -> dict[str, str] | None:
    if os.name != "nt":
        try:
            raw = Path(f"/proc/{pid}/stat").read_text()
        except FileNotFoundError:
            return None  # Direct lookup of this exact PID, never enumeration.
        _, birth = _linux_stat(raw, pid)
        fields = raw[raw.rfind(")") + 2 :].split()
        if fields[0] == "Z":
            return None
        if os.readlink(f"/proc/{pid}/ns/pid") != os.readlink("/proc/self/ns/pid"):
            raise OSError("Native process is in a foreign PID namespace")
        return {"birth": birth, "executable": os.readlink(f"/proc/{pid}/exe")}
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:
            return None
        raise OSError(error, "Native process query unavailable")
    try:
        exit_code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            raise OSError("Native process query unavailable")
        if exit_code.value != 259:
            return None
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(v) for v in times)):
            raise OSError("Native process birth unavailable")
        value = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        name = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(name))
        if not kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size)):
            raise OSError("Native image unavailable")
        return {"birth": str(value), "executable": str(Path(name.value).resolve())}
    finally:
        kernel.CloseHandle(handle)


def current() -> dict[str, Any]:
    try:
        host, boot = _host_boot()
        process = _process(os.getpid())
        if process is None or not host or not boot:
            raise OSError("Native identity unavailable")
        return dict(process, host=host, boot=boot, pid=os.getpid(), platform=platform.system())
    except (OSError, ValueError, IndexError) as error:
        raise V2Error("unavailable", "Native admission identity unavailable") from error


def child(pid: int) -> dict[str, Any]:
    """Independently birth-check one public pool PID and its direct parent."""
    if type(pid) is not int or not 0 < pid <= 2**32 - 1:
        raise V2Error("unavailable", "Invalid native child identity")
    try:
        before = _process(pid)
        if before is None:
            raise OSError("Owned child has exited")
        if os.name != "nt":
            raw = Path(f"/proc/{pid}/stat").read_text()
            parent = int(raw[raw.rfind(")") + 2 :].split()[1])
        else:
            from ctypes import wintypes

            class Basic(ctypes.Structure):
                _fields_ = [
                    ("reserved", ctypes.c_void_p),
                    ("peb", ctypes.c_void_p),
                    ("reserved2", ctypes.c_void_p * 2),
                    ("pid", ctypes.c_size_t),
                    ("parent", ctypes.c_size_t),
                ]

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.OpenProcess(0x1000, False, pid)
            if not handle:
                raise OSError("Owned child ancestry unavailable")
            try:
                basic = Basic()
                query = ctypes.WinDLL("ntdll").NtQueryInformationProcess
                query.argtypes = [
                    wintypes.HANDLE,
                    wintypes.DWORD,
                    ctypes.c_void_p,
                    wintypes.ULONG,
                    ctypes.c_void_p,
                ]
                if query(handle, 0, ctypes.byref(basic), ctypes.sizeof(basic), None) != 0:
                    raise OSError("Owned child ancestry unavailable")
                parent = basic.parent
            finally:
                kernel.CloseHandle(handle)
        if parent != os.getpid() or before != _process(pid):
            raise OSError("Owned child ancestry or birth changed")
        host, boot = _host_boot()
        identity = dict(before, pid=pid, host=host, boot=boot, platform=platform.system())
        if not valid(identity) or identity["executable"] != current()["executable"]:
            raise OSError("Owned child executable mismatch")
        return identity
    except (OSError, ValueError, IndexError) as error:
        raise V2Error("unavailable", "Owned child native identity unavailable") from error


def dead(identity: dict[str, Any]) -> bool:
    """Unknown/foreign/malformed identity never establishes death."""
    try:
        if set(identity) != {"host", "boot", "pid", "platform", "birth", "executable"}:
            return False
        if type(identity["pid"]) is not int or not 0 < identity["pid"] <= 2**32 - 1:
            return False
        if not valid(identity):
            return False
        host, boot = _host_boot()
        if identity["host"] != host or identity["platform"] != platform.system():
            return False
        if identity["boot"] != boot:
            return bool(identity["platform"] == "Windows")
        process = _process(identity["pid"])
        return process is None or process["birth"] != identity["birth"]
    except (OSError, ValueError, IndexError, KeyError, TypeError):
        return False


def same(identity: dict[str, Any]) -> bool:
    return valid(identity) and canonical_json(identity) == canonical_json(current())


def alive(identity: dict[str, Any]) -> bool:
    try:
        if not valid(identity):
            return False
        host, boot = _host_boot()
        if identity["host"] != host or identity["boot"] != boot:
            return False
        process = _process(identity["pid"])
        return process is not None and process == {
            "birth": identity["birth"],
            "executable": identity["executable"],
        }
    except (OSError, ValueError, IndexError, KeyError, TypeError):
        return False


def rebooted(identity: dict[str, Any]) -> bool:
    try:
        if not valid(identity):
            return False
        if identity["platform"] == "Linux":
            return False  # A new Linux domain is foreign, never an inferred reboot/death.
        host, boot = _host_boot()
        return bool(host == identity["host"] and boot != identity["boot"])
    except (OSError, ValueError):
        return False


def valid(identity: dict[str, Any]) -> bool:
    if set(identity) != {"host", "boot", "pid", "platform", "birth", "executable"}:
        return False
    if type(identity["pid"]) is not int or not 0 < identity["pid"] <= 2**32 - 1:
        return False
    if identity["platform"] not in {"Windows", "Linux"}:
        return False
    for field in ("host", "boot", "birth", "executable"):
        if not isinstance(identity[field], str):
            return False
    host, boot, birth, executable = (identity[k] for k in ("host", "boot", "birth", "executable"))
    if not re.fullmatch(
        r"(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})", host
    ):
        return False
    if not re.fullmatch(
        r"(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})", boot
    ):
        return False
    if not re.fullmatch(r"[1-9][0-9]{0,19}", birth) or int(birth) >= 2**64:
        return False
    return (
        0 < len(executable) <= 32768 and "\x00" not in executable and Path(executable).is_absolute()
    )


def decode(value: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(value)
    return result
