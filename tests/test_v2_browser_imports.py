"""Process identity, transport drain and stable file binding regressions."""

import asyncio
import os
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI

from marketlab.datasets.v2 import native_identity
from marketlab.datasets.v2.admission import _files
from marketlab.datasets.v2.browser_imports import _io, _revision, _signature
from marketlab.datasets.v2.common import V2Error, digest
from marketlab.datasets.v2.routes import router


def test_native_self_is_exact_live_owner():
    identity = native_identity.current()
    assert native_identity.valid(identity)
    assert native_identity.same(identity)
    assert not native_identity.dead(identity)


@pytest.mark.parametrize(
    "field,value",
    [
        ("pid", 2**32 + 1),
        ("pid", True),
        ("pid", -1),
        ("birth", "bad"),
        ("birth", "0"),
        ("birth", str(2**64)),
        ("boot", "bad"),
        ("host", "bad"),
        ("executable", "relative"),
        ("platform", "unknown"),
    ],
)
def test_malformed_native_identity_never_proves_death(field, value):
    identity = dict(native_identity.current(), **{field: value})
    assert not native_identity.valid(identity)
    assert not native_identity.dead(identity)


def test_signature_ignores_access_time(tmp_path):
    path = tmp_path / "source"
    path.write_bytes(b"hash this")
    before = _signature(path)
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns + 1000000000, stat.st_mtime_ns))
    assert _signature(path) == before
    path.write_bytes(b"changed")
    assert _signature(path) != before


@pytest.mark.asyncio
async def test_cancelled_executor_io_drains_before_propagating():
    started, released, stopped = threading.Event(), threading.Event(), threading.Event()

    def write():
        started.set()
        released.wait(10)
        stopped.set()

    task = asyncio.create_task(_io(write))
    assert await asyncio.to_thread(started.wait, 3)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done() and not stopped.is_set()
    released.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"expected_revision": True},
        {"expected_revision": -1},
        {"expected_revision": 1, "extra": 0},
    ],
)
def test_revision_rejects_coercions_unknown_fields(body):
    with pytest.raises(V2Error):
        _revision(body)


def test_inventory_root_symlink_rejected(tmp_path):
    # Native Windows symlinks require privileges; a real junction is exercised
    # separately by the owned native acceptance campaign where available.
    if os.name == "nt":
        pytest.skip("POSIX symlink case; native Windows junction acceptance is separate")
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(V2Error):
        list(_files(link))


def test_inventory_does_not_silently_omit_traversal_error(tmp_path, monkeypatch):
    def denied(*args, **kwargs):
        kwargs["onerror"](PermissionError("controlled denial"))
        yield from ()

    monkeypatch.setattr(os, "walk", denied)
    with pytest.raises(V2Error):
        list(_files(Path(tmp_path)))


@pytest.mark.asyncio
async def test_capabilities_strict_hash_and_effective_limits():
    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        response = await client.get("/v2/capabilities")
        value = response.json()
        sha = value.pop("sha256")
        assert response.status_code == 200 and sha == digest(value)
        assert value["limits"]["canonical_bytes"] == 4 * 1024**3
        assert value["auth_mode"] == "local" and value["memo_available"]
        assert value["copilot_available"]
        assert value["limits"]["model_input_bytes"] == 6000
        invalid = await client.get("/v2/capabilities?unknown=yes")
        assert invalid.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data,media,status",
    [
        (b"{}", "text/plain", 415),
        (b'{"x":1,"x":2}', "application/json", 422),
        (b" " * 65537, "application/json", 413),
    ],
    ids=["unsupported-media", "duplicate-json", "oversized-control"],
)
async def test_import_control_fails_before_service(data, media, status):
    app = FastAPI()
    app.include_router(router)
    fake = SimpleNamespace(create=Mock())
    app.state.v2_import_service = fake
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        response = await client.post("/v2/imports", content=data, headers={"Content-Type": media})
    assert response.status_code == status
    assert response.json()["error"]["request_id"]
    fake.create.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers", [{"Origin": "https://foreign.example"}, {"Sec-Fetch-Site": "cross-site"}]
)
async def test_foreign_origin_put_never_claims_or_reads_upload(headers):
    app = FastAPI()
    app.include_router(router)
    fake = SimpleNamespace(receive=AsyncMock())
    app.state.v2_import_service = fake
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        response = await client.put(
            "/v2/imports/00000000-0000-0000-0000-000000000001/content",
            content=b"untrusted",
            headers=headers,
        )
    assert response.status_code == 403
    fake.receive.assert_not_called()


@pytest.mark.asyncio
async def test_import_mutation_rejects_query_before_service():
    app = FastAPI()
    app.include_router(router)
    fake = SimpleNamespace(create=Mock())
    app.state.v2_import_service = fake
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        response = await client.post("/v2/imports?unexpected=yes", json={})
    assert response.status_code == 422
    fake.create.assert_not_called()
