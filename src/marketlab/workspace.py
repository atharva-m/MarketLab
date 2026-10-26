"""Bounded local-workspace HTTP adapters over retained durable services."""

import asyncio
import base64
import binascii
import json
import re
import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from marketlab.analytics.bars import BarService
from marketlab.analytics.verification import VerificationUnavailable
from marketlab.copilot import store as copilot
from marketlab.datasets import jobs as ingestion
from marketlab.datasets.normalize import VerificationCancelled
from marketlab.datasets.publication import dataset_versions, inspect_version
from marketlab.datasets.source import DatasetError
from marketlab.research import store as research
from marketlab.research.spec import ResearchError, parse_json

router = APIRouter(tags=["local workspace"])
STATES = {"queued", "running", "retry_wait", "succeeded", "failed"}
COPILOT_STATES = {"queued", "running", "retry_wait", "completed", "failed"}


def identity(value: str, *, version: bool = False) -> str:
    if version:
        if re.fullmatch(r"[0-9a-f]{64}", value) is not None:
            return value
    else:
        try:
            if str(UUID(value)) == value:
                return value
        except ValueError:
            pass
    raise HTTPException(422, "Invalid workspace identity")


def day(value: Any) -> date:
    if not isinstance(value, str) or re.fullmatch(r"2025-0[12]-[0-9]{2}", value) is None:
        raise HTTPException(422, "Invalid January date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise HTTPException(422, "Invalid January date") from error
    if not date(2025, 1, 1) <= parsed <= date(2025, 2, 1):
        raise HTTPException(422, "Invalid January date")
    return parsed


@dataclass(frozen=True)
class Page:
    collection: str
    limit: int
    filters: dict[str, str]
    after: tuple[datetime, str] | None

    @classmethod
    def create(cls, request: Request, collection: str) -> "Page":
        allowed = {"limit", "cursor"}
        if collection == "datasets":
            allowed |= {"symbol", "start_date", "before_date"}
        else:
            allowed |= {"state"}
            if collection == "ingestion":
                allowed.add("symbol")
        pairs = list(request.query_params.multi_items())
        if len(pairs) != len({name for name, _ in pairs}) or any(
            name not in allowed for name, _ in pairs
        ):
            raise HTTPException(422, "Invalid workspace query fields")
        values = dict(pairs)
        raw_limit = values.get("limit", "25")
        if re.fullmatch(r"[1-9][0-9]{0,2}", raw_limit) is None or int(raw_limit) > 100:
            raise HTTPException(422, "Invalid workspace page limit")
        filters = {name: value for name, value in values.items() if name not in {"limit", "cursor"}}
        if "symbol" in filters and filters["symbol"] not in {"BTCUSDT", "ETHUSDT"}:
            raise HTTPException(422, "Invalid workspace symbol")
        if "state" in filters and filters["state"] not in (
            COPILOT_STATES if collection == "copilot" else STATES
        ):
            raise HTTPException(422, "Invalid workspace state")
        for name in ("start_date", "before_date"):
            if name in filters:
                day(filters[name])
        if filters.get("start_date", "2025-01-01") >= filters.get("before_date", "2025-02-01"):
            raise HTTPException(422, "Invalid workspace date interval")
        after = None
        if "cursor" in values:
            token = values["cursor"]
            if len(token) > 2048 or re.fullmatch(r"[A-Za-z0-9_-]+", token) is None:
                raise HTTPException(422, "Invalid workspace cursor")
            try:
                data = parse_json(
                    base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
                )
                if (
                    not isinstance(data, dict)
                    or set(data) != {"schema", "collection", "filters", "time", "id"}
                    or data["schema"] != "workspace-cursor-v1"
                    or data["collection"] != collection
                    or data["filters"] != filters
                    or not isinstance(data["time"], str)
                    or not data["time"].endswith("+00:00")
                    or len(data["time"]) > 40
                    or not isinstance(data["id"], str)
                ):
                    raise ValueError
                stamp = datetime.fromisoformat(data["time"])
                identity(data["id"], version=collection == "datasets")
                after = stamp, data["id"]
            except (ValueError, TypeError, binascii.Error, ResearchError, HTTPException) as error:
                raise HTTPException(422, "Invalid workspace cursor") from error
        return cls(collection, int(raw_limit), filters, after)

    def cursor(self, stamp: datetime, unique: str) -> str:
        raw = json.dumps(
            {
                "schema": "workspace-cursor-v1",
                "collection": self.collection,
                "filters": self.filters,
                "time": stamp.astimezone(UTC).isoformat(),
                "id": unique,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def engine(request: Request) -> Engine:
    return request.app.state.trade_engine  # type: ignore[no-any-return]


def failure(error: Exception) -> HTTPException:
    if isinstance(error, sa.exc.SQLAlchemyError) or (
        isinstance(error, DatasetError) and isinstance(error.__cause__, sa.exc.SQLAlchemyError)
    ):
        return HTTPException(503, "Workspace catalog unavailable")
    return HTTPException(422, "Workspace artifact integrity failure")


def collection(db: Engine, page: Page) -> dict[str, Any]:
    """Fixed queries and keyset ordering; no paths or full artifact reads."""
    if page.collection == "datasets":
        table, unique, stamp = (
            dataset_versions,
            dataset_versions.c.dataset_version_id,
            dataset_versions.c.published_at,
        )
        query = sa.select(
            *[
                table.c[name]
                for name in (
                    "dataset_version_id",
                    "venue",
                    "symbol",
                    "trade_date",
                    "row_count",
                    "source_sha256",
                    "manifest_sha256",
                    "published_at",
                )
            ]
        ).where(table.c.status == "published")
        for field, op in (("start_date", "ge"), ("before_date", "lt")):
            if field in page.filters:
                boundary = day(page.filters[field])
                query = query.where(
                    table.c.trade_date >= boundary if op == "ge" else table.c.trade_date < boundary
                )
        if "symbol" in page.filters:
            query = query.where(table.c.symbol == page.filters["symbol"])
    elif page.collection == "ingestion":
        table, unique, stamp = (
            ingestion.submissions,
            ingestion.submissions.c.submission_id,
            ingestion.submissions.c.created_at,
        )
        counts = (
            sa.select(
                ingestion.jobs.c.submission_id,
                sa.func.count().label("total"),
                *[
                    sa.func.count().filter(ingestion.jobs.c.state == state).label(state)
                    for state in sorted(STATES)
                ],
            )
            .where(ingestion.jobs.c.source_mode == "official")
            .group_by(ingestion.jobs.c.submission_id)
            .subquery()
        )
        query = sa.select(
            table.c.submission_id,
            table.c.symbols,
            table.c.start_date,
            table.c.before_date,
            table.c.created_at,
            *[counts.c[name] for name in ["total", *sorted(STATES)]],
        ).join(counts, counts.c.submission_id == unique)
        if "state" in page.filters or "symbol" in page.filters:
            matching = sa.select(ingestion.jobs.c.job_id).where(
                ingestion.jobs.c.submission_id == unique
            )
            for name in ("state", "symbol"):
                if name in page.filters:
                    matching = matching.where(ingestion.jobs.c[name] == page.filters[name])
            query = query.where(matching.exists())
    elif page.collection == "research":
        table, unique, stamp = research.runs, research.runs.c.run_id, research.runs.c.created_at
        query = sa.select(
            table.c.run_id,
            table.c.state,
            table.c.attempt_count,
            table.c.created_at,
            table.c.updated_at,
            research.submissions.c.spec,
        ).join(research.submissions, research.submissions.c.submission_id == table.c.submission_id)
        if "state" in page.filters:
            query = query.where(table.c.state == page.filters["state"])
    else:
        table, unique, stamp = (
            copilot.requests,
            copilot.requests.c.request_id,
            copilot.requests.c.created_at,
        )
        query = (
            sa.select(
                table.c.request_id,
                table.c.current_revision.label("revision"),
                table.c.run_id,
                table.c.created_at,
                table.c.updated_at,
                copilot.jobs.c.state,
                copilot.revisions.c.outcome,
            )
            .join(
                copilot.jobs,
                sa.and_(
                    copilot.jobs.c.request_id == unique,
                    copilot.jobs.c.revision == table.c.current_revision,
                ),
            )
            .join(
                copilot.revisions,
                sa.and_(
                    copilot.revisions.c.request_id == unique,
                    copilot.revisions.c.revision == table.c.current_revision,
                ),
            )
        )
        if "state" in page.filters:
            query = query.where(copilot.jobs.c.state == page.filters["state"])
    order_id = unique.collate("C")
    if page.after is not None:
        last_time, last_id = page.after
        query = query.where(
            sa.or_(stamp < last_time, sa.and_(stamp == last_time, order_id < last_id))
        )
    query = query.order_by(stamp.desc(), order_id.desc()).limit(page.limit + 1)
    with db.begin() as connection:
        research.bounded(connection)
        rows = [dict(row) for row in connection.execute(query).mappings()]
    extra = len(rows) > page.limit
    rows = rows[: page.limit]
    token = None
    if extra:
        last = rows[-1]
        token = page.cursor(last[stamp.name], str(last[unique.name]))
    for row in rows:
        if page.collection == "datasets":
            row["verification"] = "registered_metadata"
        elif page.collection == "ingestion":
            row["symbols"] = json.loads(row["symbols"])
        elif page.collection == "research":
            spec = json.loads(row.pop("spec"))
            row.update({name: spec[name] for name in ("workflow", "symbols", "start", "end")})
    return {"items": rows, "next_cursor": token}


async def listing(request: Request, name: str) -> JSONResponse:
    page = Page.create(request, name)
    try:
        result = await asyncio.to_thread(collection, engine(request), page)
        return JSONResponse(jsonable_encoder(result))
    except (sa.exc.SQLAlchemyError, ValueError, KeyError, TypeError) as error:
        raise failure(error) from error


@router.get("/v1/datasets")
async def datasets(request: Request) -> JSONResponse:
    return await listing(request, "datasets")


async def verified_detail(service: BarService, version: str) -> dict[str, object] | None:
    if service.closed:
        raise HTTPException(503, "Dataset verification unavailable")
    try:
        await asyncio.wait_for(service.capacity.acquire(), service.admission_timeout)
    except TimeoutError as error:
        raise HTTPException(503, "Dataset verification capacity unavailable") from error
    cancelled = threading.Event()
    try:

        def inspect() -> dict[str, object] | None:
            with service.reader.compute.query(cancelled, service.admission_timeout):
                return inspect_version(service.reader.engine, service.reader.root, version)

        return await service._thread(inspect, cancelled)  # type: ignore[no-any-return]
    except (VerificationUnavailable, VerificationCancelled) as error:
        raise HTTPException(503, "Dataset verification capacity unavailable") from error
    finally:
        service.capacity.release()


class WorkspaceService:
    """Own new full-inspection tasks and drain them before BarService shutdown."""

    def __init__(self, bars: BarService) -> None:
        self.bars = bars
        self.tasks: set[asyncio.Task[dict[str, object] | None]] = set()
        self.closed = False
        self.closing: asyncio.Task[None] | None = None

    async def inspect(self, version: str) -> dict[str, object] | None:
        if self.closed:
            raise HTTPException(503, "Dataset verification unavailable")
        task = asyncio.create_task(verified_detail(self.bars, version))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return await task

    async def close(self) -> None:
        self.closed = True

        async def drain() -> None:
            tasks = list(self.tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        if self.closing is None:
            self.closing = asyncio.create_task(drain())
        cancelled = None
        while not self.closing.done():
            try:
                await asyncio.shield(self.closing)
            except asyncio.CancelledError as error:
                cancelled = error
        self.closing.result()
        if cancelled is not None:
            raise cancelled


@router.get("/v1/datasets/{version_id}")
async def dataset(request: Request, version_id: str) -> JSONResponse:
    identity(version_id, version=True)
    try:
        manifest = await request.app.state.workspace_service.inspect(version_id)
        if manifest is None:
            raise HTTPException(404, "Dataset version not found")
        return JSONResponse(
            {"dataset_version_id": version_id, "verification": "verified", "manifest": manifest}
        )
    except (sa.exc.SQLAlchemyError, DatasetError, OSError, ValueError, TypeError) as error:
        raise failure(error) from error


def local_mutation(request: Request) -> None:
    """New adapter is local-only; absent Origin preserves nonbrowser clients."""
    try:
        host = urlsplit("http://" + request.headers.get("host", ""))
        if (
            host.hostname not in {"127.0.0.1", "localhost", "::1"}
            or host.username
            or host.password
            or host.path
            or host.query
            or host.fragment
            or (host.port is not None and not 1 <= host.port <= 65535)
        ):
            raise ValueError
        origin = request.headers.get("origin")
        if origin is not None:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
                or (parsed.port is not None and not 1 <= parsed.port <= 65535)
                or not (parsed.netloc == host.netloc or origin == "http://127.0.0.1:5173")
            ):
                raise ValueError
    except ValueError as error:
        raise HTTPException(403, "Local workspace origin required") from error


@router.post("/v1/ingestion/submissions", status_code=201)
async def submit(
    request: Request, idempotency_key: str = Header(alias="Idempotency-Key")
) -> JSONResponse:
    local_mutation(request)
    if request.query_params:
        raise HTTPException(422, "Invalid ingestion query")
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise HTTPException(422, "Ingestion submission requires application/json")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 65536:
            raise HTTPException(422, "Ingestion submission exceeds 64 KiB")
    try:
        body = parse_json(bytes(raw))
        if (
            not isinstance(body, dict)
            or set(body) != {"schema", "symbols", "start_date", "before_date"}
            or body["schema"] != "ingestion-submission-v1"
            or not isinstance(body["symbols"], list)
            or any(not isinstance(symbol, str) for symbol in body["symbols"])
        ):
            raise HTTPException(422, "Invalid ingestion submission fields")
        start, before = day(body["start_date"]), day(body["before_date"])
        symbols = ingestion.validate_request(body["symbols"], start, before, idempotency_key)
        submission_id = await asyncio.to_thread(
            ingestion.submit, engine(request), symbols, start, before, idempotency_key
        )
        return JSONResponse({"submission_id": submission_id}, status_code=201)
    except ResearchError as error:
        raise HTTPException(422, "Invalid ingestion JSON") from error
    except DatasetError as error:
        status = 409 if str(error) == "submission key conflicts with existing request" else 422
        raise HTTPException(
            status, "Ingestion key conflict" if status == 409 else "Invalid ingestion submission"
        ) from error
    except sa.exc.SQLAlchemyError as error:
        raise failure(error) from error


@router.get("/v1/ingestion/submissions")
async def ingestion_list(request: Request) -> JSONResponse:
    return await listing(request, "ingestion")


@router.get("/v1/ingestion/submissions/{submission_id}")
async def ingestion_detail(request: Request, submission_id: str) -> JSONResponse:
    identity(submission_id)
    if request.query_params:
        raise HTTPException(422, "Invalid ingestion query")
    try:
        info = await asyncio.to_thread(ingestion.inspect_submission, engine(request), submission_id)
        return JSONResponse(jsonable_encoder(info))
    except DatasetError as error:
        raise HTTPException(404, "Ingestion submission not found") from error
    except sa.exc.SQLAlchemyError as error:
        raise failure(error) from error


@router.get("/v1/research/runs")
async def research_list(request: Request) -> JSONResponse:
    return await listing(request, "research")


@router.get("/v1/copilot/requests")
async def copilot_list(request: Request) -> JSONResponse:
    return await listing(request, "copilot")
