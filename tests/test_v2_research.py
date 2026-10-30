"""Strict generalized requests and exact metadata projection over retained arithmetic."""

import copy
import threading
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from test_research import bars as old_bars

from marketlab.app import create_app
from marketlab.datasets.v2.common import V2Error, canonical_json
from marketlab.research.v2.numerics import calculate
from marketlab.research.v2.spec import ResearchSpec


def body(workflow="market_profile", day="2025-03-01", warmup=12, count=20):
    first = datetime.fromisoformat(day).replace(tzinfo=UTC)
    return {
        "schema": "research-spec-v2",
        "workflow": workflow,
        "instrument_ids": ["binance:spot:SOLUSDT"]
        if workflow != "cross_asset"
        else ["binance:spot:BTCUSDT", "binance:spot:SOLUSDT"],
        "dataset_versions": ["a" * 64],
        "history_start": first.isoformat(),
        "start": (first + timedelta(minutes=5 * warmup)).isoformat(),
        "end": (first + timedelta(minutes=5 * count)).isoformat(),
        "interval": "5m",
        "metrics": ["profile"],
        "parameters": {},
        "predicates": {"volatility_quantile": "0.9", "volume_multiple": "2", "min_bars": 2}
        if workflow == "volatility_cluster"
        else {},
    }


def test_generalized_request_canonical_and_legacy_rejected():
    initial = body("cross_asset")
    changed = copy.deepcopy(initial)
    changed["instrument_ids"].reverse()
    changed["start"] = changed["start"].replace("+00:00", "Z")
    assert ResearchSpec.create(initial).digest == ResearchSpec.create(changed).digest
    assert ResearchSpec.parse(canonical_json(initial)).body()["schema"] == "research-spec-v2"
    initial["symbols"] = initial.pop("instrument_ids")
    with pytest.raises(V2Error):
        ResearchSpec.create(initial)


@pytest.mark.parametrize(
    "key,value",
    [
        ("instrument_ids", ["binance:future:SOLUSDT"]),
        ("instrument_ids", True),
        ("instrument_ids", ["binance:spot:SOLUSDT", "binance:spot:BTCUSDT"]),
        ("dataset_versions", ["A" * 64]),
        ("dataset_versions", [f"{i:064x}" for i in range(63)]),
        ("parameters", {"sql": "SELECT 1"}),
        ("predicates", {"min_bars": True}),
        ("start", "2025-03-01T01:01:00Z"),
        ("end", "2025-03-01T01:40:00"),
        ("interval", "1m"),
        ("metrics", ["strategy"]),
        ("extra", 1),
    ],
)
def test_invalid_generalized_spec(key, value):
    request = body()
    request[key] = value
    with pytest.raises(V2Error):
        ResearchSpec.create(request)


def test_limits_warmup_and_last_supported_day():
    assert ResearchSpec.create(body(day="9999-12-30")).start.year == 9999
    request = body()
    request["end"] = "2025-05-03T00:00:00Z"
    with pytest.raises(V2Error):
        ResearchSpec.create(request)
    request = body("volatility_cluster", count=301, warmup=300)
    assert ResearchSpec.create(request).workflow == "volatility_cluster"
    request["predicates"]["min_bars"] = True
    with pytest.raises(V2Error):
        ResearchSpec.create(request)


def test_projection_uses_registry_units_not_symbol_heuristics():
    spec = ResearchSpec.create(body())
    inputs = old_bars()
    for row in inputs:
        for key in ("start", "end"):
            row[key] = row[key].replace("2025-01-01", "2025-03-01")
    identity = spec.instrument_ids[0]
    metadata = {identity: {"base_asset": "SOL", "quote_asset": "USDC", "display_name": "<data>"}}
    result, summary = calculate(spec, {identity: inputs}, metadata, threading.Event())
    assert result["units"]["price"] == "USDC"
    assert result["units"]["base_volume"] == {identity: "SOL"}
    assert result["profiles"][identity]["coverage"]["observed"] == 8
    assert result["schema"] == "research-results-v2"
    assert summary["instruments"] == metadata


async def test_http_strict_errors_and_origin_without_database():
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        response = await client.post(
            "/v2/research/runs", content=b"x", headers={"content-type": "text/plain"}
        )
        assert response.status_code == 415
        assert response.json()["error"]["code"] == "unsupported_media"
        response = await client.post(
            "/v2/research/runs", json=body(), headers={"Origin": "https://evil.test"}
        )
        assert response.status_code == 403
        response = await client.post(
            "/v2/research/runs", content=b" " * 65537, headers={"content-type": "application/json"}
        )
        assert response.status_code == 413
        response = await client.get(
            "/v2/bars?instrument_id=a&version=b&interval=5m&start=x&end=y&extra=1"
        )
        assert response.status_code == 422
