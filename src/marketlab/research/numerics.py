"""Timestamp-ordered Decimal80 descriptive statistics; no inference or strategies."""

from collections import deque
from datetime import timedelta
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from threading import Event
from typing import Any

from .spec import NUMERICS, ResearchError, ResearchSpec, utc

D = Decimal
CONTEXT = Context(prec=80, rounding=ROUND_HALF_EVEN)
STEP = timedelta(minutes=5)


def text(value: Decimal) -> str:
    result = value.quantize(D("1e-18"))
    return format(abs(result) if result == 0 else result, ".18f")


def stat(
    value: Decimal | None, n: int, reason: str = "insufficient_observations"
) -> dict[str, Any]:
    return {
        "value": None if value is None else text(value),
        "reason": reason if value is None else None,
        "observation_count": n,
    }


def mean(values: list[Decimal]) -> Decimal:
    return sum(values, D(0)) / len(values)


def deviation(values: list[Decimal]) -> Decimal:
    average = mean(values)
    return (sum(((x - average) ** 2 for x in values), D(0)) / (len(values) - 1)).sqrt()


def quantile(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    h = D(len(values) - 1) * D("0.9")
    low = int(h)
    return ordered[low] + (ordered[min(low + 1, len(values) - 1)] - ordered[low]) * (h - low)


def prepare(bars: list[dict[str, Any]], cancelled: Event | None = None) -> list[dict[str, Any]]:
    ordered = sorted(bars, key=lambda b: b["start"])
    if len({bar["start"] for bar in ordered}) != len(ordered):
        raise ResearchError("Duplicate analytical buckets")
    result = []
    prior: dict[str, Any] | None = None
    returns: deque[Decimal] = deque(maxlen=12)
    volumes: deque[Decimal] = deque(maxlen=12)
    volatility: deque[Decimal] = deque(maxlen=288)
    for bar in ordered:
        if cancelled is not None and cancelled.is_set():
            raise ResearchError("Research calculation cancelled", 503)
        now = utc(bar["start"])
        if prior is None or now - prior["time"] != STEP:
            returns.clear()
            volumes.clear()
        current: dict[str, Any] = {**bar, "time": now}
        for name in ("open", "high", "low", "close", "base_volume", "quote_volume"):
            current[name] = D(bar[name])
        current["return"] = None
        current["log_return"] = None
        if prior is not None and now - prior["time"] == STEP:
            ratio = current["close"] / prior["close"]
            current["return"] = ratio - 1
            current["log_return"] = ratio.ln()
            returns.append(current["return"])
        current["volume_multiple"] = (
            current["base_volume"] / mean(list(volumes))
            if len(volumes) == 12 and sum(volumes, D(0))
            else None
        )
        current["volatility"] = deviation(list(returns)) if len(returns) == 12 else None
        current["threshold"] = quantile(list(volatility)) if len(volatility) == 288 else None
        current["prior_volatility_count"] = len(volatility)
        current["qualifies"] = (
            current["volatility"] is not None
            and current["threshold"] is not None
            and current["volume_multiple"] is not None
            and current["volatility"] > current["threshold"]
            and current["volume_multiple"] > 2
        )
        if current["volatility"] is not None:
            volatility.append(current["volatility"])
        volumes.append(current["base_volume"])
        result.append(current)
        prior = current
    return result


def profile(items: list[dict[str, Any]], spec: ResearchSpec) -> dict[str, Any]:
    expected = int((spec.end - spec.start).total_seconds()) // 300
    n = len(items)
    coverage = {
        "expected": expected,
        "observed": n,
        "missing": expected - n,
        "incomplete_grid": n != expected,
    }
    returns = [b["return"] for b in items if b["return"] is not None]
    average = mean(returns) if returns else None
    std = deviation(returns) if len(returns) >= 2 else None
    base = sum((b["base_volume"] for b in items), D(0))
    quote = sum((b["quote_volume"] for b in items), D(0))
    drawdown = None
    if items:
        peak = items[0]["close"]
        drawdown = D(0)
        for bar in items:
            peak = max(peak, bar["close"])
            drawdown = min(drawdown, bar["close"] / peak - 1)
    spikes = sorted(
        (b for b in items if b["volume_multiple"] is not None),
        key=lambda b: (-b["volume_multiple"], b["start"]),
    )[:3]
    return {
        "coverage": coverage,
        "first_start": items[0]["start"] if items else None,
        "last_start": items[-1]["start"] if items else None,
        "first_open": stat(items[0]["open"] if items else None, n),
        "last_close": stat(items[-1]["close"] if items else None, n),
        "high": stat(max((b["high"] for b in items), default=None), n),
        "low": stat(min((b["low"] for b in items), default=None), n),
        "base_volume": text(base),
        "quote_volume": text(quote),
        "trade_count": sum(b["trade_count"] for b in items),
        "vwap": stat(quote / base if base else None, n, "zero_denominator"),
        "close_change": stat(items[-1]["close"] / items[0]["close"] - 1 if items else None, n),
        "drawdown": stat(drawdown, n),
        "return_mean": stat(average, len(returns)),
        "return_stddev": stat(std, len(returns)),
        "sharpe": stat(
            average / std if std and average is not None else None,
            len(returns),
            "zero_variance" if std == 0 else "insufficient_observations",
        ),
        "volume_spikes": [
            {"start": b["start"], "multiple": text(b["volume_multiple"])} for b in spikes
        ],
        "undefined_returns": n - len(returns),
        "undefined_volume_windows": sum(b["volume_multiple"] is None for b in items),
    }


def clusters(items: list[dict[str, Any]], spec: ResearchSpec) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    group: list[dict[str, Any]] = []

    def finish() -> None:
        if len(group) < 2:
            return
        # Groups already have stable time order; max retains the earliest tie.
        peak = max(group, key=lambda b: b["volatility"])
        volume = max(group, key=lambda b: b["volume_multiple"])
        result.append(
            {
                "start": group[0]["start"],
                "end": group[-1]["end"],
                "bar_count": len(group),
                "base_volume": text(sum((b["base_volume"] for b in group), D(0))),
                "quote_volume": text(sum((b["quote_volume"] for b in group), D(0))),
                "max_volatility": text(peak["volatility"]),
                "max_volatility_start": peak["start"],
                "max_volume_multiple": text(volume["volume_multiple"]),
                "max_volume_multiple_start": volume["start"],
                "first_threshold": text(group[0]["threshold"]),
                "touches_start": group[0]["time"] == spec.start,
                "touches_end": group[-1]["time"] + STEP == spec.end,
            }
        )

    for bar in items:
        if not bar["qualifies"] or (group and bar["time"] - group[-1]["time"] != STEP):
            finish()
            group = []
        if bar["qualifies"]:
            group.append(bar)
    finish()
    return result


def calculate(
    spec: ResearchSpec, inputs: dict[str, list[dict[str, Any]]], cancelled: Event | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    with localcontext(CONTEXT):
        data = {symbol: prepare(inputs[symbol], cancelled) for symbol in spec.symbols}
        selected: dict[str, list[dict[str, Any]]] = {}
        for symbol, items in data.items():
            history = {b["time"] for b in items if b["time"] < spec.start}
            if spec.workflow != "volatility_cluster" and any(
                spec.start - STEP * k not in history for k in range(1, 13)
            ):
                raise ResearchError("Insufficient contiguous initial history", 409)
            selected[symbol] = [b for b in items if spec.start <= b["time"] < spec.end]
            if spec.workflow == "volatility_cluster":
                valid_history = sum(
                    b["volatility"] is not None for b in items if b["time"] < spec.start
                )
                if valid_history < 288:
                    raise ResearchError("Insufficient initial volatility history", 409)
        result: dict[str, Any] = {
            "schema": "research-results-v1",
            "definition": NUMERICS,
            "workflow": spec.workflow,
            "start": spec.body()["start"],
            "end": spec.body()["end"],
            "history_start": spec.body()["history_start"],
            "history": {
                s: {
                    "observed_bars": len([b for b in bars if b["time"] < spec.start]),
                    "first_observed_start": next(
                        (b["start"] for b in bars if b["time"] < spec.start), None
                    ),
                    "last_observed_start": next(
                        (b["start"] for b in reversed(bars) if b["time"] < spec.start), None
                    ),
                    "valid_volatility_observations": sum(
                        b["volatility"] is not None for b in bars if b["time"] < spec.start
                    ),
                    "threshold_history_start": next(
                        (
                            b["start"]
                            for b in [
                                x
                                for x in bars
                                if x["time"] < spec.start and x["volatility"] is not None
                            ][-288:]
                        ),
                        None,
                    ),
                }
                for s, bars in data.items()
            },
            "interval": "5m",
            "units": {
                "price": "USDT",
                "quote_volume": "USDT",
                "returns": "ratio",
                "base_volume": {s: s.removesuffix("USDT") for s in spec.symbols},
            },
            "profiles": {s: profile(items, spec) for s, items in selected.items()},
        }
        if spec.workflow == "cross_asset":
            by_time = [{b["time"]: b for b in selected[s]} for s in spec.symbols]
            common = sorted(set(by_time[0]) & set(by_time[1]))
            pairs = [
                (by_time[0][t]["log_return"], by_time[1][t]["log_return"])
                for t in common
                if by_time[0][t]["log_return"] is not None
                and by_time[1][t]["log_return"] is not None
            ]
            corr = None
            reason = "insufficient_observations"
            if len(pairs) >= 2:
                xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
                mx, my = mean(xs), mean(ys)
                xx = sum(((x - mx) ** 2 for x in xs), D(0))
                yy = sum(((y - my) ** 2 for y in ys), D(0))
                if xx and yy:
                    corr = sum(((x - mx) * (y - my) for x, y in pairs), D(0)) / (xx * yy).sqrt()
                else:
                    reason = "zero_variance"
            difference = None
            if common:
                changes = [
                    table[common[-1]]["close"] / table[common[0]]["close"] - 1 for table in by_time
                ]
                difference = changes[0] - changes[1]
            result["cross_asset"] = {
                "common_bar_count": len(common),
                "aligned_return_count": len(pairs),
                "correlation": stat(corr, len(pairs), reason),
                "close_change_difference": stat(difference, len(common)),
                "first_common_start": by_time[0][common[0]]["start"] if common else None,
                "last_common_start": by_time[0][common[-1]]["start"] if common else None,
            }
        if spec.workflow == "volatility_cluster":
            items = selected[spec.symbols[0]]
            result["clusters"] = clusters(items, spec)
            result["cluster_counts"] = {
                "qualifying": sum(bool(b["qualifies"]) for b in items),
                "ineligible": int((spec.end - spec.start).total_seconds()) // 300
                - len(items)
                + sum(
                    b["threshold"] is None
                    or b["volatility"] is None
                    or b["volume_multiple"] is None
                    for b in items
                ),
                "clusters": len(result["clusters"]),
            }
        summary = {
            "schema": "research-summary-v1",
            "definition": NUMERICS,
            "workflow": spec.workflow,
            "start": result["start"],
            "end": result["end"],
            "history_start": result["history_start"],
            "history": result["history"],
            "interval": "5m",
            "units": result["units"],
        }
        if "profile" in spec.metrics:
            summary["profiles"] = result["profiles"]
        if spec.workflow == "cross_asset":
            summary["cross_asset"] = {
                k: v
                for k, v in result["cross_asset"].items()
                if k in {"common_bar_count", "aligned_return_count"} or k in spec.metrics
            }
        if "clusters" in spec.metrics:
            summary["clusters"] = result["clusters"]
            summary["cluster_counts"] = result["cluster_counts"]
        return result, summary
