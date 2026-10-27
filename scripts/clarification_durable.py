"""Actual durable clarification on fresh owned resources and an isolated model adapter."""

import argparse
import asyncio
import copy
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from clarification_experiment import MODEL_9B, NULL_GUARD_PROMPT, sha
from prometheus_client import CollectorRegistry
from pydantic import SecretStr
from r5_acceptance import expected_spec, finish_copilot, restore

from marketlab.analytics.bars import BarService
from marketlab.analytics.cache import canonical
from marketlab.config import Settings
from marketlab.copilot import store as copilot_store
from marketlab.copilot.model import ModelFailure, Ollama
from marketlab.copilot.service import CopilotService
from marketlab.datasets.source import file_hash
from marketlab.research import store as research_store
from marketlab.research.service import ResearchService, execution_identity
from marketlab.research.spec import ResearchError

BASE = Path("artifacts/clarification-experiment/durable-nine-b-null-guard-first")
ROOT = Path("artifacts/r2/historical-storage").resolve()
OWNER = "clarify9b-durable-20261027"
PIN = "56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90"
PROMPT_SHA = "b5b297d29febdcc29e0dde8e845b52bb46568e6843be6a8004ffa39a6c2596c7"
FIXTURE = Path("tests/fixtures/r8_clarifications.json")
KEY_PREFIX = "clarify9b-durable-20261027-first"
OPTIONS = {"temperature": 0, "num_ctx": 8192, "num_predict": -1}


def write_new(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, default=str)


def evidence_base(path: Path) -> Path:
    resolved = path.resolve()
    if resolved != BASE.resolve():
        raise ValueError("Only the exact owned durable experiment directory is permitted")
    return resolved


def container_identity(actual: dict[str, Any], saved: dict[str, Any], kind: str) -> None:
    internal, external = ("5432/tcp", "55443") if kind == "postgres" else ("6379/tcp", "56385")
    if not (
        actual["Id"] == saved["Id"]
        and actual["Name"] == saved["Name"]
        and actual["Image"] == saved["Image"]
        and actual["Config"]["Image"] == saved["Config"]["Image"]
        and actual["Config"]["Labels"].get("marketlab.clarification.owner") == OWNER
        and actual["State"]["Running"] is True
        and actual["NetworkSettings"]["Ports"][internal]
        == [{"HostIp": "127.0.0.1", "HostPort": external}]
    ):
        raise RuntimeError("Exact disposable resource ownership/identity mismatch")


def owned_settings(base: Path) -> Settings:
    base = evidence_base(base)
    private = json.loads((base / "connection-private.json").read_text(encoding="utf-8-sig"))
    url = sa.engine.make_url(private["database_url"])
    if not (
        private.get("owner") == OWNER
        and (url.host, url.port, url.database) == ("127.0.0.1", 55443, "marketlab")
        and private["redis_url"] == "redis://127.0.0.1:56385/0"
        and private["ollama_url"] == "http://127.0.0.1:11442"
    ):
        raise RuntimeError("Only the explicit disposable endpoints are permitted")
    for kind in ("postgres", "redis"):
        saved = json.loads((base / f"owned-{kind}.json").read_text(encoding="utf-8-sig"))
        saved = saved[0] if isinstance(saved, list) else saved
        raw = subprocess.check_output(["docker", "inspect", saved["Id"]], timeout=15)
        container_identity(json.loads(raw)[0], saved, kind)
    return Settings(
        database_url=SecretStr(private["database_url"]),
        database_password=None,
        redis_url=SecretStr(private["redis_url"]),
        ollama_url=private["ollama_url"],
        storage_path=ROOT,
    )


def interpreter_identity() -> dict[str, Any]:
    if sha(NULL_GUARD_PROMPT.encode()) != PROMPT_SHA:
        raise RuntimeError("Pinned experimental prompt mismatch")
    return {
        "schema": "experimental-durable-interpreter-v1",
        "adapter_sha256": file_hash(Path(__file__)),
        "prompt_source_sha256": file_hash(Path("scripts/clarification_experiment.py")),
        "prompt_sha256": PROMPT_SHA,
        "model": MODEL_9B,
        "model_digest": PIN,
        "settings": OPTIONS,
        "think": False,
        "native_service_timeout_seconds": 120,
        "native_response_limit_bytes": 32768,
    }


