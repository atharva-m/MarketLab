import asyncio
import os
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

Check = Callable[[], Awaitable[None]]


class CheckResult(BaseModel):
    required: bool
    status: Literal["up", "down"]
    error: str | None = None


class Readiness(BaseModel):
    status: Literal["ready", "degraded", "not_ready"]
    checks: dict[str, CheckResult]


def probe_storage(path: Path) -> None:
    """Verify actual writes and reads; permissions alone do not prove usable storage."""
    path.mkdir(parents=True, exist_ok=True)
    payload = os.urandom(32)
    with tempfile.NamedTemporaryFile(dir=path, prefix=".readiness-", delete=False) as handle:
        probe = Path(handle.name)
        try:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            handle.close()
            probe.unlink(missing_ok=True)
            raise
    try:
        if probe.read_bytes() != payload:
            raise OSError("storage readback mismatch")
    finally:
        probe.unlink(missing_ok=True)


def build_checks(
    engine: AsyncEngine, redis: Redis, client: httpx.AsyncClient, storage: Path
) -> dict[str, tuple[bool, Check]]:
    async def postgres_check() -> None:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def redis_check() -> None:
        await redis.ping()

    async def ollama_check() -> None:
        response = await client.get("/api/tags")
        response.raise_for_status()
        if not isinstance(response.json().get("models"), list):
            raise ValueError("invalid Ollama tags response")

    async def storage_check() -> None:
        await asyncio.to_thread(probe_storage, storage)

    return {
        "postgresql": (True, postgres_check),
        "storage": (True, storage_check),
        "redis": (False, redis_check),
        "ollama": (False, ollama_check),
    }


async def readiness(checks: dict[str, tuple[bool, Check]], check_timeout: float) -> Readiness:
    async def run(name: str, required: bool, check: Check) -> tuple[str, CheckResult]:
        try:
            async with asyncio.timeout(check_timeout):
                await check()
            return name, CheckResult(required=required, status="up")
        except Exception as exc:
            # Never expose connection strings or dependency responses in health output.
            return name, CheckResult(required=required, status="down", error=type(exc).__name__)

    results = dict(await asyncio.gather(*(run(k, *v) for k, v in checks.items())))
    failed = [result for result in results.values() if result.status == "down"]
    status: Literal["ready", "degraded", "not_ready"] = "ready"
    if any(result.required for result in failed):
        status = "not_ready"
    elif failed:
        status = "degraded"
    return Readiness(status=status, checks=results)
