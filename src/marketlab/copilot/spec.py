"""Strict copilot inputs and independent conservative semantic validation."""

import hashlib
import re
from datetime import timedelta
from typing import Any

from marketlab.analytics.cache import canonical
from marketlab.research.spec import METRICS, PREDICATES, ResearchError, ResearchSpec, utc

FIELD_ORDER = ("workflow", "symbols", "start", "end", "history_start", "interval", "metrics")
FIELDS = set(FIELD_ORDER)
REASONS = {"none", "missing_fields", "ambiguous", "unsupported", "conflict", "coverage"}
QUESTIONS = {
    "workflow": "Choose descriptive OHLCV market_profile, cross_asset, or volatility_cluster.",
    "symbols": "Choose exact BTCUSDT and/or ETHUSDT symbols.",
    "start": "Give the inclusive evaluation start as an explicit aligned UTC timestamp.",
    "end": "Give the exclusive evaluation end as an explicit aligned UTC timestamp.",
    "history_start": "Give the explicit January UTC history start for warm-up.",
    "interval": "Confirm five-minute bars (5m).",
    "metrics": "Choose profile, correlation, close_change_difference, or clusters as supported.",
    "meaning": "Clarify volume versus VWAP, OHLCV versus TPO, dates or threshold meaning.",
    "coverage": "Supply dataset coverage and sufficient explicit January warm-up history.",
}
ALIASES = {
    "market_profile": ("market_profile", "market profile", "ohlcv profile", "descriptive profile"),
    "cross_asset": ("cross_asset", "cross-asset", "cross asset", "correlation", "compare bitcoin"),
    "volatility_cluster": ("volatility_cluster", "volatility cluster", "volatility clusters"),
}


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def key(value: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value) is None:
        raise ResearchError("Invalid copilot idempotency key")


def identity(value: str) -> None:
    if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", value) is None:
        raise ResearchError("Invalid copilot request identity")


def context(value: Any) -> dict[str, Any]:
    if type(value) is not dict or not set(value) <= FIELDS:
        raise ResearchError("Invalid copilot context")
    result = dict(value)
    for name, item in result.items():
        if name in {"symbols", "metrics"}:
            allowed = (
                {"BTCUSDT", "ETHUSDT"} if name == "symbols" else set().union(*METRICS.values())
            )
            if (
                type(item) is not list
                or not item
                or any(type(x) is not str for x in item)
                or len(set(item)) != len(item)
                or not set(item) <= allowed
            ):
                raise ResearchError("Invalid copilot selections")
            result[name] = sorted(item)
        elif name in {"start", "end", "history_start"}:
            result[name] = utc(item).isoformat().replace("+00:00", "Z")
        elif name == "workflow":
            if type(item) is not str or item not in METRICS:
                raise ResearchError("Unsupported copilot workflow")
        elif item != "5m":
            raise ResearchError("Unsupported copilot interval")
    return result


def turn(value: Any, answer: bool = False) -> dict[str, Any]:
    expected = {"schema", "text", "context", "expected_revision" if answer else "dataset_versions"}
    if type(value) is not dict or set(value) != expected:
        raise ResearchError("Invalid copilot request fields")
    try:
        size = len(canonical(value))
    except (ValueError, TypeError, RecursionError) as error:
        raise ResearchError("Invalid copilot JSON values") from error
    if size > 65536:
        raise ResearchError("Copilot submission exceeds 64 KiB")
    if value["schema"] != ("copilot-answer-v1" if answer else "copilot-request-v1"):
        raise ResearchError("Invalid copilot schema")
    text = value["text"]
    if type(text) is not str or not text.strip() or len(text.encode()) > 8192:
        raise ResearchError("Invalid copilot text")
    result = {"schema": value["schema"], "text": text, "context": context(value["context"])}
    if answer:
        if type(value["expected_revision"]) is not int or not 0 <= value["expected_revision"] < 5:
            raise ResearchError("Invalid copilot revision")
        result["expected_revision"] = value["expected_revision"]
    else:
        versions = value["dataset_versions"]
        if (
            type(versions) is not list
            or not 1 <= len(versions) <= 62
            or any(type(v) is not str or re.fullmatch(r"[0-9a-f]{64}", v) is None for v in versions)
            or len(set(versions)) != len(versions)
        ):
            raise ResearchError("Invalid copilot dataset selection")
        result["dataset_versions"] = sorted(versions)
    return result


