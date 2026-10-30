"""Bounded generalized research and fenced verified local publication."""

import asyncio
import hashlib
import json
import os
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from marketlab.analytics.bars import BarService as LegacyBars
from marketlab.analytics.cache import CacheStatus, cache_key
from marketlab.analytics.v2 import BarService, BarsRequest
from marketlab.datasets.normalize import VerificationCancelled
from marketlab.datasets.v2.common import V2Error, canonical_json, digest, safe_path, sha256_file
from marketlab.datasets.v2.core import execute, lock, one, transaction

from . import capacity, store
from .errors import code as error_code
from .errors import transient as transient_error
from .numerics import calculate
from .provenance import execution_identity
from .spec import NUMERICS, SCHEMA, ResearchSpec

MAX_RESULT = 16 * 1024**2


def verify_directory(
    path: Path, run_id: str, fingerprint: dict[str, Any], expected: str | None = None
) -> dict[str, Any]:
    manifest_path = safe_path(path, "manifest.json")
    if not manifest_path.is_file() or manifest_path.stat().st_size > 1024**2:
        raise V2Error("integrity_failure", "Research artifact integrity failure")
    if expected is not None and sha256_file(manifest_path) != expected:
        raise V2Error("integrity_failure", "Research artifact integrity failure")
    try:
        manifest: dict[str, Any] = json.loads(manifest_path.read_bytes())
        if (
            manifest["schema"] != "research-manifest-v2"
            or manifest["run_id"] != run_id
            or manifest["fingerprint"] != fingerprint
            or set(manifest["artifacts"]) != {"spec.json", "results.json", "summary.json"}
        ):
            raise ValueError
        for name, schema, maximum in (
            ("spec.json", SCHEMA, 65536),
            ("results.json", "research-results-v2", MAX_RESULT),
            ("summary.json", "research-summary-v2", MAX_RESULT),
        ):
            artifact = safe_path(path, name)
            description = manifest["artifacts"][name]
            if (
                not artifact.is_file()
                or artifact.stat().st_size > maximum
                or artifact.stat().st_size != description["bytes"]
                or sha256_file(artifact) != description["sha256"]
            ):
                raise ValueError
            body = json.loads(artifact.read_bytes())
            if not isinstance(body, dict) or body.get("schema") != schema:
                raise ValueError
            if name == "spec.json" and digest(body) != fingerprint["request_sha256"]:
                raise ValueError
        return manifest
    except (ValueError, KeyError, TypeError, RecursionError, OSError) as error:
        raise V2Error("integrity_failure", "Research artifact integrity failure") from error


def signature(path: Path) -> tuple[tuple[int, int, int, int], ...]:
    result = []
    for name in ("manifest.json", "spec.json", "results.json", "summary.json"):
        current = safe_path(path, name).stat()
        result.append((current.st_size, current.st_mtime_ns, current.st_ctime_ns, current.st_ino))
    return tuple(result)


