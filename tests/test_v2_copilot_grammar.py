"""Request-specific source proofs and protocol identities; no actual inference."""

import copy
import hashlib
import importlib.util
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_v2_copilot import candidate, request, selection

from marketlab.copilot.model import ModelFailure
from marketlab.copilot.v2 import durable
from marketlab.copilot.v2.model import (
    DIGEST,
    PROMPT,
    CopilotModel,
    copilot_versions,
    execution,
)
from marketlab.copilot.v2.spec import (
    FIELDS,
    GRAMMAR_VERSION,
    SEMANTIC_VERSION,
    _quoted_value,
    decide,
    evidence_options,
    model_schema,
)
from marketlab.datasets.v2.common import V2Error, canonical_json, digest


def two_selected():
    snapshot = selection("BTCUSDT", base="BTC")
    snapshot["instruments"]["i1"] = {
        "instrument_id": "binance:spot:SOLUSDT",
        "source_symbol": "SOLUSDT",
        "base_asset": "SOL",
        "quote_asset": "USDT",
    }
    return snapshot


def test_grammar_context_is_named_actual_and_never_selection_metadata():
    snapshot = selection()
    turns = [{"text": "Please run research.", "context": {"interval": "5m"}}]
    proofs = evidence_options(snapshot, turns)
    assert proofs["interval"] == [None, {"turn": 0, "context": True}]
    assert all(proofs[name] == [None] for name in FIELDS if name != "interval")
    grammar = model_schema(snapshot, turns)
    assert "$defs" not in grammar
    assert grammar["properties"]["evidence"]["properties"]["workflow"] == {"enum": [None]}
    assert grammar["properties"]["outcome"]["enum"] == [
        "candidate",
        "needs_clarification",
        "unsupported",
    ]
    assert grammar["properties"]["intent"]["properties"]["start"] == {
        "anyOf": [{"type": "string"}, {"type": "null"}]
    }


def test_quotes_keep_case_utc_roles_and_whole_lists_without_joining():
    snapshot = two_selected()
    text = (
        "cross_asset BTCUSDT and SOLUSDT; history_start 2025-03-01T00:00:00+00:00; "
        "start 2025-03-01T01:00:00Z; exclusive end 2025-03-01T02:00:00Z; "
        "five-minute metrics correlation and close_change_difference"
    )
    proofs = evidence_options(snapshot, [{"text": text, "context": {}}])
    assert {"turn": 0, "quote": "BTCUSDT and SOLUSDT"} in proofs["instruments"]
    assert {"turn": 0, "quote": "correlation and close_change_difference"} in proofs["metrics"]
    assert proofs["history_start"] == [None, {"turn": 0, "quote": "2025-03-01T00:00:00+00:00"}]
    assert proofs["start"] == [None, {"turn": 0, "quote": "2025-03-01T01:00:00Z"}]
    assert proofs["interval"] == [None, {"turn": 0, "quote": "five-minute"}]
    for options in proofs.values():
        for proof in options[1:]:
            assert proof["quote"] in text and len(proof["quote"]) <= 160
    assert {"turn": 0, "quote": "btcusdt solusdt"} not in proofs["instruments"]
    assert evidence_options(
        snapshot, [{"text": "history_start 2025-03-01T00:00:00Z", "context": {}}]
    )["start"] == [None]
    assert evidence_options(snapshot, [{"text": "start 2025-03-01T01:00:00+01:00", "context": {}}])[
        "start"
    ] == [None]


def test_context_priority_shortest_quote_distinct_values_and_all_turn_indices():
    snapshot = selection()
    proofs = evidence_options(
        snapshot,
        [
            {"text": "descriptive profile market_profile", "context": {}},
            {"text": "metrics profile", "context": {"metrics": ["correlation"]}},
            *[{"text": "5m", "context": {"interval": "5m"}} for _ in range(4)],
        ],
    )
    assert proofs["workflow"] == [None, {"turn": 0, "quote": "market_profile"}]
    assert proofs["metrics"] == [
        None,
        {"turn": 1, "context": True},
        {"turn": 1, "quote": "profile"},
    ]
    assert proofs["interval"] == [
        None,
        *[{"turn": index, "context": True} for index in range(2, 6)],
    ]


