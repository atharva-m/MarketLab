"""Strict v2 inputs, selected aliases and independent full-turn grounding."""

import re
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

from marketlab.copilot.spec import ALIASES, REASONS, metric_mentions, workflow_mentions
from marketlab.datasets.v2.common import V2Error, canonical_json, digest
from marketlab.research.spec import METRICS, PREDICATES
from marketlab.research.v2.spec import ResearchSpec, utc

FIELDS = ("workflow", "instruments", "start", "end", "history_start", "interval", "metrics")
GRAMMAR_VERSION = "copilot-evidence-grammar-v1"
SEMANTIC_VERSION = "copilot-semantic-coverage-v3"
QUESTIONS = {
    "workflow": "Choose descriptive market_profile, cross_asset or volatility_cluster.",
    "instruments": "Choose exact selected Binance spot symbols and quote assets.",
    "start": "Give the inclusive aligned evaluation start with explicit UTC timezone.",
    "end": "Give the exclusive aligned evaluation end with explicit UTC timezone.",
    "history_start": "Give an explicit aligned UTC history start with enough warm-up.",
    "interval": "Confirm five-minute bars (5m).",
    "metrics": "Choose the supported selected summary metrics.",
    "meaning": "Clarify the requested descriptive calculation without extra operations.",
    "coverage": "Select registered versions covering the requested days and warm-up.",
}


def invalid(message: str = "Invalid v2 copilot input") -> V2Error:
    return V2Error("invalid_request", message)


def strings(value: Any, pattern: str, maximum: int) -> list[str]:
    if (
        type(value) is not list
        or not 1 <= len(value) <= maximum
        or any(type(v) is not str or re.fullmatch(pattern, v) is None for v in value)
        or len(set(value)) != len(value)
    ):
        raise invalid()
    return sorted(value)


def context(value: Any) -> dict[str, Any]:
    allowed = (set(FIELDS) - {"instruments"}) | {"instrument_ids"}
    if type(value) is not dict or not set(value) <= allowed:
        raise invalid()
    result = dict(value)
    for name, item in result.items():
        if name == "instrument_ids":
            result[name] = strings(item, r"binance:spot:[A-Za-z0-9][A-Za-z0-9._-]{0,63}", 2)
        elif name == "metrics":
            result[name] = strings(item, "|".join(sorted(set().union(*METRICS.values()))), 4)
        elif name in {"history_start", "start", "end"}:
            result[name] = utc(item).isoformat().replace("+00:00", "Z")
        elif name == "workflow":
            if type(item) is not str or item not in METRICS:
                raise invalid()
        elif item != "5m":
            raise invalid()
    return result


def turn(value: Any, answer: bool = False) -> dict[str, Any]:
    keys = {"schema", "text", "context"} | (
        {"expected_revision"} if answer else {"instrument_ids", "dataset_versions"}
    )
    if type(value) is not dict or set(value) != keys or len(canonical_json(value)) > 65536:
        raise invalid()
    if value["schema"] != ("copilot-answer-v2" if answer else "copilot-request-v2"):
        raise invalid()
    if type(value["text"]) is not str or not value["text"].strip():
        raise invalid()
    if len(value["text"].encode()) > 8192:
        raise invalid()
    result = dict(value, context=context(value["context"]))
    if answer:
        if type(value["expected_revision"]) is not int or not 0 <= value["expected_revision"] < 5:
            raise invalid("Invalid clarification revision")
    else:
        result["instrument_ids"] = strings(
            value["instrument_ids"], r"binance:spot:[A-Za-z0-9][A-Za-z0-9._-]{0,63}", 2
        )
        result["dataset_versions"] = strings(value["dataset_versions"], r"[0-9a-f]{64}", 62)
        if not set(result["context"].get("instrument_ids", [])) <= set(result["instrument_ids"]):
            raise invalid("Context contains an unselected instrument")
    return result


