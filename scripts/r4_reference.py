"""Independent R4 acceptance reference; no production research calculations.

``scan`` freshly streams all retained trades through the independent R3 reference
into a new R4 evidence directory. ``numerics`` calculates the five full-period
R4 reference outputs from those bars. Neither command writes dataset artifacts,
historical R3 evidence, database rows, or Redis keys.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from pathlib import Path
from typing import Any

STEP = timedelta(minutes=5)
CONTEXT = Context(prec=80, rounding=ROUND_HALF_EVEN)
UNIT = Decimal("0.000000000000000001")
BASE = Path("artifacts/r4/reference-data")


def encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def text(value: Decimal) -> str:
    rounded = value.quantize(UNIT)
    return format(abs(rounded) if rounded == 0 else rounded, ".18f")


def statistic(value: Decimal | None, count: int, reason: str | None = None) -> dict[str, Any]:
    return {
        "value": None if value is None else text(value),
        "reason": reason,
        "observation_count": count,
    }


def average(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal(0)) / Decimal(len(values))


def deviation(values: list[Decimal]) -> Decimal:
    center = average(values)
    return (sum(((value - center) ** 2 for value in values), Decimal(0)) / (len(values) - 1)).sqrt()


def timeline(rows: list[dict[str, Any]]) -> dict[datetime, dict[str, Any]]:
    result = {instant(row["start"]): row for row in rows}
    assert len(result) == len(rows), "duplicate bar timestamp"
    return dict(sorted(result.items()))


def rolling(
    bars: dict[datetime, dict[str, Any]],
) -> tuple[
    dict[datetime, Decimal],
    dict[datetime, Decimal],
    dict[datetime, Decimal],
    dict[datetime, Decimal],
]:
    simple, logs, multiples, volatility = {}, {}, {}, {}
    for when, bar in bars.items():
        prior = bars.get(when - STEP)
        if prior is not None:
            ratio = Decimal(bar["close"]) / Decimal(prior["close"])
            simple[when] = ratio - 1
            logs[when] = ratio.ln()
        previous = [bars.get(when - index * STEP) for index in range(1, 13)]
        if all(item is not None for item in previous):
            baseline = average(
                [Decimal(item["base_volume"]) for item in previous if item is not None]
            )
            if baseline != 0:
                multiples[when] = Decimal(bar["base_volume"]) / baseline
        values = [simple.get(when - index * STEP) for index in range(12)]
        if all(value is not None for value in values):
            # Chronological arithmetic order is part of the numerical contract.
            volatility[when] = deviation([value for value in reversed(values) if value is not None])
    return simple, logs, multiples, volatility


def profile(rows: list[dict[str, Any]], start: datetime, end: datetime) -> dict[str, Any]:
    with localcontext(CONTEXT):
        bars = timeline(rows)
        returns, _, multiples, _ = rolling(bars)
        selected = [(when, bar) for when, bar in bars.items() if start <= when < end]
        expected = int((end - start) / STEP)
        prices = [Decimal(bar["close"]) for _, bar in selected]
        values = [value for when, value in returns.items() if start <= when < end]
        count = len(values)
        total_base = sum((Decimal(bar["base_volume"]) for _, bar in selected), Decimal(0))
        total_quote = sum((Decimal(bar["quote_volume"]) for _, bar in selected), Decimal(0))
        peaks, maximum = [], Decimal(0)
        for value in prices:
            maximum = max(maximum, value)
            peaks.append(value / maximum - 1)
        mean = average(values) if values else None
        stddev = deviation(values) if count >= 2 else None
        ranked = sorted(
            ((when, ratio) for when, ratio in multiples.items() if start <= when < end),
            key=lambda item: (-item[1], item[0]),
        )[:3]
        undefined = "insufficient_observations"
        return {
            "coverage": {
                "expected": expected,
                "observed": len(selected),
                "missing": expected - len(selected),
                "incomplete_grid": len(selected) != expected,
            },
            "first_open": statistic(
                Decimal(selected[0][1]["open"]) if selected else None,
                len(selected),
                None if selected else undefined,
            ),
            "first_start": None if not selected else stamp(selected[0][0]),
            "last_close": statistic(
                Decimal(selected[-1][1]["close"]) if selected else None,
                len(selected),
                None if selected else undefined,
            ),
            "last_start": None if not selected else stamp(selected[-1][0]),
            "high": statistic(
                max((Decimal(bar["high"]) for _, bar in selected), default=None),
                len(selected),
                None if selected else undefined,
            ),
            "low": statistic(
                min((Decimal(bar["low"]) for _, bar in selected), default=None),
                len(selected),
                None if selected else undefined,
            ),
            "base_volume": text(total_base),
            "quote_volume": text(total_quote),
            "trade_count": sum(bar["trade_count"] for _, bar in selected),
            "vwap": statistic(
                total_quote / total_base if total_base else None,
                len(selected),
                None if total_base else "zero_denominator",
            ),
            "close_change": statistic(
                prices[-1] / prices[0] - 1 if prices else None,
                len(prices),
                None if prices else undefined,
            ),
            "drawdown": statistic(
                min(peaks) if peaks else None, len(prices), None if prices else undefined
            ),
            "return_mean": statistic(mean, count, None if mean is not None else undefined),
            "return_stddev": statistic(stddev, count, None if stddev is not None else undefined),
            "sharpe": statistic(
                mean / stddev if mean is not None and stddev else None,
                count,
                undefined if stddev is None else "zero_variance" if not stddev else None,
            ),
            "volume_spikes": [
                {"start": stamp(when), "multiple": text(ratio)} for when, ratio in ranked
            ],
            "undefined_volume_windows": len(selected)
            - sum(start <= when < end for when in multiples),
            "undefined_returns": len(selected) - count,
        }


def cross_asset(
    rows: dict[str, list[dict[str, Any]]], start: datetime, end: datetime
) -> dict[str, Any]:
    with localcontext(CONTEXT):
        left, right = (timeline(rows[symbol]) for symbol in ("BTCUSDT", "ETHUSDT"))
        _, left_log, _, _ = rolling(left)
        _, right_log, _, _ = rolling(right)
        common = sorted(when for when in left.keys() & right.keys() if start <= when < end)
        pairs = sorted(when for when in left_log.keys() & right_log.keys() if start <= when < end)
        x, y = [left_log[when] for when in pairs], [right_log[when] for when in pairs]
        correlation = None
        reason = "insufficient_observations"
        if len(pairs) >= 2:
            mean_x, mean_y = average(x), average(y)
            dx, dy = [value - mean_x for value in x], [value - mean_y for value in y]
            denominator = (
                sum((value * value for value in dx), Decimal(0))
                * sum((value * value for value in dy), Decimal(0))
            ).sqrt()
            if denominator:
                correlation = (
                    sum((a * b for a, b in zip(dx, dy, strict=True)), Decimal(0)) / denominator
                )
                reason = None
            else:
                reason = "zero_variance"
        difference = None
        if common:
            first, last = common[0], common[-1]
            difference = (Decimal(left[last]["close"]) / Decimal(left[first]["close"]) - 1) - (
                Decimal(right[last]["close"]) / Decimal(right[first]["close"]) - 1
            )
        return {
            "common_bar_count": len(common),
            "aligned_return_count": len(pairs),
            "correlation": statistic(correlation, len(pairs), reason),
            "close_change_difference": statistic(
                difference,
                len(common),
                None if difference is not None else "insufficient_observations",
            ),
            "first_common_start": stamp(common[0]) if common else None,
            "last_common_start": stamp(common[-1]) if common else None,
        }


def clusters(rows: list[dict[str, Any]], start: datetime, end: datetime) -> dict[str, Any]:
    with localcontext(CONTEXT):
        bars = timeline(rows)
        _, _, multiples, volatility = rolling(bars)
        previous: deque[Decimal] = deque(maxlen=288)
        events, pending = [], []
        eligible = qualified = 0
        first_previous = [when for when in volatility if when < start][-288:]
        assert len(first_previous) == 288, "insufficient initial volatility history"

        def finish() -> None:
            if len(pending) >= 2:
                maximum_vol = max(pending, key=lambda item: item[1])
                maximum_multiple = max(pending, key=lambda item: item[2])
                events.append(
                    {
                        "start": stamp(pending[0][0]),
                        "end": stamp(pending[-1][0] + STEP),
                        "bar_count": len(pending),
                        "base_volume": text(
                            sum(
                                (Decimal(bars[item[0]]["base_volume"]) for item in pending),
                                Decimal(0),
                            )
                        ),
                        "quote_volume": text(
                            sum(
                                (Decimal(bars[item[0]]["quote_volume"]) for item in pending),
                                Decimal(0),
                            )
                        ),
                        "max_volatility": text(maximum_vol[1]),
                        "max_volatility_start": stamp(maximum_vol[0]),
                        "max_volume_multiple": text(maximum_multiple[2]),
                        "max_volume_multiple_start": stamp(maximum_multiple[0]),
                        "first_threshold": text(pending[0][3]),
                        "touches_start": pending[0][0] == start,
                        "touches_end": pending[-1][0] + STEP == end,
                    }
                )
            pending.clear()

        # Visit the complete grid so a missing bar breaks a run immediately.
        when = min(bars)
        while when < end:
            current = volatility.get(when)
            if start <= when:
                multiple = multiples.get(when)
                qualifies = False
                if current is not None and multiple is not None and len(previous) == 288:
                    eligible += 1
                    ordered = sorted(previous)
                    threshold = ordered[258] + (ordered[259] - ordered[258]) * Decimal("0.3")
                    qualifies = current > threshold and multiple > 2
                    if qualifies:
                        qualified += 1
                        pending.append((when, current, multiple, threshold))
                if not qualifies:
                    finish()
            if current is not None:
                previous.append(current)
            when += STEP
        finish()
        return {
            "clusters": events,
            "cluster_count": len(events),
            "qualifying_bars": qualified,
            "eligible_bars": eligible,
            "ineligible_bars": int((end - start) / STEP) - eligible,
            "initial_volatility_history_start": stamp(first_previous[0]),
        }


def scan_partition(record: dict[str, Any]) -> dict[str, Any]:
    # Existing reference streams source rows using scaled integers, not DuckDB.
    import r3_acceptance

    r3_acceptance.BASE = BASE
    return r3_acceptance.reference_partition(record)


def scan() -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    records = json.loads(Path("artifacts/r2/catalog-final.json").read_text())["catalog"]
    assert len(records) == 62 and sum(item["row_count"] for item in records) == 230_311_900
    started = time.perf_counter()
    completed = []
    with ProcessPoolExecutor(max_workers=2) as executor:
        for result in executor.map(scan_partition, records):
            completed.append(result)
            (BASE / "progress.json").write_text(json.dumps(completed, indent=2))
            print(json.dumps(result), flush=True)
    evidence = {
        "source": "fresh independent scaled-integer streaming of all retained trades",
        "rows": sum(item["rows"] for item in completed),
        "partitions": completed,
        "seconds": time.perf_counter() - started,
    }
    (BASE / "complete.json").write_text(json.dumps(evidence, indent=2))


def reference_payload(
    spec: dict[str, Any], rows: dict[str, list[dict[str, Any]]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return contract-shaped reference payloads without production imports."""
    start, end, history = (instant(spec[key]) for key in ("start", "end", "history_start"))
    symbols = sorted(spec["symbols"])
    inputs = {
        symbol: [bar for bar in rows[symbol] if history <= instant(bar["start"]) < end]
        for symbol in symbols
    }
    if spec["workflow"] != "volatility_cluster":
        for bars in inputs.values():
            stamps = {instant(bar["start"]) for bar in bars}
            assert all(start - index * STEP in stamps for index in range(1, 13))
    histories = {}
    with localcontext(CONTEXT):
        for symbol, source in inputs.items():
            bars = timeline(source)
            before = [when for when in bars if when < start]
            _, _, _, volatility = rolling(bars)
            valid = [when for when in volatility if when < start]
            histories[symbol] = {
                "observed_bars": len(before),
                "first_observed_start": stamp(before[0]) if before else None,
                "last_observed_start": stamp(before[-1]) if before else None,
                "valid_volatility_observations": len(valid),
                "threshold_history_start": stamp(valid[-288:][0]) if valid else None,
            }
    result = {
        "schema": "research-results-v1",
        "definition": "research-numerics-v1",
        "workflow": spec["workflow"],
        "start": stamp(start),
        "end": stamp(end),
        "history_start": stamp(history),
        "history": histories,
        "interval": "5m",
        "units": {
            "price": "USDT",
            "quote_volume": "USDT",
            "returns": "ratio",
            "base_volume": {symbol: symbol.removesuffix("USDT") for symbol in symbols},
        },
        "profiles": {symbol: profile(inputs[symbol], start, end) for symbol in symbols},
    }
    if spec["workflow"] == "cross_asset":
        result["cross_asset"] = cross_asset(inputs, start, end)
    if spec["workflow"] == "volatility_cluster":
        calculation = clusters(inputs[symbols[0]], start, end)
        result["clusters"] = calculation["clusters"]
        result["cluster_counts"] = {
            "qualifying": calculation["qualifying_bars"],
            "ineligible": calculation["ineligible_bars"],
            "clusters": calculation["cluster_count"],
        }
    summary = {
        key: result[key]
        for key in (
            "definition",
            "workflow",
            "start",
            "end",
            "history_start",
            "history",
            "interval",
            "units",
        )
    }
    summary["schema"] = "research-summary-v1"
    if "profile" in spec["metrics"]:
        summary["profiles"] = result["profiles"]
    if spec["workflow"] == "cross_asset":
        summary["cross_asset"] = {
            key: value
            for key, value in result["cross_asset"].items()
            if key in spec["metrics"] or key in {"common_bar_count", "aligned_return_count"}
        }
    if "clusters" in spec["metrics"]:
        summary["clusters"] = result["clusters"]
        summary["cluster_counts"] = result["cluster_counts"]
    return result, summary


