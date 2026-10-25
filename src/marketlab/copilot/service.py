"""Durable copilot orchestration using the existing research application service."""

import asyncio
import hashlib
from datetime import datetime
from typing import Any

import httpx
import sqlalchemy as sa
from prometheus_client import CollectorRegistry, Counter, Histogram

from marketlab.datasets.publication import dataset_versions
from marketlab.research.service import ResearchService, transient_failure
from marketlab.research.spec import ResearchError

from . import store
from .model import ModelFailure, Ollama
from .spec import QUESTIONS, assemble, decide, turn
from .spec import key as validate_key

INFERENCE_LOCK = int.from_bytes(
    hashlib.sha256(b"marketlab:copilot:inference-v1").digest()[:8], "big", signed=True
)


class CopilotService:
    def __init__(
        self, research: ResearchService, model: Ollama, registry: CollectorRegistry | None = None
    ) -> None:
        self.research, self.engine, self.model = research, research.engine, model
        self.worker_lock = asyncio.Lock()
        self.registry = registry or CollectorRegistry()
        self.outcomes = Counter(
            "marketlab_copilot_outcomes_total",
            "Copilot outcomes",
            ["outcome"],
            registry=self.registry,
        )
        self.failures = Counter(
            "marketlab_copilot_failures_total",
            "Copilot failure categories",
            ["kind"],
            registry=self.registry,
        )
        self.latency = Histogram(
            "marketlab_copilot_inference_seconds", "Local inference time", registry=self.registry
        )
        self.queue = Histogram(
            "marketlab_copilot_queue_seconds", "Copilot queue delay", registry=self.registry
        )

    async def create(self, value: Any, key: str) -> tuple[str, int, bool]:
        body = turn(value)
        validate_key(key)
        await asyncio.to_thread(self.selection, body["dataset_versions"])
        return await asyncio.to_thread(store.create, self.engine, body, key)

    def selection(self, version_ids: list[str]) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = [
                dict(r)
                for r in connection.execute(
                    sa.select(dataset_versions).where(
                        dataset_versions.c.dataset_version_id.in_(version_ids)
                    )
                ).mappings()
            ]
        if len(rows) != len(version_ids):
            raise ResearchError("Copilot dataset selection not found", 404)
        return rows

    async def answer(self, request_id: str, value: Any, key: str) -> tuple[str, int, bool]:
        return await asyncio.to_thread(
            store.answer, self.engine, request_id, turn(value, True), key
        )

    def inspect(self, request_id: str) -> dict[str, Any]:
        return store.inspect(self.engine, request_id)

    async def keep(self, current: store.Claim, done: asyncio.Event) -> None:
        while True:
            try:
                await asyncio.wait_for(done.wait(), timeout=10)
                return
            except TimeoutError:
                try:
                    if not await asyncio.to_thread(store.heartbeat, self.engine, current):
                        current.lost.set()
                        return
                except Exception:
                    current.lost.set()
                    return

    async def infer(
        self, current: store.Claim, turns: list[dict[str, Any]], pinned: str | None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        # Invalidate the physical connection on every path: session locks cannot
        # escape into the pool, even if cancellation races acquisition.
        def acquire() -> tuple[Any, bool]:
            connection = self.engine.connect()
            try:
                acquired = bool(
                    connection.scalar(sa.select(sa.func.pg_try_advisory_lock(INFERENCE_LOCK)))
                )
                connection.commit()
                return connection, acquired
            except BaseException:
                try:
                    connection.invalidate()
                finally:
                    connection.close()
                raise

        task = asyncio.create_task(asyncio.to_thread(acquire))
        connection = None
        try:
            try:
                connection, acquired = await asyncio.shield(task)
            except asyncio.CancelledError:
                connection, _ = await task
                raise
            if not acquired:
                raise ResearchError("Copilot inference capacity unavailable", 503)
            async with asyncio.timeout(120):
                installed = await self.model.identify()
                if pinned is not None and installed != pinned:
                    raise ResearchError("Ollama model identity mismatch")
                await asyncio.to_thread(
                    store.checkpoint,
                    self.engine,
                    current,
                    None,
                    {"model_digest": installed, "execution": self.research.execution},
                )
                await asyncio.to_thread(store.reserve_call, self.engine, current)
                with self.latency.time():
                    try:
                        return await self.model.infer(turns, installed)
                    except ModelFailure as error:
                        if error.provenance is not None:
                            error.provenance["execution"] = self.research.execution
                            await asyncio.to_thread(
                                store.checkpoint, self.engine, current, None, error.provenance
                            )
                        raise
        finally:
            if connection is not None:

                def release() -> None:
                    try:
                        connection.invalidate()
                    finally:
                        connection.close()

                cleanup = asyncio.create_task(asyncio.to_thread(release))
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    await cleanup
                    raise

    async def execute(self, current: store.Claim) -> None:
        done = asyncio.Event()
        keeper = asyncio.create_task(self.keep(current, done))
        try:
            info = await asyncio.to_thread(self.inspect, current.request_id)
            revision = info["revisions"][current.revision]
            self.queue.observe(
                max(
                    0,
                    (datetime.now(info["created_at"].tzinfo) - info["created_at"]).total_seconds(),
                )
            )
            turns = [r["body"] for r in info["revisions"][: current.revision + 1]]
            stored = revision["interpretation"]
            if stored is None:
                pinned = revision["provenance"]["model_digest"] if revision["provenance"] else None
                if (
                    revision["provenance"]
                    and revision["provenance"]["execution"] != self.research.execution
                ):
                    raise ResearchError("Copilot execution fingerprint mismatch")
                model, provenance = await self.infer(current, turns, pinned)
                provenance["execution"] = self.research.execution
                await asyncio.to_thread(store.checkpoint, self.engine, current, model, provenance)
            else:
                model = stored
                if revision["provenance"]["execution"] != self.research.execution:
                    raise ResearchError("Copilot execution fingerprint mismatch")
            outcome, intent, unresolved = decide(turns, model)
            spec = fingerprint = None
            if outcome == "candidate":
                versions = await asyncio.to_thread(self.selection, info["body"]["dataset_versions"])
                try:
                    spec = assemble(intent, versions)
                    fingerprint = await self.research.prepare(spec)
                    outcome = "submitted"
                except ResearchError as error:
                    if error.status not in {404, 409}:
                        raise
                    outcome, unresolved = "needs_clarification", ["coverage"]
                    spec = None
            questions = [{"field": field, "question": QUESTIONS[field]} for field in unresolved]
            await asyncio.to_thread(
                store.finish,
                self.engine,
                current,
                outcome,
                questions,
                spec.body() if spec else None,
                fingerprint,
            )
            self.outcomes.labels(outcome).inc()
        except asyncio.CancelledError:
            current.lost.set()
            raise
        except Exception as error:
            transient = transient_failure(error) or isinstance(
                error, (httpx.TransportError, TimeoutError)
            )
            self.failures.labels("transient" if transient else "permanent").inc()
            if not current.lost.is_set():
                try:
                    await asyncio.to_thread(store.fail, self.engine, current, transient)
                except Exception:
                    current.lost.set()
        finally:
            done.set()
            await keeper

    async def work(self, maximum: int, request_id: str | None = None) -> int:
        if type(maximum) is not int or not 1 <= maximum <= 62:
            raise ResearchError("Invalid bounded copilot worker limit")
        async with self.worker_lock:
            attempted = 0
            while attempted < maximum:
                current = await asyncio.to_thread(store.claim, self.engine, request_id)
                if current is None:
                    break
                await self.execute(current)
                attempted += 1
            return attempted
