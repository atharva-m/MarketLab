"""Bounded explicit v2 CLI; no automatic inference from request submission."""

import argparse
import asyncio
import json
import signal
import sys
import threading
import time
from pathlib import Path

from prometheus_client import CollectorRegistry
from sqlalchemy import create_engine

from marketlab import workers
from marketlab.analytics.bars import BarService
from marketlab.config import Settings
from marketlab.datasets.v2.common import V2Error, digest, parse_json
from marketlab.memos.v2.model import MemoModel
from marketlab.memos.v2.service import MemoService
from marketlab.monitoring import export_metrics
from marketlab.research.v2.service import ResearchService

from .model import CopilotModel
from .service import CopilotService


def parser(kind: str) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--worker-root", help="Explicit provisioned root for distributed intake/read"
    )
    commands = result.add_subparsers(dest="command", required=True)
    if kind == "copilot":
        create = commands.add_parser("create")
        create.add_argument("--request", type=Path, required=True)
        create.add_argument("--key", required=True)
        answer = commands.add_parser("answer")
        answer.add_argument("--request", required=True)
        answer.add_argument("--answer", type=Path, required=True)
        answer.add_argument("--key", required=True)
        commands.add_parser("inspect").add_argument("--request", required=True)
    else:
        enqueue = commands.add_parser("enqueue")
        enqueue.add_argument("--run", required=True)
        enqueue.add_argument("--key", required=True)
        commands.add_parser("inspect").add_argument("--run", required=True)
        commands.add_parser("read").add_argument("--run", required=True)
    worker = commands.add_parser("worker")
    worker.add_argument("--max-jobs", required=True, type=int)
    worker.add_argument("--wait-seconds", default=0, type=int)
    worker.add_argument("--request" if kind == "copilot" else "--run")
    worker.add_argument("--worker-root", default=argparse.SUPPRESS)
    cancel = commands.add_parser("cancel")
    cancel.add_argument("--job" if kind == "copilot" else "--run", required=True)
    cancel.add_argument("--expected-state-revision", required=True, type=int)
    cancel.add_argument("--key", required=True)
    return result


async def invoke(kind: str, args: argparse.Namespace) -> object:
    settings = Settings()
    engine = create_engine(
        settings.sqlalchemy_url,
        pool_timeout=settings.database_connect_timeout_seconds,
        connect_args=settings.database_connect_args,
    )
    from marketlab.db_transport import configure

    configure(engine)
    args.worker_root = args.worker_root or (
        str(settings.worker_root_id) if settings.worker_root_id else None
    )
    workers.bind_root(engine, settings.storage_path, args.worker_root)
    base = BarService(engine, settings.storage_path, settings.redis_url.get_secret_value())
    research = ResearchService(base)
    copilot = CopilotService(
        research,
        CopilotModel(settings.ollama_url, settings.copilot_model, settings.copilot_model_digest),
    )
    memo = MemoService(
        research,
        MemoModel(settings.ollama_url, settings.copilot_model, settings.copilot_model_digest),
    )
    try:
        if args.command == "cancel":
            from .durable import cancel

            return await asyncio.to_thread(
                cancel,
                engine,
                kind,
                args.job if kind == "copilot" else args.run,
                args.expected_state_revision,
                args.key,
            )
        if args.command == "worker":
            if not 1 <= args.max_jobs <= 62 or not 0 <= args.wait_seconds <= 3600:
                raise V2Error("invalid_request", "Invalid bounded worker invocation")
            service = copilot if kind == "copilot" else memo
            target = args.request if kind == "copilot" else args.run
            deadline, attempted = time.monotonic() + args.wait_seconds, 0
            stop = threading.Event()
            previous = {
                number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)
            }
            for number in previous:
                signal.signal(number, lambda signum, frame: stop.set())
            try:
                with (
                    workers.lifecycle(
                        engine,
                        settings.storage_path,
                        kind,
                        digest(service.execution),
                        args.worker_root,
                        stop,
                    ),
                    export_metrics(settings, CollectorRegistry(), durable=True),
                ):
                    while attempted < args.max_jobs and not stop.is_set():
                        attempted += await service.work(1, target)
                        if time.monotonic() >= deadline:
                            break
                        await asyncio.sleep(min(0.25, max(0, deadline - time.monotonic())))
            finally:
                for number, handler in previous.items():
                    signal.signal(number, handler)
            return {"attempted_jobs": attempted}
        if kind == "memo":
            if args.command == "enqueue":
                return await asyncio.to_thread(
                    memo.enqueue, args.run, {"schema": "memo-request-v2"}, args.key
                )
            if args.command == "read":
                content, manifest = await asyncio.to_thread(memo.read, args.run)
                return {"run_id": args.run, "memo": content, "manifest": manifest}
            return await asyncio.to_thread(memo.inspect, args.run)
        if args.command in {"create", "answer"}:
            path = args.request if args.command == "create" else args.answer
            with path.open("rb") as source:
                value = parse_json(source.read(65537))
            request_id, revision, replayed = (
                await copilot.create(value, args.key)
                if args.command == "create"
                else await copilot.answer(args.request, value, args.key)
            )
            return {"request_id": request_id, "revision": revision, "replayed": replayed}
        return await asyncio.to_thread(copilot.inspect, args.request)
    finally:
        await research.close()
        await base.close()
        await asyncio.to_thread(engine.dispose)


def main(kind: str, argv: list[str]) -> int:
    args = parser(kind).parse_args(argv)
    try:
        print(json.dumps(asyncio.run(invoke(kind, args)), sort_keys=True, allow_nan=False))
        return 0
    except (Exception, KeyboardInterrupt):
        print("V2 model workflow operation failed", file=sys.stderr)
        return 1
