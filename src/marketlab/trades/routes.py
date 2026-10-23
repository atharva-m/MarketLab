"""Small HTTP adapter over the existing transactional synthetic trade service."""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from marketlab.trades.parsers import TradeParseError
from marketlab.trades.persistence import (
    DuplicateTradeError,
    get_trade,
    import_trades_csv,
    import_trades_json,
)
from marketlab.trades.schemas import Trade

MAX_IMPORT_BYTES = 1024 * 1024
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
