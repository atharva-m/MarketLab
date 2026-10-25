"""Real Ollama evaluation of the frozen R5 corpus on owned local resources.

No mocked model, relaxed spec matching or patched retry gates are used. Numerical
execution is deliberately left queued: evaluation checks validated submission.
"""

import argparse
import asyncio
import json
import platform
import time
from pathlib import Path
from typing import Any

import httpx
import sqlalchemy as sa
from r5_acceptance import (
    BASE,
    DIGEST,
    MODEL,
    ROOT,
    expected_spec,
    finish_copilot,
    owned_settings,
    restore,
    save,
)

from marketlab.analytics.bars import BarService
from marketlab.copilot.model import Ollama
from marketlab.copilot.service import CopilotService
from marketlab.datasets.source import file_hash
from marketlab.research import store as research_store
from marketlab.research.service import ResearchService, execution_identity
from marketlab.research.spec import ResearchSpec


async def live_failures(prefix: str) -> None:
    """Measure real local failure isolation without stopping any service."""
    settings = owned_settings()
    engine = sa.create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
    records = await asyncio.to_thread(restore, engine)
    corpus = json.loads(
        await asyncio.to_thread(Path("tests/fixtures/r5_prompts.json").read_text, encoding="utf-8")
    )
    case = corpus["cases"][0]
    bars = BarService(engine, ROOT, settings.redis_url.get_secret_value())
    research = ResearchService(bars)
    unavailable = CopilotService(research, Ollama("http://127.0.0.1:11436", MODEL, DIGEST))
    body = {
        "schema": "copilot-request-v1",
        "text": case["text"],
        "context": case["context"],
        "dataset_versions": sorted(r["dataset_version_id"] for r in records),
    }
    evidence: dict[str, Any] = {
        "status": "running",
        "execution": research.execution,
        "peak_memory": "unmeasured",
        "model_url_unavailable": "http://127.0.0.1:11436",
        "checks": {},
    }
    output = BASE / f"{prefix}-live-failures.json"
    try:
        request_id, _, _ = await unavailable.create(body, prefix + "-outage")
        await unavailable.work(1, request_id)
        failed = unavailable.inspect(request_id)
        assert failed["run_id"] is None and failed["outcome"] != "submitted"
        evidence["checks"]["outage_initial"] = failed
        # A real manual numerical run completes while the model endpoint is unreachable.
        spec = ResearchSpec.create(expected_spec(case["expected_intent"], records))
        run_id, _ = await research.submit(spec, prefix + "-manual-outage")
        assert await research.work(1, run_id) == 1
        state = research.inspect(run_id)
        assert state["state"] == "succeeded", state
        result, digest = research.read(run_id, "results")
        summary, cache = await research.summary(run_id)
        assert result["schema"] == "research-results-v1"
        assert summary["schema"] == "research-summary-v1"
        evidence["checks"]["manual_during_outage"] = {
            "run_id": run_id,
            "state": state["state"],
            "results_sha256": digest,
            "summary_cache": cache,
        }
        terminal = await finish_copilot(unavailable, request_id)
        assert terminal["state"] == "failed" and terminal["run_id"] is None
        assert terminal["revisions"][-1]["model_calls"] <= 2
        evidence["checks"]["outage_terminal"] = terminal
        save(output, evidence)

        model_turn = dict(body)
        model_turn["dataset_versions"] = []
        slow = Ollama(settings.ollama_url, MODEL, DIGEST)
        slow.timeout = 0.5
        started = time.perf_counter()
        try:
            await slow.infer([model_turn])
        except (TimeoutError, httpx.TimeoutException) as error:
            evidence["checks"]["real_timeout"] = {
                "exception": type(error).__name__,
                "seconds": time.perf_counter() - started,
                "configured_deadline": slow.timeout,
            }
        else:
            raise AssertionError("Real model timeout probe unexpectedly completed")

        dispatched = asyncio.Event()

        class ObservedOllama(Ollama):
            async def bounded(
                self, client: httpx.AsyncClient, method: str, path: str, **kwargs: Any
            ) -> Any:
                if method == "POST" and path == "/api/chat":
                    dispatched.set()
                return await super().bounded(client, method, path, **kwargs)

        log = BASE / "ollama-stderr.log"
        before_log = await asyncio.to_thread(log.read_text, encoding="utf-8", errors="replace")
        probe = ObservedOllama(settings.ollama_url, MODEL, DIGEST)
        task = asyncio.create_task(probe.infer([model_turn]))
        await asyncio.wait_for(dispatched.wait(), timeout=15)
        await asyncio.sleep(0.25)
        cancel_started = time.perf_counter()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            evidence["checks"]["client_cancellation"] = {
                "cancelled": True,
                "seconds_to_return": time.perf_counter() - cancel_started,
            }
        else:
            raise AssertionError("Inference did not propagate task cancellation")
        await asyncio.sleep(2)
        after_log = await asyncio.to_thread(log.read_text, encoding="utf-8", errors="replace")
        delta = (
            after_log[len(before_log) :]
            if after_log.startswith(before_log)
            else "Log rotated; no reliable delta"
        )
        async with httpx.AsyncClient(trust_env=False, timeout=5) as client:
            response = await client.get(settings.ollama_url + "/api/ps")
            response.raise_for_status()
            processes = response.json()
        evidence["checks"]["server_after_cancellation"] = {
            "log_delta": delta[-8192:],
            "loaded_models": processes,
            "immediate_generation_stop": (
                "Not established by loaded-model inventory; inspect recorded server log"
            ),
            "observation_delay_seconds": 2,
        }
        assert execution_identity() == evidence["execution"], (
            "Source changed during live acceptance"
        )
        evidence["status"] = "passed"
    except BaseException as error:
        evidence.update(status="failed", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        save(output, evidence)
        await research.close()
        await bars.close()
        engine.dispose()


async def main(prefix: str, selected: list[str] | None = None) -> None:
    settings = owned_settings()
    engine = sa.create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
    records = await asyncio.to_thread(restore, engine)
    corpus = Path("tests/fixtures/r5_prompts.json")
    cases = json.loads(await asyncio.to_thread(corpus.read_text, encoding="utf-8"))["cases"]
    assert len(cases) == 60
    assert {
        category: sum(c["category"] == category for c in cases)
        for category in {c["category"] for c in cases}
    } == {"clear": 20, "ambiguous_invalid": 20, "adversarial_unsupported": 20}
    if selected:
        cases = [case for case in cases if case["id"] in selected]
        assert len(cases) == len(selected)
    bars = BarService(engine, ROOT, settings.redis_url.get_secret_value())
    research = ResearchService(bars)
    service = CopilotService(research, Ollama(settings.ollama_url, MODEL, DIGEST))
    output = BASE / f"{prefix}-model-evaluation.json"
    evidence: dict[str, Any] = {
        "status": "running",
        "corpus_sha256": file_hash(corpus),
        "hardware": platform.platform(),
        "peak_memory": "unmeasured",
        "model": MODEL,
        "expected_digest": DIGEST,
        "execution": research.execution,
        "partial": bool(selected),
        "cases": [],
    }
    began = time.perf_counter()
    try:
        for case in cases:
            if await asyncio.to_thread((BASE / f"{prefix}-pause").exists):
                evidence.update(
                    status="interrupted_provisional",
                    limitation="Stopped at case boundary by explicit acceptance pause file",
                    seconds=time.perf_counter() - began,
                )
                return
            started = time.perf_counter()
            body = {
                "schema": "copilot-request-v1",
                "text": case["text"],
                "dataset_versions": sorted(r["dataset_version_id"] for r in records),
                "context": case["context"],
            }
            request_id, _, _ = await service.create(body, f"{prefix}-{case['id']}")
            info = await finish_copilot(service, request_id)
            latest = info["revisions"][-1]
            actual_spec = latest["spec"]
            expected = (
                expected_spec(case["expected_intent"], records)
                if case["category"] == "clear"
                else None
            )
            correct = (
                info["outcome"] == "submitted" and actual_spec == expected
                if expected
                else info["outcome"] in case["expected_outcomes"]
            )
            with engine.connect() as connection:
                handoffs = connection.scalar(
                    sa.select(sa.func.count())
                    .select_from(research_store.submissions)
                    .where(research_store.submissions.c.idempotency_key == "copilot." + request_id)
                )
            assert handoffs == (1 if info["run_id"] is not None else 0)
            item = {
                "id": case["id"],
                "category": case["category"],
                "request_id": request_id,
                "state": info["state"],
                "outcome": info["outcome"],
                "run_id": info["run_id"],
                "canonical_spec_correct": bool(correct),
                "expected_spec": expected,
                "actual_spec": actual_spec,
                "questions": latest["questions"],
                "attempts": latest["attempts"],
                "model_calls": latest["model_calls"],
                "provenance": latest["provenance"],
                "seconds": time.perf_counter() - started,
                "error": latest["error"],
            }
            evidence["cases"].append(item)
            save(output, evidence)
            print(
                json.dumps(
                    {
                        k: item[k]
                        for k in ("id", "category", "outcome", "canonical_spec_correct", "seconds")
                    }
                ),
                flush=True,
            )
        assert execution_identity() == evidence["execution"], "Source changed during evaluation"
        clear = [item for item in evidence["cases"] if item["category"] == "clear"]
        negative = [item for item in evidence["cases"] if item["category"] != "clear"]
        clear_correct = sum(item["canonical_spec_correct"] for item in clear)
        invalid_executions = sum(item["run_id"] is not None for item in negative)
        evidence.update(
            clear_correct=clear_correct,
            clear_total=len(clear),
            invalid_adversarial_executions=invalid_executions,
            negative_total=len(negative),
            clarification_or_refusal_correct=sum(
                item["canonical_spec_correct"] for item in negative
            ),
            seconds=time.perf_counter() - began,
        )
        passed = invalid_executions == 0 and (
            clear_correct >= 18 if not selected else clear_correct == len(clear)
        )
        evidence["status"] = "passed" if passed else "failed"
        assert passed, "Actual model evaluation did not meet R5 acceptance gates"
    except BaseException as error:
        evidence.update(
            status="failed",
            error_type=type(error).__name__,
            error=str(error),
            seconds=time.perf_counter() - began,
        )
        raise
    finally:
        save(output, evidence)
        await research.close()
        await bars.close()
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-prefix", required=True)
    parser.add_argument("--case", action="append", dest="cases")
    parser.add_argument("--live-failures", action="store_true")
    args = parser.parse_args()
    if args.live_failures:
        asyncio.run(live_failures(args.key_prefix))
    else:
        asyncio.run(main(args.key_prefix, args.cases))
