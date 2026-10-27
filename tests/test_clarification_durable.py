"""Focused safety/provenance checks; actual durable acceptance uses real resources."""

import asyncio
import copy
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path("scripts").resolve()))
import clarification_durable as durable
import clarification_experiment as experiment

from marketlab.analytics.cache import canonical
from marketlab.copilot.model import PROMPT
from marketlab.copilot.spec import FIELD_ORDER, model_schema


def test_durable_evidence_serializes_nested_real_database_datetimes_exclusively(tmp_path):
    stamp = datetime(2026, 10, 27, 12, 34, 56, 123456, tzinfo=UTC)
    path = tmp_path / "snapshot.json"
    durable.write_new(
        path, {"revisions": [{"created_at": stamp, "attempts": [{"started_at": stamp}]}]}
    )
    result = json.loads(path.read_text())
    assert result["revisions"][0]["created_at"] == str(stamp)
    assert result["revisions"][0]["attempts"][0]["started_at"] == str(stamp)
    with pytest.raises(FileExistsError):
        durable.write_new(path, {"replace": True})


def test_all_frozen_histories_fit_both_native_and_actual_prompt_context_budgets():
    for case in experiment.cases():
        content = canonical(case["turns"])
        grammar = canonical(model_schema(case["turns"]))
        assert len(content) + len(grammar) + len(PROMPT.encode()) <= 6000
        assert len(content) + len(grammar) + len(durable.NULL_GUARD_PROMPT.encode()) <= 6000


def container(kind):
    internal, external = ("5432/tcp", "55443") if kind == "postgres" else ("6379/tcp", "56385")
    return {
        "Id": "f" * 64,
        "Name": "owned-" + kind,
        "Image": "sha256:owned",
        "Config": {
            "Image": "owned:pinned",
            "Labels": {"marketlab.clarification.owner": durable.OWNER},
        },
        "State": {"Running": True},
        "NetworkSettings": {"Ports": {internal: [{"HostIp": "127.0.0.1", "HostPort": external}]}},
    }


@pytest.mark.parametrize("kind", ["postgres", "redis"])
def test_container_guard_accepts_only_exact_owned_running_identity(kind):
    saved = container(kind)
    durable.container_identity(saved, saved, kind)
    for mutate in (
        lambda value: value.update(Id="a" * 64),
        lambda value: value["Config"]["Labels"].clear(),
        lambda value: value["State"].update(Running=False),
        lambda value: value["NetworkSettings"]["Ports"].update(
            {
                next(iter(value["NetworkSettings"]["Ports"])): [
                    {"HostIp": "0.0.0.0", "HostPort": "55443"}
                ]
            }
        ),
    ):
        changed = copy.deepcopy(saved)
        mutate(changed)
        with pytest.raises(RuntimeError):
            durable.container_identity(changed, saved, kind)


async def test_adapter_uses_native_infer_and_preserves_actual_request_provenance(
    tmp_path, monkeypatch
):
    turns = experiment.cases()[0]["turns"]
    supplied = turns[0]["context"]
    raw = {
        "schema": "copilot-interpretation-v1",
        "outcome": "candidate",
        "intent": {name: supplied.get(name) for name in FIELD_ORDER},
        "evidence": {name: "context" if name in supplied else None for name in FIELD_ORDER},
        "unresolved": ["symbols"],
        "reason": "missing_fields",
    }
    observed = []

    async def handle(request):
        observed.append(request)
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "fixture"})
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": durable.MODEL_9B, "digest": durable.PIN}]}
            )
        return httpx.Response(
            200,
            json={
                "message": {"content": json.dumps(raw)},
                "done": True,
                "done_reason": "stop",
                "eval_count": 123,
            },
        )

    original_client = httpx.AsyncClient

    def client(**kwargs):
        kwargs["transport"] = httpx.MockTransport(handle)
        return original_client(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    identity = durable.interpreter_identity()
    model = durable.ExperimentalOllama("http://127.0.0.1:11442", tmp_path, identity)
    parsed, provenance = await model.infer(turns, durable.PIN)
    post = next(request for request in observed if request.method == "POST")
    payload = json.loads(post.content)
    assert payload["messages"][0]["content"] == durable.NULL_GUARD_PROMPT
    assert payload["messages"][1]["content"] == canonical(turns).decode()
    assert payload["format"] == model_schema(turns)
    assert payload["think"] is False and payload["options"] == durable.OPTIONS
    assert model.timeout == 120 and model.calls == 1
    assert provenance["settings"] == durable.OPTIONS
    assert provenance["experimental_interpreter"] == identity
    assert provenance["prompt_version"].startswith("experiment-null-guard-")
    assert "symbols" not in parsed["intent"]
    assert (
        json.loads((tmp_path / "model-000-response.json").read_text())["response"]["eval_count"]
        == 123
    )


async def test_native_cancellation_retains_incomplete_invocation_without_upstream_claim(tmp_path):
    async def handle(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json={})

    model = durable.ExperimentalOllama(
        "http://127.0.0.1:11442", tmp_path, durable.interpreter_identity()
    )
    payload = experiment.payloads("original_false", experiment.cases()[0]["turns"])[0]
    payload["model"] = durable.MODEL_9B
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:11442", transport=httpx.MockTransport(handle)
    ) as client:
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.01):
                await model.bounded(client, "POST", "/api/chat", json=payload)
    failed = json.loads((tmp_path / "model-000-failed.json").read_text())
    assert failed["error_type"] == "CancelledError" and failed["client_cancellation_only"] is True


async def test_catalog_drift_is_rejected_before_ownership_or_database_access(tmp_path, monkeypatch):
    monkeypatch.setattr(durable, "BASE", tmp_path)
    monkeypatch.setattr(durable, "execution_identity", lambda: {})
    monkeypatch.setattr(durable, "interpreter_identity", lambda: {})
    monkeypatch.setattr(durable, "file_hash", lambda path: "current")
    monkeypatch.setattr(
        durable, "owned_settings", lambda base: pytest.fail("Must not reach database setup")
    )
    durable.write_new(
        tmp_path / "plan.json",
        {
            "runtime": {},
            "interpreter": {},
            "fixture_sha256": "current",
            "catalog_snapshot_sha256": "different",
        },
    )
    with pytest.raises(RuntimeError, match="drift"):
        await durable.execute(tmp_path)
