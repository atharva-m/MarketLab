"""Real PostgreSQL tests of immutable catalog publication and recovery."""

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from threading import Barrier

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from test_datasets import ROW, archive_files

from marketlab.datasets import DatasetError, ingest_archive, inspect_version

pytestmark = pytest.mark.integration


def storage_root(path: Path) -> Path:
    """Permit test-side glob/read assertions beyond Windows MAX_PATH."""
    resolved = path.resolve()
    prefix = chr(92) * 2 + "?" + chr(92)
    if os.name == "nt" and not str(resolved).startswith(prefix):
        return Path(prefix + str(resolved))
    return resolved


def catalog_count(engine: Engine) -> int:
    schema = engine.get_execution_options()["schema_translate_map"][None]
    with engine.connect() as connection:
        return connection.execute(
            text(f'SELECT count(*) FROM "{schema}".dataset_versions')
        ).scalar_one()


def test_dataset_migration_is_additive_and_constrained(dataset_engine: Engine) -> None:
    inspector = inspect(dataset_engine)
    columns = {column["name"]: column for column in inspector.get_columns("dataset_versions")}
    assert set(columns) == {
        "dataset_version_id",
        "source_sha256",
        "manifest_sha256",
        "manifest_path",
        "venue",
        "symbol",
        "trade_date",
        "row_count",
        "status",
        "published_at",
    }
    assert all(not column["nullable"] for column in columns.values())
    assert inspector.get_pk_constraint("dataset_versions")["constrained_columns"] == [
        "dataset_version_id"
    ]
    schema = dataset_engine.get_execution_options()["schema_translate_map"][None]
    with pytest.raises(IntegrityError), dataset_engine.begin() as connection:
        connection.execute(
            text(
                f'INSERT INTO "{schema}".dataset_versions '
                "(dataset_version_id,source_sha256,manifest_sha256,manifest_path,venue,symbol,"
                "trade_date,row_count,status,published_at) VALUES "
                "(:id,:source,:manifest,:path,:venue,:symbol,:day,1,:status,CURRENT_TIMESTAMP)"
            ),
            {
                "id": "a" * 64,
                "source": "b" * 64,
                "manifest": "c" * 64,
                "path": "manifest.json",
                "venue": "binance_spot",
                "symbol": "BTCUSDT",
                "day": date(2025, 1, 1),
                "status": "pending",
            },
        )


