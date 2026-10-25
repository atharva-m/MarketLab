"""Owned-resource R5 retained-month copilot/manual numerical equivalence.

Uses all 62 retained registrations and the independent R4 numerical reference.
Does not download data, change prior artifacts, migrate databases or manage services.
"""

import argparse
import asyncio
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
import time
import zipfile
from collections.abc import Awaitable
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import sqlalchemy as sa

from marketlab.analytics.bars import BarService
from marketlab.analytics.cache import canonical
from marketlab.config import Settings
from marketlab.copilot import store as copilot_store
from marketlab.copilot.model import Ollama
from marketlab.copilot.service import CopilotService
from marketlab.datasets.publication import dataset_versions, ingest_archive
from marketlab.datasets.source import file_hash
from marketlab.research import store as research_store
from marketlab.research.service import ResearchService, execution_identity
from marketlab.research.spec import ResearchError, ResearchSpec, utc

BASE = Path("artifacts/r5")
ROOT = Path("artifacts/r2/historical-storage").resolve()
MODEL = "qwen3.5:4b-q8_0"
DIGEST = "e15635ee93129fd2086640926e900c37589c5167561104abc3914bd6644c7e07"


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)


async def observed(operation: Awaitable[Any], output: Path, phase: str, index: int) -> Any:
    """Persist progress during cold verification without changing service bounds."""
    began = time.perf_counter()
    task = asyncio.create_task(operation)
    progress = output.with_suffix(".progress.json")
    try:
        while not task.done():
            snapshot = {"phase": phase, "index": index, "seconds": time.perf_counter() - began}
            save(progress, snapshot)
            print(json.dumps({"progress": snapshot}), flush=True)
            await asyncio.wait({task}, timeout=30)
        return await task
    except BaseException:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise


def owned_settings() -> Settings:
    settings = Settings()
    url = settings.sqlalchemy_url
    if (url.host, url.port, url.database) != ("127.0.0.1", 55438, "marketlab"):
        raise RuntimeError("Acceptance requires the explicitly owned R5 database")
    if settings.redis_url.get_secret_value() != "redis://127.0.0.1:56380/0":
        raise RuntimeError("Acceptance requires the explicitly owned R5 Redis")
    if settings.ollama_url != "http://127.0.0.1:11435":
        raise RuntimeError("Acceptance requires the explicitly owned R5 Ollama")
    for name, port, host_port in (
        ("postgres", "5432/tcp", "55438"),
        ("redis", "6379/tcp", "56380"),
    ):
        saved = json.loads((BASE / f"owned-{name}.json").read_text(encoding="utf-8-sig"))
        actual = json.loads(subprocess.check_output(["docker", "inspect", saved["Id"]]))[0]
        assert actual["Id"] == saved["Id"] and actual["Name"] == saved["Name"]
        assert actual["Config"]["Labels"]["marketlab.r5.owner"] == "r5-20261025"
        assert actual["State"]["Running"]
        assert actual["NetworkSettings"]["Ports"][port] == [
            {"HostIp": "127.0.0.1", "HostPort": host_port}
        ]
    return settings


