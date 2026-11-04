"""Local discovery, durable ingestion and generation-scoped raw upload adapters."""

import asyncio
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from marketlab.workspace import local_mutation

from . import catalog, core, jobs
from .browser_imports import BrowserImports
from .common import V2Error, exact_fields, parse_json

router = APIRouter(prefix="/v2", tags=["Binance spot catalog and imports"])

STATUS = {
    "not_found": 404,
    "revision_conflict": 409,
    "idempotency_conflict": 409,
    "capacity_exceeded": 429,
    "unavailable": 503,
    "integrity_failure": 409,
    "ownership_lost": 409,
    "unsupported_media": 415,
    "body_too_large": 413,
    "origin_denied": 403,
    "deadline_exceeded": 504,
}


def failure(request: Request, error: BaseException) -> JSONResponse:
    code = error.code if isinstance(error, V2Error) else "unavailable"
    if code not in STATUS and code not in {
        "invalid_request",
        "unsupported_source",
        "coverage_too_dense",
    }:
        code = "unavailable"
    return JSONResponse(
        {
            "error": {
                "code": code,
                "message": {
                    "coverage_too_dense": "Narrow the coverage window or select dataset pages.",
                    "capacity_exceeded": "Local admission capacity is unavailable.",
                    "revision_conflict": "The operation conflicts with the current resource state.",
                    "origin_denied": "Local origin required.",
                }.get(code, "The catalog or import operation could not complete."),
                "request_id": getattr(request.state, "request_id", "unavailable"),
            }
        },
        status_code=STATUS.get(code, 422),
        headers={"Retry-After": "1"} if code == "capacity_exceeded" else None,
    )


def service(request: Request) -> BrowserImports:
    return request.app.state.v2_import_service  # type: ignore[no-any-return]


def origin(request: Request) -> None:
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise V2Error("origin_denied", "Cross-site mutation denied")
    try:
        local_mutation(request)
    except Exception as error:
        raise V2Error("origin_denied", "Local origin required") from error


async def control(request: Request) -> dict[str, Any]:
    origin(request)
    query(request, set())
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise V2Error("unsupported_media", "JSON required")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > 65536:
            raise V2Error("body_too_large", "Control body too large")
        data.extend(chunk)
    return parse_json(bytes(data))


def query(request: Request, fields: set[str]) -> dict[str, str]:
    pairs = list(request.query_params.multi_items())
    if any(name not in fields for name, _ in pairs) or len({v[0] for v in pairs}) != len(pairs):
        raise V2Error("invalid_request", "Invalid discovery query")
    return dict(pairs)


def page(values: dict[str, str]) -> dict[str, Any]:
    size = values.get("limit", "25")
    if not size.isascii() or not size.isdecimal() or len(size) > 3 or not 1 <= int(size) <= 100:
        raise V2Error("invalid_request", "Invalid page size")
    return {"limit": int(size), "cursor": values.get("cursor")}


@router.get("/capabilities")
async def capabilities(request: Request) -> JSONResponse:
    try:
        query(request, set())
        from .capabilities import value

        return JSONResponse(value())
    except (V2Error, ValueError) as error:
        return failure(request, error)


@router.get("/instruments")
async def instruments(request: Request) -> JSONResponse:
    try:
        values = query(request, {"base", "quote", "venue", "limit", "cursor"})
        if values.get("venue", "binance") != "binance":
            raise V2Error("unsupported_source", "Only Binance spot is supported")
        return JSONResponse(
            await asyncio.to_thread(
                catalog.instruments,
                service(request).engine,
                base=values.get("base"),
                quote=values.get("quote"),
                **page(values),
            )
        )
    except (V2Error, SQLAlchemyError, OSError, ValueError) as error:
        return failure(request, error)


@router.get("/instruments/{identity}")
async def instrument(request: Request, identity: str) -> JSONResponse:
    try:
        query(request, set())
        return JSONResponse(
            await asyncio.to_thread(catalog.instruments, service(request).engine, identity=identity)
        )
    except (V2Error, SQLAlchemyError, OSError, ValueError) as error:
        return failure(request, error)


@router.post("/instruments")
async def add_instrument(request: Request) -> JSONResponse:
    try:
        value = await asyncio.to_thread(
            core.add_instrument,
            service(request).engine,
            await control(request),
            request.headers.get("idempotency-key", ""),
        )
        return JSONResponse(value, status_code=200 if value.get("replayed") else 201)
    except (V2Error, SQLAlchemyError, OSError, ValueError, TypeError) as error:
        return failure(request, error)


@router.patch("/instruments/{identity}")
async def update_instrument(request: Request, identity: str) -> JSONResponse:
    try:
        value = await asyncio.to_thread(
            core.update_instrument,
            service(request).engine,
            identity,
            await control(request),
            request.headers.get("idempotency-key", ""),
        )
        return JSONResponse(value)
    except (V2Error, SQLAlchemyError, OSError, ValueError, TypeError) as error:
        return failure(request, error)


