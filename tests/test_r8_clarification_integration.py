"""Real database clarification state/replay bounds with explicitly mocked inference."""

import pytest
from test_copilot import INTENT, candidate
from test_copilot_integration import FakeModel, ready
from test_copilot_integration import copilot_engine as copilot_engine
from test_copilot_integration import research_engine as research_engine

from marketlab.research.spec import ResearchError

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_five_answer_rounds_no_sixth_and_each_key_replays(copilot_engine, tmp_path):
    partial = {key: value for key, value in INTENT.items() if key != "symbols"}
    model = FakeModel(result=candidate(partial))
    service, _, body = ready(copilot_engine, tmp_path, model)
    body["context"].pop("symbols")
    request_id, _, _ = await service.create(body, "r8-round-bound")
    try:
        assert await service.work(1, request_id) == 1
        for revision in range(5):
            state = service.inspect(request_id)
            assert state["current_revision"] == revision
            assert state["outcome"] == "needs_clarification" and state["run_id"] is None
            answer = {
                "schema": "copilot-answer-v1",
                "expected_revision": revision,
                "text": "I still have not chosen an asset.",
                "context": {},
            }
            key = f"r8-round-{revision}"
            assert await service.answer(request_id, answer, key) == (
                request_id,
                revision + 1,
                False,
            )
            assert await service.answer(request_id, answer, key) == (request_id, revision + 1, True)
            with pytest.raises(ResearchError) as stale:
                await service.answer(request_id, answer, key + "-stale")
            assert stale.value.status == 409
            assert await service.work(1, request_id) == 1
        state = service.inspect(request_id)
        assert state["current_revision"] == 5 and len(state["revisions"]) == 6
        assert state["run_id"] is None and state["outcome"] == "needs_clarification"
        with pytest.raises(ResearchError) as bound:
            await service.answer(request_id, {**answer, "expected_revision": 5}, "r8-sixth")
        assert bound.value.status == 422
        assert service.inspect(request_id) == state
        with pytest.raises(ResearchError) as stale_shaped:
            await service.answer(
                request_id, {**answer, "expected_revision": 4}, "r8-sixth-valid-shape"
            )
        assert stale_shaped.value.status == 409
        assert service.inspect(request_id) == state
        assert model.calls == 6
        assert all(row["attempt_count"] == row["model_calls"] == 1 for row in state["revisions"])
    finally:
        await service.research.close()
        await service.research.bars.close()
