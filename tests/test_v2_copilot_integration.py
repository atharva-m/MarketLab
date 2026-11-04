"""Real PostgreSQL fencing, call accounting, handoffs and supplemental publication."""

import asyncio
import hashlib
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import sqlalchemy as sa
from test_v2_browser_imports_integration import browser_engine as browser_engine  # noqa: F401
from test_v2_copilot import draft, request
from test_v2_ingestion_integration import v2_engine as v2_engine  # noqa: F401
from test_v2_research_integration import fixture_version
from test_v2_research_integration import research_engine as research_engine  # noqa: F401

from marketlab.analytics.bars import BarService
from marketlab.copilot.v2 import durable, store
from marketlab.copilot.v2.model import DIGEST, CopilotModel, copilot_versions
from marketlab.copilot.v2.service import CopilotService
from marketlab.copilot.v2.spec import FIELDS, assemble, supplied
from marketlab.datasets.v2 import admission, capacity
from marketlab.datasets.v2.common import V2Error, canonical_json
from marketlab.datasets.v2.core import execute, one
from marketlab.inference import admission as inference_admission
from marketlab.memos.v2 import store as memo_store
from marketlab.memos.v2.model import MemoModel
from marketlab.memos.v2.service import MemoService
from marketlab.memos.v2.spec import facts
from marketlab.research.v2.service import ResearchService
from marketlab.research.v2.spec import ResearchSpec

pytestmark = pytest.mark.integration


@pytest.fixture
def model_engine(browser_engine):  # noqa: F811
    apply_model_migration(browser_engine)
    return browser_engine


