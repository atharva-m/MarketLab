"""Real PostgreSQL rejection of persisted old R8 execution pins.

These are deterministic persisted-state compatibility fixtures, not old-model
calls or process deaths. They use the retained actual execution identity and
normal store checkpoint/retry APIs. Retry timestamps and runtime identities are
never edited. The optional acceptance runner requires all four proof receipts.
"""

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path

import pytest
import sqlalchemy as sa
from test_copilot import candidate
from test_copilot_integration import copilot_engine as copilot_engine
from test_copilot_integration import ready as copilot_ready
from test_memos import valid_draft
from test_memos_integration import ready as memo_ready
from test_research_integration import research_engine as research_engine

from marketlab.copilot import store as copilot_store
from marketlab.memos import store as memo_store
from marketlab.research import store as research_store
from marketlab.research.service import execution_identity

pytestmark = pytest.mark.integration
OLD_IDENTITY = Path("artifacts/r8/runtime-freeze.json")
OLD_MODEL_DIGEST = "e15635ee93129fd2086640926e900c37589c5167561104abc3914bd6644c7e07"


class NoInference:
    def __init__(self):
        self.identifications = 0
        self.calls = 0

    async def identify(self):
        self.identifications += 1
        raise AssertionError("Old source must reject before model identification")

    async def infer(self, *args):
        self.calls += 1
        raise AssertionError("Old source must reject before copilot dispatch")

    async def generate(self, *args):
        self.calls += 1
        raise AssertionError("Old source must reject before memo dispatch")


def old_execution(current):
    if not OLD_IDENTITY.is_file():
        pytest.skip("Retained actual R8 source identity required for acceptance fixture")
    old = json.loads(OLD_IDENTITY.read_text())
    assert (
        old["source_sha256"] == "3ebeb6c8ac4dbfa4a71fc9e16a2f047a4a300c9cbb8d70efc867b7dce0f9fba7"
    )
    assert set(old) == set(current)
    assert old != current and old["source_sha256"] != current["source_sha256"]
    return old


def receipt(name, proof):
    target = os.environ.get("MARKETLAB_R8_SOURCE_EVIDENCE")
    if not target:
        return
    base = Path("artifacts/r8-adoption-20261027").resolve()
    root = Path(target).resolve()
    assert root.parent == base
    assert root.name.startswith("r8-") and root.name.endswith("-source-cases")
    assert root.is_dir() and not root.is_symlink()
    proof.update(
        status="passed",
        fixture_kind="Persisted real-store old execution pin; no old-model dispatch",
        old_identity_path=str(OLD_IDENTITY),
        old_identity_file_sha256=hashlib.sha256(OLD_IDENTITY.read_bytes()).hexdigest(),
        timestamp_edits=0,
    )
    with (root / (name + ".json")).open("x", encoding="utf-8") as stream:
        json.dump(proof, stream, indent=2, default=str)


