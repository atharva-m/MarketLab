"""Deferred actual-S3 fault gates. Never run without separate S3 authorization."""

import io
import json
import os
import selectors
import socket
import socketserver
import subprocess
import threading
import time
from dataclasses import replace
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError
from owned_https_proxy import Namespace, OwnedHTTPSProxy
from s3_safe_output import BoundedChild, redact_text, run_python
from test_datasets import START, archive_files
from test_storage_live import VARIABLES
from test_storage_live import credentials as credentials  # noqa: F401
from test_storage_live import s3_engine as s3_engine  # noqa: F401
from test_storage_store_integration import storage_engine as storage_engine  # noqa: F401
from test_v2_browser_imports_integration import DATA, manifest, request
from test_v2_browser_imports_integration import browser_engine as browser_engine  # noqa: F401
from test_v2_copilot_integration import model_engine as model_engine  # noqa: F401
from test_v2_ingestion_integration import v2_engine as v2_engine  # noqa: F401
from test_v2_research_integration import research_engine as research_engine  # noqa: F401

from marketlab.config import Settings
from marketlab.datasets.publication import ingest_archive, inspect_version
from marketlab.datasets.v2 import admission, catalog, service
from marketlab.datasets.v2.browser_imports import BrowserImports
from marketlab.datasets.v2.common import V2Error
from marketlab.datasets.v2.core import execute, one
from marketlab.storage import store
from marketlab.storage.backend import ObjectConfig, S3Backend, StorageUnavailable, managed_backend
from marketlab.storage.materialize import CACHE, FileCache, Scratch

pytestmark = [pytest.mark.s3, pytest.mark.integration]

_PUBLISH_CHILD = """
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine
from marketlab.config import Settings
from marketlab.datasets.publication import ingest_archive
from marketlab.storage.backend import S3Backend
from marketlab.storage.store import WriteGroup

schema, root, archive, checksum, fault = sys.argv[1:]
engine = create_engine(
    Settings().sqlalchemy_url, connect_args={"options": f"-c search_path={schema}"}
)
original_set_writing = WriteGroup._set_writing
original_write_paths = WriteGroup.write_paths
original_run = S3Backend._run

def set_writing(self, intent):
    if fault == "before_upload":
        os._exit(77)
    return original_set_writing(self, intent)

def write_paths(self, files, cancelled=None):
    verified = original_write_paths(self, files, cancelled)
    if fault == "after_verified_objects":
        os._exit(77)
    return verified

def run(self, method, **params):
    result = original_run(self, method, **params)
    if fault == "during_upload" and method == "put_object":
        os._exit(77)
    return result

def checkpoint(phase):
    if phase == fault:
        os._exit(77)

WriteGroup._set_writing = set_writing
WriteGroup.write_paths = write_paths
S3Backend._run = run
ingest_archive(engine, Path(root), Path(archive), Path(checksum), checkpoint=checkpoint)
raise SystemExit("fault boundary was not reached")
"""

