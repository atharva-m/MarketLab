import csv
import io
import json
import threading
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from marketlab.app import create_app
from marketlab.config import Settings
from marketlab.trades import Trade, routes, synthetic_trades


def json_body(records: list[dict[str, object]]) -> str:
    return json.dumps(records)


def csv_body(records: list[dict[str, object]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(Trade.model_fields))
    writer.writeheader()
    writer.writerows(records)
    return output.getvalue()


@pytest.fixture(params=[("json", "application/json", json_body), ("csv", "text/csv", csv_body)])
def wire_format(request: pytest.FixtureRequest) -> tuple[str, str, Callable[..., str]]:
    return request.param


@pytest.fixture
def route_app(tmp_path: Path) -> FastAPI:
    app = create_app(Settings(storage_path=tmp_path, _env_file=None))
    # No lifespan needed: the adapter is wired to an engine which must never connect
    # for invalid or empty requests. Successful persistence is exercised against PG below.
    engine = Mock(spec=Engine)
    engine.begin.side_effect = AssertionError("unexpected database access")
    engine.connect.side_effect = AssertionError("unexpected database access")
    app.state.trade_engine = engine
    return app


@pytest.fixture
async def route_client(route_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=route_app), base_url="http://test"
    ) as client:
        yield client


async def test_empty_import_never_accesses_database(
    route_app: FastAPI,
    route_client: httpx.AsyncClient,
    wire_format: tuple[str, str, Callable[..., str]],
) -> None:
    suffix, media, serialize = wire_format
    response = await route_client.post(
        f"/trades/import/{suffix}", content=serialize([]), headers={"Content-Type": media}
    )
    assert response.status_code == 200
    assert response.json() == {"imported": 0}
    assert route_app.state.trade_engine.mock_calls == []


@pytest.mark.parametrize("failure", ["record", "duplicate"])
async def test_invalid_batch_never_accesses_database(
    route_app: FastAPI,
    route_client: httpx.AsyncClient,
    wire_format: tuple[str, str, Callable[..., str]],
    failure: str,
) -> None:
    suffix, media, serialize = wire_format
    records = [trade.model_dump(mode="json") for trade in synthetic_trades(2)]
    if failure == "record":
        records[1]["price"] = "0"
    else:
        records[1] = records[0]
    response = await route_client.post(
        f"/trades/import/{suffix}", content=serialize(records), headers={"Content-Type": media}
    )
    assert response.status_code == 422
    assert "record 2" in response.json()["detail"]
    assert route_app.state.trade_engine.mock_calls == []


