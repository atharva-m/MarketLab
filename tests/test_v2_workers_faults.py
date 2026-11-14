"""Owned fault-hook ordering, immutable receipts and real opaque loopback cuts."""

import ctypes
import errno
import importlib.util
import json
import os
import socket
import threading
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from marketlab.copilot.v2 import durable, store
from marketlab.storage.backend import S3Backend

spec = importlib.util.spec_from_file_location(
    "phase7_fault_primitives", Path(__file__).resolve().parents[1] / "scripts/v2_phase7_faults.py"
)
assert spec is not None and spec.loader is not None
faults = importlib.util.module_from_spec(spec)
spec.loader.exec_module(faults)


def test_pidfd_backend_prefers_complete_python_api_pair(monkeypatch):
    open_fd = object()
    send_fd = object()
    monkeypatch.setattr(faults, "os", SimpleNamespace(pidfd_open=open_fd))
    monkeypatch.setattr(faults, "signal", SimpleNamespace(pidfd_send_signal=send_fd))
    assert faults.linux_pidfd_backend() == (open_fd, send_fd)


@pytest.fixture
def native_syscall(monkeypatch):
    fake = SimpleNamespace(calls=[], results=[], loaded=[], machine="x86_64", width=8, error=0)

    def syscall(number, *args):
        fake.calls.append((number, tuple(arg.value for arg in args)))
        return fake.results.pop(0)

    fake.library = SimpleNamespace(syscall=syscall)

    def load(name, **options):
        fake.loaded.append((name, options))
        return fake.library

    monkeypatch.setattr(faults, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(faults, "signal", SimpleNamespace())
    monkeypatch.setattr(
        faults,
        "os",
        SimpleNamespace(uname=lambda: fake, RTLD_NOLOAD=4, RTLD_LOCAL=0, strerror=os.strerror),
    )
    monkeypatch.setattr(
        faults,
        "ctypes",
        SimpleNamespace(
            CDLL=load,
            sizeof=lambda _: fake.width,
            get_errno=lambda: fake.error,
            c_long=ctypes.c_long,
            c_int=ctypes.c_int,
            c_uint=ctypes.c_uint,
            c_void_p=ctypes.c_void_p,
        ),
    )
    return fake


def test_pidfd_backend_uses_only_typed_x86_64_fd_syscalls(native_syscall):
    native_syscall.results[:] = [78, 0]
    open_fd, send_fd = faults.linux_pidfd_backend()
    assert open_fd(4362, 0) == 78
    assert send_fd(78, 9) is None
    assert native_syscall.loaded == [("libc.so.6", {"mode": 4, "use_errno": True})]
    assert native_syscall.library.syscall.argtypes == (ctypes.c_long,)
    assert native_syscall.library.syscall.restype is ctypes.c_long
    assert native_syscall.calls == [(434, (4362, 0)), (424, (78, 9, None, 0))]


@pytest.mark.parametrize("machine,width", [("aarch64", 8), ("x86_64", 4)])
def test_pidfd_backend_rejects_unqualified_linux_abi(native_syscall, machine, width):
    native_syscall.machine, native_syscall.width = machine, width
    with pytest.raises(ValueError, match="requires pidfd support"):
        faults.linux_pidfd_backend()
    assert native_syscall.loaded == []


def test_pidfd_backend_rejects_missing_libc_syscall(native_syscall):
    native_syscall.library = SimpleNamespace()
    with pytest.raises(ValueError, match="requires pidfd support"):
        faults.linux_pidfd_backend()
    assert native_syscall.calls == []


@pytest.mark.parametrize(
    "number,exception,operation",
    [
        (errno.ENOSYS, OSError, "open"),
        (errno.EPERM, PermissionError, "send"),
        (errno.ESRCH, ProcessLookupError, "send"),
    ],
)
def test_pidfd_backend_preserves_kernel_errno(native_syscall, number, exception, operation):
    native_syscall.results[:] = [-1]
    native_syscall.error = number
    open_fd, send_fd = faults.linux_pidfd_backend()
    with pytest.raises(exception) as failure:
        if operation == "open":
            open_fd(4362, 0)
        else:
            send_fd(78, 9)
    assert failure.value.errno == number


def test_pidfd_self_probe_fails_before_private_worker_launch(tmp_path, monkeypatch):
    events = []

    def open_fd(pid, flags):
        events.append(("open", pid, flags))
        return 78

    def send_fd(fd, signum):
        events.append(("send", fd, signum))
        raise PermissionError(errno.EPERM, "synthetic permission failure")

    monkeypatch.setattr(faults, "linux_pidfd_backend", lambda: (open_fd, send_fd))
    monkeypatch.setattr(
        faults,
        "os",
        SimpleNamespace(
            name="posix", getpid=lambda: 123, close=lambda fd: events.append(("close", fd))
        ),
    )
    with pytest.raises(PermissionError):
        faults.PrivateWorker({}, tmp_path, {})
    assert events == [("open", 123, 0), ("send", 78, 0), ("close", 78)]
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "observed_birth,observed_group,signal_errno,expected",
    [
        ("100", 4362, None, True),
        ("101", 4362, None, False),
        ("100", 4363, None, False),
        ("100", 4362, errno.ESRCH, True),
    ],
)
def test_pidfd_drain_revalidates_exact_birth_and_group_before_signal(
    monkeypatch, observed_birth, observed_group, signal_errno, expected
):
    from marketlab.datasets.v2 import native_identity

    worker = faults.PrivateWorker.__new__(faults.PrivateWorker)
    worker.process = SimpleNamespace(pid=4362)
    worker.native = {"birth": "100"}
    worker.owned = {4362: "100"}
    observations = iter([[(4362, "100")], []])
    worker.members_linux = lambda: next(observations)
    events = []

    def open_fd(pid, flags):
        events.append(("open", pid, flags))
        return 78

    def send_fd(fd, signum):
        events.append(("send", fd, signum))
        if signal_errno is not None:
            raise OSError(signal_errno, "synthetic exited process")

    def proc_stat(path):
        assert path == "/proc/4362/stat"
        fields = ["S", "1", str(observed_group), *(["0"] * 16), observed_birth]
        return SimpleNamespace(read_text=lambda: "4362 (synthetic child) " + " ".join(fields))

    worker.pidfd_open, worker.pidfd_send_signal = open_fd, send_fd
    monkeypatch.setattr(native_identity, "alive", lambda _: False)
    monkeypatch.setattr(faults, "Path", proc_stat)
    monkeypatch.setattr(faults, "signal", SimpleNamespace(SIGKILL=9))
    monkeypatch.setattr(
        faults, "os", SimpleNamespace(close=lambda fd: events.append(("close", fd)))
    )
    if expected:
        worker.drain_linux(kill=True)
        assert events == [("open", 4362, 0), ("send", 78, faults.signal.SIGKILL), ("close", 78)]
    else:
        with pytest.raises(ValueError, match="birth changed"):
            worker.drain_linux(kill=True)
        assert events == [("open", 4362, 0), ("close", 78)]


