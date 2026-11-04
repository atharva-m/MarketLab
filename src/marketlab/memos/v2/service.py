"""Verified immutable memo packages with shared conservative root accounting."""

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx

from marketlab.copilot.model import ModelFailure
from marketlab.copilot.v2 import durable
from marketlab.copilot.v2.model import DIGEST, execution
from marketlab.copilot.v2.service import drained, keep
from marketlab.datasets.v2 import admission
from marketlab.datasets.v2.common import V2Error, canonical_json, digest, safe_path, sha256_file
from marketlab.datasets.v2.core import execute, lock, one, transaction
from marketlab.inference import admission as inference_admission
from marketlab.inference import release_current
from marketlab.research.v2.service import ResearchService

from . import store
from .model import MemoModel
from .spec import FACTS, RENDERER, facts, render

PACKAGE_LIMIT = admission.MEMO_OUTPUT_LIMIT


def verify_directory(
    path: Path, info: dict[str, Any], expected: str | None = None
) -> tuple[dict[str, Any], str]:
    manifest_path = safe_path(path, "manifest.json")
    if (
        not manifest_path.is_file()
        or manifest_path.stat().st_size > 131072
        or (expected is not None and sha256_file(manifest_path) != expected)
    ):
        raise V2Error("integrity_failure", "Memo manifest integrity failure")
    try:
        manifest = json.loads(manifest_path.read_bytes())
        if (
            manifest["schema"] != "memo-manifest-v2"
            or manifest["run_id"] != info["run_id"]
            or any(
                manifest[k] != info[k]
                for k in (
                    "numerical_manifest_sha256",
                    "summary_sha256",
                    "numerical_fingerprint_sha256",
                    "execution",
                )
            )
        ):
            raise ValueError
        names = {
            "facts.json": 32768,
            "draft.json": 32768,
            "provenance.json": 131072,
            "memo.txt": 16384,
        }
        if set(manifest["artifacts"]) != set(names):
            raise ValueError
        size = manifest_path.stat().st_size
        bodies = {}
        for name, limit in names.items():
            artifact = safe_path(path, name)
            description = manifest["artifacts"][name]
            if (
                not artifact.is_file()
                or artifact.stat().st_size > limit
                or artifact.stat().st_size != description["bytes"]
                or sha256_file(artifact) != description["sha256"]
            ):
                raise ValueError
            size += artifact.stat().st_size
            bodies[name] = artifact.read_bytes()
        if size > PACKAGE_LIMIT:
            raise ValueError
        source = json.loads(bodies["facts.json"])
        value = json.loads(bodies["draft.json"])
        provenance = json.loads(bodies["provenance.json"])
        memo = bodies["memo.txt"].decode("utf-8")
        if (
            source["schema"] != FACTS
            or source["summary_sha256"] != info["summary_sha256"]
            or manifest["renderer"] != RENDERER
            or value != info["draft"]
            or provenance != info["provenance"]
            or render(value, source) != memo
        ):
            raise ValueError
        return manifest, memo
    except (ValueError, TypeError, KeyError, OSError) as error:
        raise V2Error("integrity_failure", "Memo package integrity failure") from error


