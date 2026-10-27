"""Owned R8 evidence and resource sampling; never manages original services."""

import ctypes
import json
import os
import platform
import subprocess
import threading
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from pydantic import SecretStr

from marketlab.config import Settings
from marketlab.datasets.source import file_hash
from marketlab.research.service import execution_identity


@dataclass(frozen=True)
class ResourceProfile:
    name: str
    base: Path
    owner: str
    postgres_port: int
    redis_port: int
    ollama_port: int

    @property
    def ollama_url(self) -> str:
        return f"http://127.0.0.1:{self.ollama_port}"


def resource_profile(name: str = "legacy") -> ResourceProfile:
    profiles = {
        "legacy": ResourceProfile(
            "legacy", Path("artifacts/r8"), "r8-20261026", 55442, 56384, 11441
        ),
        "adoption-20261027": ResourceProfile(
            "adoption-20261027",
            Path("artifacts/r8-adoption-20261027"),
            "r8-adoption-20261027",
            55444,
            56386,
            11443,
        ),
    }
    if name not in profiles:
        raise ValueError("Unknown fixed R8 resource profile")
    return profiles[name]


PROFILE = resource_profile(os.environ.get("MARKETLAB_R8_PROFILE", "legacy"))
OWNER = PROFILE.owner
BASE = PROFILE.base
ROOT = Path("artifacts/r2/historical-storage").resolve()
MODEL = "qwen3.5:9b-q4_K_M"
DIGEST = "56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90"
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)


def command(args: list[str], timeout: float = 15) -> str:
    return subprocess.check_output(args, text=True, timeout=timeout, creationflags=NO_WINDOW)


def recorded(kind: str, base: Path = BASE) -> dict[str, Any]:
    value = json.loads((base / f"owned-{kind}.json").read_text(encoding="utf-8-sig"))
    return value[0] if isinstance(value, list) else value


def owned_settings(base: Path = BASE) -> Settings:
    if base.resolve() != PROFILE.base.resolve():
        raise RuntimeError("R8 evidence base does not match selected fixed profile")
    private = json.loads((base / "connection-private.json").read_text(encoding="utf-8-sig"))
    if private["owner"] != OWNER:
        raise RuntimeError("R8 owner mismatch")
    url = sa.engine.make_url(private["database_url"])
    if (url.host, url.port, url.database) != ("127.0.0.1", PROFILE.postgres_port, "marketlab"):
        raise RuntimeError("R8 requires inventoried disposable PostgreSQL")
    if private["redis_url"] != f"redis://127.0.0.1:{PROFILE.redis_port}/0":
        raise RuntimeError("R8 requires inventoried disposable Redis")
    if private.get("ollama_url") != PROFILE.ollama_url:
        raise RuntimeError("R8 requires owned Ollama endpoint")
    for kind, container_port, port in (
        ("postgres", "5432/tcp", str(PROFILE.postgres_port)),
        ("redis", "6379/tcp", str(PROFILE.redis_port)),
    ):
        row = recorded(kind, base)
        actual = json.loads(command(["docker", "inspect", row["Id"]]))[0]
        labels = actual["Config"].get("Labels") or {}
        if not (
            actual["Id"] == row["Id"]
            and actual["Name"] == row["Name"]
            and actual["Image"] == row["Image"]
            and actual["State"]["Running"]
            and labels.get("marketlab.r8.owner") == OWNER
            and actual["NetworkSettings"]["Ports"][container_port]
            == [{"HostIp": "127.0.0.1", "HostPort": port}]
        ):
            raise RuntimeError("R8 resource ownership mismatch")
    return Settings(
        database_url=SecretStr(private["database_url"]),
        database_password=None,
        redis_url=SecretStr(private["redis_url"]),
        ollama_url=PROFILE.ollama_url,
        storage_path=ROOT,
    )


def engine_for(settings: Settings) -> sa.Engine:
    return sa.create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)


def validate_prefix(prefix: str) -> str:
    """Bound paths and generated idempotency keys before any setup/mutation."""
    if (
        not isinstance(prefix, str)
        or not 4 <= len(prefix) <= 64
        or not prefix.startswith("r8-")
        or not all(c in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in prefix)
    ):
        raise ValueError("Invalid bounded lowercase r8- invocation prefix")
    return prefix


