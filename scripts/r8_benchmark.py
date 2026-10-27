"""Reproducible owned R8 pipeline, cache and actual-model measurements.

Generated data and evidence remain ignored. Inputs are synthetic provider-shaped
fixtures; they do not replace official-source or retained-month acceptance.
"""

import argparse
import asyncio
import hashlib
import io
import json
import os
import socket
import statistics
import subprocess
import sys
import time
import zipfile
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import sqlalchemy as sa
from r8_common import (
    BASE,
    DIGEST,
    MODEL,
    Invocation,
    Sampler,
    engine_for,
    owned_settings,
    save,
    validate_prefix,
)
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff

from marketlab.analytics.bars import BarService, BarsRequest
from marketlab.analytics.cache import cache_key, canonical
from marketlab.copilot.model import Ollama
from marketlab.datasets.publication import ingest_archive, inspect_version
from marketlab.datasets.source import file_hash
from marketlab.memos.model import MemoModel
from marketlab.memos.spec import facts, render
from marketlab.research.service import ResearchService
from marketlab.research.spec import ResearchSpec

DAY = date(2025, 1, 1)
EPOCH_US = 1735689600000000
DAY_US = 86400000000
ALGORITHM = "r8-fixed-price-even-time-v1"


def generated_row(index: int, rows: int) -> str:
    """Closed-form oracle: price100, quantity0.01, quote1, evenly spaced UTC."""
    return f"{index + 1},100,0.01,1,{EPOCH_US + index * DAY_US // rows},True,False\n"


def bucket_count(rows: int, bucket: int, buckets: int = 288) -> int:
    # Count i for which bucket/buckets <= floor(i*DAY_US/rows)/DAY_US
    # < (bucket+1)/buckets; supported bucket boundaries divide DAY_US exactly.
    return ((bucket + 1) * rows + buckets - 1) // buckets - (bucket * rows + buckets - 1) // buckets


