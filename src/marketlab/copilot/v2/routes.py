"""Same-origin bounded control adapters for the versioned model workflows."""

import asyncio
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from marketlab.analytics.bars import BarError
from marketlab.copilot.model import ModelFailure
from marketlab.datasets.v2.common import V2Error
from marketlab.research.spec import ResearchError
from marketlab.research.v2.routes import control, failure

router = APIRouter(prefix="/v2", tags=["selected copilot and supplemental memos"])
ERRORS = (V2Error, ResearchError, SQLAlchemyError, BarError, OSError, ValueError, TimeoutError)


def error_response(request: Request, error: Exception) -> JSONResponse:
    if isinstance(error, ModelFailure):
        error = V2Error(
            "unavailable" if error.status == 503 else "invalid_request", "Model request failed"
        )
    return failure(request, error)


@router.post("/copilot/requests")
async def create(request: Request) -> JSONResponse:
    try:
        body = await control(request)
        identity, revision, replayed = await request.app.state.v2_copilot_service.create(
            body, request.headers.get("idempotency-key", "")
        )
        return JSONResponse(
            {"request_id": identity, "revision": revision, "replayed": replayed},
            status_code=200 if replayed else 201,
        )
    except ERRORS as error:
        return error_response(request, error)


@router.get("/copilot/requests/{request_id}")
async def inspect(request: Request, request_id: str) -> JSONResponse:
    try:
        return JSONResponse(
            await asyncio.to_thread(request.app.state.v2_copilot_service.inspect, request_id)
        )
    except ERRORS as error:
        return error_response(request, error)


@router.post("/copilot/requests/{request_id}/clarifications")
async def answer(request: Request, request_id: str) -> JSONResponse:
    try:
        body = await control(request)
        identity, revision, replayed = await request.app.state.v2_copilot_service.answer(
            request_id, body, request.headers.get("idempotency-key", "")
        )
        return JSONResponse(
            {"request_id": identity, "revision": revision, "replayed": replayed},
            status_code=200 if replayed else 201,
        )
    except ERRORS as error:
        return error_response(request, error)


@router.post("/research/runs/{run_id}/memo")
async def enqueue_memo(request: Request, run_id: str) -> JSONResponse:
    try:
        body = await control(request)
        result: dict[str, Any] = await asyncio.to_thread(
            request.app.state.v2_memo_service.enqueue,
            run_id,
            body,
            request.headers.get("idempotency-key", ""),
        )
        return JSONResponse(result, status_code=200 if result["replayed"] else 201)
    except ERRORS as error:
        return error_response(request, error)


@router.get("/research/runs/{run_id}/memo")
async def inspect_memo(request: Request, run_id: str) -> JSONResponse:
    try:
        return JSONResponse(
            await asyncio.to_thread(request.app.state.v2_memo_service.inspect, run_id)
        )
    except ERRORS as error:
        return error_response(request, error)
