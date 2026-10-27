"""Explicit R9 fresh-checkout, retained-file and workflow acceptance commands.

Run only after the root preservation baseline and owned inventory are recorded.
Provisioning is root-owned. The explicit fault phase cycles owned Redis, and the
packaged phase creates/removes only its separately labeled smoke image/container.
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import types
from datetime import date, datetime
from pathlib import Path

import httpx
import redis
import sqlalchemy as sa
from r9_common import (
    BASE,
    DIGEST,
    MODEL,
    PROJECT,
    Invocation,
    contained,
    docker,
    engine_for,
    environment,
    inputs,
    owned_process,
    prefix,
    read,
    require,
    resource_ids,
    settings,
)

from marketlab.analytics.bars import BarService
from marketlab.analytics.cache import canonical
from marketlab.datasets.publication import dataset_versions
from marketlab.datasets.source import file_hash
from marketlab.memos import store as memo_store
from marketlab.research import store as research_store
from marketlab.research.service import ResearchService, execution_identity
from marketlab.research.spec import ResearchSpec


def checked(
    command: list[str], evidence: Invocation, label: str, env=None, cwd=PROJECT, timeout=1800
):
    file_label = re.sub(r"[^a-zA-Z0-9._-]", "-", label)
    require(bool(file_label), "Empty command log label")
    log = BASE / f"{evidence.identity}-{file_label}.log"
    started = time.monotonic()
    with log.open("x", encoding="utf-8") as stream:
        result = subprocess.run(
            command, cwd=cwd, env=env, stdout=stream, stderr=stream, timeout=timeout
        )
    evidence.data.setdefault("commands", []).append(
        {
            "label": label,
            "command": command,
            "exit_code": result.returncode,
            "seconds": time.monotonic() - started,
            "log": str(log),
            "cwd": str(cwd),
        }
    )
    evidence.flush()
    require(result.returncode == 0, f"Command failed: {label}")
    return log


def migrate(configuration, evidence):
    checked(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        evidence,
        "migration",
        environment(configuration),
        timeout=120,
    )


def restore_catalog(engine):
    records = read(inputs()["catalog"])["catalog"]
    require(
        len(records) == 62 and sum(row["row_count"] for row in records) == 230311900,
        "Retained catalog totals mismatch",
    )
    root = settings().storage_path
    for row in records:
        path = contained(root / row["manifest_path"], root)
        require(file_hash(path) == row["manifest_sha256"], "Retained manifest hash mismatch")
        manifest = read(path)
        require(
            manifest["dataset_version_id"] == row["dataset_version_id"]
            and manifest["quality"]["accepted_rows"] == row["row_count"],
            "Retained manifest identity mismatch",
        )
    with engine.begin() as connection:
        for record in records:
            row = dict(record)
            row["trade_date"] = date.fromisoformat(row["trade_date"])
            row["published_at"] = datetime.fromisoformat(row["published_at"])
            existing = (
                connection.execute(
                    sa.select(dataset_versions).where(
                        dataset_versions.c.dataset_version_id == row["dataset_version_id"]
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is None:
                connection.execute(dataset_versions.insert().values(**row))
            else:
                require(dict(existing) == row, "Existing catalog registration differs")
    return records


def restore_research(engine):
    snapshot = read(inputs()["research_snapshot"])
    tables = {
        "research_submissions": research_store.submissions,
        "research_runs": research_store.runs,
        "research_attempts": research_store.attempts,
        "research_results": research_store.results,
    }
    require(
        all(row["state"] == "succeeded" for row in snapshot["research_runs"]),
        "Only completed retained history may be restored",
    )
    with engine.begin() as connection:
        for name, table in tables.items():
            for record in snapshot[name]:
                row = dict(record)
                for column in table.columns:
                    if row.get(column.name) is not None and isinstance(column.type, sa.DateTime):
                        row[column.name] = datetime.fromisoformat(row[column.name])
                primary = [table.c[column.name] == row[column.name] for column in table.primary_key]
                existing = (
                    connection.execute(sa.select(table).where(*primary)).mappings().one_or_none()
                )
                if existing is None:
                    connection.execute(table.insert().values(**row))
                else:
                    require(dict(existing) == row, "Retained research registration differs")
    return snapshot


def restore_memos(engine):
    pinned = inputs()
    require(
        "memo_snapshot" in pinned and "scenarios" in pinned,
        "Memo/scenario input manifests required",
    )
    snapshot = read(pinned["memo_snapshot"])["tables"]
    selected = {row["run_id"] for row in snapshot["research_results"]}
    submissions = {
        row["submission_id"] for row in snapshot["research_runs"] if row["run_id"] in selected
    }
    tables = {
        "research_submissions": research_store.submissions,
        "research_runs": research_store.runs,
        "research_attempts": research_store.attempts,
        "research_results": research_store.results,
        "memo_jobs": memo_store.jobs,
        "memo_attempts": memo_store.attempts,
        "memo_results": memo_store.results,
    }
    with engine.begin() as connection:
        for name, table in tables.items():
            rows = [
                row
                for row in snapshot[name]
                if (
                    row.get("submission_id") in submissions
                    if name == "research_submissions"
                    else row.get("run_id") in selected
                )
            ]
            for record in rows:
                row = dict(record)
                if name == "research_runs":
                    require(row["state"] == "succeeded", "Retained run is not completed")
                if name == "memo_jobs":
                    require(row["state"] == "ready", "Retained memo is not ready")
                for column in table.columns:
                    if row.get(column.name) is not None and isinstance(column.type, sa.DateTime):
                        row[column.name] = datetime.fromisoformat(row[column.name])
                primary = [table.c[column.name] == row[column.name] for column in table.primary_key]
                existing = (
                    connection.execute(sa.select(table).where(*primary)).mappings().one_or_none()
                )
                if existing is None:
                    connection.execute(table.insert().values(**row))
                else:
                    require(dict(existing) == row, "Retained memo registration differs")
    return read(pinned["scenarios"])[:5]


def source_allowed(relative: Path) -> bool:
    """Explicit source-only overlay policy; raw media stays external evidence."""
    if relative.is_absolute() or ".." in relative.parts:
        return False
    if any(
        part
        in {
            "artifacts",
            "data",
            ".venv",
            ".git",
            "secrets",
            "node_modules",
            "dist",
            "build",
            ".vite",
            "test-results",
            "playwright-report",
            "captures",
            "renders",
            "media",
            "raw",
        }
        for part in relative.parts
    ):
        return False
    if relative.parts[:2] == ("demo", "public"):
        return False
    if any(part.startswith(".env") and part != ".env.example" for part in relative.parts):
        return False
    suffixes = {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".css",
        ".svg",
        ".json",
        ".md",
        ".txt",
        ".yaml",
        ".yml",
        ".toml",
        ".lock",
        ".ps1",
        ".sql",
        ".ini",
        ".cfg",
        ".example",
    }
    return relative.suffix.lower() in suffixes or relative.name in {
        "Dockerfile",
        ".gitignore",
        ".dockerignore",
        "LICENSE",
        "Makefile",
    }


def checkout_path(identity: str) -> Path:
    token = hashlib.sha256(prefix(identity).encode()).hexdigest()[:8]
    root = PROJECT / "artifacts/c"
    return contained(root / token, root)


def source_overlay(evidence: Invocation):
    destination = checkout_path(evidence.identity)
    require(not destination.exists(), "Checkout destination exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=PROJECT).strip()
    checked(
        ["git", "clone", "--no-hardlinks", "--no-checkout", str(PROJECT), str(destination)],
        evidence,
        "clone",
        timeout=180,
    )
    checked(
        ["git", "checkout", "--detach", base], evidence, "checkout", cwd=destination, timeout=120
    )
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=PROJECT).decode().split("\0")
    untracked = (
        subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=PROJECT
        )
        .decode()
        .split("\0")
    )
    allowed_top = {
        "src",
        "tests",
        "scripts",
        "docs",
        "frontend",
        "monitoring",
        "alembic",
        "demo",
        ".github",
    }
    overlays = []
    for name in sorted(set(tracked + untracked) - {""}):
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts, "Unsafe source path")
        if not source_allowed(relative):
            continue
        if relative.parts[0] in {"artifacts", "data", ".venv", ".git", "secrets"} or any(
            part in {"node_modules", "dist", "build", ".vite", "test-results", "playwright-report"}
            for part in relative.parts
        ):
            continue
        if any(
            part.startswith(".env") and part != ".env.example" for part in relative.parts
        ) or relative.suffix.lower() in {
            ".pem",
            ".key",
            ".gguf",
            ".safetensors",
            ".mp4",
            ".webm",
            ".wav",
        }:
            continue
        if name in untracked and len(relative.parts) > 1 and relative.parts[0] not in allowed_top:
            raise RuntimeError("Unreviewed untracked source overlay path")
        source, target = PROJECT / relative, destination / relative
        if not source.exists():
            if target.is_file():
                target.unlink()
            overlays.append({"path": name, "deleted": True})
            continue
        require(source.is_file() and not source.is_symlink(), "Nonregular source overlay")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        overlays.append({"path": name, "sha256": file_hash(target)})
    evidence.data.update(
        base_sha=base,
        overlay=overlays,
        destination=str(destination),
        destination_owner={"root": str(destination.parent), "invocation": evidence.identity},
        identity="Published base plus audited source overlay; not a published R9 revision",
    )
    require(
        not (destination / ".venv").exists()
        and not (destination / "frontend/node_modules").exists(),
        "Environment copied into clone",
    )


def copy_retained(source: Path, evidence: Invocation):
    configuration = settings()
    root = configuration.storage_path
    require(not root.exists(), "Owned retained destination must not exist")
    source = source.resolve()
    require(
        source.is_dir() and source != root and not root.is_relative_to(source),
        "Invalid retained source",
    )
    candidates = []
    for top in ("datasets", "research"):
        for path in sorted((source / top).rglob("*")):
            require(not path.is_symlink() and not path.is_junction(), "Linked retained artifact")
            if not path.is_file():
                continue
            relative = path.relative_to(source)
            target = contained(root / relative, root)
            require(
                os.name != "nt" or len(str(target)) < 260,
                "Retained destination exceeds Windows budget; use a shorter owned root",
            )
            candidates.append((path, relative, target))
    require(bool(candidates), "No retained files available")
    evidence.data.update(
        copy_preflight={
            "files": len(candidates),
            "maximum_destination_characters": max(len(str(row[2])) for row in candidates),
            "destination_existed": False,
        }
    )
    evidence.flush()
    root.mkdir(parents=True)
    rows = []
    for path, relative, target in candidates:
        target.parent.mkdir(parents=True, exist_ok=True)
        before = file_hash(path)
        with path.open("rb") as incoming, target.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)
        require(
            file_hash(target) == before == file_hash(path),
            "Retained artifact changed during copy",
        )
        rows.append({"path": str(relative), "sha256": before, "bytes": target.stat().st_size})
    require(bool(rows), "No retained files copied")
    evidence.data.update(
        source=str(source),
        destination=str(root),
        files=rows,
        raw_data="Copied explicitly as retained evidence, never as source overlay",
    )


def path_a(evidence: Invocation):
    configuration = settings().model_copy(
        update={"storage_path": contained(BASE / "path-a-storage")}
    )
    engine = engine_for(configuration)
    try:
        migrate(configuration, evidence)
        with engine.connect() as connection:
            require(
                connection.scalar(sa.select(sa.func.count()).select_from(dataset_versions)) == 0,
                "Path A requires empty catalog",
            )
        require(not configuration.storage_path.exists(), "Path A storage must be fresh")
        env = environment(configuration)
        submissions = []
        for label, key in (
            ("initial", evidence.identity + "-day"),
            ("replay", evidence.identity + "-day"),
            ("recheck", evidence.identity + "-recheck"),
        ):
            log = checked(
                [
                    sys.executable,
                    "-m",
                    "marketlab.dataset_cli",
                    "submit",
                    "--symbols",
                    "BTCUSDT",
                    "--from-date",
                    "2025-01-01",
                    "--before-date",
                    "2025-01-02",
                    "--key",
                    key,
                ],
                evidence,
                label + "-submit",
                env,
            )
            submission = json.loads(log.read_text())["submission_id"]
            submissions.append(submission)
            if label != "replay":
                checked(
                    [
                        sys.executable,
                        "-m",
                        "marketlab.dataset_cli",
                        "worker",
                        "--max-jobs",
                        "1",
                        "--submission",
                        submission,
                    ],
                    evidence,
                    label + "-worker",
                    env,
                )
            state_log = checked(
                [sys.executable, "-m", "marketlab.dataset_cli", "jobs", "--submission", submission],
                evidence,
                label + "-jobs",
                env,
            )
            state = json.loads(state_log.read_text())
            require(
                state["complete"] and state["succeeded"] == 1 and state["failed"] == 0,
                "Official day did not complete",
            )
        require(
            submissions[0] == submissions[1] and submissions[2] != submissions[0],
            "Replay/recheck identities incorrect",
        )
        with engine.connect() as connection:
            rows = list(connection.execute(sa.select(dataset_versions)).mappings())
        require(len(rows) == 1, "Same-source recheck published another version")
        checked(
            [
                sys.executable,
                "-m",
                "marketlab.dataset_cli",
                "inspect",
                "--version",
                rows[0]["dataset_version_id"],
            ],
            evidence,
            "day-readback",
            env,
        )
        evidence.data.update(
            submissions=submissions,
            version=rows[0]["dataset_version_id"],
            rows=rows[0]["row_count"],
            source_sha256=rows[0]["source_sha256"],
        )
    finally:
        engine.dispose()


async def cold(evidence):
    configuration = settings()
    reference = inputs()["references"]
    original_path = PROJECT / "scripts/verifier_acceptance.py"
    original = original_path.read_text(encoding="utf-8")
    old = 'Path("artifacts/r4/reference-workflows.json")'
    require(original.count(old) == 1, "Verifier reference binding changed")
    adapted = original.replace(old, "Path(" + repr(str(reference)) + ")")
    module = types.ModuleType("r9_verifier_adapter")
    module.__file__ = str(original_path)
    exec(compile(adapted, str(original_path), "exec"), module.__dict__)
    module.BASE, module.ROOT = BASE, configuration.storage_path
    module.owned_settings = lambda: (configuration, resource_ids())
    module.restore_catalog = restore_catalog
    prior_expected = module.expected_verifications
    module.expected_verifications = lambda records: prior_expected(
        records, configuration.storage_path
    )
    output = BASE / f"{evidence.identity}-cold.json"
    require(not output.exists(), "Cold evidence exists")
    evidence.data["adapter"] = {
        "source_sha256": file_hash(original_path),
        "adapted_sha256": hashlib.sha256(adapted.encode()).hexdigest(),
        "bindings": [
            "BASE",
            "ROOT",
            "owned_settings",
            "restore_catalog",
            "expected_verifications",
            "reference path",
        ],
        "assertions": "Existing verifier numerical, hash, time and drain assertions unchanged",
    }
    evidence.flush()
    await module.cold(evidence.identity)
    result = read(output)
    require(
        result["status"] == "passed" and result["whole_workflow_seconds"] < 1800,
        "Cold workflow failed",
    )
    require(result["catalog"] == {"partitions": 62, "rows": 230311900}, "Cold catalog mismatch")
    require(result["numerical_attempts"] == 1, "Cold numerical attempt changed")
    require(
        result["memo"] == {"state": "queued", "attempts": 0, "model_calls": 0},
        "Cold memo must remain untouched",
    )
    evidence.data["result"] = result


async def research(evidence):
    configuration = settings()
    engine = engine_for(configuration)
    bars = service = None
    try:
        migrate(configuration, evidence)
        restore_catalog(engine)
        retained = restore_research(engine)
        references = read(inputs()["references"])
        require(len(references) == 5, "Expected five retained reference scenarios")
        bars = BarService(
            engine, configuration.storage_path, configuration.redis_url.get_secret_value()
        )
        service = ResearchService(bars)
        submissions = {row["submission_id"]: row for row in retained["research_submissions"]}
        evidence.data.update(retained_reads=[], fresh_runs=[])
        for run in retained["research_runs"]:
            spec = ResearchSpec.create(json.loads(submissions[run["submission_id"]]["spec"]))
            reference = next(
                row for row in references if ResearchSpec.create(row["spec"]).body() == spec.body()
            )
            results, result_hash = service.read(run["run_id"], "results")
            summary, _ = await service.summary(run["run_id"])
            require(
                results == reference["results"]
                and result_hash == reference["results_sha256"]
                and summary == reference["summary"]
                and hashlib.sha256(canonical(summary)).hexdigest() == reference["summary_sha256"],
                "Retained numerical reference mismatch",
            )
            evidence.data["retained_reads"].append(
                {"run_id": run["run_id"], "workflow": spec.workflow, "results_sha256": result_hash}
            )
            evidence.flush()
        covered = set()
        for reference in references:
            workflow = reference["spec"]["workflow"]
            if workflow in covered:
                continue
            covered.add(workflow)
            spec = ResearchSpec.create(reference["spec"])
            run_id, replay = await service.submit(spec, evidence.identity + "-" + workflow)
            require(not replay, "Fresh research key replayed")
            require(await service.work(1, run_id) == 1, "Fresh research worker did not claim")
            state = service.inspect(run_id)
            require(
                state["state"] == "succeeded" and state["attempt_count"] == 1,
                "Fresh numerical workflow failed",
            )
            results, result_hash = service.read(run_id, "results")
            summary, _ = await service.summary(run_id)
            require(
                results == reference["results"]
                and result_hash == reference["results_sha256"]
                and summary == reference["summary"]
                and hashlib.sha256(canonical(summary)).hexdigest() == reference["summary_sha256"],
                "Fresh numerical reference mismatch",
            )
            evidence.data["fresh_runs"].append(
                {
                    "run_id": run_id,
                    "workflow": workflow,
                    "results_sha256": result_hash,
                    "state": state,
                }
            )
            evidence.flush()
        require(
            covered == {"market_profile", "cross_asset", "volatility_cluster"},
            "Missing fresh workflow",
        )
    finally:
        if service is not None:
            await service.close()
        if bars is not None:
            await bars.close()
        engine.dispose()


async def retained_memos(evidence):
    from marketlab.memos.model import MemoModel
    from marketlab.memos.service import MemoService

    configuration = settings()
    engine = engine_for(configuration)
    bars = service = None
    try:
        migrate(configuration, evidence)
        restore_catalog(engine)
        scenarios = restore_memos(engine)
        require(len(scenarios) == 5, "Expected five retained memo scenarios")
        bars = BarService(
            engine, configuration.storage_path, configuration.redis_url.get_secret_value()
        )
        service = ResearchService(bars)
        memos = MemoService(service, MemoModel("http://127.0.0.1:1", MODEL, DIGEST))
        evidence.data["cases"] = []
        for row in scenarios:
            run_id = row["run_id"]
            results, result_hash = service.read(run_id, "results")
            summary, _ = await service.summary(run_id)
            content, manifest = memos.read(run_id)
            require(
                result_hash == row["result"]["results_sha256"]
                and hashlib.sha256(canonical(summary)).hexdigest()
                == row["result"]["summary_sha256"],
                "Retained scenario numerical hash mismatch",
            )
            require(
                hashlib.sha256(content.encode()).hexdigest() == row["memo"]["memo_sha256"]
                and len(content.split("\n\n")) == 3,
                "Retained memo hash/paragraph mismatch",
            )
            evidence.data["cases"].append(
                {
                    "run_id": run_id,
                    "results_sha256": result_hash,
                    "memo_sha256": manifest["artifact"]["sha256"],
                    "model_calls": 0,
                }
            )
            evidence.flush()
    finally:
        if service is not None:
            await service.close()
        if bars is not None:
            await bars.close()
        engine.dispose()


async def model_cases(evidence):
    from r5_acceptance import expected_spec, finish_copilot
    from r8_acceptance import ObservedMemo, ObservedModel

    from marketlab.copilot.service import CopilotService
    from marketlab.memos.service import MemoService

    configuration = settings()
    engine = engine_for(configuration)
    bars = research_service = None
    corpus_path = PROJECT / "tests/fixtures/r5_prompts.json"
    rubric_path = PROJECT / "tests/fixtures/r8_clarifications.json"
    corpus, rubric = read(corpus_path), read(rubric_path)
    clear = next(row for row in corpus["cases"] if row["id"] == "clear-01")
    negative = next(row for row in corpus["cases"] if row["id"] == "adversarial-01")
    initial = rubric["initial"]
    continuation = next(row for row in rubric["continuations"] if row["id"] == "complete-answer")
    evidence.data.update(
        frozen_cases={
            "clear": clear,
            "negative": negative,
            "clarification_initial": initial,
            "answer": continuation,
        },
        corpus_sha256=file_hash(corpus_path),
        clarification_sha256=file_hash(rubric_path),
        actual_model=MODEL,
        digest=DIGEST,
        cases=[],
    )
    evidence.flush()  # Prospective request identities/bytes are saved before actual calls.
    evidence.data["owned_model_process"] = owned_process("ollama", 11444)
    evidence.flush()
    try:
        migrate(configuration, evidence)
        records = restore_catalog(engine)
        versions = sorted(row["dataset_version_id"] for row in records)
        bars = BarService(
            engine, configuration.storage_path, configuration.redis_url.get_secret_value()
        )
        research_service = ResearchService(bars)
        model = ObservedModel(configuration.ollama_url, MODEL, DIGEST)
        evidence.data["model_observations"] = model.observations
        service = CopilotService(research_service, model)
        clear_run = None
        for case in (clear, negative):
            request = {
                "schema": "copilot-request-v1",
                "text": case["text"],
                "context": case["context"],
                "dataset_versions": versions,
            }
            key = evidence.identity + "-" + case["id"]
            request_id, _, replay = await service.create(request, key)
            require(not replay, "Model case key replayed")
            state = await finish_copilot(service, request_id)
            evidence.data["cases"].append(
                {"id": case["id"], "request": request, "request_id": request_id, "state": state}
            )
            evidence.flush()
            replay_identity = await service.create(request, key)
            require(replay_identity == (request_id, 0, True), "Copilot create replay differs")
            if case is clear:
                require(
                    state["outcome"] == "submitted"
                    and state["revisions"][-1]["spec"]
                    == expected_spec(case["expected_intent"], records),
                    "Clear actual model case failed",
                )
                clear_run = state["run_id"]
            else:
                require(
                    state["run_id"] is None and state["outcome"] in case["expected_outcomes"],
                    "Negative actual model gate failed",
                )
        request = {"schema": "copilot-request-v1", **initial, "dataset_versions": versions}
        request_id, _, _ = await service.create(request, evidence.identity + "-clarification")
        before = await finish_copilot(service, request_id)
        evidence.data["clarification"] = {"request_id": request_id, "initial": before}
        evidence.flush()
        require(
            before["outcome"] == "needs_clarification",
            "Initial clarification safely failed; continuation gate incomplete",
        )
        answer = {
            "schema": "copilot-answer-v1",
            "expected_revision": 0,
            "text": continuation["answer_text"],
            "context": continuation["answer_context"],
        }
        answer_key = evidence.identity + "-answer"
        require(
            await service.answer(request_id, answer, answer_key) == (request_id, 1, False),
            "Answer identity mismatch",
        )
        require(
            await service.answer(request_id, answer, answer_key) == (request_id, 1, True),
            "Answer replay mismatch",
        )
        final = await finish_copilot(service, request_id)
        evidence.data["clarification"]["final"] = final
        evidence.data["model_observations"] = model.observations
        evidence.flush()
        intent = {**initial["context"], **continuation["answer_context"]}
        require(
            final["outcome"] == "submitted"
            and final["current_revision"] == 1
            and final["revisions"][-1]["spec"] == expected_spec(intent, records),
            "Actual clarification did not hand off correctly",
        )
        require(
            clear_run is not None and await research_service.work(1, clear_run) == 1,
            "Clear numerical worker did not execute",
        )
        require(
            research_service.inspect(clear_run)["state"] == "succeeded",
            "Clear numerical execution failed",
        )
        summary_before, summary_hash = research_service.read(clear_run, "summary")
        memo_model = ObservedMemo(configuration.ollama_url, MODEL, DIGEST)
        evidence.data["memo_observations"] = memo_model.observations
        memos = MemoService(research_service, memo_model)
        evidence.data["memo_before"] = memos.inspect(clear_run)
        deadline = time.monotonic() + 420
        while time.monotonic() < deadline:
            await memos.work(1, clear_run)
            info = memos.inspect(clear_run)
            if info["state"] in {"ready", "failed"}:
                break
            await asyncio.sleep(0.5)
        evidence.data.update(memo=info, memo_observations=memo_model.observations)
        evidence.flush()
        require(info["state"] == "ready", "Fresh actual memo did not publish")
        content, manifest = memos.read(clear_run)
        require(len(content.split("\n\n")) == 3, "Fresh memo paragraph count mismatch")
        require(
            research_service.read(clear_run, "summary") == (summary_before, summary_hash),
            "Memo changed numerical summary",
        )
        evidence.data.update(
            memo_content=content,
            memo_manifest=manifest,
            summary_for_independent_audit=summary_before,
        )
    finally:
        evidence.flush()
        if research_service is not None:
            await research_service.close()
        if bars is not None:
            await bars.close()
        engine.dispose()


async def failure_isolation(evidence):
    """Actual owned Redis outage plus unavailable-model numerical independence."""
    from r8_acceptance import ObservedMemo

    from marketlab.memos.service import MemoService

    configuration = settings()  # Validate current identities before any stop.
    engine = engine_for(configuration)
    bars = service = None
    redis_id = resource_ids()["redis"]["id"]
    stopped = False
    try:
        references = read(inputs()["references"])
        reference = next(row for row in references if row["spec"]["workflow"] == "market_profile")
        bars = BarService(
            engine, configuration.storage_path, configuration.redis_url.get_secret_value()
        )
        service = ResearchService(bars)
        run_id, replay = await service.submit(
            ResearchSpec.create(reference["spec"]), evidence.identity + "-manual"
        )
        require(
            not replay and await service.work(1, run_id) == 1,
            "Unavailable-model manual run did not execute",
        )
        require(service.inspect(run_id)["state"] == "succeeded", "Manual numerics failed")
        summary, _ = await service.summary(run_id)
        require(summary == reference["summary"], "Manual numerical reference mismatch")
        await asyncio.sleep(0)  # Allow completed single-flight cleanup before next read.
        _, warm = await service.summary(run_id)
        require(warm == "HIT", "Owned Redis cache did not prime")
        await asyncio.sleep(0)
        docker("stop", redis_id)
        stopped = True
        unavailable, cache_status = await service.summary(run_id)
        require(
            unavailable == summary and cache_status == "BYPASS",
            "Redis outage changed numerical summary",
        )
        evidence.data.update(
            run_id=run_id, cache_before=warm, cache_during_outage=cache_status, redis_id=redis_id
        )
        evidence.flush()
        docker("start", redis_id)
        stopped = False
        deadline = time.monotonic() + 20
        client = redis.Redis.from_url(
            configuration.redis_url.get_secret_value(), socket_timeout=1, socket_connect_timeout=1
        )
        try:
            while True:
                try:
                    require(client.ping(), "Owned Redis did not recover")
                    break
                except redis.RedisError:
                    if time.monotonic() >= deadline:
                        raise
                    await asyncio.sleep(0.2)
        finally:
            client.close()
        bad_model = ObservedMemo("http://127.0.0.1:1", MODEL, DIGEST)
        memos = MemoService(service, bad_model)
        require(await memos.work(1, run_id) == 1, "Unavailable memo worker did not claim")
        memo = memos.inspect(run_id)
        require(
            memo["state"] != "ready" and memo["attempt_count"] == 1 and memo["error"] is not None,
            "Unavailable model was not observed",
        )
        result, result_hash = service.read(run_id, "results")
        require(
            result == reference["results"]
            and result_hash == reference["results_sha256"]
            and service.read(run_id, "summary")[0] == summary,
            "Model failure affected numerical reads",
        )
        evidence.data.update(
            memo_unavailable=memo,
            results_sha256=result_hash,
            manual_used_no_model=True,
            redis_recovered=True,
            summary_unchanged=True,
        )
    finally:
        if stopped:
            docker("start", redis_id)
            evidence.data["redis_restarted_after_failure"] = True
        if service is not None:
            await service.close()
        if bars is not None:
            await bars.close()
        engine.dispose()


def observe_endpoints(evidence):
    """Read only fixed owned HTTP/collector/worker endpoints; do not launch them."""
    settings()
    evidence.data["owned_processes"] = {
        role: owned_process(role, port)
        for role, port in (("api", 58007), ("collector", 59119), ("worker", 59120))
    }
    urls = {
        "api_health": "http://127.0.0.1:58007/health/live",
        "api_ready": "http://127.0.0.1:58007/health/ready",
        "api_metrics": "http://127.0.0.1:58007/metrics",
        "collector": "http://127.0.0.1:59119/metrics",
        "worker": "http://127.0.0.1:59120/metrics",
    }
    evidence.data["observations"] = []
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=10) as client:
        for name, url in urls.items():
            response = client.get(url)
            require(response.status_code == 200, "Owned endpoint unavailable")
            body = response.text
            if name == "collector":
                require(
                    "marketlab_durable_available 1.0" in body
                    or "marketlab_durable_available 1" in body,
                    "Durable collector snapshot unavailable",
                )
                require("marketlab_durable_jobs" in body, "Durable job telemetry missing")
            elif name not in {"api_health", "api_ready"}:
                require("marketlab_" in body, "Separate application/worker registry missing")
            evidence.data["observations"].append(
                {
                    "name": name,
                    "url": url,
                    "status": response.status_code,
                    "sha256": hashlib.sha256(response.content).hexdigest(),
                    "body": body,
                }
            )
            evidence.flush()


def compatibility_source(original: str, old_path: Path) -> tuple[str, dict[str, str]]:
    """Bind external evidence and the original fixture when outside tests/ scope."""
    replacements = {
        'Path("artifacts/r8/runtime-freeze.json")': "Path(" + repr(str(old_path)) + ")",
        'Path("artifacts/r8-adoption-20261027")': "Path(" + repr(str(BASE)) + ")",
        'root.name.startswith("r8-")': 'root.name.startswith("r9-")',
        "import sqlalchemy as sa\n": (
            "import sqlalchemy as sa\nfrom conftest import dataset_engine as dataset_engine\n"
        ),
    }
    adapted = original
    for before, after in replacements.items():
        require(original.count(before) == 1, "Source compatibility evidence binding changed")
        adapted = adapted.replace(before, after)
    return adapted, replacements


def source_compatibility(evidence):
    """Retain exact old identity/strict assertions; adapt evidence and fixture scope."""
    configuration = settings()
    pinned = inputs()
    require("old_execution" in pinned, "Pinned historical execution input required")
    old = read(pinned["old_execution"])
    require(old != execution_identity(), "Old and current source identities must differ")
    source = PROJECT / "tests/test_r8_source_compatibility_integration.py"
    original = source.read_text(encoding="utf-8")
    adapted, replacements = compatibility_source(original, pinned["old_execution"])
    generated = BASE / f"test_{evidence.identity.replace('-', '_')}_source_compatibility.py"
    with generated.open("x", encoding="utf-8") as stream:
        stream.write(adapted)
    receipts = BASE / f"{evidence.identity}-source-cases"
    receipts.mkdir(exist_ok=False)
    env = environment(configuration)
    env["MARKETLAB_R8_SOURCE_EVIDENCE"] = str(receipts)
    env["PYTHONPATH"] = str(PROJECT / "tests") + os.pathsep + env.get("PYTHONPATH", "")
    evidence.data.update(
        old_execution=old,
        original_test_sha256=file_hash(source),
        adapted_test_sha256=file_hash(generated),
        bindings=replacements,
        fixture_binding="Original conftest.dataset_engine imported into generated module scope",
        assertions="Unchanged old identity, natural retries, no dispatch and rejection assertions",
    )
    evidence.flush()
    checked(
        [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            "integration",
            "-vv",
            str(generated),
            "tests/test_jobs_integration.py::test_incompatible_execution_contract_is_not_claimed",
            "tests/test_research_integration.py::test_worker_fingerprint_mismatch_is_terminal",
            "--basetemp=" + str(BASE / f"{evidence.identity}-pytest-source"),
        ],
        evidence,
        "source-tests",
        env,
        timeout=240,
    )
    cases = {path.stem: read(path) for path in receipts.glob("*.json")}
    require(
        set(cases) == {"copilot-provenance", "copilot-validated", "memo-pin", "memo-validated"},
        "Four actual source receipts required; skips are incomplete",
    )
    for row in cases.values():
        require(
            row["status"] == "passed"
            and row["old_execution"] == old
            and row["current_execution"] == evidence.data["execution"]
            and row["model_identifications"]
            == row["new_model_calls"]
            == row["timestamp_edits"]
            == 0,
            "Source compatibility evidence mismatch",
        )
    evidence.data["cases"] = cases


def packaged_linux(evidence):
    """Reuse native packaged verifier and ownership-checked cleanup unchanged."""
    configuration = settings()
    pinned = inputs()
    require("native_reference" in pinned, "Pinned native bar reference required")
    rows = read(pinned["catalog"])["catalog"]
    selected = min(rows, key=lambda row: row["row_count"])
    require(
        read(pinned["native_reference"])["version"] == selected["dataset_version_id"],
        "Native reference does not match selected smallest day",
    )
    source = PROJECT / "scripts/verifier_acceptance.py"
    original = source.read_text(encoding="utf-8")
    before = (
        'Path("artifacts/r4/reference-data") / (\n'
        '            "reference-" + selected["dataset_version_id"] + ".json"\n        )'
    )
    require(original.count(before) == 1, "Packaged native reference binding changed")
    adapted = original.replace(before, "Path(" + repr(str(pinned["native_reference"])) + ")")
    module = types.ModuleType("r9_linux_adapter")
    module.__file__ = str(source)
    exec(compile(adapted, str(source), "exec"), module.__dict__)
    module.BASE, module.ROOT = BASE, configuration.storage_path
    module.owned_settings = lambda: (configuration, resource_ids())
    module.restore_catalog = restore_catalog
    evidence.data["adapter"] = {
        "source_sha256": file_hash(source),
        "adapted_sha256": hashlib.sha256(adapted.encode()).hexdigest(),
        "bindings": ["BASE", "ROOT", "owned_settings", "restore_catalog", "native reference"],
        "assertions": "Native bar/hash/drain and exact owned cleanup assertions unchanged",
    }
    evidence.flush()
    module.linux_smoke(evidence.identity)
    result = read(BASE / f"{evidence.identity}-linux.json")
    require(
        result["status"] == "passed"
        and result["owned_container_removed"]
        and result["owned_image_removed"],
        "Packaged Linux smoke or cleanup failed",
    )
    evidence.data["result"] = result


def checks(evidence, frontend=False):
    configuration = settings()
    env = environment(configuration)
    uv = shutil.which("uv") or str(PROJECT / ".venv/Scripts/uv.exe")
    if frontend:
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        require(npm is not None, "npm unavailable")
        for label, command in [
            ("npm-ci", [npm, "ci"]),
            *[
                (name, [npm, "run", name])
                for name in ("typecheck", "lint", "test", "build", "test:e2e")
            ],
        ]:
            checked(
                command, evidence, label, env={**os.environ, "CI": "1"}, cwd=PROJECT / "frontend"
            )
    else:
        migrate(configuration, evidence)
        for label, args in [
            ("lint", ["ruff", "check", "."]),
            ("format", ["ruff", "format", "--check", "."]),
            ("mypy", ["mypy"]),
            ("offline", ["pytest", "-m", "not integration", "-q"]),
            ("postgres", ["pytest", "-m", "integration", "-q"]),
        ]:
            if label in {"offline", "postgres"}:
                temporary = pytest_temp(evidence.identity, label)
                args = [*args, "--basetemp=" + str(temporary)]
            checked([uv, "run", "--locked", *args], evidence, label, env)


def pytest_temp(identity: str, label: str) -> Path:
    """Keep native Windows marker paths below classic limits without system changes."""
    token = hashlib.sha256((prefix(identity) + ":" + label).encode()).hexdigest()[:8]
    root = PROJECT / "artifacts/t"
    temporary = contained(root / token, root)
    require(not temporary.exists(), "Fresh test temporary directory required")
    root.mkdir(parents=True, exist_ok=True)
    return temporary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase",
        choices=(
            "clone",
            "copy-retained",
            "path-a",
            "cold",
            "research",
            "retained-memos",
            "model",
            "failure-isolation",
            "observe",
            "source-compatibility",
            "packaged-linux",
            "checks",
            "frontend",
        ),
    )
    parser.add_argument("--prefix", required=True, type=prefix)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    envelope_phase = (
        args.phase + "-envelope" if args.phase in {"cold", "packaged-linux"} else args.phase
    )
    with Invocation(args.prefix, envelope_phase) as evidence:
        if args.phase == "clone":
            source_overlay(evidence)
        elif args.phase == "copy-retained":
            require(args.source is not None, "copy-retained requires --source")
            copy_retained(args.source, evidence)
        elif args.phase == "path-a":
            path_a(evidence)
        elif args.phase == "checks":
            checks(evidence)
        elif args.phase == "frontend":
            checks(evidence, frontend=True)
        elif args.phase == "observe":
            observe_endpoints(evidence)
        elif args.phase == "source-compatibility":
            source_compatibility(evidence)
        elif args.phase == "packaged-linux":
            packaged_linux(evidence)
        else:
            asyncio.run(
                {
                    "cold": cold,
                    "research": research,
                    "retained-memos": retained_memos,
                    "model": model_cases,
                    "failure-isolation": failure_isolation,
                }[args.phase](evidence)
            )


if __name__ == "__main__":
    main()
