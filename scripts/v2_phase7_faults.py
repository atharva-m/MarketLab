"""Owned Phase 7 fault primitives and prepared-job adapter.

Only an explicit frozen host binding may dispatch work. Faults are installed in
the private acceptance child, never through production environment switches.
Receipts retain actual ledger observations; execution never marks acceptance.
"""

from __future__ import annotations

import asyncio
import ctypes
import importlib.util
import json
import os
import re
import select
import signal
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
KINDS = {"ingestion", "research", "copilot", "memo"}
BOUNDARIES = {
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
}


def load_runner() -> Any:
    spec = importlib.util.spec_from_file_location(
        "phase7_acceptance_transport", ROOT / "scripts/v2_phase7_acceptance.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def safe_folder(root: Path, request_id: str) -> Path:
    UUID(request_id)
    root = root.absolute()
    if any(p.is_symlink() or p.is_junction() for p in (root, *root.parents)):
        raise ValueError("Linked evidence root rejected")
    if not root.is_dir():
        raise ValueError("Existing owned evidence root required")
    result = root / request_id
    result.mkdir(exist_ok=False)
    return result


def write_once(path: Path, value: Any) -> None:
    from marketlab.datasets.v2.common import canonical_json
    from marketlab.datasets.v2.core import wire

    raw = canonical_json(wire(value))
    if len(raw) > 65536:
        raise ValueError("Fault marker exceeds bound")
    temporary = path.with_suffix(".pending")
    with temporary.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.link(temporary, path, follow_symlinks=False)
    temporary.unlink()


def worker_arguments(
    kind: str, target: str, root_id: str, compact_sha256: str | None = None
) -> list[str]:
    if kind not in KINDS:
        raise ValueError("Unsupported prepared worker kind")
    UUID(target)
    UUID(root_id)
    module = {
        "ingestion": "dataset_cli",
        "research": "research_cli",
        "copilot": "copilot_cli",
        "memo": "memo_cli",
    }[kind]
    arguments = [
        f"marketlab.{module}",
        "v2",
        "worker",
        "--worker-root",
        root_id,
        "--max-runs" if kind == "research" else "--max-jobs",
        "1",
        "--wait-seconds",
        "0",
    ]
    arguments += [
        {"ingestion": "--submission", "research": "--run", "copilot": "--request", "memo": "--run"}[
            kind
        ],
        target,
    ]
    if compact_sha256 is not None:
        flags = {"ingestion": "--compact-official-sha256", "research": "--compact-fingerprint"}
        if kind not in flags or re.fullmatch(r"[a-f0-9]{64}", compact_sha256) is None:
            raise ValueError("Invalid compact worker source binding")
        arguments.extend([flags[kind], compact_sha256])
    return arguments


def require_budget(packet: dict[str, Any], count: int) -> None:
    remaining = packet.get("jobs_remaining")
    if type(remaining) is not int or not count <= remaining <= 62:
        raise ValueError("Insufficient bounded dispatch budget before any job starts")


class DispatchBudget:
    def __init__(self, packet: dict[str, Any], reserved: int) -> None:
        require_budget(packet, reserved)
        self.reserved = reserved
        self.started = 0
        self.lock = threading.Lock()

    def start(self) -> None:
        with self.lock:
            if self.started >= self.reserved:
                raise ValueError("Claiming invocation budget exhausted")
            self.started += 1

    def receipt(self) -> dict[str, int]:
        return {"dispatches_reserved": self.reserved, "dispatches_started": self.started}


def verify_peer(packet: dict[str, Any], peer: dict[str, Any]) -> None:
    allowed = packet.get("allowed_hosts")
    if not isinstance(allowed, list) or len(allowed) != 2:
        raise ValueError("Frozen two-host transport allowlist required")
    if not any(
        all(peer.get(key) == host.get(key) for key in ("host_id", "ssh_target")) for host in allowed
    ):
        raise ValueError("Peer is outside the frozen two-host transport allowlist")


def wait_due(engine: Any, kind: str, job_id: str, seconds: float) -> None:
    from marketlab.datasets.v2.core import execute

    ident = "job_id" if kind in {"ingestion", "copilot"} else "run_id"
    table = "v2_research_runs" if kind == "research" else f"v2_{kind}_jobs"
    deadline = time.monotonic() + min(75, seconds)
    while True:
        with engine.connect() as connection:
            due = execute(
                connection,
                f"SELECT state NOT IN ('running','retry_wait') OR "
                "(state='running' AND lease_until<=clock_timestamp()) OR "
                f"(state='retry_wait' AND eligible_at<=clock_timestamp()) FROM {table} "
                f"WHERE {ident}=:id",
                id=job_id,
            ).scalar_one()
        if due:
            return
        if time.monotonic() >= deadline:
            raise TimeoutError("Unchanged durable eligibility deadline did not elapse")
        time.sleep(0.1)


class Relay:
    """Bounded opaque TCP cut; no payload logging, server configuration or deletion."""

    def __init__(self, host: str, port: int) -> None:
        if not host or type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("Explicit relay endpoint required")
        self.target = host, port
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(16)
        self.listener.settimeout(0.1)
        self.port = self.listener.getsockname()[1]
        self.stop = threading.Event()
        self.cut = threading.Event()
        self.connections: set[socket.socket] = set()
        self.lock = threading.Lock()
        self.children: list[threading.Thread] = []
        self.accepted = 0
        self.forwarded = 0
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                client, _ = self.listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            if self.cut.is_set() or self.accepted >= 32:
                client.close()
                continue
            self.accepted += 1
            thread = threading.Thread(target=self.forward, args=(client,), daemon=True)
            self.children.append(thread)
            thread.start()

    def forward(self, client: socket.socket) -> None:
        upstream = None
        try:
            upstream = socket.create_connection(self.target, timeout=5)
            with self.lock:
                self.connections.update((client, upstream))
            for channel in (client, upstream):
                channel.setblocking(False)
            deadline = time.monotonic() + 1800
            while not self.stop.is_set() and not self.cut.is_set() and time.monotonic() < deadline:
                readable, _, _ = select.select([client, upstream], [], [], 0.1)
                for source in readable:
                    data = source.recv(65536)
                    if not data:
                        return
                    destination = upstream if source is client else client
                    pending = memoryview(data)
                    send_deadline = time.monotonic() + 5
                    while pending:
                        if (
                            self.stop.is_set()
                            or self.cut.is_set()
                            or time.monotonic() >= send_deadline
                        ):
                            return
                        if select.select([], [destination], [], 0.1)[1]:
                            pending = pending[destination.send(pending) :]
                    self.forwarded += len(data)
        except OSError:
            pass
        finally:
            with self.lock:
                self.connections.discard(client)
                if upstream is not None:
                    self.connections.discard(upstream)
            client.close()
            if upstream is not None:
                upstream.close()

    def disconnect(self) -> None:
        self.cut.set()
        with self.lock:
            for channel in self.connections:
                try:
                    channel.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def close(self) -> None:
        self.disconnect()
        self.stop.set()
        self.listener.close()
        self.thread.join(2)
        for thread in self.children:
            thread.join(6)
        if self.thread.is_alive() or any(thread.is_alive() for thread in self.children):
            raise TimeoutError("Owned relay did not drain")


def install_pause(boundary: str, folder: Path, kind: str) -> None:
    from marketlab.copilot.v2 import durable
    from marketlab.copilot.v2 import store as copilot_store
    from marketlab.datasets.v2 import jobs
    from marketlab.datasets.v2 import service as ingestion
    from marketlab.memos.v2.service import MemoService
    from marketlab.research.v2 import store as research_store
    from marketlab.research.v2.service import ResearchService
    from marketlab.storage import store as storage
    from marketlab.storage.backend import S3Backend

    fired = threading.Event()

    def pause(current: Any = None) -> None:
        if fired.is_set():
            return
        fired.set()
        from marketlab.inference import _held

        admission = _held.get()
        claim = {}
        if isinstance(current, dict):
            claim = {
                key: str(current[key]) if key in {"job_id", "owner"} else current[key]
                for key in ("job_id", "owner", "fencing_token", "attempt_count")
                if key in current
            }
        elif current is not None:
            claim = {
                key: getattr(current, key)
                for key in (
                    "kind",
                    "identity",
                    "run_id",
                    "owner",
                    "token",
                    "attempt",
                    "request_id",
                    "revision",
                    "relative_path",
                )
                if hasattr(current, key)
            }
        write_once(
            folder / "ready.json",
            {
                "boundary": boundary,
                "pid": os.getpid(),
                "claim": claim,
                "admission_backend_pid": admission[
                    2
                ].connection.driver_connection.pgconn.backend_pid
                if admission
                else None,
                "monotonic": time.monotonic(),
            },
        )
        deadline = time.monotonic() + 180
        while not (folder / "continue.json").exists():
            if time.monotonic() >= deadline:
                raise TimeoutError("Fault controller did not release its private worker")
            time.sleep(0.02)

    def wrap(owner: Any, name: str, *, before: bool = False, claim: bool = False) -> None:
        original = getattr(owner, name)

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            if before:
                pause(args[1] if len(args) > 1 else None)
            result = original(*args, **kwargs)
            if not before and (not claim or result is not None):
                pause(result if claim else (args[1] if len(args) > 1 else None))
            return result

        setattr(owner, name, wrapped)

    if boundary in {
        "after_claim",
        "worker_death",
        "lease_expiry",
        "database_partition",
        "stale_success",
    }:
        wrap(
            jobs if kind == "ingestion" else research_store if kind == "research" else durable,
            "claim",
            claim=True,
        )
    elif boundary in {"before_model_reservation", "after_model_reservation"}:
        if kind not in {"copilot", "memo"}:
            raise ValueError("Model boundary requires inference job")
        wrap(durable, "reserve", before=boundary == "before_model_reservation")
    elif boundary in {"during_output_upload", "storage_partition"}:
        original = S3Backend._run

        def uploaded(self: Any, method: str, **values: Any) -> Any:
            result = original(self, method, **values)
            if method == "upload_part" or boundary == "storage_partition":
                pause()
            return result

        S3Backend._run = uploaded
    elif boundary == "verified_before_commit":
        wrap(storage, "register", before=True)
    elif boundary == "committed_before_response":
        owner, name = {
            "ingestion": (ingestion, "_publish_storage_dataset"),
            "research": (ResearchService, "publish"),
            "copilot": (copilot_store, "finish"),
            "memo": (MemoService, "publish"),
        }[kind]
        wrap(owner, name)
    elif boundary == "cancellation_publication":
        owner, name = {
            "research": (ResearchService, "publish"),
            "copilot": (copilot_store, "finish"),
            "memo": (MemoService, "publish"),
        }.get(kind, (None, None))
        if owner is None:
            raise ValueError("Cancellation boundary requires research or inference job")
        wrap(owner, name, before=True)
    else:
        raise ValueError("Unsupported controlled pause boundary")


def child(config: dict[str, Any]) -> int:
    if os.environ.get("MARKETLAB_PHASE6_BOOTSTRAP_ACTIVE") != "guarded-python-v1":
        raise ValueError("Guarded acceptance child required")
    deadline = time.monotonic() + 15
    while not (Path(config["folder"]) / "launch.json").exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("Private supervisor did not establish native ownership")
        time.sleep(0.02)
    relay = config.get("storage_relay")
    if relay:
        genuine = socket.getaddrinfo

        def redirected(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
            name = host.decode("ascii") if isinstance(host, bytes) else str(host)
            if name.casefold() in relay["hosts"] and int(port) == relay["port"]:
                return genuine("127.0.0.1", relay["local_port"], *args, **kwargs)
            return genuine(host, port, *args, **kwargs)

        socket.getaddrinfo = redirected
    install_pause(config["boundary"], Path(config["folder"]), config["kind"])
    import importlib

    arguments = worker_arguments(
        config["kind"], config["target"], config["root_id"], config.get("compact_sha256")
    )
    sys.argv = arguments
    return int(importlib.import_module(arguments[0]).main())


def linux_pidfd_backend() -> tuple[Callable[[int, int], int], Callable[[int, int], None]]:
    open_fd = getattr(os, "pidfd_open", None)
    send_fd = getattr(signal, "pidfd_send_signal", None)
    if open_fd is not None and send_fd is not None:
        return open_fd, send_fd
    if (
        sys.platform != "linux"
        or os.uname().machine != "x86_64"
        or ctypes.sizeof(ctypes.c_long) != 8
        or ctypes.sizeof(ctypes.c_void_p) != 8
    ):
        raise ValueError("Exact Linux process drain requires pidfd support")
    try:
        # Acquire only an already loaded libc. Never load a separate runtime library.
        libc = ctypes.CDLL("libc.so.6", mode=os.RTLD_NOLOAD | os.RTLD_LOCAL, use_errno=True)
        syscall = libc.syscall
    except (AttributeError, OSError) as error:
        raise ValueError("Exact Linux process drain requires pidfd support") from error
    syscall.argtypes = (ctypes.c_long,)
    syscall.restype = ctypes.c_long

    def checked_call(number: int, *args: Any) -> int:
        result = syscall(number, *args)
        if result == -1:
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code))
        return result

    # Linux x86_64 LP64 UAPI: arch/x86/entry/syscalls/syscall_64.tbl.
    def open_x86_64(pid: int, flags: int) -> int:
        return checked_call(434, ctypes.c_int(pid), ctypes.c_uint(flags))

    def send_x86_64(descriptor: int, signum: int) -> None:
        checked_call(
            424, ctypes.c_int(descriptor), ctypes.c_int(signum), ctypes.c_void_p(), ctypes.c_uint(0)
        )

    return open_x86_64, send_x86_64


