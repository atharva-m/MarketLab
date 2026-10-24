"""Additive bounded bar HTTP adapter."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from .bars import BarError, BarService, BarsRequest
from .schemas import BarResponse

router = APIRouter(prefix="/v1", tags=["historical analytics"])


@router.get(
    "/bars",
    response_model=BarResponse,
    summary="Read completed UTC bars from explicitly pinned published datasets",
    responses={
        404: {"description": "Unknown dataset version"},
        409: {"description": "Incomplete or mismatched daily coverage"},
        422: {"description": "Invalid request, artifact integrity or arithmetic failure"},
        503: {"description": "Catalog unavailable or query capacity exhausted"},
        504: {"description": "DuckDB execution deadline exceeded"},
    },
    description=(
        "Repeated version parameters select exactly one registered version per touched UTC day. "
        "One symbol, 1m/5m, aligned UTC start/end, at most 1440 expected buckets and five "
        "partitions. Missing buckets are omitted. Decimal values are strings. X-Cache is HIT, "
        "MISS or BYPASS. The 60-second deadline applies to DuckDB execution; cold full artifact "
        "verification can take longer."
    ),
)
async def bars(
    request: Request,
    version: Annotated[list[str], Query(min_length=1, max_length=5)],
    symbol: Literal["BTCUSDT", "ETHUSDT"],
    interval: Literal["1m", "5m"],
    start: str,
    end: str,
) -> JSONResponse:
    try:
        query = BarsRequest.create(
            versions=version, symbol=symbol, interval=interval, start=start, end=end
        )
        service: BarService = request.app.state.bar_service
        body, status = await service.read(query)
        return JSONResponse(body, headers={"X-Cache": status})
    except BarError as error:
        raise HTTPException(error.status, str(error)) from error
