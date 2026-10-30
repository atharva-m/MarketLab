"""Actual owned Redis cache/failure campaign, with immutable invocation identity.

Requires independent source review before execution. Stops/restarts only the exact
ledger-verified Phase 3 Redis container; never changes Redis configuration or
flushes the database. All data/evidence stay under the ignored Phase 3 root.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import re
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from v2_phase3_acceptance import BASE, PROJECT, RETAINED, config, inventory, request, save, stamp

from marketlab.analytics.bars import BarService as LegacyBars
from marketlab.analytics.cache import CACHE_SCHEMA, MAX_VALUE, cache_key, canonical
from marketlab.analytics.v2 import BarsRequest
from marketlab.datasets.v2 import capacity
from marketlab.datasets.v2.common import sha256_file
from marketlab.research.v2.service import ResearchService
from marketlab.research.v2.spec import NUMERICS, ResearchSpec

OWNER = "v2-phase3-20261029"
EXPECTED_CONFIGURATION = {
    "maxmemory": "268435456",
    "maxmemory-policy": "allkeys-lru",
    "save": "",
    "appendonly": "no",
}


def configuration_text(raw: dict[Any, Any]) -> dict[str, str]:
    """CONFIG GET callbacks may return text even when ordinary values are bytes."""

    def text(value: Any) -> str:
        if type(value) is str:
            return value
        if type(value) is bytes:
            return value.decode("utf-8", errors="strict")
        raise ValueError("Invalid Redis configuration response type")

    result = {}
    for key, value in raw.items():
        decoded = text(key)
        if decoded in result:
            raise ValueError("Duplicate Redis configuration response field")
        result[decoded] = text(value)
    if set(result) != set(EXPECTED_CONFIGURATION):
        raise ValueError("Invalid Redis configuration response fields")
    return result


def diagnostic(error: BaseException) -> list[dict[str, Any]]:
    """Bounded source locations/types only; never exception messages, values or locals."""
    result = []
    visited = set()
    while error is not None and len(result) < 3 and id(error) not in visited:
        visited.add(id(error))
        frames = []
        traceback = error.__traceback__
        while traceback is not None:
            code = traceback.tb_frame.f_code
            path = Path(code.co_filename)
            try:
                filename = path.relative_to(PROJECT).as_posix()
            except ValueError:
                filename = path.name
            frames.append(
                {"filename": filename, "line": traceback.tb_lineno, "function": code.co_name}
            )
            traceback = traceback.tb_next
        result.append({"error_type": type(error).__name__, "frames": frames[-32:]})
        error = error.__cause__ or error.__context__
    return result


def docker(*arguments: str) -> str:
    return subprocess.check_output(["docker", *arguments], text=True, timeout=30).strip()


def owned_redis(expected: dict[str, Any], *, running: bool | None = None) -> dict[str, Any]:
    """Exact recorded identity is required before every container mutation."""
    assert re.fullmatch(r"[0-9a-f]{64}", expected["Id"])
    assert expected["Name"] == "/marketlab-v2p3-redis-r3"
    assert expected["Labels"] == {"marketlab.v2phase3.owner": OWNER}
    assert expected["Ports"] == {"6379/tcp": [{"HostIp": "127.0.0.1", "HostPort": "56392"}]}
    observed = json.loads(docker("inspect", expected["Id"]))[0]
    for field in ("Id", "Name", "Image", "Mounts"):
        assert observed[field] == expected[field]
    assert observed["Config"]["Labels"] == expected["Labels"]
    # Runtime port mappings may disappear while stopped; immutable host bindings
    # still identify the exact intended loopback destination before recovery.
    assert observed["HostConfig"]["PortBindings"] == expected["Ports"]
    if observed["State"]["Running"]:
        assert observed["NetworkSettings"]["Ports"] == expected["Ports"]
    if running is not None:
        assert observed["State"]["Running"] is running
    return observed


def transition(action: str, expected: dict[str, Any], folder: Path) -> dict[str, Any]:
    """CLI success plus exact native inspection establishes an owned state change."""
    if action not in {"stop", "start"}:
        raise ValueError("Invalid owned Redis transition")
    owned_redis(expected, running=action == "stop")
    arguments = ["docker", action, *(["--time", "5"] if action == "stop" else []), expected["Id"]]
    completed = subprocess.run(
        arguments, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30
    )
    stdout = completed.stdout
    record = {
        "action": action,
        "expected_id": expected["Id"],
        "returncode": completed.returncode,
        "stdout": stdout[:4096],
        "stdout_characters": len(stdout),
        "stdout_truncated": len(stdout) > 4096,
        "stdout_sha256_utf8": hashlib.sha256(stdout.encode()).hexdigest(),
        "stderr_characters": len(completed.stderr),
        "stderr_sha256_utf8": hashlib.sha256(completed.stderr.encode()).hexdigest(),
    }
    path = folder / ("docker-" + action + "-" + uuid4().hex + ".json")
    save(path, record)
    if completed.returncode != 0:
        raise RuntimeError("Owned Redis CLI transition failed")
    try:
        observed = owned_redis(expected, running=action == "start")
    except BaseException as error:
        record["inspection_error_stack"] = diagnostic(error)
        save(path, record)
        raise
    record.update(
        inspected_id=observed["Id"],
        running=observed["State"]["Running"],
        exact_identity_and_state_verified=True,
    )
    save(path, record)
    return observed


def protected() -> list[dict[str, Any]]:
    baseline = json.loads((BASE / "protected-before.json").read_text(encoding="utf-8-sig"))
    receipt = []
    for entry in baseline["files"]:
        path = (PROJECT / entry["path"]).resolve()
        assert path.is_relative_to(PROJECT.resolve()) and path.is_file()
        actual = sha256_file(path)
        assert actual == entry["sha256"]
        receipt.append({"path": entry["path"], "sha256": actual, "matches": True})
    return receipt


def originals() -> list[dict[str, Any]]:
    baseline = json.loads((BASE / "services-before.json").read_text(encoding="utf-8-sig"))
    receipt = []
    for expected in baseline["services"]:
        observed = json.loads(docker("inspect", expected["Id"]))[0]
        current = {key: observed[key] for key in ("Id", "Name", "Image", "RestartCount", "Mounts")}
        labels = observed["Config"]["Labels"]
        current.update(
            started_at=observed["State"]["StartedAt"],
            running=observed["State"]["Running"],
            health=observed["State"].get("Health", {}).get("Status"),
            Ports=observed["NetworkSettings"]["Ports"],
            compose_project=labels.get("com.docker.compose.project"),
            compose_service=labels.get("com.docker.compose.service"),
        )
        assert all(current.get(key) == value for key, value in expected.items())
        receipt.append(current)
    return receipt


def poison(key: str, body: dict[str, Any]) -> bytes:
    """Self-consistent hostile envelope exercises the production body validator."""
    return canonical(
        {
            "schema": CACHE_SCHEMA,
            "key": key,
            "body": body,
            "sha256": hashlib.sha256(canonical(body)).hexdigest(),
        }
    )


async def purge_pressure(client: Redis, prefix: str) -> None:
    assert re.fullmatch(r"p3:cache:pressure:p3-[A-Za-z0-9-]{1,76}:[0-9a-f]{32}:", prefix)
    batch = []
    async for key in client.scan_iter(match=prefix + "*", count=100):
        batch.append(key)
        if len(batch) == 100:
            await client.delete(*batch)
            batch = []
    if batch:
        await client.delete(*batch)


async def campaign(value: dict[str, Any], folder: Path, record: dict[str, Any]) -> dict[str, Any]:
    root = Path(value["storage_path"])
    ledger = json.loads((BASE / "owned-resources.json").read_text(encoding="utf-8-sig"))
    selected = [r for r in ledger if r["Name"] == "/marketlab-v2p3-redis-r3"]
    assert len(selected) == 1
    expected_container = selected[0]
    observed = owned_redis(expected_container, running=True)
    assert observed["State"]["StartedAt"] == expected_container["StartedAt"]
    assert (
        observed["HostConfig"]["Memory"] == 0 or observed["HostConfig"]["Memory"] >= 512 * 1024**2
    )
    client = Redis.from_url(
        value["redis_url"],
        decode_responses=False,
        socket_connect_timeout=3,
        socket_timeout=3,
        retry=Retry(NoBackoff(), 0),
        retry_on_timeout=False,
    )
    engine = sa.create_engine(value["database_url"])
    base = LegacyBars(engine, root, value["redis_url"])
    research = ResearchService(base)
    pressure = "p3:cache:pressure:" + folder.name + ":" + uuid4().hex + ":"
    targets: set[str] = set()
    restart_required = False
    steps: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "steps": steps,
        "redis_id": expected_container["Id"],
        "pressure_prefix": pressure,
        "memory_scope": "Redis samples only; other memory unmeasured",
    }
    input_hashes: dict[str, str] = {}

    def checkpoint(name: str, details: dict[str, Any]) -> None:
        steps.append({"name": name, "utc": stamp(datetime.now(UTC)), **details})
        save(folder / "progress.json", result)

    async def verify_configuration() -> dict[str, str]:
        raw = await client.config_get("maxmemory", "maxmemory-policy", "save", "appendonly")
        configuration = configuration_text(raw)
        assert configuration == EXPECTED_CONFIGURATION
        return configuration

    async def restore_redis() -> None:
        nonlocal restart_required
        if not restart_required:
            return
        current = await asyncio.to_thread(owned_redis, expected_container)
        if not current["State"]["Running"]:
            # Reverify exact ID/ownership immediately before starting this stopped container.
            await asyncio.to_thread(owned_redis, expected_container, running=False)
            await asyncio.to_thread(transition, "start", expected_container, folder)
        deadline = time.monotonic() + 30
        while True:
            try:
                if await client.ping():
                    break
            except Exception:
                if time.monotonic() >= deadline:
                    raise
            await asyncio.sleep(0.1)
        after = await asyncio.to_thread(owned_redis, expected_container, running=True)
        assert await verify_configuration() == EXPECTED_CONFIGURATION
        save(
            folder / "owned-redis-after-restart.json",
            {
                "Id": after["Id"],
                "Name": after["Name"],
                "Image": after["Image"],
                "Mounts": after["Mounts"],
                "Labels": after["Config"]["Labels"],
                "Ports": after["NetworkSettings"]["Ports"],
                "StartedAt": after["State"]["StartedAt"],
                "prior_started_at": expected_container["StartedAt"],
                "expected_owned_restart": True,
                "active_ledger_requires_refresh": True,
            },
        )
        checkpoint(
            "owned_redis_restored",
            {"started_at": after["State"]["StartedAt"], "configuration": EXPECTED_CONFIGURATION},
        )
        restart_required = False

    async def prepare_request(identity: str, version: str, day: str):
        chart = BarsRequest.create(
            instrument_id=identity,
            versions=[version],
            interval="5m",
            start=day + "T12:00:00Z",
            end=day + "T12:05:00Z",
        )
        reservation = await asyncio.to_thread(capacity.reserve, engine, root)
        try:
            rows = await research.bars.prepare_selection(
                [identity], [version], chart.start, chart.end, threading.Event()
            )
        finally:
            await asyncio.to_thread(capacity.release, engine, root, reservation)
        row = rows[0]
        for path in (
            row["manifest_path"],
            row["path"],
            row["manifest_path"].parent / "quality.json",
        ):
            actual = sha256_file(path)
            assert str(path) not in input_hashes or input_hashes[str(path)] == actual
            input_hashes[str(path)] = actual
        save(folder / "inputs-before.json", input_hashes)
        key = cache_key(
            "bars",
            [
                {
                    "version": row["dataset_version_id"],
                    "manifest": row["manifest_sha256"],
                    "semantic": row["semantic_sha256"],
                }
            ],
            chart.parameters() | {"metadata": row["metadata"]},
        )
        targets.add(key)
        return chart, key, rows

    async def read_chart(chart: BarsRequest, expected: dict[str, Any], outcome: str) -> None:
        actual, status = await research.bars.read(chart)
        assert actual == expected and status == outcome

    try:
        checkpoint(
            "configuration",
            {
                "configuration": await verify_configuration(),
                "container_memory_limit": observed["HostConfig"]["Memory"],
            },
        )
        chart, bar_key, rows = await prepare_request(
            "binance:spot:SOLUSDT", RETAINED["sol_official"], "2025-03-01"
        )
        spec = ResearchSpec.create(
            request(
                "market_profile",
                ["binance:spot:SOLUSDT"],
                [RETAINED["sol_official"]],
                "2025-03-01T00:00:00Z",
                "2025-03-01T01:00:00Z",
                "2025-03-02T00:00:00Z",
            )
        )
        save(
            folder / "fixtures.json",
            {
                "request": spec.body(),
                "chart": chart.parameters(),
                "dataset_versions": RETAINED,
                "pressure_values": 512,
                "pressure_value_bytes": 1024**2,
            },
        )
        run, replayed = await research.submit(spec, "p3-cache-" + folder.name)
        assert not replayed and await research.work(1, run) == 1
        info = research.inspect(run)
        assert info["state"] == "succeeded" and info["attempt_count"] == 1
        expected_summary, summary_hash = research.read(run, "summary")
        expected_results, results_hash = research.read(run, "results")
        summary_key = cache_key(
            "summary", {"v2_run": run, "sha256": summary_hash}, {"definition": NUMERICS}
        )
        targets.add(summary_key)
        await client.delete(bar_key, summary_key)
        expected_bars, bar_status = await research.bars.read(chart)
        assert bar_status == "MISS" and await client.exists(bar_key)
        await read_chart(chart, expected_bars, "HIT")

        async def read_summary(outcome: str) -> None:
            actual, status = await research.summary(run)
            assert actual == expected_summary and status == outcome

        await read_summary("MISS")
        await read_summary("HIT")
        assert 810 <= await client.ttl(bar_key) <= 990
        assert 3240 <= await client.ttl(summary_key) <= 3960
        checkpoint(
            "native_miss_hit",
            {
                "run_id": run,
                "bars": ["MISS", "HIT"],
                "summary": ["MISS", "HIT"],
                "results_sha256": results_hash,
                "summary_sha256": summary_hash,
            },
        )
        for kind, key in (("bars", bar_key), ("summary", summary_key)):
            for bad in (b'{"invalid":true}', b"x" * (MAX_VALUE + 1)):
                await client.set(key, bad)
                await (
                    read_chart(chart, expected_bars, "MISS")
                    if kind == "bars"
                    else read_summary("MISS")
                )
        hostile_cases = []
        for name, updates in (
            ("schema", {"schema": "bars-v1", "definition": "bars-v1"}),
            ("instrument", {"instrument_id": "binance:spot:BTCUSDT"}),
            ("version", {"dataset_versions": [RETAINED["sol_csv"]]}),
        ):
            candidate = copy.deepcopy(expected_bars)
            candidate.update(updates)
            await client.set(bar_key, poison(bar_key, candidate))
            await read_chart(chart, expected_bars, "MISS")
            hostile_cases.append(name)
        checkpoint(
            "corruption_and_binding",
            {
                "corrupt_and_oversize": "bars+summary rejected",
                "self_consistent_hostile_envelopes": hostile_cases,
            },
        )
        for identity, version, day in (
            ("binance:spot:SOLUSDT", RETAINED["sol_csv"], "2025-03-01"),
            ("binance:spot:BTCUSDT", RETAINED["btc_official"], "2025-02-01"),
        ):
            alternative, key, _ = await prepare_request(identity, version, day)
            assert key != bar_key
            await client.delete(key)
            body, status = await research.bars.read(alternative)
            assert status == "MISS" and body["instrument_id"] == identity
            assert body["dataset_versions"] == [version]
            await read_chart(alternative, body, "HIT")
            if identity == "binance:spot:SOLUSDT":
                assert body["bars"] == expected_bars["bars"]
        checkpoint("native_instrument_and_version_isolation", {"independent_keys": True})

        # Native unchanged allkeys-lru pressure, bounded cumulative writes and RSS samples.
        await read_chart(chart, expected_bars, "HIT")
        await read_summary("HIT")
        before = int((await client.info("stats"))["evicted_keys"])
        pressure_value = b"p3" * (1024**2 // 2)
        samples = []
        for index in range(512):
            assert await client.set(pressure + str(index), pressure_value, ex=600)
            if index % 8 == 0:
                memory = await client.info("memory")
                samples.append(
                    {
                        "index": index,
                        "used_memory_rss": int(memory["used_memory_rss"]),
                        "used_memory": int(memory["used_memory"]),
                    }
                )
                assert samples[-1]["used_memory_rss"] < 512 * 1024**2
        after = int((await client.info("stats"))["evicted_keys"])
        assert (
            after > before
            and not await client.exists(bar_key)
            and not await client.exists(summary_key)
        )
        await read_chart(chart, expected_bars, "MISS")
        await read_chart(chart, expected_bars, "HIT")
        await read_summary("MISS")
        await read_summary("HIT")
        checkpoint(
            "native_eviction",
            {
                "evicted_before": before,
                "evicted_after": after,
                "written_values": 512,
                "value_bytes": len(pressure_value),
                "cumulative_written_bytes": 512 * len(pressure_value),
                "rss_samples": samples,
            },
        )
        await purge_pressure(client, pressure)

        await asyncio.to_thread(owned_redis, expected_container, running=True)
        restart_required = True  # Even an interrupted stop command must enter recovery.
        await asyncio.to_thread(transition, "stop", expected_container, folder)
        await asyncio.to_thread(owned_redis, expected_container, running=False)
        checkpoint("owned_redis_stopped", {"Id": expected_container["Id"]})
        try:
            await read_chart(chart, expected_bars, "BYPASS")
            await read_summary("BYPASS")
            outage_run, replayed = await research.submit(spec, "p3-cache-outage-" + folder.name)
            assert not replayed and await research.work(1, outage_run) == 1
            outage_info = research.inspect(outage_run)
            assert outage_info["state"] == "succeeded" and outage_info["attempt_count"] == 1
            assert research.read(outage_run, "results") == (expected_results, results_hash)
            assert research.read(outage_run, "summary") == (expected_summary, summary_hash)
            checkpoint(
                "actual_outage_numerical_independence",
                {
                    "run_id": outage_run,
                    "bars": "BYPASS",
                    "summary": "BYPASS",
                    "equal_numerical_hashes": True,
                    "attempt_count": 1,
                    "memo_available": outage_info["memo_available"],
                },
            )
        finally:
            await restore_redis()
        wait = max(0.0, base.cache.open_until - time.monotonic()) + 0.05
        assert wait <= 10.1
        await asyncio.sleep(wait)
        await read_chart(chart, expected_bars, "MISS")
        await read_chart(chart, expected_bars, "HIT")
        await read_summary("MISS")
        await read_summary("HIT")
        checkpoint(
            "cache_recovered",
            {
                "actual_breaker_wait_seconds": wait,
                "bars": ["MISS", "HIT"],
                "summary": ["MISS", "HIT"],
            },
        )
        input_after = {path: sha256_file(Path(path)) for path in input_hashes}
        assert input_after == input_hashes
        save(folder / "inputs-after.json", input_after)
        result.update(
            run_id=run,
            results_sha256=results_hash,
            summary_sha256=summary_hash,
            protected_inputs_equal=True,
            active_ledger_requires_refresh=True,
        )
        return result
    finally:
        try:
            await restore_redis()
        finally:
            try:
                await purge_pressure(client, pressure)
                if targets:
                    await client.delete(*sorted(targets))
                checkpoint(
                    "owned_cache_keys_removed",
                    {"pressure_namespace": pressure, "exact_target_keys": sorted(targets)},
                )
            finally:
                await research.close()
                await base.close()
                await client.aclose()
                engine.dispose()
                record["cache_campaign"] = result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--invocation", required=True)
    args = parser.parse_args()
    assert re.fullmatch(r"p3-[A-Za-z0-9-]{1,76}", args.invocation)
    folder = BASE / args.invocation
    folder.mkdir(exist_ok=False)
    started = time.monotonic()
    record = {
        "action": "actual-cache",
        "invocation": args.invocation,
        "status": "running",
        "started_utc": stamp(datetime.now(UTC)),
        "source_before": inventory(),
        "memory": "Redis sampled RSS only; no campaign peak claim",
    }
    save(folder / "invocation.json", record)
    try:
        value = config(args.config)  # Exact immutable active-ledger identity/start check.
        save(folder / "protected-before.json", protected())
        save(folder / "originals-before.json", originals())
        record["result"] = asyncio.run(campaign(value, folder, record))
        record["status"] = "passed"
    except BaseException as error:
        record.update(
            status="failed", error_type=type(error).__name__, error_stack=diagnostic(error)
        )
    finally:
        try:
            save(folder / "protected-after.json", protected())
            save(folder / "originals-after.json", originals())
            record["source_after"] = inventory()
            assert record["source_after"] == record["source_before"]
        except BaseException as error:
            record.update(
                status="failed",
                preservation_error_type=type(error).__name__,
                preservation_error_stack=diagnostic(error),
            )
        record.update(
            finished_utc=stamp(datetime.now(UTC)), elapsed_seconds=time.monotonic() - started
        )
        save(folder / "invocation.json", record)
    print(
        json.dumps(
            {
                "status": record["status"],
                "invocation": args.invocation,
                "elapsed_seconds": record["elapsed_seconds"],
            }
        )
    )
    return 0 if record["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
