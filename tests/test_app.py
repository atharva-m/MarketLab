import io
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from marketlab.app import create_app
from marketlab.config import Settings
from marketlab.observability import REQUEST_ID, JsonFormatter, logger


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings(storage_path=tmp_path, _env_file=None))
    async with app.router.lifespan_context(app):

        async def up() -> None:
            pass

        async def down() -> None:
            raise ConnectionError("private")

        app.state.checks = {
            "postgresql": (True, up),
            "storage": (True, up),
            "redis": (False, down),
            "ollama": (False, down),
        }
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as session:
            yield session


async def test_live_is_independent_of_dependencies(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


async def test_ready_and_dependencies_remain_available_when_optional_down(
    client: httpx.AsyncClient,
) -> None:
    for endpoint in ("/health/ready", "/health/dependencies"):
        response = await client.get(endpoint)
        assert response.status_code == 200
        assert response.json()["status"] == "degraded"


async def test_json_request_log_and_request_id(client: httpx.AsyncClient) -> None:
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    try:
        response = await client.get("/health/live", headers={"X-Request-ID": "test-123"})
    finally:
        logger.removeHandler(handler)
    assert response.headers["X-Request-ID"] == "test-123"
    record = json.loads(output.getvalue())
    assert record["request_id"] == "test-123"
    assert record["status"] == 200
    assert record["duration_ms"] >= 0


async def test_bad_id_is_replaced_and_404_is_observed(client: httpx.AsyncClient) -> None:
    response = await client.get("/missing", headers={"X-Request-ID": "invalid id"})
    assert response.status_code == 404
    assert REQUEST_ID.fullmatch(response.headers["X-Request-ID"])
    metrics = await client.get("/metrics")
    assert 'route="unmatched",status="404"' in metrics.text
    assert "marketlab_http_request_duration_seconds" in metrics.text


async def test_unhandled_error_retains_request_id_and_is_observed(tmp_path: Path) -> None:
    app = create_app(Settings(storage_path=tmp_path, _env_file=None))

    @app.get("/test-error")
    async def failure() -> None:
        raise RuntimeError("private failure details")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        response = await client.get("/test-error", headers={"X-Request-ID": "error-123"})
        metrics = await client.get("/metrics")
    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "error-123"
    assert response.json() == {"detail": "Internal server error"}
    assert 'route="/test-error",status="500"' in metrics.text


@given(st.text())
def test_json_formatter_escapes_untrusted_text(value: str) -> None:
    record = logging.LogRecord("test", logging.INFO, "", 1, "http_request", (), None)
    record.fields = {"request_id": value}
    encoded = JsonFormatter().format(record)
    assert "\n" not in encoded
    assert json.loads(encoded)["request_id"] == value


def test_settings_hides_credentials_and_rejects_wrong_driver() -> None:
    settings = Settings(_env_file=None)
    assert "marketlab:marketlab" not in repr(settings)
    with pytest.raises(ValidationError):
        Settings(database_url="sqlite://", _env_file=None)


def test_separate_database_password_handles_url_delimiters() -> None:
    settings = Settings(database_password="a@b/#%:c", _env_file=None)
    assert settings.sqlalchemy_url.password == "a@b/#%:c"
