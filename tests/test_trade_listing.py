import json
import threading
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import insert, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from marketlab.app import create_app
from marketlab.config import Settings
from marketlab.trades import import_trades_json, list_trades, routes, synthetic_trades
from marketlab.trades.persistence import trades
from marketlab.trades.schemas import Trade, TradePage


@pytest.fixture
def listing_app(tmp_path: Path) -> FastAPI:
    app = create_app(Settings(storage_path=tmp_path, _env_file=None))
    engine = Mock(spec=Engine)
    engine.connect.side_effect = AssertionError("unexpected database access")
    app.state.trade_engine = engine
    return app


@pytest.fixture
async def listing_client(listing_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=listing_app), base_url="http://test"
    ) as client:
        yield client


@pytest.mark.parametrize("limit", [1, 100, 500])
@pytest.mark.parametrize("after_id", [None, "SYN-0-000000"])
@pytest.mark.parametrize("symbol", [None, "SYN.A", "A0-."])
def test_service_bounds_query_and_uses_explicit_c_collation(
    limit: int, after_id: str | None, symbol: str | None
) -> None:
    engine = Mock(spec=Engine)
    connection = engine.connect.return_value.__enter__ = Mock()
    connection.return_value.execute.return_value.mappings.return_value.all.return_value = []
    engine.connect.return_value.__exit__ = Mock()
    assert list_trades(engine, limit, after_id, symbol) == TradePage(items=(), next_after_id=None)
    calls = connection.return_value.execute.call_args_list
    assert len(calls) == 2
    assert str(calls[0].args[0]) == "SET LOCAL TIME ZONE 'UTC'"
    compiled = calls[1].args[0].compile(dialect=postgresql.dialect())
    assert 'ORDER BY trades.trade_id COLLATE "C"' in str(compiled)
    literal_sql = str(calls[1].args[0].compile(compile_kwargs={"literal_binds": True}))
    assert f"LIMIT {limit + 1}" in literal_sql
    assert "OFFSET" not in str(compiled)
    if after_id is not None:
        assert '(trades.trade_id COLLATE "C") >' in str(compiled)
        assert after_id in compiled.params.values()
    if symbol is not None:
        assert "trades.symbol =" in str(compiled)
        assert symbol in compiled.params.values()
        assert symbol not in str(compiled)
        assert str(compiled).index("trades.symbol =") < str(compiled).index("LIMIT")
    if after_id is None and symbol is None:
        assert "WHERE" not in str(compiled)


@pytest.mark.parametrize("count", [0, 1, 2, 3])
def test_service_returns_only_page_and_sets_cursor_from_last_visible_item(count: int) -> None:
    expected = synthetic_trades(count)
    engine = Mock(spec=Engine)
    connection = engine.connect.return_value.__enter__ = Mock()
    connection.return_value.execute.return_value.mappings.return_value.all.return_value = [
        trade.model_dump() for trade in expected
    ]
    engine.connect.return_value.__exit__ = Mock()
    page = list_trades(engine, limit=2)
    assert page.items == expected[:2]
    assert page.next_after_id == (expected[1].trade_id if count > 2 else None)


@pytest.mark.parametrize("limit", [0, 501, -1, 1.5, True, "1"])
def test_service_invalid_limit_never_connects(limit: object) -> None:
    engine = Mock(spec=Engine)
    with pytest.raises(ValueError, match="limit"):
        list_trades(engine, limit)  # type: ignore[arg-type]
    assert engine.mock_calls == []


@pytest.mark.parametrize("after_id", ["", "_bad", "bad id", "é", "a" * 65, "bad\n"])
def test_service_invalid_boundary_never_connects(after_id: str) -> None:
    engine = Mock(spec=Engine)
    with pytest.raises(ValueError, match="after_id"):
        list_trades(engine, after_id=after_id)
    assert engine.mock_calls == []


