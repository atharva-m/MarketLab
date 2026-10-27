"""Independent targeted-question audit and actual R8 clarification continuations."""

import argparse
import asyncio
import json
import time
from pathlib import Path

import sqlalchemy as sa
from prometheus_client import CollectorRegistry
from r5_acceptance import expected_spec, finish_copilot, restore
from r8_acceptance import ObservedModel
from r8_common import (
    BASE,
    DIGEST,
    MODEL,
    ROOT,
    Invocation,
    Sampler,
    engine_for,
    owned_settings,
    validate_prefix,
)

from marketlab.analytics.bars import BarService
from marketlab.copilot.service import CopilotService
from marketlab.datasets.source import file_hash
from marketlab.research import store as research_store
from marketlab.research.service import ResearchService
from marketlab.research.spec import ResearchError

FIXTURE = Path("tests/fixtures/r8_clarifications.json")


def question_audit(cases: list[dict], rubric: dict) -> dict:
    """Measure relevant targeted fields, separately from mere outcome accuracy.

    The frozen rubric is a minimum relevance test, not unrestricted assessment of
    all possible omissions. Every question must name a known field and have
    nonempty wording; this is not a linguistic quality oracle. The denominator
    includes every ambiguous corpus case.
    """
    fields = {
        "workflow",
        "symbols",
        "start",
        "end",
        "history_start",
        "interval",
        "metrics",
        "meaning",
        "coverage",
    }
    results = []
    for row in cases:
        if row["id"] not in rubric["question_fields_any_of"]:
            continue
        revision = row["state"]["revisions"][-1]
        questions = revision.get("questions") or []
        observed = {question.get("field") for question in questions}
        shaped = all(
            set(question) == {"field", "question"}
            and question["field"] in fields
            and isinstance(question["question"], str)
            and bool(question["question"].strip())
            for question in questions
        )
        relevant = bool(observed & set(rubric["question_fields_any_of"][row["id"]]))
        passed = row["outcome"] == "needs_clarification" and shaped and relevant
        results.append(
            {
                "id": row["id"],
                "outcome": row["outcome"],
                "targeted_relevant": passed,
                "question_fields": sorted(observed),
                "rubric_any_of": rubric["question_fields_any_of"][row["id"]],
            }
        )
    return {
        "correct_targeted_minimum_relevance": sum(row["targeted_relevant"] for row in results),
        "denominator": len(results),
        "method": "Frozen minimum relevant-question-field alternatives; safe failures remain in denominator. Does not claim exhaustive natural-language question quality.",  # noqa: E501
        "cases": results,
    }


def audit(prefix: str, campaign: Path) -> None:
    prefix = validate_prefix(prefix)
    value = json.loads(campaign.read_text(encoding="utf-8-sig"))
    rubric = json.loads(FIXTURE.read_text(encoding="utf-8-sig"))
    with Invocation(prefix, "question-audit") as evidence:
        evidence.data.update(
            campaign=str(campaign),
            campaign_sha256=file_hash(campaign),
            rubric_sha256=file_hash(FIXTURE),
            script_sha256=file_hash(Path(__file__)),
            **question_audit(value["cases"], rubric),
        )
        assert evidence.data["denominator"] == 20