def apply_model_migration(engine):
    path = Path(__file__).resolve().parents[1] / "migrations/versions/0011_v2_copilot_memos.py"
    spec = importlib.util.spec_from_file_location("phase5_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with engine.begin() as connection:
        for name in (
            "copilot_requests",
            "copilot_revisions",
            "copilot_jobs",
            "copilot_attempts",
            "research_submissions",
            "research_runs",
            "research_attempts",
            "research_results",
            "memo_jobs",
            "memo_attempts",
            "memo_results",
            "ingestion_submissions",
            "ingestion_jobs",
            "ingestion_attempts",
        ):
            execute(connection, f"CREATE TABLE {name} (LIKE public.{name} INCLUDING ALL)")
        connection.execute(sa.text(module.DDL))


def receipt(value, identities):
    raw = canonical_json(value).decode()
    return {
        **identities,
        **(copilot_versions() if value.get("schema") == "copilot-interpretation-v2" else {}),
        "model_digest": DIGEST,
        "response": raw,
        "response_sha256": hashlib.sha256(raw.encode()).hexdigest(),
    }


class ProtocolCopilot(CopilotModel):
    def __init__(self):
        super().__init__("http://unused")
        self.calls = 0

    async def identify(self):
        return DIGEST

    async def interpret(self, snapshot, turns, pinned=DIGEST, expected=None):
        assert expected is None or expected == self.prepare(snapshot, turns)
        self.calls += 1
        intent = dict.fromkeys(FIELDS)
        evidence = dict.fromkeys(FIELDS)
        for n, item in enumerate(turns):
            for key, value in supplied(item["context"], snapshot).items():
                intent[key] = value
                evidence[key] = {"turn": n, "context": True}
        unresolved = sorted(k for k, v in intent.items() if v is None)
        value = {
            "schema": "copilot-interpretation-v2",
            "outcome": "needs_clarification" if unresolved else "candidate",
            "reason": "missing_fields" if unresolved else "none",
            "intent": intent,
            "evidence": evidence,
            "unresolved": unresolved,
        }
        return value, receipt(value, self.prepare(snapshot, turns))


class ProtocolMemo(MemoModel):
    def __init__(self):
        super().__init__("http://unused")
        self.calls = 0

    async def identify(self):
        return DIGEST

    async def generate(self, source, pinned=DIGEST):
        self.calls += 1
        value = draft()
        return value, receipt(value, self.prepare(source))


async def setup(engine, tmp_path):
    root = tmp_path / "storage"
    admission.initialize(engine, root)
    version = fixture_version(engine, root, tmp_path)
    base = BarService(engine, root, None)
    numerical = ResearchService(base)
    copilot = CopilotService(numerical, ProtocolCopilot())
    memo = MemoService(numerical, ProtocolMemo())
    body = request()
    body["instrument_ids"] = body["context"]["instrument_ids"] = ["binance:spot:BTCUSDT"]
    body["dataset_versions"] = [version]
    return base, numerical, copilot, memo, body


async def test_durable_manual_equivalence_idempotency_auto_enqueue_and_verified_memo(
    model_engine, tmp_path
):
    base, numerical, copilot, memo, body = await setup(model_engine, tmp_path)
    try:
        identity, revision, replayed = await copilot.create(body, "copilot-one")
        assert revision == 0 and not replayed
        assert await copilot.create(body, "copilot-one") == (identity, 0, True)
        assert await copilot.work(1, identity) == 1
        info = copilot.inspect(identity)
        assert info["outcome"] == "submitted" and copilot.model.calls == 1
        run = info["run_id"]
        spec = ResearchSpec.create(info["revisions"][0]["spec"])
        manual, _ = await numerical.submit(spec, "manual-equivalent")
        assert await numerical.work(1, run) == 1
        assert await numerical.work(1, manual) == 1
        actual, _ = numerical.read(run, "results")
        expected, _ = numerical.read(manual, "results")
        assert actual == expected
        assert memo.inspect(run)["state"] == "queued"
        assert await memo.work(1, run) == 1
        ready = memo.inspect(run)
        assert ready["state"] == "succeeded" and memo.model.calls == 1
        assert len(ready["memo"].strip().split("\n\n")) == 3
        assert memo.enqueue(run, {"schema": "memo-request-v2"}, "same-memo")["replayed"]
        assert await memo.work(1, run) == 0
        with model_engine.connect() as connection:
            row = one(connection, "SELECT * FROM v2_memo_results WHERE run_id=:id", id=run)
            attempt = one(connection, "SELECT * FROM v2_memo_attempts WHERE run_id=:id", id=run)
            charge = one(
                connection,
                "SELECT * FROM v2_data_charges WHERE charge_id=:id",
                id=attempt["charge_id"],
            )
            assert charge["charged_bytes"] == row["package_bytes"] and charge["state"] == "retained"
        # Corruption does not regenerate, fall back or spend a call.
        package = numerical.root / row["relative_path"]
        (package / "memo.txt").write_text("invented", encoding="utf-8")
        with pytest.raises(V2Error):
            memo.read(run)
        assert memo.model.calls == 1
    finally:
        await numerical.close()
        await base.close()


async def test_five_answers_sixth_response_replays_and_stale_revision_have_no_extra_work(
    model_engine, tmp_path
):
    base, numerical, copilot, memo, body = await setup(model_engine, tmp_path)
    try:
        full = body["context"]
        body["context"] = {}
        identity, _, _ = await copilot.create(body, "clarification")
        assert await copilot.work(1, identity) == 1
        for n, name in enumerate(("workflow", "instrument_ids", "start", "end", "history_start")):
            answer = {
                "schema": "copilot-answer-v2",
                "expected_revision": n,
                "text": "Confirm.",
                "context": {name: full[name]},
            }
            assert await copilot.answer(identity, answer, f"answer-{n}") == (identity, n + 1, False)
            assert await copilot.answer(identity, answer, f"answer-{n}") == (identity, n + 1, True)
            assert await copilot.work(1, identity) == 1
        assert copilot.model.calls == 6
        sixth = {
            "schema": "copilot-answer-v2",
            "expected_revision": 5,
            "text": "Confirm 5m.",
            "context": {},
        }
        with pytest.raises(V2Error) as error:
            await copilot.answer(identity, sixth, "sixth")
        assert error.value.code == "invalid_request"
        sixth["expected_revision"] = 0
        with pytest.raises(V2Error) as error:
            await copilot.answer(identity, sixth, "stale")
        assert error.value.code == "revision_conflict"
        info = store.inspect(model_engine, identity)
        assert len(info["revisions"]) == 6 and info["run_id"] is None
        assert all(r["model_calls"] == 1 for r in info["revisions"])
        assert copilot.model.calls == 6
    finally:
        await numerical.close()
        await base.close()


async def test_spent_reservation_survives_death_and_checkpoint_recovery(model_engine, tmp_path):
    base, numerical, copilot, memo, body = await setup(model_engine, tmp_path)
    try:
        identity, _, _ = await copilot.create(body, "recover")
        claim = durable.claim(model_engine, "copilot", copilot.execution, identity)
        info = store.inspect(model_engine, identity)
        value, proof = await copilot.model.interpret(info["snapshot"], [body])
        number = durable.reserve(
            model_engine, claim, copilot.model.prepare(info["snapshot"], [body]), DIGEST
        )
        durable.checkpoint(model_engine, claim, number, value, proof)
        with model_engine.begin() as connection:
            execute(
                connection,
                "UPDATE v2_copilot_jobs SET lease_until=clock_timestamp()-interval '1 second' "
                "WHERE job_id=:id",
                id=claim.identity,
            )
        assert await copilot.work(1, identity) == 1
        assert copilot.model.calls == 1
        info = store.inspect(model_engine, identity)
        assert info["outcome"] == "submitted" and info["revisions"][0]["model_calls"] == 1
        with pytest.raises(V2Error):
            store.finish(model_engine, claim, "unsupported", [])
    finally:
        await numerical.close()
        await base.close()


@pytest.mark.parametrize(
    "field", ["input_sha256", "schema_sha256", "prompt_sha256", "input_bytes", *copilot_versions()]
)
async def test_recovered_checkpoint_requires_exact_inputs_versions_without_reinference(
    model_engine, tmp_path, field
):
    base, numerical, copilot, memo, body = await setup(model_engine, tmp_path)
    try:
        identity, _, _ = await copilot.create(body, "recovery-mismatch")
        claim = durable.claim(model_engine, "copilot", copilot.execution, identity)
        info = store.inspect(model_engine, identity)
        expected = copilot.model.prepare(info["snapshot"], [body])
        value, proof = await copilot.model.interpret(info["snapshot"], [body], expected=expected)
        number = durable.reserve(model_engine, claim, expected, DIGEST)
        durable.checkpoint(model_engine, claim, number, value, proof)
        changed = dict(proof, **{field: "changed"})
        with model_engine.begin() as connection:
            execute(
                connection,
                "UPDATE v2_copilot_revisions SET provenance_json=:proof WHERE request_id=:id",
                proof=canonical_json(changed).decode(),
                id=identity,
            )
            execute(
                connection,
                "UPDATE v2_copilot_jobs SET lease_until=clock_timestamp()-interval '1 second' "
                "WHERE job_id=:id",
                id=claim.identity,
            )
        assert await copilot.work(1, identity) == 1
        after = store.inspect(model_engine, identity)
        assert after["state"] == "failed" and after["run_id"] is None
        assert after["revisions"][0]["model_calls"] == 1 and copilot.model.calls == 1
        assert len(after["revisions"][0]["calls"]) == 1
        assert after["revisions"][0]["provenance"] == changed
    finally:
        await numerical.close()
        await base.close()


async def test_checkpoint_requires_reserved_dynamic_schema_and_explicit_versions(
    model_engine, tmp_path
):
    base, numerical, copilot, memo, body = await setup(model_engine, tmp_path)
    try:
        identity, _, _ = await copilot.create(body, "checkpoint-identities")
        claim = durable.claim(model_engine, "copilot", copilot.execution, identity)
        info = store.inspect(model_engine, identity)
        expected = copilot.model.prepare(info["snapshot"], [body])
        value, proof = await copilot.model.interpret(info["snapshot"], [body], expected=expected)
        number = durable.reserve(model_engine, claim, expected, DIGEST)
        for field in ("schema_sha256", "prompt_sha256", *copilot_versions()):
            with pytest.raises(V2Error):
                durable.checkpoint(
                    model_engine, claim, number, value, dict(proof, **{field: "old"})
                )
        durable.checkpoint(model_engine, claim, number, value, proof)
        with model_engine.connect() as connection:
            call = one(
                connection, "SELECT * FROM v2_copilot_calls WHERE job_id=:id", id=claim.identity
            )
            assert call["state"] == "checkpointed"
            assert call["schema_sha256"] == expected["schema_sha256"]
            assert call["prompt_sha256"] == expected["prompt_sha256"]
        assert copilot.model.calls == 1
    finally:
        await numerical.close()
        await base.close()


def test_memo_excluded_but_legacy_retains_shared_eight_slot_contention(model_engine, tmp_path):
    root = tmp_path / "storage"
    admission.initialize(model_engine, root)
    tickets = [admission.acquire(model_engine, root, "legacy", 0) for _ in range(8)]
    memo = admission.acquire(model_engine, root, "memo", 1)
    try:
        with pytest.raises(V2Error):
            admission.acquire(model_engine, root, "research", 0)
        upload = admission.acquire(model_engine, root, "upload", 0)
        admission.finish(model_engine, upload, 0)
    finally:
        admission.finish(model_engine, memo, 0)
        for ticket in tickets:
            admission.finish(model_engine, ticket, 0)


def test_active_partial_memo_allows_audit_and_independent_admission(model_engine, tmp_path):
    root = tmp_path / "storage"
    admission.initialize(model_engine, root)
    ticket = admission.acquire(model_engine, root, "memo", 1024**2, physical_bytes=1024**2)
    relative = "memos-v2/partial-fixture/owned-attempt"
    admission.mark_path(model_engine, ticket, relative)
    path = root / relative
    path.mkdir(parents=True)
    (path / "partial.json").write_bytes(b"retained partial bytes")
    admission.audit(model_engine, root)
    independent = admission.acquire(model_engine, root, "research", 0)
    admission.finish(model_engine, independent, 0)
    assert admission.inventory_owned(model_engine, ticket, relative) == 22
    admission.finish(model_engine, ticket, 22, relative)
    admission.audit(model_engine, root)
    with model_engine.connect() as connection:
        charge = one(
            connection, "SELECT * FROM v2_data_charges WHERE charge_id=:id", id=ticket["charge_id"]
        )
        assert charge["charged_bytes"] == 22 and charge["state"] == "retained"


@pytest.mark.parametrize("text", ["Run research on Kucoin spot.", "Use DOGEEUR.", "Use 1d bars."])
async def test_unknown_constraints_with_valid_context_create_zero_research_handoffs(
    model_engine, tmp_path, text
):
    base, numerical, copilot, memo, body = await setup(model_engine, tmp_path)
    try:
        body["text"] = text
        identity, _, _ = await copilot.create(body, "unknown-constraint")
        assert await copilot.work(1, identity) == 1
        assert copilot.inspect(identity)["run_id"] is None
        with model_engine.connect() as connection:
            assert execute(connection, "SELECT count(*) FROM v2_research_runs").scalar_one() == 0
    finally:
        await numerical.close()
        await base.close()


async def test_identity_phase_deadline_spends_no_call_and_releases_admission(
    model_engine, tmp_path
):
    base, numerical, copilot, memo, body = await setup(model_engine, tmp_path)
    try:

        async def slow_identity():
            await asyncio.sleep(10)
            return DIGEST

        copilot.model.timeout = 0.01
        copilot.model.identify = slow_identity
        identity, _, _ = await copilot.create(body, "slow-identity")
        assert await asyncio.wait_for(copilot.work(1, identity), 3) == 1
        info = copilot.inspect(identity)
        assert info["state"] == "retry_wait" and info["revisions"][0]["model_calls"] == 0
        async with inference_admission(model_engine) as acquired:
            assert acquired
    finally:
        await numerical.close()
        await base.close()


@pytest.mark.parametrize(
    "old_identity",
    [
        {"source_sha256": "0" * 64},
        {"prompt": "copilot-prompt-v2"},
        {"prompt": "copilot-prompt-v3"},
        {"prompt": "copilot-prompt-v4"},
        {"prompt": "copilot-prompt-v5"},
        {"schema": "copilot-execution-v2"},
        {"grammar": "copilot-evidence-grammar-old"},
        {"semantic": "copilot-semantic-coverage-old"},
    ],
)
async def test_incompatible_pending_copilot_does_not_starve_current_memo(
    model_engine, tmp_path, old_identity
):
    base, numerical, copilot, memo, body = await setup(model_engine, tmp_path)
    try:
        snapshot = copilot.snapshot(body)
        old_execution = dict(copilot.execution, **old_identity)
        identity, _, _ = store.create(model_engine, body, snapshot, old_execution, "incompatible")
        old = store.inspect(model_engine, identity)
        spec = ResearchSpec.create(
            {
                "schema": "research-spec-v2",
                **body["context"],
                "dataset_versions": body["dataset_versions"],
                "parameters": {},
                "predicates": {},
            }
        )
        run, _ = await numerical.submit(spec, "memo-target")
        assert await numerical.work(1, run) == 1
        assert not durable.pending(model_engine, copilot.execution)
        assert await memo.work(1, run) == 1
        assert memo.inspect(run)["state"] == "succeeded"
        assert store.inspect(model_engine, identity) == old
        assert copilot.inspect(identity)["error_code"] == "incompatible_execution"
        compatible, _, _ = await copilot.create(body, "compatible")
        assert durable.pending(model_engine, copilot.execution)
        other, _ = await numerical.submit(spec, "memo-waits")
        assert await numerical.work(1, other) == 1
        assert await memo.work(1, other) == 0
        assert memo.inspect(other)["attempt_count"] == 0
    finally:
        await numerical.close()
        await base.close()


async def test_simultaneous_create_and_answer_are_single_append_operations(model_engine, tmp_path):
    base, numerical, copilot, memo, body = await setup(model_engine, tmp_path)
    try:
        body["context"] = {}
        created = await asyncio.gather(
            *(copilot.create(body, "concurrent-create") for _ in range(2))
        )
        identity = created[0][0]
        assert {c[0] for c in created} == {identity}
        assert sum(not c[2] for c in created) == 1
        assert await copilot.work(1, identity) == 1
        answer = {
            "schema": "copilot-answer-v2",
            "expected_revision": 0,
            "text": "Confirm.",
            "context": {"workflow": "market_profile"},
        }
        outcomes = await asyncio.gather(
            copilot.answer(identity, answer, "first-answer"),
            copilot.answer(identity, answer, "second-answer"),
            return_exceptions=True,
        )
        assert sum(isinstance(v, tuple) for v in outcomes) == 1
        assert sum(isinstance(v, V2Error) and v.code == "revision_conflict" for v in outcomes) == 1
        assert len(store.inspect(model_engine, identity)["revisions"]) == 2
        assert copilot.model.calls == 1
    finally:
        await numerical.close()
        await base.close()


async def test_two_competing_fenced_handoffs_commit_one_run(model_engine, tmp_path):
    base, numerical, copilot, memo, body = await setup(model_engine, tmp_path)
    reservation = None
    try:
        identity, _, _ = await copilot.create(body, "handoff-race")
        current = durable.claim(model_engine, "copilot", copilot.execution, identity)
        info = store.inspect(model_engine, identity)
        value, proof = await copilot.model.interpret(info["snapshot"], [body])
        number = durable.reserve(
            model_engine, current, copilot.model.prepare(info["snapshot"], [body]), DIGEST
        )
        durable.checkpoint(model_engine, current, number, value, proof)
        spec = assemble(supplied(body["context"], info["snapshot"]), info["snapshot"])
        reservation = capacity.reserve(model_engine, numerical.root)
        rows, _ = await numerical.prepare(spec, current.lost, reservation)
        fingerprint = numerical.fingerprint(spec, rows, numerical.execution)

        def publish():
            try:
                return store.finish(model_engine, current, "submitted", [], spec, fingerprint, rows)
            except V2Error as error:
                return error.code

        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: publish(), range(2)))
        assert results.count("revision_conflict") == 1
        with model_engine.connect() as connection:
            assert execute(connection, "SELECT count(*) FROM v2_research_runs").scalar_one() == 1
        assert store.inspect(model_engine, identity)["run_id"] in results
    finally:
        if reservation is not None:
            capacity.release(model_engine, numerical.root, reservation)
        await numerical.close()
        await base.close()


