"""Additive manual research HTTP adapters; no model dependency."""

import asyncio

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from marketlab.analytics.bars import BarError
from marketlab.datasets.source import DatasetError

from .service import ResearchService
from .spec import ResearchError, ResearchSpec, parse_json

router = APIRouter(prefix="/v1/research", tags=["deterministic research"])


def service(request: Request) -> ResearchService:
    return request.app.state.research_service  # type: ignore[no-any-return]


def failure(error: Exception) -> HTTPException:
    if isinstance(error, (ResearchError, BarError)):
        return HTTPException(error.status, str(error))
    if isinstance(error, SQLAlchemyError):
        return HTTPException(503, "Research catalog unavailable")
    return HTTPException(422, "Research artifact integrity failure")


@router.post("/runs", status_code=201, summary="Submit a strict pinned research-spec-v1")
async def submit(
    request: Request, idempotency_key: str = Header(alias="Idempotency-Key")
) -> JSONResponse:
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 65536:
            raise HTTPException(422, "Research submission exceeds 64 KiB")
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise HTTPException(422, "Research submission requires application/json")
    try:
        spec = ResearchSpec.create(parse_json(bytes(raw)))
        run_id, replayed = await service(request).submit(spec, idempotency_key)
        return JSONResponse(
            {"run_id": run_id, "replayed": replayed}, status_code=200 if replayed else 201
        )
    except (ResearchError, BarError, DatasetError, SQLAlchemyError, OSError, ValueError) as error:
        raise failure(error) from error
    except TimeoutError as error:
        raise HTTPException(503, "Research validation deadline exceeded") from error


@router.get("/runs/{run_id}", summary="Inspect durable research state and pinned provenance")
async def inspect(request: Request, run_id: str) -> JSONResponse:
    try:
        info = await asyncio.to_thread(service(request).inspect, run_id)
        return JSONResponse(jsonable_encoder(info))
    except (ResearchError, SQLAlchemyError) as error:
        raise failure(error) from error


@router.get("/runs/{run_id}/results", summary="Read verified immutable numerical results")
async def results(request: Request, run_id: str) -> JSONResponse:
    try:
        body, _ = await asyncio.to_thread(service(request).read, run_id, "results")
        return JSONResponse(body)
    except (ResearchError, DatasetError, SQLAlchemyError, OSError, ValueError) as error:
        raise failure(error) from error


@router.get("/runs/{run_id}/summary", summary="Read verified immutable summary with optional Redis")
async def summary(request: Request, run_id: str) -> JSONResponse:
    try:
        body, status = await service(request).summary(run_id)
        return JSONResponse(body, headers={"X-Cache": status})
    except (ResearchError, DatasetError, SQLAlchemyError, OSError, ValueError) as error:
        raise failure(error) from error
