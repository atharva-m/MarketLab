"""Owned P5-04 faults, invoked only by the independently reviewed evaluation runner.

The proxy retains genuine upstream and explicitly injected transport bytes
separately. Native deaths target only a held private Job; no original service,
model setting, persisted lease or job state is changed by fault injection.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()
BASE = ROOT / "artifacts/v2-phase5-20261102"
CLEAR = "clear-first_profile-1"
PROXY_MODES = ("unavailable", "digest", "swap", "malformed", "oversized", "length", "timeout")
NATIVE_STAGES = (
    ("copilot", "reserved"),
    ("copilot", "checkpointed"),
    ("copilot", "handoff"),
    ("memo", "staged"),
    ("memo", "published"),
)


def contained(path: Path) -> Path:
    absolute = path.absolute()
    if any(
        p.exists() and (p.is_symlink() or p.is_junction()) for p in (absolute, *absolute.parents)
    ):
        raise ValueError("Linked fault evidence path rejected")
    value = absolute.resolve()
    if not value.is_relative_to(BASE.resolve()) or value == BASE.resolve():
        raise ValueError("Named Phase 5 artifact path required")
    return value


def write(path: Path, value: Any) -> None:
    from marketlab.datasets.v2.core import wire

    raw = (json.dumps(wire(value), sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    if len(raw) > 2 * 1024**2:
        raise ValueError("Fault receipt exceeded bound")
    target = contained(path)
    temporary = contained(target.with_name(target.name + ".pending-" + uuid4().hex))
    with temporary.open("xb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    # Atomic creation without replacement on Windows and POSIX. Readers cannot
    # observe readiness until the complete, closed receipt has been published.
    os.link(temporary, target, follow_symlinks=False)
    temporary.unlink()


def now() -> dict[str, Any]:
    return {"utc": datetime.now(UTC).isoformat(), "monotonic": time.monotonic()}


async def upstream_request(url: str, method: str, path: str, body: bytes) -> tuple[int, bytes]:
    import httpx

    async with asyncio.timeout(125):
        async with httpx.AsyncClient(
            base_url=url,
            timeout=httpx.Timeout(125, connect=5),
            trust_env=False,
            follow_redirects=False,
            transport=httpx.AsyncHTTPTransport(retries=0),
        ) as client:
            async with client.stream(
                method, path, content=body, headers={"Content-Type": "application/json"}
            ) as response:
                buffer = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(buffer) + len(chunk) > 32768:
                        raise ValueError("Native upstream response exceeded bound")
                    buffer.extend(chunk)
                return response.status_code, bytes(buffer)


class FaultProxy:
    """Single owned loopback listener with bounded native forwarding and no retries."""

    def __init__(self, upstream: str, mode: str, folder: Path) -> None:
        from urllib.parse import urlsplit

        if mode not in PROXY_MODES or urlsplit(upstream).hostname != "127.0.0.1":
            raise ValueError("Reviewed loopback fault mode required")
        self.upstream, self.mode, self.folder = upstream, mode, contained(folder)
        self.stop = threading.Event()
        self.events: list[dict[str, Any]] = []
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:
                pass

            def do_GET(self) -> None:
                self.forward()

            def do_POST(self) -> None:
                self.forward()

            def forward(self) -> None:
                from marketlab.copilot.v2.model import DIGEST, MODEL

                started = time.monotonic()
                ordinal = len(proxy.events)
                event: dict[str, Any] = {
                    **now(),
                    "method": self.command,
                    "path": self.path,
                    "mode": proxy.mode,
                    "upstream_completed": False,
                }
                proxy.events.append(event)
                try:
                    if self.path not in {"/api/tags", "/api/version", "/api/chat"}:
                        raise ValueError("Unreviewed upstream path")
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 <= size <= 65536:
                        raise ValueError("Proxy request body exceeded bound")
                    body = self.rfile.read(size)
                    if len(body) != size:
                        raise ValueError("Incomplete proxy request")
                    status = 503 if proxy.mode == "unavailable" else 200
                    native = b"{}"
                    if proxy.mode != "unavailable":
                        status, native = asyncio.run(
                            upstream_request(proxy.upstream, self.command, self.path, body)
                        )
                        event.update(
                            upstream_completed=True,
                            upstream_finished=now(),
                            native_status=status,
                            native_bytes=len(native),
                            native_sha256=hashlib.sha256(native).hexdigest(),
                        )
                        (proxy.folder / f"native-{ordinal:02}.bin").write_bytes(native)
                    injected = native
                    if status == 200:
                        value = json.loads(native)
                        swap_after_call = proxy.mode == "swap" and any(
                            e["path"] == "/api/chat" and e["upstream_completed"]
                            for e in proxy.events
                        )
                        if (proxy.mode == "digest" or swap_after_call) and self.path == "/api/tags":
                            matches = [
                                m
                                for m in value["models"]
                                if m.get("name") == MODEL or m.get("model") == MODEL
                            ]
                            if len(matches) != 1 or matches[0]["digest"] != DIGEST:
                                raise ValueError("Genuine upstream identity prerequisite failed")
                            matches[0]["digest"] = "0" * 64
                            event["identity_mutation"] = (
                                "initial" if proxy.mode == "digest" else "after_completion"
                            )
                        elif self.path == "/api/chat":
                            if proxy.mode == "malformed":
                                value["message"]["content"] = "{malformed controlled transport"
                            elif proxy.mode == "oversized":
                                value["message"]["content"] = "x" * 32769
                            elif proxy.mode == "length":
                                value["done_reason"] = "length"
                            elif proxy.mode == "timeout":
                                event["stall_started"] = now()
                                proxy.stop.wait(max(0, 125 - (time.monotonic() - started)))
                                event["stall_ended"] = now()
                        injected = json.dumps(value, separators=(",", ":")).encode()
                    event.update(
                        injected_sha256=hashlib.sha256(injected).hexdigest(),
                        injected_bytes=len(injected),
                    )
                    (proxy.folder / f"injected-{ordinal:02}.bin").write_bytes(injected)
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(injected)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    try:
                        self.wfile.write(injected)
                        event["client_write"] = "completed"
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        event["client_write"] = "closed"
                except BaseException as error:
                    event["exception_type"] = type(error).__name__
                    self.close_connection = True
                finally:
                    event["ended"] = now()
                    write(proxy.folder / f"transport-{ordinal:02}.json", event)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.1}
        )
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self) -> None:
        self.stop.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(135)
        if self.thread.is_alive():
            raise TimeoutError("Owned proxy did not drain; upstream status is unknown")
        if any(e.get("exception_type") for e in self.events):
            raise ValueError("Proxy upstream prerequisite failed; do not dispatch more work")


def install_stop_point(kind: str, stage: str, identity: str, folder: Path) -> None:
    from marketlab.copilot.v2 import durable, store
    from marketlab.memos.v2.service import MemoService

    def stop(current: Any) -> None:
        if (
            current.kind != kind
            or (current.request_id if kind == "copilot" else current.identity) != identity
        ):
            return
        write(
            folder / "ready.json",
            {
                **now(),
                "pid": os.getpid(),
                "stage": stage,
                "claim": {
                    k: getattr(current, k)
                    for k in (
                        "kind",
                        "identity",
                        "owner",
                        "token",
                        "attempt",
                        "request_id",
                        "revision",
                        "relative_path",
                    )
                },
            },
        )
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            time.sleep(0.1)
        raise TimeoutError("Native fault controller did not stop its owned worker")

    if stage in {"reserved", "checkpointed"}:
        function = durable.reserve if stage == "reserved" else durable.checkpoint

        def wrapped(engine: Any, current: Any, *args: Any, **kwargs: Any) -> Any:
            result = function(engine, current, *args, **kwargs)
            stop(current)
            return result

        if stage == "reserved":
            durable.reserve = wrapped
        else:
            durable.checkpoint = wrapped
    elif stage == "handoff":
        finish = store.finish

        def handoff(engine: Any, current: Any, *args: Any, **kwargs: Any) -> Any:
            result = finish(engine, current, *args, **kwargs)
            stop(current)
            return result

        store.finish = handoff
    elif stage in {"staged", "published"}:
        method = MemoService.stage if stage == "staged" else MemoService.publish

        def memo(self: Any, current: Any, *args: Any, **kwargs: Any) -> Any:
            result = method(self, current, *args, **kwargs)
            stop(current)
            return result

        if stage == "staged":
            MemoService.stage = memo
        else:
            MemoService.publish = memo
    else:
        raise ValueError("Unreviewed stop point")


async def worker(args: argparse.Namespace) -> None:
    import v2_phase5_model_eval as evaluation

    if not os.environ.get("MARKETLAB_P5_OWNED_NONCE"):
        raise ValueError("Worker requires the outer owned supervisor")
    folder = contained(args.receipt_dir)
    cfg = evaluation.config(args.config)
    engine, bars, research, copilot, memo = evaluation.services(cfg)
    install_stop_point(args.kind, args.stage, args.identity, folder)
    try:
        service = copilot if args.kind == "copilot" else memo
        await service.work(1, args.identity)
        raise ValueError("Planned native stop point was not reached")
    finally:
        await evaluation.close_services(engine, bars, research)


async def wait_terminal(service: Any, identity: str) -> dict[str, Any]:
    deadline = time.monotonic() + 2160
    while time.monotonic() < deadline:
        info = await asyncio.to_thread(service.inspect, identity)
        if info["state"] in {"succeeded", "failed"}:
            return info
        await service.work(1, identity)
        await asyncio.sleep(0.25)
    raise TimeoutError("Fault recovery did not reach a bounded terminal outcome")


async def run(
    cfg: dict[str, Any], bound: dict[str, Any], folder: Path, *, config_path: Path
) -> dict[str, Any]:
    import v2_phase5_model_eval as evaluation
    from v2_phase4_lifecycle import OwnedJob

    from marketlab.copilot.v2 import durable
    from marketlab.datasets.v2.common import V2Error
    from marketlab.datasets.v2.core import transaction
    from marketlab.research.v2.spec import ResearchSpec

    if not os.environ.get("MARKETLAB_P5_OWNED_NONCE"):
        raise ValueError("Faults require the reviewed outer owned supervisor")
    folder = contained(folder)
    clear = next(c for c in bound["bound_fixture"]["copilot_cases"] if c["id"] == CLEAR)
    reference = next(
        m for m in bound["memo_runs"]["A"] if m["expected_spec"] == clear["expected_spec"]
    )
    engine, bars, research, copilot, memo = evaluation.services(cfg)
    result: dict[str, Any] = {
        "schema": "phase5-faults-v1",
        "functional": "incomplete",
        "started": now(),
        "cases": [],
        "limitations": [
            "Controlled transport faults are distinct from spontaneous model errors.",
            "Digest fault changes only proxy bytes, not installed model weights.",
            "Client timeout does not prove upstream token cancellation.",
        ],
    }
    prefix = "p5.fault." + uuid4().hex

    async def numerical(key: str, run_id: str | None = None) -> str:
        if run_id is None:
            run_id, _ = await research.submit(ResearchSpec.create(clear["expected_spec"]), key)
        await research.work(1, run_id)
        if research.inspect(run_id)["state"] != "succeeded":
            raise ValueError("Manual/numerical path was not usable")
        for kind in ("summary", "results"):
            body, expected = await asyncio.to_thread(research.read, run_id, kind)
            recorded = reference["numerical_evidence"]["hashes"][kind]
            if expected != recorded or evaluation.digest(body) != recorded:
                raise ValueError("Fault numerical result differs from frozen independent reference")
        return run_id

    try:
        for mode in PROXY_MODES:
            case = contained(folder / ("proxy-" + mode))
            case.mkdir()
            proxy = FaultProxy(cfg["ollama_url"], mode, case)
            original_url = copilot.model.url
            copilot.model.url = proxy.url
            entry: dict[str, Any] = {"mode": mode, "started": now(), "dispatches": []}
            try:
                identity, _, _ = await copilot.create(clear["request"], prefix + "." + mode)
                for _ in range(2):
                    started = time.monotonic()
                    await copilot.work(1, identity)
                    elapsed = time.monotonic() - started
                    entry["dispatches"].append(
                        {
                            "elapsed": elapsed,
                            "ledger": evaluation.ledger(engine, identity, "copilot"),
                        }
                    )
                    if mode == "timeout" and not 119 <= elapsed <= 150:
                        raise ValueError("Timeout did not hit the unchanged native120s bound")
                    info = copilot.inspect(identity)
                    if info["state"] in {"failed", "succeeded"}:
                        break
                    await asyncio.sleep(10.25)
                ledger = evaluation.ledger(engine, identity, "copilot")
                if ledger["handoffs"] != 0 or info["run_id"] is not None:
                    raise ValueError("Fault produced an unsafe handoff")
                expected_calls = (
                    0 if mode in {"unavailable", "digest"} else 2 if mode == "timeout" else 1
                )
                if len(ledger["calls"]) != expected_calls or info["state"] != "failed":
                    raise ValueError("Fault call accounting/terminal state mismatch")
                if mode in {"digest", "swap"} and not any(
                    e.get("identity_mutation") for e in proxy.events
                ):
                    raise ValueError("Planned identity boundary was not actually exercised")
                entry.update(identity=identity, ledger=ledger, outcome=info)
            finally:
                copilot.model.url = original_url
                try:
                    await asyncio.to_thread(proxy.close)
                finally:
                    entry.update(transports=proxy.events, ended=now())
                    write(case / "outcome.json", entry)
            entry["manual_run"] = await numerical(prefix + ".manual." + mode)
            result["cases"].append(entry)

        for kind, stage in NATIVE_STAGES:
            case = contained(folder / (kind + "-" + stage))
            case.mkdir()
            if kind == "copilot":
                identity, _, _ = await copilot.create(clear["request"], prefix + "." + stage)
            else:
                identity = await numerical(prefix + ".memo." + stage)
            job = OwnedJob()
            log = (case / "worker.log").open("wb")
            child = None
            try:
                child = job.spawn(
                    [
                        sys.executable,
                        "-B",
                        str(SELF),
                        "worker",
                        "--config",
                        str(config_path),
                        "--identity",
                        identity,
                        "--kind",
                        kind,
                        "--stage",
                        stage,
                        "--receipt-dir",
                        str(case),
                    ],
                    cwd=ROOT,
                    env=evaluation.environment(cfg),
                    output=log,
                )
                deadline = time.monotonic() + 150
                while not (case / "ready.json").exists():
                    if child.poll() is not None or time.monotonic() >= deadline:
                        raise ValueError("Owned worker did not reach its planned native stop point")
                    await asyncio.sleep(0.1)
                ready = evaluation.read(case / "ready.json")
                record = child.record()
                if record["pid"] != ready["pid"]:
                    raise ValueError("Native worker receipt identity mismatch")
                before = evaluation.ledger(engine, identity, kind)
                job.terminate()
                await asyncio.to_thread(child.wait, 10)
                await asyncio.to_thread(job.wait_empty, 10)
                write(
                    case / "native-death.json",
                    {"worker": record, "ready": ready, "before": before, **now()},
                )
            finally:
                if child is not None and child.poll() is None:
                    job.terminate()
                    await asyncio.to_thread(child.wait, 10)
                    await asyncio.to_thread(job.wait_empty, 10)
                job.close()
                log.close()
            service = copilot if kind == "copilot" else memo
            # Real DB clock eligibility/lease expiry; no timestamp/state editing.
            info = await wait_terminal(service, identity)
            ledger = evaluation.ledger(engine, identity, kind)
            expected = 2 if stage == "reserved" else 1
            if info["state"] != "succeeded" or len(ledger["calls"]) != expected:
                raise ValueError("Native recovery refunded/spent an unexpected call or failed")
            if kind == "copilot":
                if info["outcome"] != "submitted" or ledger["handoffs"] != 1:
                    raise ValueError("Native recovery duplicated/missed research handoff")
                await numerical(prefix + ".recovered." + stage, info["run_id"])
            elif len(info["memo"].strip().split("\n\n")) != 3:
                raise ValueError("Recovered memo is not a grounded three-paragraph artifact")
            before_stale = evaluation.ledger(engine, identity, kind)
            stale = durable.Claim(**ready["claim"])
            try:
                with transaction(engine) as connection:
                    durable.fence(connection, stale)
            except V2Error as error:
                if error.code != "revision_conflict":
                    raise
            else:
                raise ValueError("Stale native publisher was not rejected")
            if evaluation.ledger(engine, identity, kind) != before_stale:
                raise ValueError("Stale rejection changed call/handoff records")
            entry = {
                "kind": kind,
                "stage": stage,
                "identity": identity,
                "outcome": info,
                "ledger": ledger,
                "stale_publisher": "rejected",
                "ended": now(),
            }
            write(case / "outcome.json", entry)
            result["cases"].append(entry)
        result["functional"] = "passed"
        return result
    except BaseException as error:
        result.update(functional="failed", exception_type=type(error).__name__)
        raise
    finally:
        result["ended"] = now()
        write(folder / "faults.json", result)
        await evaluation.close_services(engine, bars, research)


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    child = commands.add_parser("worker")
    child.add_argument("--config", type=Path, required=True)
    child.add_argument("--identity", required=True)
    child.add_argument("--kind", choices=("copilot", "memo"), required=True)
    child.add_argument(
        "--stage",
        choices=("reserved", "checkpointed", "handoff", "staged", "published"),
        required=True,
    )
    child.add_argument("--receipt-dir", type=Path, required=True)
    asyncio.run(worker(parser.parse_args()))


if __name__ == "__main__":
    main()
