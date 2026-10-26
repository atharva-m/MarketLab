"""Workspace boundaries, replay, keyset discovery and shared expensive admission."""

import asyncio
import threading
from datetime import UTC, date, datetime
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
import sqlalchemy as sa
from test_copilot import request as copilot_body
from test_copilot_integration import copilot_engine as copilot_engine
from test_research import body as research_body
from test_research_integration import research_engine as research_engine

from marketlab.analytics.bars import BarService
from marketlab.app import create_app
from marketlab.copilot import store as copilot_store
from marketlab.datasets import jobs
from marketlab.datasets.publication import dataset_versions
from marketlab.research import store as research_store
from marketlab.workspace import Page, WorkspaceService, collection, verified_detail


def app():
    application = create_app()
    application.state.trade_engine = Mock()
    return application


@pytest.mark.parametrize(
    "path",
    [
        "/v1/datasets?limit=0",
        "/v1/datasets?limit=101",
        "/v1/datasets?limit=true",
        "/v1/datasets?limit=01",
        "/v1/datasets?symbol=btcUSDT",
        "/v1/datasets?sql=x",
        "/v1/datasets?limit=1&limit=2",
        "/v1/datasets?cursor=..",
        "/v1/datasets?cursor=" + "a" * 2049,
        "/v1/datasets?start_date=2025-01-02&before_date=2025-01-02",
        "/v1/datasets?start_date=2024-12-31",
        "/v1/datasets?before_date=2025-02-02",
        "/v1/research/runs?state=ready",
        "/v1/copilot/requests?state=succeeded",
        "/v1/ingestion/submissions?symbol=SOLUSDT",
        "/v1/datasets/" + "A" * 64,
        "/v1/ingestion/submissions/not-an-id",
    ],
)
async def test_invalid_discovery_precedes_database(path):
    application = app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://127.0.0.1"
    ) as client:
        assert (await client.get(path)).status_code == 422
    application.state.trade_engine.assert_not_called()
    application.state.trade_engine.begin.assert_not_called()


def request(path):
    from urllib.parse import urlsplit

    from starlette.requests import Request

    parsed = urlsplit(path)
    return Request({"type": "http", "query_string": parsed.query.encode(), "headers": []})


def test_cursor_filter_binding_shape_and_identity():
    page = Page.create(request("/?symbol=BTCUSDT"), "datasets")
    stamp = datetime(2026, 1, 1, tzinfo=UTC)
    token = page.cursor(stamp, "a" * 64)
    parsed = Page.create(request("/?symbol=BTCUSDT&limit=100&cursor=" + token), "datasets")
    assert parsed.after == (stamp, "a" * 64)
    from fastapi import HTTPException

    for url, name in [
        ("/?symbol=ETHUSDT&cursor=" + token, "datasets"),
        ("/?cursor=" + token, "research"),
    ]:
        with pytest.raises(HTTPException):
            Page.create(request(url), name)


@pytest.mark.parametrize(
    "host,origin",
    [
        ("evil.example", None),
        ("localhost.evil", "http://localhost.evil"),
        ("127.0.0.1:8000", "https://evil.example"),
        ("127.0.0.1:8000", "null"),
        ("127.0.0.1:8000", "http://127.0.0.1:9999"),
        ("127.0.0.1:8000", "http://127.0.0.1:8000/path"),
    ],
)
async def test_ingestion_origin_rejected_before_database(host, origin):
    application = app()
    headers = {"Host": host, "Idempotency-Key": "x"}
    if origin is not None:
        headers["Origin"] = origin
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://127.0.0.1"
    ) as client:
        assert (
            await client.post("/v1/ingestion/submissions", headers=headers, json={})
        ).status_code == 403
    application.state.trade_engine.begin.assert_not_called()


INGEST = {
    "schema": "ingestion-submission-v1",
    "symbols": ["BTCUSDT"],
    "start_date": "2025-01-01",
    "before_date": "2025-01-02",
}


@pytest.mark.parametrize(
    "change",
    [
        {"source_mode": "fixture"},
        {"symbols": [True]},
        {"symbols": ["BTCUSDT", "BTCUSDT"]},
        {"start_date": "2024-12-31"},
        {"before_date": "2025-02-02"},
        {"schema": "bad"},
    ],
)
async def test_ingestion_strict_body_before_database(change):
    application = app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://127.0.0.1"
    ) as client:
        result = await client.post(
            "/v1/ingestion/submissions", headers={"Idempotency-Key": "x"}, json=INGEST | change
        )
        assert result.status_code == 422
    application.state.trade_engine.begin.assert_not_called()


async def test_ingestion_stream_content_type_duplicate_key_limits():
    application = app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://127.0.0.1"
    ) as client:
        for raw, kind in [
            (b"{}", "text/plain"),
            (b'{"x":1,"x":2}', "application/json"),
            (b" " * 65537, "application/json"),
        ]:
            result = await client.post(
                "/v1/ingestion/submissions",
                headers={"Idempotency-Key": "x", "Content-Type": kind},
                content=raw,
            )
            assert result.status_code == 422
    application.state.trade_engine.begin.assert_not_called()


