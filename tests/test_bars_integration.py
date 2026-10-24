"""Real catalog visibility and retained historical publication compatibility."""

from datetime import timedelta

import pytest
import sqlalchemy as sa
from test_bars import START, FakeRedis
from test_datasets import ROW, archive_files

from marketlab.analytics import BarError, BarService, BarsRequest
from marketlab.datasets import ingest_archive
from marketlab.datasets.publication import _storage_root, dataset_versions

pytestmark = pytest.mark.integration


def published(engine, directory, rows=None):
    archive, checksum = archive_files(directory / "source", rows)
    result = ingest_archive(engine, directory / "storage", archive, checksum)
    request = BarsRequest.create(
        versions=[result["dataset_version_id"]],
        symbol="BTCUSDT",
        interval="1m",
        start=START,
        end=START + timedelta(minutes=5),
    )
    return directory / "storage", result, request


@pytest.mark.asyncio
async def test_published_fixture_cache_hit_and_unchanged_catalog(dataset_engine, tmp_path):
    root, result, request = published(dataset_engine, tmp_path)
    reader = BarService(dataset_engine, root)
    reader.cache.client = FakeRedis()
    with dataset_engine.connect() as connection:
        before = connection.execute(sa.select(dataset_versions)).mappings().all()
    body, first = await reader.read(request)
    repeated, second = await reader.read(request)
    assert body == repeated and (first, second) == ("MISS", "HIT")
    assert body["bars"][0]["trade_count"] == 1
    with dataset_engine.connect() as connection:
        assert before == connection.execute(sa.select(dataset_versions)).mappings().all()
    assert result["schema_version"] == 1
    await reader.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["manifest", "parquet", "missing", "catalog"])
async def test_integrity_checked_before_warm_cache(dataset_engine, tmp_path, target):
    root, result, request = published(dataset_engine, tmp_path)
    reader = BarService(dataset_engine, root)
    reader.cache.client = FakeRedis()
    await reader.read(request)
    assert (await reader.read(request))[1] == "HIT"
    manifest = next(_storage_root(root).rglob("manifest.json"))
    artifact = manifest.parent / "trades.parquet"
    if target == "manifest":
        manifest.write_bytes(manifest.read_bytes() + b" ")
    elif target == "parquet":
        data = bytearray(artifact.read_bytes())
        data[10] ^= 1
        artifact.write_bytes(data)
    elif target == "missing":
        artifact.unlink()
    else:
        with dataset_engine.begin() as connection:
            connection.execute(dataset_versions.update().values(row_count=999))
    with pytest.raises(BarError, match="integrity"):
        await reader.read(request)
    await reader.close()


@pytest.mark.asyncio
async def test_unregistered_orphan_unknown_and_rollback_are_invisible(dataset_engine, tmp_path):
    root, result, request = published(dataset_engine, tmp_path)
    with dataset_engine.connect() as connection:
        row = dict(connection.execute(sa.select(dataset_versions)).mappings().one())
    with dataset_engine.begin() as connection:
        connection.execute(dataset_versions.delete())
    reader = BarService(dataset_engine, root)
    with pytest.raises(BarError, match="not found"):
        await reader.read(request)
    with dataset_engine.connect() as writer:
        transaction = writer.begin()
        writer.execute(dataset_versions.insert().values(**row))
        with pytest.raises(BarError, match="not found"):
            await reader.read(request)
        transaction.rollback()
    with pytest.raises(BarError, match="not found"):
        await reader.read(request)
    await reader.close()


@pytest.mark.asyncio
async def test_mismatched_coverage_and_competing_same_day_versions(dataset_engine, tmp_path):
    root, _, request = published(dataset_engine, tmp_path)
    # A second genuine immutable source version for the same day is ambiguous.
    archive, checksum = archive_files(tmp_path / "different", [ROW.replace("93500.", "93501.")])
    second = ingest_archive(dataset_engine, root, archive, checksum)
    reader = BarService(dataset_engine, root)
    competing = BarsRequest.create(
        versions=[*request.versions, second["dataset_version_id"]],
        symbol="BTCUSDT",
        interval="1m",
        start=START,
        end=START + timedelta(minutes=5),
    )
    with pytest.raises(BarError, match="coverage"):
        await reader.read(competing)
    other_symbol = BarsRequest.create(
        versions=request.versions,
        symbol="ETHUSDT",
        interval="1m",
        start=START,
        end=START + timedelta(minutes=5),
    )
    with pytest.raises(BarError, match="coverage"):
        await reader.read(other_symbol)
    await reader.close()


@pytest.mark.asyncio
async def test_catalog_unavailable_is_redacted(tmp_path):
    engine = sa.create_engine("sqlite://")
    reader = BarService(engine, tmp_path)
    request = BarsRequest.create(
        versions=["f" * 64],
        symbol="BTCUSDT",
        interval="1m",
        start=START,
        end=START + timedelta(minutes=5),
    )
    with pytest.raises(BarError, match="^Dataset catalog unavailable$") as result:
        await reader.read(request)
    assert result.value.status == 503
    await reader.close()
    engine.dispose()
