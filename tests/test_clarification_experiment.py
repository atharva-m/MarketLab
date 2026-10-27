"""Experiment scoring must distinguish useful clarification from safe rejection."""

import asyncio
import copy
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path("scripts").resolve()))
import clarification_experiment as experiment


def expected(case):
    supplied = dict(case["turns"][0]["context"])
    if case["complete"]:
        supplied["symbols"] = ["BTCUSDT"]
    return {
        "schema": "copilot-interpretation-v1",
        "outcome": "candidate" if case["complete"] else "needs_clarification",
        "intent": {key: supplied.get(key) for key in experiment.FIELD_ORDER},
        "evidence": {key: "context" if key in supplied else None for key in experiment.FIELD_ORDER},
        "unresolved": [] if case["complete"] else ["symbols"],
        "reason": "none" if case["complete"] else "missing_fields",
    }


def test_null_asset_clarification_passes_retained_validator_without_executable_candidate():
    case = experiment.cases()[0]
    value = expected(case)
    result = experiment.score(value, case)
    assert result["combined_success"]
    assert result["semantic_outcome"] == "needs_clarification"
    assert result["semantic_unresolved"] == ["symbols"]
    assert "symbols" not in result["semantic_grounded"]
    assert value["intent"]["symbols"] is None


def test_complete_answer_preserves_context_and_exact_symbol():
    case = experiment.cases()[1]
    result = experiment.score(expected(case), case)
    assert result["combined_success"]
    assert result["semantic_outcome"] == "candidate"
    assert result["semantic_grounded"]["symbols"] == ["BTCUSDT"]


def test_historical_unsupported_symbol_choice_is_rejected_not_counted_as_clarification():
    case = experiment.cases()[0]
    value = expected(case)
    value["intent"]["symbols"] = ["BTCUSDT", "ETHUSDT"]
    value.update(outcome="candidate", reason="none", unresolved=[])
    result = experiment.score(value, case)
    assert not result["combined_success"]
    assert not result["validator_accepted"]
    assert result["semantic_outcome"] is None
    assert result["cross_section_errors"] == ["intent_evidence_null_mismatch:symbols"]


def test_each_split_projects_disjoint_complete_schema_and_preserves_full_history():
    case = experiment.cases()[-1]
    for arm, count in (("split_two", 2), ("split_three", 3)):
        payloads = experiment.payloads(arm, case["turns"])
        assert len(payloads) == count
        fields = [set(payload["format"]["required"]) for payload in payloads]
        assert set.union(*fields) == {
            "schema",
            "outcome",
            "intent",
            "evidence",
            "unresolved",
            "reason",
        }
        assert sum(len(field) for field in fields) == 6
        for payload in payloads:
            assert json.loads(payload["messages"][1]["content"]) == case["turns"]
            assert not payload["think"]


def test_schema_rejects_missing_extra_and_unsupported_evidence():
    case = experiment.cases()[0]
    payload = experiment.payloads("original_false", case["turns"])[0]
    value = expected(case)
    assert not experiment.schema_errors(value, payload["format"])
    bad = copy.deepcopy(value)
    bad["evidence"]["symbols"] = "made up"
    assert experiment.schema_errors(bad, payload["format"])
    del bad["intent"]["end"]
    bad["extra"] = True
    errors = experiment.schema_errors(bad, payload["format"])
    assert "$.intent:missing:end" in errors and "$:extra:extra" in errors


def test_summary_includes_failed_group_without_crashing_or_credit():
    row = {
        "arm": "original_true",
        "score": None,
        "all_sections_valid": False,
        "seconds": 120,
        "http_intervals_overlap": False,
    }
    result = experiment.summary([row])["original_true"]
    assert result["groups"] == 1 and result["invalid_or_failed_groups"] == 1
    assert result["combined_success"] == result["semantic_expected_met"] == 0