async def test_competing_memo_publishers_fence_and_charge_one_package(model_engine, tmp_path):
    base, numerical, copilot, memo, body = await setup(model_engine, tmp_path)
    ticket = None
    try:
        spec = ResearchSpec.create(
            {
                "schema": "research-spec-v2",
                **body["context"],
                "dataset_versions": body["dataset_versions"],
                "parameters": {},
                "predicates": {},
            }
        )
        run, _ = await numerical.submit(spec, "memo-publish-race")
        assert await numerical.work(1, run) == 1
        current = durable.claim(model_engine, "memo", memo.execution, run)
        summary, _, _ = memo.numerical(run)
        source = facts(summary)
        value, proof = await memo.model.generate(source)
        number = durable.reserve(model_engine, current, memo.model.prepare(source), DIGEST)
        durable.checkpoint(model_engine, current, number, value, proof)
        ticket = admission.acquire(model_engine, numerical.root, "memo", 1024**2, run, 1024**2)
        admission.mark_path(model_engine, ticket, current.relative_path)
        with model_engine.begin() as connection:
            admission.activate(
                connection, ticket, run, attempt=current.attempt, token=current.token
            )
            execute(
                connection,
                "UPDATE v2_memo_attempts SET ticket_id=:ticket,charge_id=:charge "
                "WHERE run_id=:id AND attempt_number=1",
                ticket=ticket["ticket_id"],
                charge=ticket["charge_id"],
                id=run,
            )
        info = memo_store.inspect(model_engine, run)
        path, manifest, size = memo.stage(current, info, source)

        def publish():
            try:
                memo.publish(current, info, path, manifest, size, ticket)
                return "succeeded"
            except V2Error as error:
                return error.code

        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: publish(), range(2)))
        assert sorted(results) == ["revision_conflict", "succeeded"]
        assert memo.read(run)[0] == memo.inspect(run)["memo"]
        with model_engine.connect() as connection:
            assert execute(connection, "SELECT count(*) FROM v2_memo_results").scalar_one() == 1
    finally:
        if ticket is not None:
            admission.complete_legacy(model_engine, ticket)
        await numerical.close()
        await base.close()


