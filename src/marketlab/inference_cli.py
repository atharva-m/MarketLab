"""Bounded shared inference worker with nonpreemptive copilot priority."""

import argparse
import asyncio
import json
import sys

from sqlalchemy import create_engine

from marketlab.analytics.bars import BarService
from marketlab.config import Settings
from marketlab.copilot import store as copilot_store
from marketlab.copilot.model import Ollama
from marketlab.copilot.service import CopilotService
from marketlab.inference import admission
from marketlab.memos import store as memo_store
from marketlab.memos.model import MemoModel
from marketlab.memos.service import MemoService
from marketlab.research.service import ResearchService
from marketlab.research.spec import ResearchError


async def work(copilot: CopilotService, memo: MemoService, maximum: int) -> int:
    if type(maximum) is not int or not 1 <= maximum <= 62:
        raise ResearchError("Invalid bounded inference worker limit")
    attempted = 0
    while attempted < maximum:
        async with admission(copilot.engine) as acquired:
            if not acquired:
                break
            current = await asyncio.to_thread(copilot_store.claim, copilot.engine)
            if current is not None:
                await copilot.execute(current)
            else:
                pending = await asyncio.to_thread(memo_store.claim, memo.engine)
                if pending is None:
                    break
                await memo.execute(pending)
            attempted += 1
    return attempted


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    worker = result.add_subparsers(dest="command", required=True).add_parser("worker")
    worker.add_argument("--max-jobs", required=True, type=int)
    return result


async def invoke(maximum: int) -> dict[str, int]:
    settings = Settings()
    engine = create_engine(
        settings.sqlalchemy_url,
        pool_timeout=settings.database_connect_timeout_seconds,
        connect_args=settings.database_connect_args,
    )
    bars = BarService(engine, settings.storage_path, settings.redis_url.get_secret_value())
    research = ResearchService(bars)
    copilot = CopilotService(
        research, Ollama(settings.ollama_url, settings.copilot_model, settings.copilot_model_digest)
    )
    memo = MemoService(
        research,
        MemoModel(settings.ollama_url, settings.copilot_model, settings.copilot_model_digest),
    )
    try:
        return {"attempted_jobs": await work(copilot, memo, maximum)}
    finally:
        await research.close()
        await bars.close()
        await asyncio.to_thread(engine.dispose)


def main() -> int:
    args = parser().parse_args()
    try:
        print(json.dumps(asyncio.run(invoke(args.max_jobs)), sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt):
        print("Inference operation failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