class Invocation(AbstractContextManager):
    """Create evidence exclusively; finalization never replaces an earlier run."""

    def __init__(self, prefix: str, phase: str, base: Path = BASE):
        prefix = validate_prefix(prefix)
        self.path = base / f"{prefix}-{phase}.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("x", encoding="utf-8") as stream:
            stream.write("{}")
        self.started = time.monotonic()
        self.data: dict[str, Any] = {
            "schema": "r8-evidence-v1",
            "status": "running",
            "phase": phase,
            "invocation": prefix,
            "resource_profile": PROFILE.name,
            "started_at": datetime.now(UTC).isoformat(),
            "execution": execution_identity(),
            "platform": platform.platform(),
            "lock_sha256": file_hash(Path("uv.lock")),
            "common_sha256": file_hash(Path(__file__)),
            "cases": [],
        }
        self.flush()

    def flush(self) -> None:
        self.data["seconds"] = time.monotonic() - self.started
        save(self.path, self.data)

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        if error is not None:
            self.data.update(status="failed", error_type=kind.__name__, error=str(error))
        elif execution_identity() != self.data["execution"]:
            self.data.update(
                status="failed",
                error_type="SourceDrift",
                error="Runtime source changed during invocation",
            )
        elif self.data["status"] == "running":
            self.data["status"] = "passed"
        self.flush()
        if error is None and self.data.get("error_type") == "SourceDrift":
            raise RuntimeError("Runtime source changed during invocation")
        return False


def processes() -> dict[int, dict[str, Any]]:
    """Native working set/RSS plus creation identity, without optional packages."""
    if os.name != "nt":
        result = {}
        for directory in Path("/proc").iterdir():
            if not directory.name.isdigit():
                continue
            try:
                raw = (directory / "stat").read_text()
                fields = raw[raw.rfind(")") + 2 :].split()
                result[int(directory.name)] = {
                    "parent": int(fields[1]),
                    "identity": fields[19],
                    "rss_bytes": int(fields[21]) * os.sysconf("SC_PAGE_SIZE"),
                }
            except (OSError, ValueError, IndexError):
                pass
        return result
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [
            ("size", wintypes.DWORD),
            ("usage", wintypes.DWORD),
            ("pid", wintypes.DWORD),
            ("heap", ctypes.c_size_t),
            ("module", wintypes.DWORD),
            ("threads", wintypes.DWORD),
            ("parent", wintypes.DWORD),
            ("priority", wintypes.LONG),
            ("flags", wintypes.DWORD),
            ("exe", wintypes.WCHAR * 260),
        ]

    class Memory(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
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

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Memory), wintypes.DWORD]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        raise OSError("Native process inventory unavailable")
    entry = Entry()
    entry.size = ctypes.sizeof(entry)
    result = {}
    try:
        more = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            handle = kernel.OpenProcess(0x1000 | 0x0010, False, entry.pid)
            if handle:
                try:
                    created, exited, cpu, user = (wintypes.FILETIME() for _ in range(4))
                    memory = Memory()
                    memory.cb = ctypes.sizeof(memory)
                    if kernel.GetProcessTimes(
                        handle,
                        ctypes.byref(created),
                        ctypes.byref(exited),
                        ctypes.byref(cpu),
                        ctypes.byref(user),
                    ) and psapi.GetProcessMemoryInfo(handle, ctypes.byref(memory), memory.cb):
                        result[int(entry.pid)] = {
                            "parent": int(entry.parent),
                            "identity": (created.dwHighDateTime << 32) | created.dwLowDateTime,
                            "rss_bytes": int(memory.working),
                            "private_bytes": int(memory.private),
                        }
                finally:
                    kernel.CloseHandle(handle)
            more = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    return result


def descendants(
    rows: dict[int, dict[str, Any]], roots: dict[int, Any]
) -> dict[int, dict[str, Any]]:
    selected = {
        pid for pid, identity in roots.items() if pid in rows and rows[pid]["identity"] == identity
    }
    while True:
        updated = selected | {
            pid
            for pid, value in rows.items()
            if value["parent"] in selected
            and int(value["identity"]) >= int(rows[value["parent"]]["identity"])
        }
        if updated == selected:
            return {pid: rows[pid] for pid in selected}
        selected = updated


