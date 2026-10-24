"""Synchronous local historical dataset ingestion and verified catalog inspection."""

import argparse
import json
import signal
import sys
import threading
from collections.abc import Sequence
from datetime import date
from typing import Never

from sqlalchemy import create_engine

from marketlab.config import Settings
from marketlab.datasets import DatasetError, ingest_day, inspect_version
from marketlab.datasets.jobs import inspect_submission, submit, validate_request, work
from marketlab.datasets.publication import run_claim
from marketlab.datasets.source import validate_scope


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        self.exit(2, "dataset-cli: invalid arguments; see --help\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _Parser(description="Publish/inspect R1 immutable historical datasets")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    ingest = commands.add_parser("ingest")
    ingest.add_argument("--symbol", required=True)
    ingest.add_argument("--date", required=True, type=date.fromisoformat)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--version", required=True)
    submission = commands.add_parser("submit")
    submission.add_argument("--symbols", nargs="+", required=True)
    submission.add_argument("--from-date", type=date.fromisoformat, required=True)
    submission.add_argument("--before-date", type=date.fromisoformat, required=True)
    submission.add_argument("--key", required=True)
    worker = commands.add_parser("worker")
    worker.add_argument("--max-jobs", type=int, default=1)
    worker.add_argument("--submission")
    worker.add_argument("--wait-seconds", type=int, default=0)
    status = commands.add_parser("jobs")
    status.add_argument("--submission", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "ingest":
            validate_scope(args.symbol, args.date)
        elif args.command == "inspect" and (
            len(args.version) != 64 or any(c not in "0123456789abcdef" for c in args.version)
        ):
            raise DatasetError("invalid dataset version")
        elif args.command == "submit":
            validate_request(args.symbols, args.from_date, args.before_date, args.key)
        elif args.command == "worker" and not (
            1 <= args.max_jobs <= 62 and 0 <= args.wait_seconds <= 3600
        ):
            raise DatasetError("invalid worker bounds")
    except DatasetError:
        parser.error("invalid scope")
    try:
        result: dict[str, object] | None
        settings = Settings()
        engine = create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
        try:
            if args.command == "ingest":
                manifest = ingest_day(
                    engine, settings.storage_path, symbol=args.symbol, trade_date=args.date
                )
                result = {
                    "dataset_version_id": manifest["dataset_version_id"],
                    "manifest_path": f"datasets/{manifest['dataset_version_id']}/"
                    f"venue=binance_spot/symbol={args.symbol}/date={args.date}/manifest.json",
                }
            elif args.command == "inspect":
                result = inspect_version(engine, settings.storage_path, args.version)
                if result is None:
                    raise DatasetError("dataset version not found")
            elif args.command == "submit":
                result = {
                    "submission_id": submit(
                        engine, args.symbols, args.from_date, args.before_date, args.key
                    )
                }
            elif args.command == "jobs":
                result = inspect_submission(engine, args.submission)
            else:
                stop = threading.Event()
                previous = {
                    number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)
                }
                for number in previous:
                    signal.signal(number, lambda signum, frame: stop.set())
                try:
                    attempted = work(
                        engine,
                        lambda current: run_claim(engine, settings.storage_path, current),
                        max_jobs=args.max_jobs,
                        submission_id=args.submission,
                        wait_seconds=args.wait_seconds,
                        stop_event=stop,
                    )
                finally:
                    for number, handler in previous.items():
                        signal.signal(number, handler)
                result = {"attempted_jobs": attempted}
            print(json.dumps(result, separators=(",", ":"), default=str))
        finally:
            engine.dispose()
    except DatasetError as error:
        print(f"dataset-cli: {error}", file=sys.stderr)
        return 1
    except Exception:
        print("dataset-cli: historical dataset operation failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