def generate_input(rows: int, base: Path) -> tuple[Path, Path, dict[str, Any]]:
    if rows < 288 or rows > 20_000_000:
        raise ValueError("fixture row count outside production/test bounds")
    base.mkdir(parents=True, exist_ok=False)
    archive = base / "BTCUSDT-trades-2025-01-01.zip"
    info = zipfile.ZipInfo("BTCUSDT-trades-2025-01-01.csv", (2025, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    began = time.monotonic()
    expanded = 0
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as target:
        with target.open(info, "w", force_zip64=True) as binary:
            with io.TextIOWrapper(binary, encoding="ascii", newline="", write_through=False) as csv:
                for index in range(rows):
                    row = generated_row(index, rows)
                    csv.write(row)
                    expanded += len(row)
    checksum = base / "source.CHECKSUM"
    digest = file_hash(archive)
    checksum.write_text(digest + "  " + archive.name, encoding="ascii")
    evidence = {
        "algorithm": ALGORITHM,
        "seed": 0,
        "rows": rows,
        "source_sha256": digest,
        "compressed_bytes": archive.stat().st_size,
        "expanded_bytes": expanded,
        "generation_seconds": time.monotonic() - began,
        "label": "Synthetic provider-shaped input; not official exchange data",
    }
    save(base / "input.json", evidence)
    return archive, checksum, evidence


@contextmanager
def isolated(prefix: str):
    """Migrated disposable schema/root; never original services or retained files."""
    settings = owned_settings()
    admin = engine_for(settings)
    schema = "r8_bench_" + uuid4().hex
    root = (BASE / (prefix + "-storage")).resolve()
    root.mkdir(parents=True, exist_ok=False)
    with admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    url = settings.sqlalchemy_url.update_query_dict({"options": f"-csearch_path={schema}"})
    env = {
        **os.environ,
        "MARKETLAB_DATABASE_URL": url.render_as_string(hide_password=False),
        "MARKETLAB_DATABASE_PASSWORD": url.password or "",
        "MARKETLAB_STORAGE_PATH": str(root),
        "MARKETLAB_REDIS_URL": settings.redis_url.get_secret_value(),
        "MARKETLAB_OLLAMA_URL": settings.ollama_url,
    }
    engine = sa.create_engine(url, connect_args=settings.database_connect_args)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode:
            raise RuntimeError("Owned benchmark schema migration failed")
        yield settings, engine, root, env
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin.dispose()


def check_bars(payload: dict[str, Any], rows: int) -> None:
    assert payload["returned_buckets"] == 288 and payload["empty_buckets"] == 0
    assert len(payload["bars"]) == 288
    for index, bar in enumerate(payload["bars"]):
        count = bucket_count(rows, index)
        assert bar["trade_count"] == count
        assert all(
            bar[name] == "100.000000000000000000"
            for name in ("open", "high", "low", "close", "vwap")
        )
        assert bar["base_volume"] == format(Decimal(count) / 100, ".18f")
        assert bar["quote_volume"] == format(Decimal(count), ".18f")


async def numerical(engine, root, version: str, rows: int) -> dict[str, Any]:
    bars = BarService(engine, root, None)
    research = ResearchService(bars)
    try:
        request = BarsRequest.create(
            versions=[version],
            symbol="BTCUSDT",
            interval="5m",
            start="2025-01-01T00:00:00Z",
            end="2025-01-02T00:00:00Z",
        )
        started = time.monotonic()
        payload, outcome = await bars.read(request)
        check_bars(payload, rows)
        bar_seconds = time.monotonic() - started
        spec = ResearchSpec.create(
            {
                "schema": "research-spec-v1",
                "workflow": "market_profile",
                "symbols": ["BTCUSDT"],
                "dataset_versions": [version],
                "start": "2025-01-01T01:00:00Z",
                "end": "2025-01-02T00:00:00Z",
                "history_start": "2025-01-01T00:00:00Z",
                "interval": "5m",
                "metrics": ["profile"],
                "parameters": {},
                "predicates": {},
            }
        )
        started = time.monotonic()
        run, replayed = await research.submit(spec, "benchmark-profile")
        assert not replayed and await research.work(1, run) == 1
        state = research.inspect(run)
        assert state["state"] == "succeeded" and state["attempt_count"] == 1
        result, result_hash = research.read(run, "results")
        summary, summary_hash = research.read(run, "summary")
        profile = summary["profiles"]["BTCUSDT"]
        eval_rows = sum(bucket_count(rows, index) for index in range(12, 288))
        assert profile["trade_count"] == eval_rows
        assert profile["base_volume"] == format(Decimal(eval_rows) / 100, ".18f")
        assert profile["quote_volume"] == format(Decimal(eval_rows), ".18f")
        assert profile["vwap"]["value"] == "100.000000000000000000"
        assert (
            profile["close_change"]["value"]
            == profile["drawdown"]["value"]
            == "0.000000000000000000"
        )
        assert profile["sharpe"]["value"] is None and profile["sharpe"]["reason"] == "zero_variance"
        assert len(result["profiles"]) == 1
        return {
            "bars_seconds": bar_seconds,
            "bar_cache": outcome,
            "bar_payload_sha256": hashlib.sha256(canonical(payload)).hexdigest(),
            "research_seconds": time.monotonic() - started,
            "run_id": run,
            "results_sha256": result_hash,
            "summary_sha256": summary_hash,
            "oracle": "Independent closed-form counts and constant-price arithmetic",
        }
    finally:
        await research.close()
        await bars.close()


async def pipeline(prefix: str, rows: int) -> None:
    with Invocation(prefix, "pipeline") as evidence:
        archive, checksum, generated = generate_input(rows, BASE / (prefix + "-input"))
        evidence.data.update(input=generated, rows=rows)
        evidence.flush()
        with isolated(prefix) as (_, engine, root, _):
            with Sampler(BASE / (prefix + "-resources.json")):
                started = time.monotonic()
                checkpoints = []
                manifest = await asyncio.to_thread(
                    ingest_archive,
                    engine,
                    root,
                    archive,
                    checksum,
                    checkpoint=lambda stage: checkpoints.append(
                        {"stage": stage, "seconds": time.monotonic() - started}
                    ),
                )
                publication_seconds = time.monotonic() - started
                assert manifest["quality"]["accepted_rows"] == rows
                version = str(manifest["dataset_version_id"])
                verified = await asyncio.to_thread(inspect_version, engine, root, version)
                assert verified == manifest
                numerical_evidence = await numerical(engine, root, version, rows)
                evidence.data.update(
                    publication_seconds=publication_seconds,
                    rows_per_second=rows / publication_seconds,
                    expanded_bytes_per_second=generated["expanded_bytes"] / publication_seconds,
                    complete_pipeline_seconds=time.monotonic() - started,
                    checkpoints=checkpoints,
                    version=version,
                    manifest=manifest,
                    numerical=numerical_evidence,
                )
                evidence.flush()
        evidence.data["owned_schema_removed"] = True


def statistics_for(samples: list[dict[str, Any]]) -> dict[str, Any]:
    values = [row["seconds"] for row in samples]
    return {
        "count": len(values),
        "median_seconds": statistics.median(values),
        "minimum_seconds": min(values),
        "maximum_seconds": max(values),
        "percentile_claim": "No tail percentile claim from these small samples",
    }


async def cache_benchmark(prefix: str) -> None:
    with Invocation(prefix, "cache") as evidence:
        archive, checksum, generated = generate_input(10000, BASE / (prefix + "-input"))
        with isolated(prefix) as (settings, engine, root, _):
            manifest = await asyncio.to_thread(ingest_archive, engine, root, archive, checksum)
            version = str(manifest["dataset_version_id"])
            bars = BarService(engine, root, settings.redis_url.get_secret_value())
            request = BarsRequest.create(
                versions=[version],
                symbol="BTCUSDT",
                interval="5m",
                start="2025-01-01T00:00:00Z",
                end="2025-01-02T00:00:00Z",
            )
            key = cache_key(
                "bars", {"versions": [version], "definition": "bars-v1"}, request.parameters()
            )
            original = bars.cache.client
            assert original is not None
            reserve = socket.socket()
            reserve.bind(("127.0.0.1", 56385))
            # Hold a bound, deliberately non-listening owned endpoint for the fault.
            absent = Redis.from_url(
                "redis://127.0.0.1:56385/0",
                socket_connect_timeout=0.1,
                socket_timeout=0.1,
                retry=Retry(NoBackoff(), 0),
                retry_on_timeout=False,
            )
            payload_hash = None
            try:
                # Separate initial application verification from Redis-condition timing.
                await bars.read(request)
                with Sampler(BASE / (prefix + "-resources.json")):
                    for condition in ("cold", "warm", "unavailable", "recovered"):
                        if condition == "unavailable":
                            bars.cache.client = absent
                        elif condition == "recovered":
                            bars.cache.client = original
                            # Keep actual circuit state and let its real ten-second gate expire.
                            await asyncio.sleep(10.1)
                        samples = []
                        for index in range(20):
                            if condition == "cold":
                                await original.delete(key)  # Only this owned fixture's exact key.
                            started = time.monotonic()
                            body, outcome = await bars.read(request)
                            seconds = time.monotonic() - started
                            digest = hashlib.sha256(canonical(body)).hexdigest()
                            payload_hash = payload_hash or digest
                            assert digest == payload_hash
                            assert (
                                outcome
                                == {
                                    "cold": "MISS",
                                    "warm": "HIT",
                                    "unavailable": "BYPASS",
                                    "recovered": "HIT",
                                }[condition]
                            )
                            samples.append(
                                {
                                    "index": index,
                                    "seconds": seconds,
                                    "outcome": outcome,
                                    "payload_sha256": digest,
                                }
                            )
                        evidence.data["cases"].append(
                            {
                                "condition": condition,
                                "samples": samples,
                                "statistics": statistics_for(samples),
                            }
                        )
                        evidence.flush()
                evidence.data.update(
                    input=generated,
                    unavailable_method=(
                        "Owned unused endpoint56385; real connection failures, service unchanged"
                    ),
                    verification_state="Application verification warm before measurements",
                )
            finally:
                bars.cache.client = original
                await absent.aclose()
                reserve.close()
                await original.delete(key)
                await bars.close()


class RecordingMixin:
    """Observe native returned timing metadata without changing requests/results."""

    completion: dict[str, Any]

    async def bounded(self, client, method, path, **kwargs):
        result = await super().bounded(client, method, path, **kwargs)
        if method == "POST" and path == "/api/chat":
            self.completion = {
                name: result.get(name)
                for name in (
                    "total_duration",
                    "load_duration",
                    "prompt_eval_count",
                    "prompt_eval_duration",
                    "eval_count",
                    "eval_duration",
                    "done_reason",
                )
            }
        return result


class RecordedCopilot(RecordingMixin, Ollama):
    pass


class RecordedMemo(RecordingMixin, MemoModel):
    pass


def completion_sample(index, seconds, outcome, timing, residency, provenance, validation):
    """Keep harness completion and interpretation outcomes in distinct namespaces."""
    return {
        "index": index,
        "seconds": seconds,
        "outcome": outcome,
        "native_timing": timing,
        "before_residency": residency,
        "provenance": provenance,
        "validation": validation,
    }


async def model_residency(client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.get("/api/ps")
    response.raise_for_status()
    value = response.json()
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("models"), list)
        or any(
            not isinstance(row, dict) or not isinstance(row.get("digest"), str)
            for row in value["models"]
        )
    ):
        raise ValueError("Invalid model residency response")
    return value


async def model_benchmark(prefix: str) -> None:
    settings = owned_settings()
    with Invocation(prefix, "model-benchmark") as evidence:
        corpus = json.loads(
            await asyncio.to_thread(Path("tests/fixtures/r5_prompts.json").read_text)
        )
        summaries = json.loads(
            await asyncio.to_thread(Path("tests/fixtures/r6_summaries.json").read_text)
        )
        summary = summaries["cases"][0]["summary"]
        case = corpus["cases"][0]
        turns = [{"text": case["text"], "context": case["context"]}]
        with Sampler(BASE / (prefix + "-resources.json"), model=True):
            async with httpx.AsyncClient(
                base_url=settings.ollama_url, trust_env=False, follow_redirects=False, timeout=120
            ) as client:
                for workload in ("copilot", "memo"):
                    model = (
                        RecordedCopilot(settings.ollama_url, MODEL, DIGEST)
                        if workload == "copilot"
                        else RecordedMemo(settings.ollama_url, MODEL, DIGEST)
                    )
                    for condition, repetitions in (("cold", 3), ("warm", 10)):
                        samples = []
                        for index in range(repetitions):
                            if condition == "cold":
                                response = await client.post(
                                    "/api/generate", json={"model": MODEL, "keep_alive": 0}
                                )
                                response.raise_for_status()
                                resident = await model_residency(client)
                                assert not any(
                                    row.get("digest") == DIGEST
                                    for row in resident.get("models", [])
                                )
                            else:
                                resident = await model_residency(client)
                                assert any(
                                    row.get("digest") == DIGEST
                                    for row in resident.get("models", [])
                                )
                            model.completion = {}
                            started = time.monotonic()
                            try:
                                if workload == "copilot":
                                    interpreted, provenance = await model.infer(turns, DIGEST)
                                    validated = {"interpretation_outcome": interpreted["outcome"]}
                                else:
                                    draft, provenance = await model.generate(facts(summary), DIGEST)
                                    content = render(draft, facts(summary))
                                    assert len(content.split("\n\n")) == 3
                                    validated = {
                                        "memo_sha256": hashlib.sha256(content.encode()).hexdigest()
                                    }
                                outcome = "completed"
                            except Exception as error:
                                outcome, provenance, validated = (
                                    type(error).__name__,
                                    getattr(error, "provenance", None),
                                    {},
                                )
                            timing = dict(model.completion)
                            seconds = time.monotonic() - started
                            if timing.get("eval_duration") and timing.get("eval_count") is not None:
                                timing["output_tokens_per_second"] = timing["eval_count"] / (
                                    timing["eval_duration"] / 1e9
                                )
                            samples.append(
                                completion_sample(
                                    index, seconds, outcome, timing, resident, provenance, validated
                                )
                            )
                            evidence.data["active_samples"] = samples
                            evidence.flush()
                        completed = sum(row["outcome"] == "completed" for row in samples)
                        timing_count = sum(
                            row["native_timing"].get("eval_count") is not None
                            and bool(row["native_timing"].get("eval_duration"))
                            for row in samples
                        )
                        evidence.data["cases"].append(
                            {
                                "workload": workload,
                                "condition": condition,
                                "samples": samples,
                                "statistics": statistics_for(samples),
                                "completed": completed,
                                "failed": repetitions - completed,
                                "native_timing_available": timing_count,
                            }
                        )
                        evidence.flush()
                        assert completed > 0, "All model benchmark calls failed"
                        assert timing_count == repetitions, (
                            "Native throughput measurement incomplete"
                        )
        evidence.data.update(
            model=MODEL,
            digest=DIGEST,
            scope="Unchanged production model-client calls; durable evaluation is separate",
            queue="Queue delay measured separately in durable campaigns and real priority scenario",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("pipeline", "cache", "model"))
    parser.add_argument("--prefix", required=True, type=validate_prefix)
    parser.add_argument("--rows", type=int, choices=(1000000, 10000000), default=1000000)
    args = parser.parse_args()
    operation = (
        pipeline(args.prefix, args.rows)
        if args.mode == "pipeline"
        else cache_benchmark(args.prefix)
        if args.mode == "cache"
        else model_benchmark(args.prefix)
    )
    asyncio.run(operation)


if __name__ == "__main__":
    main()
