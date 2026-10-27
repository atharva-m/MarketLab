"""R8 owned recovery adapters preserving historical acceptance scripts.

Historical R5/R6 harnesses have fixed evidence roots/owners. Only those harness
bindings change here; production retry/lease/fencing/model behavior is untouched.
"""

import argparse
import asyncio
import hashlib
import importlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
import types
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
from r8_common import (
    BASE,
    DIGEST,
    MODEL,
    OWNER,
    PROFILE,
    ROOT,
    Invocation,
    Sampler,
    engine_for,
    owned_settings,
    save,
    validate_prefix,
)


def operational_adapter() -> types.ModuleType:
    path = Path("scripts/r6_operational.py")
    original = path.read_text(encoding="utf-8")
    substitutions = {"marketlab.r6.owner": "marketlab.r8.owner", "r6-20261025": OWNER}
    expected_sites = {"marketlab.r6.owner": 8, "r6-20261025": 2}
    if any(original.count(before) != expected_sites[before] for before in substitutions):
        raise RuntimeError("Historical operational harness identity sites changed")
    adapted = original
    for before, after in substitutions.items():
        adapted = adapted.replace(before, after)
    module = types.ModuleType("r8_operational_adapter")
    module.__file__ = str(path.resolve())
    exec(compile(adapted, str(path), "exec"), module.__dict__)
    module.BASE = BASE
    module.MODEL, module.DIGEST = MODEL, DIGEST
    module.owned_settings = owned_settings
    module.save = save
    module.adapter_provenance = {
        "historical_path": str(path),
        "original_sha256": hashlib.sha256(original.encode()).hexdigest(),
        "adapted_sha256": hashlib.sha256(adapted.encode()).hexdigest(),
        "identity_substitutions": substitutions,
        "binding_substitutions": ["BASE", "MODEL", "DIGEST", "owned_settings", "save"],
        "assertions": "Historical assertions retained; exact owner checks target R8",
    }
    return module


def durability_adapter(name: str) -> types.ModuleType:
    if name not in {"r5_acceptance", "r6_acceptance"}:
        raise ValueError("Unsupported historical harness")
    module = importlib.import_module(name)
    module.BASE, module.ROOT = BASE, ROOT
    module.MODEL, module.DIGEST = MODEL, DIGEST
    module.owned_settings = owned_settings
    module.save = save
    if name == "r6_acceptance":
        module.engine_for = engine_for
    module.adapter_provenance = {
        "historical_path": "scripts/" + name + ".py",
        "original_sha256": hashlib.sha256(Path("scripts", name + ".py").read_bytes()).hexdigest(),
        "binding_substitutions": ["BASE", "ROOT", "MODEL", "DIGEST", "owned_settings", "save"]
        + (["engine_for"] if name == "r6_acceptance" else []),
        "assertions": "Historical native-time assertions unchanged; no source replacement",
    }
    return module