_UPLOAD_CHILD = """
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from sqlalchemy import create_engine
from starlette.requests import Request
from marketlab.config import Settings
from marketlab.datasets.v2.browser_imports import BrowserImports
from marketlab.datasets.v2.common import V2Error
from marketlab.storage.backend import S3Backend

schema, root, source, description, receipt, fault, release = sys.argv[1:]
engine = create_engine(
    Settings().sqlalchemy_url, connect_args={"options": f"-c search_path={schema}"}
)
browser = BrowserImports(engine, Path(root))
data = Path(source).read_bytes()
created = browser.create(
    {"manifest": json.loads(Path(description).read_text()), "content_length": len(data)},
    "fault-upload",
)
Path(receipt).write_text(json.dumps({
    "id": created["id"], "generation": created["upload"]["generation"]
}))
original_run = S3Backend._run
original_uploaded = BrowserImports._uploaded

def run(self, method, **params):
    result = original_run(self, method, **params)
    if method == fault:
        os._exit(78)
    return result

def uploaded(self, generation, group=None):
    if fault in {"cancel_after_verified", "expire_after_verified"}:
        Path(receipt + ".ready").write_text("verified")
        deadline = time.monotonic() + 100
        while not Path(release).exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("bounded parent cancellation gate timed out")
            time.sleep(.02)
    return original_uploaded(self, generation, group)

S3Backend._run = run
BrowserImports._uploaded = uploaded
if fault == "expire_after_verified":
    # Simulate an owner that cannot renew, while retaining the exact lease.
    BrowserImports._heartbeat = lambda self, generation, done, lost: done.wait(110)
sent = False
async def receive():
    global sent
    if sent:
        raise RuntimeError("duplicate receive")
    sent = True
    return {"type": "http.request", "body": data, "more_body": False}
request = Request({
    "type": "http", "method": "PUT", "path": "/",
    "headers": [
        (b"content-length", str(len(data)).encode()),
        (b"content-type", b"application/octet-stream"),
        (b"x-upload-token", created["upload"]["required_headers"]["X-Upload-Token"].encode()),
    ],
}, receive)
try:
    asyncio.run(browser.receive(created["id"], request))
except V2Error as error:
    if fault in {"cancel_after_verified", "expire_after_verified"} and error.code in {
        "ownership_lost", "revision_conflict"
    }:
        raise SystemExit(79)
    raise
raise SystemExit("fault boundary was not reached")
"""


def _schema(engine):
    with engine.connect() as connection:
        return execute(connection, "SELECT current_schema()").scalar_one()


def _pending_charge(engine):
    with engine.connect() as connection:
        return one(
            connection,
            "SELECT c.*,o.state AS object_state,o.version_id,o.multipart_id,o.copy_id "
            "FROM v2_data_charges c JOIN v2_storage_objects o USING(charge_id) "
            "WHERE c.backend_alias<>'local' ORDER BY o.member LIMIT 1",
        )


def _retain_child_output(folder, child):
    (folder / "child-stdout.txt").write_text(redact_text(child.stdout or ""), encoding="utf-8")
    (folder / "child-stderr.txt").write_text(redact_text(child.stderr or ""), encoding="utf-8")


@pytest.mark.parametrize(
    "boundary",
    [
        "before_upload",
        "during_upload",
        "after_verified_objects",
        "before_catalog_commit",
        "after_catalog_commit",
    ],
)
def test_actual_publication_process_death_retains_objects_and_fences(s3_engine, tmp_path, boundary):
    root = tmp_path / "managed"
    admission.initialize(s3_engine, root)
    archive, checksum = archive_files(tmp_path / "source", [f"1,100,1,100,{START},True,False"])
    crashed = run_python(
        [
            "-c",
            _PUBLISH_CHILD,
            _schema(s3_engine),
            str(root),
            str(archive),
            str(checksum),
            boundary,
        ],
        timeout=90,
    )
    _retain_child_output(tmp_path, crashed)
    assert crashed.returncode == 77, "owned child did not reach the exact fault checkpoint"
    charge = _pending_charge(s3_engine)
    assert charge is not None
    with s3_engine.connect() as connection:
        job = one(connection, "SELECT * FROM ingestion_jobs")
        registered = execute(connection, "SELECT count(*) FROM dataset_versions").scalar_one()
        object_count = execute(connection, "SELECT count(*) FROM v2_storage_objects").scalar_one()
    assert job is not None and object_count == 2
    if boundary == "after_catalog_commit":
        assert registered == 1 and job["state"] == "succeeded"
        result = inspect_version(s3_engine, root, job["result_version"])
        replay = ingest_archive(
            s3_engine, root, archive, checksum, resume_job_id=str(job["job_id"])
        )
        assert result == replay and charge["state"] == "retained"
        with s3_engine.connect() as connection:
            assert execute(connection, "SELECT count(*) FROM v2_storage_objects").scalar_one() == 2
    else:
        assert registered == 0 and job["state"] != "succeeded"
        assert charge["charged_bytes"] == charge["ceiling_bytes"] > 0
        assert charge["copy_id"] is None
        if boundary == "before_upload":
            assert charge["object_state"] == "planned"
        elif boundary in {"after_verified_objects", "before_catalog_commit"}:
            assert charge["object_state"] == "verified" and charge["version_id"]