def interpretation(value: Any) -> dict[str, Any]:
    if (
        type(value) is not dict
        or set(value) != {"schema", "outcome", "intent", "evidence", "unresolved", "reason"}
        or value["schema"] != "copilot-interpretation-v1"
        or type(value["outcome"]) is not str
        or value["outcome"] not in {"candidate", "needs_clarification", "unsupported"}
        or type(value["reason"]) is not str
        or value["reason"] not in REASONS
    ):
        raise ResearchError("Invalid copilot interpretation")
    value = dict(value)
    if type(value["intent"]) is dict and type(value["evidence"]) is dict:
        if not set(value["intent"]) <= FIELDS or not set(value["evidence"]) <= FIELDS:
            raise ResearchError("Unknown copilot interpretation fields")
        absent = {n for n, item in value["intent"].items() if item is None}
        if any(value["evidence"].get(n) is not None for n in absent):
            raise ResearchError("Invalid absent copilot evidence")
        value["intent"] = {n: item for n, item in value["intent"].items() if item is not None}
        value["evidence"] = {n: item for n, item in value["evidence"].items() if n not in absent}
    value["intent"] = context(value["intent"])
    evidence, unresolved = value["evidence"], value["unresolved"]
    if (
        type(evidence) is not dict
        or set(evidence) != set(value["intent"])
        or any(type(v) is not str or not v or len(v.encode()) > 1024 for v in evidence.values())
        or type(unresolved) is not list
        or any(type(v) is not str or v not in QUESTIONS for v in unresolved)
        or len(set(unresolved)) != len(unresolved)
    ):
        raise ResearchError("Invalid copilot interpretation evidence")
    return dict(value)


def unsupported(text: str) -> bool:
    patterns = (
        r"https?://|\b(?:sql|python|javascript|shell|ignore|override|system prompt|"
        r"credentials|password|backtest|strategy|predict|prediction|forecast|leverage|"
        r"buy|sell|tpo|hourly|daily bars|beta|regression|cointegration|"
        r"interpolate|forward.fill|fill missing|fill bars)\b",
        r"\b(?:do not|don.t)\s+(?:automatically\s+)?(?:submit|execute|run)|"
        r"only (?:an? )?example|"
        r"example only|draft only",
        r"\b(?:without|skip|bypass|disable|avoid)\s+(?:all\s+)?"
        r"(?:validat\w*|checks|fenc\w*|idempot\w*|restrict\w*)",
        r"\b(?:execute|submit|run)\s+(?:twice|multiple|two|three|[2-9])\b|"
        r"\b(?:two|three|multiple|[2-9])\s+(?:research\s+)?runs\b",
        r"\b(?:latest|newest|most recent)\s+(?:dataset|version|data)\b",
        r"\b(?:one|1|fifteen|15|sixty|60)[ -]minute",
        r"\b(?:202[0-46-9]|203[0-9])-\d\d-\d\d",
    )
    if any(re.search(pattern, text, re.I) for pattern in patterns):
        return True
    # Parameter-specific exact constants. Unknown parameter wording fails closed;
    # a model cannot legitimize a numeric change by returning fixed defaults.
    remaining = text.lower()
    allowed = (
        r"(?:quantile|volatility_quantile)\s*(?:=|:|is|of)\s*0\.9(?![\w.])",
        r"\b90(?:th)?[ -]percentile\b",
        r"(?:volume_multiple)\s*(?:=|:|is)\s*2(?![\w.])",
        r"(?:min_bars)\s*(?:=|:|is)\s*2(?![\w.])",
        r"(?:minimum|at least)\s+(?:two|2)(?![\w.])\s+(?:adjacent|consecutive|contiguous)\s+bars",
        r"(?:volume\s+(?:strictly\s+)?(?:above|greater than|>)\s+)?"
        r"(?:twice|(?:two|2)\s+times)\s+(?:the\s+)?"
        r"(?:preceding|previous|prior)[ -](?:12|twelve)(?:[ -]bar)?"
        r"\s+(?:mean|average)(?:\s+volume)?",
    )
    for pattern in allowed:
        remaining = re.sub(pattern, " fixedconstant ", remaining)
    remaining = re.sub(
        r"(?:usual|undefined|unspecified)(?: volatility)? threshold",
        " ambiguousmeaning ",
        remaining,
    )
    # These categories are fully consumed above or rejected. Unknown qualifier
    # wording is not silently discarded merely because structured context is valid.
    if any(
        symbol.upper() not in {"BTCUSDT", "ETHUSDT"}
        for symbol in re.findall(r"\b[A-Za-z]{2,12}USDT\b", text, re.I)
    ):
        return True
    if any(word.lower() != "five" for word in re.findall(r"\b([A-Za-z]+)[ -]minutes?\b", text)):
        return True
    for amount, unit in re.findall(r"\b(\d+(?:\.\d+)?)\s*(m|h|minutes?|hours?)\b", text, re.I):
        if amount != "5" or unit.lower() not in {"m", "minute", "minutes"}:
            return True
    return bool(
        re.search(
            r"\b(?:quantile|volatility_quantile|percentile|volume_multiple|min_bars|"
            r"lookback|rolling|threshold|minimum|consecutive|contiguous)\b|"
            r"\b(?:at least|\w+ times|twice)\b",
            remaining,
            re.I,
        )
    )