async def test_verification_shares_compute_and_drains_real_thread(monkeypatch, tmp_path):
    service = BarService(Mock(), tmp_path, admission_timeout=0.03)
    entered, release = threading.Event(), threading.Event()

    def inspect(*_):
        entered.set()
        assert release.wait(5)
        return {"verified": True}

    monkeypatch.setattr("marketlab.workspace.inspect_version", inspect)
    assert service.reader.compute.try_acquire("verification")
    task = asyncio.create_task(verified_detail(service, "a" * 64))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        assert service.reader.compute.snapshot()["active"] == 2
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as unavailable:
            await verified_detail(service, "b" * 64)
        assert unavailable.value.status_code == 503
        task.cancel()
        await asyncio.sleep(0.02)
        assert not task.done()
        assert service.reader.compute.snapshot()["active"] == 2
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert service.reader.compute.snapshot()["active"] == 1
        assert service.capacity._value == 2
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        service.reader.compute.release("verification")
        await service.close()


async def test_catalog_connect_failure_is_unavailable(monkeypatch, tmp_path):
    application = app()
    db = Mock()
    db.connect.side_effect = sa.exc.OperationalError("redacted", {}, Exception("private"))
    bars = BarService(db, tmp_path)
    application.state.workspace_service = WorkspaceService(bars)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://127.0.0.1"
        ) as client:
            response = await client.get("/v1/datasets/" + "a" * 64)
            assert response.status_code == 503
            assert response.json() == {"detail": "Workspace catalog unavailable"}
            assert "private" not in response.text
    finally:
        await application.state.workspace_service.close()
        await bars.close()


async def test_workspace_close_drains_inspection_before_capacity_release(monkeypatch, tmp_path):
    bars = BarService(Mock(), tmp_path)
    workspace = WorkspaceService(bars)
    entered, release = threading.Event(), threading.Event()

    def inspect(*_):
        entered.set()
        assert release.wait(5)
        return {}

    monkeypatch.setattr("marketlab.workspace.inspect_version", inspect)
    read = asyncio.create_task(workspace.inspect("a" * 64))
    close = None
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        close = asyncio.create_task(workspace.close())
        await asyncio.sleep(0.03)
        close.cancel()
        await asyncio.sleep(0.02)
        assert not close.done()
        assert bars.reader.compute.snapshot()["active"] == 1
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await close
        with pytest.raises(asyncio.CancelledError):
            await read
        assert bars.reader.compute.snapshot()["active"] == 0
        assert not workspace.tasks
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as stopped:
            await workspace.inspect("b" * 64)
        assert stopped.value.status_code == 503
    finally:
        release.set()
        await asyncio.gather(read, *([close] if close else []), return_exceptions=True)
        await workspace.close()
        await bars.close()


@pytest.mark.integration
async def test_real_ingestion_http_replay_conflict_partial_and_listing(dataset_engine):
    application = app()
    application.state.trade_engine = dataset_engine
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://127.0.0.1"
    ) as client:
        headers = {"Idempotency-Key": "workspace-" + uuid4().hex}
        body = INGEST | {"symbols": ["BTCUSDT", "ETHUSDT"]}
        first = await client.post("/v1/ingestion/submissions", headers=headers, json=body)
        assert first.status_code == 201
        submission = first.json()["submission_id"]
        assert (
            await client.post("/v1/ingestion/submissions", headers=headers, json=body)
        ).json() == first.json()
        assert (
            await client.post("/v1/ingestion/submissions", headers=headers, json=INGEST)
        ).status_code == 409
        with dataset_engine.begin() as connection:
            connection.execute(
                jobs.jobs.update()
                .where(
                    sa.and_(
                        jobs.jobs.c.submission_id == submission, jobs.jobs.c.symbol == "ETHUSDT"
                    )
                )
                .values(state="failed", error="safe failure")
            )
        detail = (await client.get("/v1/ingestion/submissions/" + submission)).json()
        assert detail["total"] == 2 and detail["failed"] == 1 and not detail["complete"]
        listing = (await client.get("/v1/ingestion/submissions?state=failed&symbol=ETHUSDT")).json()
        assert listing["items"][0]["submission_id"] == submission
        assert listing["items"][0]["queued"] == 1
        assert (await client.get("/v1/ingestion/submissions/" + str(uuid4()))).status_code == 404