@pytest.mark.parametrize(
    "boundary", ["create_multipart_upload", "upload_part", "complete_multipart_upload"]
)
def test_actual_ambiguous_multipart_process_death_keeps_full_reservation(
    s3_engine, tmp_path, boundary
):
    root = tmp_path / "managed"
    admission.initialize(s3_engine, root)
    data = b"x" * (16 * 1024**2 + 1)
    source, description, receipt = (
        tmp_path / "input.csv",
        tmp_path / "manifest.json",
        tmp_path / "receipt.json",
    )
    source.write_bytes(data)
    description.write_text(json.dumps(manifest(data)), encoding="utf-8")
    crashed = run_python(
        [
            "-c",
            _UPLOAD_CHILD,
            _schema(s3_engine),
            str(root),
            str(source),
            str(description),
            str(receipt),
            boundary,
            str(tmp_path / "release"),
        ],
        timeout=90,
    )
    _retain_child_output(tmp_path, crashed)
    assert crashed.returncode == 78, "owned child did not reach the provider outcome boundary"
    identity = json.loads(receipt.read_text())
    charge = _pending_charge(s3_engine)
    assert charge and charge["charged_bytes"] == charge["ceiling_bytes"] == len(data)
    assert charge["copy_id"] is None and charge["version_id"] is None
    assert charge["object_state"] == "writing"
    assert (charge["multipart_id"] is None) == (boundary == "create_multipart_upload")
    with pytest.raises(V2Error, match="registration missing"):
        store.get_registered(s3_engine, "upload_generation", identity["generation"], root=root)
    with s3_engine.connect() as connection:
        assert execute(connection, "SELECT count(*) FROM v2_storage_objects").scalar_one() == 1
        assert execute(connection, "SELECT count(*) FROM v2_storage_copies").scalar_one() == 0
    if boundary == "upload_part":
        # Observe the real unchanged 60-second lease, then use normal renewal.
        browser = BrowserImports(s3_engine, root)
        deadline = time.monotonic() + 75
        while browser.inspect(identity["id"])["state"] == "uploading":
            assert time.monotonic() < deadline, "existing upload lease did not expire"
            browser.recover(identity["id"])
            time.sleep(0.1)
        current = browser.inspect(identity["id"])
        renewed = browser.renew(
            identity["id"], {"expected_revision": current["revision"]}, "renew-after-crash"
        )
        assert renewed["upload"]["generation"] != identity["generation"]
        with s3_engine.connect() as connection:
            total = execute(
                connection,
                "SELECT sum(charged_bytes) FROM v2_data_charges "
                "WHERE state IN ('reserved','retained')",
            ).scalar_one()
        assert total == 2 * len(data)