def workflow_mentions(text: str) -> list[tuple[str, re.Match[str]]]:
    return [
        (workflow, match)
        for workflow, aliases in ALIASES.items()
        for alias in aliases
        for match in re.finditer(
            r"(?<![A-Za-z0-9_])" + re.escape(alias) + r"(?![A-Za-z0-9_])", text, re.I
        )
    ]


def metric_mentions(text: str) -> list[re.Match[str]]:
    # Workflow names do not implicitly select summary metrics. Correlation itself
    # is an explicitly named metric even when it also implies cross_asset.
    workflow_spans = [
        match.span()
        for _, match in workflow_mentions(text)
        if match.group().lower() != "correlation"
    ]
    return [
        match
        for match in re.finditer(
            r"\b(?:profile|correlation|close_change_difference|clusters)\b", text, re.I
        )
        if not any(first <= match.start() < last for first, last in workflow_spans)
    ]


def extract(text: str, ambiguities: set[str] | None = None) -> dict[str, Any]:
    """Conservative independent grounding; uncertainty causes clarification."""
    result: dict[str, Any] = {}
    ambiguities = ambiguities if ambiguities is not None else set()
    workflows = sorted({w for w, _ in workflow_mentions(text)})
    if len(workflows) == 1:
        result["workflow"] = workflows[0]
    elif len(workflows) > 1:
        ambiguities.add("workflow")
    symbols = [
        s
        for s, pattern in (
            ("BTCUSDT", r"\b(?:btcusdt|bitcoin|btc)\b"),
            ("ETHUSDT", r"\b(?:ethusdt|ethereum|eth)\b"),
        )
        if re.search(pattern, text, re.I)
    ]
    if symbols:
        result["symbols"] = symbols
    if re.search(r"(?<![A-Za-z0-9_])(?:5m|five[ -]minute|5[ -]minute)(?![A-Za-z0-9_])", text, re.I):
        result["interval"] = "5m"
    # Only explicit named boundaries; unlabeled ranges remain model-ambiguous.
    for name, pattern in (
        ("history_start", r"(?:history(?:_start| start)?|warm[ -]up(?: start)?)"),
        (
            "start",
            r"(?<!history_)(?<!history )(?<!warm-up )(?:evaluation start|\bstart|inclusive start)",
        ),
        ("end", r"(?:exclusive end|end|before)"),
    ):
        matches = re.findall(
            r"(?<![A-Za-z0-9_])"
            + pattern
            + r"(?![A-Za-z0-9_])"
            + r"\s*(?:is|at|from|=|:)?\s*(2025-\d\d-\d\d[T ]\d\d:\d\d(?::00)?"
            r"(?:Z|\+00:00| UTC))(?![A-Za-z0-9_])",
            text,
            re.I,
        )
        values = set()
        for match in matches:
            normalized = match.replace(" UTC", "Z").replace(" ", "T")
            if re.search(r"T\d\d:\d\dZ$", normalized):
                normalized = normalized[:-1] + ":00Z"
            values.add(utc(normalized).isoformat().replace("+00:00", "Z"))
        if len(values) == 1:
            result[name] = values.pop()
        elif len(values) > 1:
            ambiguities.add(name)
    stamps = r"(2025-\d\d-\d\dT\d\d:\d\d:00(?:Z|\+00:00))(?![A-Za-z0-9_])"
    ranges = re.findall(
        r"(?<![A-Za-z0-9_])(?:evaluation\s+)?from\s+"
        + stamps
        + r"\s+(?:to|until|before)\s+"
        + stamps,
        text,
        re.I,
    )
    if len(set(ranges)) == 1:
        bounds = [utc(t).isoformat().replace("+00:00", "Z") for t in ranges[0]]
        for name, value in zip(("start", "end"), bounds, strict=True):
            if name in result and result[name] != value:
                ambiguities.add(name)
            result[name] = value
    elif len(set(ranges)) > 1:
        ambiguities |= {"start", "end"}
    metrics = sorted({match.group().lower() for match in metric_mentions(text)})
    if metrics:
        result["metrics"] = sorted(metrics)
    return result


