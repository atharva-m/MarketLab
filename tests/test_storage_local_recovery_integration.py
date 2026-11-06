"""Local-only restore entry points against separate owned PostgreSQL databases."""

import json
import os
import shutil
import subprocess
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_storage_store_integration import storage_engine as storage_engine  # noqa: F401
from test_v2_browser_imports_integration import DATA, manifest, request
from test_v2_browser_imports_integration import browser_engine as browser_engine  # noqa: F401
from test_v2_copilot_integration import model_engine as model_engine  # noqa: F401
from test_v2_ingestion_integration import v2_engine as v2_engine  # noqa: F401
from test_v2_research_integration import research_engine as research_engine  # noqa: F401

from marketlab.config import Settings
from marketlab.datasets.v2 import admission, catalog, service
from marketlab.datasets.v2.browser_imports import BrowserImports
from marketlab.datasets.v2.common import V2Error, digest
from marketlab.datasets.v2.core import execute
from marketlab.storage import recovery, store
from marketlab.storage.materialize import CACHE

pytestmark = pytest.mark.integration


@pytest.fixture
def local_engine(storage_engine, monkeypatch):
    monkeypatch.setenv("MARKETLAB_STORAGE_BACKEND", "local")
    for suffix in ("ENDPOINT", "BUCKET", "ACCESS_KEY", "SECRET_KEY", "SESSION_TOKEN"):
        monkeypatch.delenv("MARKETLAB_STORAGE_S3_" + suffix, raising=False)
    return storage_engine


def test_local_restore_rejects_original_database(local_engine, tmp_path):
    root = tmp_path / "source"
    admission.initialize(local_engine, root)
    receipt = recovery.local_backup_inventory(local_engine, root)
    other = tmp_path / "restored"
    other.mkdir()
    with pytest.raises(V2Error, match="original database"):
        recovery.local_rebind_restore(local_engine, other, receipt)
    with local_engine.connect() as connection:
        assert admission.binding(connection)["root_path"] == str(root.resolve())


@pytest.mark.parametrize(
    "proof", [None, {}, {"database_oid": "1"}, {"cluster_identifier": "", "database_oid": "1"}]
)
def test_local_restore_requires_exact_source_identity(local_engine, tmp_path, proof):
    root = tmp_path / "source"
    admission.initialize(local_engine, root)
    receipt = recovery.local_backup_inventory(local_engine, root)
    if proof is None:
        receipt.pop("source_database")
    else:
        receipt["source_database"] = proof
    receipt["inventory_sha256"] = digest(
        {key: value for key, value in receipt.items() if key != "inventory_sha256"}
    )
    with pytest.raises(V2Error, match="Invalid isolated restore inventory"):
        recovery.local_rebind_restore(local_engine, tmp_path / "other", receipt)


@pytest.mark.parametrize(
    "settings",
    [
        {"storage_backend": "unavailable"},
        {"storage_s3_endpoint": "https://example.invalid"},
        {"storage_s3_bucket": "unavailable"},
        {"storage_s3_access_key": "unused-local-guard"},
    ],
)
def test_local_entry_points_reject_nonlocal_configuration(local_engine, tmp_path, settings):
    configured = Settings(**settings)
    with pytest.raises(V2Error, match="local-only storage configuration"):
        recovery.local_backup_inventory(local_engine, tmp_path, configured)
    with pytest.raises(V2Error, match="local-only storage configuration"):
        recovery.local_rebind_restore(local_engine, tmp_path / "other", {}, configured)


@pytest.mark.parametrize("field,value", [("object_alias", "unavailable"), ("remote_members", [{}])])
def test_local_restore_rejects_nonlocal_backup_receipt(local_engine, tmp_path, field, value):
    root = tmp_path / "source"
    admission.initialize(local_engine, root)
    receipt = recovery.local_backup_inventory(local_engine, root)
    receipt[field] = value
    receipt["inventory_sha256"] = digest(
        {key: item for key, item in receipt.items() if key != "inventory_sha256"}
    )
    with pytest.raises(V2Error, match="entirely local backup"):
        recovery.local_rebind_restore(local_engine, tmp_path / "other", receipt)


def test_local_backup_rejects_nonlocal_retained_ledger(local_engine, tmp_path):
    root = tmp_path / "source"
    admission.initialize(local_engine, root)
    with local_engine.begin() as connection:
        execute(
            connection,
            "INSERT INTO v2_data_charges (charge_id,root_id,ceiling_bytes,charged_bytes,state,"
            "backend_alias,created_at,updated_at) SELECT :id,root_id,1,1,'retained',"
            "'unavailable',clock_timestamp(),clock_timestamp() FROM v2_capacity_roots",
            id=uuid4(),
        )
    with pytest.raises(V2Error, match="remote storage records"):
        recovery.local_backup_inventory(local_engine, root)