def test_publish_reconcile_and_idempotent_rerun(dataset_engine: Engine, tmp_path: Path) -> None:
    archive, checksum = archive_files(tmp_path / "input", [ROW, ROW])
    root = storage_root(tmp_path / "storage")
    first = ingest_archive(dataset_engine, root, archive, checksum)
    second = ingest_archive(dataset_engine, root, archive, checksum)
    assert first == second
    assert catalog_count(dataset_engine) == 1
    assert first["source"]["actual_sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert first["quality"]["raw_rows"] == 2
    assert first["quality"]["accepted_rows"] == 1
    assert first["quality"]["duplicate_rows"] == 1
    assert first["quality"]["conflict_rows"] == 0
    assert first["requested_from"] == "2025-01-01T00:00:00Z"
    assert first["requested_before"] == "2025-01-02T00:00:00Z"
    assert first["build"]["git_revision"]
    assert len(first["build"]["lock_sha256"]) == 64
    assert inspect_version(dataset_engine, root, first["dataset_version_id"]) == first
    assert len(list(root.rglob("manifest.json"))) == 1
    assert len(list(root.rglob("*.parquet"))) == 1


def test_changed_source_creates_new_immutable_version(
    dataset_engine: Engine, tmp_path: Path
) -> None:
    root = storage_root(tmp_path / "storage")
    archive, checksum = archive_files(tmp_path / "input")
    first = ingest_archive(dataset_engine, root, archive, checksum)
    old_manifest = next(root.rglob("manifest.json"))
    old_bytes = old_manifest.read_bytes()
    archive, checksum = archive_files(
        tmp_path / "input", [ROW.replace("True,False", "False,False")]
    )
    second = ingest_archive(dataset_engine, root, archive, checksum)
    assert first["dataset_version_id"] != second["dataset_version_id"]
    assert catalog_count(dataset_engine) == 2
    assert old_manifest.read_bytes() == old_bytes
    assert inspect_version(dataset_engine, root, first["dataset_version_id"]) == first


def test_concurrent_same_source_has_single_publication(
    dataset_engine: Engine, tmp_path: Path
) -> None:
    archive, checksum = archive_files(tmp_path / "input")
    root = storage_root(tmp_path / "storage")
    barrier = Barrier(2, timeout=30)

    def checkpoint(phase: str) -> None:
        if phase == "artifacts_complete":
            barrier.wait()

    def publish() -> dict[str, object]:
        return ingest_archive(dataset_engine, root, archive, checksum, checkpoint=checkpoint)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(publish)
        second = executor.submit(publish)
        results = [first.result(timeout=60), second.result(timeout=60)]
    assert results[0] == results[1]
    assert catalog_count(dataset_engine) == 1
    assert len(list(root.rglob("manifest.json"))) == 1
    assert len(list(root.rglob("*.parquet"))) == 1


@pytest.mark.parametrize("phase", ["artifacts_complete", "before_catalog_commit"])
def test_failure_not_discoverable_and_retry_safe(
    dataset_engine: Engine, tmp_path: Path, phase: str
) -> None:
    archive, checksum = archive_files(tmp_path / "input")
    root = storage_root(tmp_path / "storage")
    observed: list[str] = []

    def checkpoint(current: str) -> None:
        if current == phase:
            observed.append(current)
            assert catalog_count(dataset_engine) == 0
            # A guessed version/orphan must not become discoverable through inspection.
            for manifest_path in root.rglob("manifest.json"):
                payload = json.loads(manifest_path.read_text())
                assert inspect_version(dataset_engine, root, payload["dataset_version_id"]) is None
            raise RuntimeError("deliberate publication failure")

    with pytest.raises((DatasetError, RuntimeError)):
        ingest_archive(dataset_engine, root, archive, checksum, checkpoint=checkpoint)
    assert observed == [phase]
    assert catalog_count(dataset_engine) == 0
    result = ingest_archive(dataset_engine, root, archive, checksum)
    assert catalog_count(dataset_engine) == 1
    assert inspect_version(dataset_engine, root, result["dataset_version_id"]) == result


@pytest.mark.parametrize("target", ["parquet", "manifest", "missing"])
def test_registered_artifact_damage_detected_without_replacement(
    dataset_engine: Engine, tmp_path: Path, target: str
) -> None:
    archive, checksum = archive_files(tmp_path / "input")
    root = storage_root(tmp_path / "storage")
    result = ingest_archive(dataset_engine, root, archive, checksum)
    artifact = next(root.rglob("*.parquet" if target == "parquet" else "manifest.json"))
    if target == "missing":
        artifact.unlink()
        damaged = None
    else:
        artifact.write_bytes(artifact.read_bytes() + b"corruption")
        damaged = artifact.read_bytes()
    with pytest.raises(DatasetError):
        inspect_version(dataset_engine, root, result["dataset_version_id"])
    with pytest.raises(DatasetError):
        ingest_archive(dataset_engine, root, archive, checksum)
    assert catalog_count(dataset_engine) == 1
    if damaged is not None:
        assert artifact.read_bytes() == damaged
    else:
        assert not artifact.exists()


def test_corrupt_orphan_is_not_adopted(dataset_engine: Engine, tmp_path: Path) -> None:
    archive, checksum = archive_files(tmp_path / "input")
    root = storage_root(tmp_path / "storage")

    def fail(phase: str) -> None:
        if phase == "before_catalog_commit":
            raise RuntimeError("deliberate rollback")

    with pytest.raises((DatasetError, RuntimeError)):
        ingest_archive(dataset_engine, root, archive, checksum, checkpoint=fail)
    assert catalog_count(dataset_engine) == 0
    parquet = next(root.rglob("*.parquet"))
    parquet.write_bytes(b"broken orphan")
    with pytest.raises(DatasetError):
        ingest_archive(dataset_engine, root, archive, checksum)
    assert catalog_count(dataset_engine) == 0
    assert parquet.read_bytes() == b"broken orphan"


def test_unknown_version_is_absent_even_with_unregistered_directory(
    dataset_engine: Engine, tmp_path: Path
) -> None:
    root = storage_root(tmp_path / "storage")
    (root / "datasets" / ("a" * 64)).mkdir(parents=True)
    assert inspect_version(dataset_engine, root, "a" * 64) is None


def test_historical_identity_coexists_with_same_synthetic_trade_id(
    dataset_engine: Engine,
    trade_engine: Engine,
    tmp_path: Path,
) -> None:
    from marketlab.trades import get_trade, import_trades_json

    payload = json.dumps(
        [
            {
                "trade_id": "1",
                "symbol": "SYN.A",
                "executed_at": "2025-01-01T00:00:00Z",
                "price": "9",
                "quantity": "2",
            }
        ]
    )
    assert import_trades_json(trade_engine, payload) == 1
    archive, checksum = archive_files(tmp_path / "input")
    manifest = ingest_archive(dataset_engine, storage_root(tmp_path / "storage"), archive, checksum)
    assert manifest["venue"] == "binance_spot"
    assert manifest["symbol"] == "BTCUSDT"
    assert manifest["quality"]["accepted_rows"] == 1
    stored = get_trade(trade_engine, "1")
    assert stored is not None and str(stored.price) == "9.00000000"
    assert stored.symbol == "SYN.A"
    assert catalog_count(dataset_engine) == 1


def test_normal_long_storage_root_ingests_and_inspects(
    dataset_engine: Engine,
    tmp_path: Path,
) -> None:
    """The public service accepts ordinary paths and extends them internally."""
    archive, checksum = archive_files(tmp_path / "input")
    ordinary_root = tmp_path / ("long-parent-" * 8) / "storage"
    manifest = ingest_archive(dataset_engine, ordinary_root, archive, checksum)
    assert (
        inspect_version(dataset_engine, ordinary_root, manifest["dataset_version_id"]) == manifest
    )
    assert len(list(storage_root(ordinary_root).rglob("manifest.json"))) == 1
