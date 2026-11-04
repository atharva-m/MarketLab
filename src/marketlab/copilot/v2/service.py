"""Selected immutable context and durable grounded numerical handoffs."""

import asyncio
import threading
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx

from marketlab.analytics.bars import BarError
from marketlab.copilot.model import ModelFailure
from marketlab.datasets.v2 import capacity, catalog
from marketlab.datasets.v2.common import V2Error, canonical_json, digest
from marketlab.inference import admission, release_current
from marketlab.research.v2.service import ResearchService

from . import durable, store
from .model import DIGEST, CopilotModel, copilot_versions, execution
from .spec import QUESTIONS, assemble, decide, supplied, turn


async def drained[T](operation: Callable[[], T], current: durable.Claim) -> T:
    task = asyncio.create_task(asyncio.to_thread(operation))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        current.lost.set()
        try:
            await task
        except BaseException:
            pass
        raise


async def keep(engine: Any, current: durable.Claim, done: asyncio.Event) -> None:
    while True:
        try:
            await asyncio.wait_for(done.wait(), 10)
            return
        except TimeoutError:
            try:
                if not await asyncio.to_thread(durable.heartbeat, engine, current):
                    current.lost.set()
                    return
            except Exception:
                current.lost.set()
                return


class CopilotService:
    def __init__(self, research: ResearchService, model: CopilotModel) -> None:
        self.research, self.model = research, model
        self.engine, self.root = research.engine, research.root
        self.worker_lock = asyncio.Lock()
        self._execution: dict[str, Any] | None = None

    @property
    def execution(self) -> dict[str, Any]:
        if self._execution is None:
            self._execution = execution("copilot")
        return self._execution

    def snapshot(self, body: dict[str, Any]) -> dict[str, Any]:
        from marketlab.datasets.v2.capabilities import value as capabilities

        rows = self.research.bars._catalog(tuple(body["dataset_versions"]))
        selected = body["instrument_ids"]
        if set(selected) != {r["instrument_id"] for r in rows} or len(
            {(r["instrument_id"], r["trade_date"]) for r in rows}
        ) != len(rows):
            raise V2Error("revision_conflict", "Selected instrument/day alternatives conflict")
        cancelled = threading.Event()
        for row in rows:
            with self.research.base.reader.compute.query(
                cancelled, self.research.base.admission_timeout
            ):
                catalog.inspect_version(self.engine, self.root, row["dataset_version_id"])
        after = self.research.bars._catalog(tuple(body["dataset_versions"]))
        if any(
            (a["catalog_identity"], a["signature"]) != (b["catalog_identity"], b["signature"])
            for a, b in zip(rows, after, strict=True)
        ):
            raise V2Error("integrity_failure", "Selected snapshot changed during verification")
        instruments, coverage = {}, {}
        pinned = {}
        for number, identity in enumerate(selected):
            metadata = next(r["metadata"] for r in rows if r["instrument_id"] == identity)
            slot = f"i{number}"
            instruments[slot] = {
                k: metadata[k]
                for k in ("instrument_id", "source_symbol", "base_asset", "quote_asset")
            }
            pinned[identity] = metadata
            ranges: list[dict[str, str]] = []
            for day in sorted(r["trade_date"] for r in rows if r["instrument_id"] == identity):
                first, end = day.isoformat(), (day + timedelta(days=1)).isoformat()
                if ranges and ranges[-1]["end"] == first:
                    ranges[-1]["end"] = end
                else:
                    ranges.append({"start": first, "end": end})
            coverage[slot] = ranges
        result = {
            "schema": "copilot-selection-v2",
            "instruments": instruments,
            "metadata": pinned,
            "registry_sha256": digest(pinned),
            "capability_sha256": capabilities()["sha256"],
            "coverage": coverage,
            "datasets": [
                {
                    k: str(r[k])
                    for k in (
                        "dataset_version_id",
                        "instrument_id",
                        "trade_date",
                        "manifest_sha256",
                        "semantic_sha256",
                    )
                }
                for r in rows
            ],
        }
        if len(canonical_json(result)) > 65536:
            raise V2Error("invalid_request", "Selected context exceeds limit")
        supplied(body["context"], result)
        return result

    async def create(self, value: Any, key: str) -> tuple[str, int, bool]:
        body = turn(value)
        previous = await asyncio.to_thread(store.replay, self.engine, body, key)
        if previous:
            return previous
        snapshot = await asyncio.to_thread(self.snapshot, body)
        self.model.prepare(snapshot, [body])
        return await asyncio.to_thread(
            store.create, self.engine, body, snapshot, self.execution, key
        )

    async def answer(self, request_id: str, value: Any, key: str) -> tuple[str, int, bool]:
        body = turn(value, True)
        info = await asyncio.to_thread(store.inspect, self.engine, request_id)
        # Exact key replays return without reconstructing later transcript budgets.
        for revision in info["revisions"]:
            if revision["answer_key"] == key:
                return await asyncio.to_thread(store.answer, self.engine, request_id, body, key)
        if body["expected_revision"] != info["current_revision"]:
            raise V2Error("revision_conflict", "Clarification revision conflict")
        turns = [r["body"] for r in info["revisions"]] + [body]
        self.model.prepare(info["snapshot"], turns)
        return await asyncio.to_thread(store.answer, self.engine, request_id, body, key)

    def inspect(self, request_id: str) -> dict[str, Any]:
        info = store.inspect(self.engine, request_id)
        if info["state"] not in {"succeeded", "failed"} and info["execution"] != self.execution:
            info["error_code"] = "incompatible_execution"
        for revision in info["revisions"]:
            if revision["provenance"] is not None:
                revision["provenance"] = {
                    k: v for k, v in revision["provenance"].items() if k != "response"
                }
        return info

    async def execute(self, current: durable.Claim) -> None:
        done = asyncio.Event()
        heartbeat = asyncio.create_task(keep(self.engine, current, done))
        reservation = None
        try:
            info = await drained(
                lambda: store.inspect(self.engine, str(current.request_id)), current
            )
            if info["execution"] != self.execution:
                raise V2Error("incompatible_execution", "Interpretation source mismatch")
            turns = [r["body"] for r in info["revisions"]]
            revision = info["revisions"][current.revision]
            interpretation = revision["interpretation"]
            if interpretation is None:
                async with asyncio.timeout(self.model.timeout):
                    identities = self.model.prepare(info["snapshot"], turns)
                    installed = await self.model.identify()
                    number = await drained(
                        lambda: durable.reserve(self.engine, current, identities, installed),
                        current,
                    )
                    try:
                        interpretation, provenance = await self.model.interpret(
                            info["snapshot"], turns, installed, expected=identities
                        )
                    except ModelFailure as error:
                        failed_provenance = error.provenance
                        if failed_provenance is not None:
                            await drained(
                                lambda: durable.checkpoint(
                                    self.engine, current, number, None, failed_provenance
                                ),
                                current,
                            )
                        raise
                    await drained(
                        lambda: durable.checkpoint(
                            self.engine, current, number, interpretation, provenance
                        ),
                        current,
                    )
            else:
                provenance = revision["provenance"]
                identities = self.model.prepare(info["snapshot"], turns)
                if (
                    type(provenance) is not dict
                    or provenance.get("model_digest") != DIGEST
                    or any(
                        provenance.get(key) != value
                        for key, value in {**identities, **copilot_versions()}.items()
                    )
                ):
                    raise V2Error("integrity_failure", "Stored interpretation receipt mismatch")
            await release_current(self.engine)
            outcome, intent, unresolved = decide(turns, info["snapshot"], interpretation)
            spec = fingerprint = rows = None
            if outcome == "candidate":
                try:
                    spec = assemble(intent, info["snapshot"])
                    reservation = await drained(
                        lambda: capacity.reserve(self.engine, self.root), current
                    )
                    from marketlab.datasets.v2.native_children import scope

                    with scope(self.engine, reservation.get("_admission")):
                        async with asyncio.timeout(self.research.attempt_timeout):
                            rows, _ = await self.research.prepare(
                                spec, current.lost, reservation, info["snapshot"]["metadata"]
                            )
                    original = {r["dataset_version_id"]: r for r in info["snapshot"]["datasets"]}
                    if any(
                        any(
                            str(row[k]) != original[row["dataset_version_id"]][k]
                            for k in ("manifest_sha256", "semantic_sha256")
                        )
                        for row in rows
                    ):
                        raise V2Error("integrity_failure", "Selected snapshot identity mismatch")
                    fingerprint = self.research.fingerprint(
                        spec, rows, self.research.execution, info["snapshot"]["metadata"]
                    )
                    outcome = "submitted"
                except (V2Error, BarError) as error:
                    if isinstance(error, V2Error) and error.code not in {
                        "coverage_gap",
                        "revision_conflict",
                        "not_found",
                        "invalid_request",
                    }:
                        raise
                    if isinstance(error, BarError) and error.status == 503:
                        raise
                    outcome, unresolved, spec, fingerprint, rows = (
                        "needs_clarification",
                        ["coverage"],
                        None,
                        None,
                        None,
                    )
            questions = [{"field": f, "question": QUESTIONS[f]} for f in unresolved]
            await drained(
                lambda: store.finish(
                    self.engine, current, outcome, questions, spec, fingerprint, rows
                ),
                current,
            )
        except asyncio.CancelledError:
            current.lost.set()
            raise
        except Exception as error:
            transient = isinstance(error, (httpx.TransportError, TimeoutError))
            if not current.lost.is_set():
                try:
                    await drained(
                        lambda: durable.fail(
                            self.engine,
                            current,
                            transient,
                        ),
                        current,
                    )
                except Exception:
                    current.lost.set()
        finally:
            done.set()
            await heartbeat
            if reservation is not None:
                await asyncio.to_thread(capacity.release, self.engine, self.root, reservation)

    async def work(self, maximum: int, request_id: str | None = None) -> int:
        if type(maximum) is not int or not 1 <= maximum <= 62:
            raise V2Error("invalid_request", "Invalid bounded copilot worker limit")
        async with self.worker_lock:
            count = 0
            while count < maximum:
                async with admission(self.engine) as acquired:
                    if not acquired:
                        break
                    current = await asyncio.to_thread(
                        durable.claim, self.engine, "copilot", self.execution, request_id
                    )
                    if current is None:
                        break
                    await self.execute(current)
                    count += 1
            return count
