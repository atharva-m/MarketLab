"""Actual S3 family parity/races using protocol memo fixtures, not model acceptance.

Every remote version, local copy, deliberate mapping fault and private schema
remains retained. Execution requires the separately reviewed owned live launcher.
"""

import hashlib
import shutil
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID

import pytest
from test_datasets import archive_files
from test_memos_integration import ready as ready_legacy_memo
from test_storage_live import (  # noqa: F401
    browser_engine,
    credentials,
    model_engine,
    research_engine,
    storage_engine,
    v2_engine,
)
from test_storage_live import (
    s3_engine as s3_engine,
)
from test_v2_copilot_integration import ProtocolMemo
from test_v2_research import body
from test_v2_research_integration import fixture_version

from marketlab.analytics.bars import BarService
from marketlab.datasets import ingest_archive
from marketlab.datasets.publication import _storage_root
from marketlab.datasets.publication import inspect_version as inspect_legacy_dataset
from marketlab.datasets.source import DatasetError
from marketlab.datasets.v2 import admission, catalog
from marketlab.datasets.v2.common import V2Error
from marketlab.datasets.v2.core import execute, one
from marketlab.memos.v2.service import MemoService
from marketlab.research.spec import ResearchError
from marketlab.research.v2.service import ResearchService
from marketlab.research.v2.spec import ResearchSpec
from marketlab.storage import operator, store
from marketlab.storage.backend import ObjectRef, backend_for, managed_backend

pytestmark = [pytest.mark.s3, pytest.mark.integration]


@pytest.mark.asyncio
async def test_actual_six_family_read_copy_switch_reverse_and_missing_active(s3_engine, tmp_path):
    root = tmp_path / "storage"
    admission.initialize(s3_engine, root)
    legacy_memo, legacy_run = await ready_legacy_memo(s3_engine, tmp_path)
    base = BarService(s3_engine, root)
    research = ResearchService(base)
    try:
        assert await legacy_memo.work(1, legacy_run) == 1
        version = fixture_version(s3_engine, root, tmp_path)
        spec = body()
        spec["instrument_ids"] = ["binance:spot:BTCUSDT"]
        spec["dataset_versions"] = [version]
        run, _ = await research.submit(ResearchSpec.create(spec), "s3-family-parity")
        assert await research.work(1, run) == 1
        memo = MemoService(research, ProtocolMemo())
        assert await memo.work(1, run) == 1
        with s3_engine.connect() as connection:
            legacy = one(connection, "SELECT * FROM dataset_versions")
            current = one(connection, "SELECT * FROM v2_dataset_versions")
            supplemental = one(connection, "SELECT * FROM v2_memo_results")
        assert legacy is not None and current is not None and supplemental is not None
        legacy_version = legacy["dataset_version_id"]
        cases = (
            (
                "legacy_dataset",
                legacy_version,
                legacy["manifest_path"],
                lambda: inspect_legacy_dataset(s3_engine, root, legacy_version),
                DatasetError,
            ),
            (
                "v2_dataset",
                version,
                current["manifest_relative_path"],
                lambda: catalog.inspect_version(s3_engine, root, version),
                V2Error,
            ),
            (
                "legacy_research",
                legacy_run,
                f"research/{legacy_run}/manifest.json",
                lambda: legacy_memo.research.read(legacy_run, "results"),
                ResearchError,
            ),
            (
                "v2_research",
                run,
                f"research-v2/{run}/manifest.json",
                lambda: research.read(run, "results"),
                V2Error,
            ),
            (
                "legacy_memo",
                legacy_run,
                f"research/{legacy_run}/memo/manifest.json",
                lambda: legacy_memo.read(legacy_run),
                ResearchError,
            ),
            (
                "v2_memo",
                run,
                supplemental["relative_path"] + "/manifest.json",
                lambda: memo.read(run),
                V2Error,
            ),
        )
        fallbacks = []
        active_copies = []
        for owner, identity, logical_manifest, read, _ in cases:
            original = read()
            refs = store.get_registered(s3_engine, owner, identity, root=root)
            assert refs and all(ref.alias != "local" and ref.version for ref in refs)
            request = operator.plan(s3_engine, root, owner, identity)
            assert request.refs == refs
            moved = operator.copy(s3_engine, root, request, "local")
            source, target = UUID(moved["source_copy_id"]), UUID(moved["target_copy_id"])
            local_refs = tuple(ObjectRef(**member) for member in moved["members"])
            expected = {ref.member: (ref.length, ref.sha256, ref.media_schema) for ref in refs}
            assert {
                ref.member: (ref.length, ref.sha256, ref.media_schema) for ref in local_refs
            } == expected
            for ref in refs:
                with managed_backend(backend_for(root, ref.alias)) as backend:
                    backend.stat(ref)
            for ref in local_refs:
                assert ref.alias == "local" and ref.version is None
                path = _storage_root(root) / ref.key
                assert path.stat().st_size == ref.length
                assert hashlib.sha256(path.read_bytes()).hexdigest() == ref.sha256
            operator.switch(s3_engine, root, owner, identity, source, target)
            assert read() == original
            operator.switch(s3_engine, root, owner, identity, target, source)
            assert read() == original
            assert store.get_registered(s3_engine, owner, identity, root=root) == refs
            with s3_engine.connect() as connection:
                selected = store.snapshot(connection, owner, identity)
            assert selected.package_id == request.source.package_id and selected.copy_id == source
            fallbacks.append((logical_manifest, local_refs))
            active_copies.append(source)

        # Add fault-only historical paths after all legitimate location work.
        # These exact bytes and inactive local copies cannot mask a missing
        # active mapping. Existing staged evidence is verified, never replaced.
        for logical_manifest, local_refs in fallbacks:
            fallback = (_storage_root(root) / logical_manifest).parent
            fallback.mkdir(parents=True, exist_ok=True)
            for ref in local_refs:
                destination = fallback / ref.member
                if destination.exists():
                    assert hashlib.sha256(destination.read_bytes()).hexdigest() == ref.sha256
                else:
                    shutil.copyfile(_storage_root(root) / ref.key, destination)

        # Isolate each fault so memo failures cannot be caused by a missing
        # numerical dependency. Restore only this injected pointer between
        # probes, then retain all six missing-pointer faults in the final state.
        for (_, _, _, read, expected_error), copy_id in zip(cases, active_copies, strict=True):
            with s3_engine.begin() as connection:
                assert (
                    execute(
                        connection,
                        "UPDATE v2_storage_copies SET active=false WHERE copy_id=:id AND active",
                        id=copy_id,
                    ).rowcount
                    == 1
                )
            try:
                with pytest.raises(expected_error) as failure:
                    read()
                if isinstance(failure.value, V2Error):
                    assert failure.value.code == "integrity_failure"
                elif isinstance(failure.value, ResearchError):
                    assert failure.value.status == 422
                else:
                    assert "Active artifact copy missing" in str(failure.value)
            finally:
                with s3_engine.begin() as connection:
                    assert (
                        execute(
                            connection,
                            "UPDATE v2_storage_copies SET active=true "
                            "WHERE copy_id=:id AND NOT active",
                            id=copy_id,
                        ).rowcount
                        == 1
                    )
        with s3_engine.begin() as connection:
            for copy_id in active_copies:
                assert (
                    execute(
                        connection,
                        "UPDATE v2_storage_copies SET active=false WHERE copy_id=:id AND active",
                        id=copy_id,
                    ).rowcount
                    == 1
                )
    finally:
        await legacy_memo.research.bars.close()
        await research.close()
        await base.close()