@pytest.mark.parametrize("kind", ["ingestion", "research", "copilot", "memo"])
def test_owned_worker_arguments_pin_one_job_zero_wait_exact_root_and_target(kind):
    target, root = str(uuid4()), str(uuid4())
    arguments = faults.worker_arguments(kind, target, root)
    assert arguments[1:3] == ["v2", "worker"]
    assert arguments[arguments.index("--worker-root") + 1] == root
    assert arguments[arguments.index("--wait-seconds") + 1] == "0"
    maximum = "--max-runs" if kind == "research" else "--max-jobs"
    assert arguments[arguments.index(maximum) + 1] == "1"
    assert arguments[-1] == target
    with pytest.raises(ValueError):
        faults.worker_arguments(kind, "--injected-option", root)


def test_compact_fault_worker_argument_is_only_for_model_free_targets():
    target, root, pin = str(uuid4()), str(uuid4()), "a" * 64
    for kind, flag in (
        ("ingestion", "--compact-official-sha256"),
        ("research", "--compact-fingerprint"),
    ):
        assert faults.worker_arguments(kind, target, root, pin) == [
            *faults.worker_arguments(kind, target, root),
            flag,
            pin,
        ]
    for kind, value in (("memo", pin), ("research", "--input")):
        with pytest.raises(ValueError, match="compact worker source binding"):
            faults.worker_arguments(kind, target, root, value)


