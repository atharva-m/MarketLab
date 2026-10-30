"""Generalized reference adaptation preserves retained independent arithmetic and units."""

import copy
import importlib.util
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest


@pytest.fixture
def harness():
    path = Path(__file__).resolve().parents[1] / "scripts/v2_phase3_acceptance.py"
    specification = importlib.util.spec_from_file_location(
        "phase3_generalized_reference_test", path
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def rows(multiplier=1, count=320):
    first = datetime(2025, 3, 1, tzinfo=UTC)
    result = []
    for index in range(count):
        price = Decimal(100) + Decimal(index * multiplier) / Decimal(10)
        start = (first + timedelta(minutes=index * 5)).isoformat().replace("+00:00", "Z")
        end = (first + timedelta(minutes=(index + 1) * 5)).isoformat().replace("+00:00", "Z")
        result.append(
            {
                "start": start,
                "end": end,
                **{key: format(price, ".18f") for key in ("open", "high", "low", "close")},
                "base_volume": "1.000000000000000000",
                "quote_volume": format(price, ".18f"),
                "trade_count": 1,
                "vwap": format(price, ".18f"),
            }
        )
    return result


def metadata(identities, quote="USDC"):
    return {
        identity: {
            "instrument_id": identity,
            "source_symbol": identity.rsplit(":", 1)[1],
            "base_asset": "FIRST" if index == 0 else "SECOND",
            "quote_asset": quote,
            "display_name": "BTCUSDT and ETHUSDT are literal display data",
        }
        for index, identity in enumerate(sorted(identities))
    }


@pytest.mark.parametrize("workflow", ["market_profile", "cross_asset", "volatility_cluster"])
def test_btc_sol_all_workflows_without_eth_input_have_exact_reference_projection(harness, workflow):
    identities = (
        ["binance:spot:BTCUSDT", "binance:spot:SOLUSDT"]
        if workflow == "cross_asset"
        else ["binance:spot:SOLUSDT"]
    )
    pinned = metadata(identities)
    spec = harness.request(
        workflow,
        identities,
        ["a" * 64],
        "2025-03-01T00:00:00Z",
        "2025-03-02T01:00:00Z",
        "2025-03-02T02:40:00Z",
    )
    inputs = {identity: rows(index + 1) for index, identity in enumerate(sorted(identities))}
    result, summary = harness.independent_reference(spec, inputs, pinned)
    aliases = ("BTCUSDT", "ETHUSDT")[: len(identities)]
    old = dict(spec, schema="research-spec-v1", symbols=list(aliases))
    old.pop("instrument_ids")
    baseline = harness.independent_module().reference_payload(
        old,
        {
            alias: inputs[identity]
            for alias, identity in zip(aliases, sorted(identities), strict=True)
        },
    )
    for actual, expected in zip((result, summary), baseline, strict=True):
        assert actual["history"] == {
            identity: expected["history"][alias]
            for alias, identity in zip(aliases, sorted(identities), strict=True)
        }
        if "profiles" in expected:
            assert actual["profiles"] == {
                identity: expected["profiles"][alias]
                for alias, identity in zip(aliases, sorted(identities), strict=True)
            }
        for key in ("cross_asset", "clusters", "cluster_counts"):
            if key in expected:
                assert actual[key] == expected[key]
        assert actual["units"]["price"] == actual["units"]["quote_volume"] == "USDC"
        assert actual["units"]["base_volume"] == {i: pinned[i]["base_asset"] for i in identities}
        assert actual["instruments"] == pinned
        assert all(
            m["display_name"] == "BTCUSDT and ETHUSDT are literal display data"
            for m in actual["instruments"].values()
        )


def test_cross_order_is_canonical_and_asymmetric_difference_not_request_order(harness):
    ids = ["binance:spot:BTCUSDT", "binance:spot:SOLUSDT"]
    request = harness.request(
        "cross_asset",
        ids,
        ["a" * 64],
        "2025-03-01T00:00:00Z",
        "2025-03-02T01:00:00Z",
        "2025-03-02T02:40:00Z",
    )
    inputs = {ids[0]: rows(1), ids[1]: rows(4)}
    baseline = harness.independent_reference(request, inputs, metadata(ids))
    reversed_request = copy.deepcopy(request)
    reversed_request["instrument_ids"].reverse()
    assert harness.independent_reference(reversed_request, inputs, metadata(ids)) == baseline
    difference = baseline[0]["cross_asset"]["close_change_difference"]["value"]
    assert Decimal(difference) != 0
    assert baseline[0]["comparison_order"] == ids


def test_old_reference_still_exposes_hardcode_and_generalized_adapter_does_not(harness):
    independent = harness.independent_module()
    first = datetime(2025, 3, 2, 1, tzinfo=UTC)
    before = first + timedelta(minutes=100)
    with pytest.raises(KeyError, match="ETHUSDT"):
        independent.cross_asset({"BTCUSDT": rows(), "SOLUSDT": rows(3)}, first, before)
    ids = ["binance:spot:BTCUSDT", "binance:spot:SOLUSDT"]
    spec = harness.request(
        "cross_asset",
        ids,
        ["a" * 64],
        "2025-03-01T00:00:00Z",
        first.isoformat(),
        before.isoformat(),
    )
    assert harness.independent_reference(spec, {ids[0]: rows(), ids[1]: rows(3)}, metadata(ids))[0][
        "cross_asset"
    ]


def test_arbitrary_ids_quotes_and_labels_do_not_depend_on_btc_sol_strings(harness):
    ids = ["binance:spot:AAAUSDC", "binance:spot:ZZZUSDC"]
    spec = harness.request(
        "cross_asset",
        list(reversed(ids)),
        ["a" * 64],
        "2025-03-01T00:00:00Z",
        "2025-03-02T01:00:00Z",
        "2025-03-02T02:40:00Z",
    )
    result, _ = harness.independent_reference(
        spec, {ids[0]: rows(), ids[1]: rows(2)}, metadata(ids)
    )
    assert set(result["profiles"]) == set(ids) and result["comparison_order"] == ids
    different = metadata(ids)
    different[ids[1]]["quote_asset"] = "USDT"
    with pytest.raises(ValueError, match="quote mismatch"):
        harness.independent_reference(spec, {ids[0]: rows(), ids[1]: rows(2)}, different)


def test_retained_btc_eth_reference_shapes_and_numerics_remain_exact(harness):
    ids = ["binance:spot:BTCUSDT", "binance:spot:ETHUSDT"]
    spec = harness.request(
        "cross_asset",
        ids,
        ["a" * 64],
        "2025-03-01T00:00:00Z",
        "2025-03-02T01:00:00Z",
        "2025-03-02T02:40:00Z",
    )
    pinned = metadata(ids, quote="USDT")
    pinned[ids[0]]["base_asset"] = "BTC"
    pinned[ids[1]]["base_asset"] = "ETH"
    inputs = {ids[0]: rows(), ids[1]: rows(2)}
    old = dict(spec, schema="research-spec-v1", symbols=["BTCUSDT", "ETHUSDT"])
    old.pop("instrument_ids")
    baseline = harness.independent_module().reference_payload(
        old, {"BTCUSDT": inputs[ids[0]], "ETHUSDT": inputs[ids[1]]}
    )
    actual = harness.independent_reference(spec, inputs, pinned)
    assert tuple(harness.projected(b) for b in actual) == baseline


def test_adapter_source_has_no_production_numerical_dependency(harness):
    import inspect

    source = inspect.getsource(harness.independent_reference)
    assert "marketlab.research" not in source and "legacy_calculate" not in source