class PrivateWorker:
    def __init__(self, config: dict[str, Any], folder: Path, env: dict[str, str]) -> None:
        self.folder = folder
        self.job = None
        if os.name != "nt":
            self.pidfd_open, self.pidfd_send_signal = linux_pidfd_backend()
            descriptor = self.pidfd_open(os.getpid(), 0)
            try:
                self.pidfd_send_signal(descriptor, 0)
            finally:
                os.close(descriptor)
        packet = folder / "child.json"
        write_once(packet, config)
        command = [
            sys.executable,
            "-I",
            "-S",
            str(ROOT / "tests/s3/guarded_python.py"),
            "--",
            str(Path(__file__).resolve()),
            "--child",
            str(packet),
        ]
        self.output = (folder / "worker-output.log").open("xb")
        if os.name == "nt":
            spec = importlib.util.spec_from_file_location(
                "phase7_fault_private_job", ROOT / "scripts/v2_phase4_lifecycle.py"
            )
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.job = module.OwnedJob()
            self.process = self.job.spawn(command, cwd=ROOT, env=env, output=self.output)
        else:
            self.process = subprocess.Popen(
                command,
                cwd=ROOT,
                env=env,
                stdout=self.output,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
            from marketlab.datasets.v2 import native_identity

            try:
                self.native = native_identity.child(self.process.pid)
            except BaseException:
                if self.process.poll() is None:
                    self.process.kill()
                self.process.wait(timeout=15)
                self.output.close()
                raise
            self.owned = {self.process.pid: self.native["birth"]}
        try:
            write_once(folder / "launch.json", {"launch": True})
        except BaseException:
            self.close()
            raise

    def ready(self, seconds: float) -> dict[str, Any]:
        deadline = time.monotonic() + min(seconds, 180)
        while time.monotonic() < deadline:
            marker = self.folder / "ready.json"
            if marker.exists():
                if marker.stat().st_size > 65536:
                    raise ValueError("Marker bound exceeded")
                if self.job is None:
                    self.capture_linux()
                return json.loads(marker.read_bytes())
            if self.process.poll() is not None:
                raise ValueError("Worker exited before its actual boundary")
            if (self.folder / "worker-output.log").stat().st_size > 65536:
                raise ValueError("Private worker output bound exceeded")
            time.sleep(0.02)
        raise TimeoutError("Private worker boundary deadline")

    def release(self) -> None:
        write_once(self.folder / "continue.json", {"continue": True})

    def kill(self) -> None:
        if self.job is not None:
            self.job.terminate()
            self.job.wait_empty(15)
        else:
            self.drain_linux(kill=True)
        self.process.wait(timeout=15)

    def wait(self, seconds: float) -> None:
        self.process.wait(timeout=seconds)
        if self.job is not None:
            self.job.wait_empty(15)
        else:
            self.drain_linux(kill=False)

    def drain_linux(self, *, kill: bool) -> None:
        deadline = time.monotonic() + 15
        while True:
            from marketlab.datasets.v2 import native_identity

            if native_identity.alive(self.native):
                self.capture_linux()
            members = self.members_linux()
            if not members:
                return
            if any(self.owned.get(pid) != birth for pid, birth in members):
                raise ValueError(
                    "Unverified native descendant or reused process domain; accounting retained"
                )
            if not kill or time.monotonic() >= deadline:
                raise ValueError("Owned Linux native descendants have not drained")
            for pid, birth in members:
                try:
                    descriptor = self.pidfd_open(pid, 0)
                    try:
                        raw = Path(f"/proc/{pid}/stat").read_text()
                        fields = raw[raw.rfind(")") + 2 :].split()
                        if fields[19] != birth or int(fields[2]) != self.process.pid:
                            raise ValueError("Owned process birth changed")
                        self.pidfd_send_signal(descriptor, signal.SIGKILL)
                    finally:
                        os.close(descriptor)
                except (FileNotFoundError, ProcessLookupError):
                    continue
            time.sleep(0.02)

    def members_linux(self) -> list[tuple[int, str]]:
        result = []
        for path in Path("/proc").iterdir():
            if not path.name.isdigit():
                continue
            try:
                raw = (path / "stat").read_text()
                fields = raw[raw.rfind(")") + 2 :].split()
                if len(fields) >= 20 and int(fields[2]) == self.process.pid and fields[0] != "Z":
                    result.append((int(path.name), fields[19]))
            except (FileNotFoundError, ProcessLookupError):
                continue
        return result

    def capture_linux(self) -> None:
        from marketlab.datasets.v2 import native_identity

        if not native_identity.alive(self.native):
            raise ValueError("Original private process domain is no longer observable")
        members = self.members_linux()
        if len(members) > 9 or any(int(birth) < int(self.native["birth"]) for _, birth in members):
            raise ValueError("Unexpected private native process domain")
        if not native_identity.alive(self.native):
            raise ValueError("Private process birth changed during capture")
        self.owned.update(members)

    def close(self) -> None:
        try:
            if self.process.poll() is None or (self.job is not None and self.job.active()):
                self.kill()
            elif self.job is None:
                self.drain_linux(kill=True)
        finally:
            if self.job is not None:
                self.job.close()
            self.output.close()


def ledger(engine: Any, kind: str, job_id: str) -> dict[str, Any]:
    from marketlab.datasets.v2.core import execute, one, wire

    UUID(job_id)
    ident = "job_id" if kind in {"ingestion", "copilot"} else "run_id"
    table = "v2_research_runs" if kind == "research" else f"v2_{kind}_jobs"
    with engine.connect() as connection:
        row = one(connection, f"SELECT * FROM {table} WHERE {ident}=:id", id=job_id)
        if row is None:
            raise ValueError("Prepared job missing")
        attempts = [
            dict(r)
            for r in execute(
                connection,
                f"SELECT a.attempt_number,a.fencing_token,"
                "a.worker_instance_id,a.outcome,h.host_id FROM "
                f"v2_{kind}_attempts a LEFT JOIN v2_worker_instances w "
                "ON w.instance_id=a.worker_instance_id "
                "LEFT JOIN v2_worker_roots r ON r.root_id=w.root_id "
                "LEFT JOIN v2_worker_hosts h USING(host_id) "
                f"WHERE a.{ident}=:id ORDER BY attempt_number",
                id=job_id,
            ).mappings()
        ]
        for attempt in attempts:
            attempt.update(job_id=job_id, committed=attempt["outcome"] == "succeeded")
        calls = int(row.get("model_calls", 0))
        if kind == "ingestion":
            present = bool(
                row["result_version"]
                and one(
                    connection,
                    "SELECT dataset_version_id FROM v2_dataset_versions "
                    "WHERE dataset_version_id=:id",
                    id=row["result_version"],
                )
            )
        elif kind == "research":
            present = (
                one(
                    connection, "SELECT run_id FROM v2_research_results WHERE run_id=:id", id=job_id
                )
                is not None
            )
        elif kind == "memo":
            present = (
                one(connection, "SELECT run_id FROM v2_memo_results WHERE run_id=:id", id=job_id)
                is not None
            )
        else:
            revision = one(
                connection,
                "SELECT outcome FROM v2_copilot_revisions "
                "WHERE request_id=:id AND revision=:revision",
                id=row["request_id"],
                revision=row["revision"],
            )
            present = bool(
                revision
                and revision["outcome"] in {"submitted", "needs_clarification", "unsupported"}
            )
        agreement = (row["state"] == "succeeded") == present
        accounting = {
            "data_bytes": int(
                execute(
                    connection,
                    "SELECT coalesce(sum(charged_bytes),0) FROM v2_data_charges "
                    "WHERE state IN ('reserved','retained')",
                ).scalar_one()
            ),
            "physical_bytes": int(
                execute(
                    connection,
                    "SELECT (SELECT coalesce(sum(physical_bytes),0) FROM v2_admission_tickets "
                    "WHERE state<>'released')+"
                    "(SELECT coalesce(sum(reserved_bytes),0) FROM v2_storage_reservations "
                    "WHERE state<>'released')+"
                    "(SELECT coalesce(sum(scratch_bytes+spill_bytes+output_bytes),0) "
                    "FROM v2_research_reservations WHERE state<>'released')",
                ).scalar_one()
            ),
            "slots": int(
                execute(
                    connection, "SELECT count(*) FROM v2_admission_tickets WHERE state<>'released'"
                ).scalar_one()
            ),
        }
    return wire(
        {
            "job": row,
            "attempts": attempts,
            "model_calls": calls,
            "terminal_catalog_agree": agreement,
            "accounting": accounting,
        }
    )


def validate_target(engine: Any, kind: str, target: str, job_id: str, row: dict[str, Any]) -> None:
    from marketlab.datasets.v2.core import execute

    expected = str(
        row["request_id"]
        if kind == "copilot"
        else row["submission_id"]
        if kind == "ingestion"
        else row["run_id"]
    )
    if target != expected:
        raise ValueError("Prepared target does not identify the inspected job")
    if kind == "ingestion":
        with engine.connect() as connection:
            identities = list(
                execute(
                    connection,
                    "SELECT job_id FROM v2_ingestion_jobs WHERE submission_id=:id "
                    "AND state IN ('queued','retry_wait','running')",
                    id=target,
                ).scalars()
            )
        if identities and identities != [UUID(job_id)]:
            raise ValueError("Fault ingestion target must contain exactly one eligible owned job")


def execute(config: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    """Dispatch only explicit prepared owned targets; never manufacture scenario outcomes."""
    from sqlalchemy import create_engine

    from marketlab import workers
    from marketlab.config import Settings
    from marketlab.datasets.v2.core import execute as sql
    from marketlab.datasets.v2.core import one

    if os.environ.get("MARKETLAB_PHASE6_BOOTSTRAP_ACTIVE") != "guarded-python-v1":
        raise ValueError("Guarded acceptance supervisor required")
    if packet.get("action") in {"inference", "inference_recover"}:
        return execute_inference(config, packet)
    if packet.get("action") not in {"fault", "fault_recover"}:
        raise ValueError("Explicit prepared fault action required")
    budget = DispatchBudget(packet, 1 if packet["action"] == "fault_recover" else 2)
    boundary = packet.get("boundary")
    if boundary not in BOUNDARIES:
        raise ValueError("Unknown fault boundary")
    repetition = packet.get("repetition")
    if type(repetition) is not int or not 0 <= repetition <= 2:
        raise ValueError("Invalid repetition")
    key = f"{boundary}:{repetition}"
    model_scenario = packet.get("model_scenario")
    if model_scenario is not None:
        expected = {
            "session_loss": "before_model_reservation",
            "nonrefundable_reservation": "after_model_reservation",
        }
        if expected.get(model_scenario) != boundary:
            raise ValueError("Invalid frozen model fault boundary")
        binding = config.get("model_bindings", {}).get(model_scenario)
        if isinstance(binding, dict):
            binding = dict(binding, fault_mode="admission_session_loss")
    else:
        binding = config.get("fault_bindings", {}).get(key)
    if not isinstance(binding, dict):
        raise ValueError("Frozen prepared fault binding required")
    kind = binding["kind"]
    target = binding["target"]
    job_id = binding["job_id"]
    if kind not in KINDS:
        raise ValueError("Invalid bound kind")
    for value in (target, job_id, config["host_id"], config["root_id"]):
        UUID(value)
    compact_sha256 = binding.get("compact_sha256")
    if "compact_sha256" in binding and (
        (kind, boundary)
        not in {("ingestion", "during_output_upload"), ("research", "storage_partition")}
        or not isinstance(compact_sha256, str)
    ):
        raise ValueError("Compact worker binding requires the exact model-free fault boundary")
    worker_args = worker_arguments(kind, target, config["root_id"], compact_sha256)
    seconds = packet["seconds_remaining"]
    if type(seconds) not in {int, float} or not 0 < seconds <= 1800:
        raise ValueError("Invalid fault deadline")
    settings = Settings()
    engine = create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
    workers.bind_root(engine, settings.storage_path, config["root_id"])
    runner = load_runner()
    started = time.monotonic()

    def remaining() -> float:
        value = seconds - (time.monotonic() - started)
        if value <= 0:
            raise TimeoutError("Fault deadline exhausted")
        return value

    try:
        with engine.connect() as connection:
            current = workers.mode(connection)
            root = one(
                connection,
                "SELECT host_id FROM v2_worker_roots WHERE root_id=:id",
                id=config["root_id"],
            )
            database = sql(connection, "SELECT current_database()").scalar_one()
        if (
            current is None
            or current["mode"] != "distributed"
            or root is None
            or str(root["host_id"]) != config["host_id"]
            or database != config.get("owned_database")
        ):
            raise ValueError("Explicit owned distributed database and host proof required")
        before = ledger(engine, kind, job_id)
        validate_target(engine, kind, target, job_id, before["job"])
        if kind in {"copilot", "memo"} and config.get("allow_model_dispatch") is not True:
            raise ValueError("Explicit pinned model dispatch binding required")
        if kind in {"copilot", "memo"} and config.get("owned_model_url") != settings.ollama_url:
            raise ValueError("Explicit owned pinned model endpoint required")
        if packet["action"] == "fault_recover":
            budget.start()
            runner.cli(worker_args, remaining())
            return {
                "request_id": packet["request_id"],
                "host_id": config["host_id"],
                "status": "observed",
                **ledger(engine, kind, job_id),
                **budget.receipt(),
            }
        if before["job"]["state"] != "queued" or before["attempts"] or before["model_calls"]:
            raise ValueError(
                "Fresh frozen queued fault target required; previous attempts stay retained"
            )
        peer = binding.get("peer")
        if not isinstance(peer, dict) or peer.get("host_id") == config["host_id"]:
            raise ValueError("Distinct frozen peer host required")
        UUID(peer["host_id"])
        verify_peer(packet, peer)
        folder = safe_folder(Path(config["evidence_root"]), packet["request_id"])
        write_once(folder / "before.json", before)

        def peer_worker() -> dict[str, Any]:
            budget.start()
            response = runner.transport(
                peer,
                {
                    "schema": "phase7-adapter-v1",
                    "request_id": packet["request_id"],
                    "action": "fault_recover",
                    "boundary": boundary,
                    "repetition": repetition,
                    **({"model_scenario": model_scenario} if model_scenario else {}),
                    "allowed_hosts": packet["allowed_hosts"],
                    "frozen_identity": packet["frozen_identity"],
                    "jobs_remaining": 1,
                    "seconds_remaining": min(1800, remaining()),
                },
                min(1800, remaining()),
            )
            write_once(folder / "peer.json", response)
            if (
                response.get("request_id") != packet["request_id"]
                or response.get("host_id") != peer["host_id"]
            ):
                raise ValueError("Stale peer ownership response")
            return response

        if boundary == "competing_claims":
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=2) as pool:
                remote = pool.submit(peer_worker)
                budget.start()
                local = pool.submit(runner.cli, worker_args, remaining())
                local.result(timeout=remaining())
                remote.result(timeout=remaining())
            after = ledger(engine, kind, job_id)
            if len(after["attempts"]) != 1 or after["job"]["state"] != "succeeded":
                raise ValueError("Competing claims did not produce exactly one successful attempt")
            marker = {
                "boundary": boundary,
                "actual_competing_hosts": [config["host_id"], peer["host_id"]],
            }
        else:
            expected_terminal = "succeeded"
            relay = None
            env = dict(os.environ)
            child_packet = {
                "boundary": "committed_before_response"
                if boundary == "cancellation_publication" and repetition == 1
                else boundary,
                "folder": str(folder),
                "kind": kind,
                "target": target,
                "root_id": config["root_id"],
            }
            if compact_sha256 is not None:
                child_packet["compact_sha256"] = compact_sha256
            if boundary == "database_partition":
                url = settings.sqlalchemy_url
                relay = Relay(url.host or "", url.port or 5432)
                env["MARKETLAB_DATABASE_URL"] = url.set(
                    port=relay.port, query={**url.query, "hostaddr": "127.0.0.1"}
                ).render_as_string(hide_password=False)
            elif boundary == "storage_partition":
                from urllib.parse import urlsplit

                from marketlab.storage.backend import ObjectConfig

                object_config = ObjectConfig.from_settings(settings)
                if object_config is None:
                    raise ValueError("Versioned object endpoint required")
                endpoint = urlsplit(
                    object_config.endpoint or f"https://s3.{object_config.region}.amazonaws.com"
                )
                host = endpoint.hostname
                port = endpoint.port or (443 if endpoint.scheme == "https" else 80)
                relay = Relay(host or "", port)
                child_packet["storage_relay"] = {
                    "hosts": [str(host).casefold(), f"{object_config.bucket}.{host}".casefold()],
                    "port": port,
                    "local_port": relay.port,
                }
            budget.start()
            private = PrivateWorker(child_packet, folder, env)
            try:
                marker = private.ready(remaining())
                write_once(folder / "boundary.json", marker)
                if marker["boundary"] != child_packet["boundary"]:
                    raise ValueError("Wrong actual fault boundary")
                if boundary == "cancellation_publication":
                    old = ledger(engine, kind, job_id)["job"]
                    args = [
                        f"marketlab.{'research' if kind == 'research' else kind}_cli",
                        "v2",
                        "cancel",
                        "--run" if kind in {"research", "memo"} else "--job",
                        job_id,
                        "--expected-revision"
                        if kind == "research"
                        else "--expected-state-revision",
                        str(old["revision"] if kind == "research" else old["state_revision"]),
                        "--key",
                        "p7.cancel." + packet["request_id"],
                    ]
                    if repetition == 0:
                        cancelled = runner.cli(args, remaining())
                        write_once(folder / "cancel.json", cancelled)
                        expected_terminal = "cancelled"
                        private.release()
                    else:

                        def cancel_direct() -> dict[str, Any]:
                            from marketlab.datasets.v2.common import V2Error

                            try:
                                if kind == "research":
                                    from marketlab.research.v2.store import cancel

                                    return cancel(
                                        engine,
                                        job_id,
                                        old["revision"],
                                        "p7.cancel." + packet["request_id"],
                                    )
                                from marketlab.copilot.v2.durable import cancel

                                return cancel(
                                    engine,
                                    kind,
                                    job_id,
                                    old["state_revision"],
                                    "p7.cancel." + packet["request_id"],
                                )
                            except V2Error as error:
                                if error.code != "revision_conflict":
                                    raise
                                return {"error_code": error.code}

                        if repetition == 1:
                            cancelled = cancel_direct()
                            if cancelled.get("error_code") != "revision_conflict":
                                raise ValueError("Committed success accepted cancellation")
                            private.release()
                        else:
                            from concurrent.futures import ThreadPoolExecutor

                            with ThreadPoolExecutor(max_workers=1) as pool:
                                request = pool.submit(cancel_direct)
                                private.release()
                                cancelled = request.result(timeout=remaining())
                        expected_terminal = (
                            "succeeded"
                            if cancelled.get("error_code") == "revision_conflict"
                            else "cancelled"
                        )
                        write_once(folder / "cancel.json", cancelled)
                    private.wait(remaining())
                elif binding.get("fault_mode") == "admission_session_loss":
                    pid = marker.get("admission_backend_pid")
                    if type(pid) is not int or pid <= 0:
                        raise ValueError("Actual held admission session not observed")
                    with engine.begin() as connection:
                        target_session = one(
                            connection,
                            "SELECT pid FROM pg_stat_activity WHERE pid=:pid "
                            "AND datname=current_database() AND usename=current_user "
                            "AND backend_type='client backend'",
                            pid=pid,
                        )
                        if target_session is None:
                            raise ValueError("Exact owned admission session missing")
                        if not sql(
                            connection, "SELECT pg_terminate_backend(:pid)", pid=pid
                        ).scalar_one():
                            raise ValueError("Exact owned admission session was not terminated")
                    private.release()
                    private.wait(min(180, remaining()))
                elif relay is not None:
                    if relay.accepted < 1 or relay.forwarded < 1:
                        raise ValueError(
                            "No actual target flow traversed the owned partition relay"
                        )
                    relay.disconnect()
                    private.release()
                    private.wait(min(180, remaining()))
                    write_once(
                        folder / "relay.json",
                        {
                            "cut": True,
                            "accepted_connections": relay.accepted,
                            "forwarded_bytes": relay.forwarded,
                        },
                    )
                else:
                    private.kill()
                observed = ledger(engine, kind, job_id)
                write_once(folder / "after-fault.json", observed)
                wait_due(engine, kind, job_id, remaining())
                peer_worker()
                after = ledger(engine, kind, job_id)
                if boundary == "before_model_reservation" and observed["model_calls"] != 0:
                    raise ValueError("Before-reservation crash spent a call")
                if boundary == "after_model_reservation" and (
                    observed["model_calls"] != 1 or after["model_calls"] < 1
                ):
                    raise ValueError("Reserved model call was not retained")
                if boundary == "committed_before_response" and len(after["attempts"]) != 1:
                    raise ValueError("Committed response loss caused duplicate work")
                if (
                    boundary == "cancellation_publication"
                    and after["job"]["state"] != expected_terminal
                ):
                    raise ValueError("Accepted cancellation failed publication fence")
                if boundary == "stale_success":
                    if kind not in {"copilot", "memo", "research", "ingestion"}:
                        raise ValueError("Unknown fence kind")
                    stale_fence(engine, kind, marker["claim"], job_id)
            finally:
                private.close()
                if relay is not None:
                    relay.close()
        if not after["terminal_catalog_agree"] or after["job"]["state"] != (
            expected_terminal if boundary == "cancellation_publication" else "succeeded"
        ):
            raise ValueError("Scenario did not reach actual terminal/catalog agreement")
        if len(after["attempts"]) > 3 or sum(a["committed"] for a in after["attempts"]) > 1:
            raise ValueError("Scenario violated attempt/publication limits")
        receipt = {
            "request_id": packet["request_id"],
            "host_id": config["host_id"],
            "status": "observed",
            "jobs_started": len(after["attempts"]) - len(before["attempts"]),
            "model_calls_before": before["model_calls"],
            "model_calls_after": after["model_calls"],
            "attempts": after["attempts"],
            "terminal_catalog_agree": after["terminal_catalog_agree"],
            "fault_boundary": marker,
            "unknown_native_work": False,
            "acceptance": "incomplete",
        }
        receipt.update(budget.receipt())
        if boundary != "competing_claims":
            receipt["upstream_continuation"] = (
                "unknown" if observed["model_calls"] else "not_dispatched"
            )
        write_once(folder / "result.json", receipt)
        return receipt
    finally:
        engine.dispose()


def stale_fence(engine: Any, kind: str, claim: dict[str, Any], job_id: str) -> None:
    from marketlab.datasets.v2.common import V2Error
    from marketlab.datasets.v2.core import transaction

    try:
        with transaction(engine) as connection:
            if kind == "ingestion":
                from marketlab.datasets.v2.jobs import fence

                fence(connection, claim)
            elif kind == "research":
                from marketlab.research.v2.store import Claim, fence

                fence(connection, Claim(job_id, claim["owner"], claim["token"], claim["attempt"]))
            else:
                from marketlab.copilot.v2.durable import Claim, fence

                fence(
                    connection,
                    Claim(
                        kind,
                        job_id,
                        claim["owner"],
                        claim["token"],
                        claim["attempt"],
                        claim.get("request_id"),
                        claim.get("revision"),
                        claim.get("relative_path"),
                    ),
                )
    except V2Error:
        return
    raise ValueError("Stale publication fence accepted an expired claim")


class ModelProxy:
    """Forward genuine pinned-model bytes while independently observing client closure."""

    def __init__(self, upstream: str, folder: Path) -> None:
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from urllib.parse import urlsplit

        endpoint = urlsplit(upstream)
        if (
            endpoint.scheme not in {"http", "https"}
            or not endpoint.hostname
            or endpoint.username is not None
            or endpoint.password is not None
            or endpoint.path not in {"", "/"}
            or endpoint.query
            or endpoint.fragment
        ):
            raise ValueError("Explicit owned model endpoint required")
        self.started = threading.Event()
        self.completed = threading.Event()
        self.stop = threading.Event()
        self.closed_at = None
        self.finished_at = None
        self.response_sha256 = None
        self.error = False
        self.handlers: list[threading.Thread] = []
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:
                pass

            def do_GET(self) -> None:
                self.forward()

            def do_POST(self) -> None:
                self.forward()

            def forward(self) -> None:
                import hashlib

                import httpx

                proxy.handlers.append(threading.current_thread())
                if self.path not in {"/api/chat", "/api/tags", "/api/version"}:
                    self.send_error(404)
                    return
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 <= size <= 65536:
                    self.send_error(413)
                    return
                body = self.rfile.read(size)
                if len(body) != size:
                    self.close_connection = True
                    return
                generation = self.path == "/api/chat"
                watcher = None
                if generation:
                    if proxy.started.is_set():
                        self.send_error(409)
                        return
                    proxy.started.set()

                    def watch() -> None:
                        while not proxy.completed.is_set() and not proxy.stop.is_set():
                            try:
                                if select.select([self.connection], [], [], 0.1)[
                                    0
                                ] and not self.connection.recv(1, socket.MSG_PEEK):
                                    proxy.closed_at = time.monotonic()
                                    return
                            except OSError:
                                proxy.closed_at = time.monotonic()
                                return

                    watcher = threading.Thread(target=watch, daemon=True)
                    watcher.start()
                try:
                    with httpx.Client(
                        base_url=upstream,
                        trust_env=False,
                        follow_redirects=False,
                        timeout=httpx.Timeout(125, connect=5),
                    ) as client:
                        with client.stream(
                            self.command,
                            self.path,
                            content=body,
                            headers={"Content-Type": "application/json"},
                        ) as response:
                            raw = bytearray()
                            for block in response.iter_bytes():
                                if len(raw) + len(block) > 32768:
                                    raise ValueError("Bounded upstream response required")
                                raw.extend(block)
                            if response.status_code != 200:
                                raise ValueError("Genuine model endpoint unavailable")
                    if generation:
                        value = json.loads(raw)
                        if value.get("done") is not True:
                            raise ValueError("Genuine complete model response required")
                        proxy.finished_at = time.monotonic()
                        proxy.response_sha256 = hashlib.sha256(raw).hexdigest()
                        with (folder / "genuine-upstream-response.bin").open("xb") as output:
                            output.write(raw)
                    try:
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(raw)))
                        self.end_headers()
                        self.wfile.write(raw)
                    except OSError:
                        pass
                except Exception:
                    proxy.error = True
                    self.close_connection = True
                finally:
                    if generation:
                        proxy.completed.set()
                    if watcher is not None:
                        watcher.join(1)

        class Server(ThreadingHTTPServer):
            daemon_threads = True

        self.server = Server(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True
        )
        self.thread.start()

    def close(self) -> None:
        self.stop.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        for thread in self.handlers:
            thread.join(135)
        if any(thread.is_alive() for thread in self.handlers) or self.thread.is_alive():
            raise TimeoutError("Genuine upstream observation did not drain")