@router.get("/datasets")
async def datasets(request: Request) -> JSONResponse:
    try:
        values = query(request, {"instrument_id", "from_date", "before_date", "limit", "cursor"})
        return JSONResponse(
            await asyncio.to_thread(
                catalog.datasets,
                service(request).engine,
                identity=values.get("instrument_id"),
                first=values.get("from_date"),
                before=values.get("before_date"),
                **page(values),
            )
        )
    except (V2Error, SQLAlchemyError, OSError, ValueError) as error:
        return failure(request, error)


@router.get("/datasets/{version}")
async def dataset(request: Request, version: str) -> JSONResponse:
    try:
        query(request, set())
        return JSONResponse(
            await asyncio.to_thread(
                catalog.inspect_version, service(request).engine, service(request).root, version
            )
        )
    except (V2Error, SQLAlchemyError, OSError, ValueError) as error:
        return failure(request, error)


@router.get("/coverage")
async def coverage(request: Request) -> JSONResponse:
    try:
        values = query(request, {"instrument_id", "from_date", "before_date"})
        if set(values) != {"instrument_id", "from_date", "before_date"}:
            raise V2Error("invalid_request", "Coverage fields required")
        return JSONResponse(
            await asyncio.to_thread(
                catalog.coverage,
                service(request).engine,
                values["instrument_id"],
                values["from_date"],
                values["before_date"],
                root=service(request).root,
            )
        )
    except (V2Error, SQLAlchemyError, OSError, ValueError) as error:
        return failure(request, error)


@router.post("/ingestion/submissions")
async def submit(request: Request) -> JSONResponse:
    try:
        value = await asyncio.to_thread(
            jobs.submit,
            service(request).engine,
            await control(request),
            request.headers.get("idempotency-key", ""),
        )
        value["id"] = value["submission_id"]
        return JSONResponse(value, status_code=200 if value.get("replayed") else 201)
    except (V2Error, SQLAlchemyError, OSError, ValueError, TypeError) as error:
        return failure(request, error)


@router.get("/ingestion/submissions/{identity}")
async def submission(request: Request, identity: str) -> JSONResponse:
    try:
        query(request, set())
        return JSONResponse(
            await asyncio.to_thread(jobs.inspect_submission, service(request).engine, identity)
        )
    except (V2Error, SQLAlchemyError, OSError, ValueError) as error:
        return failure(request, error)


@router.post("/jobs/{identity}/cancel")
async def cancel_job(request: Request, identity: str) -> JSONResponse:
    try:
        body = await control(request)
        exact_fields(body, {"expected_revision"})
        return JSONResponse(
            await asyncio.to_thread(
                jobs.cancel,
                service(request).engine,
                identity,
                body["expected_revision"],
                request.headers.get("idempotency-key", ""),
            )
        )
    except (V2Error, SQLAlchemyError, OSError, ValueError, TypeError) as error:
        return failure(request, error)


@router.post("/imports")
async def create_import(request: Request) -> JSONResponse:
    try:
        value = await asyncio.to_thread(
            service(request).create,
            await control(request),
            request.headers.get("idempotency-key", ""),
        )
        return JSONResponse(value, status_code=200 if value.get("replayed") else 201)
    except (V2Error, SQLAlchemyError, OSError, ValueError, TypeError) as error:
        return failure(request, error)


@router.get("/imports/{identity}")
async def import_status(request: Request, identity: str) -> JSONResponse:
    try:
        query(request, set())
        return JSONResponse(await asyncio.to_thread(service(request).inspect, identity))
    except (V2Error, SQLAlchemyError, OSError, ValueError) as error:
        return failure(request, error)


@router.put("/imports/{identity}/content")
async def content(request: Request, identity: str) -> JSONResponse:
    try:
        origin(request)
        query(request, set())
        return JSONResponse(await service(request).receive(identity, request))
    except (V2Error, SQLAlchemyError, OSError, ValueError, TimeoutError) as error:
        return failure(request, error)


@router.post("/imports/{identity}/{action}")
async def import_action(request: Request, identity: str, action: str) -> JSONResponse:
    try:
        actions = {
            "upload": service(request).renew,
            "finalize": service(request).finalize,
            "cancel": service(request).cancel,
        }
        if action not in actions:
            raise V2Error("not_found", "Import action not found")
        value = await asyncio.to_thread(
            actions[action],
            identity,
            await control(request),
            request.headers.get("idempotency-key", ""),
        )
        return JSONResponse(
            value, status_code=201 if action == "finalize" and not value.get("replayed") else 200
        )
    except (V2Error, SQLAlchemyError, OSError, ValueError, TypeError) as error:
        return failure(request, error)
