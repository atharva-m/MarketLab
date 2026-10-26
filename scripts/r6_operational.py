"""Owned R6 operational acceptance, isolated from retained public job records.

Uses existing Docker images/model weights, a generated schema and synthetic source
archives. No original service is restarted and no retained artifact is rewritten.
"""

import argparse
import asyncio
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import zipfile
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import sqlalchemy as sa
from r6_acceptance import BASE, DIGEST, MODEL, owned_settings, save

from marketlab.analytics.bars import BarService
from marketlab.copilot.model import Ollama
from marketlab.copilot.service import CopilotService
from marketlab.datasets.publication import ingest_archive
from marketlab.datasets.source import file_hash
from marketlab.inference import admission
from marketlab.inference_cli import work
from marketlab.memos import store
from marketlab.memos.model import MemoModel
from marketlab.memos.service import MemoService
from marketlab.research.service import ResearchService, execution_identity
from marketlab.research.spec import ResearchSpec


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def recorded_resource(kind: str) -> dict[str, Any]:
    recorded = json.loads((BASE / ("owned-" + kind + ".json")).read_text(encoding="utf-8-sig"))
    return recorded[0] if isinstance(recorded, list) else recorded


def cli(env: dict[str, str], module: str, *arguments: str, raw: bool = False) -> Any:
    result = subprocess.run(
        [sys.executable, "-m", module, *arguments],
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if result.returncode:
        raise AssertionError(f"Owned CLI failed: {module}: {result.stderr[:300]}")
    return result.stdout if raw else json.loads(result.stdout)


@contextmanager
def isolated(prefix: str, target: str = "head"):
    settings = owned_settings()
    schema = "r6_op_" + uuid4().hex
    root = (BASE / (prefix + "-storage")).resolve()
    root.mkdir(parents=True, exist_ok=False)
    admin = sa.create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
    with admin.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    url = settings.sqlalchemy_url.update_query_dict({"options": "-csearch_path=" + schema})
    env = {
        **os.environ,
        "MARKETLAB_DATABASE_URL": url.render_as_string(hide_password=False),
        "MARKETLAB_REDIS_URL": settings.redis_url.get_secret_value(),
        "MARKETLAB_OLLAMA_URL": settings.ollama_url,
        "MARKETLAB_STORAGE_PATH": str(root),
        "MARKETLAB_COPILOT_MODEL_DIGEST": DIGEST,
        "MARKETLAB_DATABASE_PASSWORD": url.password or "",
    }
    engine = sa.create_engine(url, connect_args=settings.database_connect_args)
    try:
        migrated = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", target],
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if migrated.returncode:
            raise AssertionError("Owned schema migration failed: " + migrated.stderr[-1000:])
        save(BASE / (prefix + "-schema.json"), {"schema": schema, "owner": prefix})
        yield settings, engine, root, env
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def migration(prefix: str) -> None:
    """Actual upgrade over copied R1-R5 records with real FK/check constraints."""
    output = BASE / (prefix + "-migration.json")
    evidence: dict[str, Any] = {
        "status": "running",
        "checks": {},
        "execution": execution_identity(),
    }
    began = time.perf_counter()
    try:
        with isolated(prefix, "0006_copilot") as (_, engine, _, env):
            snapshot = json.loads(
                Path("artifacts/r5/catalog-final.json").read_text(encoding="utf-8")
            )["tables"]
            metadata = sa.MetaData()
            metadata.reflect(bind=engine)
            with engine.begin() as connection:
                for name, records in snapshot.items():
                    table = metadata.tables[name]
                    for record in records:
                        row = dict(record)
                        for column in table.columns:
                            if row.get(column.name) is None:
                                continue
                            if isinstance(column.type, sa.DateTime):
                                row[column.name] = datetime.fromisoformat(row[column.name])
                            elif isinstance(column.type, sa.Date):
                                row[column.name] = date.fromisoformat(row[column.name])
                        connection.execute(table.insert().values(**row))
                connection.execute(
                    metadata.tables["trades"]
                    .insert()
                    .values(
                        trade_id="R6-migration-preserved",
                        symbol="R6MIG",
                        price="1.25000000",
                        quantity="2.50000000",
                        executed_at=datetime.fromisoformat("2025-01-01T00:00:00+00:00"),
                    )
                )

            def inventory() -> dict[str, Any]:
                inspector = sa.inspect(engine)
                result = {}
                with engine.connect() as connection:
                    for name in sorted(metadata.tables):
                        if name == "alembic_version":
                            continue
                        table = metadata.tables[name]
                        rows = [
                            dict(row) for row in connection.execute(sa.select(table)).mappings()
                        ]
                        rows.sort(key=lambda row: json.dumps(row, sort_keys=True, default=str))
                        result[name] = {
                            "rows": rows,
                            "columns": inspector.get_columns(name),
                            "primary_key": inspector.get_pk_constraint(name),
                            "foreign_keys": inspector.get_foreign_keys(name),
                            "unique": inspector.get_unique_constraints(name),
                            "checks": inspector.get_check_constraints(name),
                            "indexes": inspector.get_indexes(name),
                        }
                return json.loads(json.dumps(result, sort_keys=True, default=str))

            before = inventory()
            upgraded = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            assert upgraded.returncode == 0, "Populated R6 migration failed"
            after = inventory()
            assert after == before, "Retained table rows/definitions changed"
            assert set(sa.inspect(engine).get_table_names()) == set(metadata.tables) | {
                "memo_jobs",
                "memo_attempts",
                "memo_results",
            }
            run = snapshot["research_results"][0]
            no_result = next(
                row
                for row in snapshot["research_runs"]
                if row["run_id"] not in {value["run_id"] for value in snapshot["research_results"]}
            )
            with engine.begin() as connection:
                store.enqueue(
                    connection, run["run_id"], run["manifest_sha256"], run["summary_sha256"]
                )
            with engine.connect() as connection:
                base = dict(connection.execute(sa.select(store.jobs)).mappings().one())
            rejected: dict[str, str] = {}

            def reject(label: str, statement: Any) -> None:
                try:
                    with engine.begin() as connection:
                        connection.execute(statement)
                except sa.exc.IntegrityError as error:
                    rejected[label] = str(getattr(error.orig, "sqlstate", "unknown"))
                else:
                    raise AssertionError("Database accepted invalid constraint case: " + label)

            reject(
                "missing_research_run_fk",
                store.jobs.insert().values(**{**base, "run_id": str(uuid4())}),
            )
            reject(
                "existing_run_missing_result_fk",
                store.jobs.insert().values(**{**base, "run_id": no_result["run_id"]}),
            )
            for label, values in {
                "negative_attempt": {"attempt_count": -1},
                "fourth_attempt": {"attempt_count": 4},
                "negative_model_calls": {"model_calls": -1},
                "third_model_call": {"model_calls": 3},
                "negative_token": {"fencing_token": -1},
                "unknown_state": {"state": "unknown"},
                "queued_owner": {"owner": str(uuid4())},
                "queued_lease": {"lease_until": sa.func.clock_timestamp()},
                "running_no_owner_or_lease": {"state": "running"},
                "ready_without_result_hash": {"state": "ready"},
                "execution_hash_without_body": {"execution_sha256": "a" * 64},
            }.items():
                reject(
                    label,
                    store.jobs.update()
                    .where(store.jobs.c.run_id == run["run_id"])
                    .values(**values),
                )
            attempt = {
                "run_id": run["run_id"],
                "attempt_number": 1,
                "fencing_token": 1,
                "owner": str(uuid4()),
                "started_at": sa.func.clock_timestamp(),
                "outcome": "running",
            }
            reject(
                "attempt_missing_job_fk",
                store.attempts.insert().values(**{**attempt, "run_id": str(uuid4())}),
            )
            reject(
                "attempt_zero", store.attempts.insert().values(**{**attempt, "attempt_number": 0})
            )
            reject(
                "attempt_four", store.attempts.insert().values(**{**attempt, "attempt_number": 4})
            )
            reject(
                "running_attempt_with_end",
                store.attempts.insert().values(
                    **{**attempt, "ended_at": sa.func.clock_timestamp()}
                ),
            )
            reject(
                "memo_result_missing_job_fk",
                store.results.insert().values(
                    run_id=str(uuid4()),
                    manifest_path="unused",
                    manifest_sha256="a" * 64,
                    memo_sha256="b" * 64,
                    summary_sha256="c" * 64,
                    registered_at=sa.func.clock_timestamp(),
                ),
            )
            fk_inventory = {
                name: sa.inspect(engine).get_foreign_keys(name)
                for name in ("memo_jobs", "memo_attempts", "memo_results")
            }
            assert len(fk_inventory["memo_jobs"]) == 2
            evidence.update(
                status="passed",
                retained_rows={name: len(value["rows"]) for name, value in before.items()},
                exact_rows_and_definitions_preserved=True,
                constraint_rejections=rejected,
                foreign_keys=fk_inventory,
                historical_snapshot_sha256=file_hash(Path("artifacts/r5/catalog-final.json")),
            )
    except BaseException as error:
        evidence.update(status="failed", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        evidence["seconds"] = time.perf_counter() - began
        save(output, evidence)


def fixture(engine: sa.Engine, root: Path) -> ResearchSpec:
    source = root / "source"
    source.mkdir()
    archive = source / "BTCUSDT-trades-2025-01-01.zip"
    seed = int(uuid4().hex[:6], 16) + 100
    rows = [
        f"{i + 1},{seed + i},1,{seed + i},{1735689600000000 + i * 300000000},True,False"
        for i in range(24)
    ]
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("BTCUSDT-trades-2025-01-01.csv", "\n".join(rows) + "\n")
    checksum = source / "source.CHECKSUM"
    checksum.write_text(file_hash(archive) + "  " + archive.name, encoding="utf-8")
    published = ingest_archive(engine, root, archive, checksum)
    assert ingest_archive(engine, root, archive, checksum) == published
    return ResearchSpec.create(
        {
            "schema": "research-spec-v1",
            "workflow": "market_profile",
            "symbols": ["BTCUSDT"],
            "dataset_versions": [published["dataset_version_id"]],
            "start": "2025-01-01T01:00:00Z",
            "end": "2025-01-01T01:40:00Z",
            "history_start": "2025-01-01T00:00:00Z",
            "interval": "5m",
            "metrics": ["profile"],
            "parameters": {},
            "predicates": {},
        }
    )


async def successful(research: ResearchService, spec: ResearchSpec, key: str) -> str:
    run, _ = await research.submit(spec, key)
    assert await research.work(1, run) == 1
    assert research.inspect(run)["state"] == "succeeded"
    return run


def request(spec: ResearchSpec) -> dict[str, Any]:
    return {
        "schema": "copilot-request-v1",
        "text": "Study Bitcoin recently.",
        "dataset_versions": list(spec.dataset_versions),
        "context": {},
    }


@contextmanager
def api(env: dict[str, str], prefix: str):
    port = free_port()
    log_path = BASE / (prefix + "-api.log")
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
    save(BASE / (prefix + "-api-owned.json"), {"pid": process.pid, "port": port})
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}",
            timeout=240,
            trust_env=False,
            follow_redirects=False,
        ) as client:
            for _ in range(200):
                try:
                    if client.get("/health/live").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if process.poll() is not None:
                    raise AssertionError("Owned API exited before ready")
                time.sleep(0.1)
            else:
                raise AssertionError("Owned API startup timed out")
            yield client, port
    finally:
        if process.poll() is None:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
            else:
                process.terminate()
        process.wait(timeout=15)


