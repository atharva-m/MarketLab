"""Managed local reader publication and shared physical reservation checks."""

import hashlib
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID

import pytest
from test_memos_integration import ready as ready_legacy_memo
from test_storage_store_integration import storage_engine as storage_engine  # noqa: F401
from test_v2_browser_imports_integration import browser_engine as browser_engine  # noqa: F401
from test_v2_copilot_integration import ProtocolMemo
from test_v2_copilot_integration import model_engine as model_engine  # noqa: F401
from test_v2_ingestion_integration import v2_engine as v2_engine  # noqa: F401
from test_v2_research import body
from test_v2_research_integration import fixture_version
from test_v2_research_integration import research_engine as research_engine  # noqa: F401

from marketlab.analytics.bars import BarService
from marketlab.datasets.publication import _storage_root
from marketlab.datasets.publication import inspect_version as inspect_legacy_dataset
from marketlab.datasets.source import DatasetError
from marketlab.datasets.v2 import admission, catalog
from marketlab.datasets.v2.capacity import outstanding
from marketlab.datasets.v2.common import V2Error
from marketlab.datasets.v2.core import execute, one
from marketlab.memos.v2.service import MemoService
from marketlab.research.v2.service import ResearchService
from marketlab.research.v2.spec import ResearchSpec
from marketlab.storage import materialize_space, store
from marketlab.storage.backend import ObjectRef, backend_for
from marketlab.storage.materialize import CACHE, materialize_package

pytestmark = pytest.mark.integration


@pytest.fixture
def reader_engine(storage_engine):
    try:
        yield storage_engine
    finally:
        CACHE.close(storage_engine)


def test_materialization_reservations_compete_under_shared_lock(
    storage_engine, tmp_path, monkeypatch
):
    root = tmp_path / "data"
    admission.initialize(storage_engine, root)
    monkeypatch.setattr(
        materialize_space.shutil, "disk_usage", lambda path: SimpleNamespace(free=4096)
    )
    start = Barrier(2, timeout=5)

    def compete(_):
        start.wait()
        try:
            return materialize_space.reserve_space(storage_engine, root, 3072)
        except V2Error as error:
            assert error.code == "capacity_exceeded"
            return None

    with ThreadPoolExecutor(2) as pool:
        reservations = [space for space in pool.map(compete, range(2)) if space is not None]
    try:
        assert len(reservations) == 1
        with storage_engine.connect() as connection:
            assert outstanding(connection) == 3072
        owned = reservations[0]
        (owned.path / "payload").write_bytes(b"owned physical bytes")
        admission.audit(storage_engine, root)
    finally:
        for space in reservations:
            space.close()
    with storage_engine.connect() as connection:
        assert outstanding(connection) == 0