async def wait_for_eligibility(engine, table, key, identity):
    began = time.monotonic()
    while True:
        with engine.connect() as connection:
            row = connection.execute(
                sa.select(table.c.eligible_at, sa.func.clock_timestamp().label("now")).where(
                    key == identity
                )
            ).one()
        if row.eligible_at <= row.now:
            return {
                "wait_seconds": time.monotonic() - began,
                "eligible_at": row.eligible_at,
                "database_observed_at": row.now,
            }
        if time.monotonic() - began > 20:
            raise AssertionError("Native ten-second retry eligibility exceeded finite bound")
        await asyncio.sleep(0.1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "validated", [False, True], ids=["provenance-only", "validated-checkpoint"]
)
async def test_old_copilot_pin_rejected_after_real_retry(copilot_engine, tmp_path, validated):
    model = NoInference()
    service, _, body = copilot_ready(copilot_engine, tmp_path, model)
    try:
        current_execution = service.research.execution
        assert current_execution == execution_identity()
        old = old_execution(current_execution)
        request, _, _ = await service.create(body, "old-source")
        first = copilot_store.claim(copilot_engine, request)
        assert first is not None
        copilot_store.reserve_call(copilot_engine, first)
        copilot_store.checkpoint(
            copilot_engine,
            first,
            candidate() if validated else None,
            {"execution": old, "model_digest": OLD_MODEL_DIGEST},
        )
        copilot_store.fail(copilot_engine, first, transient=True)
        before = service.inspect(request)["revisions"][0]
        assert (
            before["state"] == "retry_wait"
            and before["attempt_count"] == before["model_calls"] == 1
        )
        assert await service.work(1, request) == 0
        timing = await wait_for_eligibility(
            copilot_engine, copilot_store.jobs, copilot_store.jobs.c.job_id, first.job_id
        )
        assert await service.work(1, request) == 1
        info = service.inspect(request)
        state = info["revisions"][0]
        assert state["state"] == "failed" and info["outcome"] == "failed"
        assert state["attempt_count"] == 2 and state["model_calls"] == 1
        assert [row["outcome"] for row in state["attempts"]] == ["transient", "permanent"]
        assert state["provenance"]["execution"] == old
        assert model.identifications == model.calls == 0
        assert info["run_id"] is None
        assert await service.work(1, request) == 0
        with copilot_engine.connect() as connection:
            assert (
                connection.scalar(sa.select(sa.func.count()).select_from(research_store.runs)) == 0
            )
            assert (
                connection.scalar(
                    sa.select(sa.func.count()).select_from(research_store.submissions)
                )
                == 0
            )
        receipt(
            "copilot-validated" if validated else "copilot-provenance",
            {
                "subsystem": "R5",
                "validated_checkpoint": validated,
                "old_execution": old,
                "current_execution": current_execution,
                "request_id": request,
                "state": state,
                "retry": timing,
                "model_identifications": model.identifications,
                "new_model_calls": model.calls,
                "linked_run": info["run_id"],
                "research_publications": 0,
            },
        )
    finally:
        await service.research.close()
        await service.research.bars.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("validated", [False, True], ids=["pin-only", "validated-draft"])
async def test_old_memo_pin_rejected_after_real_retry(copilot_engine, tmp_path, validated):
    model = NoInference()
    memo, run = await memo_ready(copilot_engine, tmp_path, model)
    try:
        current_execution = memo.research.execution
        assert current_execution == execution_identity()
        old = old_execution(current_execution)
        numerical = memo.research.root / "research" / run
        before_files = {
            path.name: path.read_bytes() for path in numerical.iterdir() if path.is_file()
        }
        before_read = {name: memo.research.read(run, name) for name in ("results", "summary")}
        first = memo_store.claim(copilot_engine, run)
        assert first is not None
        memo_store.pin(copilot_engine, first, old)
        memo_store.reserve_call(copilot_engine, first)
        memo_store.checkpoint(
            copilot_engine,
            first,
            valid_draft() if validated else None,
            {"model_digest": OLD_MODEL_DIGEST},
        )
        memo_store.fail(copilot_engine, first, transient=True)
        before = memo_store.inspect(copilot_engine, run)
        assert (
            before["state"] == "retry_wait"
            and before["attempt_count"] == before["model_calls"] == 1
        )
        assert await memo.work(1, run) == 0
        timing = await wait_for_eligibility(
            copilot_engine, memo_store.jobs, memo_store.jobs.c.run_id, run
        )
        assert await memo.work(1, run) == 1
        state = memo_store.inspect(copilot_engine, run)
        assert state["state"] == "failed" and state["attempt_count"] == 2
        assert state["model_calls"] == 1 and state["execution"] == old
        assert [row["outcome"] for row in state["attempts"]] == ["transient", "permanent"]
        assert model.identifications == model.calls == 0
        assert {name: (numerical / name).read_bytes() for name in before_files} == before_files
        assert {name: memo.research.read(run, name) for name in before_read} == before_read
        assert not (numerical / "memo").exists()
        with copilot_engine.connect() as connection:
            assert (
                connection.scalar(sa.select(sa.func.count()).select_from(memo_store.results)) == 0
            )
        assert await memo.work(1, run) == 0
        receipt(
            "memo-validated" if validated else "memo-pin",
            {
                "subsystem": "R6",
                "validated_checkpoint": validated,
                "old_execution": old,
                "current_execution": current_execution,
                "run_id": run,
                "state": state,
                "retry": timing,
                "model_identifications": model.identifications,
                "new_model_calls": model.calls,
                "memo_publications": 0,
                "numerical_hashes": {
                    name: hashlib.sha256(raw).hexdigest() for name, raw in before_files.items()
                },
                "numerical_readable": True,
            },
        )
    finally:
        await memo.research.close()
        await memo.research.bars.close()