@pytest.mark.parametrize(
    "text,first,last,valid",
    [
        (" BTC ", 1, 4, True),
        ("éBTCé", 1, 4, True),
        ("xBTCx", 1, 4, False),
        ("_BTC", 1, 4, False),
        ("BTC_", 0, 3, False),
        ("BTC", -1, 3, False),
        ("BTC", 0, 4, False),
        ("BTC", 0, 0, False),
        ("BTC" + " " * 158, 0, 161, False),
    ],
)
def test_known_span_ascii_boundaries_and_quote_limit(text, first, last, valid):
    assert (_quoted_value("instruments", text, first, last, two_selected()) is not None) == valid


def test_whole_list_model_evidence_still_requires_independent_equality():
    body, snapshot = request(), two_selected()
    body["instrument_ids"] = body["context"]["instrument_ids"] = [
        "binance:spot:BTCUSDT",
        "binance:spot:SOLUSDT",
    ]
    body["text"] = "BTCUSDT and SOLUSDT"
    native = candidate(body, snapshot)
    native["evidence"]["instruments"] = {"turn": 0, "quote": "BTCUSDT"}
    assert native["evidence"]["instruments"] in evidence_options(snapshot, [body])["instruments"]
    with pytest.raises(V2Error, match="Ungrounded quoted intent"):
        decide([body], snapshot, native)
    native["evidence"]["instruments"]["quote"] = "BTCUSDT and SOLUSDT"
    assert decide([body], snapshot, native)[0] == "candidate"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("cross_asset comparison", "candidate"),
        ("CROSS_ASSET\tcomparison", "candidate"),
        ("comparison", "needs_clarification"),
        ("cross_asset comparable", "needs_clarification"),
        ("cross_asset comparison on Kraken", "unsupported"),
        ("cross_asset comparison not profile", "needs_clarification"),
        ("cross_asset comparison with magicfilter", "needs_clarification"),
        ("cross_asset comparison market_profile", "needs_clarification"),
        ("xcross_asset comparison", "needs_clarification"),
        ("cross_asset comparison2", "needs_clarification"),
    ],
)
def test_only_explicit_cross_asset_redundant_noun_is_covered(text, expected):
    body, snapshot = request(), selection()
    body["context"].update(workflow="cross_asset", metrics=["correlation"])
    body["text"] = text
    assert decide([body], snapshot, candidate(body, snapshot))[0] == expected


def test_content_lower_bound_rejects_before_candidate_enumeration(monkeypatch):
    from marketlab.copilot.v2 import model as module

    def forbidden(*args):
        raise AssertionError("Impossible raw content must reject before grammar work")

    monkeypatch.setattr(module, "model_schema", forbidden)
    with pytest.raises(ModelFailure, match="exceeds inference budget"):
        CopilotModel("http://unused").prepare(selection(), [{"text": "x" * 6000, "context": {}}])


def test_execution_and_protocol_versions_are_explicit_and_memo_is_unchanged():
    identity = execution("copilot")
    assert identity["schema"] == "copilot-execution-v3"
    assert identity["grammar"] == GRAMMAR_VERSION
    assert identity["semantic"] == SEMANTIC_VERSION
    assert "grammar" not in execution("memo") and "semantic" not in execution("memo")
    assert execution("memo")["schema"] == "memo-execution-v2"
    for field, old in (("schema", "copilot-execution-v2"), ("grammar", "old"), ("semantic", "old")):
        assert digest(identity) != digest(dict(identity, **{field: old}))