@pytest.mark.parametrize("boundary", ["cancel_after_verified", "expire_after_verified"])
def test_actual_cancel_or_stale_generation_cannot_publish_verified_objects(
    s3_engine, tmp_path, boundary
):
    root = tmp_path / "managed"
    admission.initialize(s3_engine, root)
    source, description, receipt, release = (
        tmp_path / "input.csv",
        tmp_path / "manifest.json",
        tmp_path / "receipt.json",
        tmp_path / "release",
    )
    source.write_bytes(DATA)
    description.write_text(json.dumps(manifest(DATA)), encoding="utf-8")
    child = BoundedChild(
        [
            "-c",
            _UPLOAD_CHILD,
            _schema(s3_engine),
            str(root),
            str(source),
            str(description),
            str(receipt),
            boundary,
            str(release),
        ],
    )
    try:
        deadline = time.monotonic() + 60
        while not receipt.with_name(receipt.name + ".ready").exists():
            assert child.poll() is None, "owned child ended before verified-object gate"
            assert time.monotonic() < deadline, "verified-object gate timed out"
            time.sleep(0.02)
        identity = json.loads(receipt.read_text())
        browser = BrowserImports(s3_engine, root)
        current = browser.inspect(identity["id"])
        if boundary == "cancel_after_verified":
            browser.cancel(
                identity["id"], {"expected_revision": current["revision"]}, "cancel-fault"
            )
        else:
            deadline = time.monotonic() + 75
            while browser.inspect(identity["id"])["state"] == "uploading":
                assert time.monotonic() < deadline, "unchanged upload lease did not expire"
                browser.recover(identity["id"])
                time.sleep(0.1)
            current = browser.inspect(identity["id"])
            renewed = browser.renew(
                identity["id"], {"expected_revision": current["revision"]}, "stale-renew"
            )
            assert renewed["upload"]["generation"] != identity["generation"]
        release.write_text("continue")
        stdout, stderr = child.communicate(timeout=30)
        _retain_child_output(
            tmp_path, subprocess.CompletedProcess(child.args, child.returncode, stdout, stderr)
        )
        assert child.returncode == 79
        charge = _pending_charge(s3_engine)
        assert charge and charge["copy_id"] is None and charge["object_state"] == "verified"
        # Registration lost its fence: retain the complete original reservation.
        # Only atomic copy attachment changes a verified group's charge to retained.
        assert charge["charged_bytes"] == charge["ceiling_bytes"] == len(DATA)
        assert charge["state"] == "reserved"
        assert charge["version_id"]
        with s3_engine.connect() as connection:
            assert execute(
                connection,
                "SELECT coalesce(sum(charged_bytes),0) FROM v2_data_charges "
                "WHERE charge_id=:id AND state IN ('reserved','retained')",
                id=charge["charge_id"],
            ).scalar_one() == len(DATA)
        with pytest.raises(V2Error, match="registration missing"):
            store.get_registered(s3_engine, "upload_generation", identity["generation"], root=root)
    finally:
        try:
            release.write_text("drain")
            if child.poll() is None:
                try:
                    child.communicate(timeout=30)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.communicate(timeout=10)
                    pytest.fail("owned child required forced termination after its bounded release")
        finally:
            child.close()


async def _published_dataset(engine, root):
    admission.initialize(engine, root)
    browser = BrowserImports(engine, root)
    created = browser.create({"manifest": manifest(DATA), "content_length": len(DATA)}, "input")
    uploaded = await browser.receive(
        created["id"], request(DATA, created["upload"]["required_headers"]["X-Upload-Token"])
    )
    result = browser.finalize(
        created["id"],
        {"expected_revision": uploaded["revision"], "generation": created["upload"]["generation"]},
        "final",
    )
    assert (
        service.work(engine, root, max_jobs=1, submission_id=result["submission_id"])[
            "succeeded_jobs"
        ]
        == 1
    )
    version = browser.inspect(created["id"])["dataset_version_id"]
    return version, catalog.inspect_version(engine, root, version)


@pytest.mark.asyncio
async def test_actual_registered_generation_and_poisoned_or_pinned_cache(s3_engine, tmp_path):
    root = tmp_path / "managed"
    version, original = await _published_dataset(s3_engine, root)
    refs = store.get_registered(s3_engine, "v2_dataset", version, root=root)
    assert refs
    manifest_ref = next(ref for ref in refs if ref.member == "manifest.json")
    with CACHE.pin(s3_engine, root, manifest_ref, Scratch()) as path:
        path.write_bytes(b"poisoned")
    assert catalog.inspect_version(s3_engine, root, version) == original
    config = ObjectConfig.from_settings(Settings())
    assert config is not None
    with managed_backend(S3Backend.configured(config, Settings())) as backend:
        # A missing pinned generation cannot resolve to this key's current bytes.
        different = next(ref for ref in refs if ref.member != "manifest.json")
        with pytest.raises(V2Error):
            backend.read_verified(
                replace(manifest_ref, version="phase6-missing-" + uuid4().hex), io.BytesIO()
            )
        with pytest.raises(V2Error, match="content mismatch"):
            backend.read_verified(replace(manifest_ref, sha256="0" * 64), io.BytesIO())
        cache = FileCache(limit=manifest_ref.length)
        try:
            with cache.pin(s3_engine, root, manifest_ref, Scratch()):
                with (
                    pytest.raises(V2Error, match="scratch limit"),
                    cache.pin(s3_engine, root, different, Scratch(used=20 * 1024**3)),
                ):
                    pytest.fail("pinned cache pressure exceeded scratch allowance")
        finally:
            cache.close()


