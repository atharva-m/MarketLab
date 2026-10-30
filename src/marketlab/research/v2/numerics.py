"""Versioned metadata projection over the retained Decimal80 numerical engine."""

from threading import Event
from typing import Any

from marketlab.datasets.v2.common import V2Error
from marketlab.research.numerics import calculate as legacy_calculate
from marketlab.research.spec import ResearchError
from marketlab.research.spec import ResearchSpec as LegacySpec

from .spec import NUMERICS, ResearchSpec


def calculate(
    spec: ResearchSpec,
    inputs: dict[str, list[dict[str, Any]]],
    metadata: dict[str, dict[str, Any]],
    cancelled: Event,
) -> tuple[dict[str, Any], dict[str, Any]]:
    adapter = LegacySpec(
        spec.workflow,
        spec.instrument_ids,
        spec.dataset_versions,
        spec.start,
        spec.end,
        spec.history_start,
        spec.metrics,
    )
    try:
        result, summary = legacy_calculate(adapter, inputs, cancelled)
    except ResearchError as error:
        raise V2Error("coverage_gap", "Insufficient actual research history") from error
    units = {
        "price": metadata[spec.instrument_ids[0]]["quote_asset"],
        "quote_volume": metadata[spec.instrument_ids[0]]["quote_asset"],
        "returns": "ratio",
        "base_volume": {i: metadata[i]["base_asset"] for i in spec.instrument_ids},
    }
    for body, schema in ((result, "research-results-v2"), (summary, "research-summary-v2")):
        body.update(
            schema=schema,
            definition=NUMERICS,
            units=units,
            instrument_ids=list(spec.instrument_ids),
            instruments=metadata,
            coverage_claim="observed_only",
        )
        if spec.workflow == "cross_asset":
            body["comparison_order"] = list(spec.instrument_ids)
    return result, summary
