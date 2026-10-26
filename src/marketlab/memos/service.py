"""Verified memo generation and fenced immutable supplemental publication."""

import asyncio
import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import sqlalchemy as sa
from prometheus_client import CollectorRegistry, Counter, Histogram

from marketlab.analytics.cache import canonical
from marketlab.copilot.model import ModelFailure
from marketlab.copilot.spec import identity
from marketlab.datasets.publication import _safe_path
from marketlab.datasets.source import file_hash
from marketlab.inference import admission, release_current
from marketlab.research import store as research_store
from marketlab.research.service import ResearchService, transient_failure
from marketlab.research.spec import ResearchError

from . import store
from .model import MemoModel
from .spec import FACTS, RENDERER, facts, render


async def drained[T](operation: Callable[[], T], current: store.Claim) -> T:
    task = asyncio.create_task(asyncio.to_thread(operation))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        current.lost.set()
        try:
            await task
        except BaseException:
            pass
        raise cancellation


class MemoService:
    def __init__(
        self, research: ResearchService, model: MemoModel, registry: CollectorRegistry | None = None
    ) -> None:
        self.research, self.model = research, model
        self.engine, self.root = research.engine, research.root
        registry = registry or CollectorRegistry()
        self.outcomes = Counter(
            "marketlab_memo_outcomes_total", "Memo outcomes", ["outcome"], registry=registry
        )
        self.latency = Histogram(
            "marketlab_memo_inference_seconds", "Memo inference time", registry=registry
        )
        self.queue = Histogram(
            "marketlab_memo_queue_seconds", "Memo queue delay", registry=registry
        )
        self.failures = Counter(
            "marketlab_memo_failures_total", "Memo failure categories", ["kind"], registry=registry
        )
        self.publications = Histogram(
            "marketlab_memo_publication_seconds",
            "Memo supplemental publication time",
            registry=registry,
        )
        self.worker_lock = asyncio.Lock()
        self.attempt_timeout = 180.0

    def numerical(self, run_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        summary, summary_hash = self.research.read(run_id, "summary")
        with self.engine.connect() as connection:
            row = dict(
                connection.execute(
                    sa.select(research_store.results).where(
                        research_store.results.c.run_id == run_id
                    )
                )
                .mappings()
                .one()
            )
        if row["summary_sha256"] != summary_hash:
            raise ResearchError("Memo numerical identity mismatch")
        return summary, row

    def enqueue(self, run_id: str) -> tuple[str, bool]:
        identity(run_id)
        _, verified = self.numerical(run_id)
        with self.engine.begin() as connection:
            research_store.bounded(connection)
            row = (
                connection.execute(
                    sa.select(research_store.runs)
                    .where(research_store.runs.c.run_id == run_id)
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            research_store.advisory(connection, "run:" + run_id)
            registered = (
                connection.execute(
                    sa.select(research_store.results).where(
                        research_store.results.c.run_id == run_id
                    )
                )
                .mappings()
                .one()
            )
            if row["state"] != "succeeded" or dict(registered) != verified:
                raise ResearchError("Memo numerical identity mismatch", 409)
            replayed = store.enqueue(
                connection, run_id, verified["manifest_sha256"], verified["summary_sha256"]
            )
        return run_id, replayed

    def verify(
        self, directory: Path, info: dict[str, Any], expected: str | None = None
    ) -> tuple[dict[str, Any], str]:
        path = _safe_path(directory, Path("manifest.json"))
        if (
            not path.is_file()
            or path.stat().st_size > 131072
            or (expected is not None and file_hash(path) != expected)
        ):
            raise ResearchError("Memo artifact integrity failure")
        manifest = json.loads(path.read_bytes())
        run_id = info["run_id"]
        if (
            manifest.get("schema") != "memo-manifest-v1"
            or manifest.get("run_id") != run_id
            or manifest.get("numerical_manifest_sha256") != info["numerical_manifest_sha256"]
            or manifest.get("summary_sha256") != info["summary_sha256"]
            or manifest.get("execution") != info["execution"]
            or manifest.get("provenance") != info["provenance"]
            or manifest.get("draft") != info["draft"]
        ):
            raise ResearchError("Memo artifact integrity failure")
        name = "research_memo_" + run_id + ".md"
        memo = _safe_path(directory, Path(name))
        description = manifest.get("artifact", {})
        if description.get("name") != name or not memo.is_file() or memo.stat().st_size > 16384:
            raise ResearchError("Memo artifact integrity failure")
        raw = memo.read_bytes()
        if (
            description.get("bytes") != len(raw)
            or description.get("sha256") != hashlib.sha256(raw).hexdigest()
        ):
            raise ResearchError("Memo artifact integrity failure")
        summary, registered = self.numerical(run_id)
        source = facts(summary)
        if (
            registered["manifest_sha256"] != info["numerical_manifest_sha256"]
            or manifest.get("facts_sha256") != hashlib.sha256(canonical(source)).hexdigest()
            or manifest.get("facts_version") != FACTS
            or manifest.get("renderer") != RENDERER
            or not isinstance(manifest.get("renderer_sha256"), str)
            or len(manifest["renderer_sha256"]) != 64
            or raw != render(info["draft"], source).encode()
        ):
            raise ResearchError("Memo artifact grounding failure")
        return manifest, raw.decode()

    def stage(self, current: store.Claim, info: dict[str, Any], source: dict[str, Any]) -> Path:
        parent = _safe_path(self.root, Path(".staging"))
        parent.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix="memo-", dir=parent))
        try:
            raw = render(info["draft"], source).encode()
            name = "research_memo_" + current.run_id + ".md"
            with self.engine.connect() as connection:
                generated_at: str = (
                    connection.execute(sa.select(sa.func.clock_timestamp()))
                    .scalar_one()
                    .isoformat()
                )
            manifest = {
                "schema": "memo-manifest-v1",
                "run_id": current.run_id,
                "numerical_manifest_sha256": info["numerical_manifest_sha256"],
                "summary_sha256": info["summary_sha256"],
                "execution": info["execution"],
                "provenance": info["provenance"],
                "draft": info["draft"],
                "facts_version": FACTS,
                "facts_sha256": hashlib.sha256(canonical(source)).hexdigest(),
                "renderer": RENDERER,
                "renderer_sha256": file_hash(Path(__file__).with_name("spec.py")),
                "generated_at": generated_at,
                "validation": "grounded",
                "artifact": {
                    "name": name,
                    "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                },
            }
            for filename, data in ((name, raw), ("manifest.json", canonical(manifest))):
                with (directory / filename).open("xb") as output:
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
            self.verify(directory, info)
            if current.lost.is_set():
                raise ResearchError("Memo ownership lost", 409)
            return directory
        except BaseException:
            shutil.rmtree(directory)
            raise

    def publish(self, current: store.Claim, staging: Path, info: dict[str, Any]) -> None:
        final = _safe_path(self.root, Path("research") / current.run_id / "memo")
        verified = final if final.exists() else staging
        manifest, _ = self.verify(verified, info)
        digest = file_hash(verified / "manifest.json")
        with self.engine.begin() as connection:
            research_store.bounded(connection)
            store.fence(connection, current)
            research_store.advisory(connection, "memo:" + current.run_id)
            if final.exists() and verified != final:
                raise ResearchError("Memo publication requires verified adoption", 503)
            store.fence(connection, current)
            if not final.exists():
                staging.rename(final)
            connection.execute(
                store.results.insert().values(
                    run_id=current.run_id,
                    manifest_path=(
                        Path("research") / current.run_id / "memo" / "manifest.json"
                    ).as_posix(),
                    manifest_sha256=digest,
                    memo_sha256=manifest["artifact"]["sha256"],
                    summary_sha256=info["summary_sha256"],
                    registered_at=sa.func.clock_timestamp(),
                )
            )
            store.finish(connection, current, manifest["artifact"]["sha256"])

    def inspect(self, run_id: str) -> dict[str, Any]:
        info = store.inspect(self.engine, run_id)
        # Bounded raw model output is provenance for local audit, never a status payload.
        info.pop("draft", None)
        info.pop("execution", None)
        if info["provenance"] is not None:
            info["provenance"] = {k: v for k, v in info["provenance"].items() if k != "response"}
        if info["state"] == "ready":
            content, manifest = self.read(run_id)
            info["content"] = content
            info["memo_sha256"] = manifest["artifact"]["sha256"]
        return info

    def read(self, run_id: str) -> tuple[str, dict[str, Any]]:
        info = store.inspect(self.engine, run_id)
        if info["state"] != "ready":
            raise ResearchError("Memo is not ready", 409)
        with self.engine.connect() as connection:
            row = (
                connection.execute(sa.select(store.results).where(store.results.c.run_id == run_id))
                .mappings()
                .one_or_none()
            )
        expected = (Path("research") / run_id / "memo" / "manifest.json").as_posix()
        if (
            row is None
            or row["manifest_path"] != expected
            or row["summary_sha256"] != info["summary_sha256"]
        ):
            raise ResearchError("Memo registration integrity failure")
        directory = _safe_path(self.root, Path("research") / run_id / "memo")
        manifest, content = self.verify(directory, info, row["manifest_sha256"])
        if (
            row["memo_sha256"] != manifest["artifact"]["sha256"]
            or row["memo_sha256"] != info["result_sha256"]
        ):
            raise ResearchError("Memo registration integrity failure")
        return content, manifest

    async def keep(self, current: store.Claim, done: asyncio.Event) -> None:
        while True:
            try:
                await asyncio.wait_for(done.wait(), 10)
                return
            except TimeoutError:
                try:
                    if not await asyncio.to_thread(store.heartbeat, self.engine, current):
                        current.lost.set()
                        return
                except Exception:
                    current.lost.set()
                    return

    async def execute(self, current: store.Claim) -> None:
        async with admission(self.engine) as acquired:
            if not acquired:
                raise ResearchError("Memo inference capacity unavailable", 503)
            await self._execute(current)

    async def _execute(self, current: store.Claim) -> None:
        done = asyncio.Event()
        keeper = asyncio.create_task(self.keep(current, done))
        staging: Path | None = None
        try:
            async with asyncio.timeout(self.attempt_timeout):
                info = await drained(lambda: store.inspect(self.engine, current.run_id), current)

                def queue_delay() -> float:
                    with self.engine.connect() as connection:
                        now: datetime = connection.execute(
                            sa.select(sa.func.clock_timestamp())
                        ).scalar_one()
                    return float(max(0.0, (now - info["created_at"]).total_seconds()))

                self.queue.observe(await drained(queue_delay, current))
                await drained(
                    lambda: store.pin(self.engine, current, self.research.execution), current
                )
                summary, numerical = await drained(lambda: self.numerical(current.run_id), current)
                if (
                    numerical["manifest_sha256"] != info["numerical_manifest_sha256"]
                    or numerical["summary_sha256"] != info["summary_sha256"]
                ):
                    raise ResearchError("Memo numerical identity mismatch")
                source = facts(summary)
                if info["draft"] is None:
                    pinned = info["provenance"]["model_digest"] if info["provenance"] else None
                    installed = await self.model.identify()
                    if pinned is not None and installed != pinned:
                        raise ResearchError("Ollama model identity mismatch")
                    await drained(
                        lambda: store.checkpoint(
                            self.engine, current, None, {"model_digest": installed}
                        ),
                        current,
                    )
                    await drained(lambda: store.reserve_call(self.engine, current), current)
                    try:
                        with self.latency.time():
                            value, provenance = await self.model.generate(source, installed)
                        render(value, source)
                    except ModelFailure as error:
                        if error.provenance is not None:
                            failed_provenance = error.provenance
                            await drained(
                                lambda: store.checkpoint(
                                    self.engine, current, None, failed_provenance
                                ),
                                current,
                            )
                        raise
                    await drained(
                        lambda: store.checkpoint(self.engine, current, value, provenance), current
                    )
                await release_current(self.engine)
                info = await drained(lambda: store.inspect(self.engine, current.run_id), current)
                staging = await drained(lambda: self.stage(current, info, source), current)
                with self.publications.time():
                    await drained(lambda: self.publish(current, staging, info), current)
                self.outcomes.labels("ready").inc()
        except asyncio.CancelledError:
            current.lost.set()
            raise
        except Exception as error:
            self.outcomes.labels("failure").inc()
            transient = transient_failure(error) or isinstance(error, httpx.TransportError)
            self.failures.labels("transient" if transient else "rejected").inc()
            if not current.lost.is_set():
                try:
                    await asyncio.to_thread(
                        store.fail,
                        self.engine,
                        current,
                        transient,
                    )
                except Exception:
                    current.lost.set()
        finally:
            done.set()
            await keeper
            if staging is not None and staging.exists():
                await asyncio.to_thread(shutil.rmtree, staging)

    async def work(self, maximum: int, run_id: str | None = None) -> int:
        from marketlab.copilot import store as copilot_store

        if type(maximum) is not int or not 1 <= maximum <= 62:
            raise ResearchError("Invalid bounded memo worker limit")
        async with self.worker_lock:
            count = 0
            while count < maximum:
                async with admission(self.engine) as acquired:
                    if not acquired or await asyncio.to_thread(copilot_store.pending, self.engine):
                        break
                    current = await asyncio.to_thread(store.claim, self.engine, run_id)
                    if current is None:
                        break
                    await self.execute(current)
                    count += 1
            return count