@pytest.fixture
def evaluator():
    location = Path(__file__).resolve().parents[1] / "scripts/v2_phase5_model_eval.py"
    spec = importlib.util.spec_from_file_location("phase5_dynamic_protocol_test", location)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_evaluation_protocol_describes_per_request_schemas_without_static_hash(evaluator):
    protocols = evaluator.protocols()
    assert protocols["copilot_versions"] == copilot_versions()
    assert protocols["copilot_schema_policy"] == "request-specific-canonical-evidence-v1"
    assert "copilot_schema" not in protocols and "copilot_schema_sha256" not in protocols
    assert digest(protocols["memo_schema"]) == protocols["memo_schema_sha256"]


def test_v7_prompt_preserves_bounded_protocol_identity():
    assert copilot_versions()["prompt_version"] == "copilot-prompt-v7"
    assert len(PROMPT.encode()) == 1731
    assert hashlib.sha256(PROMPT.encode()).hexdigest() == (
        "a0f0d25af2189d2d775f4a994433c78cb50576b95dadcdbbdc376a6cef5e09b9"
    )
    prepared = CopilotModel("http://unused").prepare(selection(), [request()])
    assert prepared["input_bytes"] <= 6000


def test_existing_preparation_rejects_history_mutation_or_model_calls(evaluator):
    old = '{"run_id":"old"}'
    fresh = '{"run_id":"fresh"}'
    tables = ("v2_research_runs", "v2_research_attempts", "v2_research_results", "v2_memo_jobs")
    before = {**{table: Counter([old]) for table in tables}, "v2_memo_calls": Counter()}
    after = {**{table: Counter([old, fresh]) for table in tables}, "v2_memo_calls": Counter()}
    evaluator.verify_preparation_history(before, after, {"fresh"})
    with pytest.raises(ValueError, match="Historical"):
        evaluator.verify_preparation_history(
            before, {**after, "v2_memo_calls": Counter([fresh])}, {"fresh"}
        )
    with pytest.raises(ValueError, match="Historical"):
        evaluator.verify_preparation_history(
            before, {**after, "v2_research_runs": Counter([fresh])}, {"fresh"}
        )


@pytest.fixture
def bind_selection(evaluator, tmp_path):
    from marketlab.datasets.v2.capabilities import value as capabilities

    files = {name: tmp_path / name for name in ("manifest.json", "trades.parquet", "quality.json")}
    for file in files.values():
        file.write_bytes(b"original")
    row = {
        "manifest_path": files["manifest.json"],
        "path": files["trades.parquet"],
        "contract": "dataset-manifest-v2",
        "catalog_identity": ("row",),
        "signature": ("constant-test-signature",),
        "metadata": {"display_name": "Bitcoin"},
    }
    calls = []
    body = request()

    def full_snapshot(value):
        calls.append(value)
        return dict(selection(), capability_sha256=capabilities()["sha256"])

    copilot = SimpleNamespace(
        root=tmp_path,
        research=SimpleNamespace(bars=SimpleNamespace(_catalog=lambda versions: [row])),
        snapshot=full_snapshot,
    )
    return evaluator.BindSnapshots(copilot), body, row, calls, files


def test_bind_reuses_exact_selection_but_checks_context_and_copies_snapshot(bind_selection):
    cache, body, _, calls, _ = bind_selection
    first = cache.snapshot(body)
    first["instruments"].clear()
    assert cache.snapshot(dict(body, text="A different literal"))["instruments"]
    with pytest.raises(V2Error, match="unselected"):
        cache.snapshot(dict(body, context={"instrument_ids": ["binance:spot:BTCUSDT"]}))
    assert len(calls) == 1 and cache.reused == 1
    other = dict(body, dataset_versions=["a" * 64, "b" * 64])
    cache.snapshot(other)
    cache.snapshot(dict(other, dataset_versions=list(reversed(other["dataset_versions"]))))
    assert len(calls) == 3
    cache.check_final()


