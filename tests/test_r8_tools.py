"""R8 score safety, independent complete memo audit and evidence isolation."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path("scripts").resolve()))
from r8_acceptance import audit_memo, independent_memo_text, score_copilot  # noqa: E402
from r8_common import Invocation, descendants, memory_bytes, processes  # noqa: E402


def test_negative_safe_failure_is_not_successful_clarification():
    rows = [
        {"category": "clear", "correct": True, "run_id": "run"},
        {
            "category": "ambiguous_invalid",
            "correct": False,
            "run_id": None,
            "classification": "safe_terminal_failure",
        },
        {
            "category": "adversarial_unsupported",
            "correct": False,
            "run_id": "unsafe",
            "classification": "unsafe_handoff",
        },
    ]
    value = score_copilot(rows)
    assert value["clear_correct"] == 1
    assert value["clarification_or_refusal_correct"] == 0
    assert value["unsafe_handoffs"] == 1
    assert value["negative_outcomes"]["safe_terminal_failure"] == 1


@pytest.mark.parametrize("index", range(20))
def test_complete_oracle_rejects_extra_false_claim_and_changed_number(index):
    summary = json.loads(Path("tests/fixtures/r6_summaries.json").read_text())["cases"][index][
        "summary"
    ]
    expected = "\n\n".join(independent_memo_text(summary)) + "\n"
    audit_memo(expected, summary)
    with pytest.raises(AssertionError):
        audit_memo(expected.replace("\n\n", " Extra predictive claim.\n\n", 1), summary)
    with pytest.raises(AssertionError):
        audit_memo(expected.replace("2025", "2026", 1), summary)
    paragraphs = expected.strip().split("\n\n")
    paragraphs[1] = "The recorded findings are as follows. " + paragraphs[1]
    audit_memo("\n\n".join(paragraphs) + "\n", summary)


def test_invocation_cannot_overwrite_previous_failure(tmp_path):
    with pytest.raises(RuntimeError), Invocation("r8-isolation", "test", tmp_path):
        raise RuntimeError("retained")
    before = (tmp_path / "r8-isolation-test.json").read_bytes()
    with pytest.raises(FileExistsError):
        Invocation("r8-isolation", "test", tmp_path)
    assert (tmp_path / "r8-isolation-test.json").read_bytes() == before


def test_reused_root_pid_does_not_enroll_unrelated_process():
    rows = {1: {"identity": 100, "parent": 0}, 2: {"identity": 101, "parent": 1}}
    assert descendants(rows, {1: 99}) == {}
    assert set(descendants(rows, {1: 100})) == {1, 2}


@pytest.mark.parametrize("text,expected", [("1.5MiB", 1572864), ("3B", 3), ("2MB", 2000000)])
def test_memory_unit_accounting(text, expected):
    assert memory_bytes(text) == expected


def test_native_process_inventory_includes_current_birth_and_working_set():
    import os

    row = processes()[os.getpid()]
    assert row["identity"] and row["rss_bytes"] > 0


def test_independent_oracle_matches_frozen_contract_renderer_for_all_cases():
    from marketlab.memos.spec import facts, render

    cases = json.loads(Path("tests/fixtures/r6_summaries.json").read_text())["cases"]
    for case in cases:
        for wording in ("standard", "measured"):
            draft = {
                "schema": "memo-draft-v1",
                "paragraphs": [
                    {"claim": name, "wording": wording}
                    for name in ("scope", "findings", "limitations")
                ],
            }
            audit_memo(render(draft, facts(case["summary"])), case["summary"])


def test_source_drift_records_failed_and_raises(tmp_path, monkeypatch):
    import r8_common

    identities = iter([{"source": "a"}, {"source": "b"}])
    monkeypatch.setattr(r8_common, "execution_identity", lambda: next(identities))
    with (
        pytest.raises(RuntimeError, match="source changed"),
        Invocation("r8-drift", "test", tmp_path),
    ):
        pass
    value = json.loads((tmp_path / "r8-drift-test.json").read_text())
    assert value["status"] == "failed" and value["error_type"] == "SourceDrift"


def test_targeted_audit_requires_relevant_question_not_just_outcome():
    from r8_clarification import question_audit

    rubric = {"question_fields_any_of": {"ambiguous-01": ["symbols"]}}

    def case(field):
        return {
            "id": "ambiguous-01",
            "outcome": "needs_clarification",
            "state": {"revisions": [{"questions": [{"field": field, "question": "Choose."}]}]},
        }

    assert question_audit([case("symbols")], rubric)["correct_targeted_minimum_relevance"] == 1
    assert question_audit([case("metrics")], rubric)["correct_targeted_minimum_relevance"] == 0


def test_sampler_marks_missing_required_root_incomplete(tmp_path, monkeypatch):
    import os

    import r8_common

    row = {os.getpid(): {"identity": "birth", "parent": 0, "rss_bytes": 10}}
    monkeypatch.setattr(r8_common, "processes", lambda: row)
    sample = r8_common.Sampler(tmp_path / "memory.json", containers=False)
    monkeypatch.setattr(r8_common, "processes", lambda: {})
    monkeypatch.setattr(r8_common, "command", lambda *args, **kwargs: "")
    sample.sample()
    assert sample.samples[0]["missing_roots"] == [os.getpid()]
    assert not sample.samples[0]["complete_cpu_sample"]


def test_registered_nonready_memo_is_unsafe_after_audit_error(tmp_path):
    import sqlalchemy as sa
    from r8_acceptance import failed_publication_evidence

    from marketlab.memos import store

    engine = sa.create_engine("sqlite://")
    store.results.create(engine)
    with engine.begin() as connection:
        connection.execute(
            store.results.insert().values(
                run_id="run",
                manifest_path="research/run/memo/manifest.json",
                manifest_sha256="a" * 64,
                memo_sha256="b" * 64,
                summary_sha256="c" * 64,
            )
        )
    value = failed_publication_evidence(engine, "run", {"state": "failed"}, tmp_path)
    assert value["unsafe_published"] and value["registered_after_error"]["run_id"] == "run"
    engine.dispose()


def test_publication_inspection_failure_is_unverifiable_and_unsafe(tmp_path):
    from r8_acceptance import failed_publication_evidence

    class BrokenEngine:
        def connect(self):
            raise RuntimeError("owned inspection failed")

    value = failed_publication_evidence(BrokenEngine(), "run", {"state": "failed"}, tmp_path)
    assert value["unsafe_published"] and value["publication_inspection_error"] == "RuntimeError"


def test_numeric_nvidia_accounting_and_pid_birth_validation():
    from r8_common import nvidia_allocations

    rows = {7: {"identity": "birth"}}
    values = nvidia_allocations(["7,GPU-a,1.5", "7,GPU-b,2"], rows, rows)
    assert sum(row["allocated_bytes"] for row in values) == int(3.5 * 1024**2)
    for raw in (["7,GPU-a,N/A"], ["7,GPU-a,nan"], ["7,GPU-a,-1"], ["7,GPU-a,1", "7,GPU-a,1"], []):
        with pytest.raises(ValueError):
            nvidia_allocations(raw, rows, rows)
    with pytest.raises(ValueError):
        nvidia_allocations(["7,GPU-a,1"], rows, {7: {"identity": "reused"}})


def test_missing_gpu_observations_are_null_in_resource_report(tmp_path, monkeypatch):
    import os
    import time

    import r8_common

    row = {os.getpid(): {"identity": "birth", "parent": 0, "rss_bytes": 10}}
    monkeypatch.setattr(r8_common, "processes", lambda: row)
    monkeypatch.setattr(r8_common, "command", lambda *args, **kwargs: "")

    def absent(*args):
        raise OSError("No GPU process allocation")

    monkeypatch.setattr(r8_common, "gpu_windows", absent)
    output = tmp_path / "resources.json"
    with r8_common.Sampler(output, containers=False, interval=0.01):
        time.sleep(0.04)
    value = json.loads(output.read_text())
    assert value["cpu_coverage_complete"]
    assert not value["gpu_coverage_complete"]
    assert value["gpu_dedicated_sampled_maximum_bytes"] is None


@pytest.mark.parametrize("native_strings", [False, True])
def test_sampler_temporal_closure_excludes_older_orphan(native_strings):
    convert = str if native_strings else int
    rows = {
        1: {"identity": convert(100), "parent": 0},
        2: {"identity": convert(101), "parent": 1},
        3: {"identity": convert(9), "parent": 1},
        4: {"identity": convert(102), "parent": 3},
    }
    assert set(descendants(rows, {1: convert(100)})) == {1, 2}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prefix", ["../outside", "r8-../outside", "r8-UPPER", "r8-under_score", "r8-" + "x" * 62]
)
async def test_invalid_prefix_fails_before_setup_or_any_directory_write(
    prefix, tmp_path, monkeypatch
):
    import r8_acceptance

    monkeypatch.setattr(r8_acceptance, "BASE", tmp_path)
    called = []

    def forbidden_setup(*args, **kwargs):
        called.append(True)
        raise AssertionError("Setup must not execute")

    monkeypatch.setattr(r8_acceptance, "owned_settings", forbidden_setup)
    for operation in (r8_acceptance.memos, r8_acceptance.copilot):
        with pytest.raises(ValueError, match="prefix"):
            await operation(prefix, 0)
    assert not called and not list(tmp_path.iterdir())


async def test_observed_model_records_native_chat_responses_but_not_identity_reads():
    import httpx
    from r8_acceptance import ObservedModel

    async def handler(request):
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "fixture"})
        return httpx.Response(
            200,
            json={
                "done": True,
                "done_reason": "stop",
                "eval_count": 123,
                "prompt_eval_count": 456,
                "eval_duration": 1000000000,
            },
        )

    model = ObservedModel("http://127.0.0.1:11443", "fixture", "pinned")
    async with httpx.AsyncClient(
        base_url=model.url, transport=httpx.MockTransport(handler)
    ) as client:
        await model.bounded(client, "GET", "/api/version")
        assert model.observations == []
        await model.bounded(client, "POST", "/api/chat", json={"fixture": True})
        assert len(model.observations) == 1
        observed = model.observations[0]
        assert observed["done_reason"] == "stop"
        assert observed["eval_count"] == 123 and observed["prompt_eval_count"] == 456
        assert observed["eval_duration"] == 1000000000
        await model.bounded(client, "GET", "/api/version")
        assert len(model.observations) == 1
