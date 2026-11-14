"""Explicit bounded v2 CLI; no new public HTTP routes."""

import argparse
import json
import signal
import sys
import threading
from collections.abc import Sequence
from pathlib import Path

from prometheus_client import CollectorRegistry
from sqlalchemy import create_engine

from marketlab import workers
from marketlab.config import Settings
from marketlab.monitoring import export_metrics

from . import catalog, core, jobs, service
from .common import V2Error, read_json
from .ingestion_budget import OfficialBudget


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Binance spot v2 dataset operations")
    parser.add_argument(
        "--worker-root", help="Explicit provisioned root for distributed intake/read"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("capacity-initialize")
    command = commands.add_parser("worker-provision")
    command.add_argument("--host", required=True)
    command.add_argument("--label", required=True)
    command.add_argument("--root-id", required=True)
    command.add_argument("--root", required=True, type=Path)
    command = commands.add_parser("worker-recover")
    command.add_argument("--root-id", required=True)
    command.add_argument("--root", required=True, type=Path)
    command.add_argument("--recovery-token")
    command = commands.add_parser("worker-mode")
    command.add_argument("--mode", required=True, choices=("local", "distributed"))
    command.add_argument("--receipt", required=True, type=Path)
    for name in ("workers", "worker-attempts"):
        command = commands.add_parser(name)
        command.add_argument("--limit", type=int, default=25)
        command.add_argument("--cursor")
        if name == "worker-attempts":
            command.add_argument("--kind", choices=tuple(workers.CONTRACTS), required=True)
    for name in ("instrument-add", "instrument-update", "submit"):
        command = commands.add_parser(name)
        command.add_argument("--request", required=True, type=Path)
        command.add_argument("--key", required=True)
        if name == "instrument-update":
            command.add_argument("--instrument", required=True)
    command = commands.add_parser("import")
    command.add_argument("--manifest", required=True, type=Path)
    command.add_argument("--file", required=True, type=Path)
    command.add_argument("--key", required=True)
    for name, flag in (("imports", "import"), ("jobs", "submission"), ("inspect", "version")):
        command = commands.add_parser(name)
        command.add_argument("--" + flag, required=True, dest="identity")
    command = commands.add_parser("cancel")
    command.add_argument("--job", required=True)
    command.add_argument("--expected-revision", required=True, type=int)
    command.add_argument("--key", required=True)
    command = commands.add_parser("worker")
    command.add_argument("--max-jobs", type=int, default=1)
    command.add_argument("--submission")
    command.add_argument("--compact-official-sha256")
    command.add_argument("--wait-seconds", type=int, default=0)
    command.add_argument("--worker-root", default=argparse.SUPPRESS)
    for name in ("instruments", "datasets"):
        command = commands.add_parser(name)
        command.add_argument("--instrument")
        command.add_argument("--limit", type=int, default=25)
        command.add_argument("--cursor")
        if name == "instruments":
            command.add_argument("--base")
            command.add_argument("--quote")
        else:
            command.add_argument("--from-date")
            command.add_argument("--before-date")
    command = commands.add_parser("coverage")
    command.add_argument("--instrument", required=True)
    command.add_argument("--from-date", required=True)
    command.add_argument("--before-date", required=True)
    args = parser.parse_args(argv)
    settings = Settings()
    engine = create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
    from marketlab.db_transport import configure

    configure(engine)
    args.worker_root = args.worker_root or (
        str(settings.worker_root_id) if settings.worker_root_id else None
    )
    if args.command not in {
        "worker-provision",
        "worker-recover",
        "worker-mode",
        "workers",
        "worker-attempts",
    }:
        workers.bind_root(engine, settings.storage_path, args.worker_root)
    try:
        name = args.command
        if name == "worker-provision":
            result = workers.provision(engine, args.host, args.label, args.root_id, args.root)
        elif name == "worker-recover":
            result = workers.recover_root(engine, args.root_id, args.root, args.recovery_token)
        elif name == "worker-mode":
            result = workers.switch_mode(engine, args.mode, read_json(args.receipt))
        elif name == "workers":
            result = workers.inspect_workers(engine, args.limit, args.cursor)
        elif name == "worker-attempts":
            result = workers.inspect_attempts(engine, args.kind, args.limit, args.cursor)
        elif name == "capacity-initialize":
            from .admission import initialize

            result = initialize(engine, settings.storage_path)
        elif name == "instrument-add":
            result = core.add_instrument(engine, read_json(args.request), args.key)
        elif name == "instrument-update":
            result = core.update_instrument(
                engine, args.instrument, read_json(args.request), args.key
            )
        elif name == "submit":
            result = jobs.submit(engine, read_json(args.request), args.key)
        elif name == "import":
            result = service.import_file(
                engine, settings.storage_path, read_json(args.manifest), args.file, args.key
            )
        elif name == "imports":
            result = service.inspect_import(engine, args.identity)
        elif name == "jobs":
            result = jobs.inspect_submission(engine, args.identity)
        elif name == "cancel":
            result = jobs.cancel(engine, args.job, args.expected_revision, args.key)
        elif name == "inspect":
            result = catalog.inspect_version(engine, settings.storage_path, args.identity)
        elif name == "instruments":
            result = catalog.instruments(
                engine,
                identity=args.instrument,
                base=args.base,
                quote=args.quote,
                limit=args.limit,
                cursor=args.cursor,
            )
        elif name == "datasets":
            result = catalog.datasets(
                engine,
                identity=args.instrument,
                first=args.from_date,
                before=args.before_date,
                limit=args.limit,
                cursor=args.cursor,
            )
        elif name == "coverage":
            result = catalog.coverage(
                engine,
                args.instrument,
                args.from_date,
                args.before_date,
                root=settings.storage_path,
            )
        else:
            budget = None
            if args.compact_official_sha256 is not None:
                if args.submission is None or args.max_jobs != 1:
                    raise V2Error(
                        "invalid_request", "Compact ingestion requires one selected submission"
                    )
                budget = OfficialBudget(args.submission, args.compact_official_sha256)
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
                        "ingestion",
                        core.execution_identity()["execution_sha256"],
                        args.worker_root,
                        stop,
                    ),
                    export_metrics(settings, CollectorRegistry(), durable=True),
                ):
                    result = service.work(
                        engine,
                        settings.storage_path,
                        max_jobs=args.max_jobs,
                        submission_id=args.submission,
                        wait_seconds=args.wait_seconds,
                        stop_event=stop,
                        **({"budget": budget} if budget is not None else {}),
                    )
            finally:
                for number, handler in previous.items():
                    signal.signal(number, handler)
        print(json.dumps(core.wire(result), separators=(",", ":")))
        return 0
    except V2Error as error:
        print(json.dumps({"error": {"code": error.code, "message": str(error)}}), file=sys.stderr)
        return 2 if error.code in {"invalid_request", "unsupported_source"} else 1
    except Exception:
        print(
            '{"error":{"code":"operation_failed","message":"V2 dataset operation failed"}}',
            file=sys.stderr,
        )
        return 1
    finally:
        engine.dispose()