async def interfaces(prefix: str) -> None:
    output = BASE / (prefix + "-interfaces.json")
    evidence: dict[str, Any] = {
        "status": "running",
        "execution": execution_identity(),
        "checks": {},
    }
    began = time.perf_counter()
    try:
        with isolated(prefix) as (settings, engine, root, env):
            spec = await asyncio.to_thread(fixture, engine, root)
            bars = BarService(engine, root, settings.redis_url.get_secret_value())
            research = ResearchService(bars)
            try:
                run = await successful(research, spec, prefix + "-numerical")
                summary, summary_hash = research.read(run, "summary")
                original = {
                    name: file_hash(root / "research" / run / name)
                    for name in ("manifest.json", "spec.json", "results.json", "summary.json")
                }
                with api(env, prefix) as (client, port):
                    path = f"/v1/research/runs/{run}/memo"
                    assert client.get("/health/ready").status_code == 200
                    assert (
                        path.replace(run, "{run_id}") in client.get("/openapi.json").json()["paths"]
                    )
                    assert client.get(path).json()["status"] == "pending"
                    assert client.post(path, json={}).status_code == 422
                    assert client.post("/v1/research/runs/" + "z" * 36 + "/memo").status_code == 422
                    assert client.post(path).status_code == 200
                    # Simulate the absence of a pre-R6 supplement only in this owned schema.
                    with engine.begin() as connection:
                        connection.execute(store.jobs.delete().where(store.jobs.c.run_id == run))
                    assert client.post(path).status_code == 201
                    assert client.post(path).status_code == 200
                    assert cli(env, "marketlab.memo_cli", "enqueue", "--run", run)["replayed"]
                    created = client.post(
                        "/v1/copilot/requests",
                        json=request(spec),
                        headers={"Idempotency-Key": prefix + "-copilot"},
                    )
                    assert created.status_code == 201
                    copilot_id = created.json()["request_id"]
                    assert (
                        cli(env, "marketlab.inference_cli", "worker", "--max-jobs", "1")[
                            "attempted_jobs"
                        ]
                        == 1
                    )
                    cp = client.get("/v1/copilot/requests/" + copilot_id).json()
                    assert cp["outcome"] == "needs_clarification", cp
                    assert client.get(path).json()["attempt_count"] == 0
                    assert (
                        cli(env, "marketlab.inference_cli", "worker", "--max-jobs", "1")[
                            "attempted_jobs"
                        ]
                        == 1
                    )
                    ready = client.get(path).json()
                    assert ready["status"] == "ready", ready
                    content = ready["content"]
                    assert len(content.strip().split("\n\n")) == 3
                    assert hashlib.sha256(content.encode()).hexdigest() == ready["memo_sha256"]
                    assert (
                        cli(env, "marketlab.memo_cli", "inspect", "--run", run)["content"]
                        == content
                    )
                    read = cli(env, "marketlab.memo_cli", "read", "--run", run)
                    assert read["content"] == content
                    assert (
                        cli(env, "marketlab.memo_cli", "read", "--run", run, "--markdown", raw=True)
                        == content
                    )
                    assert client.post(path).json()["replayed"]
                    assert client.get(f"/v1/research/runs/{run}/summary").json() == summary
                    evidence["checks"]["memo_tcp_cli_priority_replay"] = {
                        "run_id": run,
                        "request_id": copilot_id,
                        "memo_sha256": ready["memo_sha256"],
                        "summary_sha256": summary_hash,
                        "content": content,
                    }
                    token = "R6" + uuid4().hex[:10]
                    trade = {
                        "trade_id": token + "A",
                        "symbol": token.upper(),
                        "price": "1.25",
                        "quantity": "2.5",
                        "executed_at": "2025-01-03T01:00:00Z",
                    }
                    lower = {**trade, "trade_id": token + "a"}
                    assert (
                        client.post("/trades/import/json", json=[trade, lower]).json()["imported"]
                        == 2
                    )
                    assert (
                        client.post(
                            "/trades/import/json",
                            content="[]",
                            headers={"Content-Type": "text/plain"},
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
                    rolled = {**trade, "trade_id": token + "B"}
                    assert (
                        client.post("/trades/import/json", json=[rolled, trade]).status_code == 409
                    )
                    assert client.get("/trades/" + rolled["trade_id"]).status_code == 404
                    rows = client.get(
                        "/trades",
                        params={
                            "symbol": trade["symbol"],
                            "after_id": token + "Z",
                            "executed_from": trade["executed_at"],
                            "executed_before": "2025-01-03T01:05:00Z",
                            "limit": 1,
                        },
                    ).json()["items"]
                    assert [row["trade_id"] for row in rows] == [lower["trade_id"]]
                    assert (
                        cli(
                            env,
                            "marketlab.trade_cli",
                            "--port",
                            str(port),
                            "--trade-id",
                            trade["trade_id"],
                        )
                        == client.get("/trades/" + trade["trade_id"]).json()
                    )
                    evidence["checks"]["legacy_http_transaction_filters_cli"] = "passed"
                    params = {
                        "version": spec.dataset_versions[0],
                        "symbol": "BTCUSDT",
                        "interval": "5m",
                        "start": "2025-01-01T01:00:00Z",
                        "end": "2025-01-01T01:40:00Z",
                    }
                    first = client.get("/v1/bars", params=params)
                    second = client.get("/v1/bars", params=params)
                    assert first.status_code == second.status_code == 200
                    assert first.json() == second.json() and second.headers["x-cache"] == "HIT"
                    assert len(second.json()["bars"]) == 8
                    evidence["checks"]["bars_cache"] = [
                        first.headers["x-cache"],
                        second.headers["x-cache"],
                    ]
                    summary_path = f"/v1/research/runs/{run}/summary"
                    assert client.get(summary_path).json() == summary
                    assert client.get(summary_path).headers["x-cache"] == "HIT"
                    recorded = recorded_resource("redis")
                    actual = json.loads(
                        await asyncio.to_thread(
                            subprocess.check_output, ["docker", "inspect", recorded["Id"]]
                        )
                    )[0]
                    assert actual["Id"] == recorded["Id"]
                    assert actual["Config"]["Labels"]["marketlab.r6.owner"] == "r6-20261025"
                    try:
                        await asyncio.to_thread(
                            subprocess.run,
                            ["docker", "stop", "--time", "2", actual["Id"]],
                            check=True,
                            capture_output=True,
                            timeout=20,
                        )
                        outage_bars = client.get("/v1/bars", params=params)
                        outage_summary = client.get(summary_path)
                        assert outage_bars.status_code == outage_summary.status_code == 200
                        assert outage_bars.json() == second.json()
                        assert outage_summary.json() == summary
                        assert outage_bars.headers["x-cache"] == "BYPASS"
                        assert outage_summary.headers["x-cache"] == "BYPASS"
                        evidence["checks"]["actual_owned_redis_outage"] = {
                            "container_id": actual["Id"],
                            "bars": outage_bars.headers["x-cache"],
                            "summary": outage_summary.headers["x-cache"],
                            "numerical_bodies_unchanged": True,
                        }
                    finally:
                        await asyncio.to_thread(
                            subprocess.run,
                            ["docker", "start", actual["Id"]],
                            check=True,
                            capture_output=True,
                            timeout=20,
                        )
                    for _ in range(100):
                        recovery = await asyncio.to_thread(
                            subprocess.run,
                            ["docker", "exec", actual["Id"], "redis-cli", "ping"],
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )
                        if recovery.returncode == 0 and "PONG" in recovery.stdout:
                            break
                        await asyncio.sleep(0.1)
                    else:
                        raise AssertionError("Owned Redis did not recover")
                    assert client.get("/v1/bars", params=params).json() == second.json()
                    assert client.get(summary_path).json() == summary
                    evidence["checks"]["owned_redis_recovered"] = "PONG; responses unchanged"
                    assert (
                        cli(
                            env,
                            "marketlab.dataset_cli",
                            "inspect",
                            "--version",
                            spec.dataset_versions[0],
                        )["dataset_version_id"]
                        == spec.dataset_versions[0]
                    )
                    metrics = client.get("/metrics")
                    assert metrics.status_code == 200 and "marketlab_memo" in metrics.text
                    evidence["checks"]["ingestion_sync_repeat_readback_metrics"] = "passed"
                unavailable = MemoService(
                    research, MemoModel("http://127.0.0.1:" + str(free_port()), MODEL, DIGEST)
                )
                other = await successful(research, spec, prefix + "-unavailable")
                assert await unavailable.work(1, other) == 1
                assert unavailable.inspect(other)["state"] == "retry_wait"
                assert research.read(other, "summary")[0] == summary
                assert unavailable.read(run)[0] == content
                assert all(
                    file_hash(root / "research" / run / name) == sha
                    for name, sha in original.items()
                )
                evidence["checks"]["model_outage_numerical_and_ready_memo_independence"] = "passed"
                evidence["checks"]["numerical_files_unchanged"] = original
            finally:
                await research.close()
                await bars.close()
        assert execution_identity() == evidence["execution"], (
            "Source changed during live interfaces"
        )
        evidence["status"] = "passed"
    except BaseException as error:
        evidence.update(status="failed", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        evidence["seconds"] = time.perf_counter() - began
        save(output, evidence)


class ObservedMemo(MemoModel):
    def __init__(
        self, url: str, started: asyncio.Event | None = None, permit: asyncio.Event | None = None
    ):
        super().__init__(url, MODEL, DIGEST)
        self.started, self.permit = started, permit
        self.calls = 0
        self.dispatch = asyncio.Event()
        self.chat_timeout: float | None = None

    async def bounded(
        self, client: httpx.AsyncClient, method: str, path: str, **kwargs: Any
    ) -> Any:
        if method == "POST" and path == "/api/chat":
            self.dispatch.set()
            if self.chat_timeout is not None:
                async with asyncio.timeout(self.chat_timeout):
                    return await super().bounded(client, method, path, **kwargs)
        return await super().bounded(client, method, path, **kwargs)

    async def generate(self, source: dict[str, Any], pinned: str):
        self.calls += 1
        if self.started is not None:
            self.started.set()
        if self.permit is not None:
            await self.permit.wait()
        return await super().generate(source, pinned)


async def lifecycle(prefix: str) -> None:
    output = BASE / (prefix + "-lifecycle.json")
    evidence: dict[str, Any] = {
        "status": "running",
        "execution": execution_identity(),
        "checks": {},
        "guarantee": (
            "Serialized cooperating application requests; upstream generation after "
            "client cancellation is not universally guaranteed stopped"
        ),
    }
    began = time.perf_counter()
    try:
        with isolated(prefix) as (settings, engine, root, _):
            spec = await asyncio.to_thread(fixture, engine, root)
            bars = BarService(engine, root, settings.redis_url.get_secret_value())
            research = ResearchService(bars)
            copilot = CopilotService(research, Ollama(settings.ollama_url, MODEL, DIGEST))
            active = None
            task = None
            try:
                run = await successful(research, spec, prefix + "-active")
                started, permit = asyncio.Event(), asyncio.Event()
                observed = ObservedMemo(settings.ollama_url, started, permit)
                memo = MemoService(research, observed)
                active = asyncio.create_task(work(copilot, memo, 1))
                await asyncio.wait_for(started.wait(), 15)
                copilot_id, _, _ = await copilot.create(request(spec), prefix + "-priority")
                pending_before = copilot.inspect(copilot_id)
                another = MemoService(research, MemoModel(settings.ollama_url, MODEL, DIGEST))
                assert await work(copilot, another, 1) == 0
                pending_after = copilot.inspect(copilot_id)
                assert pending_after["revisions"][0]["attempt_count"] == 0
                assert pending_after["revisions"][0]["model_calls"] == 0
                assert memo.inspect(run)["state"] == "running"
                permit.set()
                assert await active == 1
                assert memo.inspect(run)["state"] == "ready"
                assert await work(copilot, another, 1) == 1
                assert copilot.inspect(copilot_id)["outcome"] == "needs_clarification"
                evidence["checks"]["active_memo_nonpreemption_concurrent_capacity"] = {
                    "memo_run": run,
                    "copilot_id": copilot_id,
                    "memo_model_calls": observed.calls,
                    "pending_before": pending_before["revisions"][0]["state"],
                    "waiting_attempts": 0,
                    "waiting_calls": 0,
                    "method": (
                        "Controlled pause immediately before actual MemoModel.generate "
                        "dispatch; real Ollama completed both jobs"
                    ),
                }
                cancelled_run = await successful(research, spec, prefix + "-cancelled")
                cancelling = ObservedMemo(settings.ollama_url)
                cancel_service = MemoService(research, cancelling)
                task = asyncio.create_task(cancel_service.work(1, cancelled_run))
                await asyncio.wait_for(cancelling.dispatch.wait(), 15)
                await asyncio.sleep(0.05)
                task.cancel()
                result = await asyncio.gather(task, return_exceptions=True)
                assert isinstance(result[0], asyncio.CancelledError)
                cancelled = cancel_service.inspect(cancelled_run)
                assert cancelled["state"] == "running" and cancelled["model_calls"] == 1
                async with admission(engine) as acquired:
                    assert acquired
                await asyncio.sleep(2)
                evidence["checks"]["actual_client_cancellation"] = {
                    "run_id": cancelled_run,
                    "dispatch_entered": True,
                    "local_task_cancelled": True,
                    "admission_released": True,
                    "job_state": cancelled["state"],
                    "model_calls": cancelled["model_calls"],
                    "server_generation_stopped": "not established by client cancellation",
                }
                timeout_run = await successful(research, spec, prefix + "-timeout")
                timing = ObservedMemo(settings.ollama_url)
                timing.chat_timeout = 0.05
                timeout_service = MemoService(research, timing)
                assert await timeout_service.work(1, timeout_run) == 1
                timed = timeout_service.inspect(timeout_run)
                assert timing.dispatch.is_set(), (
                    "Short timeout happened before actual chat dispatch"
                )
                assert timed["state"] == "retry_wait" and timed["model_calls"] == 1, timed
                async with admission(engine) as acquired:
                    assert acquired
                await asyncio.sleep(2)
                evidence["checks"]["actual_shortened_inference_timeout"] = {
                    "run_id": timeout_run,
                    "test_timeout_seconds": timing.chat_timeout,
                    "injection_point": "Actual POST /api/chat HTTP operation after identity checks",
                    "production_timeout_seconds": 120,
                    "state": timed["state"],
                    "dispatch_entered": True,
                    "admission_released": True,
                    "server_generation_stopped": "not established by client timeout",
                }
                log = BASE / "ollama-stderr.log"
                tail = log.read_text(encoding="utf-8", errors="replace")[-14000:]
                save(
                    BASE / (prefix + "-ollama-observations.json"),
                    {
                        "tail": tail,
                        "interpretation": (
                            "Raw owned-server observations; no universal token-generation "
                            "cancellation or no-overlap claim"
                        ),
                    },
                )
            finally:
                outstanding = [operation for operation in (active, task) if operation is not None]
                for operation in outstanding:
                    if not operation.done():
                        operation.cancel()
                await asyncio.gather(*outstanding, return_exceptions=True)
                await research.close()
                await bars.close()
        assert execution_identity() == evidence["execution"], (
            "Source changed during lifecycle acceptance"
        )
        evidence["status"] = "passed"
    except BaseException as error:
        evidence.update(status="failed", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        evidence["seconds"] = time.perf_counter() - began
        save(output, evidence)


async def packaged(prefix: str) -> None:
    """Overlay smoke with unchanged installed dependencies; not a clean image build."""
    output = BASE / (prefix + "-packaged.json")
    evidence: dict[str, Any] = {
        "status": "running",
        "execution": execution_identity(),
        "build_kind": (
            "Current src/migrations over existing marketlab:local locked image; no pulls or network"
        ),
    }
    image_name = "marketlab:" + prefix
    container_id = None
    image_id = None
    began = time.perf_counter()
    try:
        with isolated(prefix) as (settings, engine, root, env):
            spec = await asyncio.to_thread(fixture, engine, root)
            bars = BarService(engine, root, settings.redis_url.get_secret_value())
            research = ResearchService(bars)
            memo = MemoService(research, MemoModel(settings.ollama_url, MODEL, DIGEST))
            try:
                run = await successful(research, spec, prefix + "-numerical")
                assert await memo.work(1, run) == 1
                content, _ = memo.read(run)
                summary, _ = research.read(run, "summary")
                results, _ = research.read(run, "results")
                dockerfile = BASE / (prefix + ".Dockerfile")
                dockerfile.write_text(
                    "FROM marketlab:local\nUSER root\nWORKDIR /app\n"
                    "COPY src ./src\nCOPY migrations ./migrations\nUSER marketlab\n",
                    encoding="utf-8",
                )
                with (BASE / (prefix + "-image-build.log")).open("w", encoding="utf-8") as log:
                    build = await asyncio.to_thread(
                        subprocess.run,
                        [
                            "docker",
                            "build",
                            "--network=none",
                            "--pull=false",
                            "--label",
                            "marketlab.r6.owner=" + prefix,
                            "-f",
                            str(dockerfile),
                            "-t",
                            image_name,
                            ".",
                        ],
                        stdout=log,
                        stderr=log,
                        timeout=180,
                    )
                assert build.returncode == 0, "Owned overlay image build failed"
                image = json.loads(
                    await asyncio.to_thread(
                        subprocess.check_output, ["docker", "image", "inspect", image_name]
                    )
                )[0]
                image_id = image["Id"]
                assert image["Config"]["Labels"]["marketlab.r6.owner"] == prefix
                pg = recorded_resource("postgres")
                redis = recorded_resource("redis")
                actual_pg = json.loads(
                    await asyncio.to_thread(
                        subprocess.check_output, ["docker", "inspect", pg["Id"]]
                    )
                )[0]
                actual_redis = json.loads(
                    await asyncio.to_thread(
                        subprocess.check_output, ["docker", "inspect", redis["Id"]]
                    )
                )[0]
                for actual in (actual_pg, actual_redis):
                    assert actual["Config"]["Labels"]["marketlab.r6.owner"] == "r6-20261025"
                pg_networks = actual_pg["NetworkSettings"]["Networks"]
                redis_networks = actual_redis["NetworkSettings"]["Networks"]
                common_networks = sorted(set(pg_networks) & set(redis_networks))
                assert common_networks, "Owned PostgreSQL/Redis share no network"
                network = common_networks[0]
                pg_ip = pg_networks[network]["IPAddress"]
                redis_ip = redis_networks[network]["IPAddress"]
                url = sa.engine.make_url(env["MARKETLAB_DATABASE_URL"]).set(host=pg_ip, port=5432)
                port = free_port()
                args = [
                    "docker",
                    "run",
                    "--pull=never",
                    "-d",
                    "--name",
                    prefix,
                    "--network",
                    network,
                    "--label",
                    "marketlab.r6.owner=" + prefix,
                    "-p",
                    f"127.0.0.1:{port}:8000",
                    "--mount",
                    f"type=bind,source={root},target=/data/marketlab,readonly",
                    "-e",
                    "MARKETLAB_DATABASE_URL=" + url.render_as_string(hide_password=False),
                    "-e",
                    "MARKETLAB_REDIS_URL=redis://" + redis_ip + ":6379/0",
                    "-e",
                    "MARKETLAB_OLLAMA_URL=http://127.0.0.1:1",
                    image_id,
                ]
                container_id = (
                    await asyncio.to_thread(subprocess.check_output, args, text=True)
                ).strip()
                actual = json.loads(
                    await asyncio.to_thread(
                        subprocess.check_output, ["docker", "inspect", container_id]
                    )
                )[0]
                assert actual["Config"]["Labels"]["marketlab.r6.owner"] == prefix
                evidence["owned"] = {
                    "container_id": container_id,
                    "image_id": image_id,
                    "port": port,
                    "network": network,
                }
                save(output, evidence)
                with httpx.Client(
                    base_url=f"http://127.0.0.1:{port}", timeout=15, trust_env=False
                ) as client:
                    for _ in range(150):
                        try:
                            if (
                                await asyncio.to_thread(client.get, "/health/live")
                            ).status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        await asyncio.sleep(0.1)
                    else:
                        raise AssertionError("Owned packaged API startup failed")
                    assert (
                        await asyncio.to_thread(client.get, f"/v1/research/runs/{run}/results")
                    ).json() == results
                    assert (
                        await asyncio.to_thread(client.get, f"/v1/research/runs/{run}/summary")
                    ).json() == summary
                    ready = await asyncio.to_thread(client.get, f"/v1/research/runs/{run}/memo")
                    assert ready.status_code == 200 and ready.json()["content"] == content
                check = await asyncio.to_thread(
                    subprocess.run,
                    [
                        "docker",
                        "exec",
                        container_id,
                        "python",
                        "-c",
                        (
                            "import hashlib,pathlib,json; print(json.dumps({'lock':"
                            "hashlib.sha256(pathlib.Path('/app/uv.lock').read_bytes()).hexdigest(),"
                            "'git':pathlib.Path('/app/.git').exists()}))"
                        ),
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=15,
                )
                metadata = json.loads(check.stdout)
                assert metadata["lock"] == file_hash(Path("uv.lock")) and not metadata["git"]
                evidence["checks"] = {
                    "startup_without_checkout": True,
                    "ollama_unavailable": True,
                    "numerical_and_memo_readback_equal": True,
                    "lock_identity": metadata["lock"],
                }
            finally:
                if container_id is not None:
                    actual = json.loads(
                        await asyncio.to_thread(
                            subprocess.check_output, ["docker", "inspect", container_id]
                        )
                    )[0]
                    assert actual["Config"]["Labels"]["marketlab.r6.owner"] == prefix
                    await asyncio.to_thread(
                        subprocess.run,
                        ["docker", "rm", "-f", container_id],
                        check=True,
                        capture_output=True,
                    )
                    evidence["owned_container_removed"] = True
                    container_id = None
                await research.close()
                await bars.close()
        assert execution_identity() == evidence["execution"], "Source changed during packaged smoke"
        evidence["status"] = "passed"
    except BaseException as error:
        evidence.update(status="failed", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        if image_id is not None:
            image = json.loads(
                await asyncio.to_thread(
                    subprocess.check_output, ["docker", "image", "inspect", image_id]
                )
            )[0]
            assert image["Config"]["Labels"]["marketlab.r6.owner"] == prefix
            await asyncio.to_thread(
                subprocess.run, ["docker", "image", "rm", image_id], check=True, capture_output=True
            )
            evidence["owned_image_removed"] = True
        evidence["seconds"] = time.perf_counter() - began
        save(output, evidence)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True)
    parser.add_argument(
        "--phase", choices=("interfaces", "lifecycle", "packaged", "migration"), required=True
    )
    args = parser.parse_args()
    if not args.prefix.startswith("r6-op-") or any(
        c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in args.prefix
    ):
        parser.error("prefix must be an r6-op- lowercase owned identity")
    if args.phase == "migration":
        migration(args.prefix)
    else:
        phases = {"interfaces": interfaces, "lifecycle": lifecycle, "packaged": packaged}
        asyncio.run(phases[args.phase](args.prefix))
