"""Deferred real browser, exact transport boundary and pinned-model bindings."""

import hashlib
import importlib.util
import json
import os
import secrets
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import pytest
from s3_safe_output import MemoryCapture
from sqlalchemy import create_engine

from marketlab.config import Settings
from marketlab.datasets.v2 import admission
from marketlab.datasets.v2.core import execute
from marketlab.storage import store
from marketlab.storage.backend import ObjectConfig

pytestmark = [pytest.mark.s3, pytest.mark.integration]
ROOT = Path(__file__).resolve().parents[2]


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _hash(file):
    sha = hashlib.sha256()
    with Path(file).open("rb") as stream:
        for part in iter(lambda: stream.read(1024**2), b""):
            sha.update(part)
    return sha.hexdigest()


@pytest.fixture
def browser_plan():
    path = os.environ.get("MARKETLAB_PHASE6_BROWSER_PLAN")
    if os.environ.get("MARKETLAB_PHASE6_OWNED_S3") != "confirmed-disposable-prefix" or not path:
        pytest.skip("requires reviewed owned browser/input plan and S3-test authority")
    value = json.loads(Path(path).read_bytes())
    assert value["schema"] == "phase6-browser-inputs-v1"
    parsed = urlsplit(value["ui_url"])
    assert parsed.hostname == "127.0.0.1" and parsed.port not in {None, 8000, 11434}
    for source in value["canonical"].values():
        assert Path(source["file_path"]).stat().st_size == source["bytes"]
        assert _hash(source["file_path"]) == source["sha256"] == source["metadata"]["source_sha256"]
    settings = Settings()
    config = ObjectConfig.from_settings(settings)
    assert config is not None and settings.storage_backend == config.alias
    engine = create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
    with engine.connect() as connection:
        store.verify_namespace(admission.require(connection, settings.storage_path), config)
    try:
        yield value, engine, settings
    finally:
        from marketlab.storage.materialize import CACHE

        CACHE.close(engine)
        engine.dispose()


def _run_owned(argv, folder, *, nonce, timeout=7200):
    if os.name != "nt":
        pytest.skip("existing actual-browser lifecycle requires Windows Job containment")
    lifecycle = _load("phase6_browser_lifecycle", ROOT / "scripts/v2_phase4_lifecycle.py")
    job = lifecycle.OwnedJob()
    receipt = {"forced_cleanup": False, "samples": []}
    source = {
        str(path.relative_to(ROOT)): _hash(path)
        for path in sorted((ROOT / "src/marketlab").rglob("*.py"))
    }
    source["uv.lock"] = _hash(ROOT / "uv.lock")
    start = time.monotonic()
    output = MemoryCapture()
    try:
        env = {
            **os.environ,
            "MARKETLAB_PHASE4_RUN_NONCE": nonce,
            "MARKETLAB_PHASE6_PYTHON": sys.executable,
        }
        if Path(argv[1]).resolve() == ROOT / "scripts/v2_phase4_browser.mjs":
            # The reused boundary controller has no CLI worker to authenticate.
            # Keep all AWS material out of it and its native browser children.
            env = {
                key: value
                for key, value in env.items()
                if not key.startswith(
                    (
                        "AWS_",
                        "MARKETLAB_STORAGE_S3_",
                        "MARKETLAB_PHASE6_RESTORE_S3_",
                        "MARKETLAB_PHASE6_EXPIRED_S3_",
                    )
                )
                and key not in {"S3_BUCKET_NAME", "MARKETLAB_PHASE6_REDACTION_VALUES"}
            }
        child = job.spawn(
            argv,
            cwd=ROOT,
            env=env,
            output=output.writer,
        )
        previous = start
        while child.poll() is None:
            now = time.monotonic()
            peak = job.peak_commit()
            receipt["samples"].append({"elapsed": now - start, "peak_commit_bytes": peak})
            assert not output.overflow, "Owned in-memory output exceeded its bound"
            assert now - previous <= 1.0
            assert peak <= 8 * 1024**3 and now - start <= timeout
            previous = now
            time.sleep(0.5)
        assert child.poll() == 0
        job.wait_empty(30)
        assert all(_hash(ROOT / name) == sha for name, sha in source.items())
        receipt.update(
            {"source_files": source, "root": child.record(), "final_active": job.active()}
        )
    finally:
        try:
            try:
                if job.active():
                    receipt["forced_cleanup"] = True
                    job.terminate()
            finally:
                job.close()
        finally:
            try:
                output.finish()
            finally:
                if not output.thread.is_alive():
                    (folder / "native-log.txt").write_text(output.sanitized(), encoding="utf-8")
                receipt["output"] = {
                    "captured_bytes": len(output.buffer),
                    "limit_bytes": output.limit,
                    "overflow": output.overflow,
                    "reader_drained": not output.thread.is_alive(),
                    "raw_output_persisted": False,
                }
                (folder / "lifecycle.json").write_text(json.dumps(receipt, indent=2))
    assert not receipt["forced_cleanup"] and receipt["final_active"] == 0


