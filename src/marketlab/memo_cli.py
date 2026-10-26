"""Bounded local memo enqueue, inspection and exact Markdown read."""

import argparse
import asyncio
import json
import sys

from fastapi.encoders import jsonable_encoder
from sqlalchemy import create_engine

from marketlab.analytics.bars import BarService
from marketlab.config import Settings
from marketlab.memos.model import MemoModel
from marketlab.memos.service import MemoService
from marketlab.research.service import ResearchService


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("enqueue", "inspect", "read"):
        command = commands.add_parser(name)
        command.add_argument("--run", required=True)
        if name == "read":
            command.add_argument("--markdown", action="store_true")
    return result


async def invoke(args: argparse.Namespace) -> object:
    settings = Settings()
    engine = create_engine(
        settings.sqlalchemy_url,
        pool_timeout=settings.database_connect_timeout_seconds,
        connect_args=settings.database_connect_args,
    )
    bars = BarService(engine, settings.storage_path, settings.redis_url.get_secret_value())
    research = ResearchService(bars)
    memo = MemoService(
        research,
        MemoModel(settings.ollama_url, settings.copilot_model, settings.copilot_model_digest),
    )
    try:
        if args.command == "enqueue":
            run_id, replayed = await asyncio.to_thread(memo.enqueue, args.run)
            return {"run_id": run_id, "replayed": replayed}
        if args.command == "read":
            content, manifest = await asyncio.to_thread(memo.read, args.run)
            return (
                content
                if args.markdown
                else {"run_id": args.run, "content": content, "manifest": manifest}
            )
        return await asyncio.to_thread(memo.inspect, args.run)
    finally:
        await research.close()
        await bars.close()
        await asyncio.to_thread(engine.dispose)


def main() -> int:
    args = parser().parse_args()
    try:
        result = asyncio.run(invoke(args))
        if args.command == "read" and args.markdown:
            print(result, end="")
        else:
            print(json.dumps(jsonable_encoder(result), sort_keys=True, allow_nan=False))
        return 0
    except (Exception, KeyboardInterrupt):
        print("Memo operation failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
