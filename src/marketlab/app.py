from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.concurrency import run_in_threadpool

from marketlab import __version__
from marketlab.analytics import BarService
from marketlab.analytics.routes import router as bar_router
from marketlab.config import Settings
from marketlab.health import build_checks, readiness
from marketlab.observability import RequestMetrics, RequestMiddleware, configure_logging
from marketlab.trades.routes import router as trade_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging()
    metrics = RequestMetrics()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_async_engine(
            settings.sqlalchemy_url,
            pool_pre_ping=True,
            pool_timeout=settings.database_connect_timeout_seconds,
            connect_args=settings.database_connect_args,
        )
        redis = Redis.from_url(settings.redis_url.get_secret_value())
        # This lazy synchronous engine serves the existing week 3 service in worker threads.
        trade_engine = create_engine(
            settings.sqlalchemy_url,
            pool_pre_ping=True,
            pool_timeout=settings.database_connect_timeout_seconds,
            connect_args=settings.database_connect_args,
        )
        app.state.trade_engine = trade_engine
        app.state.bar_service = BarService(
            trade_engine,
            settings.storage_path,
            settings.redis_url.get_secret_value(),
            registry=metrics.registry,
        )
        async with httpx.AsyncClient(
            base_url=settings.ollama_url, timeout=settings.dependency_timeout_seconds
        ) as client:
            app.state.checks = build_checks(engine, redis, client, settings.storage_path)
            try:
                yield
            finally:
                await app.state.bar_service.close()
                await run_in_threadpool(trade_engine.dispose)
                await redis.aclose()
                await engine.dispose()

    app = FastAPI(title="Marketlab", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.metrics = metrics
    app.add_middleware(RequestMiddleware, metrics=metrics)
    app.include_router(trade_router)
    app.include_router(bar_router)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            {"detail": "Internal server error"},
            status_code=500,
            headers={"X-Request-ID": request.state.request_id},
        )

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "alive", "version": __version__}

    @app.get("/health/ready")
    @app.get("/health/dependencies")
    async def ready(request: Request) -> JSONResponse:
        result = await readiness(request.app.state.checks, settings.dependency_timeout_seconds)
        return JSONResponse(
            result.model_dump(), status_code=503 if result.status == "not_ready" else 200
        )

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics() -> Response:
        return Response(
            generate_latest(metrics.registry), headers={"Content-Type": CONTENT_TYPE_LATEST}
        )

    return app
