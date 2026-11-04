"""Controlled protocol tests for the fault harness; never actual-model acceptance."""

import asyncio
import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from test_v2_copilot import candidate, request, selection

from marketlab.copilot.model import ModelFailure
from marketlab.copilot.v2 import durable
from marketlab.copilot.v2.model import DIGEST, MODEL, CopilotModel

location = Path(__file__).resolve().parents[1] / "scripts/v2_phase5_faults.py"
spec = importlib.util.spec_from_file_location("p5_fault_tests", location)
faults = importlib.util.module_from_spec(spec)
spec.loader.exec_module(faults)


@pytest.fixture
def native_server():
    class Handler(BaseHTTPRequestHandler):
        calls = 0

        def log_message(self, *_args):
            pass

        def do_GET(self):
            value = (
                {"models": [{"name": MODEL, "digest": DIGEST}]}
                if self.path == "/api/tags"
                else {"version": "protocol-fixture"}
            )
            self.respond(value)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert body["model"] == MODEL and body["think"] is False
            assert body["options"] == {"temperature": 0, "num_ctx": 8192, "num_predict": -1}
            Handler.calls += 1
            self.respond(
                {
                    "message": {"content": json.dumps(candidate())},
                    "done": True,
                    "done_reason": "stop",
                }
            )

        def respond(self, value):
            raw = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", Handler
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
        assert not thread.is_alive()


@pytest.mark.parametrize(
    "mode", ["unavailable", "digest", "swap", "malformed", "oversized", "length"]
)
async def test_proxy_preserves_native_identity_settings_and_separates_fault_bytes(
    native_server, tmp_path, monkeypatch, mode
):
    monkeypatch.setattr(faults, "BASE", tmp_path)
    folder = tmp_path / mode
    folder.mkdir()
    upstream, handler = native_server
    proxy = faults.FaultProxy(upstream, mode, folder)
    try:
        model = CopilotModel(proxy.url)
        with pytest.raises(ModelFailure):
            if mode in {"unavailable", "digest"}:
                await model.identify()
            else:
                assert await model.identify() == DIGEST
                await model.interpret(selection(), [request()], DIGEST)
    finally:
        await asyncio.to_thread(proxy.close)
    assert handler.calls == (0 if mode in {"unavailable", "digest"} else 1)
    if mode == "swap":
        mutations = [e for e in proxy.events if e.get("identity_mutation")]
        assert len(mutations) == 1 and mutations[0]["identity_mutation"] == "after_completion"
        first_tag = next(e for e in proxy.events if e["path"] == "/api/tags")
        assert "identity_mutation" not in first_tag
    assert all(
        e.get("native_sha256") != e.get("injected_sha256")
        for e in proxy.events
        if e.get("identity_mutation")
    )
    assert list(folder.glob("transport-*.json"))


def test_fault_path_containment_and_committed_reservation_stop_point(tmp_path, monkeypatch):
    monkeypatch.setattr(faults, "BASE", tmp_path)
    with pytest.raises(ValueError):
        faults.contained(tmp_path / ".." / "outside")
    folder = tmp_path / "native"
    folder.mkdir()
    committed = []
    monkeypatch.setattr(durable, "reserve", lambda *args, **kwargs: committed.append(True) or 1)
    clock = iter([0, 0, 181])
    monkeypatch.setattr(faults.time, "monotonic", lambda: next(clock, 181))
    faults.install_stop_point("copilot", "reserved", "request", folder)
    current = durable.Claim("copilot", "job", "owner", 1, 1, "request", 0)
    with pytest.raises(TimeoutError):
        durable.reserve(None, current, {}, DIGEST)
    assert committed == [True]
    receipt = json.loads((folder / "ready.json").read_bytes())
    assert receipt["claim"]["token"] == 1 and receipt["stage"] == "reserved"


def test_readiness_is_not_visible_during_partial_write(tmp_path, monkeypatch):
    monkeypatch.setattr(faults, "BASE", tmp_path)
    halfway, resume = threading.Event(), threading.Event()
    original_open = Path.open
    target = tmp_path / "ready.json"
    errors = []

    class SplitWriter:
        def __init__(self, output):
            self.output = output

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.output.__exit__(*args)

        def write(self, raw):
            middle = len(raw) // 2
            self.output.write(raw[:middle])
            self.output.flush()
            halfway.set()
            assert resume.wait(2)
            self.output.write(raw[middle:])

        def flush(self):
            self.output.flush()

        def fileno(self):
            return self.output.fileno()

    def instrument(path, mode="r", *args, **kwargs):
        output = original_open(path, mode, *args, **kwargs)
        return SplitWriter(output) if mode == "xb" else output

    monkeypatch.setattr(Path, "open", instrument)

    def publish():
        try:
            faults.write(target, {"stage": "complete", "body": "x" * 1024})
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=publish)
    thread.start()
    try:
        assert halfway.wait(2)
        assert not target.exists()
    finally:
        resume.set()
        thread.join(2)
    assert not thread.is_alive() and not errors
    assert json.loads(target.read_bytes())["stage"] == "complete"


def test_fault_receipt_publication_never_replaces_existing_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(faults, "BASE", tmp_path)
    target = tmp_path / "receipt.json"
    faults.write(target, {"original": True})
    with pytest.raises(FileExistsError):
        faults.write(target, {"original": False})
    assert json.loads(target.read_bytes()) == {"original": True}
