import json
import logging
import re
import sys
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from prometheus_client import CollectorRegistry, Counter, Histogram
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("marketlab.requests")
REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,128}\Z")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        output: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        output.update(getattr(record, "fields", {}))
        return json.dumps(output, separators=(",", ":"))


def configure_logging() -> None:
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


class RequestMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "marketlab_http_requests_total",
            "Completed HTTP requests",
            ["method", "route", "status"],
            registry=self.registry,
        )
        self.duration = Histogram(
            "marketlab_http_request_duration_seconds",
            "HTTP request duration",
            ["method", "route"],
            registry=self.registry,
        )


class RequestMiddleware:
    def __init__(self, app: ASGIApp, metrics: RequestMetrics) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        supplied = headers.get(b"x-request-id", b"").decode("latin-1")
        request_id = supplied if REQUEST_ID.fullmatch(supplied) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.perf_counter()
        status = 500

        async def capture(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                response_headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ]
                message["headers"] = [*response_headers, (b"x-request-id", request_id.encode())]
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            elapsed = time.perf_counter() - started
            route = getattr(scope.get("route"), "path", "unmatched")
            method = scope["method"]
            self.metrics.requests.labels(method, route, str(status)).inc()
            self.metrics.duration.labels(method, route).observe(elapsed)
            logger.info(
                "http_request",
                extra={
                    "fields": {
                        "request_id": request_id,
                        "method": method,
                        "path": scope["path"],
                        "status": status,
                        "duration_ms": round(elapsed * 1000, 3),
                    }
                },
            )