@pytest.mark.parametrize("prefix", ["../escape", "clarify-../escape", "CLARIFY-a", "clarify-"])
def test_evidence_prefix_cannot_escape_owned_directory(prefix):
    with pytest.raises(ValueError):
        experiment.directory(prefix)


@pytest.mark.parametrize(
    "url", ["http://example.com:11442", "http://u:p@127.0.0.1:11442", "http://127.0.0.1:11442/x"]
)
def test_only_explicit_loopback_endpoint_allowed(url):
    with pytest.raises(ValueError):
        experiment.endpoint(url)


async def test_concurrent_calls_retain_both_completions_and_native_counters(tmp_path):
    arrived = 0
    both = asyncio.Event()
    case = experiment.cases()[0]
    payloads = experiment.payloads("split_two", case["turns"])
    value = expected(case)

    async def handle(request):
        nonlocal arrived
        arrived += 1
        if arrived == 2:
            both.set()
        await asyncio.wait_for(both.wait(), timeout=1)
        sent = json.loads(request.content)
        selected = {key: value[key] for key in sent["format"]["required"]}
        return httpx.Response(
            200,
            json={
                "done": True,
                "done_reason": "stop",
                "eval_count": 42,
                "message": {"content": json.dumps(selected), "thinking": "internal fixture"},
            },
        )

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:11442", transport=httpx.MockTransport(handle)
    ) as client:
        rows = await asyncio.gather(
            *[
                experiment.call(client, payload, tmp_path / f"call-{index}.json")
                for index, payload in enumerate(payloads)
            ]
        )
    assert all(row["success"] for row in rows)
    assert max(row["started_monotonic"] for row in rows) < min(
        row["ended_monotonic"] for row in rows
    )
    assert all(row["response"]["eval_count"] == 42 for row in rows)
    assert all(row["thinking_bytes"] > 0 for row in rows)


async def test_truncated_thinking_response_retained_but_not_scored_valid(tmp_path):
    async def handle(request):
        return httpx.Response(
            200,
            json={
                "done": True,
                "done_reason": "length",
                "message": {"content": "{}", "thinking": "truncated fixture"},
            },
        )

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:11442", transport=httpx.MockTransport(handle)
    ) as client:
        row = await experiment.call(
            client,
            experiment.payloads("original_true", experiment.cases()[0]["turns"])[0],
            tmp_path / "call.json",
        )
    assert not row["success"]
    assert row["response"]["done_reason"] == "length"
    assert "truncated" in row["error"]


def test_thinking_only_plan_has_27_single_calls_without_old_token_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(experiment, "BASE", tmp_path)
    monkeypatch.setattr(experiment, "execution_identity", lambda: {"source": "fixture"})
    experiment.prepare(
        "clarify-thinking-profile-test", "http://127.0.0.1:11442", thinking_only=True
    )
    plan = json.loads((tmp_path / "clarify-thinking-profile-test" / "plan.json").read_text())
    assert plan["profile"] == "thinking-unlimited"
    assert plan["request_deadline_seconds"] == 1800
    assert len(plan["groups"]) == 27
    assert {group["arm"] for group in plan["groups"]} == {"original_true"}
    assert {group["repetition"] for group in plan["groups"]} == {1, 2, 3}
    for group in plan["groups"]:
        assert len(group["payloads"]) == 1
        payload = group["payloads"][0]
        assert payload["think"] is True
        assert payload["options"] == {"temperature": 0, "num_ctx": 8192, "num_predict": -1}
        assert payload["messages"][0]["content"] == experiment.PROMPT


async def test_explicit_watchdog_remains_finite_and_retains_timeout(tmp_path):
    async def handle(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:11442", transport=httpx.MockTransport(handle)
    ) as client:
        row = await experiment.call(
            client,
            experiment.payloads("original_true", experiment.cases()[0]["turns"])[0],
            tmp_path / "timeout.json",
            deadline=0.01,
        )
    assert row["success"] is False and row["error_type"] == "TimeoutError"