@pytest.mark.parametrize(
    "symbol",
    ["", "syn.a", "SYN.a", " SYN.A", "SYN.A ", "A" * 21, "1A", "A_B", "É", "A,B", "A\n"],
)
def test_service_invalid_symbol_never_connects(symbol: str) -> None:
    engine = Mock(spec=Engine)
    with pytest.raises(ValueError, match="symbol"):
        list_trades(engine, symbol=symbol)
    assert engine.mock_calls == []


@pytest.mark.parametrize(
    "params",
    [
        {"limit": "0"},
        {"limit": "501"},
        {"limit": "-1"},
        {"limit": "1.5"},
        {"limit": "abc"},
        {"limit": ""},
        {"after_id": ""},
        {"after_id": "a" * 65},
        {"after_id": "bad id"},
        {"after_id": "é"},
        {"after_id": "' OR 1=1 --"},
        {"after_id": "_bad"},
        {"after_id": "bad\n"},
        {"symbol": ""},
        {"symbol": "syn.a"},
        {"symbol": "SYN.a"},
        {"symbol": " SYN.A"},
        {"symbol": "SYN.A "},
        {"symbol": "A" * 21},
        {"symbol": "1A"},
        {"symbol": "A_B"},
        {"symbol": "É"},
        {"symbol": "SYN.A,SYN.B"},
        {"symbol": "SYN.A\n"},
        {"symbol": "SYN.%"},
        {"symbol": "' OR 1=1 --"},
    ],
)
async def test_invalid_query_is_422_without_service_access(
    listing_app: FastAPI, listing_client: httpx.AsyncClient, params: dict[str, str]
) -> None:
    response = await listing_client.get("/trades", params=params)
    assert response.status_code == 422
    assert listing_app.state.trade_engine.mock_calls == []


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"limit": "1"},
        {"limit": "500", "after_id": "A._:-9"},
        {"symbol": "SYN.A"},
        {"symbol": "A" + "9" * 19, "limit": "1", "after_id": "a"},
    ],
)
async def test_route_parameters_serialization_and_worker(
    listing_app: FastAPI,
    listing_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    params: dict[str, str],
) -> None:
    main_thread = threading.get_ident()
    trade = Trade.model_validate(
        {
            "trade_id": "SYN-list",
            "symbol": "SYN.A",
            "executed_at": "2025-01-02T23:59:59.123456-05:30",
            "price": "999999999999.99999999",
            "quantity": "0.00000001",
        }
    )

    def listing(engine: Engine, limit: int, after_id: str | None, symbol: str | None) -> TradePage:
        assert threading.get_ident() != main_thread
        assert engine is listing_app.state.trade_engine
        assert limit == int(params.get("limit", "100"))
        assert after_id == params.get("after_id")
        assert symbol == params.get("symbol")
        return TradePage(items=(trade,), next_after_id=trade.trade_id)

    monkeypatch.setattr(routes, "list_trades", listing)
    response = await listing_client.get("/trades", params=params)
    assert response.status_code == 200
    assert response.json() == {
        "items": [trade.model_dump(mode="json")],
        "next_after_id": trade.trade_id,
    }
    assert response.json()["items"][0]["executed_at"] == "2025-01-03T05:29:59.123456Z"


@pytest.mark.parametrize("params", [{}, {"symbol": "UNKNOWN"}])
async def test_empty_page_is_200(
    listing_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, params: dict[str, str]
) -> None:
    monkeypatch.setattr(
        routes, "list_trades", lambda *args: TradePage(items=(), next_after_id=None)
    )
    response = await listing_client.get("/trades", params=params)
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_after_id": None}


@pytest.mark.parametrize("params", [{}, {"symbol": "SYN.A"}])
async def test_listing_database_error_is_redacted_and_observed(
    listing_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, params: dict[str, str]
) -> None:
    monkeypatch.setattr(
        routes,
        "list_trades",
        Mock(side_effect=SQLAlchemyError("password=secret; SELECT * FROM trades")),
    )
    response = await listing_client.get(
        "/trades", params=params, headers={"X-Request-ID": "list-db-123"}
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "Trade database unavailable"}
    assert response.headers["X-Request-ID"] == "list-db-123"
    assert 'route="/trades",status="503"' in (await listing_client.get("/metrics")).text


