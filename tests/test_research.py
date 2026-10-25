"""Strict research inputs and hand-derived numerical/window boundaries."""

import copy
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from unittest.mock import Mock

import httpx
import pytest

from marketlab.app import create_app
from marketlab.research.numerics import CONTEXT, calculate, clusters, prepare, quantile
from marketlab.research.spec import PREDICATES, ResearchError, ResearchSpec, parse_json

START = datetime(2025, 1, 1, tzinfo=UTC)


def stamp(value):
    return value.isoformat().replace("+00:00", "Z")


def body(workflow="market_profile", count=20, warmup=12):
    return {
        "schema": "research-spec-v1",
        "workflow": workflow,
        "symbols": ["BTCUSDT", "ETHUSDT"] if workflow == "cross_asset" else ["BTCUSDT"],
        "dataset_versions": ["a" * 64],
        "history_start": stamp(START),
        "start": stamp(START + timedelta(minutes=5 * warmup)),
        "end": stamp(START + timedelta(minutes=5 * count)),
        "interval": "5m",
        "metrics": ["profile", "correlation", "close_change_difference"]
        if workflow == "cross_asset"
        else ["profile", "clusters"]
        if workflow == "volatility_cluster"
        else ["profile"],
        "parameters": {},
        "predicates": PREDICATES.copy() if workflow == "volatility_cluster" else {},
    }


def bars(count=20, prices=None, volumes=None):
    result = []
    for index in range(count):
        price = Decimal(str(prices[index] if prices is not None else 100 + index))
        volume = Decimal(str(volumes[index] if volumes is not None else 1))
        result.append(
            {
                "start": stamp(START + timedelta(minutes=5 * index)),
                "end": stamp(START + timedelta(minutes=5 * (index + 1))),
                **{key: f"{price:.18f}" for key in ("open", "high", "low", "close")},
                "base_volume": f"{volume:.18f}",
                "quote_volume": f"{price * volume:.18f}",
                "trade_count": 1,
                "vwap": f"{price:.18f}",
            }
        )
    return result


@pytest.mark.parametrize(
    "field,value",
    [
        ("extra", 1),
        ("interval", "1m"),
        ("parameters", {"sql": "x"}),
        ("symbols", ["btcusdt"]),
        ("symbols", ["BTCUSDT", "BTCUSDT"]),
        ("dataset_versions", ["A" * 64]),
        ("metrics", ["beta"]),
        ("start", "2025-01-01T01:01:00Z"),
        ("start", "2025-01-01T01:00:00-00:00"),
        ("start", "2025-01-01T01:00:00"),
        ("metrics", ["profile", "profile"]),
        ("symbols", True),
        ("predicates", {"expr": "1"}),
    ],
)
def test_strict_spec_rejects(field, value):
    spec = body()
    spec[field] = value
    with pytest.raises(ResearchError):
        ResearchSpec.create(spec)


def test_json_duplicate_and_size_rejection():
    with pytest.raises(ResearchError):
        parse_json(b'{"x":1,"x":2}')
    with pytest.raises(ResearchError):
        parse_json(b" " * 65537)
    with pytest.raises(ResearchError):
        parse_json(b"{invalid}")
    with pytest.raises(ResearchError):
        parse_json(b'{"x":NaN}')


def test_canonical_order_and_timestamps():
    first = body("cross_asset")
    second = copy.deepcopy(first)
    second["symbols"].reverse()
    second["metrics"].reverse()
    second["start"] = second["start"].replace("Z", "+00:00")
    assert ResearchSpec.create(first).digest == ResearchSpec.create(second).digest


def test_profile_hand_derived_and_first_return_uses_warmup():
    prices = [100] * 12 + [100, 110, 99, 108.9]
    spec = ResearchSpec.create(body(count=16))
    result, summary = calculate(spec, {"BTCUSDT": bars(16, prices)})
    p = result["profiles"]["BTCUSDT"]
    assert p["coverage"] == {"expected": 4, "observed": 4, "missing": 0, "incomplete_grid": False}
    assert p["return_mean"]["value"] == "0.025000000000000000"
    assert p["return_mean"]["observation_count"] == 4
    assert p["drawdown"]["value"] == "-0.100000000000000000"
    assert p["vwap"]["value"] == "104.475000000000000000"
    assert p["close_change"]["value"] == "0.089000000000000000"
    assert [x["start"] for x in p["volume_spikes"]] == [b["start"] for b in bars(16)[12:15]]
    assert summary["profiles"] == result["profiles"]


def test_constant_returns_undefined_sharpe_and_one_close_drawdown():
    result, _ = calculate(ResearchSpec.create(body(count=13)), {"BTCUSDT": bars(13, [100] * 13)})
    p = result["profiles"]["BTCUSDT"]
    assert p["drawdown"]["value"] == "0.000000000000000000"
    assert p["return_stddev"]["reason"] == "insufficient_observations"
    result, _ = calculate(ResearchSpec.create(body()), {"BTCUSDT": bars(20, [100] * 20)})
    assert result["profiles"]["BTCUSDT"]["sharpe"]["reason"] == "zero_variance"


