"""Hand-controlled numerical boundary witnesses for the approved R4 contract."""

from datetime import timedelta
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

import pytest
from test_research import START, bars, body, stamp

from marketlab.research.numerics import calculate, prepare
from marketlab.research.spec import ResearchSpec

DECIMAL80 = Context(prec=80, rounding=ROUND_HALF_EVEN)


def at(index: int) -> str:
    return stamp(START + timedelta(minutes=5 * index))


def prepared(source):
    with localcontext(DECIMAL80):
        return {row["start"]: row for row in prepare(source)}


def test_nonzero_volatility_equal_to_previous_percentile_does_not_qualify():
    # Alternating closes give six +1 and six -1/2 returns in EVERY 12-return
    # window. All 288 previous deviations and the current deviation are equal.
    prices = [1 if index % 2 == 0 else 2 for index in range(301)]
    source = bars(301, prices, [1] * 300 + [3])
    current = prepared(source)[at(300)]
    assert current["volatility"] > 0
    assert current["volatility"] == current["threshold"]
    assert current["volume_multiple"] == 3
    assert current["qualifies"] is False
    result, _ = calculate(
        ResearchSpec.create(body("volatility_cluster", 301, 300)), {"BTCUSDT": source}
    )
    assert result["cluster_counts"] == {"qualifying": 0, "ineligible": 0, "clusters": 0}


@pytest.mark.parametrize("volume,qualifies", [("2", False), ("2.000000000000000001", True)])
def test_volume_exactly_twice_mean_is_excluded_without_serialization_rounding(volume, qualifies):
    # Eleven zero returns and one +1 return have positive deviation; all 288
    # previous deviations are zero. Only the strict volume comparison can fail.
    source = bars(301, [100] * 300 + [200], [1] * 300 + [volume])
    current = prepared(source)[at(300)]
    assert current["volatility"] > current["threshold"] == 0
    assert current["volume_multiple"] == Decimal(volume)
    assert current["qualifies"] is qualifies
    result, _ = calculate(
        ResearchSpec.create(body("volatility_cluster", 301, 300)), {"BTCUSDT": source}
    )
    assert result["cluster_counts"]["qualifying"] == int(qualifies)
    assert result["clusters"] == []  # A qualifying singleton is still excluded.


def test_inverse_price_paths_give_negative_unit_log_return_correlation():
    # ETH is the reciprocal of BTC: each aligned log return has opposite sign.
    left = bars(16, [1] * 12 + [1, 2, 1, 4])
    right = bars(16, [1] * 12 + [1, "0.5", 1, "0.25"])
    result, _ = calculate(
        ResearchSpec.create(body("cross_asset", 16)), {"BTCUSDT": left, "ETHUSDT": right}
    )
    assert result["cross_asset"]["correlation"] == {
        "value": "-1.000000000000000000",
        "reason": None,
        "observation_count": 4,
    }


@pytest.mark.parametrize("constant_symbol", ["BTCUSDT", "ETHUSDT"])
def test_one_constant_return_series_makes_correlation_undefined(constant_symbol):
    inputs = {
        "BTCUSDT": bars(16, [100] * 12 + [100, 200, 100, 400]),
        "ETHUSDT": bars(16, [100] * 12 + [100, 200, 100, 400]),
    }
    inputs[constant_symbol] = bars(16, [100] * 16)
    result, _ = calculate(ResearchSpec.create(body("cross_asset", 16)), inputs)
    assert result["cross_asset"]["correlation"] == {
        "value": None,
        "reason": "zero_variance",
        "observation_count": 4,
    }


def test_single_aligned_pair_has_insufficient_correlation_observations():
    source = bars(13, [100] * 13)
    result, _ = calculate(
        ResearchSpec.create(body("cross_asset", 13)), {"BTCUSDT": source, "ETHUSDT": source}
    )
    assert result["cross_asset"]["correlation"] == {
        "value": None,
        "reason": "insufficient_observations",
        "observation_count": 1,
    }