async def test_openapi_describes_listing(listing_client: httpx.AsyncClient) -> None:
    document = (await listing_client.get("/openapi.json")).json()
    operation = document["paths"]["/trades"]["get"]
    assert {"200", "422", "503"} <= set(operation["responses"])
    parameters = {parameter["name"]: parameter for parameter in operation["parameters"]}
    assert set(parameters) == {"limit", "after_id", "symbol"}
    assert parameters["limit"]["schema"]["default"] == 100
    assert parameters["limit"]["schema"]["minimum"] == 1
    assert parameters["limit"]["schema"]["maximum"] == 500
    assert "C collation" in operation["description"]
    assert "retain the same symbol" in operation["description"]
    symbol_schema = parameters["symbol"]["schema"]
    assert parameters["symbol"]["required"] is False
    assert symbol_schema["anyOf"][0]["maxLength"] == 20
    assert symbol_schema["anyOf"][0]["minLength"] == 1
    assert symbol_schema["anyOf"][0]["pattern"] == r"^[A-Z][A-Z0-9.-]{0,19}$"
    page = document["components"]["schemas"]["TradePage"]
    assert set(page["properties"]) == {"items", "next_after_id"}
    assert page["properties"]["items"]["type"] == "array"


@pytest.mark.integration
@pytest.mark.parametrize("limit", [1, 2, 7, 500])
async def test_postgres_http_c_order_and_keyset_boundaries(
    trade_engine: Engine,
    listing_app: FastAPI,
    listing_client: httpx.AsyncClient,
    limit: int,
) -> None:
    listing_app.state.trade_engine = trade_engine
    assert (await listing_client.get("/trades")).json() == {"items": [], "next_after_id": None}
    ids = ["a", "A", "A_", "A:", "A.", "A-", "0", "a0", "Z", "z"]
    template = synthetic_trades(1)[0].model_dump(mode="json")
    records = [{**template, "trade_id": trade_id} for trade_id in ids]
    assert (await listing_client.post("/trades/import/json", json=records)).status_code == 200
    observed: list[str] = []
    params: dict[str, str | int] = {"limit": limit}
    while True:
        response = await listing_client.get("/trades", params=params)
        assert response.status_code == 200
        page = response.json()
        assert len(page["items"]) <= limit
        observed.extend(item["trade_id"] for item in page["items"])
        assert all(Trade.model_validate(item).executed_at.tzinfo is UTC for item in page["items"])
        if page["next_after_id"] is None:
            break
        assert page["next_after_id"] == page["items"][-1]["trade_id"]
        params["after_id"] = page["next_after_id"]
    assert observed == sorted(ids)
    for boundary in ["A", "A.0", "Y", "zz"]:
        response = await listing_client.get("/trades", params={"after_id": boundary})
        assert [item["trade_id"] for item in response.json()["items"]] == [
            trade_id for trade_id in sorted(ids) if trade_id > boundary
        ]
        assert response.json()["next_after_id"] is None


@pytest.mark.integration
async def test_postgres_http_default_and_maximum_pages(
    trade_engine: Engine, listing_app: FastAPI, listing_client: httpx.AsyncClient
) -> None:
    listing_app.state.trade_engine = trade_engine
    expected = synthetic_trades(501)
    import_trades_json(
        trade_engine, json.dumps([trade.model_dump(mode="json") for trade in expected])
    )
    default = (await listing_client.get("/trades")).json()
    assert len(default["items"]) == 100
    assert default["next_after_id"] == expected[99].trade_id
    maximum = (await listing_client.get("/trades", params={"limit": 500})).json()
    assert len(maximum["items"]) == 500
    assert maximum["next_after_id"] == expected[499].trade_id
    final = (
        await listing_client.get("/trades", params={"after_id": maximum["next_after_id"]})
    ).json()
    assert [Trade.model_validate(item) for item in final["items"]] == [expected[500]]
    assert final["next_after_id"] is None