@pytest.mark.parametrize("engine_name", ["chromium", "firefox", "webkit"])
@pytest.mark.parametrize("format_name", ["csv", "parquet"])
def test_actual_browser_import_to_catalog_on_object_storage(
    browser_plan, tmp_path, engine_name, format_name
):
    inputs, engine, settings = browser_plan
    node = shutil.which("node")
    assert node
    plan = {
        "schema": "phase6-browser-v1",
        "mode": "canonical",
        "engine": engine_name,
        "ui_url": inputs["ui_url"],
        "source": inputs["canonical"][format_name],
    }
    file = tmp_path / "plan.json"
    file.write_text(json.dumps(plan))
    _run_owned(
        [node, str(Path(__file__).with_name("storage_browser.mjs")), str(file)],
        tmp_path,
        nonce=secrets.token_hex(24),
    )
    receipt = json.loads((tmp_path / "receipt.json").read_bytes())
    assert receipt["state"] == "passed"
    for owner, identity in (
        ("upload_generation", receipt["generation"]),
        ("v2_dataset", receipt["dataset_version"]),
    ):
        refs = store.get_registered(engine, owner, identity, root=settings.storage_path)
        assert refs and all(ref.alias == settings.storage_backend and ref.version for ref in refs)


@pytest.mark.parametrize("engine_name", ["chromium", "firefox", "webkit"])
def test_actual_official_browser_ingestion_to_catalog(browser_plan, tmp_path, engine_name):
    inputs, engine, settings = browser_plan
    node = shutil.which("node")
    assert node
    plan = {
        "schema": "phase6-browser-v1",
        "mode": "official",
        "engine": engine_name,
        "ui_url": inputs["ui_url"],
        "official": inputs["official_by_engine"][engine_name],
    }
    file = tmp_path / "plan.json"
    file.write_text(json.dumps(plan))
    _run_owned(
        [node, str(Path(__file__).with_name("storage_browser.mjs")), str(file)],
        tmp_path,
        nonce=secrets.token_hex(24),
    )
    receipt = json.loads((tmp_path / "receipt.json").read_bytes())
    assert receipt["state"] == "passed" and receipt["versions"]
    for version in receipt["versions"]:
        refs = store.get_registered(engine, "v2_dataset", version, root=settings.storage_path)
        assert refs and all(ref.alias == settings.storage_backend and ref.version for ref in refs)