def restore(engine: sa.Engine) -> list[dict[str, Any]]:
    records = json.loads(Path("artifacts/r2/catalog-final.json").read_text(encoding="utf-8"))[
        "catalog"
    ]
    assert len(records) == 62 and sum(r["row_count"] for r in records) == 230311900
    # Verify saved registration identity against existing immutable manifests first.
    for record in records:
        manifest = ROOT / record["manifest_path"]
        assert manifest.is_relative_to(ROOT) and file_hash(manifest) == record["manifest_sha256"]
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        assert file_hash(manifest.parent / "trades.parquet") == payload["artifact"]["sha256"]
    with engine.begin() as connection:
        for record in records:
            existing = (
                connection.execute(
                    sa.select(dataset_versions).where(
                        dataset_versions.c.dataset_version_id == record["dataset_version_id"]
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                assert existing["manifest_sha256"] == record["manifest_sha256"]
                assert existing["manifest_path"] == record["manifest_path"]
                continue
            row = dict(record)
            row["trade_date"] = date.fromisoformat(row["trade_date"])
            row["published_at"] = datetime.fromisoformat(row["published_at"])
            connection.execute(dataset_versions.insert().values(**row))
    return records


def expected_spec(intent: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    first = utc(intent["history_start"]).date()
    end = utc(intent["end"])
    from datetime import timedelta

    before = (end - timedelta(microseconds=1)).date()
    versions = sorted(
        r["dataset_version_id"]
        for r in records
        if r["symbol"] in intent["symbols"]
        and first <= date.fromisoformat(r["trade_date"]) <= before
    )
    # Independent assembly uses the published contract's fixed constants.
    return {
        "schema": "research-spec-v1",
        **intent,
        "symbols": sorted(intent["symbols"]),
        "metrics": sorted(intent["metrics"]),
        "dataset_versions": versions,
        "parameters": {},
        "predicates": {"volatility_quantile": "0.9", "volume_multiple": "2", "min_bars": 2}
        if intent["workflow"] == "volatility_cluster"
        else {},
    }


async def finish_copilot(service: CopilotService, request_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 420
    while time.monotonic() < deadline:
        info = service.inspect(request_id)
        if info["state"] in {"completed", "failed"}:
            return info
        await service.work(1, request_id)
        info = service.inspect(request_id)
        if info["state"] in {"completed", "failed"}:
            return info
        # Observe the durable DB-time gate; never reset eligibility or attempts.
        await asyncio.sleep(0.5)
    raise TimeoutError("Bounded copilot acceptance did not reach a terminal state")


async def durability_live(prefix: str) -> None:
    """Actual database-time retry/heartbeat/expiry; no edited eligibility clocks."""
    settings = owned_settings()
    engine = sa.create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
    schema = "r5_live_" + uuid4().hex
    isolated = engine.execution_options(schema_translate_map={None: schema})
    names = (
        "trades",
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
    )
    body = {
        "schema": "copilot-request-v1",
        "text": "Probe only: no model dispatched",
        "context": {},
        "dataset_versions": ["a" * 64],
    }
    evidence: dict[str, Any] = {
        "status": "running",
        "schema": schema,
        "clock_policy": "Real clock_timestamp eligibility and 60s leases; no timestamp edits",
        "checks": {},
    }
    output = BASE / f"{prefix}-durability-live.json"
    start = time.perf_counter()

    def state(request_id: str) -> dict[str, Any]:
        with isolated.connect() as connection:
            row = dict(
                connection.execute(
                    sa.select(copilot_store.jobs).where(
                        copilot_store.jobs.c.request_id == request_id
                    )
                )
                .mappings()
                .one()
            )
            row["database_now"] = connection.scalar(sa.select(sa.func.clock_timestamp()))
            return row

    async def wait_database(request_id: str, field: str) -> dict[str, Any]:
        deadline = time.monotonic() + 100
        while time.monotonic() < deadline:
            row = await asyncio.to_thread(state, request_id)
            if row["database_now"] >= row[field]:
                return row
            await asyncio.sleep(0.25)
        raise TimeoutError("Database clock did not reach the persisted gate")

    try:
        with engine.begin() as connection:
            connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            for name in names:
                connection.execute(
                    sa.text(f'CREATE TABLE "{schema}".{name} (LIKE public.{name} INCLUDING ALL)')
                )
        immediate_started = time.perf_counter()
        for index in range(100):
            request_id, _, _ = copilot_store.create(isolated, body, f"immediate-{index}")
            claim = copilot_store.claim(isolated, request_id)
            assert claim is not None and claim.attempt == 1
            copilot_store.fail(isolated, claim)
        evidence["checks"]["immediate_claims"] = {
            "count": 100,
            "seconds": time.perf_counter() - immediate_started,
        }
        retry_id, _, _ = copilot_store.create(isolated, body, "retry-gates")
        current = copilot_store.claim(isolated, retry_id)
        assert current is not None
        gates = []
        for expected_delay in (10, 30):
            before = time.perf_counter()
            copilot_store.fail(isolated, current, transient=True)
            waiting = state(retry_id)
            assert copilot_store.claim(isolated, retry_id) is None
            due = await wait_database(retry_id, "eligible_at")
            newer = copilot_store.claim(isolated, retry_id)
            assert newer is not None and newer.attempt == current.attempt + 1
            gates.append(
                {
                    "expected_backoff_seconds": expected_delay,
                    "eligible_at": waiting["eligible_at"],
                    "database_now_when_due": due["database_now"],
                    "observed_host_seconds": time.perf_counter() - before,
                    "attempt": newer.attempt,
                }
            )
            current = newer
        copilot_store.fail(isolated, current)
        assert copilot_store.claim(isolated, retry_id) is None
        evidence["checks"]["retry_gates"] = gates
        save(output, evidence)

        lease_id, _, _ = copilot_store.create(isolated, body, "lease-budget")
        current = copilot_store.claim(isolated, lease_id)
        assert current is not None
        heartbeats = []
        for _ in range(2):
            await asyncio.sleep(10)
            assert copilot_store.heartbeat(isolated, current)
            heartbeats.append(state(lease_id))
        evidence["checks"]["heartbeats"] = heartbeats
        cycles = []
        for cycle in range(3):
            before = time.perf_counter()
            due = await wait_database(lease_id, "lease_until")
            assert not copilot_store.heartbeat(isolated, current)
            rejected = []
            for name, operation in (
                ("reserve_call", lambda c=current: copilot_store.reserve_call(isolated, c)),
                ("checkpoint", lambda c=current: copilot_store.checkpoint(isolated, c, {}, {})),
                ("fail", lambda c=current: copilot_store.fail(isolated, c)),
                ("finish", lambda c=current: copilot_store.finish(isolated, c, "unsupported", [])),
            ):
                try:
                    operation()
                except ResearchError as error:
                    assert error.status == 409
                    rejected.append(name)
                else:
                    raise AssertionError("Expired worker mutation succeeded: " + name)
            newer = copilot_store.claim(isolated, lease_id)
            cycles.append(
                {
                    "cycle": cycle + 1,
                    "expired_attempt": current.attempt,
                    "token": current.token,
                    "database_now_when_expired": due["database_now"],
                    "lease_until": due["lease_until"],
                    "observed_host_wait_seconds": time.perf_counter() - before,
                    "rejected": rejected,
                    "reclaimed": newer is not None,
                }
            )
            evidence["checks"]["lease_cycles"] = cycles
            save(output, evidence)
            if cycle < 2:
                assert newer is not None and newer.token > current.token
                assert newer.attempt == current.attempt + 1
                current = newer
            else:
                assert newer is None
        final = copilot_store.inspect(isolated, lease_id)
        assert final["state"] == "failed" and final["revisions"][-1]["attempt_count"] == 3
        assert len(final["revisions"][-1]["attempts"]) == 3
        evidence["checks"]["no_fourth_attempt"] = final
        call_id, _, _ = copilot_store.create(isolated, body, "call-budget")
        current = copilot_store.claim(isolated, call_id)
        assert current is not None
        copilot_store.reserve_call(isolated, current)
        copilot_store.reserve_call(isolated, current)
        try:
            copilot_store.reserve_call(isolated, current)
        except ResearchError:
            pass
        else:
            raise AssertionError("Third inference reservation succeeded")
        copilot_store.fail(isolated, current)
        evidence["checks"]["two_call_budget"] = copilot_store.inspect(isolated, call_id)
        evidence.update(status="passed", seconds=time.perf_counter() - start)
    except BaseException as error:
        evidence.update(
            status="failed",
            error_type=type(error).__name__,
            error=str(error),
            seconds=time.perf_counter() - start,
        )
        raise
    finally:
        with engine.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        evidence["owned_schema_removed"] = True
        save(output, evidence)
        engine.dispose()


def interfaces_live(prefix: str) -> None:
    """Actual TCP API/CLI, cache and retained ingestion checks on owned services."""
    settings = owned_settings()
    engine = sa.create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
    records = restore(engine)
    evidence: dict[str, Any] = {
        "status": "running",
        "execution": execution_identity(),
        "checks": {},
    }
    output = BASE / f"{prefix}-interfaces-live.json"
    env = os.environ.copy()
    env["MARKETLAB_STORAGE_PATH"] = str(ROOT)
    env["MARKETLAB_COPILOT_MODEL_DIGEST"] = DIGEST
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    log_path = BASE / f"{prefix}-api.log"
    process = None
    client = None

    def cli(module: str, *arguments: str, extra_env: dict[str, str] | None = None) -> Any:
        invocation = subprocess.run(
            [sys.executable, "-m", module, *arguments],
            env={**env, **(extra_env or {})},
            capture_output=True,
            text=True,
            timeout=240,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if invocation.returncode != 0:
            raise AssertionError(f"Owned CLI failed: {module}: {invocation.stderr[:400]}")
        return json.loads(invocation.stdout)

    try:
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "marketlab.app:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--loop",
                    "asyncio:SelectorEventLoop",
                    "--no-access-log",
                ],
                env=env,
                stdout=log,
                stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        evidence["owned_api"] = {"pid": process.pid, "port": port, "log": str(log_path)}
        save(output, evidence)
        client = httpx.Client(
            base_url=f"http://127.0.0.1:{port}",
            timeout=240,
            trust_env=False,
            follow_redirects=False,
        )
        for _ in range(200):
            try:
                if client.get("/health/live").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if process.poll() is not None:
                raise AssertionError("Owned API exited before readiness")
            time.sleep(0.1)
        else:
            raise AssertionError("Owned API failed startup")
        assert client.get("/health/ready").status_code == 200
        openapi = client.get("/openapi.json").json()
        assert "/v1/copilot/requests" in openapi["paths"]
        assert "/v1/research/runs" in openapi["paths"] and "/trades" in openapi["paths"]
        evidence["checks"]["startup_openapi_health"] = "passed"
        save(output, evidence)

        symbol = "R5" + uuid4().hex[:8].upper()
        identity = "R5" + uuid4().hex[:12]
        trades = [
            {
                "trade_id": identity + tail,
                "symbol": symbol,
                "price": "1.25",
                "quantity": "2.5",
                "executed_at": "2025-01-03T01:00:00Z",
            }
            for tail in ("A", "a")
        ]
        response = client.post("/trades/import/json", json=trades)
        assert response.status_code == 200 and response.json()["imported"] == 2
        assert (
            client.post(
                "/trades/import/json", content="[]", headers={"Content-Type": "text/plain"}
            ).status_code
            == 415
        )
        assert (
            client.post(
                "/trades/import/json",
                content=b" " * (1048576 + 1),
                headers={"Content-Type": "application/json"},
            ).status_code
            == 413
        )
        uncommitted = {**trades[0], "trade_id": identity + "B"}
        assert client.post("/trades/import/json", json=[uncommitted, trades[0]]).status_code == 409
        assert client.get("/trades/" + uncommitted["trade_id"]).status_code == 404
        stored_trade = {
            **trades[0],
            "price": "1.25000000",
            "quantity": "2.50000000",
        }
        assert client.get("/trades/" + trades[0]["trade_id"]).json() == stored_trade
        page = client.get(
            "/trades",
            params={
                "symbol": symbol,
                "after_id": identity + "Z",
                "executed_from": "2025-01-03T01:00:00Z",
                "executed_before": "2025-01-03T01:05:00Z",
                "limit": 1,
            },
        ).json()
        assert [r["trade_id"] for r in page["items"]] == [trades[1]["trade_id"]]
        lookup = cli(
            "marketlab.trade_cli", "--port", str(port), "--trade-id", trades[0]["trade_id"]
        )
        assert lookup == stored_trade
        evidence["checks"]["legacy_import_transaction_case_filter_cli"] = "passed"
        save(output, evidence)

        selected = next(
            row
            for row in records
            if row["symbol"] == "BTCUSDT" and row["trade_date"] == "2025-01-03"
        )
        params = {
            "version": selected["dataset_version_id"],
            "symbol": "BTCUSDT",
            "interval": "5m",
            "start": "2025-01-03T03:00:00Z",
            "end": "2025-01-03T04:00:00Z",
        }
        first = client.get("/v1/bars", params=params)
        second = client.get("/v1/bars", params=params)
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json() and second.headers["x-cache"] == "HIT"
        independent = json.loads(
            (
                Path("artifacts/r4/reference-data")
                / f"reference-{selected['dataset_version_id']}.json"
            ).read_text(encoding="utf-8")
        )
        assert second.json()["bars"] == [
            bar for bar in independent["five"] if params["start"] <= bar["start"] < params["end"]
        ]
        evidence["checks"]["exact_bars_real_cache"] = {
            "headers": [first.headers["x-cache"], second.headers["x-cache"]],
            "bars": len(second.json()["bars"]),
        }
        save(output, evidence)

        request = {
            "schema": "copilot-request-v1",
            "text": "Study Bitcoin recently.",
            "dataset_versions": sorted(r["dataset_version_id"] for r in records),
            "context": {},
        }
        request_path = BASE / f"{prefix}-request.json"
        save(request_path, request)
        created = client.post(
            "/v1/copilot/requests", json=request, headers={"Idempotency-Key": prefix + "-http"}
        )
        assert created.status_code == 201
        request_id = created.json()["request_id"]
        assert (
            client.post(
                "/v1/copilot/requests", json=request, headers={"Idempotency-Key": prefix + "-http"}
            ).status_code
            == 200
        )
        assert (
            cli("marketlab.copilot_cli", "worker", "--max-jobs", "1", "--request", request_id)[
                "attempted_jobs"
            ]
            == 1
        )
        initial = client.get("/v1/copilot/requests/" + request_id).json()
        assert initial["outcome"] == "needs_clarification" and initial["run_id"] is None
        context = {
            "workflow": "market_profile",
            "symbols": ["BTCUSDT"],
            "start": "2025-01-03T01:00:00Z",
            "end": "2025-01-03T02:00:00Z",
            "history_start": "2025-01-01T00:00:00Z",
            "interval": "5m",
            "metrics": ["profile"],
        }
        answer = {
            "schema": "copilot-answer-v1",
            "expected_revision": 0,
            "text": "Use these explicit descriptive OHLCV research choices.",
            "context": context,
        }
        answered = client.post(
            f"/v1/copilot/requests/{request_id}/clarifications",
            json=answer,
            headers={"Idempotency-Key": prefix + "-answer"},
        )
        assert answered.status_code == 201, answered.text
        answer_path = BASE / f"{prefix}-answer.json"
        save(answer_path, answer)
        replay = cli(
            "marketlab.copilot_cli",
            "answer",
            "--request",
            request_id,
            "--answer",
            str(answer_path),
            "--key",
            prefix + "-answer",
        )
        assert replay["replayed"] and replay["revision"] == 1
        assert (
            cli("marketlab.copilot_cli", "worker", "--max-jobs", "1", "--request", request_id)[
                "attempted_jobs"
            ]
            == 1
        )
        completed = cli("marketlab.copilot_cli", "inspect", "--request", request_id)
        assert completed["outcome"] == "submitted", completed
        run_id = completed["run_id"]
        cli("marketlab.research_cli", "worker", "--max-runs", "1", "--run", run_id)
        result = client.get(f"/v1/research/runs/{run_id}/results")
        summary = client.get(f"/v1/research/runs/{run_id}/summary")
        warm = client.get(f"/v1/research/runs/{run_id}/summary")
        assert result.status_code == summary.status_code == warm.status_code == 200
        assert summary.json() == warm.json() and warm.headers["x-cache"] == "HIT"
        evidence["checks"]["http_clarification_cli_replay_research"] = {
            "request_id": request_id,
            "run_id": run_id,
            "revision": completed["current_revision"],
            "summary_cache": [summary.headers["x-cache"], warm.headers["x-cache"]],
        }

        fixture_root = BASE / f"{prefix}-fixture-storage"
        fixture_root.mkdir(parents=True, exist_ok=True)
        archive = fixture_root / "BTCUSDT-trades-2025-01-01.zip"
        with zipfile.ZipFile(archive, "w") as compressed:
            compressed.writestr(
                "BTCUSDT-trades-2025-01-01.csv", "1,100,1,100,1735689600000000,True,True\n"
            )
        checksum = fixture_root / "source.CHECKSUM"
        checksum.write_text(file_hash(archive) + "  " + archive.name, encoding="utf-8")
        published = ingest_archive(engine, fixture_root, archive, checksum)
        assert ingest_archive(engine, fixture_root, archive, checksum) == published
        inspected = cli(
            "marketlab.dataset_cli",
            "inspect",
            "--version",
            published["dataset_version_id"],
            extra_env={"MARKETLAB_STORAGE_PATH": str(fixture_root.resolve())},
        )
        assert inspected["dataset_version_id"] == published["dataset_version_id"]
        evidence["checks"]["historical_fixture_sync_repeat_inspect_cli"] = published[
            "dataset_version_id"
        ]
        metrics = client.get("/metrics")
        assert metrics.status_code == 200 and "marketlab_copilot" in metrics.text
        assert execution_identity() == evidence["execution"], (
            "Source changed during live interfaces"
        )
        evidence["status"] = "passed"
    except BaseException as error:
        evidence.update(status="failed", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        if client is not None:
            client.close()
        if process is not None:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
            else:
                process.terminate()
            process.wait(timeout=15)
            evidence["owned_api_removed"] = True
        save(output, evidence)
        engine.dispose()


async def retained_results(prefix: str) -> None:
    """Read all ten old registered R4 runs under final R5 source without rewriting."""
    settings = owned_settings()
    engine = sa.create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
    schema = "r5_retained_" + uuid4().hex
    isolated = engine.execution_options(schema_translate_map={None: schema})
    retained_path = Path("artifacts/r4/catalog-final.json")
    retained = json.loads(await asyncio.to_thread(retained_path.read_text, encoding="utf-8"))
    reference_path = Path("artifacts/r4/reference-workflows.json")
    references = json.loads(await asyncio.to_thread(reference_path.read_text, encoding="utf-8"))
    evidence: dict[str, Any] = {
        "status": "running",
        "catalog_snapshot_sha256": file_hash(retained_path),
        "execution": execution_identity(),
        "readbacks": [],
    }
    output = BASE / f"{prefix}-retained-results.json"
    bars = None
    reader = worker = None

    class OldResultReader(ResearchService):
        @property
        def execution(self) -> dict[str, Any]:
            raise AssertionError("Old numerical retrieval must not request current Git provenance")

    try:
        with engine.begin() as connection:
            connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            for name in (
                "dataset_versions",
                "research_submissions",
                "research_runs",
                "research_attempts",
                "research_results",
            ):
                connection.execute(
                    sa.text(f'CREATE TABLE "{schema}".{name} (LIKE public.{name} INCLUDING ALL)')
                )
        assert len(retained["research_results"]) == len(retained["research_runs"]) == 10
        assert all(run["state"] == "succeeded" for run in retained["research_runs"])
        tables = {
            "dataset_versions": dataset_versions,
            "research_submissions": research_store.submissions,
            "research_runs": research_store.runs,
            "research_attempts": research_store.attempts,
            "research_results": research_store.results,
        }
        with isolated.begin() as connection:
            for name, table in tables.items():
                for record in retained[name]:
                    row = dict(record)
                    for column in table.columns:
                        if row.get(column.name) is not None:
                            if isinstance(column.type, sa.DateTime):
                                row[column.name] = datetime.fromisoformat(row[column.name])
                            elif isinstance(column.type, sa.Date):
                                row[column.name] = date.fromisoformat(row[column.name])
                    connection.execute(table.insert().values(**row))
        bars = BarService(isolated, ROOT, settings.redis_url.get_secret_value())
        reader = OldResultReader(bars)
        submissions = {row["submission_id"]: row for row in retained["research_submissions"]}
        results = {row["run_id"]: row for row in retained["research_results"]}
        for run in retained["research_runs"]:
            run_id = run["run_id"]
            source = submissions[run["submission_id"]]
            spec = json.loads(source["spec"])
            canonical_spec = ResearchSpec.create(spec).body()
            reference = next(
                row
                for row in references
                if ResearchSpec.create(row["spec"]).body() == canonical_spec
            )
            result, result_hash = reader.read(run_id, "results")
            summary, cache = await reader.summary(run_id)
            summary_hash = hashlib.sha256(canonical(summary)).hexdigest()
            assert result == reference["results"] and summary == reference["summary"]
            assert result_hash == results[run_id]["results_sha256"] == reference["results_sha256"]
            assert summary_hash == results[run_id]["summary_sha256"] == reference["summary_sha256"]
            evidence["readbacks"].append(
                {
                    "run_id": run_id,
                    "results_sha256": result_hash,
                    "summary_sha256": summary_hash,
                    "cache": cache,
                }
            )
            save(output, evidence)
        # A new queued execution carrying the old source identity must still refuse.
        worker = ResearchService(bars)
        source = retained["research_submissions"][0]
        fingerprint = json.loads(source["fingerprint"])
        assert fingerprint["execution"] != worker.execution
        queued, _ = research_store.submit(
            isolated, prefix + "-incompatible", json.loads(source["spec"]), fingerprint
        )
        assert await worker.work(1, queued) == 1
        rejected = worker.inspect(queued)
        assert rejected["state"] == "failed" and rejected["attempt_count"] == 1
        with isolated.connect() as connection:
            assert (
                connection.scalar(
                    sa.select(sa.func.count())
                    .select_from(research_store.results)
                    .where(research_store.results.c.run_id == queued)
                )
                == 0
            )
        evidence["incompatible_queued_refused"] = {
            "run_id": queued,
            "state": rejected["state"],
            "attempt_count": rejected["attempt_count"],
            "error": rejected["error"],
        }
        assert execution_identity() == evidence["execution"]
        evidence["status"] = "passed"
    except BaseException as error:
        evidence.update(status="failed", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        if reader is not None:
            await reader.close()
        if worker is not None:
            await worker.close()
        if bars is not None:
            await bars.close()
        with engine.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        evidence["owned_schema_removed"] = True
        save(output, evidence)
        engine.dispose()


def month_text(spec: dict[str, Any]) -> str:
    return (
        f"Run {spec['workflow']} for {' and '.join(spec['symbols'])} using 5m bars. "
        f"Metrics: {', '.join(spec['metrics'])}. "
        f"Inclusive start {spec['start']}; exclusive end {spec['end']}; "
        f"history from {spec['history_start']}. "
        + (
            "Use the fixed R4 cluster definition."
            if spec["workflow"] == "volatility_cluster"
            else "Use descriptive OHLCV where applicable."
        )
    )


async def main(prefix: str) -> None:
    settings = owned_settings()
    engine = sa.create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
    records = await asyncio.to_thread(restore, engine)
    reference_path = Path("artifacts/r4/reference-workflows.json")
    references = json.loads(await asyncio.to_thread(reference_path.read_text, encoding="utf-8"))
    assert len(references) == 5
    bars = BarService(engine, ROOT, settings.redis_url.get_secret_value())
    research = ResearchService(bars)
    copilot = CopilotService(research, Ollama(settings.ollama_url, MODEL, DIGEST))
    output = BASE / f"{prefix}-month.json"
    evidence: dict[str, Any] = {
        "status": "running",
        "hardware": platform.platform(),
        "peak_memory": "unmeasured",
        "partitions": len(records),
        "input_rows": sum(r["row_count"] for r in records),
        "reference_sha256": file_hash(reference_path),
        "execution": research.execution,
        "runs": [],
        "copilot_requests": [],
    }
    began = time.perf_counter()
    try:
        for index, reference in enumerate(references):
            started = time.perf_counter()
            spec = ResearchSpec.create(reference["spec"])
            body = {
                "schema": "copilot-request-v1",
                "text": month_text(spec.body()),
                "dataset_versions": sorted(r["dataset_version_id"] for r in records),
                "context": {},
            }
            request_id, revision, replayed = await copilot.create(body, f"{prefix}-copilot-{index}")
            assert await copilot.create(body, f"{prefix}-copilot-{index}") == (
                request_id,
                revision,
                True,
            )
            info = await observed(
                finish_copilot(copilot, request_id),
                output,
                "copilot_interpretation_validation",
                index,
            )
            assert info["outcome"] == "submitted", info
            assert info["revisions"][-1]["spec"] == spec.body()
            evidence["copilot_requests"].append(info)
            copilot_run = info["run_id"]
            manual_run, _ = await observed(
                research.submit(spec, f"{prefix}-manual-{index}"),
                output,
                "manual_validation",
                index,
            )
            assert copilot_run != manual_run
            hashes = []
            for kind, run_id in (("copilot", copilot_run), ("manual", manual_run)):
                assert (
                    await observed(
                        research.work(1, run_id), output, kind + "_numerical_execution", index
                    )
                    == 1
                )
                status = research.inspect(run_id)
                assert status["state"] == "succeeded", status
                result, result_hash = research.read(run_id, "results")
                summary, cache = await research.summary(run_id)
                warm, warm_cache = await research.summary(run_id)
                summary_hash = hashlib.sha256(canonical(summary)).hexdigest()
                assert result == reference["results"] and summary == reference["summary"]
                assert (
                    result_hash == reference["results_sha256"]
                    and summary_hash == reference["summary_sha256"]
                )
                assert warm == summary and warm_cache == "HIT"
                hashes.append((result_hash, summary_hash))
                evidence["runs"].append(
                    {
                        "index": index,
                        "kind": kind,
                        "request_id": request_id,
                        "run_id": run_id,
                        "workflow": spec.workflow,
                        "symbols": spec.symbols,
                        "attempts": status["attempt_count"],
                        "result_sha256": result_hash,
                        "summary_sha256": summary_hash,
                        "cache": [cache, warm_cache],
                        "seconds_since_pair_start": time.perf_counter() - started,
                        "inspection": status,
                    }
                )
                save(output, evidence)
                print(
                    json.dumps(
                        {
                            key: value
                            for key, value in evidence["runs"][-1].items()
                            if key not in {"inspection", "request_id", "run_id"}
                        }
                    ),
                    flush=True,
                )
            assert hashes[0] == hashes[1]
        assert execution_identity() == evidence["execution"], "Source changed during acceptance"
        for record in records:
            manifest = ROOT / record["manifest_path"]
            assert file_hash(manifest) == record["manifest_sha256"]
            assert (
                file_hash(manifest.parent / "trades.parquet")
                == json.loads(manifest.read_text(encoding="utf-8"))["artifact"]["sha256"]
            )
        evidence.update(
            status="passed", seconds=time.perf_counter() - began, source_hashes_unchanged=62
        )
    except BaseException as error:
        evidence.update(
            status="failed",
            error_type=type(error).__name__,
            error=str(error),
            seconds=time.perf_counter() - began,
        )
        raise
    finally:
        save(output, evidence)
        await research.close()
        await bars.close()
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-prefix", required=True)
    parser.add_argument("--durability-live", action="store_true")
    parser.add_argument("--interfaces-live", action="store_true")
    parser.add_argument("--retained-results", action="store_true")
    args = parser.parse_args()
    if args.durability_live:
        asyncio.run(durability_live(args.key_prefix))
    elif args.interfaces_live:
        interfaces_live(args.key_prefix)
    elif args.retained_results:
        asyncio.run(retained_results(args.key_prefix))
    else:
        asyncio.run(main(args.key_prefix))
