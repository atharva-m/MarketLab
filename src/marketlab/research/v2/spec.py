"""Strict generalized requests, with unchanged bounded numerical choices."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from marketlab.analytics.bars import timestamp
from marketlab.datasets.v2.common import HASH, V2Error, canonical_json, digest, parse_json
from marketlab.research.spec import METRICS, PREDICATES
from marketlab.trades.schemas import normalize_timestamp

SCHEMA = "research-spec-v2"
NUMERICS = "research-numerics-v2"


def utc(value: Any) -> datetime:
    try:
        if not isinstance(value, str) or not value.endswith(("Z", "+00:00")):
            raise ValueError
        instant = normalize_timestamp(value)
        if instant.utcoffset() != timedelta(0) or instant.second or instant.microsecond:
            raise ValueError
        if instant.minute % 5:
            raise ValueError
        return instant.astimezone(UTC)
    except (ValueError, TypeError, OverflowError) as error:
        raise V2Error("invalid_request", "Invalid aligned UTC research timestamp") from error


@dataclass(frozen=True)
class ResearchSpec:
    workflow: str
    instrument_ids: tuple[str, ...]
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
            "instrument_ids",
            "dataset_versions",
            "start",
            "end",
            "history_start",
            "interval",
            "metrics",
            "parameters",
            "predicates",
        }
        try:
            if not isinstance(value, dict) or set(value) != fields:
                raise ValueError
            if len(canonical_json(value)) > 65536:
                raise ValueError
            workflow = value["workflow"]
            if not isinstance(workflow, str) or workflow not in METRICS:
                raise ValueError
            for key, maximum in (("instrument_ids", 2), ("dataset_versions", 62), ("metrics", 3)):
                items = value[key]
                if (
                    type(items) is not list
                    or not 1 <= len(items) <= maximum
                    or any(not isinstance(v, str) for v in items)
                    or len(set(items)) != len(items)
                ):
                    raise ValueError
            instruments = tuple(sorted(value["instrument_ids"]))
            if (
                any(
                    re.fullmatch(r"binance:spot:[A-Za-z0-9][A-Za-z0-9._-]{0,63}", i) is None
                    for i in instruments
                )
                or len(instruments) != (2 if workflow == "cross_asset" else 1)
                or any(HASH.fullmatch(v) is None for v in value["dataset_versions"])
                or not set(value["metrics"]) <= METRICS[workflow]
                or value["schema"] != SCHEMA
                or value["interval"] != "5m"
                or type(value["parameters"]) is not dict
                or value["parameters"] != {}
            ):
                raise ValueError
            expected = PREDICATES if workflow == "volatility_cluster" else {}
            if (
                type(value["predicates"]) is not dict
                or value["predicates"] != expected
                or (
                    workflow == "volatility_cluster"
                    and type(value["predicates"].get("min_bars")) is not int
                )
            ):
                raise ValueError
            start, end, history = (utc(value[k]) for k in ("start", "end", "history_start"))
            needed = 300 if workflow == "volatility_cluster" else 12
            if not (
                datetime(1970, 1, 1, tzinfo=UTC)
                <= history
                < start
                < end
                <= datetime(9999, 12, 31, tzinfo=UTC)
            ):
                raise ValueError
            duration = end - history
            buckets = (duration.days * 86400 + duration.seconds) // 300 * len(instruments)
            if start - history < timedelta(minutes=needed * 5) or buckets > 17856:
                raise V2Error("coverage_gap", "Insufficient or excessive research history")
            return cls(
                workflow,
                instruments,
                tuple(sorted(value["dataset_versions"])),
                start,
                end,
                history,
                tuple(sorted(value["metrics"])),
            )
        except (ValueError, TypeError, KeyError, RecursionError, OverflowError) as error:
            raise V2Error("invalid_request", "Invalid bounded research specification") from error

    @classmethod
    def parse(cls, raw: bytes) -> "ResearchSpec":
        return cls.create(parse_json(raw))

    def body(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "workflow": self.workflow,
            "instrument_ids": list(self.instrument_ids),
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
        return digest(self.body())