@pytest.mark.integration
@pytest.mark.parametrize("db_timezone", ["Pacific/Honolulu", "Pacific/Kiritimati"])
@pytest.mark.parametrize("symbol", [None, "SYN.A"])
async def test_postgres_listing_decimal_and_timestamp_boundaries(
    trade_engine: Engine,
    listing_app: FastAPI,
    listing_client: httpx.AsyncClient,
    db_timezone: str,
    symbol: str | None,
) -> None:
    listing_app.state.trade_engine = trade_engine
    template = {**synthetic_trades(1)[0].model_dump(mode="json"), "symbol": "SYN.A"}
    records = [
        {**template, "trade_id": "A", "executed_at": "0001-01-01T00:00:00Z"},
        {
            **template,
            "trade_id": "a",
            "executed_at": "9999-12-31T23:59:59.999999Z",
            "price": "999999999999.99999999",
            "quantity": "0.00000001",
        },
    ]
    with trade_engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('TimeZone', :zone, false)"), {"zone": db_timezone}
        )
    assert (await listing_client.post("/trades/import/json", json=records)).status_code == 200
    response = await listing_client.get("/trades", params={"symbol": symbol} if symbol else {})
    assert response.status_code == 200
    page = response.json()
    assert [Trade.model_validate(item) for item in page["items"]] == [
        Trade.model_validate(record) for record in records
    ]
    assert page["items"][0]["executed_at"] == "0001-01-01T00:00:00Z"
    assert page["items"][1]["executed_at"] == "9999-12-31T23:59:59.999999Z"
    assert page["items"][1]["quantity"] == "0.00000001"
    assert page["items"][1]["price"] == "999999999999.99999999"
    with trade_engine.connect() as connection:
        assert connection.execute(text("SHOW TIME ZONE")).scalar_one() == db_timezone


@pytest.mark.integration
async def test_postgres_listing_reads_current_commits(
    trade_engine: Engine, listing_app: FastAPI, listing_client: httpx.AsyncClient
) -> None:
    listing_app.state.trade_engine = trade_engine
    template = synthetic_trades(1)[0].model_dump(mode="json")
    for trade_id in ["A", "Z"]:
        import_trades_json(trade_engine, json.dumps([{**template, "trade_id": trade_id}]))
    first = (await listing_client.get("/trades", params={"limit": 1})).json()
    assert first["next_after_id"] == "A"
    for trade_id in ["0", "B"]:
        import_trades_json(trade_engine, json.dumps([{**template, "trade_id": trade_id}]))
    second = (await listing_client.get("/trades", params={"after_id": "A"})).json()
    assert [item["trade_id"] for item in second["items"]] == ["B", "Z"]
    assert second["next_after_id"] is None
    assert datetime.fromisoformat(second["items"][0]["executed_at"]).tzinfo is UTC


@pytest.mark.integration
@pytest.mark.parametrize("symbol", [None, "SYN.A"])
async def test_postgres_listing_failure_is_redacted(
    trade_engine: Engine,
    listing_app: FastAPI,
    listing_client: httpx.AsyncClient,
    symbol: str | None,
) -> None:
    listing_app.state.trade_engine = trade_engine
    # A real SQL failure in the fixture's private schema; fixture teardown removes it.
    with trade_engine.begin() as connection:
        schema = trade_engine.get_execution_options()["schema_translate_map"][None]
        connection.execute(text(f'DROP TABLE "{schema}".trades'))
    # Validation must win over the deliberately unavailable trade table.
    for invalid in ["", "syn.a", " SYN.A", "SYN.A ", "SYN.A,SYN.B", "A" * 21, "A\n"]:
        assert (await listing_client.get("/trades", params={"symbol": invalid})).status_code == 422
    response = await listing_client.get("/trades", params={"symbol": symbol} if symbol else {})
    assert response.status_code == 503
    assert response.json() == {"detail": "Trade database unavailable"}