def test_fault_receipt_cannot_overwrite_prior_evidence_or_exceed_bound(tmp_path):
    marker = tmp_path / "ready.json"
    faults.write_once(marker, {"first": True})
    original = marker.read_bytes()
    with pytest.raises(FileExistsError):
        faults.write_once(marker, {"first": False})
    assert marker.read_bytes() == original
    oversized = tmp_path / "oversized.json"
    with pytest.raises(ValueError):
        faults.write_once(oversized, {"value": "x" * 65536})
    assert not oversized.exists()


def test_fault_folder_is_fresh_and_scoped_to_owned_root(tmp_path):
    identity = str(uuid4())
    folder = faults.safe_folder(tmp_path, identity)
    assert folder.parent == tmp_path and folder.name == identity
    with pytest.raises(FileExistsError):
        faults.safe_folder(tmp_path, identity)
    with pytest.raises(ValueError):
        faults.safe_folder(tmp_path, "../escape")


@pytest.mark.parametrize(
    "boundary,expected",
    [
        ("before_model_reservation", ["pause", "reserve"]),
        ("after_model_reservation", ["reserve", "pause"]),
        ("committed_before_response", ["commit", "pause"]),
        ("cancellation_publication", ["pause", "commit"]),
    ],
)
def test_controlled_hooks_pause_on_the_exact_side_of_reservation_and_commit(
    tmp_path, monkeypatch, boundary, expected
):
    events = []
    name, owner = ("reserve", durable) if "reservation" in boundary else ("finish", store)

    def original(*args, **kwargs):
        events.append("reserve" if name == "reserve" else "commit")
        return "original-result"

    monkeypatch.setattr(owner, name, original)
    actual_write = faults.write_once

    def marker(path, value):
        events.append("pause")
        actual_write(path, value)

    monkeypatch.setattr(faults, "write_once", marker)
    (tmp_path / "continue.json").write_text("{}")
    current = durable.Claim("copilot", str(uuid4()), str(uuid4()), 1, 1)
    faults.install_pause(boundary, tmp_path, "copilot")
    assert getattr(owner, name)(None, current) == "original-result"
    assert events == expected
    receipt = json.loads((tmp_path / "ready.json").read_bytes())
    assert receipt["boundary"] == boundary and receipt["claim"]["token"] == 1


def test_after_claim_does_not_pause_incompatible_or_empty_queue(tmp_path, monkeypatch):
    monkeypatch.setattr(durable, "claim", lambda *args, **kwargs: None)
    faults.install_pause("after_claim", tmp_path, "copilot")
    assert durable.claim(None, "copilot", {}) is None
    assert not (tmp_path / "ready.json").exists()


def test_upload_boundary_runs_after_actual_upload_part_return_not_multipart_setup(
    tmp_path, monkeypatch
):
    calls = []
    monkeypatch.setattr(
        S3Backend, "_run", lambda self, method, **kwargs: calls.append(method) or {}
    )
    (tmp_path / "continue.json").write_text("{}")
    faults.install_pause("during_output_upload", tmp_path, "memo")
    backend = object.__new__(S3Backend)
    backend._run("create_multipart_upload")
    assert not (tmp_path / "ready.json").exists()
    backend._run("upload_part")
    assert calls == ["create_multipart_upload", "upload_part"]
    assert json.loads((tmp_path / "ready.json").read_bytes())["boundary"] == "during_output_upload"


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("MARKETLAB_PHASE7_LOOPBACK_RELAY_TESTS") != "1",
    reason="requires explicit owned loopback socket test opt-in",
)
def test_actual_opaque_relay_forwards_bytes_then_cuts_and_drains():
    upstream = socket.socket()
    upstream.bind(("127.0.0.1", 0))
    upstream.listen(1)
    upstream.settimeout(5)

    def serve():
        with upstream.accept()[0] as connection:
            connection.settimeout(5)
            payload = connection.recv(1024)
            connection.sendall(payload)
            try:
                connection.recv(1)
            except OSError:
                pass

    server = threading.Thread(target=serve)
    server.start()
    relay = faults.Relay("127.0.0.1", upstream.getsockname()[1])
    try:
        with socket.create_connection(("127.0.0.1", relay.port), timeout=5) as client:
            client.settimeout(5)
            client.sendall(b"opaque-owned-fixture")
            assert client.recv(1024) == b"opaque-owned-fixture"
            relay.disconnect()
            try:
                assert client.recv(1) == b""
            except ConnectionResetError:
                pass
    finally:
        relay.close()
        upstream.close()
        server.join(6)
    assert relay.accepted == 1 and relay.forwarded == 2 * len(b"opaque-owned-fixture")
    assert not server.is_alive()
    assert not relay.thread.is_alive() and all(not child.is_alive() for child in relay.children)


