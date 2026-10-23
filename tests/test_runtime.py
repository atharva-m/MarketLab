import asyncio
import gc
import json
import socket
import threading
from pathlib import Path
from typing import NoReturn

import pytest
from uvicorn import Config

from marketlab.health import readiness


def test_container_loop_handles_dns_failure_after_readiness_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the shipped loop's cancellation with a DNS error arriving late."""
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()
    command = json.loads(
        next(line[4:] for line in dockerfile.splitlines() if line.startswith("CMD "))
    )
    loop_option = command[command.index("--loop") + 1]
    assert loop_option == "asyncio"
    loop_factory = Config("marketlab.app:create_app", loop=loop_option).get_loop_factory()
    dns_started = threading.Event()
    release_dns = threading.Event()
    dns_finished = threading.Event()

    def delayed_dns_failure(*args: object, **kwargs: object) -> NoReturn:
        dns_started.set()
        try:
            if not release_dns.wait(5):
                raise AssertionError("test did not release DNS lookup")
            raise socket.gaierror(socket.EAI_NONAME, "synthetic DNS failure")
        finally:
            dns_finished.set()

    monkeypatch.setattr(socket, "getaddrinfo", delayed_dns_failure)

    async def exercise() -> None:
        loop = asyncio.get_running_loop()
        unhandled = []
        loop.set_exception_handler(lambda _, context: unhandled.append(context))

        async def redis_connection() -> None:
            await asyncio.open_connection("synthetic-redis.invalid", 6379)

        # Warm up the executor so the timeout measures the lookup, not thread startup.
        await asyncio.to_thread(lambda: None)
        try:
            async with asyncio.timeout(2):
                result = await readiness({"redis": (False, redis_connection)}, 0.05)
            assert dns_started.is_set()
            assert not dns_finished.is_set()
            assert result.model_dump() == {
                "status": "degraded",
                "checks": {"redis": {"required": False, "status": "down", "error": "TimeoutError"}},
            }
        finally:
            release_dns.set()

        assert await asyncio.to_thread(dns_finished.wait, 2)
        # Flush completion callbacks and collect abandoned futures before checking.
        await asyncio.sleep(0)
        gc.collect()
        await asyncio.sleep(0)
        assert unhandled == []

    with asyncio.Runner(loop_factory=loop_factory) as runner:
        runner.run(exercise())