class ExperimentalOllama(Ollama):
    """Change only the isolated request payload and label actual provenance honestly."""

    def __init__(self, url: str, base: Path, identity: dict[str, Any]) -> None:
        super().__init__(url, MODEL_9B, PIN)
        self.base, self.experiment = base, identity
        self.calls = 0

    async def bounded(self, client, method, path, **kwargs):
        if method != "POST" or path != "/api/chat":
            return await super().bounded(client, method, path, **kwargs)
        payload = copy.deepcopy(kwargs["json"])
        if payload["model"] != MODEL_9B or payload["think"] is not False:
            raise ModelFailure("Unexpected native model request")
        payload["messages"][0]["content"] = NULL_GUARD_PROMPT
        payload["options"] = OPTIONS.copy()
        size = sum(len(message["content"].encode()) for message in payload["messages"])
        if size + len(canonical(payload["format"])) > 6000:
            raise ModelFailure("Experimental prompt exceeds native inference context budget")
        kwargs["json"] = payload
        index = self.calls
        self.calls += 1
        await asyncio.to_thread(write_new, self.base / f"model-{index:03d}-request.json", payload)
        started = time.perf_counter()
        try:
            response = await super().bounded(client, method, path, **kwargs)
        except (Exception, asyncio.CancelledError) as error:
            await asyncio.to_thread(
                write_new,
                self.base / f"model-{index:03d}-failed.json",
                {
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "seconds": time.perf_counter() - started,
                    "client_cancellation_only": isinstance(error, asyncio.CancelledError),
                },
            )
            raise
        await asyncio.to_thread(
            write_new,
            self.base / f"model-{index:03d}-response.json",
            {
                "response": response,
                "seconds": time.perf_counter() - started,
            },
        )
        return response

    def provenance(self, value: dict[str, Any]) -> dict[str, Any]:
        value.update(
            prompt_version="experiment-null-guard-" + PROMPT_SHA,
            settings=OPTIONS.copy(),
            experimental_interpreter=self.experiment,
        )
        return value

    async def infer(self, turns, pinned=None):
        try:
            value, provenance = await super().infer(turns, pinned)
        except ModelFailure as error:
            if error.provenance is not None:
                error.provenance = self.provenance(error.provenance)
            raise
        return value, self.provenance(provenance)


class ExperimentalResearch(ResearchService):
    def __init__(self, bars: BarService, identity: dict[str, Any]) -> None:
        super().__init__(bars)
        self._execution = {**execution_identity(), "experimental_interpreter": identity}


def prepare(base: Path) -> None:
    base = evidence_base(base)
    owned_settings(base)
    plan = {
        "schema": "experimental-durable-clarification-v1",
        "runtime": execution_identity(),
        "interpreter": interpreter_identity(),
        "fixture_sha256": file_hash(FIXTURE),
        "catalog_snapshot_sha256": file_hash(Path("artifacts/r2/catalog-final.json")),
        "key_prefix": KEY_PREFIX,
        "cases": json.loads(FIXTURE.read_text(encoding="utf-8-sig")),
        "sixth_public_service_status": 422,
        "stale_valid_shaped_status": 409,
        "legacy_sixth_409_expectation_pass_claim": False,
    }
    write_new(base / "plan.json", plan)
    print(json.dumps({"plan": str(base / "plan.json"), "sha256": file_hash(base / "plan.json")}))


