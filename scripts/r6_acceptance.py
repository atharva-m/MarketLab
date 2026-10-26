"""Owned-resource R6 acceptance; preserves historical R5 tooling and evidence."""

import argparse
import asyncio
import hashlib
import json
import os
import platform
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from r5_acceptance import DIGEST, MODEL, ROOT, observed, restore, save

from marketlab.analytics.bars import BarService
from marketlab.config import Settings
from marketlab.datasets.source import file_hash
from marketlab.memos import store
from marketlab.memos.model import MemoModel
from marketlab.memos.service import MemoService
from marketlab.memos.spec import facts, render
from marketlab.research import store as research_store
from marketlab.research.service import ResearchService, execution_identity
from marketlab.research.spec import ResearchError, ResearchSpec

BASE = Path("artifacts/r6")


def owned_settings() -> Settings:
    settings = Settings()
    if (
        settings.sqlalchemy_url.host,
        settings.sqlalchemy_url.port,
        settings.sqlalchemy_url.database,
    ) != ("127.0.0.1", 55439, "marketlab"):
        raise RuntimeError("R6 requires explicitly owned database")
    if (
        settings.redis_url.get_secret_value() != "redis://127.0.0.1:56381/0"
        or settings.ollama_url != "http://127.0.0.1:11437"
    ):
        raise RuntimeError("R6 requires explicitly owned Redis/Ollama")
    for kind in ("postgres", "redis"):
        recorded = json.loads((BASE / ("owned-" + kind + ".json")).read_text(encoding="utf-8-sig"))
        if isinstance(recorded, list):
            recorded = recorded[0]
        actual = json.loads(subprocess.check_output(["docker", "inspect", recorded["Id"]]))[0]
        assert actual["Id"] == recorded["Id"] and actual["State"]["Running"]
        assert actual["Config"]["Labels"]["marketlab.r6.owner"] == "r6-20261025"
    return settings


def engine_for(settings: Settings) -> sa.Engine:
    return sa.create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)


def restore_research(engine: sa.Engine) -> list[dict[str, Any]]:
    snapshot = json.loads(Path("artifacts/r4/catalog-final.json").read_text(encoding="utf-8"))
    tables = {
        "research_submissions": research_store.submissions,
        "research_runs": research_store.runs,
        "research_attempts": research_store.attempts,
        "research_results": research_store.results,
    }
    with engine.begin() as connection:
        for name, table in tables.items():
            for record in snapshot[name]:
                row = dict(record)
                for column in table.columns:
                    if row.get(column.name) is not None and isinstance(column.type, sa.DateTime):
                        row[column.name] = datetime.fromisoformat(row[column.name])
                primary = [table.c[c.name] == row[c.name] for c in table.primary_key]
                if connection.execute(sa.select(table).where(*primary)).first() is None:
                    connection.execute(table.insert().values(**row))
    return snapshot["research_runs"]


