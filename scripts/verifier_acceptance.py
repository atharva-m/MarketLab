"""Owned acceptance for bounded cold verification, without cache warm-up work.

``cold`` starts a fresh BarService, empty process verification cache and empty
owned Redis, then submits/executes/reads one normal all-62 cross-asset workflow.
This is application-cold evidence; it does not flush operating-system caches.
``linux-smoke`` builds a no-network overlay over the existing locked local image
and checks spawned verification, exact bars and cleanup in a Linux container.
"""

import argparse
import asyncio
import hashlib
import json
import multiprocessing
import os
import platform
import subprocess
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import redis
import sqlalchemy as sa
from pydantic import SecretStr

from marketlab.analytics.bars import BarService, BarsRequest
from marketlab.analytics.cache import canonical
from marketlab.config import Settings
from marketlab.datasets.publication import dataset_versions
from marketlab.datasets.source import file_hash
from marketlab.memos import store as memo_store
from marketlab.research import store as research_store
from marketlab.research.service import ResearchService, execution_identity
from marketlab.research.spec import ResearchSpec

BASE = Path("artifacts/verifier-opt")
ROOT = Path("artifacts/r2/historical-storage").resolve()
OWNER = "verifier-opt-20261025"
LIMIT_SECONDS = 1800.0


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)


def recorded_resource(kind: str) -> dict[str, Any]:
    value = json.loads((BASE / ("owned-" + kind + ".json")).read_text(encoding="utf-8-sig"))
    return value[0] if isinstance(value, list) else value


def owned_settings() -> tuple[Settings, dict[str, Any]]:
    private = json.loads((BASE / "connection-private.json").read_text(encoding="utf-8-sig"))
    assert private["owner"] == OWNER
    settings = Settings(
        database_url=SecretStr(private["database_url"]),
        database_password=None,
        redis_url=SecretStr(private["redis_url"]),
        storage_path=ROOT,
        ollama_url="http://127.0.0.1:1",
    )
    url = settings.sqlalchemy_url
    assert (url.host, url.port, url.database) == ("127.0.0.1", 55440, "marketlab")
    assert settings.redis_url.get_secret_value() == "redis://127.0.0.1:56382/0"
    resources: dict[str, Any] = {}
    for kind, container_port, host_port in (
        ("postgres", "5432/tcp", "55440"),
        ("redis", "6379/tcp", "56382"),
    ):
        recorded = recorded_resource(kind)
        actual = json.loads(
            subprocess.check_output(["docker", "inspect", recorded["Id"]], timeout=10)
        )[0]
        assert actual["Id"] == recorded["Id"] and actual["Name"] == recorded["Name"]
        assert actual["Config"]["Labels"]["marketlab.verifier.owner"] == OWNER
        assert actual["State"]["Running"]
        assert actual["NetworkSettings"]["Ports"][container_port] == [
            {"HostIp": "127.0.0.1", "HostPort": host_port}
        ]
        resources[kind] = {"id": actual["Id"], "name": actual["Name"], "image": actual["Image"]}
    return settings, resources


def environment(settings: Settings) -> dict[str, str]:
    return {
        **os.environ,
        "MARKETLAB_DATABASE_URL": settings.sqlalchemy_url.render_as_string(hide_password=False),
        "MARKETLAB_DATABASE_PASSWORD": settings.sqlalchemy_url.password or "",
        "MARKETLAB_REDIS_URL": settings.redis_url.get_secret_value(),
        "MARKETLAB_STORAGE_PATH": str(settings.storage_path),
        "MARKETLAB_OLLAMA_URL": settings.ollama_url,
    }


def migrate(settings: Settings) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=environment(settings),
        capture_output=True,
        text=True,
        timeout=90,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert result.returncode == 0, "Owned verifier database migration failed"


