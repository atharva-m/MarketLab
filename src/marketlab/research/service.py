"""Validated manual submission, bounded research execution and immutable publication."""

import asyncio
import hashlib
import json
import os
import shutil
import tempfile
import threading
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, OperationalError

from marketlab.analytics.bars import BarError, BarService, BarsRequest
from marketlab.analytics.cache import CacheStatus, cache_key, canonical
from marketlab.datasets.publication import _build, _safe_path, _storage_root, dataset_versions
from marketlab.datasets.source import file_hash

from . import store
from .numerics import calculate
from .spec import NUMERICS, SCHEMA, ResearchError, ResearchSpec

MAX_RESULT = 16 * 1024 * 1024


def transient_failure(error: Exception) -> bool:
    if isinstance(error, DBAPIError):
        return getattr(error.orig, "sqlstate", None) in {
            "40001",
            "40P01",
            "55P03",
            "57014",
            "08006",
            "08003",
        }
    return isinstance(error, TimeoutError) or (
        isinstance(error, (BarError, ResearchError)) and error.status in {503, 504}
    )


def execution_identity() -> dict[str, Any]:
    project = Path(__file__).resolve().parents[3]
    hashes = {
        str(path.relative_to(project)).replace("\\", "/"): file_hash(path)
        for path in sorted((project / "src" / "marketlab").rglob("*.py"))
    }
    return {
        **_build(),
        "source_sha256": hashlib.sha256(canonical(hashes)).hexdigest(),
        "schema": SCHEMA,
        "numerics": NUMERICS,
        "bars": "bars-v1",
    }


def verify_directory(
    path: Path, run_id: str, fingerprint: dict[str, Any], expected_hash: str | None = None
) -> dict[str, Any]:
    manifest_path = _safe_path(path, Path("manifest.json"))
    if (
        not manifest_path.is_file()
        or manifest_path.stat().st_size > 1024 * 1024
        or (expected_hash is not None and file_hash(manifest_path) != expected_hash)
    ):
        raise ResearchError("Research artifact integrity failure")
    manifest: dict[str, Any] = json.loads(manifest_path.read_bytes())
    if (
        manifest.get("schema") != "research-manifest-v1"
        or manifest.get("run_id") != run_id
        or manifest.get("fingerprint") != fingerprint
        or set(manifest.get("artifacts", {})) != {"spec.json", "results.json", "summary.json"}
    ):
        raise ResearchError("Research artifact integrity failure")
    for name, description in manifest["artifacts"].items():
        artifact = _safe_path(path, Path(name))
        if (
            not artifact.is_file()
            or artifact.stat().st_size > MAX_RESULT
            or artifact.stat().st_size != description["bytes"]
            or file_hash(artifact) != description["sha256"]
        ):
            raise ResearchError("Research artifact integrity failure")
        value = json.loads(artifact.read_bytes())
        expected_schema = {
            "spec.json": SCHEMA,
            "results.json": "research-results-v1",
            "summary.json": "research-summary-v1",
        }[name]
        if not isinstance(value, dict) or value.get("schema") != expected_schema:
            raise ResearchError("Research artifact integrity failure")
    return manifest


