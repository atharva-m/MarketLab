"""Additive bounded copilot HTTP adapters."""

import asyncio

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from marketlab.research.spec import ResearchError, parse_json

router = APIRouter(prefix="/v1/copilot", tags=["durable copilot"])


async def body(request: Request) -> object:
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise ResearchError("Copilot submission requires application/json")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 65536:
            raise ResearchError("Copilot submission exceeds 64 KiB")
    return parse_json(bytes(raw))


def failure(error: Exception) -> HTTPException:
    if isinstance(error, ResearchError):
        return HTTPException(error.status, str(error))
    return HTTPException(503, "Copilot catalog unavailable")


@router.post("/requests", status_code=201)
async def create(
    request: Request, idempotency_key: str = Header(alias="Idempotency-Key")
) -> JSONResponse:
    try:
        request_id, revision, replayed = await request.app.state.copilot_service.create(
            await body(request), idempotency_key
        )
        return JSONResponse(
            {"request_id": request_id, "revision": revision, "replayed": replayed},
            status_code=200 if replayed else 201,
        )
    except (ResearchError, SQLAlchemyError) as error:
        raise failure(error) from error


@router.get("/requests/{request_id}")
async def inspect(request: Request, request_id: str) -> JSONResponse:
    try:
        info = await asyncio.to_thread(request.app.state.copilot_service.inspect, request_id)
        return JSONResponse(jsonable_encoder(info))
    except (ResearchError, SQLAlchemyError) as error:
        raise failure(error) from error


@router.post("/requests/{request_id}/clarifications", status_code=201)
async def answer(
    request: Request, request_id: str, idempotency_key: str = Header(alias="Idempotency-Key")
) -> JSONResponse:
    try:
        identity, revision, replayed = await request.app.state.copilot_service.answer(
            request_id, await body(request), idempotency_key
        )
        return JSONResponse(
            {"request_id": identity, "revision": revision, "replayed": replayed},
            status_code=200 if replayed else 201,
        )
    except (ResearchError, SQLAlchemyError) as error:
        raise failure(error) from error