async def continuations(prefix: str) -> None:
    prefix = validate_prefix(prefix)
    rubric = json.loads(await asyncio.to_thread(FIXTURE.read_text, encoding="utf-8-sig"))
    settings = owned_settings()
    engine = engine_for(settings)
    registry = CollectorRegistry()
    bars = BarService(engine, ROOT, settings.redis_url.get_secret_value(), registry=registry)
    research = ResearchService(bars)
    model = ObservedModel(settings.ollama_url, MODEL, DIGEST)
    service = CopilotService(research, model, registry)
    try:
        records = await asyncio.to_thread(restore, engine)
        with (
            Invocation(prefix, "continuations") as evidence,
            Sampler(BASE / f"{prefix}-continuation-resources.json", model=True),
        ):
            evidence.data.update(
                fixture_sha256=file_hash(FIXTURE),
                script_sha256=file_hash(Path(__file__)),
                resource_evidence=str(BASE / f"{prefix}-continuation-resources.json"),
            )
            for case in rubric["continuations"]:
                began = time.monotonic()
                observations_before = len(model.observations)
                request = {
                    "schema": "copilot-request-v1",
                    **rubric["initial"],
                    "dataset_versions": sorted(row["dataset_version_id"] for row in records),
                }
                request_id, _, _ = await service.create(request, f"{prefix}-{case['id']}")
                initial = await finish_copilot(service, request_id)
                item = {
                    "id": case["id"],
                    "kind": case["kind"],
                    "initial": initial,
                    "steps": [],
                    "protocol_checks": [],
                    "valid": False,
                }
                try:
                    assert initial["outcome"] == "needs_clarification", (
                        "Initial safely terminal outcome is not answerable; no state forced"
                    )
                    state = initial
                    rounds = 5 if case["kind"] == "round_limit" else 1
                    for index in range(rounds):
                        assert state["outcome"] == "needs_clarification", (
                            "Round bound not reached because earlier outcome terminal"
                        )
                        answer = {
                            "schema": "copilot-answer-v1",
                            "expected_revision": index,
                            "text": case["answer_text"],
                            "context": case["answer_context"],
                        }
                        key = f"{prefix}-{case['id']}-answer-{index}"
                        identity = await service.answer(request_id, answer, key)
                        assert identity == (request_id, index + 1, False)
                        replay_before = await asyncio.to_thread(service.inspect, request_id)
                        responses_before_replay = len(model.observations)
                        replay = await service.answer(request_id, answer, key)
                        assert replay == (request_id, index + 1, True)
                        assert replay_before == await asyncio.to_thread(service.inspect, request_id)
                        assert len(model.observations) == responses_before_replay
                        item["protocol_checks"].append(
                            {
                                "revision": index + 1,
                                "accepted": identity,
                                "replay": replay,
                                "state_unchanged": True,
                            }
                        )
                        for conflict, conflict_key in (
                            ({**answer, "text": "Different body"}, key),
                            (answer, key + "-stale"),
                        ):
                            rejection_before = await asyncio.to_thread(service.inspect, request_id)
                            responses_before_rejection = len(model.observations)
                            try:
                                await service.answer(request_id, conflict, conflict_key)
                            except ResearchError as error:
                                assert error.status == 409
                                assert len(model.observations) == responses_before_rejection
                                assert rejection_before == await asyncio.to_thread(
                                    service.inspect, request_id
                                )
                                item["protocol_checks"].append(
                                    {
                                        "key": conflict_key,
                                        "status": error.status,
                                        "state_unchanged": True,
                                    }
                                )
                            else:
                                raise AssertionError("Conflicting or stale answer accepted")
                        state = await finish_copilot(service, request_id)
                        item["steps"].append(state)
                        if case["kind"] == "valid":
                            intent = {**rubric["initial"]["context"], **case["answer_context"]}
                            assert state["outcome"] == "submitted" and state["revisions"][-1][
                                "spec"
                            ] == expected_spec(intent, records)
                        elif case["kind"] == "round_limit":
                            assert (
                                state["run_id"] is None
                                and state["outcome"] == "needs_clarification"
                            )
                        else:
                            assert (
                                state["run_id"] is None
                                and state["outcome"] in case["expected_outcomes"]
                            )
                    if case["kind"] == "round_limit":
                        assert state["current_revision"] == 5 and len(state["revisions"]) == 6
                        assert all(
                            row["state"] == "completed" and row["model_calls"] >= 1
                            for row in state["revisions"]
                        )
                        # Native public parsing accepts expected_revision0..4. The proper
                        # sixth payload is422; a valid-shaped stale4 is409 at current5.
                        for expected_revision, expected_status, suffix in (
                            (5, 422, "sixth"),
                            (4, 409, "sixth-stale-valid-shape"),
                        ):
                            before = await asyncio.to_thread(service.inspect, request_id)
                            responses_before_boundary = len(model.observations)
                            try:
                                await service.answer(
                                    request_id,
                                    {**answer, "expected_revision": expected_revision},
                                    key + "-" + suffix,
                                )
                            except ResearchError as error:
                                assert error.status == expected_status
                            else:
                                raise AssertionError("Sixth answer accepted")
                            assert before == await asyncio.to_thread(service.inspect, request_id)
                            assert len(model.observations) == responses_before_boundary
                            item["protocol_checks"].append(
                                {
                                    "probe": suffix,
                                    "expected_revision": expected_revision,
                                    "status": expected_status,
                                    "state_unchanged": True,
                                }
                            )
                    with engine.connect() as connection:
                        count = connection.scalar(
                            sa.select(sa.func.count())
                            .select_from(research_store.submissions)
                            .where(
                                research_store.submissions.c.idempotency_key
                                == "copilot." + request_id
                            )
                        )
                    assert count == int(state["run_id"] is not None)
                    reserved_calls = sum(row["model_calls"] for row in state["revisions"])
                    assert len(model.observations) - observations_before == reserved_calls
                    item.update(valid=True, final=state, reserved_model_calls=reserved_calls)
                except Exception as error:
                    item.update(error_type=type(error).__name__, error=str(error))
                item["completed_model_responses"] = len(model.observations) - observations_before
                item["runtime_counters"] = model.observations[observations_before:]
                item["seconds"] = time.monotonic() - began
                evidence.data["cases"].append(item)
                evidence.flush()
                print(
                    json.dumps(
                        {"id": case["id"], "valid": item["valid"], "seconds": item["seconds"]}
                    ),
                    flush=True,
                )
            assert all(item["valid"] for item in evidence.data["cases"]), (
                "Clarification continuation gate incomplete/failed"
            )
    finally:
        await research.close()
        await bars.close()
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("audit", "continuations"))
    parser.add_argument("--prefix", required=True, type=validate_prefix)
    parser.add_argument("--campaign", type=Path)
    args = parser.parse_args()
    if args.phase == "audit":
        if args.campaign is None:
            parser.error("audit requires --campaign")
        audit(args.prefix, args.campaign)
    else:
        asyncio.run(continuations(args.prefix))


if __name__ == "__main__":
    main()
