"""Owned S3 acceptance cases. Requires a separately authorized run and fixtures."""

import hashlib
import io
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from test_storage_store_integration import storage_engine as storage_engine  # noqa: F401
from test_v2_browser_imports_integration import DATA, manifest, request
from test_v2_browser_imports_integration import browser_engine as browser_engine  # noqa: F401
from test_v2_copilot_integration import model_engine as model_engine  # noqa: F401
from test_v2_ingestion_integration import v2_engine as v2_engine  # noqa: F401
from test_v2_research_integration import research_engine as research_engine  # noqa: F401

from marketlab.config import Settings
from marketlab.datasets.v2 import admission, catalog, service
from marketlab.datasets.v2.browser_imports import BrowserImports
from marketlab.datasets.v2.common import V2Error
from marketlab.datasets.v2.core import execute
from marketlab.storage import operator, store
from marketlab.storage.backend import (
    ObjectConfig,
    ObjectRef,
    S3Backend,
    managed_backend,
    new_prefix,
)

pytestmark = [pytest.mark.s3, pytest.mark.integration]
OWNED = "MARKETLAB_PHASE6_OWNED_S3"
VARIABLES = (
    "MARKETLAB_STORAGE_BACKEND",
    "MARKETLAB_STORAGE_S3_ALIAS",
    "MARKETLAB_STORAGE_S3_ENDPOINT",
    "MARKETLAB_STORAGE_S3_REGION",
    "MARKETLAB_STORAGE_S3_BUCKET",
    "MARKETLAB_STORAGE_S3_PREFIX",
    "MARKETLAB_STORAGE_S3_ACCESS_KEY",
    "MARKETLAB_STORAGE_S3_SECRET_KEY",
    "MARKETLAB_STORAGE_S3_SESSION_TOKEN",
)


@pytest.fixture
def credentials():
    if os.environ.get(OWNED) != "confirmed-disposable-prefix":
        pytest.skip("requires separately authorized owned S3 namespace")
    return {name: os.environ[name] for name in VARIABLES if name in os.environ}


@pytest.fixture
def s3_engine(credentials, request, monkeypatch):
    # Resolve the local test's schema fixture only after snapshotting operator settings.
    engine = request.getfixturevalue("storage_engine")
    for name, value in credentials.items():
        monkeypatch.setenv(name, value)
    settings = Settings()
    config = ObjectConfig.from_settings(settings)
    assert config is not None and settings.storage_backend == config.alias
    return engine


def test_actual_endpoint_versioning_policy_and_exact_digest(credentials):
    settings = Settings()
    config = ObjectConfig.from_settings(settings)
    assert config is not None
    with managed_backend(S3Backend.configured(config, settings)) as backend:
        backend.require_versioning()
        ref = ObjectRef(
            config.alias,
            new_prefix(str(uuid4()), 1) + "/package.json",
            None,
            len(DATA),
            hashlib.sha256(DATA).hexdigest(),
            "package.json",
            "application/json",
        )
        receipt = backend.put_new(ref, io.BytesIO(DATA), multipart=lambda _: pytest.fail())
        assert receipt.version
        output = io.BytesIO()
        backend.read_verified(receipt, output)
        assert output.getvalue() == DATA
        with pytest.raises(V2Error, match="Immutable object write conflict"):
            backend.put_new(ref, io.BytesIO(DATA), multipart=lambda _: pytest.fail())
        # The qualified policy must reject unconditional writes to its managed prefix.
        with pytest.raises(V2Error, match="request rejected"):
            backend._run(
                "put_object",
                Key=f"{config.prefix}/{ref.key}",
                Body=b"must never replace",
            )
        # Keep this owned object/version as evidence until the approved cleanup stage.
        backend.stat(receipt)


@pytest.mark.asyncio
async def test_actual_browser_ingestion_remote_local_switch_and_reversal(s3_engine, tmp_path: Path):
    root = tmp_path / "managed"
    admission.initialize(s3_engine, root)
    browser = BrowserImports(s3_engine, root)
    upload = browser.create({"manifest": manifest(DATA), "content_length": len(DATA)}, "s3-case")
    generation = upload["upload"]["generation"]
    token = upload["upload"]["required_headers"]["X-Upload-Token"]
    complete = await browser.receive(upload["id"], request(DATA, token))
    refs = store.get_registered(s3_engine, "upload_generation", generation, root=root)
    assert refs and refs[0].alias != "local" and refs[0].version
    finalized = browser.finalize(
        upload["id"],
        {"expected_revision": complete["revision"], "generation": generation},
        "s3-finalize",
    )
    result = service.work(s3_engine, root, max_jobs=1, submission_id=finalized["submission_id"])
    assert result["succeeded_jobs"] == 1
    version = browser.inspect(upload["id"])["dataset_version_id"]
    original = catalog.inspect_version(s3_engine, root, version)
    registered = store.get_registered(s3_engine, "v2_dataset", version, root=root)
    assert registered and all(ref.alias != "local" and ref.version for ref in registered)
    move = operator.copy(
        s3_engine, root, operator.plan(s3_engine, root, "v2_dataset", version), "local"
    )
    source, target = UUID(move["source_copy_id"]), UUID(move["target_copy_id"])
    operator.switch(s3_engine, root, "v2_dataset", version, source, target)
    assert catalog.inspect_version(s3_engine, root, version) == original
    operator.switch(s3_engine, root, "v2_dataset", version, target, source)
    assert catalog.inspect_version(s3_engine, root, version) == original
    with s3_engine.connect() as connection:
        assert (
            execute(
                connection,
                "SELECT count(*) FROM v2_data_charges WHERE backend_alias<>'local' "
                "AND state='retained'",
            ).scalar_one()
            == 2
        )
