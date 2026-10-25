"""Hand-derived checks for the independent retained-data acceptance reference."""

import importlib.util
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "scripts" / "r4_reference.py"
loader = importlib.util.spec_from_file_location("r4_independent_reference", path)
assert loader is not None and loader.loader is not None
reference = importlib.util.module_from_spec(loader)
loader.loader.exec_module(reference)


def bars(closes: list[str], volumes: list[str] | None = None) -> list[dict[str, object]]:
    beginning = datetime(2025, 1, 1, tzinfo=UTC)
    result = []
    for index, close in enumerate(closes):
        when = beginning + timedelta(minutes=5 * index)
        volume = volumes[index] if volumes else "1"
        result.append(
            {
                "start": reference.stamp(when),
                "end": reference.stamp(when + reference.STEP),
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "base_volume": volume,
                "quote_volume": str(Decimal(close) * Decimal(volume)),
                "trade_count": 1,
            }
        )
    return result


def test_reference_profile_hand_derived_sample_deviation_and_drawdown() -> None:
    rows = bars(["100"] * 12 + ["100", "110", "99"])
    start, end = reference.instant(rows[12]["start"]), reference.instant(rows[-1]["end"])
    result = reference.profile(rows, start, end)
    assert result["return_mean"]["value"] == "0.000000000000000000"
    assert result["return_stddev"]["value"] == "0.100000000000000000"
    assert result["sharpe"]["value"] == "0.000000000000000000"
    assert result["drawdown"]["value"] == "-0.100000000000000000"
    assert result["close_change"]["value"] == "-0.010000000000000000"
    assert result["vwap"]["value"] == "103.000000000000000000"
    assert [spike["start"] for spike in result["volume_spikes"]] == [
        row["start"] for row in rows[12:]
    ]


def test_reference_missing_bar_breaks_return_and_volume_history() -> None:
    rows = bars(["100"] * 15)
    start, end = reference.instant(rows[12]["start"]), reference.instant(rows[-1]["end"])
    del rows[13]
    result = reference.profile(rows, start, end)
    assert result["coverage"]["missing"] == 1
    assert result["undefined_returns"] == 1
    assert result["undefined_volume_windows"] == 1
    assert result["return_mean"]["observation_count"] == 1
    assert result["return_stddev"]["reason"] == "insufficient_observations"


def test_reference_cross_asset_identical_returns_have_unit_correlation() -> None:
    rows = bars(["100"] * 12 + ["100", "110", "99"])
    start, end = reference.instant(rows[12]["start"]), reference.instant(rows[-1]["end"])
    result = reference.cross_asset({"BTCUSDT": rows, "ETHUSDT": rows}, start, end)
    assert result["correlation"]["value"] == "1.000000000000000000"
    assert result["close_change_difference"]["value"] == "0.000000000000000000"


def test_reference_cluster_two_bar_fixture_and_no_warmup_singleton() -> None:
    rows = bars(["100"] * 300 + ["200", "100", "100"], ["1"] * 300 + ["10", "10", "1"])
    start, end = reference.instant(rows[300]["start"]), reference.instant(rows[-1]["end"])
    result = reference.clusters(rows, start, end)
    assert result["cluster_count"] == 1
    event = result["clusters"][0]
    assert event["bar_count"] == 2
    assert event["first_threshold"] == "0.000000000000000000"
    assert event["base_volume"] == "20.000000000000000000"
    assert event["max_volume_multiple"] == "10.000000000000000000"
    with localcontext(reference.CONTEXT):
        assert event["max_volatility"] == reference.text((Decimal(59) / 528).sqrt())
    assert event["touches_start"] is True
    assert event["touches_end"] is False
    # Moving evaluation after the first qualifying bar leaves a singleton.
    clipped = reference.clusters(rows, start + reference.STEP, end)
    assert clipped["qualifying_bars"] == 1
    assert clipped["cluster_count"] == 0