@pytest.mark.parametrize(
    ("suffix", "media", "body"),
    [
        ("json", "application/json", b"{"),
        ("json", "application/json", b"{}"),
        ("json", "application/json", b'[{"price": 1, "price": 2}]'),
        ("json", "application/json", b"[" * 2000 + b"]" * 2000),
        ("json", "application/json", b"[" + b"1" * 5000 + b"]"),
        ("csv", "text/csv", b"trade_id,symbol\r\n"),
        ("csv", "text/csv", b'"unterminated'),
        ("json", "application/json", b"\xff"),
        ("csv", "text/csv", b"\xff"),
    ],
)
async def test_malformed_import_is_422(
    route_client: httpx.AsyncClient, suffix: str, media: str, body: bytes
) -> None:
    response = await route_client.post(
        f"/trades/import/{suffix}", content=body, headers={"Content-Type": media}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("content_type", [None, "text/plain", "multipart/form-data"])
async def test_unsupported_content_type(
    route_client: httpx.AsyncClient,
    wire_format: tuple[str, str, Callable[..., str]],
    content_type: str | None,
) -> None:
    suffix, _, serialize = wire_format
    headers = {"Content-Type": content_type} if content_type else {}
    response = await route_client.post(
        f"/trades/import/{suffix}", content=serialize([]), headers=headers
    )
    assert response.status_code == 415


async def test_content_type_parameters_and_case(route_client: httpx.AsyncClient) -> None:
    response = await route_client.post(
        "/trades/import/json",
        content="[]",
        headers={"Content-Type": "Application/JSON; charset=utf-8"},
    )
    assert response.status_code == 200


async def test_openapi_describes_raw_import_bodies(route_client: httpx.AsyncClient) -> None:
    document = (await route_client.get("/openapi.json")).json()
    for suffix, media in (("json", "application/json"), ("csv", "text/csv")):
        operation = document["paths"][f"/trades/import/{suffix}"]["post"]
        assert media in operation["requestBody"]["content"]
        assert operation["requestBody"]["required"]
        assert {"409", "413", "415", "422", "503"} <= set(operation["responses"])


async def test_lifespan_disposes_trade_engine_in_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main_thread = threading.get_ident()
    engine = Mock(spec=Engine)
    disposed: list[int] = []
    engine.dispose.side_effect = lambda: disposed.append(threading.get_ident())
    monkeypatch.setattr("marketlab.app.create_engine", Mock(return_value=engine))
    app = create_app(Settings(storage_path=tmp_path, _env_file=None))
    with pytest.raises(RuntimeError, match="lifespan test"):
        async with app.router.lifespan_context(app):
            assert app.state.trade_engine is engine
            assert engine.mock_calls == []
            raise RuntimeError("lifespan test")
    assert engine.mock_calls == [("dispose", (), {})]
    assert len(disposed) == 1
    assert disposed[0] != main_thread


@pytest.mark.parametrize("streamed", [False, True])
@pytest.mark.parametrize("excess", [0, 1])
async def test_size_limit_counts_actual_bytes(
    route_app: FastAPI,
    route_client: httpx.AsyncClient,
    wire_format: tuple[str, str, Callable[..., str]],
    streamed: bool,
    excess: int,
) -> None:
    suffix, media, serialize = wire_format
    empty = serialize([]).encode()
    # JSON whitespace is valid at the boundary; CSV reaches its existing parser
    # and returns 422 for the invalid extra row, rather than a premature 413.
    body = empty + b" " * (routes.MAX_IMPORT_BYTES - len(empty) + excess)

    async def chunks() -> AsyncIterator[bytes]:
        for index in range(0, len(body), 16384):
            yield body[index : index + 16384]

    headers = {"Content-Type": media}
    if streamed:
        # A dishonest Content-Length must not bypass the actual streamed byte count.
        headers["Content-Length"] = "2"
    response = await route_client.post(
        f"/trades/import/{suffix}", content=chunks() if streamed else body, headers=headers
    )
    assert response.status_code == (413 if excess else (200 if suffix == "json" else 422))
    assert route_app.state.trade_engine.mock_calls == []


async def test_chunked_size_limit_without_content_length(route_client: httpx.AsyncClient) -> None:
    async def chunks() -> AsyncIterator[bytes]:
        yield b" " * routes.MAX_IMPORT_BYTES
        yield b"x"
        raise AssertionError("adapter should stop consuming an oversized body")

    response = await route_client.post(
        "/trades/import/json", content=chunks(), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413


@pytest.mark.parametrize("status", [413, 415, 422])
async def test_import_errors_keep_request_id_and_metrics(
    route_client: httpx.AsyncClient, status: int
) -> None:
    response = await route_client.post(
        "/trades/import/json",
        content=b"x" * (routes.MAX_IMPORT_BYTES + 1) if status == 413 else b"invalid",
        headers={
            "Content-Type": "text/plain" if status == 415 else "application/json",
            "X-Request-ID": "import-error-123",
        },
    )
    assert response.status_code == status
    assert response.headers["X-Request-ID"] == "import-error-123"
    metrics = await route_client.get("/metrics")
    assert f'route="/trades/import/json",status="{status}"' in metrics.text


async def test_import_runs_service_in_worker(
    route_app: FastAPI, route_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    main_thread = threading.get_ident()

    def importer(engine: Engine, payload: str) -> int:
        assert threading.get_ident() != main_thread
        assert engine is route_app.state.trade_engine
        assert payload == "[]"
        return 0

    monkeypatch.setattr(routes, "import_trades_json", importer)
    response = await route_client.post(
        "/trades/import/json", content="[]", headers={"Content-Type": "application/json"}
    )
    assert response.json() == {"imported": 0}


async def test_get_serialization_and_worker(
    route_app: FastAPI, route_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    main_thread = threading.get_ident()
    trade = synthetic_trades(1)[0]

    def lookup(engine: Engine, trade_id: str) -> Trade | None:
        assert threading.get_ident() != main_thread
        assert engine is route_app.state.trade_engine
        return trade if trade_id == trade.trade_id else None

    monkeypatch.setattr(routes, "get_trade", lookup)
    response = await route_client.get(f"/trades/{trade.trade_id}")
    assert response.status_code == 200
    assert response.json() == trade.model_dump(mode="json")
    assert (await route_client.get(f"/trades/{trade.trade_id.lower()}")).status_code == 404
    assert (await route_client.get("/trades/missing")).status_code == 404


@pytest.mark.parametrize("endpoint", ["/trades/import/json", "/trades/import/csv", "/trades/SYN-1"])
async def test_database_errors_are_redacted_and_observed(
    route_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, endpoint: str
) -> None:
    failure = Mock(side_effect=SQLAlchemyError("secret password; INSERT INTO trades"))
    for name in ("import_trades_json", "import_trades_csv", "get_trade"):
        monkeypatch.setattr(routes, name, failure)
    response = (
        await route_client.get(endpoint, headers={"X-Request-ID": "db-123"})
        if endpoint.endswith("SYN-1")
        else await route_client.post(
            endpoint,
            content="[]",
            headers={
                "Content-Type": "text/csv" if endpoint.endswith("csv") else "application/json",
                "X-Request-ID": "db-123",
            },
        )
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "Trade database unavailable"}
    assert response.headers["X-Request-ID"] == "db-123"
    metrics = await route_client.get("/metrics")
    assert (
        f'route="{endpoint if "import" in endpoint else "/trades/{trade_id}"}",status="503"'
        in metrics.text
    )


@pytest.mark.integration
async def test_http_postgres_round_trip(
    trade_engine: Engine,
    route_app: FastAPI,
    route_client: httpx.AsyncClient,
    wire_format: tuple[str, str, Callable[..., str]],
) -> None:
    route_app.state.trade_engine = trade_engine
    suffix, media, serialize = wire_format
    record = {
        "trade_id": "SYN-Exact.Case:1",
        "symbol": "SYN.A",
        "executed_at": "2025-01-02T23:59:59.123456-05:30",
        "price": "999999999999.99999999",
        "quantity": "0.00000001",
    }
    response = await route_client.post(
        f"/trades/import/{suffix}", content=serialize([record]), headers={"Content-Type": media}
    )
    assert response.status_code == 200
    assert response.json() == {"imported": 1}
    response = await route_client.get(f"/trades/{record['trade_id']}")
    assert response.status_code == 200
    assert response.json() == {**record, "executed_at": "2025-01-03T05:29:59.123456Z"}
    assert (await route_client.get("/trades/syn-exact.case:1")).status_code == 404
    assert (await route_client.get("/trades/SYN-missing")).status_code == 404


@pytest.mark.integration
@pytest.mark.parametrize("duplicate_index", [0, 1, 2])
async def test_http_cross_batch_conflict_rolls_back(
    trade_engine: Engine,
    route_app: FastAPI,
    route_client: httpx.AsyncClient,
    wire_format: tuple[str, str, Callable[..., str]],
    duplicate_index: int,
) -> None:
    route_app.state.trade_engine = trade_engine
    suffix, media, serialize = wire_format
    records = [trade.model_dump(mode="json") for trade in synthetic_trades(3, seed=73)]
    stored = records[duplicate_index]
    response = await route_client.post("/trades/import/json", json=[stored])
    assert response.status_code == 200
    changed = [{**record, "price": "1.25"} for record in records]
    response = await route_client.post(
        f"/trades/import/{suffix}",
        content=serialize(changed),
        headers={"Content-Type": media, "X-Request-ID": "conflict-123"},
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "Batch contains an already stored trade_id"}
    assert response.headers["X-Request-ID"] == "conflict-123"
    for record in records:
        response = await route_client.get(f"/trades/{record['trade_id']}")
        if record == stored:
            assert response.status_code == 200
            assert Trade.model_validate(response.json()) == Trade.model_validate(stored)
        else:
            assert response.status_code == 404
    response = await route_client.post(
        f"/trades/import/{suffix}",
        content=serialize([record for record in records if record != stored]),
        headers={"Content-Type": media},
    )
    assert response.status_code == 200
    assert response.json() == {"imported": 2}


@pytest.mark.integration
@pytest.mark.parametrize("failure", ["record", "duplicate"])
async def test_http_invalid_and_empty_preserve_existing_records(
    trade_engine: Engine,
    route_app: FastAPI,
    route_client: httpx.AsyncClient,
    wire_format: tuple[str, str, Callable[..., str]],
    failure: str,
) -> None:
    route_app.state.trade_engine = trade_engine
    suffix, media, serialize = wire_format
    stored, fresh = [trade.model_dump(mode="json") for trade in synthetic_trades(2, seed=88)]
    assert (await route_client.post("/trades/import/json", json=[stored])).status_code == 200
    records = [fresh, dict(fresh)]
    if failure == "record":
        records[1]["quantity"] = "0"
    response = await route_client.post(
        f"/trades/import/{suffix}", content=serialize(records), headers={"Content-Type": media}
    )
    assert response.status_code == 422
    assert (await route_client.get(f"/trades/{fresh['trade_id']}")).status_code == 404
    response = await route_client.post(
        f"/trades/import/{suffix}", content=serialize([]), headers={"Content-Type": media}
    )
    assert response.status_code == 200
    assert response.json() == {"imported": 0}
    response = await route_client.get(f"/trades/{stored['trade_id']}")
    assert response.status_code == 200
    assert Trade.model_validate(response.json()) == Trade.model_validate(stored)
