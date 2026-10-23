"""Small HTTP adapter over the existing transactional synthetic trade service."""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BeforeValidator
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from marketlab.trades.parsers import TradeParseError
from marketlab.trades.persistence import (
    DuplicateTradeError,
    get_trade,
    import_trades_csv,
    import_trades_json,
    list_trades,
)
from marketlab.trades.schemas import (
    SYMBOL_PATTERN,
    TRADE_ID_PATTERN,
    Trade,
    TradePage,
    normalize_timestamp,
)

MAX_IMPORT_BYTES = 1024 * 1024
ExecutionTimestamp = Annotated[datetime, BeforeValidator(normalize_timestamp)]
router = APIRouter(prefix="/trades", tags=["synthetic trades"])
_IMPORT_RESPONSES: dict[int | str, dict[str, Any]] = {
    409: {"description": "Stored trade_id conflict; entire batch rejected"},
    413: {"description": "Import body exceeds 1,048,576 bytes"},
    415: {"description": "Unsupported Content-Type; use the endpoint's media type"},
    422: {"description": "Malformed UTF-8, invalid trade or duplicate ID within the batch"},
    503: {"description": "Trade database unavailable"},
}


async def _import(
    request: Request, media_type: str, importer: Callable[[Engine, str], int]
) -> dict[str, int]:
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != media_type:
        raise HTTPException(415, f"Content-Type must be {media_type}")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_IMPORT_BYTES:
            raise HTTPException(413, "Import body exceeds 1 MiB")
        body.extend(chunk)
    try:
        payload = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HTTPException(422, "Import body must be UTF-8") from error
    try:
        count = await run_in_threadpool(importer, request.app.state.trade_engine, payload)
    except (TradeParseError, RecursionError) as error:
        # Excessive JSON nesting is invalid input too; keep the week 2 parser unchanged.
        detail = str(error) if isinstance(error, TradeParseError) else "Invalid JSON nesting"
        raise HTTPException(422, detail) from error
    except DuplicateTradeError as error:
        raise HTTPException(409, "Batch contains an already stored trade_id") from error
    except ValueError as error:
        # json.loads also raises plain ValueError for integers exceeding Python's
        # digit limit. Do not expose its runtime detail or change the pure parser.
        raise HTTPException(422, "Invalid trade input") from error
    except SQLAlchemyError as error:
        raise HTTPException(503, "Trade database unavailable") from error
    return {"imported": count}


@router.post(
    "/import/json",
    responses=_IMPORT_RESPONSES,
    summary="Atomically import a synthetic JSON trade array",
    openapi_extra={
        "requestBody": {
            "required": True,
            "description": "UTF-8 JSON array, at most 1 MiB; decimal fields must be strings.",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "array",
                        "items": Trade.model_json_schema(mode="serialization"),
                    }
                }
            },
        }
    },
)
async def import_json(request: Request) -> dict[str, int]:
    return await _import(request, "application/json", import_trades_json)


@router.post(
    "/import/csv",
    responses=_IMPORT_RESPONSES,
    summary="Atomically import synthetic CSV trades",
    openapi_extra={
        "requestBody": {
            "required": True,
            "description": "UTF-8 CSV with the five canonical headers, at most 1 MiB.",
            "content": {"text/csv": {"schema": {"type": "string"}}},
        }
    },
)
async def import_csv(request: Request) -> dict[str, int]:
    return await _import(request, "text/csv", import_trades_csv)


@router.get(
    "",
    response_model=TradePage,
    summary="Browse synthetic trades in bounded, case-sensitive ID order",
    description=(
        "Orders trade_id ascending using PostgreSQL C collation. after_id is an exclusive "
        "boundary and need not exist. Fetches at most limit + 1 records; next_after_id is null "
        "at the end. Each request reads current committed data without a cross-page snapshot. "
        "Optional symbol matches the existing symbol syntax exactly, without normalization or "
        "partial matching. Optional executed_from is inclusive and executed_before is exclusive; "
        "either may be supplied alone. Both require executed_from < executed_before. Timestamp "
        "syntax requires seconds and timezone, with up to six fractional digits; values normalize "
        "to UTC. Use uppercase T and Z or a numeric +/-HH:MM offset. "
        "Filtering precedes pagination; retain the same symbol and time bounds across pages. "
        "Results remain ordered by ID, not execution time. Omitting time bounds preserves symbol "
        "filtering; omitting all filters lists all trades. "
        "Prices and quantities are decimal strings; timestamps are UTC."
    ),
    responses={
        422: {
            "description": "Invalid pagination, symbol or execution-time bounds; no database access"
        },
        503: _IMPORT_RESPONSES[503],
    },
)
def browse_trades(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=500, description="Maximum trades per page")] = 100,
    after_id: Annotated[
        str | None,
        Query(
            pattern=TRADE_ID_PATTERN,
            min_length=1,
            max_length=64,
            description="Exclusive trade_id boundary; need not exist in storage",
        ),
    ] = None,
    symbol: Annotated[
        str | None,
        Query(
            pattern=SYMBOL_PATTERN,
            min_length=1,
            max_length=20,
            description="Exact symbol; retain the same value across pages (for example SYN.A)",
        ),
    ] = None,
    executed_from: Annotated[
        ExecutionTimestamp | None,
        Query(
            description=(
                "Inclusive bound: YYYY-MM-DDTHH:MM:SS[.ffffff]Z or +/-HH:MM offset; "
                "optional fraction has 1-6 digits. URL-encode '+' as '%2B'."
            )
        ),
    ] = None,
    executed_before: Annotated[
        ExecutionTimestamp | None,
        Query(
            description=(
                "Exclusive bound: YYYY-MM-DDTHH:MM:SS[.ffffff]Z or +/-HH:MM offset; "
                "optional fraction has 1-6 digits. URL-encode '+' as '%2B'."
            )
        ),
    ] = None,
) -> TradePage:
    if (
        executed_from is not None
        and executed_before is not None
        and executed_from >= executed_before
    ):
        raise HTTPException(422, "executed_from must be earlier than executed_before")
    try:
        return list_trades(
            request.app.state.trade_engine, limit, after_id, symbol, executed_from, executed_before
        )
    except SQLAlchemyError as error:
        raise HTTPException(503, "Trade database unavailable") from error


@router.get(
    "/{trade_id}",
    response_model=Trade,
    summary="Retrieve a synthetic trade by exact, case-sensitive ID",
    responses={404: {"description": "No trade with that exact ID"}, 503: _IMPORT_RESPONSES[503]},
)
def retrieve_trade(request: Request, trade_id: str) -> Trade:
    # FastAPI runs synchronous routes in its worker pool, away from the event loop.
    try:
        trade = get_trade(request.app.state.trade_engine, trade_id)
    except SQLAlchemyError as error:
        raise HTTPException(503, "Trade database unavailable") from error
    if trade is None:
        raise HTTPException(404, "Trade not found")
    return trade
