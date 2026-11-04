"""The fixed model chooses bounded wording, never numerical facts or prose."""

from typing import Any

from marketlab.copilot.v2.model import DIGEST, V2Model

from .spec import draft, schema

PROMPT = """Select wording for a grounded descriptive research memo.
Return only memo-draft-v2 JSON. Exactly three paragraph objects in order:
scope, findings, limitations. Each has claim and wording only.
Choose all three required claim IDs. Wording is standard or measured.
No prose, numbers, tools, HTML, additional claims, causes, forecasts or advice.
The application alone resolves validated placeholders into pinned facts.
"""


class MemoModel(V2Model):
    @staticmethod
    def content(source: dict[str, Any]) -> dict[str, Any]:
        return {"claims": source["claims"], "instruction": "Choose all three claims in order."}

    def prepare(self, source: dict[str, Any]) -> dict[str, Any]:
        return self.preflight(self.content(source), schema(), PROMPT)

    async def generate(
        self, source: dict[str, Any], pinned: str = DIGEST
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        return await self.complete(self.content(source), schema(), PROMPT, "memo", draft, pinned)