def decide(
    turns: list[dict[str, Any]], model: dict[str, Any]
) -> tuple[str, dict[str, Any], list[str]]:
    """Only independently grounded supported fields can become executable intent."""
    model = interpretation(model)
    combined = "\n".join(t["text"] for t in turns)
    if unsupported(combined):
        return "unsupported", {}, []
    grounded: dict[str, Any] = {}
    pending: set[str] = set()
    for item in turns:
        literal_ambiguities: set[str] = set()
        literal = extract(item["text"], literal_ambiguities)
        supplied = item["context"]
        explicit = literal.keys() | supplied.keys()
        pending -= explicit
        pending |= literal_ambiguities
        if re.search(r"inclusive end|end inclusive", item["text"], re.I):
            pending.add("end")
        if re.search(r"exclusive start|start exclusive", item["text"], re.I):
            pending.add("start")
        if re.search(r"fixed R4|standard R4|fixed definitions", item["text"], re.I):
            pending.discard("meaning")
        conflicts = {n for n in literal.keys() & supplied.keys() if literal[n] != supplied[n]}
        pending |= conflicts
        grounded.update(literal)
        grounded.update(supplied)
        # Negative/exclusive selection cannot be reinterpreted as a positive token.
        for field, terms in (
            ("metrics", r"profile|correlation|close_change_difference|clusters|metrics"),
            ("symbols", r"bitcoin|ethereum|btc|eth|btcusdt|ethusdt|symbols"),
            ("workflow", r"market_profile|cross_asset|volatility_cluster|workflow"),
        ):
            if re.search(
                r"\b(?:not|don.t|exclude|except|without)\b(?:\s+\w+){0,3}"
                r"\s+\b(?:" + terms + r")\b",
                item["text"],
                re.I,
            ):
                pending.add(field)
        if re.search(r"\b(?:recent|yesterday|today|last week)\b", item["text"], re.I):
            pending |= {"start", "end"}
        if re.search(
            r"volume (?:or|versus|vs) vwap|usual threshold|undefined threshold|"
            r"unspecified threshold|high volume",
            item["text"],
            re.I,
        ):
            pending.add("meaning")
        if (
            re.search(r"market profile", item["text"], re.I)
            and not re.search(r"descriptive|ohlcv", item["text"], re.I)
            and "workflow" not in supplied
        ):
            pending.add("workflow")
    if pending:
        return "needs_clarification", grounded, sorted(pending)
    for name, item in model["intent"].items():
        evidence = model["evidence"][name]
        if evidence != "context":
            # Exact phrase boundaries prevent identifier fragments becoming evidence.
            if (
                re.search(
                    r"(?<![A-Za-z0-9_])" + re.escape(evidence) + r"(?![A-Za-z0-9_])", combined
                )
                is None
            ):
                raise ResearchError("Ungrounded copilot interpretation")
            supported: Any
            if name in {"start", "end", "history_start"}:
                try:
                    supported = utc(evidence).isoformat().replace("+00:00", "Z")
                except ResearchError:
                    supported = extract(evidence).get(name)
            else:
                supported = extract(evidence).get(name)
            if supported is None or supported != item:
                raise ResearchError("Copilot evidence conflicts with intent")
        elif not any(t["context"].get(name) == item for t in turns):
            raise ResearchError("Ungrounded copilot context evidence")
        # Never synthesize missing full-turn fields from a selected excerpt.
        # Quoting one branch cannot resolve missing/ambiguous user intent.
        if name in grounded and grounded[name] != item:
            return "needs_clarification", {}, ["meaning"]
    missing = sorted(FIELDS - grounded.keys())
    if missing:
        return "needs_clarification", grounded, missing
    if model["outcome"] == "unsupported":
        return "unsupported", {}, []
    if model["outcome"] == "needs_clarification":
        return "needs_clarification", grounded, model["unresolved"] or ["meaning"]
    return "candidate", grounded, []