@pytest.mark.parametrize(
    "endpoint",
    [
        "ftp://model.invalid",
        "http://user:fixture@model.invalid",
        "http://model.invalid/nested",
        "https://model.invalid?query=value",
        "http://model.invalid/#fragment",
    ],
)
def test_model_proxy_rejects_nonbare_or_credentialed_endpoint_before_any_listener(
    tmp_path, monkeypatch, endpoint
):
    import http.server

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid endpoint attempted to create a listener")

    monkeypatch.setattr(http.server, "ThreadingHTTPServer", forbidden)
    with pytest.raises(ValueError):
        faults.ModelProxy(endpoint, tmp_path)


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("MARKETLAB_PHASE7_LOOPBACK_RELAY_TESTS") != "1",
    reason="requires explicit owned loopback socket test opt-in",
)
@pytest.mark.parametrize(
    "endpoint", ["http://model.example.invalid:11434", "https://model.example.invalid/"]
)
def test_model_proxy_accepts_declared_remote_endpoint_but_only_binds_loopback(
    tmp_path, monkeypatch, endpoint
):
    def forbidden(*args, **kwargs):
        pytest.fail("Constructing a proxy attempted an upstream connection")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    proxy = faults.ModelProxy(endpoint, tmp_path)
    try:
        assert proxy.server.server_address[0] == "127.0.0.1"
        assert proxy.url.startswith("http://127.0.0.1:")
        assert not proxy.started.is_set() and not proxy.handlers
    finally:
        proxy.close()
    assert not proxy.thread.is_alive()


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("MARKETLAB_PHASE7_LOOPBACK_RELAY_TESTS") != "1",
    reason="requires explicit owned loopback socket test opt-in",
)
@pytest.mark.parametrize("close_mode", ["orderly", "reset"])
def test_model_proxy_records_http_response_after_client_close_without_token_compute_claim(
    tmp_path, close_mode
):
    import hashlib
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import urlsplit

    upstream_started, finish_upstream = threading.Event(), threading.Event()
    response = b'{"done":true,"fixture":"synthetic HTTP response; no model invoked"}'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            length = int(self.headers["Content-Length"])
            self.rfile.read(length)
            upstream_started.set()
            if not finish_upstream.wait(5):
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server = threading.Thread(target=upstream.serve_forever, kwargs={"poll_interval": 0.05})
    server.start()
    proxy = faults.ModelProxy(f"http://127.0.0.1:{upstream.server_port}", tmp_path)
    client = None
    try:
        address = urlsplit(proxy.url)
        client = socket.create_connection(("127.0.0.1", address.port), timeout=5)
        client.sendall(
            b"POST /api/chat HTTP/1.1\r\nHost: owned-fixture\r\nContent-Length: 2\r\n\r\n{}"
        )
        assert upstream_started.wait(5)
        if close_mode == "reset":
            import struct

            client.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_LINGER,
                struct.pack("hh" if os.name == "nt" else "ii", 1, 0),
            )
        else:
            client.shutdown(socket.SHUT_RDWR)
        client.close()
        client = None
        import time

        deadline = time.monotonic() + 5
        while proxy.closed_at is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert proxy.closed_at is not None
        finish_upstream.set()
        assert proxy.completed.wait(5) and not proxy.error
        assert proxy.finished_at > proxy.closed_at
        assert proxy.response_sha256 == hashlib.sha256(response).hexdigest()
        assert (tmp_path / "genuine-upstream-response.bin").read_bytes() == response
    finally:
        if client is not None:
            client.close()
        finish_upstream.set()
        proxy.close()
        upstream.shutdown()
        upstream.server_close()
        server.join(5)
    assert not server.is_alive() and not proxy.thread.is_alive()
