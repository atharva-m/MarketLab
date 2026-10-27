"""Independent benchmark oracles and source generation reproducibility."""

import inspect
import sys
import zipfile
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path("scripts").resolve()))
import r8_benchmark as benchmark


def test_fault_client_retry_uses_async_production_protocol():
    assert inspect.iscoroutinefunction(benchmark.Retry.call_with_retry)


@pytest.mark.parametrize("rows", [288, 289, 1000, 10000])
def test_closed_form_counts_match_independent_row_enumeration(rows):
    counts = [0] * 288
    for index in range(rows):
        timestamp = int(benchmark.generated_row(index, rows).split(",")[4])
        assert benchmark.EPOCH_US <= timestamp < benchmark.EPOCH_US + benchmark.DAY_US
        counts[(timestamp - benchmark.EPOCH_US) // 300000000] += 1
    assert counts == [benchmark.bucket_count(rows, index) for index in range(288)]
    assert sum(counts) == rows


def test_fixture_bytes_are_deterministic_and_provider_shaped(tmp_path):
    first, checksum, evidence = benchmark.generate_input(1000, tmp_path / "one")
    second, _, repeated = benchmark.generate_input(1000, tmp_path / "two")
    assert first.read_bytes() == second.read_bytes()
    assert evidence["source_sha256"] == repeated["source_sha256"]
    assert checksum.read_text().split()[0] == evidence["source_sha256"]
    with zipfile.ZipFile(first) as archive:
        lines = archive.read(archive.namelist()[0]).decode().splitlines()
    assert len(lines) == 1000
    assert len(lines[0].split(",")) == 7
    assert lines[-1].startswith("1000,100,0.01,1,")
    with pytest.raises(FileExistsError):
        benchmark.generate_input(1000, tmp_path / "one")


def test_small_sample_summary_reports_counts_and_range_without_tail_claims():
    summary = benchmark.statistics_for([{"seconds": 1.0}, {"seconds": 3.0}, {"seconds": 2.0}])
    assert summary["count"] == 3 and summary["median_seconds"] == 2.0
    assert summary["minimum_seconds"] == 1.0 and summary["maximum_seconds"] == 3.0
    assert "No tail percentile" in summary["percentile_claim"]


def test_candidate_interpretation_cannot_overwrite_completed_benchmark_outcome():
    sample = benchmark.completion_sample(
        0,
        2.5,
        "completed",
        {"eval_count": 100, "eval_duration": 1000000000},
        {"models": []},
        {"model_digest": "pinned"},
        {"outcome": "candidate"},
    )
    assert sample["outcome"] == "completed"
    assert sample["validation"]["outcome"] == "candidate"
    assert sum(row["outcome"] == "completed" for row in [sample]) == 1
    assert sample["native_timing"]["eval_count"] == 100


async def test_native_timing_observer_preserves_completion_identity():
    response = {"eval_count": 15, "eval_duration": 1000000000, "message": {"content": "unchanged"}}

    class Native:
        async def bounded(self, client, method, path, **kwargs):
            return response

    class Observed(benchmark.RecordingMixin, Native):
        pass

    observed = Observed()
    actual = await observed.bounded(None, "POST", "/api/chat")
    assert actual is response
    assert observed.completion["eval_count"] == 15
    assert response["message"]["content"] == "unchanged"


@pytest.mark.parametrize(
    "status,body",
    [
        (503, {"error": "unavailable"}),
        (200, {"error": "no models field"}),
        (200, {"models": [{"model": "missing digest"}]}),
    ],
)
async def test_invalid_residency_never_counts_as_model_cold(status, body):
    async with httpx.AsyncClient(
        base_url="http://owned-model",
        trust_env=False,
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body)),
    ) as client:
        with pytest.raises((httpx.HTTPStatusError, ValueError)):
            await benchmark.model_residency(client)