def _owned_postgres(engine):
    container = os.environ.get("MARKETLAB_PHASE6_PG_CONTAINER")
    if not container:
        pytest.skip("requires an explicitly identified owned Phase 6 PostgreSQL container")
    observed = json.loads(
        subprocess.run(
            ["docker", "inspect", container],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        ).stdout
    )[0]
    assert observed["Config"]["Labels"].get("marketlab.phase6.owner") == "phase6-implementation"
    assert observed["State"]["Running"]
    expected_hosts = {
        "127.0.0.1": {"127.0.0.1"},
        "localhost": {"127.0.0.1", "::1"},
        "::1": {"::1"},
    }
    assert engine.url.host in expected_hosts, "local recovery tests require an owned loopback DB"
    bindings = observed["NetworkSettings"]["Ports"]["5432/tcp"]
    assert any(
        int(binding["HostPort"]) == engine.url.port
        and binding["HostIp"] in expected_hosts[engine.url.host]
        for binding in bindings
    )
    return observed["Id"]


@pytest.fixture
def restored_database(local_engine, tmp_path):
    container = _owned_postgres(local_engine)
    with local_engine.connect() as connection:
        schema = execute(connection, "SELECT current_schema()").scalar_one()
    name = "phase6_local_restore_" + uuid4().hex
    admin = sa.create_engine(
        local_engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with admin.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    target = sa.create_engine(
        local_engine.url.set(database=name), connect_args={"options": f"-c search_path={schema}"}
    )

    def restore():
        saved = subprocess.run(
            [
                "docker",
                "exec",
                container,
                "pg_dump",
                "-U",
                local_engine.url.username,
                "-d",
                local_engine.url.database,
                "--schema",
                schema,
                "--no-owner",
                "--no-privileges",
                "--format=c",
            ],
            check=True,
            capture_output=True,
            timeout=60,
        ).stdout
        (tmp_path / "local-schema.dump").write_bytes(saved)
        subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                container,
                "pg_restore",
                "-U",
                local_engine.url.username,
                "-d",
                name,
                "--no-owner",
                "--no-privileges",
                "--exit-on-error",
            ],
            input=saved,
            check=True,
            capture_output=True,
            timeout=60,
        )
        return target

    try:
        yield restore
    finally:
        CACHE.close(target)
        target.dispose()
        with admin.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}"')
        admin.dispose()


@pytest.mark.asyncio
async def test_local_restore_verifies_distinct_database_bytes_and_normal_readers(
    local_engine, restored_database, tmp_path
):
    root = tmp_path / "source"
    admission.initialize(local_engine, root)
    browser = BrowserImports(local_engine, root)
    created = browser.create({"manifest": manifest(DATA), "content_length": len(DATA)}, "source")
    uploaded = await browser.receive(
        created["id"], request(DATA, created["upload"]["required_headers"]["X-Upload-Token"])
    )
    receipt = recovery.local_backup_inventory(local_engine, root)
    target = restored_database()
    destination = tmp_path / "restored"
    shutil.copytree(root, destination)
    sample = destination / receipt["local_files"][0]["relative_path"]
    original = sample.read_bytes()
    sample.write_bytes(b"invalid restored bytes")
    with pytest.raises(V2Error, match="Restored local file differs"):
        recovery.local_rebind_restore(target, destination, receipt)
    sample.unlink()
    with pytest.raises(V2Error, match="Restored local file differs"):
        recovery.local_rebind_restore(target, destination, receipt)
    with target.connect() as connection:
        assert admission.binding(connection)["root_path"] == str(root.resolve())
    sample.write_bytes(original)
    assert recovery.local_rebind_restore(target, destination, receipt) == {}
    refs = store.get_registered(
        target, "upload_generation", created["upload"]["generation"], root=destination
    )
    assert refs and all(ref.alias == "local" for ref in refs)
    restored = BrowserImports(target, destination)
    queued = restored.finalize(
        created["id"],
        {"expected_revision": uploaded["revision"], "generation": created["upload"]["generation"]},
        "restored-finalize",
    )
    assert (
        service.work(target, destination, max_jobs=1, submission_id=queued["submission_id"])[
            "succeeded_jobs"
        ]
        == 1
    )
    version = restored.inspect(created["id"])["dataset_version_id"]
    assert catalog.inspect_version(target, destination, version)["dataset_version_id"] == version
    assert recovery.local_backup_inventory(local_engine, root) == receipt