class TimeoutEndpoint:
    """Owned chat blackhole; real identity GETs forward only to owned Ollama."""

    def __init__(self, url: str):
        if url != PROFILE.ollama_url:
            raise ValueError("Timeout proxy requires owned Ollama")
        self.stop, self.dispatch = threading.Event(), threading.Event()
        endpoint = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path not in {"/api/tags", "/api/version"}:
                    self.send_error(404)
                    return
                with httpx.Client(trust_env=False, follow_redirects=False, timeout=5) as client:
                    response = client.get(url + self.path)
                self.send_response(response.status_code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(response.content)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                if self.path != "/api/chat" or not 0 < length <= 32768:
                    self.send_error(422)
                    return
                self.rfile.read(length)
                endpoint.dispatch.set()
                endpoint.stop.wait(150)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.url = "http://127.0.0.1:" + str(self.server.server_port)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


async def native_timeout(prefix: str, evidence: Invocation) -> None:
    """Normal inference CLI + unchanged120s model deadline against owned blackhole."""
    from r8_benchmark import isolated

    from marketlab.analytics.bars import BarService
    from marketlab.memos.model import MemoModel
    from marketlab.memos.service import MemoService
    from marketlab.research.service import ResearchService

    adapter = operational_adapter()
    evidence.data["adapter"] = adapter.adapter_provenance
    with isolated(prefix) as (settings, engine, root, environment):
        spec = await asyncio.to_thread(adapter.fixture, engine, root)
        bars = BarService(engine, root, settings.redis_url.get_secret_value())
        research = ResearchService(bars)
        process = None
        try:
            run_id = await adapter.successful(research, spec, prefix + "-numerical")
            summary, summary_hash = research.read(run_id, "summary")
            with TimeoutEndpoint(settings.ollama_url) as endpoint:
                with socket.socket() as reserve:
                    reserve.bind(("127.0.0.1", 59110))
                environment.update(
                    MARKETLAB_OLLAMA_URL=endpoint.url,
                    MARKETLAB_COPILOT_MODEL_DIGEST=DIGEST,
                    MARKETLAB_METRICS_PORT="59110",
                )
                log = BASE / (prefix + "-worker.log")
                args = [
                    sys.executable,
                    "-m",
                    "marketlab.inference_cli",
                    "worker",
                    "--max-jobs",
                    "1",
                ]
                with log.open("x", encoding="utf-8") as output:
                    process = await asyncio.to_thread(
                        subprocess.Popen,
                        args,
                        env=environment,
                        stdout=output,
                        stderr=output,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    )
                    evidence.data["owned_worker"] = {
                        "pid": process.pid,
                        "command": args,
                        "port": 59110,
                    }
                    began = time.monotonic()
                    previous = None
                    metric_samples = []
                    async with httpx.AsyncClient(trust_env=False, timeout=2) as client:
                        while process.poll() is None:
                            assert time.monotonic() - began < 145, (
                                "Native timeout worker exceeded bound"
                            )
                            try:
                                response = await client.get("http://127.0.0.1:59110/metrics")
                                response.raise_for_status()
                                if response.text != previous:
                                    previous = response.text
                                    metric_samples.append(
                                        {"seconds": time.monotonic() - began, "metrics": previous}
                                    )
                            except httpx.HTTPError:
                                pass
                            if (
                                time.monotonic() - began > 10
                                and "prometheus_worker" not in evidence.data
                            ):
                                response = await client.get(
                                    "http://127.0.0.1:59090/api/v1/query",
                                    params={"query": 'up{job="marketlab-inference-worker"}'},
                                )
                                response.raise_for_status()
                                observed = response.json()
                                assert observed.get("status") == "success"
                                assert any(
                                    row.get("metric", {}).get("instance")
                                    == "host.docker.internal:59110"
                                    and row.get("metric", {}).get("job")
                                    == "marketlab-inference-worker"
                                    and float(row["value"][1]) == 1
                                    for row in observed["data"]["result"]
                                ), "Normal CLI worker was not scraped by Prometheus"
                                evidence.data["prometheus_worker"] = observed
                                evidence.flush()
                            await asyncio.sleep(0.1)
                    elapsed = time.monotonic() - began
                    assert process.wait(timeout=5) == 0
                memo = MemoService(research, MemoModel(settings.ollama_url, MODEL, DIGEST))
                state = memo.inspect(run_id)
                assert endpoint.dispatch.is_set() and 119 <= elapsed < 145
                assert state["state"] == "retry_wait" and state["model_calls"] == 1
                assert state["attempt_count"] == 1 and state["result_sha256"] is None
                assert research.read(run_id, "summary") == (summary, summary_hash)
                assert any(
                    "marketlab_memo_queue_seconds_count 1.0" in row["metrics"]
                    for row in metric_samples
                )
                evidence.data.update(
                    run_id=run_id,
                    worker_seconds=elapsed,
                    state=state,
                    metric_samples=metric_samples,
                    production_timeout_seconds=120,
                    method="Normal CLI to owned chat blackhole; no upstream generation",
                    upstream_token_cancellation="Not tested by this blackhole deadline scenario",
                )
                evidence.flush()
        finally:
            if process is not None and process.poll() is None:
                if os.name == "nt":
                    await asyncio.to_thread(
                        subprocess.run,
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        capture_output=True,
                        check=False,
                    )
                else:
                    process.terminate()
                process.wait(timeout=10)
            await research.close()
            await bars.close()


async def run(prefix: str, phase: str) -> None:
    with Invocation(prefix, "recovery-" + phase) as evidence:
        if phase == "native-timeout-cli":
            await native_timeout(prefix, evidence)
        elif phase in {"interfaces", "lifecycle", "migration"}:
            adapter = operational_adapter()
            evidence.data["adapter"] = adapter.adapter_provenance
            evidence.flush()
            sampling = (
                nullcontext()
                if phase == "interfaces"
                else Sampler(BASE / (prefix + "-resources.json"), model=phase != "migration")
            )
            if phase == "interfaces":
                evidence.data["resource_scope"] = (
                    "Intentional owned Redis outage; this phase receives no memory gate credit"
                )
            with sampling:
                operation = getattr(adapter, phase)
                if phase == "migration":
                    await asyncio.to_thread(operation, prefix)
                else:
                    await operation(prefix)
            output = BASE / (prefix + "-" + phase + ".json")
            result = json.loads(await asyncio.to_thread(output.read_text, encoding="utf-8"))
            assert result["status"] == "passed"
            evidence.data["result"] = result
            if phase == "lifecycle":
                evidence.data["scope"] = (
                    "Real model priority/nonpreemption/client cancellation. Short chat-timeout "
                    "fault does not establish native120s deadline."
                )
        elif phase == "durability":
            r5 = durability_adapter("r5_acceptance")
            r6 = durability_adapter("r6_acceptance")
            evidence.data["adapters"] = [r5.adapter_provenance, r6.adapter_provenance]
            evidence.flush()
            with Sampler(BASE / (prefix + "-resources.json")):
                await r5.durability_live(prefix + "-copilot")
                await r6.durability(prefix + "-memo")
            evidence.data["results"] = [
                json.loads(
                    await asyncio.to_thread(
                        (BASE / (prefix + suffix + "-durability-live.json")).read_text,
                        encoding="utf-8",
                    )
                )
                for suffix in ("-copilot", "-memo")
            ]
            assert all(result["status"] == "passed" for result in evidence.data["results"])
        elif phase == "r2r4-clock":
            from r8_benchmark import isolated

            historical = importlib.import_module("r4_clock_acceptance")
            evidence.data["adapter"] = {
                "historical_path": "scripts/r4_clock_acceptance.py",
                "original_sha256": hashlib.sha256(
                    await asyncio.to_thread(Path("scripts/r4_clock_acceptance.py").read_bytes)
                ).hexdigest(),
                "method": "Unchanged API/retries/leases with owned migrated schema engine",
                "timestamp_edits": 0,
            }
            with isolated(prefix) as (_, engine, _, _):
                apis = [historical.API(kind, engine, prefix) for kind in ("R2", "R4")]
                with Sampler(BASE / (prefix + "-resources.json")):
                    evidence.data["retry_gates"] = await asyncio.to_thread(historical.retries, apis)
                    evidence.flush()
                    evidence.data["leases"] = await asyncio.to_thread(historical.leases, apis)
            evidence.data["owned_schema_removed"] = True
        elif phase == "process-tests":
            settings = owned_settings()
            environment = {
                **os.environ,
                "MARKETLAB_DATABASE_URL": settings.sqlalchemy_url.render_as_string(
                    hide_password=False
                ),
                "MARKETLAB_DATABASE_PASSWORD": settings.sqlalchemy_url.password or "",
            }
            args = [
                sys.executable,
                "-m",
                "pytest",
                "-m",
                "integration",
                "-vv",
                "--basetemp=" + str(BASE / (prefix + "-pytest")),
                "tests/test_jobs_integration.py",
                "tests/test_research_integration.py",
                "tests/test_copilot_integration.py",
                "tests/test_memos_integration.py",
                "-k",
                "crash or kill or stale or rollback or orphan or budget or atomic",
            ]
            log = BASE / (prefix + "-process-tests.log")
            with log.open("x", encoding="utf-8") as output:
                result = await asyncio.to_thread(
                    subprocess.run, args, env=environment, stdout=output, stderr=output, timeout=300
                )
            evidence.data.update(returncode=result.returncode, command=args, log=str(log))
            evidence.data["scope"] = (
                "Deterministic process/boundary/fencing tests include accelerated DB timestamps; "
                "separate R2/R4/R5/R6 phases establish native elapsed-time expiry"
            )
            assert result.returncode == 0
        else:
            raise ValueError("Unknown recovery phase")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase",
        choices=(
            "interfaces",
            "lifecycle",
            "migration",
            "durability",
            "r2r4-clock",
            "native-timeout-cli",
            "process-tests",
        ),
    )
    parser.add_argument("--prefix", required=True, type=validate_prefix)
    args = parser.parse_args()
    asyncio.run(run(args.prefix, args.phase))


if __name__ == "__main__":
    main()