async def test_genuine_preexisting_0010_run_enqueues_without_rewriting_numerics(
    browser_engine, tmp_path
):  # noqa: F811
    root = tmp_path / "storage"
    admission.initialize(browser_engine, root)
    version = fixture_version(browser_engine, root, tmp_path)
    base = BarService(browser_engine, root, None)
    numerical = ResearchService(base)
    try:
        value = request()
        spec = ResearchSpec.create(
            {
                "schema": "research-spec-v2",
                **value["context"],
                "instrument_ids": ["binance:spot:BTCUSDT"],
                "dataset_versions": [version],
                "parameters": {},
                "predicates": {},
            }
        )
        run, _ = await numerical.submit(spec, "preexisting-0010")
        assert await numerical.work(1, run) == 1
        before = numerical.read(run, "summary")
        apply_model_migration(browser_engine)
        admission.initialize(browser_engine, root)
        memo = MemoService(numerical, ProtocolMemo())
        result = memo.enqueue(run, {"schema": "memo-request-v2"}, "old-run-enqueue")
        assert result["state"] == "queued" and not result["replayed"]
        assert await memo.work(1, run) == 1
        assert numerical.read(run, "summary") == before
        assert memo.enqueue(run, {"schema": "memo-request-v2"}, "other-key")["replayed"]
    finally:
        await numerical.close()
        await base.close()