def aliases(snapshot: dict[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for slot, item in snapshot["instruments"].items():
        for alias in (item["source_symbol"], item["base_asset"]):
            result.setdefault(alias.lower(), []).append(slot)
        legacy_name = {"BTC": "bitcoin", "ETH": "ethereum"}.get(item["base_asset"])
        if legacy_name:
            result.setdefault(legacy_name, []).append(slot)
    return result


def supplied(value: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    if "instrument_ids" in result:
        mapping = {v["instrument_id"]: k for k, v in snapshot["instruments"].items()}
        try:
            result["instruments"] = sorted(mapping[i] for i in result.pop("instrument_ids"))
        except KeyError as error:
            raise invalid("Context contains an unselected instrument") from error
    return result


def unsupported(text: str, snapshot: dict[str, Any]) -> bool:
    forbidden = (
        r"https?://|\b(?:sql|python|javascript|shell|ignore|override|credentials|password|"
        r"backtest|strategy|predict\w*|forecast\w*|leverage|buy|sell|tpo|hourly|beta|"
        r"regression|cointegration|interpolate|futures?|perpetuals?|derivatives?|"
        r"coinbase|kraken|bybit|okx|binanceus|uniswap|polygon|yahoo)\b|"
        r"\b(?:model|prompt|dataset|version)\s*(?:=|:)|\b(?:system prompt|daily bars|"
        r"fill missing|fill bars|latest dataset|latest version|newest version|"
        r"skip validation|bypass checks|do not submit|don't submit|example only|draft only)\b"
    )
    if re.search(forbidden, text, re.I):
        return True
    if re.search(
        r"\b(?:num_ctx|num_predict|temperature|threshold|quantile|percentile|"
        r"volume_multiple|min_bars|lookback|rolling|minimum)\b",
        text,
        re.I,
    ):
        return True
    selected = {v["source_symbol"] for v in snapshot["instruments"].values()}
    mentioned = re.findall(r"\b[A-Za-z0-9]{2,24}(?:USDT|USDC|BUSD|BTC|ETH|BNB)\b", text, re.I)
    if any(s.upper() not in selected for s in mentioned):
        return True
    if re.search(r"\b(?:execute|run|submit)\s+(?:twice|multiple|two|three|[2-9])\b", text, re.I):
        return True
    for amount, unit in re.findall(r"\b(\d+(?:\.\d+)?)\s*(m|h|minutes?|hours?)\b", text, re.I):
        if amount != "5" or unit.lower() not in {"m", "minute", "minutes"}:
            return True
    return False


def extract(text: str, snapshot: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
    found: dict[str, Any] = {}
    uncertain: set[str] = set()
    workflows = sorted({w for w, _ in workflow_mentions(text)})
    if len(workflows) == 1:
        found["workflow"] = workflows[0]
    elif workflows:
        uncertain.add("workflow")
    instruments: set[str] = set()
    for alias, matches in aliases(snapshot).items():
        if re.search(r"(?<![A-Za-z0-9_])" + re.escape(alias) + r"(?![A-Za-z0-9_])", text, re.I):
            if len(set(matches)) == 1:
                instruments.update(matches)
            else:
                uncertain.add("instruments")
    if instruments:
        found["instruments"] = sorted(instruments)
    if re.search(r"\b(?:5m|five[ -]minute|5[ -]minute)\b", text, re.I):
        found["interval"] = "5m"
    for name, pattern in (
        ("history_start", r"(?:history(?:_start| start)?|warm[ -]up(?: start)?)"),
        (
            "start",
            r"(?<!history_)(?<!history )(?<!warm-up )(?:evaluation start|\bstart|inclusive start)",
        ),
        ("end", r"(?:exclusive end|end|before)"),
    ):
        matches = re.findall(
            r"(?<![A-Za-z0-9_])" + pattern + r"(?![A-Za-z0-9_])\s*(?:is|at|from|=|:)?\s*"
            r"([0-9]{4}-\d\d-\d\dT\d\d:\d\d:00(?:Z|\+00:00))(?![A-Za-z0-9_])",
            text,
            re.I,
        )
        values = {utc(m).isoformat().replace("+00:00", "Z") for m in matches}
        if len(values) == 1:
            found[name] = values.pop()
        elif values:
            uncertain.add(name)
    metrics = sorted({m.group().lower() for m in metric_mentions(text)})
    if metrics:
        found["metrics"] = metrics
    if re.search(r"\b(?:recent|yesterday|today|last week)\b", text, re.I):
        uncertain |= {"start", "end"}
    if re.search(r"inclusive end|end inclusive", text, re.I):
        uncertain.add("end")
    if re.search(r"exclusive start|start exclusive", text, re.I):
        uncertain.add("start")
    if re.search(r"\b(?:not|exclude|except|without|versus|usual|high volume)\b", text, re.I):
        uncertain.add("meaning")
    if re.search(r"market profile", text, re.I) and not re.search(r"descriptive|ohlcv", text, re.I):
        uncertain.add("workflow")
    if not semantically_covered(text, snapshot):
        uncertain.add("meaning")
    return found, uncertain


def semantically_covered(text: str, snapshot: dict[str, Any]) -> bool:
    """Unknown constraints cannot disappear behind otherwise valid structured context.

    Recognize only application-owned semantic tokens and explicit labelled
    boundaries. Ordinary grammatical words carry no new capability. Everything
    else requires clarification, including unknown venue/symbol/interval syntax.
    This intentionally trades recall for a closed handoff boundary.
    """
    remaining = re.sub(
        r"(?<![A-Za-z0-9_])(cross_asset)\s+comparison(?![A-Za-z0-9_])",
        r"\1",
        text,
        flags=re.I,
    )
    names = set(aliases(snapshot))
    for item in snapshot["instruments"].values():
        names |= {item["instrument_id"].lower(), item["quote_asset"].lower()}
    # The legacy workflow alias contains an instrument name; recognize that
    # name independently so it cannot legitimize an unselected asset.
    names |= {a for values in ALIASES.values() for a in values if a != "compare bitcoin"}
    names |= set().union(*METRICS.values())
    for name in sorted(names, key=len, reverse=True):
        remaining = re.sub(
            r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])",
            " ",
            remaining,
            flags=re.I,
        )
    remaining = re.sub(r"\b(?:5m|five[ -]minute|5[ -]minute)\b", " ", remaining, flags=re.I)
    remaining = re.sub(
        r"\b(?:history_start|history start|history|warm-up start|warm-up|evaluation start|"
        r"inclusive start|start|exclusive end|end|before)\s*(?:is|at|from|=|:)?\s*"
        r"[0-9]{4}-\d\d-\d\dT\d\d:\d\d:00(?:Z|\+00:00)(?![A-Za-z0-9_])",
        " ",
        remaining,
        flags=re.I,
    )
    harmless = {
        "a",
        "an",
        "the",
        "and",
        "of",
        "for",
        "on",
        "in",
        "with",
        "using",
        "use",
        "please",
        "run",
        "submit",
        "execute",
        "compare",
        "research",
        "descriptive",
        "ohlcv",
        "request",
        "confirm",
        "confirmed",
        "choose",
        "selected",
        "selection",
        "registered",
        "pinned",
        "binance",
        "spot",
        "instrument",
        "instruments",
        "instrument_ids",
        "symbol",
        "symbols",
        "asset",
        "assets",
        "base",
        "quote",
        "workflow",
        "metric",
        "metrics",
        "interval",
        "bars",
        "start",
        "end",
        "history",
        "history_start",
        "evaluation",
        "inclusive",
        "exclusive",
        "is",
        "at",
        "from",
        "to",
        "until",
        "before",
        "fixed",
        "standard",
        "definitions",
        "r4",
    }
    tokens = re.findall(r"\w+|[^\s\w.,;:!?=()\[\]{}+\-/\"']", remaining, flags=re.UNICODE)
    return all(token.lower() in harmless for token in tokens)


def interpretation(value: Any) -> dict[str, Any]:
    if (
        type(value) is not dict
        or set(value) != {"schema", "outcome", "reason", "intent", "evidence", "unresolved"}
        or value["schema"] != "copilot-interpretation-v2"
        or type(value["outcome"]) is not str
        or value["outcome"] not in {"candidate", "needs_clarification", "unsupported"}
        or type(value["reason"]) is not str
        or value["reason"] not in REASONS
        or type(value["intent"]) is not dict
        or set(value["intent"]) != set(FIELDS)
        or type(value["evidence"]) is not dict
        or set(value["evidence"]) != set(FIELDS)
        or type(value["unresolved"]) is not list
        or any(type(x) is not str or x not in QUESTIONS for x in value["unresolved"])
        or len(set(value["unresolved"])) != len(value["unresolved"])
    ):
        raise invalid("Invalid v2 interpretation")
    for name, item in value["intent"].items():
        if item is None:
            continue
        if name == "instruments":
            strings(item, r"i[01]", 2)
        elif name == "metrics":
            strings(item, "|".join(sorted(set().union(*METRICS.values()))), 3)
        elif type(item) is not str:
            raise invalid("Invalid intent value type")
        elif name == "workflow" and item not in METRICS:
            raise invalid("Invalid workflow intent")
        elif name == "interval" and item != "5m":
            raise invalid("Invalid interval intent")
        elif name in {"start", "end", "history_start"}:
            utc(item)
    return dict(value)


def decide(
    turns: list[dict[str, Any]], snapshot: dict[str, Any], value: Any
) -> tuple[str, dict[str, Any], list[str]]:
    model = interpretation(value)
    if unsupported("\n".join(t["text"] for t in turns), snapshot):
        return "unsupported", {}, []
    grounded: dict[str, Any] = {}
    pending: set[str] = set()
    for item in turns:
        literal, unclear = extract(item["text"], snapshot)
        supplied_fields = supplied(item["context"], snapshot)
        explicit = literal.keys() | supplied_fields.keys()
        previous_pending = set(pending)
        pending -= explicit
        pending |= unclear
        for name in explicit:
            choices = [source[name] for source in (literal, supplied_fields) if name in source]
            if any(v != choices[0] for v in choices):
                pending.add(name)
            candidate = choices[-1]
            if name in grounded and grounded[name] != candidate and name not in previous_pending:
                pending.add(name)
            grounded[name] = candidate
    if pending:
        return "needs_clarification", grounded, sorted(pending)
    for name in FIELDS:
        candidate, evidence = model["intent"][name], model["evidence"][name]
        if candidate is None:
            if evidence is not None:
                raise invalid("Evidence without intent")
            continue
        if type(evidence) is not dict or set(evidence) not in (
            {"turn", "context"},
            {"turn", "quote"},
        ):
            raise invalid("Invalid evidence reference")
        index = evidence["turn"]
        if type(index) is not int or not 0 <= index < len(turns):
            raise invalid("Invalid evidence turn")
        if "context" in evidence:
            if (
                evidence["context"] is not True
                or supplied(turns[index]["context"], snapshot).get(name) != candidate
            ):
                raise invalid("Ungrounded context evidence")
        else:
            quote = evidence["quote"]
            if type(quote) is not str or not quote or len(quote) > 160:
                raise invalid("Invalid evidence quote")
            if (
                re.search(
                    r"(?<![A-Za-z0-9_])" + re.escape(quote) + r"(?![A-Za-z0-9_])",
                    turns[index]["text"],
                )
                is None
            ):
                raise invalid("Missing evidence quote")
            proven = extract(quote, snapshot)[0].get(name)
            if name in {"start", "end", "history_start"}:
                try:
                    proven = utc(quote).isoformat().replace("+00:00", "Z")
                except (V2Error, ValueError):
                    pass
            if proven != candidate:
                raise invalid("Ungrounded quoted intent")
        if grounded.get(name) != candidate:
            return "needs_clarification", grounded, ["meaning"]
    missing = sorted(set(FIELDS) - grounded.keys())
    if missing:
        return "needs_clarification", grounded, missing
    if model["outcome"] == "unsupported":
        return "unsupported", {}, []
    if model["outcome"] == "needs_clarification":
        return "needs_clarification", grounded, model["unresolved"] or ["meaning"]
    if any(model["intent"][f] != grounded[f] for f in FIELDS) or model["unresolved"]:
        raise invalid("Incomplete candidate")
    return "candidate", grounded, []


def assemble(intent: dict[str, Any], snapshot: dict[str, Any]) -> ResearchSpec:
    ids = sorted(snapshot["instruments"][s]["instrument_id"] for s in intent["instruments"])
    first = utc(intent["history_start"]).date()
    last = (utc(intent["end"]) - timedelta(microseconds=1)).date()
    versions = sorted(
        v["dataset_version_id"]
        for v in snapshot["datasets"]
        if v["instrument_id"] in ids and first.isoformat() <= v["trade_date"] <= last.isoformat()
    )
    return ResearchSpec.create(
        {
            "schema": "research-spec-v2",
            "workflow": intent["workflow"],
            "instrument_ids": ids,
            "dataset_versions": versions,
            "start": intent["start"],
            "end": intent["end"],
            "history_start": intent["history_start"],
            "interval": intent["interval"],
            "metrics": intent["metrics"],
            "parameters": {},
            "predicates": PREDICATES if intent["workflow"] == "volatility_cluster" else {},
        }
    )


def _mention_windows(spans: list[tuple[int, int]]) -> Iterator[tuple[int, int]]:
    """Sort mentions, then examine only their fixed 160-character neighbourhood."""
    spans = sorted(set(spans))
    for index, (first, _) in enumerate(spans):
        for ending in range(index, len(spans)):
            next_first, last = spans[ending]
            if next_first - first >= 160:
                break
            if last - first <= 160:
                yield first, last


def _quoted_value(name: str, text: str, first: int, last: int, snapshot: dict[str, Any]) -> Any:
    if not 0 <= first < last <= len(text) or last - first > 160:
        return None
    if first > 0 and re.fullmatch(r"[A-Za-z0-9_]", text[first - 1]):
        return None
    if last < len(text) and re.fullmatch(r"[A-Za-z0-9_]", text[last]):
        return None
    quote = text[first:last]
    value = extract(quote, snapshot)[0].get(name)
    if name in {"start", "end", "history_start"}:
        try:
            value = utc(quote).isoformat().replace("+00:00", "Z")
        except (V2Error, ValueError):
            pass
    return value


def evidence_options(snapshot: dict[str, Any], turns: list[dict[str, Any]]) -> dict[str, list[Any]]:
    """Canonical valid citations; never choose or repair the model's intent."""
    result: dict[str, list[Any]] = {name: [None] for name in FIELDS}
    for index, item in enumerate(turns):
        text = item["text"]
        context = supplied(item["context"], snapshot)
        spans: dict[str, list[tuple[int, int]]] = {name: [] for name in FIELDS}
        spans["workflow"] = [match.span() for _, match in workflow_mentions(text)]
        spans["instruments"] = list(
            _mention_windows(
                [
                    match.span()
                    for alias in aliases(snapshot)
                    for match in re.finditer(
                        r"(?<![A-Za-z0-9_])" + re.escape(alias) + r"(?![A-Za-z0-9_])",
                        text,
                        re.I,
                    )
                ]
            )
        )
        spans["metrics"] = list(_mention_windows([match.span() for match in metric_mentions(text)]))
        spans["interval"] = [
            match.span()
            for match in re.finditer(r"\b(?:5m|five[ -]minute|5[ -]minute)\b", text, re.I)
        ]
        for name, label in (
            ("history_start", r"(?:history(?:_start| start)?|warm[ -]up(?: start)?)"),
            (
                "start",
                r"(?<!history_)(?<!history )(?<!warm-up )"
                r"(?:evaluation start|\bstart|inclusive start)",
            ),
            ("end", r"(?:exclusive end|end|before)"),
        ):
            pattern = (
                r"(?<![A-Za-z0-9_])" + label + r"(?![A-Za-z0-9_])\s*(?:is|at|from|=|:)?\s*"
                r"([0-9]{4}-\d\d-\d\dT\d\d:\d\d:00(?:Z|\+00:00))(?![A-Za-z0-9_])"
            )
            spans[name] = [match.span(1) for match in re.finditer(pattern, text, re.I)]
        for name in FIELDS:
            choices: dict[bytes, tuple[int, int, dict[str, Any]]] = {}
            if name in context:
                choices[canonical_json(context[name])] = (0, 0, {"turn": index, "context": True})
            for first, last in spans[name]:
                value = _quoted_value(name, text, first, last, snapshot)
                if value is None:
                    continue
                key = canonical_json(value)
                candidate = (last - first, first, {"turn": index, "quote": text[first:last]})
                if key not in choices or candidate[:2] < choices[key][:2]:
                    choices[key] = candidate
            result[name] += [choices[key][2] for key in sorted(choices)]
    return result


def model_schema(snapshot: dict[str, Any], turns: list[dict[str, Any]]) -> dict[str, Any]:
    definitions: dict[str, Any] = {
        "workflow": {"enum": list(ALIASES)},
        "instruments": {
            "type": "array",
            "minItems": 1,
            "maxItems": 2,
            "items": {"enum": ["i0", "i1"]},
        },
        **{n: {"type": "string"} for n in ("start", "end", "history_start")},
        "interval": {"const": "5m"},
        "metrics": {
            "type": "array",
            "minItems": 1,
            "maxItems": 4,
            "items": {"enum": sorted(set().union(*METRICS.values()))},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["schema", "outcome", "reason", "intent", "evidence", "unresolved"],
        "properties": {
            "schema": {"const": "copilot-interpretation-v2"},
            "outcome": {"enum": ["candidate", "needs_clarification", "unsupported"]},
            "reason": {"enum": sorted(REASONS)},
            "intent": {
                "type": "object",
                "additionalProperties": False,
                "required": list(FIELDS),
                "properties": {n: {"anyOf": [d, {"type": "null"}]} for n, d in definitions.items()},
            },
            "evidence": {
                "type": "object",
                "additionalProperties": False,
                "required": list(FIELDS),
                "properties": {
                    name: {"enum": options}
                    for name, options in evidence_options(snapshot, turns).items()
                },
            },
            "unresolved": {"type": "array", "items": {"enum": list(QUESTIONS)}},
        },
    }


def projection(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "copilot-model-context-v2",
        "snapshot_sha256": digest(snapshot),
        "instruments": snapshot["instruments"],
        "coverage": snapshot["coverage"],
        "capability_sha256": snapshot["capability_sha256"],
    }
