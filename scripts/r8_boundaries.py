"""Real owned R5/R6 crash boundaries with normal leases, budgets and publication.

Fault-location hooks deliberately terminate a real child with os._exit(81).
They do not change application source, clocks, deadlines or retry eligibility.
Actual installed-model calls run serially; numerical inputs are tiny synthetic
provider fixtures processed by the normal R1/R2 and R4 application services.
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from r8_acceptance import ObservedMemo, ObservedModel, audit_memo
from r8_benchmark import generate_input, isolated
from r8_common import (
    BASE,
    DIGEST,
    MODEL,
    NO_WINDOW,
    OWNER,
    PROFILE,
    Invocation,
    Sampler,
    owned_settings,
    processes,
    save,
    validate_prefix,
)

from marketlab.analytics.bars import BarService
from marketlab.config import Settings
from marketlab.copilot import store as cp_store
from marketlab.copilot.service import CopilotService
from marketlab.copilot.spec import assemble, decide
from marketlab.datasets.publication import ingest_archive
from marketlab.datasets.source import file_hash
from marketlab.memos import store as memo_store
from marketlab.memos.service import MemoService
from marketlab.research import store as research_store
from marketlab.research.service import ResearchService, execution_identity
from marketlab.research.spec import ResearchError, ResearchSpec

EXECUTABLE = str(Path(sys.executable).resolve())
SCRIPT = str(Path(__file__).resolve())

EXIT = 81
MODES = (
    "memo_before_checkpoint",
    "memo_corrupt_orphan",
    "copilot_before_reserve",
    "copilot_after_reserve",
    "copilot_after_checkpoint",
)


def validate_context(path: Path, context: dict[str, Any], settings: Settings) -> Path:
    """Refuse unowned schema/root/endpoint before any child write or claim."""
    base = BASE.resolve()
    if not path.resolve().is_relative_to(base) or path.is_symlink():
        raise ValueError("Child context outside owned evidence")
    if context.get("owner") != OWNER or context.get("mode") not in MODES:
        raise ValueError("Unknown child ownership/mode")
    schema = context.get("schema", "")
    root = Path(context["root"]).resolve()
    if not re.fullmatch(r"r8_bench_[0-9a-f]{32}", schema):
        raise ValueError("Unknown owned schema")
    if (
        not root.is_relative_to(base)
        or not root.name.startswith("r8-")
        or not root.name.endswith("-storage")
    ):
        raise ValueError("Unknown owned fixture root")
    url = settings.sqlalchemy_url
    if (url.host, url.port, url.database) != ("127.0.0.1", PROFILE.postgres_port, "marketlab"):
        raise ValueError("Child endpoint is not owned")
    if (
        url.query.get("options") != "-csearch_path=" + schema
        or settings.storage_path.resolve() != root
    ):
        raise ValueError("Child schema/storage mismatch")
    if settings.ollama_url != PROFILE.ollama_url:
        raise ValueError("Child model endpoint is not owned")
    if context["execution"] != execution_identity():
        raise ValueError("Child source identity drift")
    return root


def protocol_path(context_path: Path, suffix: str) -> Path:
    return context_path.with_name(context_path.stem + "-" + suffix)


def memo_rename_matches(source: Path, target: Path, root: Path, run: str) -> bool:
    return (
        target.resolve() == (root / "research" / run / "memo").resolve()
        and source.resolve().is_relative_to((root / ".staging").resolve())
        and source.name.startswith("memo-")
    )


def before_memo_registration(statement, mode: str, hook) -> None:
    """Only the real memo-result INSERT reaches this owned child fault point."""
    if (
        mode == "memo_corrupt_orphan"
        and isinstance(statement, sa.sql.dml.Insert)
        and statement.table is memo_store.results
    ):
        hook()


def crash(context_path: Path, current: Any, stage: str) -> None:
    selected = {name: getattr(current, name) for name in ("owner", "token", "attempt")}
    save(
        protocol_path(context_path, "hook.json"),
        {
            "status": "fault_location_reached",
            "method": "real os._exit(81)",
            "stage": stage,
            "pid": os.getpid(),
            "claim": selected,
            "monotonic": time.monotonic(),
        },
    )
    os._exit(EXIT)


async def child(context_path: Path) -> None:
    if (await asyncio.to_thread(context_path.stat)).st_size > 65536:
        raise ValueError("Child context too large")
    context = json.loads(await asyncio.to_thread(context_path.read_text))
    await asyncio.to_thread(owned_settings)  # Exact owned container/port identity guard.
    settings = Settings()
    root = validate_context(context_path, context, settings)
    pid = os.getpid()
    save(
        protocol_path(context_path, "ready.json"),
        {
            "pid": pid,
            "birth": processes()[pid]["identity"],
            "executable": EXECUTABLE,
            "context_sha256": file_hash(context_path),
        },
    )
    gate = protocol_path(context_path, "start")
    deadline = time.monotonic() + 30
    while not await asyncio.to_thread(gate.exists):
        if time.monotonic() > deadline:
            raise TimeoutError("Child start gate expired")
        await asyncio.sleep(0.05)
    engine = sa.create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
    bars = BarService(engine, root, None)
    research = ResearchService(bars)
    cp = CopilotService(research, ObservedModel(settings.ollama_url, MODEL, DIGEST))
    memo = MemoService(research, ObservedMemo(settings.ollama_url, MODEL, DIGEST))
    mode = context["mode"]
    original_reserve = cp_store.reserve_call
    original_cp_checkpoint = cp_store.checkpoint
    original_memo_checkpoint = memo_store.checkpoint
    original_execute = sa.engine.Connection.execute

    def reserve(engine, current):
        if mode == "copilot_before_reserve":
            crash(context_path, current, "before_durable_model_call_reservation")
        original_reserve(engine, current)
        if mode == "copilot_after_reserve":
            crash(context_path, current, "after_durable_reservation_before_model_dispatch")

    def cp_checkpoint(engine, current, value, provenance):
        if mode == "copilot_after_checkpoint" and value is not None:
            outcome, intent, _ = decide([context["body"]], value)
            assert outcome == "candidate"
            assert (
                assemble(intent, cp.selection(context["body"]["dataset_versions"])).body()
                == context["spec"]
            )
        original_cp_checkpoint(engine, current, value, provenance)
        if mode == "copilot_after_checkpoint" and value is not None:
            crash(context_path, current, "after_validated_interpretation_checkpoint")

    def memo_checkpoint(engine, current, draft, provenance):
        if mode == "memo_before_checkpoint" and draft is not None:
            crash(context_path, current, "after_validated_generation_before_draft_checkpoint")
        original_memo_checkpoint(engine, current, draft, provenance)

    def execute(connection, statement, *arguments, **keywords):
        def terminate_before_insert():
            final = root / "research" / context["target"] / "memo"
            if not final.is_dir():
                raise AssertionError("Normal memo rename did not precede result insert")
            current = memo_store.inspect(engine, context["target"])
            claim = memo_store.Claim(
                context["target"],
                current["owner"],
                current["fencing_token"],
                current["attempt_count"],
            )
            crash(context_path, claim, "after_memo_rename_before_memo_results_insert_and_commit")

        before_memo_registration(statement, mode, terminate_before_insert)
        return original_execute(connection, statement, *arguments, **keywords)

    cp_store.reserve_call = reserve
    cp_store.checkpoint = cp_checkpoint
    memo_store.checkpoint = memo_checkpoint
    sa.engine.Connection.execute = execute
    try:
        if mode.startswith("copilot"):
            await cp.work(1, context["target"])
        else:
            await memo.work(1, context["target"])
        raise AssertionError("Required child fault location not reached")
    finally:
        cp_store.reserve_call = original_reserve
        cp_store.checkpoint = original_cp_checkpoint
        memo_store.checkpoint = original_memo_checkpoint
        sa.engine.Connection.execute = original_execute
        await research.close()
        await bars.close()
        engine.dispose()


def owned_tree(
    inventory: dict[int, dict[str, Any]], launcher: int, birth: Any
) -> dict[int, dict[str, Any]]:
    selected = {launcher} if inventory.get(launcher, {}).get("identity") == birth else set()
    while True:
        updated = selected | {
            pid
            for pid, row in inventory.items()
            if row["parent"] in selected
            and int(row["identity"]) >= int(inventory[row["parent"]]["identity"])
        }
        if updated == selected:
            return {pid: inventory[pid] for pid in selected}
        selected = updated


def ready_is_owned(
    ready: dict[str, Any], inventory: dict[int, dict[str, Any]], launcher: int, birth: Any
) -> bool:
    owned = owned_tree(inventory, launcher, birth)
    return ready["pid"] in owned and owned[ready["pid"]]["identity"] == ready["birth"]


async def launch_child(context_path: Path, env: dict[str, str], sampler: Sampler) -> dict[str, Any]:
    log = context_path.with_suffix(".log")
    resolved_context = await asyncio.to_thread(context_path.resolve)
    with log.open("x", encoding="utf-8") as stream:
        process = await asyncio.to_thread(
            subprocess.Popen,
            [sys.executable, SCRIPT, "--child", str(resolved_context)],
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            creationflags=NO_WINDOW,
        )
        initial = processes().get(process.pid)
        if initial is None:
            process.kill()
            await asyncio.to_thread(process.wait, 15)
            raise RuntimeError("New launcher birth identity unavailable")
        launcher = {"pid": process.pid, "birth": initial["identity"], "executable": EXECUTABLE}
        save(protocol_path(context_path, "launcher.json"), launcher)
        ready_path = protocol_path(context_path, "ready.json")
        ready = None
        trusted_ready = None
        try:
            deadline = time.monotonic() + 30
            while not await asyncio.to_thread(ready_path.exists):
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Child did not reach owned ready gate")
                await asyncio.sleep(0.05)
            ready = json.loads(await asyncio.to_thread(ready_path.read_text))
            actual = processes().get(process.pid)
            assert actual is not None
            launcher_birth = launcher["birth"]
            assert ready_is_owned(ready, processes(), process.pid, launcher_birth)
            assert ready["executable"] == EXECUTABLE
            assert ready["context_sha256"] == file_hash(context_path)
            trusted_ready = ready
            # Keep the ready child alive until it has actually appeared in a native
            # memory sample. This wait precedes its claim and does not edit leases.
            observed_deadline = time.monotonic() + 10
            while not any(
                ready["pid"] in row["processes"]
                and row["processes"][ready["pid"]]["identity"] == ready["birth"]
                for row in sampler.samples
            ):
                if time.monotonic() > observed_deadline:
                    raise RuntimeError("Required child process resource observation missing")
                await asyncio.sleep(0.1)
            with protocol_path(context_path, "start").open("x"):
                pass
            code = await asyncio.to_thread(process.wait, 180)
            assert code == EXIT, f"Child exited {code}, expected controlled real death {EXIT}"
            proof = json.loads(
                await asyncio.to_thread(protocol_path(context_path, "hook.json").read_text)
            )
            assert proof["pid"] == ready["pid"] and process.poll() is not None
            return {
                "pid": ready["pid"],
                "birth": ready["birth"],
                "launcher": launcher,
                "exit_code": code,
                "context_sha256": ready["context_sha256"],
                "proof": proof,
                "resource_observed_before_claim": True,
                "reaped": True,
            }
        finally:
            if process.poll() is None:
                inventory = processes()
                if inventory.get(process.pid, {}).get("identity") != launcher["birth"]:
                    raise RuntimeError("Refuse termination of changed launcher identity")
                if os.name == "nt":
                    result = await asyncio.to_thread(
                        subprocess.run,
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        capture_output=True,
                        timeout=15,
                        creationflags=NO_WINDOW,
                    )
                    if result.returncode:
                        raise RuntimeError("Owned child tree termination failed")
                else:
                    # The production boundary children do not create compute
                    # workers before these fault points. Kill observed owned
                    # descendants before reaping the launcher if interrupted.
                    owned = owned_tree(inventory, process.pid, launcher["birth"])
                    for pid, row in reversed(list(owned.items())):
                        if processes().get(pid, {}).get("identity") == row["identity"]:
                            os.kill(pid, 9)
                await asyncio.to_thread(process.wait, 15)
            if trusted_ready is not None:
                remaining = processes().get(trusted_ready["pid"])
                if remaining is not None and remaining["identity"] == trusted_ready["birth"]:
                    raise RuntimeError("Owned interpreter survived launcher reaping")


def spec_for(version: str) -> ResearchSpec:
    return ResearchSpec.create(
        {
            "schema": "research-spec-v1",
            "workflow": "market_profile",
            "symbols": ["BTCUSDT"],
            "dataset_versions": [version],
            "start": "2025-01-01T01:00:00Z",
            "end": "2025-01-01T02:00:00Z",
            "history_start": "2025-01-01T00:00:00Z",
            "interval": "5m",
            "metrics": ["profile"],
            "parameters": {},
            "predicates": {},
        }
    )


def numerical_hashes(root: Path, run: str) -> dict[str, str]:
    directory = root / "research" / run
    return {
        name: file_hash(directory / name)
        for name in ("spec.json", "results.json", "summary.json", "manifest.json")
    }


def snapshot(engine, path: Path) -> None:
    tables = {}
    with engine.connect() as connection:
        for name in (
            "dataset_versions",
            "ingestion_submissions",
            "ingestion_jobs",
            "ingestion_attempts",
            "research_submissions",
            "research_runs",
            "research_attempts",
            "research_results",
            "copilot_requests",
            "copilot_revisions",
            "copilot_jobs",
            "copilot_attempts",
            "memo_jobs",
            "memo_attempts",
            "memo_results",
        ):
            tables[name] = [
                dict(row) for row in connection.execute(sa.text("SELECT * FROM " + name)).mappings()
            ]
    save(path, {"status": "owned_schema_snapshot", "tables": tables})


async def run(prefix: str) -> None:
    prefix = validate_prefix(prefix)
    if not re.fullmatch(r"r8-[a-z0-9-]{1,60}", prefix):
        raise ValueError("Invalid bounded R8 invocation prefix")
    with Invocation(prefix, "boundaries") as evidence:
        evidence.data.update(
            script_sha256=file_hash(Path(__file__)),
            clock_policy=(
                "Native database clock, 60-second leases unchanged; "
                "no lease or eligibility timestamp edits"
            ),
            fault_method="labeled fault-location hooks plus actual os._exit(81) child deaths",
            resource_evidence=str(BASE / f"{prefix}-boundaries-resources.json"),
        )
        with isolated(prefix) as (settings, engine, root, env):
            evidence.data["storage_root"] = str(root)
            with engine.connect() as connection:
                schema = connection.scalar(sa.text("SELECT current_schema()"))
            evidence.data["database_schema"] = schema
            bars = BarService(engine, root, None)
            research = ResearchService(bars)
            cp_model = ObservedModel(settings.ollama_url, MODEL, DIGEST)
            memo_model = ObservedMemo(settings.ollama_url, MODEL, DIGEST)
            cp = CopilotService(research, cp_model)
            memo = MemoService(research, memo_model)
            cases = []
            try:
                with Sampler(BASE / f"{prefix}-boundaries-resources.json", model=True) as sampler:
                    archive, checksum, generated = generate_input(1000, BASE / (prefix + "-input"))
                    manifest = await asyncio.to_thread(
                        ingest_archive, engine, root, archive, checksum
                    )
                    spec = spec_for(str(manifest["dataset_version_id"]))
                    evidence.data["input"] = generated
                    body = {
                        "schema": "copilot-request-v1",
                        "text": "Compute the descriptive OHLCV market_profile.",
                        "context": {
                            name: value
                            for name, value in spec.body().items()
                            if name
                            in {
                                "workflow",
                                "symbols",
                                "start",
                                "end",
                                "history_start",
                                "interval",
                                "metrics",
                            }
                        },
                        "dataset_versions": list(spec.dataset_versions),
                    }
                    # Memo crashes precede copilot creation so genuine copilot
                    # priority cannot prevent targeted memo claims.
                    for mode in MODES:
                        context = {
                            "owner": OWNER,
                            "mode": mode,
                            "root": str(root),
                            "schema": schema,
                            "execution": execution_identity(),
                            "spec": spec.body(),
                            "body": body,
                        }
                        if mode.startswith("memo"):
                            target, replayed = await research.submit(spec, prefix + "-" + mode)
                            assert not replayed and await research.work(1, target) == 1
                            assert research.inspect(target)["state"] == "succeeded"
                            context["numerical_before"] = numerical_hashes(root, target)
                        else:
                            target, _, replayed = await cp.create(body, prefix + "-" + mode)
                            assert not replayed
                        context["target"] = target
                        context_path = BASE / f"{prefix}-{mode}-boundary-context.json"
                        with context_path.open("x", encoding="utf-8") as stream:
                            json.dump(context, stream, indent=2)
                        process_evidence = await launch_child(context_path, env, sampler)
                        table = memo_store.jobs if mode.startswith("memo") else cp_store.jobs
                        column = table.c.run_id if mode.startswith("memo") else table.c.request_id
                        with engine.connect() as connection:
                            crashed = dict(
                                connection.execute(sa.select(table).where(column == target))
                                .mappings()
                                .one()
                            )
                        assert crashed["state"] == "running" and crashed["attempt_count"] == 1
                        expected_calls = 0 if mode == "copilot_before_reserve" else 1
                        assert crashed["model_calls"] == expected_calls
                        item = {
                            "mode": mode,
                            "target": target,
                            "context": context,
                            "child": process_evidence,
                            "crashed": crashed,
                        }
                        if mode == "copilot_after_checkpoint":
                            assert cp.inspect(target)["revisions"][0]["interpretation"] is not None
                        if mode == "memo_before_checkpoint":
                            assert memo_store.inspect(engine, target)["draft"] is None
                        if mode == "memo_corrupt_orphan":
                            state = memo_store.inspect(engine, target)
                            assert state["draft"] is not None
                            with engine.connect() as connection:
                                assert (
                                    connection.scalar(
                                        sa.select(sa.func.count())
                                        .select_from(memo_store.results)
                                        .where(memo_store.results.c.run_id == target)
                                    )
                                    == 0
                                )
                            artifact = (
                                root / "research" / target / "memo" / f"research_memo_{target}.md"
                            )
                            assert (
                                artifact.resolve().is_relative_to(root.resolve())
                                and not artifact.is_symlink()
                            )
                            orphan_manifest, orphan_content = memo.verify(artifact.parent, state)
                            assert orphan_manifest["run_id"] == target and orphan_content
                            item["orphan_verified_before_corruption"] = True
                            item["orphan_original_sha256"] = file_hash(artifact)
                            with artifact.open("ab") as stream:
                                stream.write(b"\nR8 controlled owned orphan corruption.\n")
                            item["orphan_corrupt_sha256"] = file_hash(artifact)
                            assert item["orphan_original_sha256"] != item["orphan_corrupt_sha256"]
                        cases.append(item)
                        evidence.data["cases"] = cases
                        evidence.flush()
                    latest = max(item["crashed"]["lease_until"] for item in cases)
                    began_wait = time.monotonic()
                    deadline = began_wait + 100
                    while True:
                        with engine.connect() as connection:
                            now = connection.scalar(sa.select(sa.func.clock_timestamp()))
                        if now >= latest:
                            break
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Native database lease expiry not observed")
                        await asyncio.sleep(0.25)
                    evidence.data["lease_expiry"] = {
                        "latest_recorded_lease": latest,
                        "observed_database_now": now,
                        "wait_seconds": time.monotonic() - began_wait,
                    }
                    # Resume copilot first, retaining actual priority semantics.
                    for item in sorted(
                        cases, key=lambda value: not value["mode"].startswith("copilot")
                    ):
                        mode, target = item["mode"], item["target"]
                        old = item["crashed"]
                        if mode.startswith("copilot"):
                            observed_before = len(cp_model.observations)
                            assert await cp.work(1, target) == 1
                            state = cp.inspect(target)
                            assert (
                                state["outcome"] == "submitted"
                                and state["revisions"][-1]["spec"] == spec.body()
                            )
                            assert research.inspect(state["run_id"])["state"] == "queued"
                            expected = 2 if mode == "copilot_after_reserve" else 1
                            assert state["revisions"][-1]["attempt_count"] == 2
                            assert state["revisions"][-1]["model_calls"] == expected
                            assert len(cp_model.observations) - observed_before == int(
                                mode != "copilot_after_checkpoint"
                            )
                            stale = cp_store.Claim(
                                old["job_id"],
                                target,
                                old["revision"],
                                old["owner"],
                                old["fencing_token"],
                                old["attempt_count"],
                            )
                            assert not cp_store.heartbeat(engine, stale)
                            try:
                                cp_store.reserve_call(engine, stale)
                            except ResearchError as error:
                                assert "ownership" in str(error)
                            else:
                                raise AssertionError("Stale copilot reservation accepted")
                            with engine.connect() as connection:
                                count = connection.scalar(
                                    sa.select(sa.func.count())
                                    .select_from(research_store.submissions)
                                    .where(
                                        research_store.submissions.c.idempotency_key
                                        == "copilot." + target
                                    )
                                )
                            assert count == 1 and await cp.work(1, target) == 0
                            assert await cp.create(body, prefix + "-" + mode) == (target, 0, True)
                            item["recovered"] = state
                        else:
                            observed_before = len(memo_model.observations)
                            assert await memo.work(1, target) == 1
                            state = memo_store.inspect(engine, target)
                            assert state["attempt_count"] == 2
                            if mode == "memo_before_checkpoint":
                                assert state["state"] == "ready" and state["model_calls"] == 2
                                assert len(memo_model.observations) - observed_before == 1
                                content, _ = memo.read(target)
                                summary, _ = research.read(target, "summary")
                                audit_memo(content, summary)
                                item["memo_sha256"] = hashlib.sha256(content.encode()).hexdigest()
                            else:
                                assert state["state"] == "failed" and state["model_calls"] == 1
                                assert len(memo_model.observations) == observed_before
                                with engine.connect() as connection:
                                    assert (
                                        connection.scalar(
                                            sa.select(sa.func.count())
                                            .select_from(memo_store.results)
                                            .where(memo_store.results.c.run_id == target)
                                        )
                                        == 0
                                    )
                                artifact = (
                                    root
                                    / "research"
                                    / target
                                    / "memo"
                                    / f"research_memo_{target}.md"
                                )
                                assert file_hash(artifact) == item["orphan_corrupt_sha256"]
                                try:
                                    memo.read(target)
                                except ResearchError as error:
                                    assert error.status == 409
                                else:
                                    raise AssertionError(
                                        "Corrupt unregistered memo became readable"
                                    )
                            assert (
                                numerical_hashes(root, target)
                                == item["context"]["numerical_before"]
                            )
                            assert (
                                research.read(target, "results")[0]["schema"]
                                == "research-results-v1"
                            )
                            assert (
                                research.read(target, "summary")[0]["schema"]
                                == "research-summary-v1"
                            )
                            assert research.inspect(target)["state"] == "succeeded"
                            stale = memo_store.Claim(
                                target, old["owner"], old["fencing_token"], old["attempt_count"]
                            )
                            assert not memo_store.heartbeat(engine, stale)
                            try:
                                memo_store.reserve_call(engine, stale)
                            except ResearchError as error:
                                assert "ownership" in str(error)
                            else:
                                raise AssertionError("Stale memo reservation accepted")
                            assert await memo.work(1, target) == 0
                            item.update(
                                recovered=state,
                                numerical_hashes_preserved=True,
                                numerical_reads_available=True,
                            )
                        item["status"] = "passed"
                        evidence.flush()
                        print(json.dumps({"case": mode, "status": "passed"}), flush=True)
                    assert len(cases) == 5 and all(item["status"] == "passed" for item in cases)
                    with engine.connect() as connection:
                        expected_counts = {
                            "research_runs": 5,
                            "research_results": 2,
                            "copilot_requests": 3,
                            "memo_jobs": 2,
                            "memo_results": 1,
                        }
                        observed_counts = {
                            name: connection.scalar(sa.text("SELECT count(*) FROM " + name))
                            for name in expected_counts
                        }
                    assert observed_counts == expected_counts
                    evidence.data["registered_counts"] = observed_counts
            finally:
                await research.close()
                await bars.close()
                snapshot(engine, BASE / f"{prefix}-boundaries-catalog-final.json")
        evidence.data["owned_schema_removed"] = True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=validate_prefix)
    parser.add_argument("--child", type=Path)
    args = parser.parse_args()
    if args.child is not None:
        if args.prefix is not None:
            parser.error("child and prefix are exclusive")
        asyncio.run(child(args.child))
    else:
        if args.prefix is None:
            parser.error("prefix is required")
        asyncio.run(run(args.prefix))


if __name__ == "__main__":
    main()