def test_exact_4gib_browser_upload_overlimit_rejection_and_retained_charge(browser_plan, tmp_path):
    inputs, engine, settings = browser_plan
    if shutil.disk_usage(tmp_path).free < 10 * 1024**3:
        pytest.skip("requires owned physical room for exact transport fixtures")
    # Reuse a hash-qualified retained transport fixture when the reviewed runner
    # supplies it; otherwise preserve the original Phase 4 generator path.
    boundary = inputs.get("boundary_fixture")
    if boundary is None:
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            helper = _load("phase6_transport_boundary", ROOT / "scripts/v2_phase4_acceptance.py")
            boundary = helper.make_boundary(tmp_path, inputs["canonical"]["csv"])
        finally:
            sys.path.remove(str(ROOT / "scripts"))
    else:
        assert boundary["bytes"] == 4 * 1024**3
        assert Path(boundary["file_path"]).stat().st_size == boundary["bytes"]
        assert _hash(boundary["file_path"]) == boundary["sha256"]
        assert Path(boundary["over_file_path"]).stat().st_size == 4 * 1024**3 + 1
        assert _hash(boundary["over_file_path"]) == boundary["over_sha256"]
    plan = {
        "owner": "phase6-storage",
        "mode": "boundary",
        "engines": ["chromium"],
        "ui_url": inputs["ui_url"],
        "boundary": boundary,
    }
    file, config = tmp_path / "plan.json", tmp_path / "unused-worker-config.json"
    file.write_text(json.dumps(plan))
    config.write_text("{}")
    node = shutil.which("node")
    assert node
    _run_owned(
        [
            node,
            str(ROOT / "scripts/v2_phase4_browser.mjs"),
            "browser",
            str(file),
            str(tmp_path),
            str(config),
        ],
        tmp_path,
        nonce=secrets.token_hex(24),
    )
    result = json.loads((tmp_path / "boundary.json").read_bytes())
    assert result["after"]["received_bytes"] == 4 * 1024**3
    assert result["after"]["source_sha256"] == boundary["sha256"]
    refs = store.get_registered(
        engine, "upload_generation", result["uploaded"]["generation"], root=settings.storage_path
    )
    assert refs and refs[0].length == 4 * 1024**3 and refs[0].sha256 == boundary["sha256"]
    assert refs[0].version and refs[0].alias == settings.storage_backend
    with engine.connect() as connection:
        charged = execute(
            connection,
            "SELECT d.charged_bytes,d.state FROM v2_storage_objects o "
            "JOIN v2_data_charges d USING(charge_id) "
            "WHERE o.object_key=:key AND o.version_id=:version",
            key=refs[0].key,
            version=refs[0].version,
        ).one()
    assert charged == (4 * 1024**3, "retained")


def test_one_actual_pinned_model_copilot_research_memo_storage_smoke(browser_plan, tmp_path):
    inputs, engine, settings = browser_plan
    case = inputs["model_smoke"]
    node = shutil.which("node")
    assert node and case["model_digest"] == settings.copilot_model_digest
    model = urlsplit(settings.ollama_url)
    assert model.hostname == "127.0.0.1" and model.port not in {None, 11434}
    plan = {
        **case,
        "schema": "phase6-browser-v1",
        "mode": "model",
        "engine": "chromium",
        "ui_url": inputs["ui_url"],
    }
    readback = os.environ.get("MARKETLAB_PHASE6_MODEL_READBACK")
    if readback:
        identities = json.loads(readback)
        assert set(identities) == {"request_id", "run_id"}
        assert all(str(UUID(value)) == value for value in identities.values())
        plan.update(mode="model_readback", readback=identities)
    file = tmp_path / "plan.json"
    file.write_text(json.dumps(plan))
    _run_owned(
        [node, str(Path(__file__).with_name("storage_browser.mjs")), str(file)],
        tmp_path,
        nonce=secrets.token_hex(24),
    )
    receipt = json.loads((tmp_path / "receipt.json").read_bytes())
    assert receipt["state"] == "passed"
    for owner in ("v2_research", "v2_memo"):
        refs = store.get_registered(engine, owner, receipt["run_id"], root=settings.storage_path)
        assert refs and all(ref.alias == settings.storage_backend and ref.version for ref in refs)
