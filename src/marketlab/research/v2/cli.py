"""Explicit v2 numerical CLI dispatch with bounded worker controls."""

import argparse
import asyncio
import json
import signal
import sys
import threading
from pathlib import Path

from prometheus_client import CollectorRegistry
from sqlalchemy import create_engine

from marketlab.analytics.bars import BarService
from marketlab.analytics.v2 import BarsRequest
from marketlab.config import Settings
from marketlab.datasets.v2.common import V2Error
from marketlab.monitoring import export_metrics

from .service import ResearchService
from .spec import ResearchSpec


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    submit = commands.add_parser("submit")
    submit.add_argument("--spec", type=Path, required=True)
    submit.add_argument("--key", required=True)
    worker = commands.add_parser("worker")
    worker.add_argument("--max-runs", type=int, required=True)
    worker.add_argument("--run")
    worker.add_argument("--wait-seconds", type=int, default=0)
    for name in ("inspect", "results", "summary", "cancel"):
        command = commands.add_parser(name)
        command.add_argument("--run", required=True)
        if name == "cancel":
            command.add_argument("--expected-revision", type=int, required=True)
            command.add_argument("--key", required=True)
    bars = commands.add_parser("bars")
    bars.add_argument("--instrument", required=True)
    bars.add_argument("--version", action="append", required=True)
    bars.add_argument("--interval", choices=("1m", "5m"), required=True)
    bars.add_argument("--start", required=True)
    bars.add_argument("--end", required=True)
    return result


async def invoke(args: argparse.Namespace) -> object:
    settings = Settings()
    engine = create_engine(
        settings.sqlalchemy_url,
        pool_timeout=settings.database_connect_timeout_seconds,
        connect_args=settings.database_connect_args,
    )
    registry = CollectorRegistry()
    base = BarService(
        engine, settings.storage_path, settings.redis_url.get_secret_value(), registry=registry
    )
    research = ResearchService(base)
    try:
        if args.command == "submit":
            with args.spec.open("rb") as source:
                spec = ResearchSpec.parse(source.read(65537))
            run, replayed = await research.submit(spec, args.key)
            info = await asyncio.to_thread(research.inspect, run)
            return {"id": run, "state": info["state"], "replayed": replayed}
        if args.command == "worker":
            stop = threading.Event()
            previous = {
                number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)
            }
            for number in previous:
                signal.signal(number, lambda signum, frame: stop.set())
            try:
                with export_metrics(settings, registry):
                    return {
                        "attempted_runs": await research.work(
                            args.max_runs, args.run, args.wait_seconds, stop
                        )
                    }
            finally:
                for number, handler in previous.items():
                    signal.signal(number, handler)
        if args.command == "inspect":
            return await asyncio.to_thread(research.inspect, args.run)
        if args.command == "summary":
            return (await research.summary(args.run))[0]
        if args.command == "results":
            return (await asyncio.to_thread(research.read, args.run, "results"))[0]
        if args.command == "cancel":
            return await research.cancel(args.run, args.expected_revision, args.key)
        request = BarsRequest.create(
            versions=args.version,
            instrument_id=args.instrument,
            interval=args.interval,
            start=args.start,
            end=args.end,
        )
        return (await research.bars.read(request))[0]
    finally:
        await research.close()
        await base.close()
        await asyncio.to_thread(engine.dispose)


def main(arguments: list[str] | None = None) -> int:
    args = parser().parse_args(arguments)
    try:
        print(json.dumps(asyncio.run(invoke(args)), sort_keys=True, allow_nan=False))
        return 0
    except V2Error as error:
        print("Research operation failed: " + error.code, file=sys.stderr)
        return 2 if error.code == "invalid_request" else 1
    except (Exception, KeyboardInterrupt):
        print("Research operation failed", file=sys.stderr)
        return 1
