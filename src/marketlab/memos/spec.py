"""Versioned facts, validated claim choices and exact placeholder rendering."""

import re
from decimal import Decimal
from typing import Any

from marketlab.analytics.cache import canonical
from marketlab.copilot.spec import digest
from marketlab.research.spec import ResearchError

FACTS = "memo-facts-v1"
RENDERER = "memo-renderer-v1"
KINDS = ("scope", "findings", "limitations")
REASONS = {
    "insufficient_observations",
    "missing_contiguous_history",
    "zero_denominator",
    "zero_variance",
}


def facts(summary: dict[str, Any]) -> dict[str, Any]:
    """Build bounded selected-metric facts; cluster event arrays are deliberately omitted."""
    if summary.get("schema") != "research-summary-v1" or summary.get("interval") != "5m":
        raise ResearchError("Unsupported memo summary")
    if summary.get("workflow") not in {"market_profile", "cross_asset", "volatility_cluster"}:
        raise ResearchError("Unsupported memo workflow")
    values: dict[str, str] = {}

    def add(name: str, value: Any) -> str:
        if value is None or type(value) not in (str, int):
            raise ResearchError("Invalid memo fact")
        rendered = str(value)
        if not rendered or len(rendered.encode()) > 256 or any(c in rendered for c in "\r\n<>{}"):
            raise ResearchError("Invalid memo fact")
        values[name] = rendered
        return "{{" + name + "}}"

    def stat(name: str, value: Any, unit: str) -> str:
        if not isinstance(value, dict) or set(value) != {"value", "reason", "observation_count"}:
            raise ResearchError("Invalid memo statistic")
        count = value["observation_count"]
        if type(count) is not int or count < 0:
            raise ResearchError("Invalid memo observation count")
        if value["value"] is None:
            if value["reason"] not in REASONS:
                raise ResearchError("Invalid memo null reason")
            return (
                "unavailable ("
                + add(name + "_reason", value["reason"])
                + "; observations "
                + add(name + "_n", count)
                + ")"
            )
        if (
            value["reason"] is not None
            or not isinstance(value["value"], str)
            or not re.fullmatch(r"-?[0-9]+\.[0-9]{18}", value["value"])
        ):
            raise ResearchError("Invalid memo decimal")
        return (
            add(name, value["value"])
            + " "
            + unit
            + " (observations "
            + add(name + "_n", count)
            + ")"
        )

    symbols = sorted(summary["history"])
    if not symbols or any(s not in {"BTCUSDT", "ETHUSDT"} for s in symbols):
        raise ResearchError("Invalid memo symbols")
    scope = (
        "AI-generated research memo. "
        + ", ".join(symbols)
        + " evaluation ["
        + add("start", summary["start"])
        + ", "
        + add("end", summary["end"])
        + ") uses five-minute bars; warm-up begins "
        + add("history_start", summary["history_start"])
        + " and is excluded from evaluation totals."
    )
    finding: list[str] = []
    missing = False
    for symbol, profile in sorted(summary.get("profiles", {}).items()):
        if symbol not in symbols:
            raise ResearchError("Invalid memo profile symbol")
        coverage = profile["coverage"]
        counts = [coverage[n] for n in ("expected", "observed", "missing")]
        if any(type(n) is not int or n < 0 for n in counts) or counts[0] != counts[1] + counts[2]:
            raise ResearchError("Invalid memo coverage")
        if type(coverage["incomplete_grid"]) is not bool or coverage["incomplete_grid"] != (
            counts[2] != 0
        ):
            raise ResearchError("Invalid memo coverage")
        missing |= bool(counts[2])
        scope += (
            " "
            + symbol
            + " coverage: "
            + add(symbol + "_observed", counts[1])
            + " observed of "
            + add(symbol + "_expected", counts[0])
            + " expected, "
            + add(symbol + "_missing", counts[2])
            + " missing."
        )
        finding.append(
            symbol
            + " VWAP is "
            + stat(symbol + "_vwap", profile["vwap"], "USDT")
            + "; close change is "
            + stat(symbol + "_change", profile["close_change"], "ratio")
            + "; drawdown is "
            + stat(symbol + "_drawdown", profile["drawdown"], "ratio")
            + "; the unannualized mean/deviation Sharpe proxy is "
            + stat(symbol + "_sharpe", profile["sharpe"], "ratio")
            + "."
        )
    cross = summary.get("cross_asset")
    if cross is not None:
        finding.append(
            "Cross-asset aligned returns: "
            + add("aligned_returns", cross["aligned_return_count"])
            + "; common bars: "
            + add("common_bars", cross["common_bar_count"])
            + "."
        )
        if "correlation" in cross:
            value = cross["correlation"]
            finding.append(
                "Aligned log-return Pearson correlation is "
                + stat("correlation", value, "ratio")
                + "."
            )
            if value["value"] is not None:
                number = Decimal(value["value"])
                finding.append(
                    "The measured association is "
                    + ("positive" if number > 0 else "negative" if number < 0 else "zero")
                    + "."
                )
        if "close_change_difference" in cross:
            finding.append(
                "BTC-minus-ETH close-change difference at common endpoints is "
                + stat("difference", cross["close_change_difference"], "ratio")
                + "."
            )
    if "cluster_counts" in summary:
        counts = summary["cluster_counts"]
        if any(
            type(counts[n]) is not int or counts[n] < 0
            for n in ("clusters", "qualifying", "ineligible")
        ):
            raise ResearchError("Invalid memo cluster counts")
        finding.append(
            "Detected clusters: "
            + add("clusters", counts["clusters"])
            + "; qualifying evaluation bars: "
            + add("qualifying", counts["qualifying"])
            + "; ineligible evaluation bars: "
            + add("ineligible", counts["ineligible"])
            + "."
        )
    if not finding:
        raise ResearchError("Memo selected findings unavailable")
    limits = (
        "These are descriptive asset statistics, not strategy returns, causal evidence, "
        "forecasts or trading recommendations. Ratios are not percent-scaled. "
        "Undefined statistics retain their reported reasons and observation counts."
    )
    if missing:
        limits += (
            " Missing bars make coverage incomplete; no gaps were filled, and affected "
            "contiguous-window statistics may be unavailable."
        )
    elif "profiles" not in summary:
        limits += (
            " Profile coverage metrics were not selected and are not inferred from other sections."
        )
    else:
        limits += " Registered coverage does not establish exchange completeness."
    if "cluster_counts" in summary:
        limits += (
            " Cluster boundaries outside the evaluation interval were not examined; "
            "event details remain in the numerical summary."
        )
    claims = {"scope": scope, "findings": " ".join(finding), "limitations": limits}
    result = {
        "schema": FACTS,
        "values": values,
        "claims": claims,
        "summary_sha256": digest(summary),
    }
    if len(values) > 128 or len(canonical(result)) > 32768:
        raise ResearchError("Memo facts exceed limit")
    return result


def schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["schema", "paragraphs"],
        "properties": {
            "schema": {"const": "memo-draft-v1"},
            "paragraphs": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["claim", "wording"],
                    "properties": {
                        "claim": {"type": "string", "enum": list(KINDS)},
                        "wording": {"type": "string", "enum": ["standard", "measured"]},
                    },
                },
            },
        },
    }


def draft(value: Any) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or set(value) != {"schema", "paragraphs"}
        or value["schema"] != "memo-draft-v1"
    ):
        raise ResearchError("Invalid memo draft")
    paragraphs = value["paragraphs"]
    if not isinstance(paragraphs, list) or len(paragraphs) != 3:
        raise ResearchError("Memo requires three paragraphs")
    for expected, paragraph in zip(KINDS, paragraphs, strict=True):
        if (
            not isinstance(paragraph, dict)
            or set(paragraph) != {"claim", "wording"}
            or paragraph["claim"] != expected
            or paragraph["wording"] not in {"standard", "measured"}
        ):
            raise ResearchError("Invalid memo claim or wording")
    return value


def render(value: Any, source: dict[str, Any]) -> str:
    value = draft(value)
    paragraphs = []
    for paragraph in value["paragraphs"]:
        raw = source["claims"][paragraph["claim"]]
        # Templates are application-owned; the model never supplies arbitrary prose.
        names = re.findall(r"\{\{([A-Za-z0-9_]+)\}\}", raw)
        if any(name not in source["values"] for name in names):
            raise ResearchError("Unknown memo placeholder")
        text = re.sub(r"\{\{([A-Za-z0-9_]+)\}\}", lambda m: source["values"][m[1]], raw)
        if paragraph["wording"] == "measured" and paragraph["claim"] == "findings":
            text = "The recorded findings are as follows. " + text
        if not text.strip() or any(c in text for c in "\r\n<>{}"):
            raise ResearchError("Unsafe memo rendering")
        paragraphs.append(text)
    result = "\n\n".join(paragraphs) + "\n"
    if len(result.encode()) > 16384:
        raise ResearchError("Memo output exceeds limit")
    return result