def restore_catalog(engine: sa.Engine) -> list[dict[str, Any]]:
    """Register pinned manifests; leave Parquet content verification to timed work."""
    records = json.loads(Path("artifacts/r2/catalog-final.json").read_text(encoding="utf-8"))[
        "catalog"
    ]
    assert len(records) == 62 and sum(row["row_count"] for row in records) == 230311900
    for row in records:
        path = ROOT / row["manifest_path"]
        assert path.resolve().is_relative_to(ROOT) and not path.is_symlink()
        assert file_hash(path) == row["manifest_sha256"]
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["quality"]["accepted_rows"] == row["row_count"]
        assert manifest["dataset_version_id"] == row["dataset_version_id"]
    with engine.begin() as connection:
        for row in records:
            existing = (
                connection.execute(
                    sa.select(dataset_versions).where(
                        dataset_versions.c.dataset_version_id == row["dataset_version_id"]
                    )
                )
                .mappings()
                .one_or_none()
            )
            values = dict(row)
            values["trade_date"] = date.fromisoformat(values["trade_date"])
            values["published_at"] = datetime.fromisoformat(values["published_at"])
            if existing is None:
                connection.execute(dataset_versions.insert().values(**values))
            else:
                assert dict(existing) == values
    return records


def verifier_snapshot(bars: BarService) -> dict[str, Any]:
    """Reject missing, serial or unbounded verifier/compute diagnostics."""
    snapshot = bars.reader.verifier.snapshot()
    assert snapshot["configured_max_workers"] == 2
    assert snapshot["start_method"] == "spawn"
    assert 0 <= snapshot["active_submitted"] <= 2
    assert 0 <= snapshot["peak_submitted"] <= 2
    assert len(snapshot["worker_pids"]) <= 2
    assert all(pid > 0 and pid != os.getpid() for pid in snapshot["worker_pids"])
    assert len(snapshot["completed_records"]) <= 128
    compute = snapshot["compute"]
    assert compute["limit"] == 2
    assert 0 <= compute["active"] <= 2 and 0 <= compute["peak"] <= 2
    assert sum(compute["active_by_kind"].values()) == compute["active"]
    assert not snapshot["broken"]
    return snapshot


def expected_verifications(
    records: list[dict[str, Any]], root: Path = ROOT
) -> dict[str, dict[str, Any]]:
    result = {}
    for row in records:
        manifest = json.loads((root / row["manifest_path"]).read_text(encoding="utf-8"))
        result[row["dataset_version_id"]] = {
            "row_count": row["row_count"],
            "manifest_sha256": row["manifest_sha256"],
            "logical_sha256": manifest["quality"]["logical_sha256"],
            "parquet_sha256": manifest["quality"]["parquet_sha256"],
        }
    return result


def verify_completed(snapshot: dict[str, Any], expected: dict[str, dict[str, Any]]) -> None:
    """Do not substitute counters for actual per-version verification evidence."""
    records = snapshot["completed_records"]
    assert len(records) == len(expected)
    assert {record["version"] for record in records} == set(expected)
    assert sum(record["row_count"] for record in records) == sum(
        record["row_count"] for record in expected.values()
    )
    for record in records:
        pinned = expected[record["version"]]
        assert all(
            record[key] == pinned[key]
            for key in ("row_count", "manifest_sha256", "logical_sha256", "parquet_sha256")
        )
        assert record["pid"] > 0 and record["pid"] != os.getpid()
        assert record["wall_seconds"] >= 0
        assert record["cpu_seconds"] >= 0
        assert record["arrow_cpu_threads"] == record["arrow_io_threads"] == 1
        assert record["pid"] in snapshot["worker_pids"]
    assert snapshot["submitted"] == snapshot["completed"] == len(expected)
    assert snapshot["failed"] == snapshot["cancelled"] == 0
    assert snapshot["peak_submitted"] >= 1 and snapshot["compute"]["peak"] >= 1


async def close_services(
    research: ResearchService | None,
    bars: BarService | None,
    engine: sa.Engine,
    evidence: dict[str, Any],
) -> None:
    """Attempt every cleanup and retain diagnostic failures before propagating."""
    errors: list[BaseException] = []
    for name, service in (("research", research), ("bars", bars)):
        if service is not None:
            try:
                await service.close()
            except BaseException as error:
                errors.append(error)
                evidence.setdefault("cleanup_errors", []).append(
                    {"phase": name, "type": type(error).__name__, "error": str(error)}
                )
    try:
        await asyncio.to_thread(engine.dispose)
    except BaseException as error:
        errors.append(error)
        evidence.setdefault("cleanup_errors", []).append(
            {"phase": "engine", "type": type(error).__name__, "error": str(error)}
        )
    if bars is not None:
        try:
            evidence["verifier_after_close"] = verifier_snapshot(bars)
        except BaseException as error:
            errors.append(error)
            evidence.setdefault("cleanup_errors", []).append(
                {"phase": "diagnostics", "type": type(error).__name__, "error": str(error)}
            )
    evidence["active_children_after_close"] = [
        child.pid for child in multiprocessing.active_children()
    ]
    if errors:
        raise RuntimeError("Acceptance cleanup or diagnostics failed") from errors[0]


