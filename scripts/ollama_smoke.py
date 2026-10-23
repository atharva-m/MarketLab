"""Validate an already installed Ollama model; this script never pulls models."""

import argparse
import ctypes
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict


class SmokeAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"]
    value: Literal[2]


class MemoryStatus(ctypes.Structure):
    dwLength: int
    ullTotalPhys: int
    ullAvailPhys: int
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def host_memory() -> dict[str, int | None]:
    """Best effort Windows physical RAM snapshot, independent of model allocation."""
    result: dict[str, int | None] = {"total_bytes": None, "available_bytes": None}
    if sys.platform == "win32":
        try:
            memory = MemoryStatus()
            memory.dwLength = ctypes.sizeof(memory)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
                result = {
                    "total_bytes": memory.ullTotalPhys,
                    "available_bytes": memory.ullAvailPhys,
                }
        except (AttributeError, OSError):
            pass
    return result


def check_model(client: httpx.Client, model: str) -> dict[str, Any]:
    def get(path: str) -> dict[str, Any]:
        response = client.get(path)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    version = get("/api/version")["version"]
    tags = get("/api/tags")["models"]
    normalized = model if ":" in model else f"{model}:latest"
    installed = next((tag for tag in tags if tag.get("name") in {model, normalized}), None)
    if installed is None:
        raise ValueError(
            f"Model {model!r} is not installed; install it explicitly before this test"
        )
    response = client.post("/api/show", json={"model": model})
    response.raise_for_status()
    metadata = response.json()
    quantization = metadata.get("details", {}).get("quantization_level")
    if normalized == "qwen3.5:4b-q8_0" and quantization != "Q8_0":
        raise ValueError(f"Expected Q8_0 quantization, received {quantization!r}")
    memory_before = host_memory()
    started = time.perf_counter()
    response = client.post(
        "/api/chat",
        json={
            "model": model,
            "stream": False,
            "think": False,
            "format": SmokeAnswer.model_json_schema(),
            "messages": [
                {
                    "role": "user",
                    "content": 'Return only JSON with status="ok" and value=2. What is 1+1?',
                }
            ],
            "options": {"temperature": 0, "num_predict": 256, "num_ctx": 8192},
            "keep_alive": "5m",
        },
    )
    elapsed = time.perf_counter() - started
    memory_after = host_memory()
    response.raise_for_status()
    completion = response.json()
    answer = SmokeAnswer.model_validate_json(completion["message"]["content"])
    if completion.get("done") is not True:
        raise ValueError("Ollama returned an unfinished completion")
    loaded = get("/api/ps").get("models", [])
    memory: dict[str, Any] = next(
        (item for item in loaded if item.get("name") in {model, normalized}), {}
    )
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "status": "passed",
        "ollama_version": version,
        "model": installed["name"],
        "digest": installed["digest"],
        "quantization": quantization,
        "parameter_size": metadata.get("details", {}).get("parameter_size"),
        "model_file_bytes": installed.get("size"),
        "latency_seconds": round(elapsed, 4),
        "total_duration_ns": completion.get("total_duration"),
        "load_duration_ns": completion.get("load_duration"),
        "prompt_eval_count": completion.get("prompt_eval_count"),
        "eval_count": completion.get("eval_count"),
        "eval_duration_ns": completion.get("eval_duration"),
        "memory": {
            "source": "ollama_api_ps",
            "loaded_size_bytes": memory.get("size"),
            "vram_bytes": memory.get("size_vram"),
            "context_length": memory.get("context_length"),
            "host_physical_before": memory_before,
            "host_physical_after": memory_after,
        },
        "validated_response": answer.model_dump(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen3.5:4b-q8_0")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        with httpx.Client(base_url=args.url, timeout=args.timeout) as client:
            record = check_model(client, args.model)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "failed",
            "model": args.model,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    encoded = json.dumps(record, indent=2)
    print(encoded)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    return 0 if record["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
