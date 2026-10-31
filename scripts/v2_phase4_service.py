"""Explicit API and targeted workers for the owned Phase 4 acceptance run."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]
OWNER = "v2-phase4-20261030"


def write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


def load_config(path: Path) -> dict[str, Any]:
    cfg = json.loads(path.read_text())
    url = sa.engine.make_url(cfg["database_url"])
    expected = ROOT / "artifacts/v2-phase4-20261030/storage/browser"
    if (
        cfg["owner"] != OWNER
        or (url.host, url.port, url.database) != ("127.0.0.1", 55452, "v2p4_browser")
        or cfg["redis_url"] != "redis://127.0.0.1:56394/0"
        or Path(cfg["storage_path"]).resolve() != expected.resolve()
    ):
        raise ValueError("Configuration must address the existing owned browser stack")
    for directory in (expected, *expected.parents):
        if directory.is_symlink() or directory.is_junction():
            raise ValueError("Owned storage path contains an unsafe link")
    return cfg


def require_ready(cfg: dict[str, Any]) -> None:
    from marketlab.datasets.v2 import admission

    engine = sa.create_engine(
        cfg["database_url"],
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
    )
    try:
        with engine.connect() as connection:
            admission.require(connection, Path(cfg["storage_path"]))
    finally:
        engine.dispose()


async def research(cfg: dict[str, Any], run_id: str, stop: threading.Event) -> dict[str, Any]:
    from marketlab.analytics.bars import BarService
    from marketlab.research.v2 import store
    from marketlab.research.v2.service import ResearchService

    engine = sa.create_engine(cfg["database_url"])
    bars = BarService(engine, Path(cfg["storage_path"]), cfg["redis_url"])
    service = ResearchService(bars)
    try:

        async def cancellation() -> None:
            while not await asyncio.to_thread(stop.wait, 0.1):
                pass
            current = store.inspect(engine, run_id)
            if current["state"] in {"queued", "retry_wait", "running"}:
                await service.cancel(
                    run_id,
                    current["revision"],
                    f"p4-completion-stop-{run_id}-{current['revision']}",
                )

        stopper = asyncio.create_task(cancellation())
        try:
            attempted = await service.work(1, run_id, stop_event=stop)
        finally:
            if stop.is_set():
                await stopper
            else:
                stopper.cancel()
                try:
                    await stopper
                except asyncio.CancelledError:
                    pass
        current = store.inspect(engine, run_id)
        result = {
            "run_id": run_id,
            "attempted_runs": attempted,
            "state": current["state"],
            "attempt_count": current["attempt_count"],
        }
    finally:
        await service.close()
        await bars.close()
        engine.dispose()
    result["drain"] = {
        "compute": bars.reader.compute.snapshot(),
        "verifier": bars.reader.verifier.snapshot(),
    }
    if result["drain"]["compute"]["active"] != 0:
        raise RuntimeError("Research compute did not drain")
    return result


def ingestion(
    cfg: dict[str, Any], submission: str, max_jobs: int, stop: threading.Event
) -> dict[str, Any]:
    from marketlab.datasets.v2 import jobs, service

    engine = sa.create_engine(cfg["database_url"])
    try:
        current = jobs.inspect_submission(engine, submission)
        if not 1 <= max_jobs <= current["submission"]["child_count"] <= 62:
            raise ValueError("Targeted ingestion child bound is invalid")
        result = service.work(
            engine,
            Path(cfg["storage_path"]),
            max_jobs=max_jobs,
            submission_id=submission,
            stop_event=stop,
        )
        return {
            "submission_id": submission,
            "worker": result,
            "submission": jobs.inspect_submission(engine, submission),
        }
    finally:
        engine.dispose()


def run_api(cfg: dict[str, Any], stop: threading.Event) -> dict[str, Any]:
    import uvicorn
    from pydantic import SecretStr

    from marketlab.app import create_app
    from marketlab.config import Settings

    settings = Settings(
        _env_file=None,
        environment="local",
        database_url=SecretStr(cfg["database_url"]),
        database_password=None,
        redis_url=SecretStr(cfg["redis_url"]),
        storage_path=Path(cfg["storage_path"]),
        ollama_url="http://127.0.0.1:11449",
        metrics_port=0,
        metrics_bind="127.0.0.1",
        dependency_timeout_seconds=3,
        database_connect_timeout_seconds=5,
    )
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings), host="127.0.0.1", port=55176, log_level="info", access_log=False
        )
    )
    finished = threading.Event()

    def watch() -> None:
        while not finished.wait(0.1):
            if stop.is_set():
                server.should_exit = True
                return

    watcher = threading.Thread(target=watch)
    watcher.start()
    try:
        if os.name == "nt":
            with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
                runner.run(server.serve())
        else:
            server.run()
        return {"server_exit": True, "api_port": 55176}
    finally:
        finished.set()
        watcher.join(timeout=5)
        if watcher.is_alive():
            raise TimeoutError("API stop watcher did not join")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("api", "worker"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--kind", choices=("ingestion", "research"))
    parser.add_argument("--target", type=UUID)
    parser.add_argument("--max-jobs", type=int, default=1)
    args = parser.parse_args()
    if args.role == "worker" and (args.kind is None or args.target is None):
        parser.error("Worker requires kind and one exact target UUID")
    cfg = load_config(args.config)
    require_ready(cfg)
    args.folder.mkdir(parents=True, exist_ok=False)
    nonce = os.environ["MARKETLAB_PHASE4_RUN_NONCE"]
    stop, finished = threading.Event(), threading.Event()
    errors: list[str] = []

    def request_stop(*_: Any) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    def watch() -> None:
        deadline = time.monotonic() + 7200
        while not finished.wait(0.1):
            path = args.folder / "stop.json"
            if path.exists():
                try:
                    if json.loads(path.read_text()) == {"nonce": nonce}:
                        stop.set()
                except (OSError, ValueError) as error:
                    errors.append(type(error).__name__)
            if time.monotonic() > deadline:
                stop.set()

    watcher = threading.Thread(target=watch)
    record = {
        "role": args.role,
        "state": "running",
        "pid": os.getpid(),
        "started_utc": datetime.now(UTC).isoformat(),
    }
    write(args.folder / "ready.json", {"pid": os.getpid(), "role": args.role})
    watcher.start()
    try:
        if args.role == "api":
            result = run_api(cfg, stop)
        elif args.kind == "research":
            result = asyncio.run(research(cfg, str(args.target), stop))
        else:
            result = ingestion(cfg, str(args.target), args.max_jobs, stop)
        record.update(state="passed", result=result)
        return 0
    except BaseException as error:
        record.update(state="failed", error_type=type(error).__name__)
        raise
    finally:
        finished.set()
        watcher.join(timeout=10)
        if watcher.is_alive():
            record.update(state="failed", error_type="WatcherJoinTimeout")
        record.update(
            finished_utc=datetime.now(UTC).isoformat(),
            cooperative_stop_requested=stop.is_set(),
            stop_observation_errors=errors,
        )
        write(args.folder / "receipt.json", record)
        if watcher.is_alive():
            raise TimeoutError("Worker stop watcher did not join")


if __name__ == "__main__":
    raise SystemExit(main())