class TimedResearch(ResearchService):
    def __init__(self, bars: BarService, phases: dict[str, float]):
        super().__init__(bars)
        self.phases = phases

    async def prepare(self, spec: ResearchSpec) -> dict[str, Any]:
        began = time.perf_counter()
        try:
            return await super().prepare(spec)
        finally:
            self.phases["prepare_seconds"] = time.perf_counter() - began

    async def execute(self, current: research_store.Claim) -> None:
        began = time.perf_counter()
        try:
            await super().execute(current)
        finally:
            self.phases["execute_seconds"] = time.perf_counter() - began


async def tracked(operation: Any, evidence: dict[str, Any], output: Path, phase: str) -> Any:
    task = asyncio.create_task(operation)
    began = time.perf_counter()
    try:
        while not task.done():
            save(
                output.with_suffix(".progress.json"),
                {
                    "phase": phase,
                    "phase_seconds": time.perf_counter() - began,
                    "pid": os.getpid(),
                    "source": evidence["execution"],
                },
            )
            await asyncio.wait({task}, timeout=30)
        return await task
    except BaseException:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise


async def cold(prefix: str) -> None:
    settings, resources = await asyncio.to_thread(owned_settings)
    engine = sa.create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
    output = BASE / (prefix + "-cold.json")
    evidence: dict[str, Any] = {
        "status": "running",
        "execution": execution_identity(),
        "resources": resources,
        "pid": os.getpid(),
        "hardware": platform.platform(),
        "peak_memory": "unmeasured",
        "memory_scope": {
            "parent_or_simultaneous_aggregate_peak": "unmeasured",
            "worker_records": (
                "Per-worker lifetime high-water RSS when supported; peaks are not summed"
            ),
        },
        "cold_definition": (
            "Fresh application process/service/verifier cache and empty owned Redis; "
            "OS cache not flushed"
        ),
        "prior_workflows_in_process": 0,
        "phases": {},
        "production_attempt_limit_seconds": LIMIT_SECONDS,
    }
    bars = None
    research = None
    workflow_began = None
    workflow_cpu_began = None
    try:
        await asyncio.to_thread(migrate, settings)
        records = await asyncio.to_thread(restore_catalog, engine)
        evidence["catalog"] = {
            "partitions": len(records),
            "rows": sum(row["row_count"] for row in records),
        }
        reference_path = Path("artifacts/r4/reference-workflows.json")
        references = json.loads(await asyncio.to_thread(reference_path.read_text, encoding="utf-8"))
        reference = next(row for row in references if row["spec"]["workflow"] == "cross_asset")
        evidence["reference_sha256"] = file_hash(reference_path)
        evidence["expected_verifications"] = await asyncio.to_thread(
            expected_verifications, records
        )
        spec = ResearchSpec.create(reference["spec"])
        assert len(spec.dataset_versions) == 62
        assert set(spec.dataset_versions) == {row["dataset_version_id"] for row in records}
        cache = redis.Redis.from_url(settings.redis_url.get_secret_value(), socket_timeout=2)
        try:
            evidence["redis_keys_before_owned_reset"] = await asyncio.to_thread(cache.dbsize)
            await asyncio.to_thread(cache.flushdb)
            assert await asyncio.to_thread(cache.dbsize) == 0
        finally:
            await asyncio.to_thread(cache.close)
        workflow_began = time.perf_counter()
        workflow_cpu_began = time.process_time()
        bars = BarService(engine, ROOT, settings.redis_url.get_secret_value())
        research = TimedResearch(bars, evidence["phases"])
        assert research.attempt_timeout == LIMIT_SECONDS
        assert len(bars.reader.verified) == 0 and not bars.flights
        evidence["initial_verifier"] = verifier_snapshot(bars)
        assert evidence["initial_verifier"]["submitted"] == 0
        assert evidence["initial_verifier"]["completed"] == 0
        assert not evidence["initial_verifier"]["worker_pids"]
        assert not multiprocessing.active_children()
        evidence["initial_verified_versions"] = len(bars.reader.verified)
        save(output, evidence)
        async with asyncio.timeout(LIMIT_SECONDS):
            submitted_at = time.perf_counter()
            run, replayed = await tracked(
                research.submit(spec, prefix + "-cold-cross-asset"),
                evidence,
                output,
                "prepare_and_submit",
            )
            assert not replayed
            evidence["phases"]["prepare_and_submit_seconds"] = time.perf_counter() - submitted_at
            evidence["run_id"] = run
            evidence["after_prepare_verifier"] = verifier_snapshot(bars)
            assert await tracked(research.work(1, run), evidence, output, "execute") == 1
            readback_began = time.perf_counter()
            info = await asyncio.to_thread(research.inspect, run)
            assert info["state"] == "succeeded", info["error"]
            result, result_hash = await asyncio.to_thread(research.read, run, "results")
            summary, summary_hash = await asyncio.to_thread(research.read, run, "summary")
            assert result == reference["results"] and summary == reference["summary"]
            assert result_hash == reference["results_sha256"]
            assert summary_hash == reference["summary_sha256"]
            memo = await asyncio.to_thread(memo_store.inspect, engine, run)
            assert memo["state"] == "queued" and memo["attempt_count"] == memo["model_calls"] == 0
            evidence["phases"]["readback_seconds"] = time.perf_counter() - readback_began
            evidence["results_sha256"] = result_hash
            evidence["summary_sha256"] = summary_hash
            evidence["numerical_attempts"] = info["attempt_count"]
            evidence["memo"] = {
                "state": memo["state"],
                "attempts": memo["attempt_count"],
                "model_calls": memo["model_calls"],
            }
            evidence["verified_versions"] = len(bars.reader.verified)
            evidence["final_verifier_before_close"] = verifier_snapshot(bars)
            assert evidence["verified_versions"] == 62
            verify_completed(
                evidence["final_verifier_before_close"], evidence["expected_verifications"]
            )
            assert evidence["final_verifier_before_close"]["peak_submitted"] == 2
            assert len(evidence["final_verifier_before_close"]["worker_pids"]) == 2
            assert (
                len(
                    {
                        record["pid"]
                        for record in evidence["final_verifier_before_close"]["completed_records"]
                    }
                )
                == 2
            )
        evidence["status"] = "numerical_pass_cleanup_pending"
    except BaseException as error:
        evidence.update(status="failed", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        cleanup_began = time.perf_counter()
        try:
            await close_services(research, bars, engine, evidence)
            if workflow_began is not None:
                evidence["whole_workflow_seconds"] = time.perf_counter() - workflow_began
            if workflow_cpu_began is not None:
                evidence["parent_process_cpu_seconds"] = time.process_time() - workflow_cpu_began
            if evidence["status"] == "numerical_pass_cleanup_pending":
                assert evidence["whole_workflow_seconds"] < LIMIT_SECONDS, (
                    "Whole cold workflow missed 1800s gate"
                )
                assert not evidence["active_children_after_close"], (
                    "Verifier children survived service cleanup"
                )
                assert evidence["verifier_after_close"]["closed"]
                assert evidence["verifier_after_close"]["active_submitted"] == 0
                assert evidence["verifier_after_close"]["compute"]["active"] == 0
                assert execution_identity() == evidence["execution"], (
                    "Source changed during cold acceptance"
                )
                evidence["status"] = "passed"
        except BaseException as error:
            evidence.update(
                status="failed",
                finalization_error_type=type(error).__name__,
                finalization_error=str(error),
            )
            raise
        finally:
            evidence["phases"]["cleanup_seconds"] = time.perf_counter() - cleanup_began
            save(output, evidence)


async def linux_child(version: str, reference_path: Path, output: Path) -> None:
    """Invoked inside the owned overlay; parent already verified resource ownership."""
    settings = Settings()
    engine = sa.create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
    bars = BarService(engine, settings.storage_path, settings.redis_url.get_secret_value())
    evidence: dict[str, Any] = {
        "status": "running",
        "platform": platform.platform(),
        "pid": os.getpid(),
    }
    try:
        assert not await asyncio.to_thread(Path("/app/.git").exists)
        assert len(bars.reader.verified) == 0
        evidence["initial_verifier"] = verifier_snapshot(bars)
        assert evidence["initial_verifier"]["submitted"] == 0
        assert not evidence["initial_verifier"]["worker_pids"]
        reference = json.loads(await asyncio.to_thread(reference_path.read_text, encoding="utf-8"))
        with engine.connect() as connection:
            row = (
                connection.execute(
                    sa.select(dataset_versions).where(
                        dataset_versions.c.dataset_version_id == version
                    )
                )
                .mappings()
                .one()
            )
        start = datetime.combine(row["trade_date"], datetime.min.time(), UTC)
        end = start + timedelta(hours=1)
        request = BarsRequest.create(
            versions=[version], symbol=row["symbol"], interval="5m", start=start, end=end
        )
        body, cache_status = await bars.read(request)
        expected = [
            bar
            for bar in reference["five"]
            if start.isoformat().replace("+00:00", "Z")
            <= bar["start"]
            < end.isoformat().replace("+00:00", "Z")
        ]
        assert body["bars"] == expected
        evidence.update(
            version=version,
            row_count=row["row_count"],
            bars=len(expected),
            cache_status=cache_status,
            body_sha256=hashlib.sha256(canonical(body)).hexdigest(),
            verifier_before_close=verifier_snapshot(bars),
            lock_sha256=file_hash(Path("/app/uv.lock")),
        )
        expected_checks = await asyncio.to_thread(
            expected_verifications, [dict(row)], settings.storage_path
        )
        verify_completed(evidence["verifier_before_close"], expected_checks)
        evidence["expected_verifications"] = expected_checks
        evidence["status"] = "read_pass_cleanup_pending"
    except BaseException as error:
        evidence.update(status="failed", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        try:
            await close_services(None, bars, engine, evidence)
            if evidence["status"] == "read_pass_cleanup_pending":
                assert not evidence["active_children_after_close"]
                assert evidence["verifier_after_close"]["closed"]
                assert evidence["verifier_after_close"]["active_submitted"] == 0
                assert evidence["verifier_after_close"]["compute"]["active"] == 0
                evidence["status"] = "passed"
        except BaseException as error:
            evidence.update(
                status="failed",
                finalization_error_type=type(error).__name__,
                finalization_error=str(error),
            )
            raise
        finally:
            save(output, evidence)


def linux_smoke(prefix: str) -> None:
    settings, resources = owned_settings()
    engine = sa.create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
    output = BASE / (prefix + "-linux.json")
    evidence: dict[str, Any] = {
        "status": "running",
        "resources": resources,
        "execution": execution_identity(),
        "build_kind": "No-network current-source overlay of existing locked marketlab:local image",
    }
    image_name = "marketlab:" + prefix
    container_id = None
    image_id = None
    try:
        migrate(settings)
        records = restore_catalog(engine)
        selected = min(records, key=lambda row: row["row_count"])
        native_reference = Path("artifacts/r4/reference-data") / (
            "reference-" + selected["dataset_version_id"] + ".json"
        )
        assert native_reference.is_file()
        folder = (BASE / (prefix + "-linux-data")).resolve()
        folder.mkdir(parents=True, exist_ok=False)
        (folder / "reference.json").write_bytes(native_reference.read_bytes())
        dockerfile = BASE / (prefix + ".Dockerfile")
        dockerfile.write_text(
            "FROM marketlab:local\nUSER root\nWORKDIR /app\nCOPY src ./src\n"
            "COPY scripts/verifier_acceptance.py /app/verifier_acceptance.py\n"
            "USER marketlab\n",
            encoding="utf-8",
        )
        with (BASE / (prefix + "-build.log")).open("w", encoding="utf-8") as log:
            result = subprocess.run(
                [
                    "docker",
                    "build",
                    "--network=none",
                    "--pull=false",
                    "--label",
                    "marketlab.verifier.owner=" + prefix,
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
        assert result.returncode == 0, "Owned Linux overlay build failed"
        image = json.loads(subprocess.check_output(["docker", "image", "inspect", image_name]))[0]
        image_id = image["Id"]
        assert image["Config"]["Labels"]["marketlab.verifier.owner"] == prefix
        pg = json.loads(
            subprocess.check_output(["docker", "inspect", resources["postgres"]["id"]])
        )[0]
        cache = json.loads(
            subprocess.check_output(["docker", "inspect", resources["redis"]["id"]])
        )[0]
        common = sorted(
            set(pg["NetworkSettings"]["Networks"]) & set(cache["NetworkSettings"]["Networks"])
        )
        assert common
        network = common[0]
        url = settings.sqlalchemy_url.set(
            host=pg["NetworkSettings"]["Networks"][network]["IPAddress"], port=5432
        )
        redis_url = (
            "redis://" + cache["NetworkSettings"]["Networks"][network]["IPAddress"] + ":6379/0"
        )
        arguments = [
            "docker",
            "run",
            "--pull=never",
            "-d",
            "--name",
            prefix,
            "--network",
            network,
            "--label",
            "marketlab.verifier.owner=" + prefix,
            "--mount",
            f"type=bind,source={ROOT / 'datasets'},target=/data/marketlab/datasets,readonly",
            "--mount",
            f"type=bind,source={folder},target=/acceptance",
            "-e",
            "MARKETLAB_DATABASE_URL=" + url.render_as_string(hide_password=False),
            "-e",
            "MARKETLAB_REDIS_URL=" + redis_url,
            image_id,
            "python",
            "/app/verifier_acceptance.py",
            "--phase",
            "linux-child",
            "--version",
            selected["dataset_version_id"],
            "--reference",
            "/acceptance/reference.json",
            "--output",
            "/acceptance/result.json",
        ]
        container_id = subprocess.check_output(arguments, text=True).strip()
        actual = json.loads(subprocess.check_output(["docker", "inspect", container_id]))[0]
        assert actual["Config"]["Labels"]["marketlab.verifier.owner"] == prefix
        evidence["owned"] = {"container_id": container_id, "image_id": image_id, "network": network}
        save(output, evidence)
        result = subprocess.run(
            ["docker", "wait", container_id], capture_output=True, text=True, timeout=240
        )
        assert result.returncode == 0 and result.stdout.strip() == "0", (
            "Owned Linux verifier smoke failed"
        )
        child = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        assert child["status"] == "passed" and child["lock_sha256"] == file_hash(Path("uv.lock"))
        evidence["child"] = child
        assert execution_identity() == evidence["execution"]
        evidence["status"] = "passed"
    except BaseException as error:
        evidence.update(status="failed", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        cleanup_errors = []
        try:
            for kind, identity in (("container", container_id), ("image", image_id)):
                if identity is None:
                    continue
                try:
                    inspect = (
                        ["docker", "inspect", identity]
                        if kind == "container"
                        else ["docker", "image", "inspect", identity]
                    )
                    actual = json.loads(subprocess.check_output(inspect, timeout=15))[0]
                    assert actual["Id"] == identity
                    assert actual["Config"]["Labels"]["marketlab.verifier.owner"] == prefix
                    if kind == "container":
                        logs = subprocess.run(
                            ["docker", "logs", identity], capture_output=True, text=True, timeout=15
                        )
                        (BASE / (prefix + "-container.log")).write_text(
                            logs.stdout + logs.stderr, encoding="utf-8"
                        )
                    remove = (
                        ["docker", "rm", "-f", identity]
                        if kind == "container"
                        else ["docker", "image", "rm", identity]
                    )
                    subprocess.run(remove, check=True, capture_output=True, timeout=30)
                    evidence["owned_" + kind + "_removed"] = True
                except BaseException as error:
                    cleanup_errors.append(error)
                    evidence.setdefault("cleanup_errors", []).append(
                        {"phase": kind, "type": type(error).__name__, "error": str(error)}
                    )
            if cleanup_errors:
                raise RuntimeError("Owned Linux smoke cleanup failed") from cleanup_errors[0]
        except BaseException as error:
            evidence.update(
                status="failed",
                finalization_error_type=type(error).__name__,
                finalization_error=str(error),
            )
            raise
        finally:
            try:
                engine.dispose()
            except BaseException as error:
                evidence.update(
                    status="failed",
                    finalization_error_type=type(error).__name__,
                    finalization_error=str(error),
                )
                raise
            finally:
                save(output, evidence)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("cold", "linux-smoke", "linux-child"), required=True)
    parser.add_argument("--prefix")
    parser.add_argument("--version")
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.phase == "linux-child":
        if not args.version or args.reference is None or args.output is None:
            parser.error("linux-child requires version/reference/output")
        asyncio.run(linux_child(args.version, args.reference, args.output))
    else:
        if (
            not args.prefix
            or not args.prefix.startswith("verifier-")
            or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in args.prefix)
        ):
            parser.error("prefix must be an owned verifier- lowercase identity")
        if args.phase == "cold":
            asyncio.run(cold(args.prefix))
        else:
            linux_smoke(args.prefix)