def assemble(intent: dict[str, Any], versions: list[dict[str, Any]]) -> ResearchSpec:
    first, before = (
        utc(intent["history_start"]).date(),
        (utc(intent["end"]) - timedelta(microseconds=1)).date(),
    )
    selected = [
        r["dataset_version_id"]
        for r in versions
        if r["symbol"] in intent["symbols"] and first <= r["trade_date"] <= before
    ]
    return ResearchSpec.create(
        {
            "schema": "research-spec-v1",
            **intent,
            "dataset_versions": selected,
            "parameters": {},
            "predicates": PREDICATES.copy() if intent["workflow"] == "volatility_cluster" else {},
        }
    )


def evidence_choices(turns: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Constrain quote generation to actual source spans, never supply intent."""
    choices: dict[str, set[str]] = {n: set() for n in FIELD_ORDER}
    for item in turns:
        text = item["text"]
        for name in item["context"]:
            choices[name].add("context")
        for aliases in ALIASES.values():
            for alias in aliases:
                for match in re.finditer(
                    r"(?<![A-Za-z0-9_])" + re.escape(alias) + r"(?![A-Za-z0-9_])", text, re.I
                ):
                    choices["workflow"].add(match.group())
        symbol_matches = list(
            re.finditer(r"\b(?:BTCUSDT|ETHUSDT|Bitcoin|Ethereum|BTC|ETH)\b", text, re.I)
        )
        metric_matches = metric_mentions(text)
        for field, matches in (("symbols", symbol_matches), ("metrics", metric_matches)):

            def meaning(match: re.Match[str], category: str = field) -> str:
                token = match.group().lower()
                if category == "symbols":
                    return "btc" if token in {"btc", "btcusdt", "bitcoin"} else "eth"
                return token

            distinct = {meaning(m) for m in matches}
            spans: list[str] = []
            for index, first in enumerate(matches):
                seen: set[str] = set()
                for last in matches[index:]:
                    seen.add(meaning(last))
                    if seen == distinct:
                        span = text[first.start() : last.end()]
                        if len(span.encode()) <= 160:
                            spans.append(span)
                        break
            if spans:
                choices[field].add(min(spans, key=lambda item: (len(item.encode()), item)))
        for match in re.finditer(r"\b(?:5m|five.minute|5.minute)\b", text, re.I):
            choices["interval"].add(match.group())
        # Timestamp quotes must support this exact full-turn field, not merely
        # some other boundary appearing elsewhere in the same request.
        literal = extract(text)
        for match in re.finditer(r"2025-\d\d-\d\dT\d\d:\d\d:00(?:Z|\+00:00)", text):
            normalized = utc(match.group()).isoformat().replace("+00:00", "Z")
            for field in ("start", "end", "history_start"):
                if literal.get(field) == normalized:
                    choices[field].add(match.group())
    return {n: sorted(values) for n, values in choices.items()}


def model_schema(turns: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    properties: dict[str, Any] = {n: {"type": "string"} for n in FIELD_ORDER}
    properties["workflow"] = {"type": "string", "enum": list(METRICS)}
    properties["interval"] = {"type": "string", "enum": ["5m"]}
    properties["symbols"] = {
        "type": "array",
        "items": {"type": "string", "enum": ["BTCUSDT", "ETHUSDT"]},
    }
    properties["metrics"] = {
        "type": "array",
        "items": {"type": "string", "enum": sorted(set().union(*METRICS.values()))},
    }
    evidence = evidence_choices(turns) if turns is not None else None
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["schema", "outcome", "intent", "evidence", "unresolved", "reason"],
        "properties": {
            "schema": {"const": "copilot-interpretation-v1"},
            "outcome": {"enum": ["candidate", "needs_clarification", "unsupported"]},
            "intent": {
                "type": "object",
                "required": list(FIELD_ORDER),
                "properties": {
                    n: {"anyOf": [definition, {"type": "null"}]}
                    for n, definition in properties.items()
                },
                "additionalProperties": False,
            },
            "evidence": {
                "type": "object",
                "required": list(FIELD_ORDER),
                "properties": {
                    n: (
                        {"enum": [*evidence[n], None]}
                        if evidence is not None
                        else {"anyOf": [{"type": "string", "maxLength": 160}, {"type": "null"}]}
                    )
                    for n in FIELD_ORDER
                },
                "additionalProperties": False,
            },
            "unresolved": {"type": "array", "items": {"enum": list(QUESTIONS)}},
            "reason": {"enum": sorted(REASONS)},
        },
    }