def snapshot(engine: sa.Engine, request_id: str) -> dict[str, Any]:
    with engine.connect() as connection:
        revisions = connection.scalar(
            sa.select(sa.func.count())
            .select_from(copilot_store.revisions)
            .where(copilot_store.revisions.c.request_id == request_id)
        )
        jobs = list(
            connection.execute(
                sa.select(copilot_store.jobs).where(copilot_store.jobs.c.request_id == request_id)
            ).mappings()
        )
        submissions = list(
            connection.execute(
                sa.select(research_store.submissions).where(
                    research_store.submissions.c.idempotency_key == "copilot." + request_id
                )
            ).mappings()
        )
        research_runs = list(
            connection.execute(
                sa.select(research_store.runs).where(
                    research_store.runs.c.submission_id.in_(
                        [row["submission_id"] for row in submissions]
                    )
                )
            ).mappings()
        )
    return {
        "revisions": revisions,
        "jobs": [dict(row) for row in jobs],
        "submissions": [dict(row) for row in submissions],
        "research_runs": [dict(row) for row in research_runs],
    }


async def reject(
    service: CopilotService, request_id: str, answer: dict[str, Any], key: str, status: int
) -> dict[str, Any]:
    before = await asyncio.to_thread(service.inspect, request_id)
    try:
        await service.answer(request_id, answer, key)
    except ResearchError as error:
        observed = error.status
    else:
        raise AssertionError("Rejected answer unexpectedly accepted")
    after = await asyncio.to_thread(service.inspect, request_id)
    assert before == after, "Rejected answer mutated durable request/job/attempt state"
    assert observed == status, (observed, status)
    return {
        "key": key,
        "expected_revision": answer["expected_revision"],
        "status": observed,
        "state_unchanged": True,
    }