def test_9b_profile_has_27_single_non_thinking_calls_with_exact_plan_identity(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(experiment, "BASE", tmp_path)
    monkeypatch.setattr(experiment, "execution_identity", lambda: {"source": "fixture"})
    pinned = "9" * 64
    experiment.prepare(
        "clarify-nine-b-profile-test", "http://127.0.0.1:11442", nine_b_digest=pinned
    )
    plan = json.loads((tmp_path / "clarify-nine-b-profile-test" / "plan.json").read_text())
    assert plan["profile"] == "9b-no-thinking"
    assert plan["request_deadline_seconds"] == 1800
    assert plan["model"] == "qwen3.5:9b-q4_K_M" and plan["digest"] == pinned
    assert len(plan["groups"]) == 27
    assert {group["arm"] for group in plan["groups"]} == {"original_false"}
    for group in plan["groups"]:
        assert len(group["payloads"]) == 1
        payload = group["payloads"][0]
        assert payload["think"] is False and payload["model"] == plan["model"]
        assert payload["options"] == {"temperature": 0, "num_ctx": 8192, "num_predict": -1}
        assert payload["messages"][0]["content"] == experiment.PROMPT


@pytest.mark.parametrize("digest", ["", "short", "G" * 64, "../escape"])
def test_9b_requires_valid_digest_before_creating_evidence(tmp_path, monkeypatch, digest):
    monkeypatch.setattr(experiment, "BASE", tmp_path)
    with pytest.raises(ValueError):
        experiment.prepare("clarify-bad-nine-b", "http://127.0.0.1:11442", nine_b_digest=digest)
    assert not (tmp_path / "clarify-bad-nine-b").exists()


async def test_model_identification_uses_pinned_plan_model_and_digest_without_pull():
    requests = []
    pinned = "9" * 64

    async def handle(request):
        requests.append((request.method, request.url.path))
        data = (
            {"version": "fixture"}
            if request.url.path == "/api/version"
            else {
                "models": [
                    {"name": experiment.MODEL, "digest": experiment.DIGEST},
                    {"name": experiment.MODEL_9B, "digest": pinned},
                ]
            }
        )
        return httpx.Response(200, json=data)

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:11442", transport=httpx.MockTransport(handle)
    ) as client:
        result = await experiment.identify(client, experiment.MODEL_9B, pinned)
        assert result["model_digest"] == pinned
        with pytest.raises(RuntimeError, match="identity mismatch"):
            await experiment.identify(client, experiment.MODEL_9B, "0" * 64)
    assert all(method == "GET" for method, path in requests)
    assert {path for method, path in requests} == {"/api/version", "/api/tags"}


def test_user_supplied_prompt_is_verbatim_including_boundary_newlines():
    assert experiment.USER_PROMPT.startswith("\nYou are a strict research-request interpreter.\n")
    assert experiment.USER_PROMPT.endswith("Return JSON only.\n")
    assert (
        experiment.sha(experiment.USER_PROMPT.encode())
        == "0c3146b2fef64bd9890599cc41d1b417ce6c7bb1325639144089c4c0aeb0701b"
    )