def memory_bytes(value: str) -> int:
    units = {
        "B": 1,
        "kB": 1000,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "KiB": 1024,
        "MiB": 1024**2,
        "GiB": 1024**3,
        "TiB": 1024**4,
    }
    for unit in sorted(units, key=len, reverse=True):
        if value.endswith(unit):
            return int(float(value[: -len(unit)]) * units[unit])
    raise ValueError("Unrecognized Docker memory unit")


def gpu_windows(selected: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    """Read native WDDM per-process/per-adapter dedicated allocation via PDH."""
    import math
    import re
    from ctypes import wintypes

    class Value(ctypes.Structure):
        _fields_ = [("status", wintypes.DWORD), ("value", ctypes.c_double)]

    class Item(ctypes.Structure):
        _fields_ = [("name", wintypes.LPWSTR), ("formatted", Value)]

    pdh = ctypes.WinDLL("pdh", use_last_error=True)
    pdh.PdhOpenQueryW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.c_size_t,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    pdh.PdhAddEnglishCounterW.argtypes = [
        wintypes.HANDLE,
        wintypes.LPCWSTR,
        ctypes.c_size_t,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    pdh.PdhCollectQueryData.argtypes = [wintypes.HANDLE]
    pdh.PdhGetFormattedCounterArrayW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    pdh.PdhCloseQuery.argtypes = [wintypes.HANDLE]
    query, counter = wintypes.HANDLE(), wintypes.HANDLE()
    if pdh.PdhOpenQueryW(None, 0, ctypes.byref(query)):
        raise OSError("PDH query unavailable")
    try:
        path = r"\GPU Process Memory(*)\Dedicated Usage"
        if pdh.PdhAddEnglishCounterW(query, path, 0, ctypes.byref(counter)):
            raise OSError("WDDM dedicated-memory counter unavailable")
        if pdh.PdhCollectQueryData(query):
            raise OSError("WDDM dedicated-memory collection unavailable")
        size, count = wintypes.DWORD(), wintypes.DWORD()
        pdh.PdhGetFormattedCounterArrayW(
            counter, 0x200, ctypes.byref(size), ctypes.byref(count), None
        )
        if not size.value:
            raise OSError("WDDM dedicated-memory counter returned no data")
        buffer = ctypes.create_string_buffer(size.value)
        if pdh.PdhGetFormattedCounterArrayW(
            counter, 0x200, ctypes.byref(size), ctypes.byref(count), buffer
        ):
            raise OSError("WDDM formatted memory unavailable")
        values = ctypes.cast(buffer, ctypes.POINTER(Item))
        after = processes()
        result = []
        seen = set()
        for index in range(count.value):
            item = values[index]
            match = re.match(r"pid_([0-9]+)_", item.name)
            if not match:
                continue
            pid = int(match[1])
            if (
                pid not in selected
                or pid not in after
                or after[pid]["identity"] != selected[pid]["identity"]
            ):
                continue
            if item.formatted.status not in {0, 1}:
                raise OSError("WDDM owned-process counter status invalid")
            if not math.isfinite(item.formatted.value) or item.formatted.value < 0:
                raise OSError("Invalid WDDM dedicated-memory value")
            if item.name in seen:
                raise OSError("Duplicate WDDM adapter instance")
            seen.add(item.name)
            result.append(
                {
                    "pid": pid,
                    "birth": selected[pid]["identity"],
                    "adapter_instance": item.name,
                    "dedicated_bytes": int(item.formatted.value),
                }
            )
        return result
    finally:
        pdh.PdhCloseQuery(query)


def nvidia_allocations(
    lines: list[str], selected: dict[int, dict[str, Any]], after: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Validate numeric NVIDIA MiB by owned PID birth and distinct GPU UUID."""
    import math

    result = []
    seen = set()
    for line in lines:
        pid_text, adapter, value = (part.strip() for part in line.split(","))
        pid = int(pid_text)
        if (
            pid not in selected
            or pid not in after
            or after[pid]["identity"] != selected[pid]["identity"]
        ):
            raise ValueError("GPU process birth unavailable/changed")
        number = float(value)
        if not math.isfinite(number) or number < 0 or not adapter or (pid, adapter) in seen:
            raise ValueError("Invalid/duplicate numeric GPU allocation")
        seen.add((pid, adapter))
        result.append(
            {
                "pid": pid,
                "birth": selected[pid]["identity"],
                "adapter_uuid": adapter,
                "allocated_bytes": int(number * 1024**2),
            }
        )
    if not result:
        raise ValueError("No owned numeric GPU allocation observations")
    return result


class Sampler(AbstractContextManager):
    """Sample host descendants, owned cgroup usage and separate GPU observations.

    Sampled maxima are lower bounds. The aggregate mixes host working sets and
    cgroup accounting and can include shared pages; per-sample skew is retained.
    """

    def __init__(
        self,
        output: Path,
        *,
        model: bool = False,
        containers: bool = True,
        interval: float = 1.0,
        roots: dict[int, Any] | None = None,
    ):
        self.output, self.interval = output, interval
        rows = processes()
        explicit_roots = roots or {}
        roots = [os.getpid()]
        if model:
            owned = recorded("ollama")
            pid = int(owned["pid"])
            if pid not in rows:
                raise RuntimeError("Owned model process is absent")
            actual_birth = rows[pid]["identity"] / 10000000 - 11644473600
            saved_birth = datetime.fromisoformat(owned["creation_time"]).timestamp()
            if abs(actual_birth - saved_birth) > 0.001:
                raise RuntimeError("Owned model PID creation identity changed")
            roots.append(pid)
        self.roots = {pid: rows[pid]["identity"] for pid in roots}
        for pid, identity in explicit_roots.items():
            if pid not in rows or rows[pid]["identity"] != identity:
                raise RuntimeError("Explicit sampled process birth identity changed")
            self.roots[pid] = identity
        self.containers = (
            [recorded(kind)["Id"] for kind in ("postgres", "redis")] if containers else []
        )
        self.samples: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def sample(self) -> None:
        began = time.monotonic()
        inventory = processes()
        selected = descendants(inventory, self.roots)
        missing_roots = [
            pid
            for pid, birth in self.roots.items()
            if pid not in inventory or inventory[pid]["identity"] != birth
        ]
        item: dict[str, Any] = {
            "monotonic": began,
            "processes": selected,
            "missing_roots": missing_roots,
        }
        item["process_working_set_bytes"] = sum(row["rss_bytes"] for row in selected.values())
        try:
            if self.containers:
                stats = {}
                for identity in self.containers:
                    raw = command(
                        [
                            "docker",
                            "exec",
                            identity,
                            "sh",
                            "-c",
                            "if [ -r /sys/fs/cgroup/memory.current ]; then printf 'v2 ' ; "
                            "cat /sys/fs/cgroup/memory.current; "
                            "elif [ -r /sys/fs/cgroup/memory/memory.usage_in_bytes ]; then "
                            "printf 'v1 ' ; "
                            "cat /sys/fs/cgroup/memory/memory.usage_in_bytes; else exit 7; fi",
                        ],
                        timeout=5,
                    )
                    version, number = raw.strip().split()
                    if version not in {"v1", "v2"}:
                        raise RuntimeError("Unsupported cgroup memory accounting")
                    stats[identity] = int(number)
                    item.setdefault("container_accounting", {})[identity] = version
                if set(stats) != set(self.containers):
                    raise RuntimeError("Incomplete container resource inventory")
                item["containers"] = stats
                item["container_bytes"] = sum(stats.values())
                item["aggregate_bytes"] = (
                    item["process_working_set_bytes"] + item["container_bytes"]
                )
            else:
                item["aggregate_bytes"] = item["process_working_set_bytes"]
        except Exception as error:
            item["container_error"] = type(error).__name__
        try:
            raw = command(
                [
                    "nvidia-smi",
                    "--query-compute-apps=pid,gpu_uuid,used_gpu_memory",
                    "--format=csv,noheader,nounits",
                ],
                timeout=5,
            )
            item["gpu"] = [
                line
                for line in raw.splitlines()
                if line.split(",")[0].strip().isdigit() and int(line.split(",")[0]) in selected
            ]
        except (OSError, subprocess.SubprocessError):
            item["gpu"] = "unavailable"
        item["gpu_status"] = (
            "measured"
            if isinstance(item.get("gpu"), list)
            and item["gpu"]
            and all("N/A" not in row for row in item["gpu"])
            else "unavailable"
        )
        if item["gpu_status"] == "measured":
            try:
                item["gpu_nvidia"] = nvidia_allocations(item["gpu"], selected, processes())
                item["gpu_dedicated_bytes"] = sum(
                    row["allocated_bytes"] for row in item["gpu_nvidia"]
                )
                item["gpu_status"] = "measured_nvidia_process_allocation"
            except Exception as error:
                item.update(gpu_status="unavailable", gpu_nvidia_error=type(error).__name__)
        if os.name == "nt" and item["gpu_status"] == "unavailable":
            try:
                item["gpu_wddm"] = gpu_windows(selected)
                if not item["gpu_wddm"]:
                    raise OSError("No enrolled WDDM GPU process counters")
                item["gpu_status"] = "measured_wddm_dedicated_allocation"
                item["gpu_dedicated_bytes"] = sum(
                    row["dedicated_bytes"] for row in item["gpu_wddm"]
                )
            except Exception as error:
                item["gpu_wddm_error"] = type(error).__name__
        item["complete_cpu_sample"] = not missing_roots and "aggregate_bytes" in item
        item["sample_span_seconds"] = time.monotonic() - began
        self.samples.append(item)

    def _loop(self) -> None:
        while not self.stop.is_set():
            began = time.monotonic()
            try:
                self.sample()
            except Exception as error:
                self.errors.append({"monotonic": began, "error": type(error).__name__})
            self.stop.wait(max(0, self.interval - (time.monotonic() - began)))

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, kind, error, traceback):
        self.stop.set()
        self.thread.join(timeout=20)
        if self.thread.is_alive():
            raise RuntimeError("Resource sampler did not stop")
        complete = [row for row in self.samples if row.get("complete_cpu_sample")]
        peaks: dict[str, int] = {}
        for sample in self.samples:
            for pid, row in sample["processes"].items():
                key = f"{pid}:{row['identity']}"
                peaks[key] = max(peaks.get(key, 0), row["rss_bytes"])
        save(
            self.output,
            {
                "schema": "r8-sampled-resources-v1",
                "status": "measured"
                if len(complete) == len(self.samples) and len(complete) >= 2 and not self.errors
                else "incomplete",
                "cpu_coverage_complete": len(complete) == len(self.samples)
                and len(complete) >= 2
                and not self.errors,
                "actual_sample_spacing_seconds": [
                    b["monotonic"] - a["monotonic"]
                    for a, b in zip(self.samples, self.samples[1:], strict=False)
                ],
                "requested_interval_seconds": self.interval,
                "samples": self.samples,
                "errors": self.errors,
                "roots": self.roots,
                "container_ids": self.containers,
                "process_observed_peaks_bytes": peaks,
                "gpu_dedicated_sampled_maximum_bytes": max(
                    (
                        row["gpu_dedicated_bytes"]
                        for row in self.samples
                        if "gpu_dedicated_bytes" in row
                    ),
                    default=None,
                ),
                "gpu_coverage_complete": bool(self.samples)
                and all(row["gpu_status"].startswith("measured") for row in self.samples),
                "aggregate_sampled_maximum_bytes": max(
                    (row["aggregate_bytes"] for row in complete), default=None
                ),
                "limitation": "Sampled lower bound; sample_span is timing skew. Time-skewed host working sets plus cgroup v1 usage_in_bytes/v2 memory.current mix scopes/shared pages; GPU separate and unavailable on WDDM is explicit. No true peak or physical-memory exclusivity claim.",  # noqa: E501
            },
        )
        if error is None and (
            len(complete) != len(self.samples) or len(complete) < 2 or self.errors
        ):
            raise RuntimeError("Mandatory CPU/process/container memory coverage incomplete")
        return False