class ResearchService:
    def __init__(self, base: LegacyBars) -> None:
        self.base = base
        self.bars = BarService(base)
        self.engine, self.root = base.reader.engine, base.reader.root
        self._execution: dict[str, Any] | None = None
        self.attempt_timeout = 1800.0
        self.worker_lock = asyncio.Lock()
        self.active: dict[str, threading.Event] = {}
        self.summary_flights: dict[str, asyncio.Task[tuple[dict[str, Any], CacheStatus]]] = {}

    @property
    def execution(self) -> dict[str, Any]:
        if self._execution is None:
            self._execution = execution_identity()
        return self._execution

    @staticmethod
    def fingerprint(
        spec: ResearchSpec,
        rows: list[dict[str, Any]],
        execution: dict[str, Any],
        pinned: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "request_sha256": spec.digest,
            "execution": execution,
            "instruments": pinned or {r["instrument_id"]: r["metadata"] for r in rows},
            "datasets": [
                {
                    k: str(r[k])
                    for k in (
                        "dataset_version_id",
                        "instrument_id",
                        "trade_date",
                        "contract",
                        "manifest_sha256",
                        "semantic_sha256",
                    )
                }
                for r in rows
            ],
        }

    async def load(
        self,
        spec: ResearchSpec,
        rows: list[dict[str, Any]],
        cancelled: threading.Event,
        scratch: Path,
    ) -> dict[str, list[dict[str, Any]]]:
        inputs: dict[str, list[dict[str, Any]]] = {}
        for identity in spec.instrument_ids:
            inputs[identity] = []
            first = spec.history_start
            while first < spec.end:
                if cancelled.is_set():
                    raise VerificationCancelled("research cancelled")
                before = first + min(spec.end - first, timedelta(minutes=5 * 1440))
                if ((before - timedelta(microseconds=1)).date() - first.date()).days >= 5:
                    before = datetime.combine(before.date(), datetime.min.time(), UTC)
                versions = [
                    r["dataset_version_id"]
                    for r in rows
                    if r["instrument_id"] == identity
                    and first.date()
                    <= r["trade_date"]
                    <= (before - timedelta(microseconds=1)).date()
                ]
                request = BarsRequest.create(
                    versions=versions,
                    instrument_id=identity,
                    interval="5m",
                    start=first,
                    end=before,
                )
                body, _ = await self.bars.read_prepared(
                    request, rows, cancelled, scratch_root=scratch
                )
                inputs[identity].extend(body["bars"])
                first = before
        return inputs

    async def prepare(
        self,
        spec: ResearchSpec,
        cancelled: threading.Event,
        reservation: dict[str, Any],
        pinned: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        rows = await self.bars.prepare_selection(
            spec.instrument_ids, spec.dataset_versions, spec.history_start, spec.end, cancelled
        )
        if pinned is not None:
            for row in rows:
                old = pinned[row["instrument_id"]]
                if old["semantic_sha256"] != row["semantic_sha256"]:
                    raise V2Error("integrity_failure", "Pinned instrument semantics changed")
                row["metadata"] = old
        inputs = await self.load(spec, rows, cancelled, reservation["path"])
        await self.base._thread(
            lambda: calculate(
                spec, inputs, {r["instrument_id"]: r["metadata"] for r in rows}, cancelled
            ),
            cancelled,
        )
        return rows, inputs

    async def submit(self, spec: ResearchSpec, key: str) -> tuple[str, bool]:
        spec = ResearchSpec.create(spec.body())
        previous = await asyncio.to_thread(store.replay, self.engine, key, spec.digest)
        if previous:
            return previous, True
        reservation = await asyncio.to_thread(capacity.reserve, self.engine, self.root)
        cancelled = threading.Event()
        try:
            async with asyncio.timeout(self.attempt_timeout):
                rows, _ = await self.prepare(spec, cancelled, reservation)
                fingerprint = self.fingerprint(spec, rows, self.execution)
                return await asyncio.to_thread(
                    store.submit, self.engine, key, spec, fingerprint, rows
                )
        finally:
            cancelled.set()
            await asyncio.to_thread(capacity.release, self.engine, self.root, reservation)

    def stage(
        self,
        current: store.Claim,
        spec: ResearchSpec,
        fingerprint: dict[str, Any],
        result: dict[str, Any],
        summary: dict[str, Any],
        scratch: Path,
    ) -> Path:
        path = safe_path(scratch, "publication-" + uuid4().hex)
        path.mkdir(exist_ok=False)
        artifacts = {}
        for name, body, maximum in (
            ("spec.json", spec.body(), 65536),
            ("results.json", result, MAX_RESULT),
            ("summary.json", summary, MAX_RESULT),
        ):
            raw = canonical_json(body)
            if len(raw) > maximum:
                raise V2Error("capacity_exceeded", "Numerical artifact exceeds limit")
            with (path / name).open("xb") as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            artifacts[name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        manifest = {
            "schema": "research-manifest-v2",
            "run_id": current.run_id,
            "fingerprint": fingerprint,
            "artifacts": artifacts,
            "created_at": datetime.now(UTC).isoformat(),
        }
        raw = canonical_json(manifest)
        if len(raw) > 1024**2:
            raise V2Error("capacity_exceeded", "Numerical manifest exceeds limit")
        with (path / "manifest.json").open("xb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        verify_directory(path, current.run_id, fingerprint)
        return path

    def publish(self, current: store.Claim, staging: Path, fingerprint: dict[str, Any]) -> None:
        parent = safe_path(self.root, "research-v2")
        parent.mkdir(parents=True, exist_ok=True)
        final = safe_path(self.root, f"research-v2/{current.run_id}")
        verified = final if final.exists() else staging
        staged_manifest = verify_directory(staging, current.run_id, fingerprint)
        manifest = verify_directory(verified, current.run_id, fingerprint)
        if manifest["artifacts"] != staged_manifest["artifacts"]:
            raise V2Error("integrity_failure", "Research orphan differs from deterministic output")
        checked_signature = signature(verified)
        manifest_hash = sha256_file(verified / "manifest.json")
        with transaction(self.engine) as connection:
            store.fence(connection, current)
            lock(connection, "v2-research-run:" + current.run_id)
            store.fence(connection, current)
            if current.lost.is_set() or signature(verified) != checked_signature:
                raise V2Error("revision_conflict", "Research publication ownership lost")
            if final.exists() and verified != final:
                raise V2Error("unavailable", "Research publication requires verified adoption")
            if verified == staging:
                staging.rename(final)
            execute(
                connection,
                "INSERT INTO v2_research_results VALUES "
                "(:id,:path,:manifest,:results,:summary,:result_bytes,:summary_bytes,clock_timestamp())",
                id=current.run_id,
                path=f"research-v2/{current.run_id}/manifest.json",
                manifest=manifest_hash,
                results=manifest["artifacts"]["results.json"]["sha256"],
                summary=manifest["artifacts"]["summary.json"]["sha256"],
                result_bytes=manifest["artifacts"]["results.json"]["bytes"],
                summary_bytes=manifest["artifacts"]["summary.json"]["bytes"],
            )
            store.finish(connection, current)

    async def execute(self, current: store.Claim) -> None:
        self.active[current.run_id] = current.lost
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
        reservation: dict[str, Any] | None = None
        try:
            async with asyncio.timeout(self.attempt_timeout):
                reservation = await asyncio.to_thread(
                    capacity.reserve, self.engine, self.root, current.run_id, "attempt"
                )
                info = await asyncio.to_thread(store.inspect, self.engine, current.run_id)
                pinned_execution = info["fingerprint"]["execution"]
                compatibility = (
                    "source_sha256",
                    "lock_sha256",
                    "schema",
                    "numerics",
                    "bars",
                    "inventory",
                )
                if any(pinned_execution[k] != self.execution[k] for k in compatibility):
                    raise V2Error("incompatible_execution", "Research execution is incompatible")
                spec = ResearchSpec.create(info["spec"])
                rows, inputs = await self.prepare(
                    spec, current.lost, reservation, info["fingerprint"]["instruments"]
                )
                if (
                    self.fingerprint(
                        spec, rows, pinned_execution, info["fingerprint"]["instruments"]
                    )
                    != info["fingerprint"]
                ):
                    raise V2Error("integrity_failure", "Research input provenance changed")
                result, summary = await self.base._thread(
                    lambda: calculate(
                        spec, inputs, info["fingerprint"]["instruments"], current.lost
                    ),
                    current.lost,
                )
                staging = await self.base._thread(
                    lambda: self.stage(
                        current, spec, info["fingerprint"], result, summary, reservation["path"]
                    ),
                    current.lost,
                )
                await self.base._thread(
                    lambda: self.publish(current, staging, info["fingerprint"]), current.lost
                )
        except asyncio.CancelledError:
            current.lost.set()
            raise
        except Exception as error:
            code = error_code(error)
            transient = transient_error(error)
            try:
                await asyncio.to_thread(store.fail, self.engine, current, code, transient)
            except Exception:
                current.lost.set()
        finally:
            finished.set()
            await keeper
            self.active.pop(current.run_id, None)
            if reservation is not None:
                await asyncio.to_thread(capacity.release, self.engine, self.root, reservation)

    async def work(
        self,
        maximum: int,
        run_id: str | None = None,
        wait_seconds: int = 0,
        stop_event: threading.Event | None = None,
    ) -> int:
        if (
            type(maximum) is not int
            or not 1 <= maximum <= 62
            or type(wait_seconds) is not int
            or not 0 <= wait_seconds <= 3600
        ):
            raise V2Error("invalid_request", "Invalid bounded research worker invocation")
        async with self.worker_lock:
            stop = stop_event or threading.Event()
            completed, deadline = 0, asyncio.get_running_loop().time() + wait_seconds
            while completed < maximum and not stop.is_set():
                current = await asyncio.to_thread(store.claim, self.engine, self.execution, run_id)
                if current is None:
                    if asyncio.get_running_loop().time() >= deadline:
                        break
                    await asyncio.sleep(
                        min(0.2, max(0, deadline - asyncio.get_running_loop().time()))
                    )
                    continue
                await self.execute(current)
                completed += 1
            return completed

    def inspect(self, run_id: str) -> dict[str, Any]:
        return store.inspect(self.engine, run_id)

    async def cancel(self, run_id: str, revision: int, key: str) -> dict[str, Any]:
        result = await asyncio.to_thread(store.cancel, self.engine, run_id, revision, key)
        if run_id in self.active:
            self.active[run_id].set()
        return result

    def read(self, run_id: str, kind: str) -> tuple[dict[str, Any], str]:
        if kind not in {"results", "summary"}:
            raise V2Error("invalid_request", "Invalid numerical artifact selection")
        info = self.inspect(run_id)
        if info["state"] != "succeeded":
            raise V2Error("not_ready", "Numerical result is not ready")
        with self.engine.connect() as connection:
            row = one(connection, "SELECT * FROM v2_research_results WHERE run_id=:id", id=run_id)
        expected = f"research-v2/{run_id}/manifest.json"
        if row is None or row["manifest_relative_path"] != expected:
            raise V2Error("integrity_failure", "Numerical registration integrity failure")
        path = safe_path(self.root, f"research-v2/{run_id}")
        manifest = verify_directory(path, run_id, info["fingerprint"], row["manifest_sha256"])
        for name in ("results", "summary"):
            if manifest["artifacts"][name + ".json"]["sha256"] != row[name + "_sha256"]:
                raise V2Error("integrity_failure", "Numerical registration integrity failure")
        return json.loads((path / (kind + ".json")).read_bytes()), row[kind + "_sha256"]

    async def _summary(self, run_id: str) -> tuple[dict[str, Any], CacheStatus]:
        body, expected = await asyncio.to_thread(self.read, run_id, "summary")
        key = cache_key("summary", {"v2_run": run_id, "sha256": expected}, {"definition": NUMERICS})

        def valid(value: Any) -> bool:
            return isinstance(value, dict) and digest(value) == expected

        cached, available = await self.base.cache.get(key, valid)
        if cached is not None:
            return cached, "HIT"
        stored = available and await self.base.cache.put(key, body, "summary", validator=valid)
        return body, "MISS" if stored else "BYPASS"

    async def summary(self, run_id: str) -> tuple[dict[str, Any], CacheStatus]:
        task = self.summary_flights.get(run_id)
        if task is None:
            if len(self.summary_flights) >= 128:
                raise V2Error("capacity_exceeded", "Numerical read capacity unavailable")
            task = asyncio.create_task(self._summary(run_id))
            self.summary_flights[run_id] = task
            task.add_done_callback(lambda _: self.summary_flights.pop(run_id, None))
        return await asyncio.shield(task)

    async def close(self) -> None:
        for event in self.active.values():
            event.set()
        await asyncio.gather(*list(self.summary_flights.values()), return_exceptions=True)
        await self.bars.close()