def test_actual_same_version_competing_publications_retain_loser(s3_engine, tmp_path, monkeypatch):
    root = tmp_path / "storage"
    admission.initialize(s3_engine, root)
    archive, checksum = archive_files(tmp_path / "input")
    artifacts_ready = Barrier(2, timeout=60)
    uploads_verified = Barrier(2, timeout=60)
    prepare = store.prepare

    def checkpoint(phase):
        if phase == "artifacts_complete":
            artifacts_ready.wait()

    def verified_before_either_commit(*args, **kwargs):
        group = prepare(*args, **kwargs)
        assert group is not None
        uploads_verified.wait()
        return group

    monkeypatch.setattr(store, "prepare", verified_before_either_commit)

    def publish():
        return ingest_archive(s3_engine, root, archive, checksum, checkpoint=checkpoint)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(publish) for _ in range(2)]
        results = [future.result(timeout=180) for future in futures]
    assert results[0] == results[1]
    identity = results[0]["dataset_version_id"]
    assert inspect_legacy_dataset(s3_engine, root, identity) == results[0]
    refs = store.get_registered(s3_engine, "legacy_dataset", identity, root=root)
    assert refs and all(ref.alias != "local" and ref.version for ref in refs)
    with s3_engine.connect() as connection:
        assert execute(connection, "SELECT count(*) FROM dataset_versions").scalar_one() == 1
        assert execute(connection, "SELECT count(*) FROM v2_storage_packages").scalar_one() == 1
        assert (
            execute(connection, "SELECT count(*) FROM v2_storage_copies WHERE active").scalar_one()
            == 1
        )
        assert (
            execute(
                connection, "SELECT count(*) FROM ingestion_jobs WHERE state='succeeded'"
            ).scalar_one()
            == 2
        )
        charges = execute(
            connection,
            "SELECT charged_bytes,state FROM v2_data_charges WHERE backend_alias<>'local'",
        ).all()
        # The unattached loser remains conservatively reserved; it cannot be
        # refunded merely because the other attempt won the logical version.
        assert len(charges) == 2 and all(
            size >= sum(ref.length for ref in refs) and state in {"reserved", "retained"}
            for size, state in charges
        )
        assert sum(state == "retained" for _, state in charges) == 1
        assert execute(
            connection,
            "SELECT count(*) FROM v2_storage_objects WHERE backend_alias<>'local' "
            "AND state='verified' AND copy_id IS NULL",
        ).scalar_one() == len(refs)
