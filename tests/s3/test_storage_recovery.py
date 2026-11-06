"""Restore-binding feature checks, including guards. All require S3-test authority."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import URL
from test_storage_live import credentials as credentials  # noqa: F401
from test_storage_live import s3_engine as s3_engine  # noqa: F401
from test_storage_store_integration import storage_engine as storage_engine  # noqa: F401
from test_v2_browser_imports_integration import DATA, manifest, request
from test_v2_browser_imports_integration import browser_engine as browser_engine  # noqa: F401
from test_v2_copilot_integration import model_engine as model_engine  # noqa: F401
from test_v2_ingestion_integration import v2_engine as v2_engine  # noqa: F401
from test_v2_research_integration import research_engine as research_engine  # noqa: F401

from marketlab.config import Settings
from marketlab.datasets.v2 import admission
from marketlab.datasets.v2.browser_imports import BrowserImports
from marketlab.datasets.v2.common import V2Error, digest, safe_path
from marketlab.storage import recovery, store
from marketlab.storage.backend import (
    ObjectConfig,
    S3Backend,
    backend_for,
    managed_backend,
    new_prefix,
)

pytestmark = [pytest.mark.s3, pytest.mark.integration]


def test_source_database_cannot_be_rebound_using_a_copied_root(storage_engine, tmp_path):
    root, other = tmp_path / "source", tmp_path / "restored"
    admission.initialize(storage_engine, root)
    receipt = recovery.backup_inventory(storage_engine, root)
    other.mkdir()
    with pytest.raises(V2Error, match="original database"):
        recovery.rebind_restore(storage_engine, other, receipt, {}, Settings())
    with storage_engine.connect() as connection:
        assert admission.binding(connection)["root_path"] == str(root.resolve())


@pytest.mark.parametrize(
    "proof", [None, {}, {"database_oid": "1"}, {"cluster_identifier": "", "database_oid": "1"}]
)
def test_missing_source_database_proof_is_rejected_even_with_valid_receipt_hash(
    storage_engine, tmp_path, proof
):
    root, other = tmp_path / "source", tmp_path / "restored"
    admission.initialize(storage_engine, root)
    receipt = recovery.backup_inventory(storage_engine, root)
    if proof is None:
        receipt.pop("source_database")
    else:
        receipt["source_database"] = proof
    receipt["inventory_sha256"] = digest(
        {key: value for key, value in receipt.items() if key != "inventory_sha256"}
    )
    other.mkdir()
    with pytest.raises(V2Error, match="Invalid isolated restore inventory"):
        recovery.rebind_restore(storage_engine, other, receipt, {}, Settings())


def _postgres_env(url: URL) -> tuple[str, dict[str, str]]:
    plain = URL.create(
        "postgresql",
        username=url.username,
        host=url.host,
        port=url.port,
        database=url.database,
    ).render_as_string(hide_password=False)
    return plain, {**os.environ, "PGPASSWORD": url.password or ""}


def _restore_schema(source, target_url: URL, schema: str, destination: Path):
    dump, restore = shutil.which("pg_dump"), shutil.which("pg_restore")
    if not dump or not restore:
        pytest.skip("requires installed PostgreSQL dump/restore tools")
    source_url, source_env = _postgres_env(source.url)
    target, target_env = _postgres_env(target_url)
    saved = destination / "database.dump"
    subprocess.run(
        [
            dump,
            "--dbname",
            source_url,
            "--format=c",
            "--no-owner",
            "--no-privileges",
            "--schema",
            schema,
            "--file",
            str(saved),
        ],
        env=source_env,
        check=True,
        capture_output=True,
        timeout=120,
    )
    subprocess.run(
        [restore, "--dbname", target, "--no-owner", "--no-privileges", str(saved)],
        env=target_env,
        check=True,
        capture_output=True,
        timeout=120,
    )


@pytest.mark.asyncio
async def test_verified_restore_uses_distinct_database_and_new_provider_versions(
    s3_engine, tmp_path, monkeypatch
):
    target_url = os.environ.get("MARKETLAB_PHASE6_RESTORE_DATABASE_URL")
    restored_endpoint = os.environ.get("MARKETLAB_PHASE6_RESTORE_S3_ENDPOINT")
    if not target_url or not restored_endpoint:
        pytest.skip("requires separately provisioned owned restore DB and S3 namespace")
    root = tmp_path / "source"
    admission.initialize(s3_engine, root)
    browser = BrowserImports(s3_engine, root)
    created = browser.create(
        {"manifest": manifest(DATA), "content_length": len(DATA)}, "backup-case"
    )
    await browser.receive(
        created["id"], request(DATA, created["upload"]["required_headers"]["X-Upload-Token"])
    )
    backup = recovery.backup_inventory(s3_engine, root)
    backup_file = tmp_path / "backup.json"
    backup_file.write_text(json.dumps(backup))
    with s3_engine.connect() as connection:
        schema = connection.exec_driver_sql("SELECT current_schema()").scalar_one()
        source_identity = recovery.database_identity(connection)
    destination = sa.make_url(target_url)
    restored = sa.create_engine(destination, connect_args={"options": f"-c search_path={schema}"})
    try:
        with restored.connect() as connection:
            assert recovery.database_identity(connection) != source_identity
            assert (
                connection.exec_driver_sql("SELECT to_regnamespace(%s)", (schema,)).scalar_one()
                is None
            )
        _restore_schema(s3_engine, destination, schema, tmp_path)
        restored_root = tmp_path / "restored"
        shutil.copytree(root, restored_root)
        # The backup exports exact source generations before changing configuration.
        exports = {}
        for row in backup["remote_members"]:
            path = tmp_path / (row["object_id"] + ".bin")
            with (
                path.open("xb") as stream,
                managed_backend(backend_for(root, row["alias"])) as source,
            ):
                source.read_verified(recovery._ref(row), stream)
            exports[row["object_id"]] = path
        for suffix in (
            "ENDPOINT",
            "REGION",
            "BUCKET",
            "PREFIX",
            "ACCESS_KEY",
            "SECRET_KEY",
            "SESSION_TOKEN",
        ):
            value = os.environ.get("MARKETLAB_PHASE6_RESTORE_S3_" + suffix)
            if value is not None:
                monkeypatch.setenv("MARKETLAB_STORAGE_S3_" + suffix, value)
        monkeypatch.setenv("MARKETLAB_STORAGE_S3_ALIAS", "restored-" + schema[-12:])
        monkeypatch.setenv("MARKETLAB_STORAGE_BACKEND", "restored-" + schema[-12:])
        settings = Settings()
        config = ObjectConfig.from_settings(settings)
        assert config is not None
        with managed_backend(S3Backend.configured(config, settings)) as backend:
            receipts = {}
            from dataclasses import replace
            from uuid import uuid4

            for row in backup["remote_members"]:
                original = recovery._ref(row)
                proposed = replace(
                    original,
                    alias=config.alias,
                    key=new_prefix(str(uuid4()), 0) + "/" + original.member,
                    version=None,
                )
                with exports[row["object_id"]].open("rb") as stream:
                    copied = backend.put_new(proposed, stream, multipart=lambda _: None)
                receipts[row["object_id"]] = {"key": copied.key, "version": copied.version}
            result = recovery.rebind_restore(restored, restored_root, backup, receipts, settings)
            assert result
            generation = created["upload"]["generation"]
            refs = store.get_registered(
                restored, "upload_generation", generation, root=restored_root
            )
            assert refs and refs[0].alias == config.alias
            with safe_path(restored_root, "verified-source.bin").open("xb") as stream:
                backend.read_verified(refs[0], stream)
            assert (restored_root / "verified-source.bin").read_bytes() == DATA
    finally:
        restored.dispose()
    # Keep owned restored DB/schema and versions for review and explicit cleanup.