@pytest.mark.integration
def test_real_catalog_keyset_ties_filters_and_committed_visibility(dataset_engine):
    stamp = datetime(2026, 1, 1, tzinfo=UTC)
    with dataset_engine.begin() as connection:
        for number in range(1, 7):
            version = f"{number:064x}"
            connection.execute(
                dataset_versions.insert().values(
                    dataset_version_id=version,
                    source_sha256="a" * 64,
                    manifest_sha256="b" * 64,
                    manifest_path="datasets/" + version + "/manifest.json",
                    venue="binance_spot",
                    symbol="BTCUSDT" if number % 2 else "ETHUSDT",
                    trade_date=date(2025, 1, number),
                    row_count=number,
                    status="published",
                    published_at=stamp,
                )
            )
    seen, cursor = [], None
    while True:
        url = "/?limit=2" + ("&cursor=" + cursor if cursor else "")
        response = collection(dataset_engine, Page.create(request(url), "datasets"))
        seen.extend(row["dataset_version_id"] for row in response["items"])
        assert all(
            row["verification"] == "registered_metadata" and "manifest_path" not in row
            for row in response["items"]
        )
        cursor = response["next_cursor"]
        if cursor is None:
            break
    assert seen == [f"{number:064x}" for number in range(6, 0, -1)]
    response = collection(
        dataset_engine,
        Page.create(
            request("/?symbol=BTCUSDT&start_date=2025-01-02&before_date=2025-01-06"), "datasets"
        ),
    )
    assert [row["trade_date"].day for row in response["items"]] == [5, 3]
    # An unrelated orphan directory is never consulted by this metadata-only query.
    assert len(seen) == 6


@pytest.mark.integration
async def test_real_dataset_detail_missing_and_corruption(dataset_engine, tmp_path):
    application = app()
    application.state.trade_engine = dataset_engine
    service = BarService(dataset_engine, tmp_path)
    application.state.bar_service = service
    application.state.workspace_service = WorkspaceService(service)
    version = "e" * 64
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://127.0.0.1"
        ) as client:
            assert (await client.get("/v1/datasets/" + version)).status_code == 404
            with dataset_engine.begin() as connection:
                connection.execute(
                    dataset_versions.insert().values(
                        dataset_version_id=version,
                        source_sha256="a" * 64,
                        manifest_sha256="b" * 64,
                        manifest_path="missing/manifest.json",
                        venue="binance_spot",
                        symbol="BTCUSDT",
                        trade_date=date(2025, 1, 1),
                        row_count=1,
                        status="published",
                        published_at=datetime.now(UTC),
                    )
                )
            corrupt = await client.get("/v1/datasets/" + version)
            assert corrupt.status_code == 422
            assert str(tmp_path) not in corrupt.text
    finally:
        await service.close()


@pytest.mark.integration
async def test_real_research_copilot_discovery_ties_current_revision(copilot_engine):
    application = app()
    application.state.trade_engine = copilot_engine
    stamp = datetime(2026, 1, 1, tzinfo=UTC)
    runs, requests = [], []
    for number in range(4):
        runs.append(
            research_store.submit(
                copilot_engine, f"workspace-research-{number}", research_body(), {}
            )[0]
        )
        requests.append(
            copilot_store.create(copilot_engine, copilot_body(), f"workspace-copilot-{number}")[0]
        )
    with copilot_engine.begin() as connection:
        connection.execute(research_store.runs.update().values(created_at=stamp))
        connection.execute(copilot_store.requests.update().values(created_at=stamp))
        connection.execute(
            copilot_store.revisions.update()
            .where(copilot_store.revisions.c.request_id == requests[0])
            .values(outcome="needs_clarification")
        )
        connection.execute(
            copilot_store.jobs.update()
            .where(copilot_store.jobs.c.request_id == requests[0])
            .values(state="completed")
        )
    copilot_store.answer(
        copilot_engine,
        requests[0],
        {
            "schema": "copilot-answer-v1",
            "expected_revision": 0,
            "text": "Explicit UTC January period",
            "context": {},
        },
        "workspace-answer",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://127.0.0.1"
    ) as client:
        for path, expected, field in [
            ("/v1/research/runs", runs, "run_id"),
            ("/v1/copilot/requests", requests, "request_id"),
        ]:
            found, cursor = [], None
            while True:
                response = await client.get(
                    path,
                    params={
                        "state": "queued",
                        "limit": "1",
                        **({"cursor": cursor} if cursor else {}),
                    },
                )
                assert response.status_code == 200, response.text
                result = response.json()
                found.extend(row[field] for row in result["items"])
                cursor = result["next_cursor"]
                if not cursor:
                    break
            assert found == sorted(expected, reverse=True)
        missing = await client.get("/v1/copilot/requests?state=failed")
        assert missing.json() == {"items": [], "next_cursor": None}
        current = (await client.get("/v1/copilot/requests?state=queued")).json()
        revised = next(row for row in current["items"] if row["request_id"] == requests[0])
        assert revised["revision"] == 1 and revised["outcome"] is None
        assert (await client.get("/v1/copilot/requests?state=completed")).json()["items"] == []