def test_user_prompt_profile_changes_only_system_prompt_and_keeps_27_pinned_9b_calls(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(experiment, "BASE", tmp_path)
    monkeypatch.setattr(experiment, "execution_identity", lambda: {"source": "fixture"})
    pinned = "9" * 64
    experiment.prepare(
        "clarify-user-prompt-test", "http://127.0.0.1:11442", nine_b_digest=pinned, user_prompt=True
    )
    plan = json.loads((tmp_path / "clarify-user-prompt-test" / "plan.json").read_text())
    assert plan["profile"] == "9b-user-prompt" and len(plan["groups"]) == 27
    assert (
        plan["user_prompt_sha256"]
        == "0c3146b2fef64bd9890599cc41d1b417ce6c7bb1325639144089c4c0aeb0701b"
    )
    assert plan["model"] == experiment.MODEL_9B and plan["digest"] == pinned
    assert plan["request_deadline_seconds"] == 1800
    for group in plan["groups"]:
        assert group["arm"] == "original_false" and len(group["payloads"]) == 1
        payload = group["payloads"][0]
        assert payload["messages"][0]["content"] == experiment.USER_PROMPT
        original = experiment.payloads("original_false", group["case"]["turns"])[0]
        assert payload["messages"][1] == original["messages"][1]
        assert payload["format"] == original["format"]
        assert payload["think"] is False and payload["model"] == experiment.MODEL_9B
        assert payload["options"] == {"temperature": 0, "num_ctx": 8192, "num_predict": -1}


def test_user_prompt_requires_explicit_9b_identity_before_creating_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(experiment, "BASE", tmp_path)
    with pytest.raises(ValueError, match="requires the pinned9B"):
        experiment.prepare("clarify-user-prompt-no-pin", "http://127.0.0.1:11442", user_prompt=True)
    assert not (tmp_path / "clarify-user-prompt-no-pin").exists()


def test_null_guard_prompt_is_exactly_one_added_line_and_preserves_user_prompt_bytes():
    expected = (
        "Candidate is forbidden if any required intent field (workflow, symbols, start, end, "
        "history_start, interval, metrics) is null."
    )
    assert experiment.NULL_GUARD_LINE == expected
    assert experiment.NULL_GUARD_PROMPT.count(expected) == 1
    assert experiment.NULL_GUARD_PROMPT.replace(expected + "\n", "", 1) == experiment.USER_PROMPT
    assert expected + "\nFor candidate: unresolved must be []." in experiment.NULL_GUARD_PROMPT
    assert (
        experiment.sha(experiment.NULL_GUARD_PROMPT.encode())
        == "b5b297d29febdcc29e0dde8e845b52bb46568e6843be6a8004ffa39a6c2596c7"
    )


def test_null_guard_profile_keeps_27_pinned_non_thinking_requests_identical_except_system_prompt(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(experiment, "BASE", tmp_path)
    monkeypatch.setattr(experiment, "execution_identity", lambda: {"source": "fixture"})
    pinned = "9" * 64
    experiment.prepare(
        "clarify-base-user-profile",
        "http://127.0.0.1:11442",
        nine_b_digest=pinned,
        user_prompt=True,
    )
    experiment.prepare(
        "clarify-null-guard-profile",
        "http://127.0.0.1:11442",
        nine_b_digest=pinned,
        null_guard=True,
    )
    original = json.loads((tmp_path / "clarify-base-user-profile" / "plan.json").read_text())
    plan = json.loads((tmp_path / "clarify-null-guard-profile" / "plan.json").read_text())
    assert plan["profile"] == "9b-null-guard" and len(plan["groups"]) == 27
    assert (
        plan["user_prompt_sha256"]
        == "b5b297d29febdcc29e0dde8e845b52bb46568e6843be6a8004ffa39a6c2596c7"
    )
    assert plan["base_user_prompt_sha256"] == original["user_prompt_sha256"]
    assert plan["inserted_rule"] == experiment.NULL_GUARD_LINE
    assert plan["model"] == experiment.MODEL_9B and plan["digest"] == pinned
    assert plan["request_deadline_seconds"] == 1800
    for old, new in zip(original["groups"], plan["groups"], strict=True):
        assert new["arm"] == "original_false" and new["case"] == old["case"]
        assert new["repetition"] == old["repetition"]
        assert len(new["payloads"]) == 1
        expected_payload = copy.deepcopy(old["payloads"][0])
        expected_payload["messages"][0]["content"] = experiment.NULL_GUARD_PROMPT
        assert new["payloads"][0] == expected_payload


def test_null_guard_requires_9b_pin_before_evidence_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(experiment, "BASE", tmp_path)
    with pytest.raises(ValueError):
        experiment.prepare("clarify-null-guard-no-pin", "http://127.0.0.1:11442", null_guard=True)
    assert not (tmp_path / "clarify-null-guard-no-pin").exists()
