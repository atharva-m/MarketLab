"""Local-only Phase 6 PostgreSQL, receipt, upload and location checks."""

import hashlib
import importlib.util
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from test_v2_browser_imports_integration import DATA, manifest, request
from test_v2_browser_imports_integration import browser_engine as browser_engine  # noqa: F401
from test_v2_copilot_integration import model_engine as model_engine  # noqa: F401
from test_v2_ingestion_integration import v2_engine as v2_engine  # noqa: F401
from test_v2_research_integration import research_engine as research_engine  # noqa: F401

from marketlab.datasets.v2 import admission
from marketlab.datasets.v2.browser_imports import BrowserImports
from marketlab.datasets.v2.common import V2Error
from marketlab.datasets.v2.core import execute
from marketlab.storage import operator, store
from marketlab.storage.backend import LocalBackend
from marketlab.storage.materialize import CACHE

pytestmark = pytest.mark.integration


@pytest.fixture
def storage_engine(model_engine, monkeypatch):
    monkeypatch.setenv("MARKETLAB_STORAGE_BACKEND", "local")
    monkeypatch.delenv("MARKETLAB_STORAGE_S3_ENDPOINT", raising=False)
    apply_storage(model_engine)
    try:
        yield model_engine
    finally:
        CACHE.close()


def apply_storage(engine):
    path = Path(__file__).resolve().parents[1] / "migrations/versions/0012_v2_storage.py"
    spec = importlib.util.spec_from_file_location("phase6_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with engine.begin() as connection:
        connection.exec_driver_sql(module.DDL)
        connection.exec_driver_sql("CREATE TABLE alembic_version (version_num varchar(32))")
        connection.exec_driver_sql("INSERT INTO alembic_version VALUES ('0012_v2_storage')")


@pytest.mark.asyncio
async def test_populated_upgrade_keeps_uploaded_unfinalized_generation_usable(
    model_engine, tmp_path
):
    root = tmp_path / "data"
    admission.initialize(model_engine, root)
    browser = BrowserImports(model_engine, root)
    made = browser.create(
        {"manifest": manifest(DATA), "content_length": len(DATA)}, "before-upgrade"
    )
    uploaded = await browser.receive(
        made["id"], request(DATA, made["upload"]["required_headers"]["X-Upload-Token"])
    )
    apply_storage(model_engine)
    admission.initialize(model_engine, root)
    result = browser.finalize(
        made["id"],
        {"expected_revision": uploaded["revision"], "generation": made["upload"]["generation"]},
        "after-upgrade",
    )
    assert result["state"] == "queued"


@pytest.mark.parametrize("retained", [32, 31])
def test_populated_upgrade_exact_source_link_never_refunds_unknown_bytes(
    model_engine, tmp_path, retained
):
    root = tmp_path / "data"
    admission.initialize(model_engine, root)
    browser = BrowserImports(model_engine, root)
    payload = b"x" * 64
    made = browser.create({"manifest": manifest(payload), "content_length": 64}, "pending")
    with model_engine.begin() as connection:
        generation = (
            execute(
                connection,
                "SELECT * FROM v2_upload_generations WHERE generation_id=:id",
                id=made["upload"]["generation"],
            )
            .mappings()
            .one()
        )
        path = root / generation["relative_path"]
        path.parent.mkdir(parents=True)
        path.write_bytes(b"x" * 32)
        # Represent a prior crashed local upload and its retained reservation.
        execute(
            connection,
            "UPDATE v2_upload_generations SET state='failed',received_bytes=:n",
            n=retained,
        )
        execute(
            connection,
            "UPDATE v2_canonical_imports SET state='upload_failed',received_bytes=:n",
            n=retained,
        )
        execute(
            connection,
            "UPDATE v2_storage_reservations SET retained_bytes=:n,reserved_bytes=64-:n",
            n=retained,
        )
        execute(
            connection,
            "UPDATE v2_admission_tickets SET state='released',physical_bytes=0",
        )
    apply_storage(model_engine)
    for _ in range(2):
        receipt = admission.initialize(model_engine, root)
        with model_engine.connect() as connection:
            linked = execute(
                connection, "SELECT data_charge_id FROM v2_storage_reservations"
            ).scalar_one()
            charge, state = execute(
                connection, "SELECT charged_bytes,state FROM v2_data_charges"
            ).one()
        assert linked is not None
        if retained == 32:
            assert receipt["retained_bytes"] + receipt["reserved_bytes"] == 64
            assert state == "absorbed"
        else:
            assert (charge, state) == (64, "reserved")


def test_partial_intent_attachment_cannot_release_a_charge(storage_engine, tmp_path):
    root = tmp_path / "data"
    admission.initialize(storage_engine, root)
    ticket = admission.acquire(storage_engine, root, "legacy", 64, physical_bytes=64)
    assert ticket is not None
    content = b"verified fixture"
    source = tmp_path / "source"
    source.write_bytes(content)
    group = store.begin(
        storage_engine,
        root,
        ticket,
        str(uuid4()),
        1,
        [
            (name, "application/json", len(content), hashlib.sha256(content).hexdigest())
            for name in ("manifest.json", "results.json")
        ],
    )
    assert group is not None
    complete = group.write_paths({"manifest.json": source, "results.json": source})
    with pytest.raises(V2Error, match="receipt set changed"):
        with storage_engine.begin() as connection:
            store.attach(connection, replace(complete, intents=complete.intents[:1]), uuid4())
    admission.finish(storage_engine, ticket, 0)
    with storage_engine.connect() as connection:
        assert execute(connection, "SELECT charged_bytes FROM v2_data_charges").scalar_one() == 64
        assert (
            execute(
                connection, "SELECT count(*) FROM v2_storage_objects WHERE copy_id IS NULL"
            ).scalar_one()
            == 2
        )
    admission.audit(storage_engine, root)


def _orphan_group(engine, root, source):
    admission.initialize(engine, root)
    ticket = admission.acquire(engine, root, "legacy", 64, physical_bytes=64)
    assert ticket is not None
    source.write_bytes(b"owned bytes")
    group = store.begin(
        engine,
        root,
        ticket,
        str(uuid4()),
        1,
        [
            (
                name,
                "application/json",
                source.stat().st_size,
                hashlib.sha256(source.read_bytes()).hexdigest(),
            )
            for name in ("one.json", "two.json")
        ],
    )
    assert group is not None
    complete = group.write_paths({"one.json": source, "two.json": source})
    return ticket, complete


def test_retirement_refuses_live_writer_then_releases_only_complete_orphan_group(
    storage_engine, tmp_path
):
    root = tmp_path / "data"
    ticket, group = _orphan_group(storage_engine, root, tmp_path / "source")
    first, second = group.intents
    with pytest.raises(V2Error, match="drained writers"):
        operator.delete_unreferenced(storage_engine, root, first.object_id)
    admission.finish(storage_engine, ticket)
    operator.delete_unreferenced(storage_engine, root, first.object_id)
    with storage_engine.connect() as connection:
        assert (
            execute(
                connection,
                "SELECT charged_bytes FROM v2_data_charges WHERE charge_id=:id",
                id=group.charge_id,
            ).scalar_one()
            == 64
        )
    operator.delete_unreferenced(storage_engine, root, second.object_id)
    with storage_engine.connect() as connection:
        assert execute(
            connection,
            "SELECT charged_bytes,state FROM v2_data_charges WHERE charge_id=:id",
            id=group.charge_id,
        ).one() == (0, "released")


def test_retirement_failure_keeps_charge_and_readiness_closed(
    storage_engine, tmp_path, monkeypatch
):
    root = tmp_path / "data"
    ticket, group = _orphan_group(storage_engine, root, tmp_path / "source")
    admission.finish(storage_engine, ticket)

    def fail(self, ref):
        raise V2Error("unavailable", "Owned injected removal failure")

    monkeypatch.setattr(LocalBackend, "delete_unreferenced", fail)
    with pytest.raises(V2Error, match="injected removal failure"):
        operator.delete_unreferenced(storage_engine, root, group.intents[0].object_id)
    with storage_engine.connect() as connection:
        assert not admission.binding(connection)["ready"]
        assert (
            execute(
                connection,
                "SELECT charged_bytes FROM v2_data_charges WHERE charge_id=:id",
                id=group.charge_id,
            ).scalar_one()
            == 64
        )


@pytest.mark.asyncio
async def test_managed_local_browser_staging_switch_reverse_and_no_fallback(
    storage_engine, tmp_path
):
    root = tmp_path / "data"
    admission.initialize(storage_engine, root)
    browser = BrowserImports(storage_engine, root)
    made = browser.create({"manifest": manifest(DATA), "content_length": len(DATA)}, "managed")
    generation = made["upload"]["generation"]
    token = made["upload"]["required_headers"]["X-Upload-Token"]
    uploaded = await browser.receive(made["id"], request(DATA, token))
    assert uploaded["state"] == "uploaded"
    first = store.get_registered(storage_engine, "upload_generation", generation, root=root)
    assert first and len(first) == 1
    assert first[0].sha256 == hashlib.sha256(DATA).hexdigest()
    with storage_engine.connect() as connection:
        attached = execute(
            connection, "SELECT object_id FROM v2_storage_objects WHERE copy_id IS NOT NULL"
        ).scalar_one()
    with pytest.raises(V2Error, match="referenced"):
        operator.delete_unreferenced(storage_engine, root, attached)
    result = browser.finalize(
        made["id"], {"expected_revision": uploaded["revision"], "generation": generation}, "fin"
    )
    assert result["state"] == "queued"
    selected = operator.plan(storage_engine, root, "upload_generation", generation)
    receipt = operator.copy(storage_engine, root, selected, "local")
    old, new = UUID(receipt["source_copy_id"]), UUID(receipt["target_copy_id"])
    operator.switch(storage_engine, root, "upload_generation", generation, old, new)
    moved = store.get_registered(storage_engine, "upload_generation", generation, root=root)
    assert moved and moved[0].key != first[0].key and moved[0].sha256 == first[0].sha256
    operator.switch(storage_engine, root, "upload_generation", generation, new, old)
    assert store.get_registered(storage_engine, "upload_generation", generation, root=root) == first
    for _ in range(2):
        assert admission.initialize(storage_engine, root)["retained_bytes"] == 2 * len(DATA)
    with storage_engine.begin() as connection:
        execute(connection, "UPDATE v2_storage_copies SET active=false WHERE copy_id=:id", id=old)
    with pytest.raises(V2Error, match="Active artifact copy missing"):
        store.get_registered(storage_engine, "upload_generation", generation, root=root)
