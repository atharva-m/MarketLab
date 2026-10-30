"""Acceptance orchestration rejects unbound inputs before independent scoring."""

import copy
import hashlib
import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from marketlab.datasets.v2.common import canonical_json


@pytest.fixture
def harness():
    path = Path(__file__).resolve().parents[1] / "scripts/v2_phase3_acceptance.py"
    specification = importlib.util.spec_from_file_location("phase3_harness_under_test", path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class Connection:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


def discovery(harness, monkeypatch, rows):
    queries = []

    def execute(connection, query, **values):
        queries.append((query, values))
        return SimpleNamespace(mappings=lambda: rows)

    monkeypatch.setattr(harness.core, "execute", execute)
    return SimpleNamespace(connect=Connection), queries


def test_discovery_only_hash_checks_scoped_bounded_manifest(harness, tmp_path, monkeypatch):
    version = harness.RETAINED["sol_official"]
    raw = canonical_json({"schema": "dataset-manifest-v2", "dataset_version_id": version})
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes(raw)
    row = {
        "manifest_relative_path": "manifest.json",
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "dataset_version_id": version,
    }
    engine, queries = discovery(harness, monkeypatch, [row])
    result = harness.registered(engine, tmp_path)
    assert result[0]["manifest"]["dataset_version_id"] == version
    query, values = queries[0]
    assert "LIMIT 101" in query and "2025-02-28" in query and "2025-03-03" in query
    assert set(values.values()) == set(harness.RETAINED.values())
    manifest.write_bytes(raw + b" ")
    with pytest.raises(AssertionError):
        harness.registered(engine, tmp_path)


def test_discovery_refuses_unbounded_alternatives_before_file_reads(harness, tmp_path, monkeypatch):
    engine, _ = discovery(harness, monkeypatch, [{}] * 101)
    with pytest.raises(AssertionError, match="bounded discovery"):
        harness.registered(engine, tmp_path)


@pytest.mark.parametrize("change", ["signature", "catalog_identity"])
def test_oracle_requires_unchanged_native_catalog_and_signature(harness, monkeypatch, change):
    row = {
        "dataset_version_id": "a" * 64,
        "catalog_identity": ("registered",),
        "signature": (1, 2, 3),
        "path": Path("unopened"),
    }
    current = copy.deepcopy(row)
    bars = SimpleNamespace(_catalog=lambda versions: [current])
    called = []

    def oracle(*args):
        called.append(True)
        current[change] = ("changed",)
        return {}

    monkeypatch.setattr(harness, "oracle_bars", oracle)
    with pytest.raises(AssertionError, match="binding changed"):
        harness.verified_oracle(
            bars, row, datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 2, tzinfo=UTC)
        )
    assert called == [True]


@pytest.mark.asyncio
async def test_native_preparation_reserves_calls_real_service_surface_and_drains(
    harness, tmp_path, monkeypatch
):
    calls = []
    reservation = {"path": tmp_path}

    def reserve(*args):
        calls.append("reserve")
        return reservation

    def release(*args):
        calls.append("release")

    async def prepare(identities, versions, first, before, stop):
        calls.append((identities, versions, stop.is_set()))
        return [{"dataset_version_id": versions[0]}]

    monkeypatch.setattr(harness.capacity, "reserve", reserve)
    monkeypatch.setattr(harness.capacity, "release", release)
    research = SimpleNamespace(
        engine=object(), root=tmp_path, bars=SimpleNamespace(prepare_selection=prepare)
    )
    rows = await harness.native_preparation(
        research,
        ["binance:spot:SOLUSDT"],
        ["a" * 64],
        datetime(2025, 3, 1, tzinfo=UTC),
        datetime(2025, 3, 2, tzinfo=UTC),
    )
    assert rows == [{"dataset_version_id": "a" * 64}]
    assert calls == ["reserve", (["binance:spot:SOLUSDT"], ["a" * 64], False), "release"]