@pytest.mark.asyncio
async def test_actual_expired_credentials_fail_closed_before_warm_cache(
    s3_engine, tmp_path, monkeypatch
):
    if os.environ.get("MARKETLAB_PHASE6_EXPIRED_S3") != "confirmed-expired-same-prefix-credentials":
        pytest.skip("requires separately supplied expired owned-prefix credentials")
    root = tmp_path / "managed"
    version, _ = await _published_dataset(s3_engine, root)
    refs = store.get_registered(s3_engine, "v2_dataset", version, root=root)
    assert refs
    for suffix in ("ACCESS_KEY", "SECRET_KEY", "SESSION_TOKEN"):
        expired = os.environ.get("MARKETLAB_PHASE6_EXPIRED_S3_" + suffix)
        assert expired, "all expired credential fields must be supplied"
        monkeypatch.setenv("MARKETLAB_STORAGE_S3_" + suffix, expired)
    config = ObjectConfig.from_settings(Settings())
    assert config is not None
    with managed_backend(S3Backend.configured(config, Settings())) as backend:
        with pytest.raises(ClientError) as receipt:
            response = backend._client.get_object(
                Bucket=config.bucket,
                Key=backend._key(refs[0]),
                VersionId=refs[0].version,
                Range="bytes=0-0",
            )
            # If credentials unexpectedly work, close the bounded response before
            # pytest reports the missing rejection. Never weaken the HEAD guard.
            if response.get("Body") is not None:
                response["Body"].close()
        assert receipt.value.response["Error"]["Code"] in {"ExpiredToken", "ExpiredTokenException"}
        with pytest.raises(V2Error) as denied:
            catalog.inspect_version(s3_engine, root, version)
        assert denied.value.code == "storage_denied"
        assert not getattr(denied.value, "transient", False)


@pytest.mark.asyncio
async def test_actual_remote_bytes_share_exact_logical_capacity_with_local_reservations(
    s3_engine, tmp_path
):
    root = tmp_path / "managed"
    admission.initialize(s3_engine, root)
    existing = admission.acquire(
        s3_engine, root, "legacy", admission.DATA_LIMIT - len(DATA), physical_bytes=0
    )
    assert existing is not None
    browser = BrowserImports(s3_engine, root)
    try:
        created = browser.create(
            {"manifest": manifest(DATA), "content_length": len(DATA)}, "exact-ceiling"
        )
        await browser.receive(
            created["id"], request(DATA, created["upload"]["required_headers"]["X-Upload-Token"])
        )
        refs = store.get_registered(
            s3_engine, "upload_generation", created["upload"]["generation"], root=root
        )
        assert refs and refs[0].alias != "local" and refs[0].version
        with pytest.raises(V2Error) as full:
            browser.create(
                {"manifest": manifest(DATA), "content_length": len(DATA)}, "beyond-ceiling"
            )
        assert full.value.code == "capacity_exceeded"
        with s3_engine.connect() as connection:
            assert (
                execute(
                    connection,
                    "SELECT sum(charged_bytes) FROM v2_data_charges "
                    "WHERE state IN ('reserved','retained')",
                ).scalar_one()
                == admission.DATA_LIMIT
            )
    finally:
        # Preserve the deliberately unresolved logical reservation and objects.
        admission.finish(s3_engine, existing)


