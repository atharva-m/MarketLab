"""Narrow numerical v2 HTTP surface; discovery and model workflows remain separate."""

import asyncio
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from marketlab.analytics.bars import BarError
from marketlab.analytics.v2 import BarsRequest
from marketlab.datasets.v2.common import V2Error, parse_json
from marketlab.workspace import local_mutation

from .errors import STATUS
from .errors import code as error_code
from .service import ResearchService
from .spec import ResearchSpec

router = APIRouter(prefix="/v2", tags=["generalized numerical research"])


def failure(request: Request, error: Exception) -> JSONResponse:
    code = error_code(error)
    return JSONResponse(
        {
            "error": {
                "code": code,
                "message": {
                    "coverage_gap": "Registered coverage or required history is incomplete.",
                    "not_found": "The requested numerical resource was not found.",
                    "revision_conflict": "The operation conflicts with the current resource.",
                    "capacity_exceeded": "Numerical capacity is unavailable.",
                }.get(code, "Numerical operation failed."),
                "request_id": getattr(request.state, "request_id", "unavailable"),
            }
        },
        status_code=STATUS.get(code, 422),
        headers={"Retry-After": "1"} if code == "capacity_exceeded" else None,
    )


def service(request: Request) -> ResearchService:
    return request.app.state.v2_research_service  # type: ignore[no-any-return]


async def control(request: Request) -> dict[str, Any]:
    try:
        local_mutation(request)
    except Exception as error:
        raise V2Error("origin_denied", "Local origin required") from error
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise V2Error("unsupported_media", "JSON media type required")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > 65536:
            raise V2Error("body_too_large", "Control body exceeds limit")
        raw.extend(chunk)
    return parse_json(bytes(raw))


@router.post("/research/runs")
async def submit(request: Request) -> JSONResponse:
    try:
        body = await control(request)
        spec = ResearchSpec.create(body)
        run, replayed = await service(request).submit(
            spec, request.headers.get("idempotency-key", "")
        )
        info = await asyncio.to_thread(service(request).inspect, run)
        return JSONResponse(
            {"id": run, "state": info["state"], "replayed": replayed},
            status_code=200 if replayed else 201,
        )
    except (BarError, V2Error, SQLAlchemyError, OSError, ValueError, TimeoutError) as error:
        return failure(request, error)


@router.get("/research/runs/{run_id}")
async def inspect(request: Request, run_id: str) -> JSONResponse:
    try:
        return JSONResponse(await asyncio.to_thread(service(request).inspect, run_id))
    except (BarError, V2Error, SQLAlchemyError, ValueError) as error:
        return failure(request, error)


@router.get("/research/runs/{run_id}/results")
async def results(request: Request, run_id: str) -> JSONResponse:
    try:
        body, _ = await asyncio.to_thread(service(request).read, run_id, "results")
        return JSONResponse(body)
    except (BarError, V2Error, SQLAlchemyError, ValueError, OSError) as error:
        return failure(request, error)


@router.get("/research/runs/{run_id}/summary")
async def summary(request: Request, run_id: str) -> JSONResponse:
    try:
        body, status = await service(request).summary(run_id)
        return JSONResponse(body, headers={"X-Cache": status})
    except (BarError, V2Error, SQLAlchemyError, ValueError, OSError) as error:
        return failure(request, error)


@router.post("/research/runs/{run_id}/cancel")
async def cancel(request: Request, run_id: str) -> JSONResponse:
    try:
        body = await control(request)
        if set(body) != {"expected_revision"}:
            raise V2Error("invalid_request", "Invalid cancellation body")
        return JSONResponse(
            await service(request).cancel(
                run_id, body["expected_revision"], request.headers.get("idempotency-key", "")
            )
        )
    except (BarError, V2Error, SQLAlchemyError, ValueError) as error:
        return failure(request, error)


@router.get("/bars")
async def bars(request: Request) -> JSONResponse:
    try:
        pairs = list(request.query_params.multi_items())
        allowed = {"instrument_id", "version", "interval", "start", "end"}
        if any(k not in allowed for k, _ in pairs) or any(
            len(request.query_params.getlist(k)) != 1 for k in allowed - {"version"}
        ):
            raise V2Error("invalid_request", "Invalid bar query fields")
        parsed = BarsRequest.create(
            versions=request.query_params.getlist("version"),
            instrument_id=request.query_params["instrument_id"],
            interval=request.query_params["interval"],
            start=request.query_params["start"],
            end=request.query_params["end"],
        )
        body, status = await service(request).bars.read(parsed)
        return JSONResponse(body, headers={"X-Cache": status})
    except (BarError, V2Error, SQLAlchemyError, OSError, ValueError, TimeoutError) as error:
        return failure(request, error)