async def test_two_spent_calls_are_never_refunded_or_reset(model_engine, tmp_path):
    import httpx

    base, numerical, copilot, memo, body = await setup(model_engine, tmp_path)
    try:

        async def failed_completion(*args, **kwargs):
            copilot.model.calls += 1
            raise httpx.ConnectError("Controlled protocol transport failure")

        copilot.model.interpret = failed_completion
        identity, _, _ = await copilot.create(body, "call-exhaustion")
        assert await copilot.work(1, identity) == 1
        first = store.inspect(model_engine, identity)
        assert first["state"] == "retry_wait" and first["revisions"][0]["model_calls"] == 1
        with model_engine.begin() as connection:
            execute(
                connection,
                "UPDATE v2_copilot_jobs SET eligible_at=clock_timestamp() WHERE request_id=:id",
                id=identity,
            )
        assert await copilot.work(1, identity) == 1
        info = store.inspect(model_engine, identity)
        assert info["state"] == "failed" and info["revisions"][0]["model_calls"] == 2
        assert len(info["revisions"][0]["calls"]) == 2 and copilot.model.calls == 2
        assert await copilot.create(body, "call-exhaustion") == (identity, 0, True)
        assert await copilot.work(1, identity) == 0
        assert store.inspect(model_engine, identity) == info
    finally:
        await numerical.close()
        await base.close()


