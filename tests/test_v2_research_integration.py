"""Actual generalized durable research, ownership and common capacity accounting."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_v2_ingestion_integration import canonical_input, v2_engine  # noqa: F401
from test_v2_research import body

from marketlab.analytics.bars import BarService
from marketlab.datasets.v2 import capacity, core, jobs
from marketlab.datasets.v2 import service as ingestion
from marketlab.datasets.v2.common import V2Error, sha256_file
from marketlab.research.v2.service import ResearchService
from marketlab.research.v2.spec import ResearchSpec

pytestmark = pytest.mark.integration


@pytest.fixture
def research_engine(v2_engine):  # noqa: F811
    location = Path(__file__).resolve().parents[1] / "migrations/versions/0009_v2_research.py"
    spec = importlib.util.spec_from_file_location("v2_research_migration", location)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with v2_engine.begin() as connection:
        connection.exec_driver_sql(module.DDL)
    return v2_engine


def fixture_version(engine, root, tmp_path):
    source = tmp_path / "twenty.csv"
    source.write_text(
        "source_trade_id,executed_at,price,quantity,quote_quantity,is_buyer_maker,is_best_match\n"
        + "".join(
            f"{i},2025-03-01T{i // 12:02}:{(i % 12) * 5:02}:00Z,{100 + i},1,{100 + i},true,\n"
            for i in range(20)
        ),
        encoding="utf-8",
    )
    manifest = dict(
        schema="canonical-trade-import-v1",
        instrument_id="binance:spot:BTCUSDT",
        trade_date="2025-03-01",
        format="csv",
        timestamp_encoding="rfc3339_utc",
        quote_quantity_mode="supplied",
        source_sha256=sha256_file(source),
        source_name="controlled-binance-fixture",
        source_reference=None,
        coverage_claim="observed_only",
    )
    result = ingestion.import_file(engine, root, manifest, source, "fixture")
    ingestion.work(engine, root, max_jobs=1, submission_id=result["submission_id"])
    current = jobs.inspect_submission(engine, result["submission_id"])["jobs"][0]
    assert current["state"] == "succeeded"
    return current["result_version"]


@pytest.mark.asyncio
async def test_actual_generalized_research_replay_read_cancel_and_label_pin(
    research_engine, tmp_path
):
    root = tmp_path / "storage"
    version = fixture_version(research_engine, root, tmp_path)
    request = body()
    request["instrument_ids"] = ["binance:spot:BTCUSDT"]
    request["dataset_versions"] = [version]
    spec = ResearchSpec.create(request)
    base = BarService(research_engine, root, None)
    research = ResearchService(base)
    try:
        run, replayed = await research.submit(spec, "research")
        assert not replayed
        assert await research.submit(spec, "research") == (run, True)
        core.update_instrument(
            research_engine,
            "binance:spot:BTCUSDT",
            {"expected_revision": 0, "display_name": "Later label"},
            "label",
        )
        assert await research.work(1, run) == 1
        info = research.inspect(run)
        assert info["state"] == "succeeded"
        assert not info["memo_available"]
        result, _ = research.read(run, "results")
        assert result["profiles"]["binance:spot:BTCUSDT"]["coverage"]["observed"] == 8
        assert result["instruments"]["binance:spot:BTCUSDT"]["display_name"] != "Later label"
        queued, _ = await research.submit(spec, "cancel-me")
        revision = research.inspect(queued)["revision"]
        cancelled = await research.cancel(queued, revision, "cancel-key")
        assert cancelled["state"] == "cancelled"
        assert await research.cancel(queued, revision, "cancel-key") == cancelled
        assert await research.work(1, queued) == 0
    finally:
        await research.close()
        await base.close()


@pytest.mark.parametrize("research_first", [False, True])
def test_common_capacity_prevents_cross_protocol_overcommit(
    research_engine, tmp_path, monkeypatch, research_first
):
    root = tmp_path / "capacity"
    root.mkdir()
    total = capacity.SCRATCH + capacity.SPILL + capacity.OUTPUT
    monkeypatch.setattr(capacity.shutil, "disk_usage", lambda _: SimpleNamespace(free=total + 99))
    if research_first:
        reservation = capacity.reserve(research_engine, root)
        with pytest.raises(V2Error):
            with core.transaction(research_engine) as connection:
                ingestion._reserve(connection, root, "source", 100, "source", import_id=uuid4())
        capacity.release(research_engine, root, reservation)
    else:
        # A native ingestion staging reservation blocks research admission.
        source, metadata = canonical_input(tmp_path)
        imported = ingestion.import_file(research_engine, root, metadata, source, "held-source")
        with core.transaction(research_engine) as connection:
            ingestion._reserve(
                connection, root, "held-extra", 100, "source", import_id=imported["import_id"]
            )
        with pytest.raises(V2Error):
            capacity.reserve(research_engine, root)


def test_reservation_retains_failed_charge_until_owned_cleanup(research_engine, tmp_path):
    root = tmp_path / "reservation"
    reservation = capacity.reserve(research_engine, root)
    (reservation["path"] / "failed").write_bytes(b"retained")
    capacity.release(research_engine, root, reservation, success=False)
    with research_engine.connect() as connection:
        assert (
            core.one(
                connection,
                "SELECT * FROM v2_research_reservations WHERE reservation_id=:id",
                id=reservation["reservation_id"],
            )["state"]
            == "retained"
        )
    assert (reservation["path"] / "failed").exists()
    capacity.release(research_engine, root, reservation)
    assert not reservation["path"].exists()
