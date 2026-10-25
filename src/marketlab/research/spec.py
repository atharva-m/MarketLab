"""Strict bounded research inputs and canonical identity."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from marketlab.analytics.bars import timestamp
from marketlab.analytics.cache import canonical
from marketlab.trades.schemas import normalize_timestamp

SCHEMA = "research-spec-v1"
NUMERICS = "research-numerics-v1"
METRICS = {
    "market_profile": {"profile"},
    "cross_asset": {"profile", "correlation", "close_change_difference"},
    "volatility_cluster": {"profile", "clusters"},
}
PREDICATES = {"volatility_quantile": "0.9", "volume_multiple": "2", "min_bars": 2}


class ResearchError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ResearchError("Duplicate JSON keys")
        result[key] = value
    return result


def parse_json(raw: bytes) -> Any:
    if len(raw) > 65536:
        raise ResearchError("Research submission exceeds 64 KiB")
    try:

        def invalid_constant(_: str) -> None:
            raise ResearchError("Nonfinite research JSON number")

        return json.loads(raw, object_pairs_hook=unique_pairs, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ResearchError("Invalid research JSON") from error


def utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith(("Z", "+00:00")):
        raise ResearchError("Invalid aligned UTC research timestamp")
    try:
        result = normalize_timestamp(value)
        if result.microsecond or result.second or result.minute % 5:
            raise ValueError
        return result
    except ValueError as error:
        raise ResearchError("Invalid aligned UTC research timestamp") from error


@dataclass(frozen=True)
class ResearchSpec:
    workflow: str
    symbols: tuple[str, ...]
    dataset_versions: tuple[str, ...]
    start: datetime
    end: datetime
    history_start: datetime
    metrics: tuple[str, ...]

    @classmethod
    def create(cls, value: Any) -> "ResearchSpec":
        fields = {
            "schema",
            "workflow",
            "symbols",
            "dataset_versions",
            "start",
            "end",
            "history_start",
            "interval",
            "metrics",
            "parameters",
            "predicates",
        }
        if not isinstance(value, dict) or set(value) != fields:
            raise ResearchError("Invalid research specification fields")
        workflow = value["workflow"]
        if not isinstance(workflow, str) or workflow not in METRICS:
            raise ResearchError("Unsupported research workflow")
        for name, maximum in (("symbols", 2), ("dataset_versions", 62), ("metrics", 3)):
            items = value[name]
            if (
                not isinstance(items, list)
                or not 1 <= len(items) <= maximum
                or any(not isinstance(item, str) for item in items)
                or len(set(items)) != len(items)
            ):
                raise ResearchError("Invalid research selections")
        symbols = tuple(sorted(value["symbols"]))
        if (
            any(s not in {"BTCUSDT", "ETHUSDT"} for s in symbols)
            or (workflow == "cross_asset" and len(symbols) != 2)
            or (workflow != "cross_asset" and len(symbols) != 1)
            or any(re.fullmatch(r"[0-9a-f]{64}", v) is None for v in value["dataset_versions"])
            or not set(value["metrics"]) <= METRICS[workflow]
            or value["schema"] != SCHEMA
            or value["interval"] != "5m"
            or value["parameters"] != {}
            or type(value["parameters"]) is not dict
        ):
            raise ResearchError("Invalid research selections")
        expected = PREDICATES if workflow == "volatility_cluster" else {}
        if (
            type(value["predicates"]) is not dict
            or value["predicates"] != expected
            or (
                workflow == "volatility_cluster"
                and type(value["predicates"].get("min_bars")) is not int
            )
        ):
            raise ResearchError("Invalid research predicates")
        start, end, history = (utc(value[n]) for n in ("start", "end", "history_start"))
        needed = 300 if workflow == "volatility_cluster" else 12
        if (
            not datetime(2025, 1, 1, tzinfo=UTC)
            <= history
            < start
            < end
            <= datetime(2025, 2, 1, tzinfo=UTC)
            or start - history < timedelta(minutes=5 * needed)
            or (end - history).total_seconds() // 300 * len(symbols) > 17856
        ):
            raise ResearchError("Insufficient or invalid research history", 409)
        return cls(
            workflow,
            symbols,
            tuple(sorted(value["dataset_versions"])),
            start,
            end,
            history,
            tuple(sorted(value["metrics"])),
        )

    def body(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "workflow": self.workflow,
            "symbols": list(self.symbols),
            "dataset_versions": list(self.dataset_versions),
            "start": timestamp(self.start),
            "end": timestamp(self.end),
            "history_start": timestamp(self.history_start),
            "interval": "5m",
            "metrics": list(self.metrics),
            "parameters": {},
            "predicates": PREDICATES.copy() if self.workflow == "volatility_cluster" else {},
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical(self.body())).hexdigest()