class MemoService:
    def __init__(self, research: ResearchService, model: MemoModel) -> None:
        self.research, self.model = research, model
        self.engine, self.root = research.engine, research.root
        self.worker_lock = asyncio.Lock()
        self._execution: dict[str, Any] | None = None

    @property
    def execution(self) -> dict[str, Any]:
        if self._execution is None:
            self._execution = execution("memo")
        return self._execution

    def numerical(self, run_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        summary, expected = self.research.read(run_id, "summary")
        info = self.research.inspect(run_id)
        with self.engine.connect() as connection:
            row = one(connection, "SELECT * FROM v2_research_results WHERE run_id=:id", id=run_id)
        if row is None or row["summary_sha256"] != expected:
            raise V2Error("integrity_failure", "Memo numerical registration mismatch")
        return summary, row, info["fingerprint"]

    def enqueue(self, run_id: str, body: Any, key: str) -> dict[str, Any]:
        if type(body) is not dict or body != {"schema": "memo-request-v2"}:
            raise V2Error("invalid_request", "Invalid memo request")
        summary, numerical, fingerprint = self.numerical(run_id)
        facts(summary)
        replayed = store.enqueue(self.engine, run_id, key, numerical, fingerprint, self.execution)
        return {**self.inspect(run_id), "replayed": replayed}

    def inspect(self, run_id: str) -> dict[str, Any]:
        info = store.inspect(self.engine, run_id)
        if info["state"] == "succeeded":
            info["memo"], info["manifest"] = self.read(run_id)
        elif info["state"] != "failed" and info["execution"] != self.execution:
            info["error_code"] = "incompatible_execution"
        if info["provenance"] is not None:
            info["provenance"] = {k: v for k, v in info["provenance"].items() if k != "response"}
        return info

    def read(self, run_id: str) -> tuple[str, dict[str, Any]]:
        info = store.inspect(self.engine, run_id)
        if info["state"] != "succeeded":
            raise V2Error("not_ready", "Supplemental memo is not ready")
        with self.engine.connect() as connection:
            row = one(connection, "SELECT * FROM v2_memo_results WHERE run_id=:id", id=run_id)
        if row is None or row["summary_sha256"] != info["summary_sha256"]:
            raise V2Error("integrity_failure", "Memo result registration mismatch")
        path = safe_path(self.root, row["relative_path"])
        manifest, memo = verify_directory(path, info, row["manifest_sha256"])
        summary, numerical, fingerprint = self.numerical(run_id)
        if (
            numerical["manifest_sha256"] != info["numerical_manifest_sha256"]
            or digest(fingerprint) != info["numerical_fingerprint_sha256"]
            or digest(facts(summary)) != row["facts_sha256"]
            or manifest["artifacts"]["memo.txt"]["sha256"] != row["memo_sha256"]
        ):
            raise V2Error("integrity_failure", "Memo grounding registration mismatch")
        return memo, manifest

    def stage(
        self, current: durable.Claim, info: dict[str, Any], source: dict[str, Any]
    ) -> tuple[Path, dict[str, Any], int]:
        path = safe_path(self.root, str(current.relative_path))
        path.mkdir(parents=True, exist_ok=False)
        artifacts: dict[str, dict[str, Any]] = {}
        for name, raw in (
            ("facts.json", canonical_json(source)),
            ("draft.json", canonical_json(info["draft"])),
            ("provenance.json", canonical_json(info["provenance"])),
            ("memo.txt", render(info["draft"], source).encode()),
        ):
            with (path / name).open("xb") as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            artifacts[name] = {"bytes": len(raw), "sha256": sha256_file(path / name)}
        manifest = {
            "schema": "memo-manifest-v2",
            "run_id": current.identity,
            **{
                k: info[k]
                for k in (
                    "numerical_manifest_sha256",
                    "summary_sha256",
                    "numerical_fingerprint_sha256",
                    "execution",
                )
            },
            "renderer": RENDERER,
            "facts": FACTS,
            "artifacts": artifacts,
        }
        raw = canonical_json(manifest)
        if len(raw) + sum(v["bytes"] for v in artifacts.values()) > PACKAGE_LIMIT:
            raise V2Error("capacity_exceeded", "Memo package exceeds reserved capacity")
        with (path / "manifest.json").open("xb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        verify_directory(path, info)
        size = len(raw) + sum(v["bytes"] for v in artifacts.values())
        return path, manifest, size

    def publish(
        self,
        current: durable.Claim,
        info: dict[str, Any],
        path: Path,
        manifest: dict[str, Any],
        size: int,
        ticket: dict[str, Any],
    ) -> None:
        manifest_hash = sha256_file(path / "manifest.json")
        verify_directory(path, info, manifest_hash)
        with transaction(self.engine) as connection:
            durable.fence(connection, current)
            row = one(
                connection,
                "SELECT * FROM v2_research_results WHERE run_id=:id",
                id=current.identity,
            )
            if (
                row is None
                or row["manifest_sha256"] != info["numerical_manifest_sha256"]
                or row["summary_sha256"] != info["summary_sha256"]
            ):
                raise V2Error("integrity_failure", "Memo numerical publication mismatch")
            lock(connection, "v2-space:" + ticket["root"])
            admission.require(connection, self.root)
            charged = execute(
                connection,
                "UPDATE v2_data_charges SET charged_bytes=:bytes,state='retained',"
                "updated_at=clock_timestamp() WHERE charge_id=:charge AND ticket_id=:ticket "
                "AND state='reserved' AND ceiling_bytes>=:bytes RETURNING charge_id",
                bytes=size,
                charge=ticket["charge_id"],
                ticket=ticket["ticket_id"],
            ).first()
            if charged is None:
                raise V2Error("integrity_failure", "Memo publication charge is missing")
            admission.changed(connection, ticket)
            execute(
                connection,
                "INSERT INTO v2_memo_results "
                "(run_id,attempt_number,relative_path,manifest_sha256,memo_sha256,facts_sha256,"
                "summary_sha256,package_bytes) VALUES "
                "(:id,:attempt,:path,:manifest,:memo,:facts,:summary,:bytes)",
                id=current.identity,
                attempt=current.attempt,
                path=current.relative_path,
                manifest=manifest_hash,
                memo=manifest["artifacts"]["memo.txt"]["sha256"],
                facts=manifest["artifacts"]["facts.json"]["sha256"],
                summary=info["summary_sha256"],
                bytes=size,
            )
            durable.complete(connection, current)

    async def execute(self, current: durable.Claim) -> None:
        done = asyncio.Event()
        heartbeat = asyncio.create_task(keep(self.engine, current, done))
        ticket = None
        try:
            info = await drained(lambda: store.inspect(self.engine, current.identity), current)
            if info["execution"] != self.execution:
                raise V2Error("incompatible_execution", "Memo source mismatch")
            summary, numerical, fingerprint = await drained(
                lambda: self.numerical(current.identity), current
            )
            if (
                numerical["manifest_sha256"] != info["numerical_manifest_sha256"]
                or digest(fingerprint) != info["numerical_fingerprint_sha256"]
            ):
                raise V2Error("integrity_failure", "Memo numerical identity mismatch")
            source = facts(summary)
            identities = self.model.prepare(source)
            ticket = await drained(
                lambda: admission.acquire(
                    self.engine, self.root, "memo", PACKAGE_LIMIT, current.identity, PACKAGE_LIMIT
                ),
                current,
            )
            if ticket is None:
                raise V2Error("unavailable", "Memo requires initialized root accounting")
            await drained(
                lambda: admission.mark_path(self.engine, ticket, str(current.relative_path)),
                current,
            )
            with transaction(self.engine) as connection:
                durable.fence(connection, current)
                admission.activate(
                    connection,
                    ticket,
                    current.identity,
                    attempt=current.attempt,
                    token=current.token,
                )
                execute(
                    connection,
                    "UPDATE v2_memo_attempts SET ticket_id=:ticket,charge_id=:charge WHERE "
                    "run_id=:id AND attempt_number=:attempt",
                    ticket=ticket["ticket_id"],
                    charge=ticket["charge_id"],
                    id=current.identity,
                    attempt=current.attempt,
                )
            if info["draft"] is None:
                async with asyncio.timeout(self.model.timeout):
                    installed = await self.model.identify()
                    number = await drained(
                        lambda: durable.reserve(self.engine, current, identities, installed),
                        current,
                    )
                    try:
                        value, provenance = await self.model.generate(source, installed)
                        render(value, source)
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
                        lambda: durable.checkpoint(self.engine, current, number, value, provenance),
                        current,
                    )
                    info = await drained(
                        lambda: store.inspect(self.engine, current.identity), current
                    )
            elif (
                info["provenance"]["model_digest"] != DIGEST
                or info["provenance"]["input_sha256"] != identities["input_sha256"]
            ):
                raise V2Error("integrity_failure", "Memo checkpoint input mismatch")
            await release_current(self.engine)
            path, manifest, size = await drained(lambda: self.stage(current, info, source), current)
            await drained(
                lambda: self.publish(current, info, path, manifest, size, ticket), current
            )
        except asyncio.CancelledError:
            current.lost.set()
            raise
        except Exception as error:
            transient = isinstance(error, (httpx.TransportError, TimeoutError))
            if not current.lost.is_set():
                try:
                    await drained(lambda: durable.fail(self.engine, current, transient), current)
                except Exception:
                    current.lost.set()
        finally:
            done.set()
            await heartbeat
            if ticket is not None:
                await asyncio.to_thread(admission.complete_legacy, self.engine, ticket)

    async def work(self, maximum: int, run_id: str | None = None) -> int:
        if type(maximum) is not int or not 1 <= maximum <= 62:
            raise V2Error("invalid_request", "Invalid bounded memo worker limit")
        async with self.worker_lock:
            count = 0
            while count < maximum:
                async with inference_admission(self.engine) as acquired:
                    if not acquired or await asyncio.to_thread(durable.pending, self.engine):
                        break
                    current = await asyncio.to_thread(
                        durable.claim, self.engine, "memo", self.execution, run_id
                    )
                    if current is None:
                        break
                    await self.execute(current)
                    count += 1
            return count
