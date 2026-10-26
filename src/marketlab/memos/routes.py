"""Separate memo state and verified supplemental content."""

import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from marketlab.research.spec import ResearchError

from .service import MemoService

router = APIRouter(prefix="/v1/research/runs", tags=["research memos"])


def service(request: Request) -> MemoService:
    return request.app.state.memo_service  # type: ignore[no-any-return]


def failure(error: Exception) -> HTTPException:
    if isinstance(error, ResearchError):
        return HTTPException(error.status, str(error))
    if isinstance(error, SQLAlchemyError):
        return HTTPException(503, "Memo catalog unavailable")
    return HTTPException(422, "Memo artifact integrity failure")


@router.post(
    "/{run_id}/memo", status_code=201, summary="Ensure one memo job for completed research"
)
async def enqueue(request: Request, run_id: str) -> JSONResponse:
    async for chunk in request.stream():
        if chunk:
            raise HTTPException(422, "Memo enqueue requires an empty body")
    try:
        run_id, replayed = await asyncio.to_thread(service(request).enqueue, run_id)
        return JSONResponse(
            {"run_id": run_id, "replayed": replayed}, status_code=200 if replayed else 201
        )
    except (ResearchError, SQLAlchemyError, OSError, ValueError, KeyError) as error:
        raise failure(error) from error


@router.get("/{run_id}/memo", summary="Read independent memo status and verified ready content")
async def inspect(request: Request, run_id: str) -> JSONResponse:
    try:
        return JSONResponse(
            jsonable_encoder(await asyncio.to_thread(service(request).inspect, run_id))
        )
    except (ResearchError, SQLAlchemyError, OSError, ValueError, KeyError) as error:
        raise failure(error) from error