def full_reference() -> None:
    records = json.loads(Path("artifacts/r2/catalog-final.json").read_text())["catalog"]
    rows: dict[str, list[dict[str, Any]]] = {"BTCUSDT": [], "ETHUSDT": []}
    evidence = json.loads((BASE / "complete.json").read_text())
    assert evidence["rows"] == 230_311_900 and len(evidence["partitions"]) == 62
    for record in sorted(records, key=lambda item: (item["trade_date"], item["symbol"])):
        reference = json.loads(
            (BASE / f"reference-{record['dataset_version_id']}.json").read_text()
        )
        assert reference["manifest_sha256"] == record["manifest_sha256"]
        assert reference["version"] == record["dataset_version_id"]
        assert reference["rows"] == record["row_count"]
        rows[record["symbol"]].extend(reference["five"])
    assert sum(len(value) for value in rows.values()) == 17_856
    beginning = datetime(2025, 1, 1, 1, tzinfo=UTC)
    ending = datetime(2025, 2, 1, tzinfo=UTC)
    cluster_start = datetime(2025, 1, 2, 1, tzinfo=UTC)
    results = {
        "profiles": {symbol: profile(value, beginning, ending) for symbol, value in rows.items()},
        "cross_asset": cross_asset(rows, beginning, ending),
        "clusters": {
            symbol: clusters(value, cluster_start, ending) for symbol, value in rows.items()
        },
    }
    output = Path("artifacts/r4/reference-numerics.json")
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "file": str(output),
                "sha256": hashlib.sha256(encoded(results)).hexdigest(),
                "bars": sum(len(value) for value in rows.values()),
                "clusters": {
                    symbol: value["cluster_count"] for symbol, value in results["clusters"].items()
                },
            }
        ),
        flush=True,
    )
    workflows = []
    for workflow, selected in (
        ("market_profile", ["BTCUSDT"]),
        ("market_profile", ["ETHUSDT"]),
        ("cross_asset", ["BTCUSDT", "ETHUSDT"]),
        ("volatility_cluster", ["BTCUSDT"]),
        ("volatility_cluster", ["ETHUSDT"]),
    ):
        spec = {
            "schema": "research-spec-v1",
            "workflow": workflow,
            "symbols": selected,
            "dataset_versions": sorted(
                record["dataset_version_id"] for record in records if record["symbol"] in selected
            ),
            "start": stamp(cluster_start if workflow == "volatility_cluster" else beginning),
            "end": stamp(ending),
            "history_start": "2025-01-01T00:00:00Z",
            "interval": "5m",
            "metrics": ["profile", "clusters"]
            if workflow == "volatility_cluster"
            else ["profile", "correlation", "close_change_difference"]
            if workflow == "cross_asset"
            else ["profile"],
            "parameters": {},
            "predicates": {"volatility_quantile": "0.9", "volume_multiple": "2", "min_bars": 2}
            if workflow == "volatility_cluster"
            else {},
        }
        expected_result, expected_summary = reference_payload(spec, rows)
        workflows.append(
            {
                "spec": spec,
                "results": expected_result,
                "summary": expected_summary,
                "results_sha256": hashlib.sha256(encoded(expected_result)).hexdigest(),
                "summary_sha256": hashlib.sha256(encoded(expected_summary)).hexdigest(),
            }
        )
    Path("artifacts/r4/reference-workflows.json").write_text(
        json.dumps(workflows, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("scan", "numerics"))
    options = parser.parse_args()
    if options.action == "scan":
        scan()
    else:
        full_reference()