async def test_legacy_v2_shared_admission_and_legacy_copilot_priority(model_engine, tmp_path):
    from test_copilot import request as legacy_request
    from test_copilot_integration import FakeModel
    from test_research_integration import published

    from marketlab.copilot.service import CopilotService as LegacyCopilot

    base, numerical, copilot, memo, body = await setup(model_engine, tmp_path)
    legacy_research, legacy_spec = published(model_engine, tmp_path)
    active, peak = 0, 0

    class WatchedLegacy(FakeModel):
        async def infer(self, turns, pinned=None):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(0.05)
                return await super().infer(turns, pinned)
            finally:
                active -= 1

    class WatchedV2(ProtocolCopilot):
        async def interpret(self, snapshot, turns, pinned=DIGEST, expected=None):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(0.05)
                return await super().interpret(snapshot, turns, pinned, expected=expected)
            finally:
                active -= 1

    legacy = LegacyCopilot(legacy_research, WatchedLegacy())
    copilot.model = WatchedV2()
    try:
        spec = ResearchSpec.create(
            {
                "schema": "research-spec-v2",
                **body["context"],
                "dataset_versions": body["dataset_versions"],
                "parameters": {},
                "predicates": {},
            }
        )
        run, _ = await numerical.submit(spec, "legacy-priority-memo")
        assert await numerical.work(1, run) == 1
        old_body = legacy_request()
        old_body["dataset_versions"] = list(legacy_spec.dataset_versions)
        old_id, _, _ = await legacy.create(old_body, "legacy-priority")
        assert await memo.work(1, run) == 0
        assert memo.inspect(run)["attempt_count"] == 0
        assert await legacy.work(1, old_id) == 1
        second_old, _, _ = await legacy.create(old_body, "legacy-overlap")
        current, _, _ = await copilot.create(body, "v2-overlap")
        await asyncio.gather(legacy.work(1, second_old), copilot.work(1, current))
        await legacy.work(1, second_old)
        await copilot.work(1, current)
        assert legacy.inspect(second_old)["outcome"] == "submitted"
        assert copilot.inspect(current)["outcome"] == "submitted"
        assert peak == 1 and active == 0
        assert legacy.model.calls == 2 and copilot.model.calls == 1
    finally:
        await legacy_research.close()
        await legacy_research.bars.close()
        await numerical.close()
        await base.close()
