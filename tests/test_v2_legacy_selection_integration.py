"""Real registered 31/62-partition legacy selections retain the five-file verifier bound."""

import hashlib
import threading
import zipfile
from datetime import UTC, date, datetime, timedelta

import pytest
from test_v2_ingestion_integration import v2_engine  # noqa: F401
from test_v2_research_integration import research_engine  # noqa: F401

from marketlab.analytics.bars import BarError
from marketlab.analytics.bars import BarService as LegacyBars
from marketlab.analytics.v2 import BarService
from marketlab.datasets import ingest_archive

pytestmark = pytest.mark.integration


def published_month(engine, root, source, symbols):
    with engine.begin() as connection:
        for name in ("ingestion_submissions", "ingestion_jobs", "ingestion_attempts"):
            connection.exec_driver_sql(f"CREATE TABLE {name} (LIKE public.{name} INCLUDING ALL)")
    versions = []
    for symbol in symbols:
        for offset in range(31):
            day = date(2025, 1, 1) + timedelta(days=offset)
            epoch = datetime(1970, 1, 1, tzinfo=UTC)
            delta = datetime.combine(day, datetime.min.time(), UTC) - epoch
            micros = (delta.days * 86400 + delta.seconds) * 1000000
            filename = f"{symbol}-trades-{day.isoformat()}"
            archive = source / (filename + ".zip")
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
                output.writestr(filename + ".csv", f"{offset + 1},100,1,100,{micros},True,False\n")
            checksum = source / (filename + ".zip.CHECKSUM")
            checksum.write_text(
                hashlib.sha256(archive.read_bytes()).hexdigest() + "  " + archive.name + "\n"
            )
            result = ingest_archive(engine, root, archive, checksum, symbol=symbol, trade_date=day)
            versions.append(result["dataset_version_id"])
    return versions


@pytest.mark.asyncio
@pytest.mark.parametrize("symbols", [("BTCUSDT",), ("BTCUSDT", "ETHUSDT")])
async def test_real_month_selection_batches_native_verification(
    research_engine,  # noqa: F811
    tmp_path,
    monkeypatch,
    symbols,
):
    root = tmp_path / "storage"
    source = tmp_path / "source"
    source.mkdir()
    versions = published_month(research_engine, root, source, symbols)
    base = LegacyBars(research_engine, root)
    bars = BarService(base)
    calls = []
    original = base.reader.verifier.verify_many

    def bounded(requests, cancelled):
        calls.append(len(requests))
        assert 1 <= len(requests) <= 5
        return original(requests, cancelled)

    monkeypatch.setattr(base.reader.verifier, "verify_many", bounded)
    try:
        identities = ["binance:spot:" + s for s in symbols]
        first = datetime(2025, 1, 1, tzinfo=UTC)
        before = datetime(2025, 2, 1, tzinfo=UTC)
        rows = await bars.prepare_selection(identities, versions, first, before, threading.Event())
        assert len(rows) == len(symbols) * 31
        assert {r["dataset_version_id"] for r in rows} == set(versions)
        assert all(r["manifest"]["quality"]["accepted_rows"] == 1 for r in rows)
        expected = [5] * (len(versions) // 5) + ([len(versions) % 5] if len(versions) % 5 else [])
        assert calls == expected
        assert base.reader.compute.snapshot()["active"] == 0
        repeated = await bars.prepare_selection(
            identities, versions, first, before, threading.Event()
        )
        assert len(repeated) == len(rows) and calls == expected
    finally:
        await bars.close()
        await base.close()


@pytest.mark.asyncio
async def test_cancellation_between_native_batches_stops_before_next_claim(
    research_engine,  # noqa: F811
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "storage"
    source = tmp_path / "source"
    source.mkdir()
    versions = published_month(research_engine, root, source, ("BTCUSDT",))
    base = LegacyBars(research_engine, root)
    bars = BarService(base)
    stop = threading.Event()
    original = base.reader.verifier.verify_many
    calls = []

    def cancelled_after_batch(requests, cancelled):
        calls.append(len(requests))
        result = original(requests, cancelled)
        stop.set()
        return result

    monkeypatch.setattr(base.reader.verifier, "verify_many", cancelled_after_batch)
    try:
        with pytest.raises(BarError, match="verification unavailable"):
            await bars.prepare_selection(
                ["binance:spot:BTCUSDT"],
                versions,
                datetime(2025, 1, 1, tzinfo=UTC),
                datetime(2025, 2, 1, tzinfo=UTC),
                stop,
            )
        assert calls == [5] and not bars.verified
        assert base.reader.compute.snapshot()["active"] == 0
    finally:
        await bars.close()
        await base.close()