@pytest.fixture
def outage_engine(credentials, request, monkeypatch):
    endpoint = urlsplit(credentials.get("MARKETLAB_STORAGE_S3_ENDPOINT", ""))
    if endpoint.scheme == "https":
        namespace = Namespace(
            credentials.get("MARKETLAB_STORAGE_S3_ENDPOINT", ""),
            credentials.get("MARKETLAB_STORAGE_S3_REGION", ""),
            credentials.get("MARKETLAB_STORAGE_S3_BUCKET", ""),
            credentials.get("MARKETLAB_STORAGE_S3_PREFIX", ""),
        )
        with OwnedHTTPSProxy(namespace) as proxy:
            runner = threading.Thread(target=proxy.serve_forever, kwargs={"poll_interval": 0.05})
            runner.start()
            try:
                engine = request.getfixturevalue("storage_engine")
                for name in VARIABLES:
                    if name in credentials:
                        monkeypatch.setenv(name, credentials[name])
                local = f"http://127.0.0.1:{proxy.server_address[1]}"
                monkeypatch.setenv("MARKETLAB_STORAGE_S3_ENDPOINT", local)
                configured = S3Backend.configured

                def proxied(cls, config, settings):
                    if config.endpoint != local:
                        raise AssertionError("Unexpected acceptance backend endpoint")
                    backend = configured(config, settings)
                    backend._client.meta.events.register_first("before-sign.s3", proxy.sign)
                    return backend

                monkeypatch.setattr(S3Backend, "configured", classmethod(proxied))
                yield engine, proxy.drop
            finally:
                proxy.drop.set()
                proxy.shutdown()
                runner.join(timeout=5)
                assert not runner.is_alive(), "owned forwarding listener did not drain"
        assert proxy.workers == 0 and not proxy.active, "owned forwarding workers did not drain"
        assert proxy.completed > 0, "owned forwarding completed no upstream request"
        return
    if endpoint.scheme != "http" or endpoint.hostname not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("owned outage forwarding requires a qualified acceptance endpoint")
    destination = (endpoint.hostname, endpoint.port or 80)
    drop = threading.Event()

    class Forward(socketserver.BaseRequestHandler):
        def handle(self):
            if drop.is_set():
                return
            with socket.create_connection(destination, timeout=5) as upstream:
                self.request.settimeout(5)
                with selectors.DefaultSelector() as readiness:
                    readiness.register(self.request, selectors.EVENT_READ, upstream)
                    readiness.register(upstream, selectors.EVENT_READ, self.request)
                    while not drop.is_set():
                        for key, _ in readiness.select(timeout=0.1):
                            data = key.fileobj.recv(64 * 1024)
                            if not data:
                                return
                            key.data.sendall(data)

    class OwnedProxy(socketserver.ThreadingTCPServer):
        daemon_threads = False
        block_on_close = True

    with OwnedProxy(("127.0.0.1", 0), Forward) as proxy:
        runner = threading.Thread(target=proxy.serve_forever, kwargs={"poll_interval": 0.05})
        runner.start()
        try:
            engine = request.getfixturevalue("storage_engine")
            for name in VARIABLES:
                if name in credentials:
                    monkeypatch.setenv(name, credentials[name])
            monkeypatch.setenv(
                "MARKETLAB_STORAGE_S3_ENDPOINT", f"http://127.0.0.1:{proxy.server_address[1]}"
            )
            yield engine, drop
        finally:
            drop.set()
            proxy.shutdown()
            runner.join(timeout=5)
            assert not runner.is_alive(), "owned forwarding listener did not drain"


@pytest.mark.asyncio
async def test_actual_owned_network_outage_cannot_hide_behind_warm_cache(outage_engine, tmp_path):
    engine, drop = outage_engine
    root = tmp_path / "managed"
    version, original = await _published_dataset(engine, root)
    drop.set()
    started = time.monotonic()
    with pytest.raises(StorageUnavailable):
        catalog.inspect_version(engine, root, version)
    assert time.monotonic() - started < 40
    drop.clear()
    assert catalog.inspect_version(engine, root, version) == original
