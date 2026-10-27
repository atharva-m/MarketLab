"""Bounded local copilot request, clarification, inspection and worker commands."""

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
from marketlab.copilot.model import Ollama
from marketlab.copilot.service import CopilotService
from marketlab.monitoring import export_metrics
from marketlab.research.service import ResearchService
from marketlab.research.spec import parse_json


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--request", type=Path, required=True)
    create.add_argument("--key", required=True)
    answer = commands.add_parser("answer")
    answer.add_argument("--request", required=True)
    answer.add_argument("--answer", type=Path, required=True)
    answer.add_argument("--key", required=True)
    commands.add_parser("inspect").add_argument("--request", required=True)
    worker = commands.add_parser("worker")
    worker.add_argument("--max-jobs", required=True, type=int)
    worker.add_argument("--request")
    return result


async def invoke(args: argparse.Namespace) -> object:
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
    service = CopilotService(
        research,
        Ollama(settings.ollama_url, settings.copilot_model, settings.copilot_model_digest),
        registry=registry,
    )
    try:
        if args.command in {"create", "answer"}:
            path = args.request if args.command == "create" else args.answer
            with path.open("rb") as source:
                value = parse_json(source.read(65537))
            request_id, revision, replayed = (
                await service.create(value, args.key)
                if args.command == "create"
                else await service.answer(args.request, value, args.key)
            )
            return {"request_id": request_id, "revision": revision, "replayed": replayed}
        if args.command == "worker":
            with export_metrics(settings, registry):
                return {"attempted_jobs": await service.work(args.max_jobs, args.request)}
        return await asyncio.to_thread(service.inspect, args.request)
    finally:
        await research.close()
        await bars.close()
        await asyncio.to_thread(engine.dispose)


def main() -> int:
    args = parser().parse_args()
    try:
        print(
            json.dumps(jsonable_encoder(asyncio.run(invoke(args))), sort_keys=True, allow_nan=False)
        )
        return 0
    except (Exception, KeyboardInterrupt):
        print("Copilot operation failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