@pytest.mark.integration
@pytest.mark.parametrize("limit", [1, 2, 3, 500])
async def test_postgres_exact_symbol_filter_precedes_pagination(
    trade_engine: Engine,
    listing_app: FastAPI,
    listing_client: httpx.AsyncClient,
    limit: int,
) -> None:
    listing_app.state.trade_engine = trade_engine
    template = synthetic_trades(1)[0].model_dump(mode="json")
    # Other symbols occupy the first rows and gaps between matches. Related names
    # must not match a prefix, substring or normalized form of the requested symbol.
    symbols = {
        "0": "SYN.B",
        "A": "SYN.A",
        "A-": "SYN.AA",
        "A.": "SYN.A",
        "A:": "SYN.B",
        "A_": "SYN.A",
        "Z": "XSYN.A",
        "a": "SYN.A",
        "a0": "SYN.A",
        "z": "SYN.B",
        "zz": "SYN.A",
    }
    records = [{**template, "trade_id": key, "symbol": value} for key, value in symbols.items()]
    assert (await listing_client.post("/trades/import/json", json=records)).status_code == 200
    expected = sorted(key for key, value in symbols.items() if value == "SYN.A")
    observed: list[str] = []
    params: dict[str, str | int] = {"symbol": "SYN.A", "limit": limit}
    while True:
        response = await listing_client.get("/trades", params=params)
        assert response.status_code == 200
        page = response.json()
        page_ids = [item["trade_id"] for item in page["items"]]
        assert len(page_ids) == min(limit, len(expected) - len(observed))
        assert all(item["symbol"] == "SYN.A" for item in page["items"])
        observed.extend(page_ids)
        if page["next_after_id"] is None:
            break
        assert page["next_after_id"] == page_ids[-1]
        params["after_id"] = page["next_after_id"]
    assert observed == expected
    # Includes stored nonmatching and nonexistent boundaries, plus the end boundary.
    for boundary in ["A-", "A.0", "Y", "zz", "zzz"]:
        page = (
            await listing_client.get("/trades", params={"symbol": "SYN.A", "after_id": boundary})
        ).json()
        assert [item["trade_id"] for item in page["items"]] == [
            key for key in expected if key > boundary
        ]
        assert page["next_after_id"] is None
    assert (await listing_client.get("/trades", params={"symbol": "UNKNOWN"})).json() == {
        "items": [],
        "next_after_id": None,
    }
    unfiltered = (await listing_client.get("/trades")).json()
    assert [item["trade_id"] for item in unfiltered["items"]] == sorted(symbols)


@pytest.mark.integration
async def test_postgres_filtered_pages_read_commits_during_concurrent_import(
    trade_engine: Engine, listing_app: FastAPI, listing_client: httpx.AsyncClient
) -> None:
    listing_app.state.trade_engine = trade_engine
    template = synthetic_trades(1)[0].model_dump(mode="json")
    import_trades_json(
        trade_engine,
        json.dumps([{**template, "trade_id": key, "symbol": "SYN.A"} for key in ["A", "Z"]]),
    )
    first = (await listing_client.get("/trades", params={"symbol": "SYN.A", "limit": 1})).json()
    assert first["next_after_id"] == "A"
    params = {"symbol": "SYN.A", "after_id": first["next_after_id"]}
    # A writer holds uncommitted new rows while a separate HTTP read runs. The
    # next read after commit sees matching rows beyond the previous boundary only.
    with trade_engine.begin() as writer:
        batch = [
            Trade.model_validate({**template, "trade_id": key, "symbol": symbol}).model_dump()
            for key, symbol in [("0", "SYN.A"), ("B", "SYN.A"), ("C", "SYN.B")]
        ]
        writer.execute(insert(trades), batch)
        during = (await listing_client.get("/trades", params=params)).json()
        assert [item["trade_id"] for item in during["items"]] == ["Z"]
        assert during["next_after_id"] is None
    after = (await listing_client.get("/trades", params=params)).json()
    assert [item["trade_id"] for item in after["items"]] == ["B", "Z"]
    assert after["next_after_id"] is None
    restart = (await listing_client.get("/trades", params={"symbol": "SYN.A"})).json()
    assert [item["trade_id"] for item in restart["items"]] == ["0", "A", "B", "Z"]