class ResearchService:
    """Reuse the process BarService; no private unbounded analytical engine."""

    def __init__(self, bars: BarService) -> None:
        self.bars = bars
        self.engine = bars.reader.engine
        self.root = _storage_root(bars.reader.root)
        self._execution: dict[str, Any] | None = None
        self.attempt_timeout = 1800.0
        self.worker_lock = asyncio.Lock()
        self.summary_flights: dict[str, asyncio.Task[tuple[dict[str, Any], CacheStatus]]] = {}

    @property
    def execution(self) -> dict[str, Any]:
        # Legacy startup and published result reads also run in packaged images
        # without Git metadata. Only new executions need checkout provenance.
        if self._execution is None:
            self._execution = execution_identity()
        return self._execution

    def catalog(self, spec: ResearchSpec) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = [
                dict(r)
                for r in connection.execute(
                    sa.select(dataset_versions).where(
                        dataset_versions.c.dataset_version_id.in_(spec.dataset_versions)
                    )
                ).mappings()
            ]
        if len(rows) != len(spec.dataset_versions):
            raise ResearchError("Dataset version not found", 404)
        expected: set[tuple[str, date]] = set()
        day = spec.history_start.date()
        while day <= (spec.end - timedelta(microseconds=1)).date():
            expected.update((s, day) for s in spec.symbols)
            day += timedelta(days=1)
        actual = [(r["symbol"], r["trade_date"]) for r in rows]
        if (
            len(set(actual)) != len(actual)
            or set(actual) != expected
            or any(r["venue"] != "binance_spot" or r["status"] != "published" for r in rows)
        ):
            raise ResearchError("Research dataset coverage mismatch", 409)
        return sorted(rows, key=lambda r: (r["symbol"], r["trade_date"]))

    async def load(
        self, spec: ResearchSpec
    ) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
        rows = await asyncio.to_thread(self.catalog, spec)
        inputs: dict[str, list[dict[str, Any]]] = {}
        for symbol in spec.symbols:
            inputs[symbol] = []
            first = spec.history_start
            while first < spec.end:
                # Midnight-ended chunks touch <=5 days even from partial first day.
                boundary = datetime.combine(
                    first.date() + timedelta(days=5), datetime.min.time(), UTC
                )
                before = min(spec.end, boundary, first + timedelta(minutes=5 * 1440))
                versions = [
                    r["dataset_version_id"]
                    for r in rows
                    if r["symbol"] == symbol
                    and first.date()
                    <= r["trade_date"]
                    <= (before - timedelta(microseconds=1)).date()
                ]
                body, _ = await self.bars.read(
                    BarsRequest.create(
                        versions=versions, symbol=symbol, interval="5m", start=first, end=before
                    )
                )
                inputs[symbol].extend(body["bars"])
                first = before
        return inputs, rows

    def fingerprint(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "execution": self.execution,
            "datasets": [
                {
                    "dataset_version_id": r["dataset_version_id"],
                    "manifest_sha256": r["manifest_sha256"],
                }
                for r in rows
            ],
        }

    async def submit(self, spec: ResearchSpec, key: str) -> tuple[str, bool]:
        spec = ResearchSpec.create(spec.body())
        original = await asyncio.to_thread(store.replay, self.engine, key, spec.digest)
        if original:
            return original, True
        fingerprint = await self.prepare(spec)
        return await asyncio.to_thread(store.submit, self.engine, key, spec.body(), fingerprint)

    async def prepare(self, spec: ResearchSpec) -> dict[str, Any]:
        """Complete the same catalog, integrity and warm-up validation for all callers."""
        spec = ResearchSpec.create(spec.body())
        async with asyncio.timeout(self.attempt_timeout):
            inputs, rows = await self.load(spec)
            cancelled = threading.Event()
            await self.bars._thread(lambda: calculate(spec, inputs, cancelled), cancelled)
        return self.fingerprint(rows)

    def stage(
        self,
        current: store.Claim,
        spec: ResearchSpec,
        fingerprint: dict[str, Any],
        result: dict[str, Any],
        summary: dict[str, Any],
    ) -> Path:
        staging = _safe_path(self.root, Path(".staging"))
        staging.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix="research-", dir=staging))
        try:
            artifacts: dict[str, Any] = {}
            for name, value in (
                ("spec.json", spec.body()),
                ("results.json", result),
                ("summary.json", summary),
            ):
                raw = canonical(value)
                if len(raw) > MAX_RESULT:
                    raise ResearchError("Research result exceeds 16 MiB")
                with (directory / name).open("xb") as output:
                    output.write(raw)
                    output.flush()
                    os.fsync(output.fileno())
                artifacts[name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            manifest = {
                "schema": "research-manifest-v1",
                "run_id": current.run_id,
                "fingerprint": fingerprint,
                "artifacts": artifacts,
                "created_at": datetime.now(UTC).isoformat(),
                "definition": NUMERICS,
                "units": result["units"],
                "coverage": {s: p["coverage"] for s, p in result["profiles"].items()},
            }
            with (directory / "manifest.json").open("xb") as output:
                output.write(canonical(manifest))
                output.flush()
                os.fsync(output.fileno())
            verify_directory(directory, current.run_id, fingerprint)
            if current.lost.is_set():
                raise ResearchError("Research ownership lost", 409)
            return directory
        except BaseException:
            shutil.rmtree(directory)
            raise

    def publish(self, current: store.Claim, staging: Path, fingerprint: dict[str, Any]) -> None:
        parent = _safe_path(self.root, Path("research"))
        parent.mkdir(parents=True, exist_ok=True)
        final = _safe_path(self.root, Path("research") / current.run_id)
        verified = final if final.exists() else staging
        manifest = verify_directory(verified, current.run_id, fingerprint)
        digest = file_hash(verified / "manifest.json")
        try:
            with self.engine.begin() as connection:
                store.bounded(connection)
                store.fence(connection, current)
                store.advisory(connection, "run:" + current.run_id)
                if final.exists() and verified != final:
                    raise ResearchError("Research publication requires verified adoption", 503)
                store.fence(connection, current)
                if not final.exists():
                    staging.rename(final)
                connection.execute(
                    store.results.insert().values(
                        run_id=current.run_id,
                        manifest_sha256=digest,
                        manifest_path=(
                            Path("research") / current.run_id / "manifest.json"
                        ).as_posix(),
                        results_sha256=manifest["artifacts"]["results.json"]["sha256"],
                        summary_sha256=manifest["artifacts"]["summary.json"]["sha256"],
                        registered_at=sa.func.clock_timestamp(),
                    )
                )
                store.finish(connection, current)
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    async def execute(self, current: store.Claim) -> None:
        finished = asyncio.Event()

        async def renew() -> None:
            while True:
                try:
                    await asyncio.wait_for(finished.wait(), 10)
                    return
                except TimeoutError:
                    try:
                        if not await asyncio.to_thread(store.heartbeat, self.engine, current):
                            current.lost.set()
                            return
                    except Exception:
                        current.lost.set()
                        return

        keeper = asyncio.create_task(renew())
        staging: Path | None = None
        try:
            async with asyncio.timeout(self.attempt_timeout):
                info = await asyncio.to_thread(store.inspect, self.engine, current.run_id)
                spec = ResearchSpec.create(info["spec"])
                if info["fingerprint"]["execution"] != self.execution:
                    raise ResearchError("Research execution fingerprint mismatch", 409)
                inputs, rows = await self.load(spec)
                if self.fingerprint(rows) != info["fingerprint"]:
                    raise ResearchError("Research input fingerprint mismatch", 409)
                result, summary = await self.bars._thread(
                    lambda: calculate(spec, inputs, current.lost), current.lost
                )
                staging = await self.bars._thread(
                    lambda: self.stage(current, spec, info["fingerprint"], result, summary),
                    current.lost,
                )
                await self.bars._thread(
                    lambda: self.publish(current, staging, info["fingerprint"]), current.lost
                )
                staging = None
        except asyncio.CancelledError:
            # Cancellation leaves the current fenced attempt for lease recovery.
            current.lost.set()
            raise
        except Exception as error:
            transient = transient_failure(error)
            if not current.lost.is_set():
                try:
                    await asyncio.to_thread(store.fail, self.engine, current, transient)
                except (ResearchError, OperationalError):
                    current.lost.set()
        finally:
            finished.set()
            await keeper
            if staging is not None and staging.exists():
                await asyncio.to_thread(shutil.rmtree, staging)

    async def work(self, maximum: int, run_id: str | None = None) -> int:
        if type(maximum) is not int or not 1 <= maximum <= 62:
            raise ResearchError("Invalid bounded research worker limit")
        async with self.worker_lock:
            completed = 0
            while completed < maximum:
                current = await asyncio.to_thread(store.claim, self.engine, run_id)
                if current is None:
                    break
                await self.execute(current)
                completed += 1
            return completed

    def inspect(self, run_id: str) -> dict[str, Any]:
        return store.inspect(self.engine, run_id)

    def read(self, run_id: str, kind: str) -> tuple[dict[str, Any], str]:
        if kind not in {"summary", "results"}:
            raise ResearchError("Invalid research artifact selection")
        info = store.inspect(self.engine, run_id)
        if info["state"] != "succeeded":
            raise ResearchError("Research result is not ready", 409)
        with self.engine.connect() as connection:
            row = (
                connection.execute(sa.select(store.results).where(store.results.c.run_id == run_id))
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ResearchError("Research result registration missing")
        expected = (Path("research") / run_id / "manifest.json").as_posix()
        if row["manifest_path"] != expected:
            raise ResearchError("Research artifact integrity failure")
        directory = _safe_path(self.root, Path("research") / run_id)
        manifest = verify_directory(directory, run_id, info["fingerprint"], row["manifest_sha256"])
        for artifact in ("results", "summary"):
            if manifest["artifacts"][artifact + ".json"]["sha256"] != row[artifact + "_sha256"]:
                raise ResearchError("Research artifact integrity failure")
        return json.loads((directory / (kind + ".json")).read_bytes()), row[kind + "_sha256"]

    async def _summary(self, run_id: str) -> tuple[dict[str, Any], CacheStatus]:
        body, digest = await asyncio.to_thread(self.read, run_id, "summary")
        key = cache_key("summary", {"run": run_id, "sha256": digest}, {"definition": NUMERICS})

        def valid(value: Any) -> bool:
            return (
                isinstance(value, dict) and hashlib.sha256(canonical(value)).hexdigest() == digest
            )

        cached, available = await self.bars.cache.get(key, valid)
        if cached is not None:
            return cached, "HIT"
        stored = available and await self.bars.cache.put(key, body, "summary", validator=valid)
        return body, "MISS" if stored else "BYPASS"

    async def summary(self, run_id: str) -> tuple[dict[str, Any], CacheStatus]:
        flight = self.summary_flights.get(run_id)
        if flight is None:
            if len(self.summary_flights) >= 128:
                raise ResearchError("Research read capacity unavailable", 503)
            flight = asyncio.create_task(self._summary(run_id))
            self.summary_flights[run_id] = flight
            flight.add_done_callback(lambda _: self.summary_flights.pop(run_id, None))
        else:
            self.bars.metrics.coalesced.inc()
        result = await asyncio.shield(flight)
        self.bars.metrics.outcomes.labels(result[1]).inc()
        return result

    async def close(self) -> None:
        await asyncio.gather(*list(self.summary_flights.values()), return_exceptions=True)