async def run_case(
    service: CopilotService,
    model: ExperimentalOllama,
    case: dict[str, Any],
    initial_request: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    dispatches_before = model.calls
    request_id, revision, replayed = await service.create(
        initial_request, KEY_PREFIX + "-" + case["id"]
    )
    assert revision == 0 and replayed is False
    state = await finish_copilot(service, request_id)
    item = {
        "id": case["id"],
        "request_id": request_id,
        "initial": state,
        "steps": [],
        "checks": [],
        "valid": False,
    }
    try:
        assert state["outcome"] == "needs_clarification", "Initial state is not actually answerable"
        rounds = 5 if case["kind"] == "round_limit" else 1
        for index in range(rounds):
            assert state["outcome"] == "needs_clarification", (
                "Earlier terminal outcome prevented continuation"
            )
            answer = {
                "schema": "copilot-answer-v1",
                "expected_revision": index,
                "text": case["answer_text"],
                "context": case["answer_context"],
            }
            key = KEY_PREFIX + "-" + case["id"] + f"-answer-{index}"
            assert await service.answer(request_id, answer, key) == (request_id, index + 1, False)
            before = await asyncio.to_thread(service.inspect, request_id)
            count = model.calls
            assert await service.answer(request_id, answer, key) == (request_id, index + 1, True)
            assert before == await asyncio.to_thread(service.inspect, request_id)
            item["checks"].append({"revision": index + 1, "replay": True, "state_unchanged": True})
            item["checks"].append(
                await reject(service, request_id, {**answer, "text": "Different body"}, key, 409)
            )
            item["checks"].append(await reject(service, request_id, answer, key + "-stale", 409))
            assert model.calls == count, "Replay/rejection dispatched a model call"
            state = await finish_copilot(service, request_id)
            item["steps"].append(state)
            if case["kind"] == "valid":
                intent = {**initial_request["context"], **case["answer_context"]}
                assert state["outcome"] == "submitted" and state["revisions"][-1][
                    "spec"
                ] == expected_spec(intent, records)
            elif case["kind"] == "round_limit":
                assert state["outcome"] == "needs_clarification" and state["run_id"] is None
            else:
                assert state["outcome"] in case["expected_outcomes"] and state["run_id"] is None
        if case["kind"] == "round_limit":
            assert state["current_revision"] == 5 and len(state["revisions"]) == 6
            assert all(
                row["state"] == "completed"
                and row["attempt_count"] >= 1
                and row["model_calls"] >= 1
                for row in state["revisions"]
            )
            count = model.calls
            item["checks"].append(
                await reject(
                    service, request_id, {**answer, "expected_revision": 5}, key + "-sixth", 422
                )
            )
            item["checks"].append(
                await reject(
                    service,
                    request_id,
                    {**answer, "expected_revision": 4},
                    key + "-sixth-valid-shape",
                    409,
                )
            )
            assert model.calls == count
        durable = await asyncio.to_thread(snapshot, service.engine, request_id)
        assert durable["revisions"] == len(state["revisions"]) == len(durable["jobs"])
        assert len(durable["submissions"]) == int(state["run_id"] is not None)
        assert model.calls - dispatches_before == sum(
            row["model_calls"] for row in state["revisions"]
        )
        if state["run_id"] is not None:
            assert len(durable["research_runs"]) == 1
            run = durable["research_runs"][0]
            assert (
                run["state"] == "queued" and run["attempt_count"] == 0 and run["result_id"] is None
            )
        item.update(
            valid=True,
            final=state,
            database=durable,
            actual_model_dispatches=model.calls - dispatches_before,
        )
    except Exception as error:
        item.update(
            error_type=type(error).__name__,
            error=str(error),
            final=await asyncio.to_thread(service.inspect, request_id),
            database=await asyncio.to_thread(snapshot, service.engine, request_id),
        )
    return item


async def execute(base: Path) -> None:
    base = evidence_base(base)
    plan = json.loads(await asyncio.to_thread((base / "plan.json").read_text))
    if (
        plan["runtime"] != await asyncio.to_thread(execution_identity)
        or plan["interpreter"] != await asyncio.to_thread(interpreter_identity)
        or plan["fixture_sha256"] != await asyncio.to_thread(file_hash, FIXTURE)
        or plan["catalog_snapshot_sha256"]
        != await asyncio.to_thread(file_hash, Path("artifacts/r2/catalog-final.json"))
    ):
        raise RuntimeError("Frozen experimental source/runtime/fixture drift")
    settings = await asyncio.to_thread(owned_settings, base)
    engine = sa.create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
    registry = CollectorRegistry()
    bars = BarService(engine, ROOT, settings.redis_url.get_secret_value(), registry=registry)
    research = ExperimentalResearch(bars, plan["interpreter"])
    model = ExperimentalOllama(settings.ollama_url, base, plan["interpreter"])
    service = CopilotService(research, model, registry)
    write_new(
        base / "started.json", {"plan_sha256": file_hash(base / "plan.json"), "status": "started"}
    )
    began = time.perf_counter()
    result: dict[str, Any] = {
        "status": "running",
        "cases": [],
        "plan_sha256": file_hash(base / "plan.json"),
        "execution": research.execution,
    }
    try:
        assert await model.identify() == PIN
        with engine.connect() as connection:
            assert (
                connection.scalar(sa.select(sa.func.count()).select_from(copilot_store.requests))
                == 0
            ), "Fresh owned database required"
        records = await asyncio.to_thread(restore, engine)
        for case in plan["cases"]["continuations"]:
            initial = {
                "schema": "copilot-request-v1",
                **plan["cases"]["initial"],
                "dataset_versions": sorted(row["dataset_version_id"] for row in records),
            }
            item = await run_case(service, model, case, initial, records)
            result["cases"].append(item)
            await asyncio.to_thread(write_new, base / (case["id"] + ".json"), item)
            print(
                json.dumps(
                    {
                        "case": case["id"],
                        "valid": item["valid"],
                        "current_revision": item["final"]["current_revision"],
                        "outcome": item["final"]["outcome"],
                    }
                ),
                flush=True,
            )
        result["status"] = "passed" if all(row["valid"] for row in result["cases"]) else "failed"
    except Exception as error:
        result.update(status="failed", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        result.update(seconds=time.perf_counter() - began, actual_model_dispatches=model.calls)
        await asyncio.to_thread(write_new, base / "results.json", result)
        await research.close()
        await bars.close()
        engine.dispose()
    if result["status"] != "passed":
        raise AssertionError("Actual durable clarification profile incomplete/failed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "execute"))
    parser.add_argument("--base", type=Path, default=BASE)
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare(args.base)
    else:
        asyncio.run(execute(args.base))


if __name__ == "__main__":
    main()