async def model_eval(prefix: str) -> None:
    settings = owned_settings()
    corpus_path = Path("tests/fixtures/r6_summaries.json")
    corpus = json.loads(await asyncio.to_thread(corpus_path.read_text, encoding="utf-8"))
    model = MemoModel(settings.ollama_url, MODEL, DIGEST)
    output = BASE / (prefix + "-memo-model.json")
    evidence: dict[str, Any] = {
        "status": "running",
        "corpus_sha256": file_hash(corpus_path),
        "execution": execution_identity(),
        "hardware": platform.platform(),
        "peak_memory": "unmeasured",
        "generation_boundary": (
            "Model chooses bounded wording for app-owned complete grounded "
            "paragraph claims; not unrestricted prose generation"
        ),
        "independent_audit": "pending",
        "coverage_cases": [
            {"id": case["id"], "coverage": case["coverage_case"]} for case in corpus["cases"]
        ],
        "cases": [],
    }
    began = time.perf_counter()
    try:
        for case in corpus["cases"]:
            started = time.perf_counter()
            source = facts(case["summary"])
            item: dict[str, Any] = {
                "id": case["id"],
                "coverage_case": case["coverage_case"],
                "summary": case["summary"],
                "facts": source,
            }
            try:
                value, provenance = await model.generate(source, DIGEST)
                content = render(value, source)
                item.update(
                    valid=True,
                    draft=value,
                    content=content,
                    provenance=provenance,
                    memo_sha256=hashlib.sha256(content.encode()).hexdigest(),
                )
            except Exception as error:
                item.update(valid=False, error_type=type(error).__name__, error=str(error))
            item["seconds"] = time.perf_counter() - started
            evidence["cases"].append(item)
            save(output, evidence)
            print(
                json.dumps(
                    {"case": case["id"], "valid": item["valid"], "seconds": item["seconds"]}
                ),
                flush=True,
            )
        evidence["valid"] = sum(item["valid"] for item in evidence["cases"])
        assert execution_identity() == evidence["execution"], (
            "Source changed during actual model evaluation"
        )
        assert evidence["valid"] >= 18, "Actual memo model acceptance threshold missed"
        evidence["status"] = "automated_pass_independent_audit_pending"
    except BaseException as error:
        evidence.update(status="failed", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        evidence["seconds"] = time.perf_counter() - began
        save(output, evidence)


async def durability(prefix: str) -> None:
    settings = owned_settings()
    engine = engine_for(settings)
    schema = "r6_durable_" + uuid4().hex
    isolated = engine.execution_options(schema_translate_map={None: schema})
    output = BASE / (prefix + "-durability-live.json")
    evidence: dict[str, Any] = {
        "status": "running",
        "schema": schema,
        "clock_policy": "Actual database time, no lease/eligibility timestamp edits",
        "checks": {},
    }
    began = time.perf_counter()

    def create() -> str:
        run = str(uuid4())
        with isolated.begin() as connection:
            store.enqueue(connection, run, "a" * 64, "b" * 64)
        return run

    def state(run: str) -> dict[str, Any]:
        value = store.inspect(isolated, run)
        with isolated.connect() as connection:
            value["database_now"] = connection.execute(
                sa.select(sa.func.clock_timestamp())
            ).scalar_one()
        return value

    async def wait_gate(run: str, name: str) -> dict[str, Any]:
        deadline = time.monotonic() + 100
        while time.monotonic() < deadline:
            value = await asyncio.to_thread(state, run)
            if value["database_now"] >= value[name]:
                return value
            await asyncio.sleep(0.25)
        raise TimeoutError("Actual database eligibility gate not reached")

    try:
        with engine.begin() as connection:
            connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            for name in ("memo_jobs", "memo_attempts", "memo_results"):
                connection.execute(
                    sa.text(f'CREATE TABLE "{schema}".{name} (LIKE public.{name} INCLUDING ALL)')
                )
        for _ in range(100):
            run = create()
            current = store.claim(isolated, run)
            assert current is not None and current.attempt == 1
            store.fail(isolated, current)
        evidence["checks"]["immediate_claims"] = 100
        run = create()
        current = store.claim(isolated, run)
        gates = []
        for seconds in (10, 30):
            started = time.perf_counter()
            store.fail(isolated, current, True)
            assert store.claim(isolated, run) is None
            value = await wait_gate(run, "eligible_at")
            current = store.claim(isolated, run)
            assert current is not None
            gates.append(
                {
                    "expected_seconds": seconds,
                    "host_seconds": time.perf_counter() - started,
                    "eligible_at": value["eligible_at"],
                    "database_now": value["database_now"],
                }
            )
        store.fail(isolated, current)
        evidence["checks"]["retry_gates"] = gates
        save(output, evidence)
        run = create()
        current = store.claim(isolated, run)
        beats = []
        for _ in range(2):
            await asyncio.sleep(10)
            assert store.heartbeat(isolated, current)
            beats.append(state(run))
        evidence["checks"]["heartbeats"] = beats
        cycles = []
        for attempt in (1, 2, 3):
            value = await wait_gate(run, "lease_until")
            newer = store.claim(isolated, run)
            assert not store.heartbeat(isolated, current)
            for operation in (
                lambda current=current: store.reserve_call(isolated, current),
                lambda current=current: store.checkpoint(isolated, current, None, {}),
                lambda current=current: store.fail(isolated, current),
            ):
                try:
                    operation()
                except ResearchError:
                    pass
                else:
                    raise AssertionError("Stale memo mutation accepted")
            cycles.append(
                {
                    "expired_attempt": attempt,
                    "database_now": value["database_now"],
                    "lease_until": value["lease_until"],
                }
            )
            if attempt < 3:
                assert newer is not None and newer.attempt == attempt + 1
                current = newer
            else:
                assert newer is None and store.inspect(isolated, run)["state"] == "failed"
            save(output, evidence)
        evidence["checks"]["lease_cycles"] = cycles
        run = create()
        current = store.claim(isolated, run)
        store.reserve_call(isolated, current)
        store.reserve_call(isolated, current)
        try:
            store.reserve_call(isolated, current)
        except ResearchError:
            pass
        else:
            raise AssertionError("Third model call accepted")
        store.fail(isolated, current)
        evidence["checks"]["two_call_budget"] = store.inspect(isolated, run)
        evidence["status"] = "passed"
    except BaseException as error:
        evidence.update(status="failed", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        with engine.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        evidence.update(owned_schema_removed=True, seconds=time.perf_counter() - began)
        save(output, evidence)
        engine.dispose()


async def month(prefix: str, ordered_profiles: bool = False) -> None:
    settings = owned_settings()
    engine = engine_for(settings)
    records = await asyncio.to_thread(restore, engine)
    retained = await asyncio.to_thread(restore_research, engine)
    references = json.loads(
        await asyncio.to_thread(
            Path("artifacts/r4/reference-workflows.json").read_text, encoding="utf-8"
        )
    )
    bars = BarService(engine, ROOT, settings.redis_url.get_secret_value())
    research = ResearchService(bars)
    memo = MemoService(research, MemoModel(settings.ollama_url, MODEL, DIGEST))
    output = BASE / (prefix + "-month.json")
    evidence: dict[str, Any] = {
        "status": "running",
        "execution": research.execution,
        "partitions": len(records),
        "input_rows": sum(r["row_count"] for r in records),
        "peak_memory": "unmeasured",
        "memos": [],
        "owned_supplement_runs": [],
        "ordered_profiles": ordered_profiles,
        "additional_profiles": [],
    }
    began = time.perf_counter()
    try:
        for index, reference in enumerate(references):
            selected = None
            for old in retained:
                info = research.inspect(old["run_id"])
                if (
                    ResearchSpec.create(info["spec"]).body()
                    == ResearchSpec.create(reference["spec"]).body()
                ):
                    selected = old["run_id"]
                    break
            assert selected is not None
            summary, summary_hash = research.read(selected, "summary")
            assert summary == reference["summary"] and summary_hash == reference["summary_sha256"]
            _, result_hash = research.read(selected, "results")
            assert result_hash == reference["results_sha256"]
            memo.enqueue(selected)
            evidence["owned_supplement_runs"].append(selected)
            save(output, evidence)
            memo_replayed = store.inspect(engine, selected)["state"] == "ready"
            if not memo_replayed:
                assert await memo.work(1, selected) == 1
            content, manifest = memo.read(selected)
            evidence["memos"].append(
                {
                    "index": index,
                    "run_id": selected,
                    "summary_sha256": summary_hash,
                    "results_sha256": result_hash,
                    "content": content,
                    "manifest": manifest,
                    "summary": summary,
                    "attempts": store.inspect(engine, selected)["attempt_count"],
                    "memo_replayed": memo_replayed,
                }
            )
            save(output, evidence)
            print(json.dumps({"retained_memo": index, "ready": True}), flush=True)
        if ordered_profiles:
            # Explicit existing-workflow acceptance; not a production cache warmer.
            # Each request keeps the unchanged thirty-minute preparation/execution bounds.
            for index, reference in enumerate(
                r for r in references if r["spec"]["workflow"] == "market_profile"
            ):
                label = reference["spec"]["symbols"][0]
                run, _ = await observed(
                    research.submit(
                        ResearchSpec.create(reference["spec"]), prefix + "-profile-" + label
                    ),
                    output,
                    "ordered_profile_validation_" + label,
                    index,
                )
                evidence["additional_profiles"].append(
                    {"run_id": run, "symbol": label, "status": "queued"}
                )
                save(output, evidence)
                assert (
                    await observed(
                        research.work(1, run), output, "ordered_profile_execution_" + label, index
                    )
                    == 1
                )
                result, result_hash = research.read(run, "results")
                summary, summary_hash = research.read(run, "summary")
                assert result == reference["results"] and summary == reference["summary"]
                assert (
                    result_hash == reference["results_sha256"]
                    and summary_hash == reference["summary_sha256"]
                )
                assert store.inspect(engine, run)["state"] == "queued"
                evidence["owned_supplement_runs"].append(run)
                save(output, evidence)
                assert await memo.work(1, run) == 1
                content, manifest = memo.read(run)
                evidence["additional_profiles"][-1].update(
                    status="ready",
                    results_sha256=result_hash,
                    summary_sha256=summary_hash,
                    summary=summary,
                    content=content,
                    manifest=manifest,
                    attempts=research.inspect(run)["attempt_count"],
                )
                save(output, evidence)
        # Fresh full-month cross_asset uses all 62 explicit partitions and atomic enqueue.
        reference = next(r for r in references if r["spec"]["workflow"] == "cross_asset")
        run, _ = await observed(
            research.submit(ResearchSpec.create(reference["spec"]), prefix + "-fresh-cross-asset"),
            output,
            "fresh_cross_asset_validation",
            5,
        )
        evidence["fresh_run_id"] = run
        save(output, evidence)
        assert await observed(research.work(1, run), output, "fresh_cross_asset_execution", 5) == 1
        result, result_hash = research.read(run, "results")
        summary, summary_hash = research.read(run, "summary")
        assert result == reference["results"] and summary == reference["summary"]
        assert (
            result_hash == reference["results_sha256"]
            and summary_hash == reference["summary_sha256"]
        )
        assert store.inspect(engine, run)["state"] == "queued"
        assert await memo.work(1, run) == 1
        content, manifest = memo.read(run)
        evidence["fresh"] = {
            "run_id": run,
            "results_sha256": result_hash,
            "summary_sha256": summary_hash,
            "content": content,
            "manifest": manifest,
            "attempts": research.inspect(run)["attempt_count"],
        }
        assert execution_identity() == evidence["execution"]
        evidence["status"] = "automated_pass_independent_audit_pending"
    except BaseException as error:
        evidence.update(status="failed", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        evidence["seconds"] = time.perf_counter() - began
        save(output, evidence)
        await research.close()
        await bars.close()
        engine.dispose()


async def copilot_eval(prefix: str) -> None:
    # Rebind only this invocation's module globals, preserving R5 source and old outputs.
    import r5_model_eval

    r5_model_eval.BASE = BASE
    r5_model_eval.owned_settings = owned_settings
    await r5_model_eval.main(prefix, None)


async def snapshot(prefix: str) -> None:
    """Retain replayable owned application registrations before service cleanup."""
    settings = owned_settings()
    engine = engine_for(settings)
    names = (
        "dataset_versions",
        "ingestion_submissions",
        "ingestion_jobs",
        "ingestion_attempts",
        "research_submissions",
        "research_runs",
        "research_attempts",
        "research_results",
        "copilot_requests",
        "copilot_revisions",
        "copilot_jobs",
        "copilot_attempts",
        "memo_jobs",
        "memo_attempts",
        "memo_results",
    )
    record: dict[str, Any] = {
        "audit_only": True,
        "owned_database_port": 55439,
        "storage_root": str(ROOT),
        "execution": execution_identity(),
        "tables": {},
    }
    try:
        with engine.connect() as connection:
            record["migration_head"] = connection.scalar(
                sa.text("SELECT version_num FROM alembic_version")
            )
            assert record["migration_head"] == "0007_memos"
            for name in names:
                record["tables"][name] = [
                    dict(r) for r in connection.execute(sa.text("SELECT * FROM " + name)).mappings()
                ]
        save(BASE / (prefix + "-catalog-final.json"), record)
        print(
            json.dumps(
                {"snapshot_rows": {name: len(rows) for name, rows in record["tables"].items()}}
            )
        )
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["model", "durability", "month", "copilot", "snapshot"])
    parser.add_argument("--prefix", required=True)
    parser.add_argument(
        "--ordered-profiles",
        action="store_true",
        help="Explicit bounded asset profile runs before fresh cross-asset month acceptance",
    )
    arguments = parser.parse_args()
    os.environ["MARKETLAB_STORAGE_PATH"] = str(ROOT)
    operation = {
        "model": model_eval,
        "durability": durability,
        "month": month,
        "copilot": copilot_eval,
        "snapshot": snapshot,
    }[arguments.phase]
    if arguments.phase == "month":
        asyncio.run(month(arguments.prefix, arguments.ordered_profiles))
    else:
        if arguments.ordered_profiles:
            parser.error("--ordered-profiles requires month phase")
        asyncio.run(operation(arguments.prefix))


if __name__ == "__main__":
    main()
