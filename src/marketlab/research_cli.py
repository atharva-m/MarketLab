"""Bounded manual research submission, workers and verified result retrieval."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from fastapi.encoders import jsonable_encoder
from prometheus_client import CollectorRegistry
from sqlalchemy import create_engine

from marketlab.analytics.bars import BarService
from marketlab.config import Settings
from marketlab.monitoring import export_metrics
from marketlab.research.service import ResearchService
from marketlab.research.spec import ResearchSpec, parse_json


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    submit = commands.add_parser("submit")
    submit.add_argument("--spec", type=Path, required=True)
    submit.add_argument("--key", required=True)
    worker = commands.add_parser("worker")
    worker.add_argument("--max-runs", type=int, required=True)
    worker.add_argument("--run")
    for name in ("inspect", "results", "summary"):
        commands.add_parser(name).add_argument("--run", required=True)
    return result


async def invoke(arguments: argparse.Namespace) -> object:
    settings = Settings()
    engine = create_engine(
        settings.sqlalchemy_url,
        pool_timeout=settings.database_connect_timeout_seconds,
        connect_args=settings.database_connect_args,
    )
    registry = CollectorRegistry()
    bars = BarService(
        engine, settings.storage_path, settings.redis_url.get_secret_value(), registry=registry
    )
    research = ResearchService(bars)
    try:
        if arguments.command == "submit":
            with arguments.spec.open("rb") as source:
                spec = ResearchSpec.create(parse_json(source.read(65537)))
            run, replayed = await research.submit(spec, arguments.key)
            return {"run_id": run, "replayed": replayed}
        if arguments.command == "worker":
            with export_metrics(settings, registry):
                return {"attempted_runs": await research.work(arguments.max_runs, arguments.run)}
        if arguments.command == "inspect":
            return await asyncio.to_thread(research.inspect, arguments.run)
        if arguments.command == "summary":
            return (await research.summary(arguments.run))[0]
        return (await asyncio.to_thread(research.read, arguments.run, "results"))[0]
    finally:
        await research.close()
        await bars.close()
        await asyncio.to_thread(engine.dispose)


def main() -> int:
    args = parser().parse_args()
    try:
        value = asyncio.run(invoke(args))
        print(json.dumps(jsonable_encoder(value), sort_keys=True, allow_nan=False))
        return 0
    except (Exception, KeyboardInterrupt):
        print("Research operation failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