def test_missing_bars_no_gap_return_or_volume_fill():
    source = bars(20)
    del source[14]
    result, _ = calculate(ResearchSpec.create(body()), {"BTCUSDT": source})
    p = result["profiles"]["BTCUSDT"]
    assert p["coverage"]["missing"] == 1
    assert p["undefined_returns"] == 1
    assert p["undefined_volume_windows"] == 5


def test_insufficient_actual_initial_history():
    source = bars()
    del source[3]
    with pytest.raises(ResearchError, match="history"):
        calculate(ResearchSpec.create(body()), {"BTCUSDT": source})


def test_cross_perfect_correlation_and_missing_alignment():
    spec = ResearchSpec.create(body("cross_asset"))
    source = bars()
    second = copy.deepcopy(source)
    del second[15]
    result, _ = calculate(spec, {"BTCUSDT": source, "ETHUSDT": second})
    assert result["cross_asset"]["correlation"]["value"] == "1.000000000000000000"
    assert result["cross_asset"]["aligned_return_count"] == 6
    assert result["cross_asset"]["close_change_difference"]["value"] == "0.000000000000000000"


def test_quantile_288_linear_interpolation():
    with localcontext(CONTEXT):
        assert quantile([Decimal(x) for x in range(288)]) == Decimal("258.3")


def test_300_warmup_and_no_lookahead():
    spec = ResearchSpec.create(body("volatility_cluster", 305, 300))
    source = bars(305)
    result, _ = calculate(spec, {"BTCUSDT": source})
    assert result["cluster_counts"]["qualifying"] == 0
    with localcontext(CONTEXT):
        before = prepare(source)
        changed = copy.deepcopy(source)
        changed[-1]["close"] = "999999.000000000000000000"
        after = prepare(changed)
        assert before[:-1] == after[:-1]
        assert before[300]["prior_volatility_count"] == 288
        assert before[299]["prior_volatility_count"] == 287


def test_two_adjacent_cluster_rule_and_boundaries():
    spec = ResearchSpec.create(body("volatility_cluster", 305, 300))
    with localcontext(CONTEXT):
        source = prepare(bars(305))[300:]
        for row in source:
            row.update(
                qualifies=True,
                volatility=Decimal(1),
                threshold=Decimal("0.5"),
                volume_multiple=Decimal(3),
            )
        source[2]["qualifies"] = False
        result = clusters(source, spec)
    assert [r["bar_count"] for r in result] == [2, 2]
    assert result[0]["touches_start"] and result[-1]["touches_end"]
    assert result[0]["max_volatility_start"] == source[0]["start"]


def test_shuffle_reproducibility_and_cancelled_numerical_thread():
    spec = ResearchSpec.create(body())
    assert calculate(spec, {"BTCUSDT": bars()}) == calculate(
        spec, {"BTCUSDT": list(reversed(bars()))}
    )
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(ResearchError, match="cancelled"):
        calculate(spec, {"BTCUSDT": bars()}, cancelled)


@pytest.mark.asyncio
async def test_invalid_http_research_before_database(tmp_path):
    app = create_app()
    app.state.research_service = Mock()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        invalid = body()
        invalid["parameters"] = {"code": "print(1)"}
        response = await client.post(
            "/v1/research/runs", json=invalid, headers={"Idempotency-Key": "x"}
        )
        assert response.status_code == 422
        assert (
            await client.post("/v1/research/runs", content=b"{}", headers={"Idempotency-Key": "x"})
        ).status_code == 422
    app.state.research_service.submit.assert_not_called()


@pytest.mark.parametrize(
    "state,expected",
    [
        ("40001", True),
        ("40P01", True),
        ("55P03", True),
        ("08006", True),
        ("28P01", False),
        ("3D000", False),
        (None, False),
    ],
)
def test_narrow_postgresql_retry_classification(state, expected):
    from sqlalchemy.exc import OperationalError

    from marketlab.research.service import transient_failure

    class DriverError(Exception):
        sqlstate = state

    assert transient_failure(OperationalError("private sql", {}, DriverError())) is expected


@pytest.mark.asyncio
async def test_application_service_revalidates_manual_dataclass(tmp_path):
    from dataclasses import replace

    from sqlalchemy import create_engine

    from marketlab.analytics.bars import BarService
    from marketlab.research.service import ResearchService

    reader = BarService(create_engine("sqlite://"), tmp_path)
    service = ResearchService(reader)
    invalid = replace(ResearchSpec.create(body()), metrics=("arbitrary_sql",))
    with pytest.raises(ResearchError):
        await service.submit(invalid, "one")
    await reader.close()


def test_result_cap_cleans_owned_staging(tmp_path):
    from sqlalchemy import create_engine

    from marketlab.analytics.bars import BarService
    from marketlab.research.service import MAX_RESULT, ResearchService
    from marketlab.research.store import Claim

    reader = BarService(create_engine("sqlite://"), tmp_path)
    service = ResearchService(reader)
    result = {
        "schema": "research-results-v1",
        "units": {},
        "profiles": {},
        "padding": "x" * MAX_RESULT,
    }
    with pytest.raises(ResearchError, match="16 MiB"):
        service.stage(
            Claim("a" * 36, "b" * 36, 1, 1),
            ResearchSpec.create(body()),
            {},
            result,
            {"schema": "research-summary-v1"},
        )
    assert list((tmp_path / ".staging").iterdir()) == []
