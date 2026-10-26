"""Memo factual/qualitative grounding and strict bounded model output."""

import copy
import json
from pathlib import Path

import httpx
import pytest
from test_research import bars, body

from marketlab.app import create_app
from marketlab.memos.model import MemoModel
from marketlab.memos.spec import KINDS, draft, facts, render
from marketlab.research.numerics import calculate
from marketlab.research.spec import ResearchError, ResearchSpec


def valid_draft(wording="standard"):
    return {
        "schema": "memo-draft-v1",
        "paragraphs": [{"claim": kind, "wording": wording} for kind in KINDS],
    }


def summary(workflow="market_profile", metrics=None, prices=None):
    raw = body(workflow)
    if metrics is not None:
        raw["metrics"] = metrics
    spec = ResearchSpec.create(raw)
    inputs = {s: bars(prices=prices) for s in spec.symbols}
    return calculate(spec, inputs)[1]


def test_three_paragraph_exact_values_units_and_variants():
    source = summary()
    prepared = facts(source)
    for wording in ("standard", "measured"):
        result = render(valid_draft(wording), prepared)
        assert len(result.strip().split("\n\n")) == 3
        assert result.startswith("AI-generated research memo.")
        assert "BTCUSDT" in result and "USDT" in result and "ratio" in result
        for name in ("vwap", "close_change", "drawdown", "sharpe"):
            assert source["profiles"]["BTCUSDT"][name]["value"] in result
        assert "{{" not in result and "causal evidence" in result


@pytest.mark.parametrize(
    "metrics", [["correlation"], ["close_change_difference"], ["profile", "correlation"]]
)
def test_sparse_cross_asset_metrics_are_not_invented(metrics):
    source = summary("cross_asset", metrics)
    result = render(valid_draft(), facts(source))
    assert ("Pearson correlation" in result) == ("correlation" in metrics)
    assert ("BTC-minus-ETH" in result) == ("close_change_difference" in metrics)
    assert ("VWAP" in result) == ("profile" in metrics)


def test_null_reasons_counts_and_sign_are_grounded():
    source = summary("cross_asset", ["correlation"], [100] * 20)
    result = render(valid_draft(), facts(source))
    assert "unavailable (zero_variance; observations 8)" in result
    assert "association is" not in result
    for sign, value in (
        ("positive", "0.500000000000000000"),
        ("negative", "-0.500000000000000000"),
        ("zero", "0.000000000000000000"),
    ):
        source["cross_asset"]["correlation"] = {
            "value": value,
            "reason": None,
            "observation_count": 8,
        }
        assert "association is " + sign in render(valid_draft(), facts(source))


def test_gap_and_cluster_selected_counts_with_no_event_truncation_claim():
    source = summary()
    source["profiles"]["BTCUSDT"]["coverage"] = {
        "expected": 8,
        "observed": 7,
        "missing": 1,
        "incomplete_grid": True,
    }
    result = render(valid_draft(), facts(source))
    assert "7 observed of 8 expected, 1 missing" in result
    assert "no gaps were filled" in result
    source.pop("profiles")
    source["workflow"] = "volatility_cluster"
    source["cluster_counts"] = {"clusters": 0, "qualifying": 1, "ineligible": 7}
    source["clusters"] = []
    result = render(valid_draft(), facts(source))
    assert (
        "Detected clusters: 0" in result and "Profile coverage metrics were not selected" in result
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda v: v.update(extra="buy now"),
        lambda v: v.update(schema="other"),
        lambda v: v["paragraphs"].pop(),
        lambda v: v["paragraphs"].append({"claim": "findings", "wording": "standard"}),
        lambda v: v["paragraphs"][1].update(claim="caused_by_news"),
        lambda v: v["paragraphs"][1].update(wording="profit 99%"),
        lambda v: v["paragraphs"][1].update(wording="{{unknown}}"),
        lambda v: v["paragraphs"][1].update(wording="<script>alert(1)</script>"),
        lambda v: v["paragraphs"][1].update(text="price will rise"),
        lambda v: v["paragraphs"].reverse(),
    ],
)
def test_adversarial_claims_numbers_markup_predictions_rejected(mutation):
    value = valid_draft()
    mutation(value)
    with pytest.raises(ResearchError):
        draft(value)


def test_unknown_placeholder_fact_injection_and_bounds_rejected():
    prepared = facts(summary())
    prepared["claims"]["findings"] += " {{unknown}}"
    with pytest.raises(ResearchError, match="placeholder"):
        render(valid_draft(), prepared)
    for bad in ("<script>", "x\ny", "x" * 257):
        source = summary()
        source["start"] = bad
        with pytest.raises(ResearchError):
            facts(source)


@pytest.mark.asyncio
async def test_memo_http_rejects_body_before_service_and_fixed_errors():
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.post("/v1/research/runs/x/memo", content=b'{"model":"bad"}')
        assert response.status_code == 422 and "empty body" in response.text


@pytest.mark.asyncio
async def test_model_transport_settings_digest_and_strict_response(monkeypatch):
    original = httpx.AsyncClient
    observed = []

    def endpoint(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "model", "digest": "pinned"}]})
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "test"})
        observed.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "done": True,
                "done_reason": "stop",
                "message": {"content": json.dumps(valid_draft())},
            },
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: original(**{**kw, "transport": httpx.MockTransport(endpoint)}),
    )
    model = MemoModel("http://local", "model")
    value, provenance = await model.generate(facts(summary()), "pinned")
    assert value == valid_draft() and provenance["model_digest"] == "pinned"
    assert observed[0]["options"] == {"temperature": 0, "num_ctx": 8192, "num_predict": 2048}
    assert observed[0]["think"] is False
    with pytest.raises(ResearchError, match="identity"):
        await model.generate(facts(summary()), "different")


def test_facts_do_not_mutate_summary_or_include_raw_event_array():
    source = summary()
    retained = copy.deepcopy(source)
    assert facts(source)["schema"] == "memo-facts-v1" and source == retained


def test_enqueue_rejects_malformed_uuid_before_database():
    from unittest.mock import Mock

    from marketlab.memos.service import MemoService

    research = Mock()
    memo = MemoService(research, Mock())
    with pytest.raises(ResearchError):
        memo.enqueue("-" * 36)
    research.read.assert_not_called()


def test_frozen_twenty_summary_corpus_has_required_distinct_coverage():
    corpus = json.loads((Path(__file__).parent / "fixtures" / "r6_summaries.json").read_text())
    assert len(corpus["cases"]) == 20
    correlations = []
    for case in corpus["cases"]:
        prepared = facts(case["summary"])
        assert len(render(valid_draft(), prepared).strip().split("\n\n")) == 3
        correlation = case["summary"].get("cross_asset", {}).get("correlation")
        if correlation is not None:
            correlations.append(correlation["value"])
    assert {"1.000000000000000000", "-1.000000000000000000", "0.000000000000000000", None} <= set(
        correlations
    )
