"""Actual v2 source/readback and native crash gates on explicitly owned resources.

Credentials are read from an ignored local connection document, never logged.
Failpoints exist only in this harness and run in killable child processes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import time
import zipfile
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import sqlalchemy as sa

from marketlab.datasets.v2 import catalog, core, jobs, service
from marketlab.datasets.v2.common import V2Error, canonical_json, sha256_file


def write(path: Path, value: object) -> None:
    path.write_bytes(canonical_json(value))


def config(path: Path) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if value.get("owner") != "v2-phase2-20261028":
        raise ValueError("Expected explicitly owned Phase 2 resources")
    return value


def environment(value: dict[str, Any]) -> dict[str, str]:
    return dict(
        os.environ,
        MARKETLAB_DATABASE_URL=value["database_url"],
        MARKETLAB_STORAGE_PATH=value["storage_path"],
    )


def last_job(engine: sa.Engine, submission: str) -> dict[str, Any]:
    return jobs.inspect_submission(engine, submission)["jobs"][0]  # type: ignore[no-any-return]


def run_worker(value: dict[str, Any], submission: str, evidence: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "marketlab.dataset_cli",
            "v2",
            "worker",
            "--max-jobs",
            "1",
            "--submission",
            submission,
        ],
        env=environment(value),
        capture_output=True,
        text=True,
        timeout=1800,
    )
    # CLI output is deliberately safe; no command contains credentials.
    write(
        evidence,
        {"exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr},
    )
    if completed.returncode != 0:
        raise V2Error("acceptance_failed", "Separate CLI worker failed")


def cli_import(
    value: dict[str, Any], manifest: Path, source: Path, key: str, receipt: Path
) -> dict[str, Any]:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "marketlab.dataset_cli",
            "v2",
            "import",
            "--manifest",
            str(manifest),
            "--file",
            str(source),
            "--key",
            key,
        ],
        env=environment(value),
        capture_output=True,
        text=True,
        timeout=1800,
    )
    write(
        receipt,
        {"exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr},
    )
    if completed.returncode != 0:
        raise V2Error("acceptance_failed", "Separate CLI import failed")
    parsed: dict[str, Any] = json.loads(completed.stdout)
    return parsed


def independent_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while data := stream.read(1048576):
            hasher.update(data)
    return hasher.hexdigest()


def raw_reference(
    root: Path, job: dict[str, Any], symbol: str, day: str, evidence: Path, *, convert: bool
) -> dict[str, Any]:
    """Independent raw-provider parser/oracle; never call production normalization."""
    name = f"{symbol}-trades-{day}.zip"
    archives = list((root / "attempts-v2" / job["job_id"]).glob("*/ */source/" + name))
    # Explicit recursive ownership root, not a search of original artifact storage.
    archives = list((root / "attempts-v2" / job["job_id"]).rglob(name))
    if len(archives) != 1:
        raise V2Error("acceptance_failed", "Expected one retained owned official source")
    archive = archives[0]
    checksum = archive.with_name(name + ".CHECKSUM")
    checksum_text = checksum.read_text(encoding="ascii").strip().split()
    actual_hash = independent_hash(archive)
    if (
        len(checksum_text) != 2
        or checksum_text[1].lstrip("*") != name
        or checksum_text[0].lower() != actual_hash
    ):
        raise V2Error("acceptance_failed", "Independent provider checksum check failed")
    database = evidence / (symbol + "-independent.sqlite")
    logical = hashlib.sha256()
    count = raw_count = 0
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    schema = pa.schema(
        [
            pa.field("source_trade_id", pa.string(), nullable=False),
            pa.field("executed_at", pa.timestamp("us", tz="UTC"), nullable=False),
            *(
                pa.field(k, pa.decimal128(38, 18), nullable=False)
                for k in ("price", "quantity", "quote_quantity")
            ),
            pa.field("is_buyer_maker", pa.bool_()),
            pa.field("is_best_match", pa.bool_()),
        ]
    )
    with closing(sqlite3.connect(database)) as db:
        db.execute("PRAGMA temp_store=FILE")
        db.execute("PRAGMA cache_size=-8192")
        db.execute(
            "CREATE TABLE r(id INTEGER PRIMARY KEY,t INTEGER,p TEXT,q TEXT,"
            "v TEXT,m INTEGER,b INTEGER)"
        )
        with zipfile.ZipFile(archive) as zipped:
            if zipped.namelist() != [name.removesuffix(".zip") + ".csv"]:
                raise V2Error("acceptance_failed", "Independent archive member check failed")
            with zipped.open(zipped.namelist()[0]) as incoming:
                for row in csv.reader(io.TextIOWrapper(incoming, encoding="ascii"), strict=True):
                    if len(row) != 7:
                        raise V2Error("acceptance_failed", "Independent provider row shape failed")
                    raw_count += 1
                    timestamp = int(row[4]) * (1000 if day < "2025-01-01" else 1)
                    observed = epoch + timedelta(microseconds=timestamp)
                    if (
                        observed.date().isoformat() != day
                        or row[5] not in {"True", "False"}
                        or row[6] not in {"True", "False"}
                    ):
                        raise V2Error("acceptance_failed", "Independent provider date/flags failed")
                    values = (
                        int(row[0]),
                        timestamp,
                        *(format(Decimal(row[k]), ".18f") for k in (1, 2, 3)),
                        int(row[5] == "True"),
                        int(row[6] == "True"),
                    )
                    previous = db.execute("SELECT * FROM r WHERE id=?", (values[0],)).fetchone()
                    if previous is not None and previous != values:
                        raise V2Error(
                            "acceptance_failed", "Independent provider duplicate conflict"
                        )
                    if previous is None:
                        db.execute("INSERT INTO r VALUES (?,?,?,?,?,?,?)", values)
        db.commit()
        csv_stream = (
            (evidence / "SOLUSDT-canonical.csv").open("x", encoding="utf-8", newline="")
            if convert
            else None
        )
        writer = (
            pq.ParquetWriter(evidence / "SOLUSDT-canonical.parquet", schema, compression="zstd")
            if convert
            else None
        )
        try:
            if csv_stream is not None:
                csv_stream.write(",".join(schema.names) + "\n")
            cursor = db.execute("SELECT * FROM r ORDER BY id")
            while batch := cursor.fetchmany(16384):
                arrow_rows = []
                for row in batch:
                    instant = epoch + timedelta(microseconds=row[1])
                    timestamp_text = (
                        instant.strftime("%Y-%m-%dT%H:%M:%S.") + f"{instant.microsecond:06d}Z"
                    )
                    logical.update(
                        (
                            json.dumps(
                                [
                                    "binance:spot:" + symbol,
                                    str(row[0]),
                                    timestamp_text,
                                    *row[2:5],
                                    bool(row[5]),
                                    bool(row[6]),
                                ],
                                separators=(",", ":"),
                                ensure_ascii=True,
                            )
                            + "\n"
                        ).encode("ascii")
                    )
                    count += 1
                    if csv_stream is not None:
                        csv_stream.write(
                            ",".join(
                                [
                                    str(row[0]),
                                    timestamp_text,
                                    *row[2:5],
                                    str(bool(row[5])).lower(),
                                    str(bool(row[6])).lower(),
                                ]
                            )
                            + "\n"
                        )
                        arrow_rows.append(
                            dict(
                                zip(
                                    schema.names,
                                    [
                                        str(row[0]),
                                        instant,
                                        *(Decimal(v) for v in row[2:5]),
                                        bool(row[5]),
                                        bool(row[6]),
                                    ],
                                    strict=True,
                                )
                            )
                        )
                if writer is not None:
                    writer.write_table(pa.Table.from_pylist(arrow_rows, schema=schema))
        finally:
            if csv_stream is not None:
                csv_stream.close()
            if writer is not None:
                writer.close()
    return {
        "archive": str(archive),
        "archive_sha256": actual_hash,
        "checksum_sha256": independent_hash(checksum),
        "raw_rows": raw_count,
        "rows": count,
        "logical_sha256": logical.hexdigest(),
        "parser_source_sha256": independent_hash(Path(__file__)),
        "source": "independent raw ZIP parser",
    }


def actual(
    engine: sa.Engine, value: dict[str, Any], evidence: Path, invocation: str
) -> dict[str, Any]:
    from datetime import timedelta

    root = Path(value["storage_path"])
    root.mkdir(parents=True, exist_ok=True)
    core.add_instrument(
        engine,
        dict(
            venue_id="binance",
            market="spot",
            source_symbol="SOLUSDT",
            base_asset="SOL",
            quote_asset="USDT",
            display_name="SOL/USDT",
            trade_id_order="numeric",
            adapter="binance_daily",
        ),
        invocation + "-sol",
    )
    sources = []
    for symbol, day in (("BTCUSDT", "2025-02-01"), ("SOLUSDT", "2025-03-01")):
        before = (datetime.strptime(day, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()
        request = dict(
            schema="daily-ingestion-v2",
            adapter="binance_daily",
            instrument_ids=["binance:spot:" + symbol],
            from_date=day,
            before_date=before,
        )
        submitted = jobs.submit(engine, request, invocation + "-" + symbol)
        write(evidence / (symbol + "-submission.json"), submitted)
        started = time.monotonic()
        run_worker(value, submitted["submission_id"], evidence / (symbol + "-worker.json"))
        job = last_job(engine, submitted["submission_id"])
        write(evidence / (symbol + "-job.json"), job)
        if job["state"] != "succeeded":
            raise V2Error("acceptance_failed", "Official daily ingestion did not succeed")
        manifest = catalog.inspect_version(engine, root, job["result_version"])
        write(evidence / (symbol + "-manifest.json"), manifest)
        oracle = raw_reference(root, job, symbol, day, evidence, convert=symbol == "SOLUSDT")
        if (
            oracle["rows"] != manifest["quality"]["accepted_rows"]
            or oracle["logical_sha256"] != manifest["quality"]["logical_sha256"]
            or oracle["archive_sha256"] != manifest["identity"]["source_sha256"]
        ):
            raise V2Error("acceptance_failed", "Independent raw reference differs")
        captured = (
            Path(value["evidence_root"]) / "independent-source" / f"{symbol}-trades-{day}.zip"
        )
        if not captured.is_file() or independent_hash(captured) != oracle["archive_sha256"]:
            raise V2Error("acceptance_failed", "Independently captured source digest differs")
        write(evidence / (symbol + "-independent-reference.json"), oracle)
        sources.append(
            dict(
                symbol=symbol,
                day=day,
                version=job["result_version"],
                rows=manifest["quality"]["accepted_rows"],
                logical_sha256=manifest["quality"]["logical_sha256"],
                elapsed_seconds=time.monotonic() - started,
            )
        )
    reference = sources[1]
    csv_path = evidence / "SOLUSDT-canonical.csv"
    parquet_path = evidence / "SOLUSDT-canonical.parquet"
    converted = []
    for mode, path in (("csv", csv_path), ("parquet", parquet_path)):
        metadata = dict(
            schema="canonical-trade-import-v1",
            instrument_id="binance:spot:SOLUSDT",
            trade_date="2025-03-01",
            format=mode,
            timestamp_encoding="rfc3339_utc" if mode == "csv" else "arrow_timestamp_us_utc",
            quote_quantity_mode="supplied",
            source_sha256=sha256_file(path),
            source_name="checksum-verified-binance-conversion",
            source_reference="https://data.binance.vision/data/spot/daily/trades/SOLUSDT/SOLUSDT-trades-2025-03-01.zip",
            coverage_claim="observed_only",
        )
        write(evidence / (mode + "-metadata.json"), metadata)
        staged = cli_import(
            value,
            evidence / (mode + "-metadata.json"),
            path,
            invocation + "-" + mode,
            evidence / (mode + "-cli-import.json"),
        )
        write(evidence / (mode + "-import.json"), staged)
        run_worker(value, staged["submission_id"], evidence / (mode + "-worker.json"))
        job = last_job(engine, staged["submission_id"])
        if job["state"] != "succeeded":
            raise V2Error("acceptance_failed", "Canonical daily import did not succeed")
        verified = catalog.inspect_version(engine, root, job["result_version"])
        if (
            verified["quality"]["logical_sha256"] != reference["logical_sha256"]
            or verified["quality"]["accepted_rows"] != reference["rows"]
        ):
            raise V2Error("acceptance_failed", "Canonical reference differs")
        converted.append(
            dict(
                format=mode,
                bytes=path.stat().st_size,
                sha256=metadata["source_sha256"],
                version=job["result_version"],
                logical_sha256=verified["quality"]["logical_sha256"],
                rows=verified["quality"]["accepted_rows"],
            )
        )
        replay = cli_import(
            value,
            evidence / (mode + "-metadata.json"),
            path,
            invocation + "-" + mode,
            evidence / (mode + "-cli-replay.json"),
        )
        if not replay["replayed"] or replay["job_id"] != staged["job_id"]:
            raise V2Error("acceptance_failed", "Import replay differs")
    # Fresh key deliberately rechecks source; same bytes must reuse immutable ID.
    fresh = cli_import(
        value,
        evidence / "parquet-metadata.json",
        parquet_path,
        invocation + "-fresh",
        evidence / "fresh-cli-import.json",
    )
    run_worker(value, fresh["submission_id"], evidence / "fresh-worker.json")
    if last_job(engine, fresh["submission_id"])["result_version"] != converted[-1]["version"]:
        raise V2Error("acceptance_failed", "Same-source fresh key did not reuse version")
    if len({reference["version"], *(v["version"] for v in converted)}) != 3:
        raise V2Error("acceptance_failed", "Distinct source identities were collapsed")
    return {
        "official": sources,
        "canonical": converted,
        "same_key_replay": True,
        "fresh_key_reuse": True,
        "conversion_source": __file__,
        "conversion_source_sha256": sha256_file(Path(__file__)),
        "memory_measurement": "unmeasured",
    }


def marker(path: Path, boundary: str) -> None:
    write(path, {"boundary": boundary, "pid": os.getpid(), "utc": datetime.now(UTC).isoformat()})
    while True:
        time.sleep(0.1)


def child(
    engine: sa.Engine, value: dict[str, Any], plan: dict[str, Any], marker_path: Path
) -> None:
    boundary = plan["boundary"]
    if boundary in {"stage_written", "copy_verified"}:
        if boundary == "stage_written":
            original_fsync = service.os.fsync

            def after_fsync(fd: int) -> None:
                original_fsync(fd)
                marker(marker_path, boundary)

            service.os.fsync = after_fsync
        else:

            def before_enqueue(*args: Any, **kwargs: Any) -> Any:
                marker(marker_path, boundary)

            jobs.create_submission = before_enqueue
        service.import_file(
            engine, Path(value["storage_path"]), plan["metadata"], Path(plan["source"]), plan["key"]
        )
        return
    current = jobs.claim(engine, plan["submission_id"])
    if current is None:
        raise V2Error("acceptance_failed", "Crash child could not claim")
    if boundary == "claimed":
        marker(marker_path, boundary)
    if boundary == "normalized":
        from marketlab.datasets.v2 import normalize

        original_normalize = normalize.normalize_source

        def after_normalize(*args: Any, **kwargs: Any) -> dict[str, Any]:
            result = original_normalize(*args, **kwargs)
            marker(marker_path, boundary)
            return result

        normalize.normalize_source = after_normalize
    if boundary == "renamed":
        original_rename = Path.rename

        def after_rename(path: Path, target: Path) -> Path:
            result = original_rename(path, target)
            if target.parent.name == "datasets-v2":
                marker(marker_path, boundary)
            return result

        Path.rename = after_rename  # type: ignore[method-assign]
    if boundary == "committed":
        original_transaction = service.transaction

        @contextmanager
        def after_transaction(*args: Any, **kwargs: Any) -> Any:
            with original_transaction(*args, **kwargs) as connection:
                yield connection
            if last_job(engine, plan["submission_id"])["state"] == "succeeded":
                marker(marker_path, boundary)

        service.transaction = after_transaction
    service.run_claim(engine, Path(value["storage_path"]), current)


def crashes(
    engine: sa.Engine, value: dict[str, Any], evidence: Path, invocation: str, connection_path: Path
) -> dict[str, Any]:
    root = Path(value["storage_path"])
    cases = []
    fixture_base = int(invocation[-8:], 16) * 10
    for number, boundary in enumerate(
        ("stage_written", "copy_verified", "claimed", "normalized", "renamed", "committed")
    ):
        case = evidence / boundary
        case.mkdir()
        source = case / "input.csv"
        source.write_text(
            "source_trade_id,executed_at,price,quantity,quote_quantity,"
            "is_buyer_maker,is_best_match\n"
            + f"{fixture_base + number},2025-03-01T00:00:00.000001Z,2,1,2.01,true,\n",
            encoding="utf-8",
        )
        metadata = dict(
            schema="canonical-trade-import-v1",
            instrument_id="binance:spot:BTCUSDT",
            trade_date="2025-03-01",
            format="csv",
            timestamp_encoding="rfc3339_utc",
            quote_quantity_mode="supplied",
            source_sha256=sha256_file(source),
            source_name="synthetic-crash-fixture",
            source_reference=None,
            coverage_claim="observed_only",
        )
        plan = dict(
            boundary=boundary,
            key=invocation + "-" + boundary,
            metadata=metadata,
            source=str(source.resolve()),
        )
        if boundary not in {"stage_written", "copy_verified"}:
            plan.update(service.import_file(engine, root, metadata, source, plan["key"]))
        write(case / "plan.json", plan)
        log = (case / "child.log").open("wb")
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--connection",
                str(connection_path.resolve()),
                "--evidence",
                str(case.resolve()),
                "--action",
                "child",
                "--plan",
                str((case / "plan.json").resolve()),
            ],
            stdout=log,
            stderr=log,
            env=environment(value),
        )
        deadline = time.monotonic() + 90
        while not (case / "marker.json").exists():
            if process.poll() is not None or time.monotonic() > deadline:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=15)
                log.close()
                raise V2Error("acceptance_failed", "Crash child did not reach planned boundary")
            time.sleep(0.05)
        observed = json.loads((case / "marker.json").read_text())
        process.kill()
        process.wait(timeout=15)
        log.close()
        if boundary in {"stage_written", "copy_verified"}:
            with engine.connect() as c:
                row = core.one(
                    c,
                    "SELECT response_json FROM v2_operations WHERE operation='import' AND "
                    "protocol=:protocol AND idempotency_key=:key",
                    protocol=core.PROTOCOL,
                    key=plan["key"],
                )
            assert row is not None
            plan["import_id"] = row["response_json"]["import_id"]
        record = dict(plan=plan, marker=observed, exit_code=process.returncode)
        with engine.connect() as connection:
            registered = core.execute(
                connection,
                "SELECT count(*) FROM v2_dataset_versions WHERE instrument_id=:instrument "
                "AND source_sha256=:source",
                instrument=metadata["instrument_id"],
                source=metadata["source_sha256"],
            ).scalar_one()
        record["pre_recovery_registered_count"] = registered
        expected_registered = 1 if boundary == "committed" else 0
        if registered != expected_registered:
            raise V2Error("acceptance_failed", "Crash exposed an uncommitted dataset")
        if boundary not in {"stage_written", "copy_verified"}:
            prior_job = last_job(engine, plan["submission_id"])
            record["prior_job"] = prior_job
            if boundary == "renamed":
                expected_identity = {
                    "source_sha256": metadata["source_sha256"],
                    "metadata_sha256": core.metadata_hash(metadata),
                    "instrument_semantic_sha256": prior_job["semantic_sha256"],
                    "trade_date": metadata["trade_date"],
                    "schema_version": "spot-trades-v2",
                    "transform_version": core.TRANSFORM,
                    "lock_sha256": core.execution_identity()["lock_sha256"],
                }
                orphan = root / "datasets-v2" / core.digest(expected_identity)
                record["orphan_version"] = core.digest(expected_identity)
                record["orphan_hashes"] = {
                    p.name: independent_hash(p) for p in orphan.iterdir() if p.is_file()
                }
        cases.append(record)
    # Native expiry: no test clock/database lease edits and no accelerated lease.
    started = time.monotonic()
    while time.monotonic() - started < 61:
        time.sleep(0.5)
    expired = service.expire_staging(engine, root)
    for record in cases:
        plan = record["plan"]
        if plan["boundary"] in {"stage_written", "copy_verified"}:
            imported = service.inspect_import(engine, plan["import_id"])
            if imported["state"] != "failed" or imported["submission_id"] is not None:
                raise V2Error("acceptance_failed", "Expired staging enqueued or did not terminate")
            record["result"] = imported
        else:
            run_worker(
                value, plan["submission_id"], evidence / plan["boundary"] / "recovery-worker.json"
            )
            job = last_job(engine, plan["submission_id"])
            expected = 1 if plan["boundary"] == "committed" else 2
            if job["state"] != "succeeded" or job["attempt_count"] != expected:
                raise V2Error("acceptance_failed", "Crash recovery attempt/state mismatch")
            catalog.inspect_version(engine, root, job["result_version"])
            prior = record["prior_job"]
            stale = dict(
                prior,
                job_id=core.uid(prior["job_id"]),
                owner=core.uid(prior["owner"]) if prior["owner"] else None,
            )
            if jobs.heartbeat(engine, stale):
                raise V2Error("acceptance_failed", "Stale attempt renewed after crash recovery")
            try:
                with core.transaction(engine) as connection:
                    jobs.fence(connection, stale)
            except V2Error as error:
                if error.code != "ownership_lost":
                    raise
            else:
                raise V2Error("acceptance_failed", "Stale attempt retained publication fence")
            record["stale_fence_rejected"] = True
            if plan["boundary"] == "renamed":
                final = root / "datasets-v2" / record["orphan_version"]
                actual_hashes = {
                    p.name: independent_hash(p) for p in final.iterdir() if p.is_file()
                }
                if actual_hashes != record["orphan_hashes"]:
                    raise V2Error("acceptance_failed", "Recovery changed verified orphan bytes")
                record["orphan_hashes_unchanged"] = True
            record["result"] = job
    return {
        "cases": cases,
        "expired_staging": expired,
        "native_expiry_wait_seconds": time.monotonic() - started,
        "memory_measurement": "unmeasured",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--connection", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--action", choices=("actual", "crashes", "child"), required=True)
    parser.add_argument("--plan", type=Path)
    args = parser.parse_args()
    value = config(args.connection)
    value["evidence_root"] = str(args.connection.resolve().parent)
    engine = sa.create_engine(value["database_url"])
    invocation = "p2-" + uuid4().hex
    if args.action != "child":
        args.evidence = args.evidence / invocation
        args.evidence.mkdir(parents=True, exist_ok=False)
    else:
        args.evidence.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    receipt = dict(
        invocation_id=invocation,
        action=args.action,
        started_at=datetime.now(UTC).isoformat(),
        execution=core.execution_identity(),
        source_sha256=sha256_file(Path(__file__)),
    )
    try:
        if args.action == "child":
            if args.plan is None:
                raise ValueError("child requires plan")
            child(
                engine,
                value,
                json.loads(args.plan.read_text(encoding="utf-8")),
                args.evidence / "marker.json",
            )
        else:
            receipt["result"] = (
                actual(engine, value, args.evidence, invocation)
                if args.action == "actual"
                else crashes(engine, value, args.evidence, invocation, args.connection)
            )
            receipt["outcome"] = "passed"
    except Exception as error:
        receipt["outcome"] = "failed"
        receipt["safe_error"] = {
            "type": type(error).__name__,
            "code": getattr(error, "code", "operation_failed"),
        }
        return_code = 1
    else:
        return_code = 0
    finally:
        receipt["elapsed_seconds"] = time.monotonic() - start
        receipt["ended_at"] = datetime.now(UTC).isoformat()
        write(args.evidence / (invocation + "-receipt.json"), receipt)
        engine.dispose()
    print(
        json.dumps(
            {
                "invocation_id": invocation,
                "outcome": receipt.get("outcome"),
                "receipt": str(args.evidence / (invocation + "-receipt.json")),
            }
        )
    )
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