def test_live_package_view_has_shared_inventory_coverage(reader_engine, tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    raw = b"verified fixture"
    (root / "source.json").write_bytes(raw)
    admission.initialize(reader_engine, root)
    ref = ObjectRef(
        "local",
        "source.json",
        None,
        len(raw),
        hashlib.sha256(raw).hexdigest(),
        "manifest.json",
        "application/json",
    )
    with materialize_package(reader_engine, root, (ref,), root) as path:
        assert (path / ref.member).read_bytes() == raw
        admission.audit(reader_engine, root)
        with reader_engine.connect() as connection:
            assert outstanding(connection) == 2 * len(raw)
    CACHE.close(reader_engine)
    with reader_engine.connect() as connection:
        assert outstanding(connection) == 0


def test_explicit_recovery_proves_native_drain_before_releasing(storage_engine, tmp_path):
    root = tmp_path / "data"
    admission.initialize(storage_engine, root)
    with storage_engine.connect() as connection:
        schema = execute(connection, "SELECT current_schema()").scalar_one()
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from pathlib import Path
from sqlalchemy import create_engine
from marketlab.config import Settings
from marketlab.storage.materialize_space import reserve_space

schema, root = sys.argv[1:]
engine = create_engine(
    Settings().sqlalchemy_url, connect_args={"options": f"-c search_path={schema}"}
)
for pending in (False, True):
    space = reserve_space(engine, Path(root), 32, children_pending=pending)
    (space.path / "payload").write_bytes(b"owned bytes")
    print(space.identifier)
engine.dispose()
""",
            schema,
            str(root),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    (tmp_path / "child-stderr.txt").write_text(child.stderr, encoding="utf-8")
    assert child.returncode == 0, child.stderr
    drained, unresolved = map(UUID, child.stdout.split())
    for identifier in (drained, unresolved):
        assert (root / ".materializations" / str(identifier) / "payload").is_file()
    assert materialize_space.reclaim_dead(storage_engine, root, drained)["state"] == "released"
    assert not (root / ".materializations" / str(drained)).exists()
    with pytest.raises(V2Error, match="native owner or reader is unresolved"):
        materialize_space.reclaim_dead(storage_engine, root, unresolved)
    assert (root / ".materializations" / str(unresolved) / "payload").is_file()
    with storage_engine.connect() as connection:
        assert outstanding(connection) == 32


@pytest.mark.asyncio
async def test_registered_local_readers_without_historical_artifact_paths(reader_engine, tmp_path):
    storage_engine = reader_engine
    root = tmp_path / "storage"
    admission.initialize(storage_engine, root)
    legacy_memo, legacy_run = await ready_legacy_memo(storage_engine, tmp_path)
    base = BarService(storage_engine, root)
    research = ResearchService(base)
    try:
        assert await legacy_memo.work(1, legacy_run) == 1
        with storage_engine.connect() as connection:
            legacy = one(connection, "SELECT * FROM dataset_versions")
        assert legacy is not None
        legacy_version = legacy["dataset_version_id"]

        version = fixture_version(storage_engine, root, tmp_path)
        spec = body()
        spec["instrument_ids"] = ["binance:spot:BTCUSDT"]
        spec["dataset_versions"] = [version]
        run, _ = await research.submit(ResearchSpec.create(spec), "mapped-run")
        assert await research.work(1, run) == 1
        memo = MemoService(research, ProtocolMemo())
        assert await memo.work(1, run) == 1
        with storage_engine.connect() as connection:
            current = one(connection, "SELECT * FROM v2_dataset_versions")
            supplemental = one(connection, "SELECT * FROM v2_memo_results")
        assert current is not None and supplemental is not None
        # V2 memo attempts retain their original staged package after copying.
        # Preserve that owned terminal directory as fault evidence so this read
        # can prove independence from the original layout.
        staging = root / supplemental["relative_path"]
        retained_staging = tmp_path / "retained-v2-memo-staging"
        assert staging.resolve().is_relative_to(root.resolve())
        assert retained_staging.resolve().is_relative_to(tmp_path.resolve())
        staging.rename(retained_staging)

        for owner, identity, logical in (
            ("legacy_dataset", legacy_version, legacy["manifest_path"]),
            ("v2_dataset", version, current["manifest_relative_path"]),
            ("legacy_research", legacy_run, f"research/{legacy_run}/manifest.json"),
            ("v2_research", run, f"research-v2/{run}/manifest.json"),
            ("legacy_memo", legacy_run, f"research/{legacy_run}/memo/manifest.json"),
            ("v2_memo", run, supplemental["relative_path"] + "/manifest.json"),
        ):
            refs = store.get_registered(storage_engine, owner, identity, root=root)
            assert refs and all(ref.alias == "local" for ref in refs)
            for ref in refs:
                backend_for(root, ref.alias).stat(ref)
            assert not (root / logical).exists()

        assert inspect_legacy_dataset(storage_engine, root, legacy_version)
        assert (
            catalog.inspect_version(storage_engine, root, version)["dataset_version_id"] == version
        )
        assert (
            legacy_memo.research.read(legacy_run, "results")[0]["schema"] == "research-results-v1"
        )
        assert research.read(run, "results")[0]["schema"] == "research-results-v2"
        assert len(legacy_memo.read(legacy_run)[0].strip().split("\n\n")) == 3
        assert len(memo.read(run)[0].strip().split("\n\n")) == 3

        # Even byte-exact historical paths cannot substitute for a lost active
        # mapping after this package has explicit storage ownership.
        refs = store.get_registered(storage_engine, "legacy_dataset", legacy_version, root=root)
        assert refs is not None
        fallback = (_storage_root(root) / legacy["manifest_path"]).parent
        fallback.mkdir(parents=True)
        for ref in refs:
            shutil.copyfile(_storage_root(root) / ref.key, fallback / ref.member)
        with storage_engine.begin() as connection:
            active = store.snapshot(connection, "legacy_dataset", legacy_version)
            execute(
                connection,
                "UPDATE v2_storage_copies SET active=false WHERE copy_id=:id",
                id=active.copy_id,
            )
        with pytest.raises(DatasetError, match="Active artifact copy missing"):
            inspect_legacy_dataset(storage_engine, root, legacy_version)
    finally:
        await legacy_memo.research.bars.close()
        await research.close()
        await base.close()