def execute_inference(config: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    from sqlalchemy import create_engine

    from marketlab import workers
    from marketlab.config import Settings
    from marketlab.copilot.v2.model import DIGEST
    from marketlab.datasets.v2.core import execute as sql
    from marketlab.datasets.v2.core import one
    from marketlab.inference import admission

    scenario = packet.get("scenario")
    if scenario not in {
        "cross_host_contention",
        "copilot_priority",
        "zero_wait_budget",
        "session_loss",
        "nonrefundable_reservation",
        "pinned_model_copilot",
        "pinned_model_memo",
        "upstream_continuation",
    }:
        raise ValueError("Invalid inference scenario")
    budget = DispatchBudget(
        packet,
        1
        if packet["action"] == "inference_recover"
        or scenario in {"zero_wait_budget", "pinned_model_copilot", "pinned_model_memo"}
        else 2,
    )
    binding = config.get("model_bindings", {}).get(scenario)
    if not isinstance(binding, dict) or config.get("allow_model_dispatch") is not True:
        raise ValueError("Explicit prepared pinned-model binding required")
    if packet["action"] == "inference_recover" and packet.get("contender") is not None:
        if (
            scenario != "cross_host_contention"
            or packet["contender"] != "memo"
            or not isinstance(binding.get("memo"), dict)
        ):
            raise ValueError("Invalid frozen cross-kind contender")
        binding = binding["memo"]
    kind = binding["kind"]
    target = binding["target"]
    job_id = binding["job_id"]
    if kind not in {"copilot", "memo"}:
        raise ValueError("Inference target kind required")
    for value in (target, job_id, config["host_id"], config["root_id"]):
        UUID(value)
    seconds = packet["seconds_remaining"]
    if type(seconds) not in {int, float} or not 0 < seconds <= 1800:
        raise ValueError("Invalid inference deadline")
    runner = load_runner()
    started = time.monotonic()

    def remaining() -> float:
        value = seconds - (time.monotonic() - started)
        if value <= 0:
            raise TimeoutError("Inference scenario deadline exhausted")
        return value

    if (
        scenario in {"session_loss", "nonrefundable_reservation"}
        and packet["action"] == "inference"
    ):
        boundary = (
            "before_model_reservation" if scenario == "session_loss" else "after_model_reservation"
        )
        return execute(
            config,
            {
                **packet,
                "action": "fault",
                "boundary": boundary,
                "repetition": 0,
                "model_scenario": scenario,
            },
        )
    settings = Settings()
    engine = create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
    if config.get("owned_model_url") != settings.ollama_url:
        raise ValueError("Explicit owned pinned model endpoint required")
    workers.bind_root(engine, settings.storage_path, config["root_id"])
    try:
        with engine.connect() as connection:
            mode = workers.mode(connection)
            database = sql(connection, "SELECT current_database()").scalar_one()
            root = one(
                connection,
                "SELECT host_id FROM v2_worker_roots WHERE root_id=:id",
                id=config["root_id"],
            )
        if (
            mode is None
            or mode["mode"] != "distributed"
            or database != config.get("owned_database")
            or root is None
            or str(root["host_id"]) != config["host_id"]
        ):
            raise ValueError("Exact owned distributed model scenario required")
        before = ledger(engine, kind, job_id)
        validate_target(engine, kind, target, job_id, before["job"])
        if packet["action"] == "inference_recover":
            budget.start()
            runner.cli(worker_arguments(kind, target, config["root_id"]), remaining())
            return {
                "request_id": packet["request_id"],
                "host_id": config["host_id"],
                "status": "observed",
                **ledger(engine, kind, job_id),
                **budget.receipt(),
            }
        if before["job"]["state"] != "queued" or before["attempts"] or before["model_calls"]:
            raise ValueError("Fresh queued model scenario target required")
        peer = binding.get("peer")
        if not isinstance(peer, dict) or peer.get("host_id") == config["host_id"]:
            raise ValueError("Actual distinct peer required")
        verify_peer(packet, peer)
        folder = safe_folder(Path(config["evidence_root"]), packet["request_id"])
        write_once(folder / "before.json", before)

        def remote() -> Any:
            budget.start()
            response = runner.transport(
                peer,
                {
                    **packet,
                    "action": "inference_recover",
                    "jobs_remaining": 1,
                    **({"contender": "memo"} if scenario == "cross_host_contention" else {}),
                    "seconds_remaining": min(1800, remaining()),
                },
                min(1800, remaining()),
            )
            if (
                response.get("request_id") != packet["request_id"]
                or response.get("host_id") != peer["host_id"]
            ):
                raise ValueError("Stale peer inference response")
            return response

        extra = {}
        if scenario == "zero_wait_budget":

            async def waiting() -> None:
                async with admission(engine) as held:
                    if not held:
                        raise ValueError("Owned admission lock unavailable")
                    response = await asyncio.to_thread(remote)
                    write_once(folder / "waiting-peer.json", response)

            asyncio.run(waiting())
            after = ledger(engine, kind, job_id)
            if after["attempts"] or after["model_calls"]:
                raise ValueError("Waiting spent a durable budget")
            extra["attempts_started_while_waiting"] = 0
        elif scenario == "cross_host_contention":
            if kind != "copilot" or not isinstance(binding.get("memo"), dict):
                raise ValueError("Distinct prepared copilot and memo required")
            contender = binding["memo"]
            memo_before = ledger(engine, "memo", contender["job_id"])
            validate_target(
                engine, "memo", contender["target"], contender["job_id"], memo_before["job"]
            )
            if (
                memo_before["job"]["state"] != "queued"
                or memo_before["attempts"]
                or memo_before["model_calls"]
            ):
                raise ValueError("Fresh queued peer memo required")
            budget.start()
            private = PrivateWorker(
                {
                    "boundary": "after_model_reservation",
                    "folder": str(folder),
                    "kind": kind,
                    "target": target,
                    "root_id": config["root_id"],
                },
                folder,
                dict(os.environ),
            )
            try:
                private.ready(remaining())
                response = remote()
                write_once(folder / "competing-peer.json", response)
                memo_waiting = ledger(engine, "memo", contender["job_id"])
                if memo_waiting["attempts"] or memo_waiting["model_calls"]:
                    raise ValueError("Peer memo spent budgets while copilot held admission")
                private.release()
                private.wait(remaining())
                extra.update(
                    peer_contender_kind="memo",
                    attempts_started_while_waiting=0,
                    waiting_model_calls_before=0,
                    waiting_model_calls_after=0,
                )
            finally:
                private.close()
            after = ledger(engine, kind, job_id)
            if len(after["attempts"]) != 1 or after["model_calls"] != 1:
                raise ValueError("Inference contention spent duplicate budgets")
        elif scenario == "copilot_priority":
            if kind != "memo":
                raise ValueError("Memo plus compatible queued copilot required")
            priority = binding["copilot"]
            pending = ledger(engine, "copilot", priority["job_id"])
            if pending["job"]["state"] != "queued" or pending["attempts"]:
                raise ValueError("Fresh queued priority candidate required")
            response = remote()
            write_once(folder / "priority-peer.json", response)
            waiting = ledger(engine, "memo", job_id)
            if waiting["attempts"] or waiting["model_calls"]:
                raise ValueError("Memo bypassed queued copilot priority")
            budget.start()
            runner.cli(
                worker_arguments("copilot", priority["target"], config["root_id"]), remaining()
            )
            after = ledger(engine, "copilot", priority["job_id"])
            extra["memo_attempts_while_copilot_queued"] = 0
        elif scenario == "upstream_continuation":
            proxy = ModelProxy(settings.ollama_url, folder)
            child_packet = {
                "boundary": "after_model_reservation",
                "folder": str(folder),
                "kind": kind,
                "target": target,
                "root_id": config["root_id"],
            }
            budget.start()
            private = PrivateWorker(
                child_packet, folder, {**os.environ, "MARKETLAB_OLLAMA_URL": proxy.url}
            )
            try:
                marker = private.ready(remaining())
                private.release()
                if not proxy.started.wait(min(125, remaining())):
                    raise TimeoutError("Actual model dispatch was not observed")
                pid = marker.get("admission_backend_pid")
                if type(pid) is not int or pid <= 0:
                    raise ValueError("Exact model admission session missing")
                with engine.begin() as connection:
                    if (
                        one(
                            connection,
                            "SELECT pid FROM pg_stat_activity WHERE pid=:pid "
                            "AND datname=current_database() "
                            "AND usename=current_user AND backend_type='client backend'",
                            pid=pid,
                        )
                        is None
                    ):
                        raise ValueError("Owned admission backend missing")
                    sql(connection, "SELECT pg_terminate_backend(:pid)", pid=pid)
                private.wait(min(180, remaining()))
                if (
                    not proxy.completed.wait(min(135, remaining()))
                    or proxy.error
                    or proxy.closed_at is None
                    or proxy.finished_at is None
                    or proxy.finished_at <= proxy.closed_at
                ):
                    raise ValueError(
                        "Upstream continuation after HTTP closure not established; "
                        "call remains spent"
                    )
                after = ledger(engine, kind, job_id)
                extra.update(
                    upstream_continuation="observed_after_client_close",
                    upstream_response_continuation="observed_after_client_close",
                    upstream_observation_scope=(
                        "HTTP response completion; server token activity unknown"
                    ),
                    upstream_response_sha256=proxy.response_sha256,
                    client_closed_monotonic=proxy.closed_at,
                    upstream_finished_monotonic=proxy.finished_at,
                )
                wait_due(engine, kind, job_id, remaining())
                peer_result = remote()
                write_once(folder / "continuation-peer.json", peer_result)
                after = ledger(engine, kind, job_id)
                if after["job"]["state"] != "succeeded" or not after["terminal_catalog_agree"]:
                    raise ValueError(
                        "Upstream continuation recovery did not reach terminal agreement"
                    )
            finally:
                private.close()
                proxy.close()
        else:
            if (
                scenario == "pinned_model_copilot"
                and kind != "copilot"
                or scenario == "pinned_model_memo"
                and kind != "memo"
            ):
                raise ValueError("Pinned functional target kind mismatch")
            budget.start()
            runner.cli(worker_arguments(kind, target, config["root_id"]), remaining())
            after = ledger(engine, kind, job_id)
        if scenario not in {"zero_wait_budget", "upstream_continuation"}:
            if after["job"]["state"] != "succeeded" or not after["terminal_catalog_agree"]:
                raise ValueError("Actual pinned model scenario failed")
        if scenario != "zero_wait_budget":
            checked_kind = "copilot" if scenario == "copilot_priority" else kind
            checked_id = binding["copilot"]["job_id"] if scenario == "copilot_priority" else job_id
            ident = "job_id" if checked_kind == "copilot" else "run_id"
            with engine.connect() as connection:
                digests = list(
                    sql(
                        connection,
                        f"SELECT model_digest FROM v2_{checked_kind}_calls WHERE {ident}=:id",
                        id=checked_id,
                    ).scalars()
                )
            if not digests or any(value != DIGEST for value in digests):
                raise ValueError("Actual pinned call identity mismatch")
        receipt = {
            "request_id": packet["request_id"],
            "host_id": config["host_id"],
            "status": "observed",
            "jobs_started": len(after["attempts"]) - len(before["attempts"]),
            "model_calls_before": before["model_calls"],
            "model_calls_after": after["model_calls"],
            "attempts": after["attempts"],
            "terminal_catalog_agree": after["terminal_catalog_agree"],
            "scenario": scenario,
            "acceptance": "incomplete",
            **extra,
        }
        receipt.update(budget.receipt())
        write_once(folder / "result.json", receipt)
        return receipt
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        if sys.argv[1:2] != ["--child"]:
            raise ValueError("Only guarded private child invocation supported")
        path = Path(sys.argv[2])
        if path.stat().st_size > 65536:
            raise ValueError("Bounded private child packet required")
        raise SystemExit(child(json.loads(path.read_bytes())))
    except Exception:
        print("Owned Phase 7 fault child failed", file=sys.stderr)
        raise SystemExit(1) from None
