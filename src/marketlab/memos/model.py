"""Bounded local model selection of application-validated memo claims."""

import asyncio
import hashlib
import time
from typing import Any

import httpx

from marketlab.analytics.cache import canonical
from marketlab.copilot.model import ModelFailure, Ollama
from marketlab.research.spec import parse_json

from .spec import draft, schema

PROMPT = """Select wording for a grounded descriptive research memo.
Return only memo-draft-v1 JSON. Exactly three paragraphs in this order:
scope, findings, limitations. Each object has claim and wording only.
Use wording standard or measured. No prose, numbers, tools, HTML or other claims.
Application-owned claims and numeric placeholders are resolved after validation.
Never infer causes, predictions, recommendations or strategy performance.
"""


class MemoModel(Ollama):
    async def generate(
        self, source: dict[str, Any], pinned: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        # Values remain in application memory; model sees only approved claim structure.
        content = {"claims": source["claims"], "instruction": "Choose all three claims in order."}
        grammar = schema()
        if len(canonical(content)) + len(PROMPT.encode()) + len(canonical(grammar)) > 6000:
            raise ModelFailure("Memo context exceeds inference budget")
        started = time.perf_counter()
        settings = {"temperature": 0, "num_ctx": 8192, "num_predict": 2048}
        async with asyncio.timeout(self.timeout):
            async with httpx.AsyncClient(
                base_url=self.url,
                timeout=httpx.Timeout(self.timeout, connect=5),
                trust_env=False,
                follow_redirects=False,
                transport=httpx.AsyncHTTPTransport(retries=0),
            ) as client:
                version = await self.bounded(client, "GET", "/api/version")
                installed = await self.identify()
                if installed != pinned:
                    raise ModelFailure("Ollama model identity mismatch")
                response = await self.bounded(
                    client,
                    "POST",
                    "/api/chat",
                    json={
                        "model": self.model,
                        "stream": False,
                        "think": False,
                        "format": grammar,
                        "messages": [
                            {"role": "system", "content": PROMPT},
                            {"role": "user", "content": canonical(content).decode()},
                        ],
                        "options": settings,
                    },
                )
                raw = response.get("message", {}).get("content")
                if (
                    not isinstance(raw, str)
                    or len(raw.encode()) > 32768
                    or response.get("done") is not True
                ):
                    raise ModelFailure("Invalid Ollama memo completion")
                if await self.identify() != pinned:
                    raise ModelFailure("Ollama model identity changed")
        provenance = {
            "model": self.model,
            "model_digest": installed,
            "ollama_version": version.get("version"),
            "prompt_version": "memo-prompt-v1",
            "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
            "schema": "memo-draft-v1",
            "schema_sha256": hashlib.sha256(canonical(grammar)).hexdigest(),
            "settings": settings,
            "think": False,
            "input_sha256": hashlib.sha256(canonical(content)).hexdigest(),
            "response": raw,
            "response_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "done_reason": response.get("done_reason"),
            "latency_seconds": time.perf_counter() - started,
        }
        try:
            if response.get("done_reason") == "length":
                raise ModelFailure("Ollama completion token limit reached")
            return draft(parse_json(raw.encode())), provenance
        except Exception as error:
            raise ModelFailure("Invalid Ollama memo draft", provenance=provenance) from error
