import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import httpx
import pytest
from pydantic import ValidationError


@pytest.fixture
def smoke() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / "ollama_smoke.py"
    spec = importlib.util.spec_from_file_location("ollama_smoke", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def responses(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/version":
        return httpx.Response(200, json={"version": "test"})
    if request.url.path == "/api/tags":
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "qwen3.5:4b-q8_0",
                        "digest": "sha256:test",
                        "size": 42,
                    }
                ]
            },
        )
    if request.url.path == "/api/show":
        return httpx.Response(200, json={"details": {"quantization_level": "Q8_0"}})
    if request.url.path == "/api/chat":
        payload = json.loads(request.content)
        assert payload["stream"] is False
        assert payload["think"] is False
        assert payload["options"]["num_ctx"] == 8192
        assert "properties" in payload["format"]
        return httpx.Response(
            200,
            json={
                "done": True,
                "message": {"content": '{"status":"ok","value":2}'},
            },
        )
    if request.url.path == "/api/ps":
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "qwen3.5:4b-q8_0",
                        "size": 100,
                        "size_vram": 50,
                    }
                ]
            },
        )
    raise AssertionError(f"Unexpected call: {request.method} {request.url}")


def test_ollama_schema_validation_and_telemetry(smoke: ModuleType) -> None:
    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(responses)) as client:
        result = smoke.check_model(client, "qwen3.5:4b-q8_0")
    assert result["status"] == "passed"
    assert result["digest"] == "sha256:test"
    assert result["quantization"] == "Q8_0"
    assert result["memory"]["vram_bytes"] == 50
    assert result["validated_response"] == {"status": "ok", "value": 2}


def test_smoke_rejects_wrong_model_quantization(smoke: ModuleType) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"details": {"quantization_level": "Q4_K_M"}})
        return responses(request)

    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="Expected Q8_0"):
            smoke.check_model(client, "qwen3.5:4b-q8_0")


def test_smoke_rejects_invalid_completion(smoke: ModuleType) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            return httpx.Response(
                200,
                json={
                    "done": True,
                    "message": {"content": '{"status":"ok","value":3}'},
                },
            )
        return responses(request)

    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValidationError):
            smoke.check_model(client, "qwen3.5:4b-q8_0")


def test_missing_model_never_pulls(smoke: ModuleType) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": []})
        return responses(request)

    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="not installed"):
            smoke.check_model(client, "qwen3.5:4b-q8_0")
