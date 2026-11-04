"""One canonical implemented local capability snapshot for discovery and copilot."""

from typing import Any

from .admission import DATA_LIMIT
from .common import digest


def value() -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": "capabilities-v2",
        "auth_mode": "local",
        "storage_mode": "local",
        "adapters": ["binance_daily", "canonical_file"],
        "formats": ["csv", "parquet"],
        "workflows": ["market_profile", "cross_asset", "volatility_cluster"],
        "intervals": ["1m", "5m"],
        "memo_available": True,
        "copilot_available": True,
        "limits": {
            "partitions": 62,
            "research_buckets": 17856,
            "chart_buckets": 1440,
            "chart_partitions": 5,
            "canonical_bytes": 4294967296,
            "canonical_rows": 20000000,
            "csv_record_bytes": 4096,
            "data_bytes": DATA_LIMIT,
            "staged_uploads": 4,
            "running_jobs": 8,
            "profile_warmup": 12,
            "cluster_warmup": 300,
            "copilot_instruments": 2,
            "clarification_answers": 5,
            "model_input_bytes": 6000,
            "model_response_bytes": 32768,
            "model_deadline_seconds": 120,
            "copilot_calls_per_revision": 2,
            "memo_calls_per_run": 2,
            "memo_facts": 128,
            "memo_facts_bytes": 32768,
            "memo_text_bytes": 16384,
        },
    }
    result["sha256"] = digest(result)
    return result