@pytest.mark.parametrize("change", ["bytes", "catalog", "metadata", "signature"])
def test_bind_rejects_drift_on_reuse_and_before_publication(bind_selection, change):
    cache, body, row, calls, files = bind_selection
    cache.snapshot(body)
    if change == "bytes":
        files["trades.parquet"].write_bytes(b"tampered")
    elif change == "catalog":
        row["catalog_identity"] = ("different-row",)
    elif change == "metadata":
        row["metadata"]["display_name"] = "Changed"
    else:
        row["signature"] = ("different-signature",)
    with pytest.raises(ValueError, match="changed"):
        cache.snapshot(body)
    with pytest.raises(ValueError, match="changed before publication"):
        cache.check_final()
    assert len(calls) == 1


def test_bind_rejects_bytes_changed_during_full_verification(bind_selection):
    cache, body, _, calls, files = bind_selection
    full_snapshot = cache.copilot.snapshot

    def change_during_verification(value):
        result = full_snapshot(value)
        files["quality.json"].write_bytes(b"tampered")
        return result

    cache.copilot.snapshot = change_during_verification
    with pytest.raises(ValueError, match="changed"):
        cache.snapshot(body)
    assert len(calls) == 1 and not cache.verified


def test_bind_rejects_change_during_final_hashing(evaluator, bind_selection, monkeypatch):
    cache, body, row, _, files = bind_selection
    manifest = files["manifest.json"]
    bars = cache.copilot.research.bars
    bars._catalog = lambda versions: [dict(row, signature=(manifest.stat().st_size,))]
    cache.snapshot(body)
    hash_file = evaluator.sha

    def change_after_manifest_hash(path):
        if path == files["trades.parquet"]:
            manifest.write_bytes(b"longer than original")
        return hash_file(path)

    monkeypatch.setattr(evaluator, "sha", change_after_manifest_hash)
    with pytest.raises(ValueError, match="changed during hashing"):
        cache.check_final()


@pytest.mark.parametrize("field", list(copilot_versions()))
def test_checkpoint_rejects_wrong_protocol_version_before_database_access(field):
    value = candidate()
    raw = canonical_json(value).decode()
    proof = {**copilot_versions(), "response": raw, "response_sha256": digest(value)}
    proof[field] = "old"
    claim = durable.Claim("copilot", "unused", "unused", 1, 1)
    with pytest.raises(V2Error, match="Invalid bounded model receipt"):
        durable.checkpoint(None, claim, 1, value, proof)


async def test_native_exact_dynamic_schema_matches_prepared_reservation_and_receipt(monkeypatch):
    model = CopilotModel("http://unused")
    snapshot, body = selection(), request()
    expected = model.prepare(snapshot, [body])
    sent = []

    async def identify():
        return DIGEST

    async def bounded(client, method, path, **kwargs):
        if path == "/api/version":
            return {"version": "controlled-protocol"}
        sent.append(kwargs["json"])
        return {
            "message": {"content": canonical_json(candidate()).decode()},
            "done": True,
            "done_reason": "stop",
        }

    monkeypatch.setattr(model, "identify", identify)
    monkeypatch.setattr(model, "bounded", bounded)
    _, receipt = await model.interpret(snapshot, [body], expected=expected)
    assert sent[0]["format"] == model_schema(snapshot, [body])
    assert digest(sent[0]["format"]) == receipt["schema_sha256"] == expected["schema_sha256"]
    assert sent[0]["messages"][0]["content"] == PROMPT
    assert (
        digest(model.content(snapshot, [body]))
        == receipt["input_sha256"]
        == expected["input_sha256"]
    )
    assert all(receipt[key] == version for key, version in copilot_versions().items())


async def test_native_changed_prepared_schema_rejects_before_any_network(monkeypatch):
    model = CopilotModel("http://unused")
    body, snapshot = request(), selection()
    expected = model.prepare(snapshot, [body])

    async def forbidden(*args, **kwargs):
        raise AssertionError("Changed reservation must not make an identification or native call")

    monkeypatch.setattr(model, "identify", forbidden)
    monkeypatch.setattr(model, "bounded", forbidden)
    changed = copy.deepcopy(body)
    changed["context"].pop("interval")
    with pytest.raises(ModelFailure, match="reserved model inputs changed"):
        await model.interpret(snapshot, [changed], expected=expected)
