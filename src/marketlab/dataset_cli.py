"""Synchronous local historical dataset ingestion and verified catalog inspection."""

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from typing import Never

from sqlalchemy import create_engine

from marketlab.config import Settings
from marketlab.datasets import DatasetError, ingest_day, inspect_version
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
    args = parser.parse_args(argv)
    try:
        if args.command == "ingest":
            validate_scope(args.symbol, args.date)
        elif len(args.version) != 64 or any(c not in "0123456789abcdef" for c in args.version):
            raise DatasetError("invalid dataset version")
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
            else:
                result = inspect_version(engine, settings.storage_path, args.version)
                if result is None:
                    raise DatasetError("dataset version not found")
            print(json.dumps(result, separators=(",", ":")))
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