def test_cluster_gap_breaks_windows_then_recovers_using_previous_valid_history():
    prices, volumes = [100] * 340, [1] * 340
    for first in (300, 318):
        prices[first], prices[first + 1] = 200, 100
        volumes[first] = volumes[first + 1] = 10
    source = bars(340, prices, volumes)
    del source[305]
    rows = prepared(source)
    # The first post-gap close cannot form a return. Thirteen closes are needed
    # to recover a 12-return deviation; old valid percentile history survives.
    assert rows[at(306)]["return"] is None
    assert all(rows[at(index)]["volatility"] is None for index in range(306, 318))
    assert rows[at(317)]["volume_multiple"] is None
    assert rows[at(318)]["volatility"] is not None
    assert rows[at(318)]["prior_volatility_count"] == 288
    assert rows[at(318)]["threshold"] == 0
    assert rows[at(318)]["volume_multiple"] == 10
    result, _ = calculate(
        ResearchSpec.create(body("volatility_cluster", 340, 300)), {"BTCUSDT": source}
    )
    assert result["profiles"]["BTCUSDT"]["coverage"]["missing"] == 1
    assert result["cluster_counts"] == {"qualifying": 4, "ineligible": 13, "clusters": 2}
    assert [(event["start"], event["end"]) for event in result["clusters"]] == [
        (at(300), at(302)),
        (at(318), at(320)),
    ]


def test_initial_history_can_use_288_valid_observations_before_a_recent_gap():
    # Missing349 leaves only ten contiguous closes350..359 before start360.
    # The older337 valid volatility observations satisfy the explicit contract.
    prices, volumes = [100] * 366, [1] * 366
    prices[362] = 200
    volumes[362] = volumes[363] = 3
    source = bars(366, prices, volumes)
    del source[349]
    result, _ = calculate(
        ResearchSpec.create(body("volatility_cluster", 366, 360)), {"BTCUSDT": source}
    )
    history = result["history"]["BTCUSDT"]
    assert history["valid_volatility_observations"] == 337
    assert history["threshold_history_start"] == at(61)
    assert result["cluster_counts"] == {"qualifying": 2, "ineligible": 2, "clusters": 1}
    assert result["clusters"][0]["start"] == at(362)
    assert result["clusters"][0]["end"] == at(364)


def test_missing_evaluation_start_is_ineligible_not_a_warmup_error():
    prices, volumes = [100] * 316, [1] * 316
    prices[313] = 200
    volumes[313] = volumes[314] = 10
    source = bars(316, prices, volumes)
    del source[300]
    result, _ = calculate(
        ResearchSpec.create(body("volatility_cluster", 316, 300)), {"BTCUSDT": source}
    )
    assert result["cluster_counts"] == {"qualifying": 2, "ineligible": 13, "clusters": 1}
    assert result["clusters"][0]["start"] == at(313)
    assert result["clusters"][0]["touches_start"] is False


def test_real_qualifying_boundary_pair_is_clipped_and_future_has_no_lookahead():
    prices, volumes = [100] * 330, [1] * 330
    prices[300] = 200
    volumes[300] = volumes[301] = 10
    source = bars(330, prices, volumes)
    prefix = prepared(source[:302])
    # An extreme later regime cannot enter earlier thresholds or qualifications.
    future = bars(330, prices[:302] + [999999] * 28, volumes[:302] + [999999] * 28)
    changed = prepared(future)
    assert prefix[at(300)] == changed[at(300)]
    assert prefix[at(301)] == changed[at(301)]
    boundary, _ = calculate(
        ResearchSpec.create(body("volatility_cluster", 302, 300)), {"BTCUSDT": source[:302]}
    )
    assert boundary["clusters"][0]["bar_count"] == 2
    assert boundary["clusters"][0]["touches_start"] is True
    assert boundary["clusters"][0]["touches_end"] is True
    # Bar300 is now warm-up; it cannot complete the qualifying singleton301.
    clipped, _ = calculate(
        ResearchSpec.create(body("volatility_cluster", 303, 301)), {"BTCUSDT": source[:303]}
    )
    assert prefix[at(300)]["qualifies"] is True
    assert clipped["cluster_counts"]["qualifying"] == 1
    assert clipped["clusters"] == []
