import asyncio
from pathlib import Path

import pytest

from marketlab.health import Check, probe_storage, readiness


async def up() -> None:
    pass


async def down() -> None:
    raise ConnectionError("do not expose postgresql://secret:password@server")


@pytest.mark.parametrize("optional", ["redis", "ollama"])
async def test_optional_outage_is_degraded(optional: str) -> None:
    checks: dict[str, tuple[bool, Check]] = {
        "postgresql": (True, up),
        "storage": (True, up),
        "redis": (False, up),
        "ollama": (False, up),
    }
    checks[optional] = (False, down)
    result = await readiness(checks, 0.1)
    assert result.status == "degraded"
    assert result.checks[optional].error == "ConnectionError"
    assert "secret" not in result.model_dump_json()


@pytest.mark.parametrize("critical", ["postgresql", "storage"])
async def test_critical_outage_is_not_ready(critical: str) -> None:
    result = await readiness({critical: (True, down), "ollama": (False, down)}, 0.1)
    assert result.status == "not_ready"


async def test_slow_dependency_is_bounded() -> None:
    async def slow() -> None:
        await asyncio.sleep(10)

    async with asyncio.timeout(1):
        result = await readiness({"ollama": (False, slow)}, 0.01)
    assert result.status == "degraded"
    assert result.checks["ollama"].error == "TimeoutError"


def test_storage_readback_cleans_probe(tmp_path: Path) -> None:
    storage = tmp_path / "nested"
    probe_storage(storage)
    assert list(storage.iterdir()) == []


def test_storage_cannot_use_file_as_directory(tmp_path: Path) -> None:
    storage = tmp_path / "file"
    storage.write_text("occupied")
    with pytest.raises(OSError):
        probe_storage(storage)
