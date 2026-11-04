"""Frozen Phase 5 model evaluation on explicitly reviewed owned local resources.

``plan`` is offline and performs no database/network/inference operations. ``prepare``
creates genuine numerical prerequisites, but never invokes a model. ``bind`` freezes
actual verified snapshots/facts. Each scored suite/cohort is a separate invocation
and requires an independent approval matching every source/protocol/input byte.
Never use fixture successes as actual-model acceptance or omit failed invocations.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import Counter
from copy import deepcopy
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/v2-phase5-20261102"
FIXTURE = ROOT / "tests/fixtures/v2_phase5_eval.json"
SAMPLE = 0.5
MAX_GAP = 1.0
CEILING = 8 * 1024**3
OWNER = "v2-phase5-20261102"


def canonical(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        + "\n"
    ).encode()


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def read(path: Path, maximum: int = 16 * 1024**2) -> Any:
    from marketlab.datasets.v2.common import parse_json

    raw = path.read_bytes()
    if len(raw) > maximum:
        raise ValueError("Bounded evidence input exceeded")
    return parse_json(raw, maximum)


def write(path: Path, value: Any) -> None:
    raw = canonical(value)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(raw)
    temporary.replace(path)


def contained(path: Path, parent: Path = BASE) -> Path:
    value = path.absolute()
    if not value.is_relative_to(parent.absolute()) or value == parent.absolute():
        raise ValueError("Expected a named owned artifact path")
    for part in (value, *value.parents):
        if part.exists() and (part.is_symlink() or part.is_junction()):
            raise ValueError("Owned path contains a link")
    return value


def sources() -> dict[str, str]:
    files = list((ROOT / "src/marketlab").rglob("*.py"))
    files += [
        ROOT / name
        for name in (
            "scripts/v2_phase5_model_eval.py",
            "scripts/v2_phase5_faults.py",
            "tests/test_v2_phase5_faults.py",
            "scripts/v2_phase4_lifecycle.py",
            "scripts/v2_phase4_snapshot.py",
            "scripts/v2_phase3_acceptance.py",
            "scripts/r4_reference.py",
            "tests/fixtures/v2_phase5_eval.json",
            "pyproject.toml",
            "uv.lock",
        )
    ]
    files += list((ROOT / "migrations").rglob("*.py"))
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(set(files))}


def protocols() -> dict[str, Any]:
    from marketlab.copilot.v2.model import DIGEST, MODEL, copilot_versions
    from marketlab.copilot.v2.model import PROMPT as CP
    from marketlab.memos.v2.model import PROMPT as MP
    from marketlab.memos.v2.spec import schema

    return {
        "model": MODEL,
        "model_digest": DIGEST,
        "copilot_prompt": CP,
        "copilot_prompt_sha256": hashlib.sha256(CP.encode()).hexdigest(),
        "copilot_versions": copilot_versions(),
        "copilot_schema_policy": "request-specific-canonical-evidence-v1",
        "memo_prompt": MP,
        "memo_prompt_sha256": hashlib.sha256(MP.encode()).hexdigest(),
        "memo_schema": schema(),
        "memo_schema_sha256": digest(schema()),
    }


def validate_fixture(value: dict[str, Any]) -> None:
    cases, memos = value["copilot_cases"], value["memo_cases"]
    if len(cases) != 60 or Counter(c["category"] for c in cases) != {
        "clear": 20,
        "ambiguous_invalid": 20,
        "adversarial_unsupported": 20,
    }:
        raise ValueError("Frozen copilot cohort sizes must remain 20/20/20")
    shapes = {"first_profile", "second_profile", "comparison", "first_cluster", "second_cluster"}
    if Counter(c["shape"] for c in cases if c["category"] == "clear") != dict.fromkeys(shapes, 4):
        raise ValueError("Exactly four clear cases per retained shape required")
    clear = [c for c in cases if c["category"] == "clear"]
    if (
        len({i for c in clear for i in c["request"]["instrument_ids"]}) < 3
        or len(
            {
                c["expected_spec"]["start"][:10]
                for c in clear
                if c["expected_spec"]["start"][5:7] != "01"
            }
        )
        < 2
    ):
        raise ValueError("Actual three-instrument and two non-January date cohort required")
    if (
        len({c["id"] for c in cases}) != 60
        or len(memos) != 20
        or len({m["id"] for m in memos}) != 20
    ):
        raise ValueError("Duplicate or missing evaluation case")
    if Counter(m["shape"] for m in memos) != dict.fromkeys(shapes, 4):
        raise ValueError("Exactly four memo cases per retained shape required")
    for family, rows in (("copilot", cases), ("memo", memos)):
        expected = [c["id"] for c in rows]
        cohorts = value[family + "_cohorts"]
        if [c["id"] for c in cohorts] != ["A", "B"] or any(
            c["case_ids"] != expected for c in cohorts
        ):
            raise ValueError("Two identical ordered independently invoked cohorts required")
    if value["freeze_policy"] != {
        "cohorts": (
            "A and B independently invoked with fresh operation keys "
            "and identical ordered literal cases"
        ),
        "review_required_before_inference": True,
        "posthoc_tuning": False,
        "sample_interval_seconds": 0.5,
        "maximum_sample_gap_seconds": 1.0,
        "clear_threshold": 18,
        "negative_handoffs": 0,
        "memo_threshold": 20,
        "missing_prerequisite": (
            "incomplete; never reduce cohorts, cases, thresholds, unit requirements, or bounds"
        ),
    }:
        raise ValueError("Evaluation thresholds or frozen policy changed")
    if len(value["clarification_sequences"]) != 2 or any(
        len(s["answers"]) != 5 for s in value["clarification_sequences"]
    ):
        raise ValueError("Two literal five-answer sequences required")
    oversized = [
        c
        for c in cases
        if c.get("expected_http_status") == 422 and len(c["request"]["text"].encode()) > 8192
    ]
    if len(oversized) != 1 or oversized[0]["category"] != "adversarial_unsupported":
        raise ValueError("Oversized no-call input belongs inside each frozen adversarial twenty")
    if len(value["grounding_cases"]) != 8:
        raise ValueError("All eight prospective supplemental grounding probes are mandatory")
    for sequence in value["clarification_sequences"]:
        if [a["expected_revision"] for a in sequence["answers"]] != list(range(5)):
            raise ValueError("Clarification revisions must be literal 0..4")


def replace_versions(value: Any, bindings: dict[str, str]) -> Any:
    if isinstance(value, list):
        values = [replace_versions(item, bindings) for item in value]
        return (
            sorted(values)
            if all(isinstance(x, str) and re.fullmatch(r"[0-9a-f]{64}", x) for x in values)
            else values
        )
    if isinstance(value, dict):
        return {key: replace_versions(item, bindings) for key, item in value.items()}
    if isinstance(value, str) and value.startswith("@"):
        return bindings[value[1:]]
    return value


def plan(args: argparse.Namespace) -> int:
    value = read(args.fixtures)
    validate_fixture(value)
    output = contained(args.output)
    output.mkdir(parents=True, exist_ok=False)
    inputs = {}
    missing = []
    for alias, source in value["sources"].items():
        name = source["retained_manifest"]
        if name is None:
            missing.append(alias)
            continue
        path = ROOT / name
        if not path.is_file() or not path.resolve().is_relative_to(ROOT):
            raise ValueError("Retained source manifest unavailable")
        manifest = read(path)
        if (
            manifest["dataset_version_id"] != source["dataset_version_id"]
            or manifest["quality"]["accepted_rows"] < source["minimum_rows"]
        ):
            raise ValueError("Retained source does not match literal prerequisite")
        artifact = path.parent / manifest["artifact"]["path"]
        if artifact.parent != path.parent or artifact.is_symlink() or not artifact.is_file():
            raise ValueError("Unsafe retained artifact")
        inputs[alias] = {
            "manifest": str(path),
            "manifest_sha256": sha(path),
            "artifact": str(artifact),
            "expected_artifact_sha256": manifest["artifact"]["sha256"],
            "artifact_bytes": artifact.stat().st_size,
            "source": source,
            "package_files": {
                p.name: {"bytes": p.stat().st_size, "sha256": sha(p)}
                for p in path.parent.iterdir()
                if p.is_file() and p.name in {"manifest.json", "quality.json", "trades.parquet"}
            },
        }
        if "legacy_catalog_receipt" in source:
            inputs[alias]["legacy_catalog_sha256"] = sha(ROOT / source["legacy_catalog_receipt"])
    package_bytes = sum(
        sum(p["bytes"] for p in item["package_files"].values()) for item in inputs.values()
    )
    evidence = {
        "schema": "phase5-eval-offline-plan-v1",
        "status": "unbound_not_scored",
        "fixtures_sha256": sha(args.fixtures),
        "source_files": sources(),
        "protocols": protocols(),
        "retained_sources": inputs,
        "missing_sources": missing,
        "known_selected_package_bytes": package_bytes,
        "minimum_copy_and_backup_bytes": 2 * package_bytes,
        "physical_headroom_bytes": 50 * 1024**3,
        "database_network_model_operations": 0,
        "prepare_steps": [
            "owned empty database dump/isolated restore",
            "upgrade 0010",
            "verify and copy selected immutable packages; register exact retained identities",
            "official ETHBTC registry/ingestion; actual capacity receipt",
            "twenty genuine current-source/0010 numerical runs, independent Decimal oracle",
            "quiesced dump/filesystem backup; isolated restore exact comparison/readback",
            "forward 0011 rehearsal then actual upgrade and fresh capacity receipt",
            "twenty genuine current-source/0011 numerical runs, "
            "automatic pending memos and zero model calls",
            "bind 40 exact run summaries/facts/two permitted memo renderings "
            "and all input preflights",
            "independent exact-bound-fixture/protocol/source review before inference",
        ],
    }
    write(output / "plan.json", evidence)
    print(
        json.dumps(
            {
                "status": evidence["status"],
                "plan_sha256": sha(output / "plan.json"),
                "missing_sources": missing,
            }
        )
    )
    return 0


def approval(path: Path, stage: str, target: Path) -> dict[str, Any]:
    record = read(path)
    if (
        record.get("schema") != "phase5-eval-independent-approval-v1"
        or record.get("stage") != stage
        or record.get("target_sha256") != sha(target)
        or record.get("source_files") != sources()
        or record.get("protocols_sha256") != digest(protocols())
        or record.get("reviewer") != "gpt-6-astra/medium"
        or record.get("outcome") != "passed"
    ):
        raise ValueError("Exact independent stage/source/protocol approval required")
    return dict(record)


def config(path: Path) -> dict[str, Any]:
    import sqlalchemy as sa

    value = read(path)
    private = read(contained(Path(value["postgres_receipt"])))
    name = value["database_name"]
    root = contained(Path(value["storage_path"]))
    if (
        value["owner"] != OWNER
        or private["owner"] != OWNER
        or private["port"] != 55485
        or private["user"] != "phase5"
        or not re.fullmatch(r"v2p5_eval_[a-z0-9_]{1,32}", name)
    ):
        raise ValueError("Only the explicit owned Phase 5 evaluation database allowed")
    value["database_url"] = sa.URL.create(
        "postgresql+psycopg",
        username="phase5",
        password=private["password"],
        host="127.0.0.1",
        port=55485,
        database=name,
    )
    value["storage_path"] = root
    value["_private"] = private
    value["_private_sha256"] = sha(Path(value["postgres_receipt"]))
    for family in ("postgres", "redis"):
        inventory_path = contained(Path(value[family + "_inventory"]))
        if sha(inventory_path) != value[family + "_inventory_sha256"]:
            raise ValueError("Reviewed owned resource inventory changed")
        value["_" + family + "_inventory"] = read(inventory_path)
    for field in ("redis_url", "api_url", "ollama_url"):
        url = urlsplit(value[field])
        if url.hostname != "127.0.0.1" or url.username or url.password or not url.port:
            raise ValueError("Explicit loopback evaluation endpoints required")
    if value["api_url"] != "http://127.0.0.1:58185":
        raise ValueError("Only the reviewed owned API port 58185 allowed")
    if value["redis_url"] != "redis://127.0.0.1:56395/0":
        raise ValueError("Cache writes require the exact reviewed owned Redis endpoint")
    return dict(value)


def environment(cfg: dict[str, Any]) -> dict[str, str]:
    from marketlab.copilot.v2.model import DIGEST, MODEL

    return dict(
        os.environ,
        PYTHONPATH=str(ROOT / "src"),
        MARKETLAB_DATABASE_URL=cfg["database_url"].render_as_string(hide_password=False),
        MARKETLAB_DATABASE_PASSWORD=cfg["_private"]["password"],
        MARKETLAB_STORAGE_PATH=str(cfg["storage_path"]),
        MARKETLAB_REDIS_URL=cfg["redis_url"],
        MARKETLAB_OLLAMA_URL=cfg["ollama_url"],
        MARKETLAB_COPILOT_MODEL=MODEL,
        MARKETLAB_COPILOT_MODEL_DIGEST=DIGEST,
    )


def services(cfg: dict[str, Any]) -> tuple[Any, Any, Any, Any, Any]:
    import sqlalchemy as sa

    from marketlab.analytics.bars import BarService
    from marketlab.copilot.v2.model import CopilotModel
    from marketlab.copilot.v2.service import CopilotService
    from marketlab.memos.v2.model import MemoModel
    from marketlab.memos.v2.service import MemoService
    from marketlab.research.v2.service import ResearchService

    verify_container(cfg)
    verify_redis(cfg)
    engine = sa.create_engine(
        cfg["database_url"], connect_args={"connect_timeout": 5}, pool_timeout=5
    )
    bars = BarService(engine, cfg["storage_path"], cfg["redis_url"])
    research = ResearchService(bars)
    return (
        engine,
        bars,
        research,
        CopilotService(research, CopilotModel(cfg["ollama_url"])),
        MemoService(research, MemoModel(cfg["ollama_url"])),
    )


async def close_services(engine: Any, bars: Any, research: Any) -> None:
    await research.close()
    await bars.close()
    await asyncio.to_thread(engine.dispose)


async def finish(service: Any, identity: str) -> dict[str, Any]:
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        info = await asyncio.to_thread(service.inspect, identity)
        if info["state"] in {"succeeded", "failed"}:
            return dict(info)
        await service.work(1, identity)
        await asyncio.sleep(0.25)
    raise TimeoutError("Bounded model job did not reach a terminal state")


async def develop(args: argparse.Namespace, cfg: dict[str, Any], folder: Path) -> dict[str, Any]:
    from marketlab.copilot.v2.model import PROMPT_VERSION
    from marketlab.copilot.v2.spec import turn

    plan = read(args.plan)
    cases = plan["cases"]
    if (
        plan["schema"] != "phase5-v7-development-plan-v1"
        or plan["source_files"] != sources()
        or plan["config_sha256"] != sha(args.config)
        or PROMPT_VERSION != "copilot-prompt-v7"
        or [case["id"] for case in cases]
        != [
            "clear-first_profile-3",
            "clear-first_profile-4",
            "clear-second_profile-4",
            "dev-text-profile",
            "dev-context-profile",
            "dev-missing-history",
            "dev-conflicting-end",
            "dev-unsupported-forecast",
        ]
    ):
        raise ValueError("Exact bounded development plan required")
    engine, bars, research, copilot, _ = services(cfg)
    result: dict[str, Any] = {
        "schema": "phase5-v7-development-result-v1",
        "functional": "failed",
        "plan_sha256": sha(args.plan),
        "source_files": sources(),
        "cases": [],
    }
    try:
        snapshots = BindSnapshots(copilot)
        for case in cases:
            body = turn(case["request"])
            snapshot = await asyncio.to_thread(snapshots.snapshot, body)
            if (
                snapshot != case["snapshot"]
                or copilot.model.prepare(snapshot, [body]) != case["preflight"]
            ):
                raise ValueError("Current development input differs from approved preflight")
        await asyncio.to_thread(snapshots.check_final)
        for case in cases:
            before = await asyncio.to_thread(control_counts, engine)
            identity, revision, replayed = await copilot.create(
                case["request"], "p5.v7.dev." + case["id"]
            )
            record = {"id": case["id"], "request_id": identity}
            result["cases"].append(record)
            write(folder / "inside.json", result)
            if revision != 0 or replayed or await copilot.work(1, identity) != 1:
                raise ValueError("Fresh development request did not execute exactly one attempt")
            info = await asyncio.to_thread(copilot.inspect, identity)
            trace = await asyncio.to_thread(ledger, engine, identity, "copilot")
            after = await asyncio.to_thread(control_counts, engine)
            expected_handoffs = int(case["expected_outcome"] == "submitted")
            if info["run_id"] is not None:
                numerical = await asyncio.to_thread(research.inspect, info["run_id"])
                record["numerical"] = numerical
            correct = (
                len(info["revisions"]) == 1
                and info["revisions"][0]["attempt_count"] == 1
                and info["revisions"][0]["model_calls"] == 1
                and info["outcome"] == case["expected_outcome"]
                and info["snapshot"] == case["snapshot"]
                and info["revisions"][0]["spec"] == case["expected_spec"]
                and len(trace["calls"]) == 1
                and trace["calls"][0]["state"] == "checkpointed"
                and call_inputs_match(trace["calls"], case["preflight"])
                and trace["handoffs"] == expected_handoffs
                and all(
                    after[table] - count
                    == (expected_handoffs if table == "v2_research_submissions" else 1)
                    for table, count in before.items()
                )
                and (
                    record.get("numerical", {}).get("state") == "queued"
                    and record["numerical"]["attempt_count"] == 0
                    if expected_handoffs
                    else info["run_id"] is None
                )
            )
            record.update(correct=correct, status=info, ledger=trace)
            write(folder / "inside.json", result)
            if not correct:
                return result
        result["functional"] = "passed"
        return result
    finally:
        write(folder / "inside.json", result)
        await close_services(engine, bars, research)


def prepared_source_derivation(
    path: Path, prepared: dict[str, Any], current: dict[str, str]
) -> dict[str, str] | None:
    original = prepared["source_files"]
    if original == current:
        return None
    evaluator = "scripts/v2_phase5_model_eval.py"
    archive = BASE / "actual-bind-v6-001/evaluator-before.py"
    old_hash = "101aa107c53cb486084333b4fadd92ca37a81d585d088d81b3c4bb69489bf0c1"
    if (
        path.resolve() != BASE / "actual-prompt-v6-reprepare-001/prepared.json"
        or sha(path) != "a5215d330a82352516fa36dce8411e5ec5ffc51f758ced2c09617dace3a4373e"
        or original.get(evaluator) != old_hash
        or original | {evaluator: current[evaluator]} != current
        or sha(contained(archive)) != old_hash
    ):
        raise ValueError("Prepared source identity changed; do not silently rebind")
    return {
        "path": evaluator,
        "prepared_sha256": old_hash,
        "current_sha256": current[evaluator],
        "archived_source": archive.relative_to(ROOT).as_posix(),
    }


class BindSnapshots:
    """Reuse a fully verified selection only within one frozen bind invocation."""

    def __init__(self, copilot: Any) -> None:
        self.copilot = copilot
        self.reused = 0
        self.verified: dict[
            tuple[tuple[str, ...], tuple[str, ...]], tuple[tuple[Any, ...], dict[str, Any]]
        ] = {}

    def identity(self, versions: tuple[str, ...]) -> tuple[Any, ...]:
        from marketlab.datasets.v2.capabilities import value as capabilities
        from marketlab.datasets.v2.common import safe_path

        catalog = self.copilot.research.bars._catalog
        rows = catalog(versions)

        def catalog_identity(row: dict[str, Any]) -> tuple[Any, ...]:
            return row["catalog_identity"], row["signature"], canonical(row["metadata"])

        before = tuple(catalog_identity(row) for row in rows)
        packages = []
        for row in rows:
            files = [row["manifest_path"], row["path"]]
            if row["contract"] == "dataset-manifest-v2":
                quality = row["manifest_path"].with_name("quality.json")
                files.append(
                    safe_path(self.copilot.root, str(quality.relative_to(self.copilot.root)))
                )
            packages.append(tuple((str(path), sha(path)) for path in files))
        if tuple(catalog_identity(row) for row in catalog(versions)) != before:
            raise ValueError("Verified bind selection changed during hashing")
        return capabilities()["sha256"], before, tuple(packages)

    def snapshot(self, body: dict[str, Any]) -> dict[str, Any]:
        from marketlab.copilot.v2.spec import supplied

        key = tuple(body["instrument_ids"]), tuple(body["dataset_versions"])
        before = self.identity(key[1])
        reused = key in self.verified
        if reused:
            expected, snapshot = self.verified[key]
            if before != expected:
                raise ValueError("Verified bind selection changed")
        else:
            snapshot = self.copilot.snapshot(body)
        supplied(body["context"], snapshot)
        if before != self.identity(key[1]) or snapshot["capability_sha256"] != before[0]:
            raise ValueError("Verified bind selection changed")
        self.verified[key] = before, snapshot
        self.reused += int(reused)
        return deepcopy(snapshot)

    def check_final(self) -> None:
        for (_, versions), (expected, _) in self.verified.items():
            if self.identity(versions) != expected:
                raise ValueError("Verified bind selection changed before publication")


async def bind(args: argparse.Namespace, cfg: dict[str, Any]) -> dict[str, Any]:
    from marketlab.copilot.model import ModelFailure
    from marketlab.copilot.v2.spec import model_schema, turn
    from marketlab.datasets.v2.common import V2Error
    from marketlab.memos.v2.spec import facts, render
    from marketlab.research.v2.spec import ResearchSpec

    prepared = read(args.prepared)
    fixture = read(args.fixtures)
    validate_fixture(fixture)
    if prepared["fixtures_sha256"] != sha(args.fixtures):
        raise ValueError("Prepared fixture identity changed; do not silently rebind")
    current_sources = sources()
    derivation = prepared_source_derivation(args.prepared, prepared, current_sources)
    value = replace_versions(fixture, prepared["bindings"])
    engine, bars, research, copilot, memo = services(cfg)
    snapshots = BindSnapshots(copilot)
    try:
        for case in [*value["copilot_cases"], *value["grounding_cases"]]:
            try:
                body = turn(case["request"])
                snapshot = await asyncio.to_thread(snapshots.snapshot, body)
                case["snapshot"] = snapshot
                case["preflight"] = copilot.model.prepare(snapshot, [body])
                case["model_schema"] = model_schema(snapshot, [body])
                if digest(case["model_schema"]) != case["preflight"]["schema_sha256"]:
                    raise ValueError("Frozen request-specific schema differs from preflight")
            except (V2Error, ModelFailure) as error:
                status = (
                    error.status
                    if isinstance(error, ModelFailure)
                    else {"invalid_request": 422, "revision_conflict": 409}.get(error.code)
                )
                if case.get("expected_http_status") != status or not case.get("expected_no_call"):
                    raise
                case["expected_preflight_rejection"] = {
                    "exception_type": type(error).__name__,
                    "http_status": status,
                    "reserved_calls": 0,
                }
                continue
            if case.get("expected_http_status"):
                raise ValueError("Frozen expected no-call rejection was unexpectedly admissible")
            if case.get("expected_spec") is not None:
                expected = ResearchSpec.create(case["expected_spec"]).body()
                if expected != case["expected_spec"]:
                    raise ValueError("Literal expected specification is not canonical")
            if case.get("assert_projection_omits_display"):
                hostile = value["hostile_metadata"]
                if snapshot["metadata"][hostile["instrument_id"]]["display_name"] != hostile[
                    "display_name"
                ] or hostile["display_name"].encode() in canonical(
                    copilot.model.content(snapshot, [body])
                ):
                    raise ValueError(
                        "Hostile owned metadata was not bound or entered model context"
                    )
            if "rejected_answer" in case:
                answer = turn(case["rejected_answer"], True)
                try:
                    copilot.model.prepare(snapshot, [body, answer])
                except ModelFailure as error:
                    if error.status != case["answer_http_status"]:
                        raise
                    case["answer_preflight_rejection"] = {
                        "exception_type": type(error).__name__,
                        "http_status": error.status,
                        "reserved_calls": 0,
                    }
                else:
                    raise ValueError(
                        "Literal cumulative transcript does not exceed the unchanged budget"
                    )
        for sequence in value["clarification_sequences"]:
            snapshot = await asyncio.to_thread(snapshots.snapshot, turn(sequence["request"]))
            sequence["snapshot"] = snapshot
            sequence["preflights"] = []
            sequence["model_schemas"] = []
            turns = [sequence["request"]]
            for answer in [None, *sequence["answers"]]:
                if answer is not None:
                    turns.append(turn(answer, True))
                sequence["preflights"].append(copilot.model.prepare(snapshot, turns))
                grammar = model_schema(snapshot, turns)
                if digest(grammar) != sequence["preflights"][-1]["schema_sha256"]:
                    raise ValueError("Frozen clarification schema differs from preflight")
                sequence["model_schemas"].append(grammar)
        frozen_memos: dict[str, list[dict[str, Any]]] = {}
        run_ids = set()
        for cohort in ("A", "B"):
            frozen_memos[cohort] = []
            for case in value["memo_cases"]:
                entry = prepared["memo_runs"][cohort][case["id"]]
                run_id = entry["run_id"]
                if run_id in run_ids:
                    raise ValueError(
                        "Every memo cohort selection requires a distinct numerical run"
                    )
                run_ids.add(run_id)
                summary, row, _ = await asyncio.to_thread(memo.numerical, run_id)
                info = await asyncio.to_thread(research.inspect, run_id)
                if info["spec"] != case["expected_spec"] or any(
                    k not in summary for k in case["required_sections"]
                ):
                    raise ValueError("Memo actual spec/selected sections mismatch")
                source = facts(summary)
                reasons = {k: v for k, v in source["values"].items() if k.endswith("_reason")}
                if case["require_null_reason"] and not reasons:
                    raise ValueError(
                        "Real required null reason unavailable; fixture remains incomplete"
                    )
                variants = []
                for wording in ("standard", "measured"):
                    draft = {
                        "schema": "memo-draft-v2",
                        "paragraphs": [
                            {"claim": k, "wording": wording}
                            for k in ("scope", "findings", "limitations")
                        ],
                    }
                    variants.append(render(draft, source))
                if case["mode"] == "preexisting_explicit_enqueue":
                    with engine.connect() as connection:
                        from sqlalchemy import text

                        if connection.execute(
                            text("SELECT 1 FROM v2_memo_jobs WHERE run_id=:id"), {"id": run_id}
                        ).first():
                            raise ValueError("Preexisting numerical run already has a memo job")
                else:
                    pending = await asyncio.to_thread(memo.inspect, run_id)
                    if pending["state"] != "queued" or pending["model_calls"] != 0:
                        raise ValueError(
                            "Fresh numerical success must have its original unspent automatic memo"
                        )
                frozen_memos[cohort].append(
                    {
                        **case,
                        "run_id": run_id,
                        "summary": summary,
                        "summary_sha256": row["summary_sha256"],
                        "numerical_manifest_sha256": row["manifest_sha256"],
                        "facts": source,
                        "preflight": memo.model.prepare(source),
                        "expected_memo_variants": variants,
                        "null_reasons": reasons,
                        "numerical_evidence": entry,
                    }
                )
            rows = frozen_memos[cohort]
            quotes = {i["quote_asset"] for m in rows for i in m["summary"]["instruments"].values()}
            eras = {m["coverage_era"] for m in rows}
            if len(quotes) < 2 or eras != {"retained_legacy_january", "generalized_non_january"}:
                raise ValueError("Both quote-unit and January/non-January memo coverage required")
        await asyncio.to_thread(snapshots.check_final)
        if sources() != current_sources:
            raise ValueError("Bind source changed before publication")
        return {
            "schema": "phase5-evaluation-bound-v1",
            "status": "bound_pending_independent_review",
            "fixtures_sha256": sha(args.fixtures),
            "prepared_sha256": sha(args.prepared),
            "config_sha256": sha(args.config),
            "source_files": current_sources,
            "prepared_source_derivation": derivation,
            "snapshot_verification": {
                "distinct_fully_verified": len(snapshots.verified),
                "reused": snapshots.reused,
            },
            "protocols": protocols(),
            "bound_fixture": value,
            "memo_runs": frozen_memos,
            "qualification": (
                "No model identification or inference has occurred; literal "
                "facts/render variants require independent sentence review."
            ),
        }
    finally:
        await close_services(engine, bars, research)


def ledger(engine: Any, identity: str, kind: str) -> dict[str, Any]:
    from sqlalchemy import text

    from marketlab.datasets.v2.core import wire

    with engine.connect() as connection:
        if kind == "copilot":
            jobs = (
                connection.execute(
                    text(
                        "SELECT job_id FROM v2_copilot_jobs WHERE request_id=:id ORDER BY revision"
                    ),
                    {"id": identity},
                )
                .scalars()
                .all()
            )
            calls: list[dict[str, Any]] = []
            for job in jobs:
                calls.extend(
                    dict(r)
                    for r in connection.execute(
                        text(
                            "SELECT * FROM v2_copilot_calls WHERE job_id=:id ORDER BY call_number"
                        ),
                        {"id": job},
                    ).mappings()
                )
            handoffs = connection.execute(
                text("SELECT count(*) FROM v2_research_submissions WHERE idempotency_key=:key"),
                {"key": "copilot-v2." + identity},
            ).scalar_one()
        else:
            calls = [
                dict(r)
                for r in connection.execute(
                    text("SELECT * FROM v2_memo_calls WHERE run_id=:id ORDER BY call_number"),
                    {"id": identity},
                ).mappings()
            ]
            handoffs = None
    return dict(wire({"calls": calls, "handoffs": handoffs}))


def control_counts(engine: Any) -> dict[str, int]:
    from sqlalchemy import text

    tables = (
        "v2_copilot_requests",
        "v2_copilot_revisions",
        "v2_copilot_jobs",
        "v2_copilot_calls",
        "v2_research_submissions",
    )
    with engine.connect() as connection:
        return {
            table: connection.execute(text("SELECT count(*) FROM " + table)).scalar_one()
            for table in tables
        }


def call_inputs_match(calls: list[dict[str, Any]], expected: dict[str, Any]) -> bool:
    from marketlab.copilot.v2.model import DIGEST

    return all(
        call["model_digest"] == DIGEST
        and all(
            call[key] == expected[key] for key in ("input_sha256", "schema_sha256", "prompt_sha256")
        )
        for call in calls
    )


async def score(args: argparse.Namespace, cfg: dict[str, Any], folder: Path) -> dict[str, Any]:
    import httpx

    from marketlab.copilot.v2 import store as copilot_store
    from marketlab.memos.v2 import store as memo_store

    frozen = read(args.bound)
    if (
        frozen["source_files"] != sources()
        or frozen["protocols"] != protocols()
        or frozen["config_sha256"] != sha(args.config)
    ):
        raise ValueError("Frozen fixture/source/protocol/config changed")
    if args.suite == "faults":
        import v2_phase5_faults

        return dict(await v2_phase5_faults.run(cfg, frozen, folder, config_path=args.config))
    fixture = frozen["bound_fixture"]
    engine, bars, research, copilot, memo = services(cfg)
    result: dict[str, Any] = {
        "suite": args.suite,
        "cohort": args.cohort,
        "cases": [],
        "functional": "incomplete",
        "bound_sha256": sha(args.bound),
    }
    prefix = "p5." + uuid4().hex
    result["operation_prefix"] = prefix
    controls = 0
    async with httpx.AsyncClient(
        base_url=cfg["api_url"], timeout=1800, trust_env=False, follow_redirects=False
    ) as client:

        async def post(path: str, body: Any, key: str) -> Any:
            nonlocal controls
            controls += 1
            evidence: dict[str, Any] = {
                "path": path,
                "operation_key": key,
                "body_sha256": digest(body),
                "started_utc": datetime.now(UTC).isoformat(),
                "outcome": "unconfirmed",
            }
            destination = folder / f"control-{controls:03}.json"
            write(destination, evidence)
            try:
                async with client.stream(
                    "POST",
                    path,
                    content=canonical(body),
                    headers={
                        "Content-Type": "application/json",
                        "Idempotency-Key": key,
                        "Origin": cfg["api_url"],
                        "Sec-Fetch-Site": "same-origin",
                    },
                ) as response:
                    raw = bytearray()
                    async for part in response.aiter_bytes():
                        raw.extend(part)
                        if len(raw) > 65536:
                            raise ValueError("Control response exceeds bound")
                    completed = httpx.Response(
                        response.status_code,
                        headers=response.headers,
                        content=bytes(raw),
                        request=response.request,
                    )
                    evidence.update(
                        outcome="response_received",
                        http_status=response.status_code,
                        response=completed.json(),
                    )
                    return completed
            except BaseException as error:
                evidence["exception_type"] = type(error).__name__
                raise
            finally:
                evidence["ended_utc"] = datetime.now(UTC).isoformat()
                write(destination, evidence)

        try:
            # Identify only after the exact frozen review gate and resource containment.
            result["installed_model_digest"] = await copilot.model.identify()
            if args.suite in {"copilot", "grounding"}:
                cases = (
                    fixture["copilot_cases"]
                    if args.suite == "copilot"
                    else fixture["grounding_cases"]
                )
                for case in cases:
                    record = {
                        "id": case["id"],
                        "category": case.get("category", "grounding"),
                        "expected_spec": case["expected_spec"],
                    }
                    counts_before = await asyncio.to_thread(control_counts, engine)
                    response = await post(
                        "/v2/copilot/requests", case["request"], prefix + "." + case["id"]
                    )
                    record["http_status"] = response.status_code
                    if response.status_code in {200, 201}:
                        identity = response.json()["request_id"]
                        if case.get("expected_no_call"):
                            record.update(
                                request_id=identity,
                                correct=False,
                                classification="unexpected_admission_no_model_dispatched",
                            )
                            result["cases"].append(record)
                            raise ValueError("Expected no-call HTTP rejection created durable work")
                        initial = await asyncio.to_thread(copilot_store.inspect, engine, identity)
                        if initial["snapshot"] != case["snapshot"]:
                            raise ValueError("Actual selected snapshot differs from frozen context")
                        await finish(copilot, identity)
                        info = await asyncio.to_thread(copilot_store.inspect, engine, identity)
                        trace = await asyncio.to_thread(ledger, engine, identity, "copilot")
                        if not call_inputs_match(trace["calls"], case["preflight"]):
                            raise ValueError("Actual copilot call inputs differ from frozen review")
                        record.update(
                            request_id=identity,
                            status=info,
                            ledger=trace,
                            handoff=info["run_id"] is not None,
                            correct=info["outcome"] == "submitted"
                            and info["revisions"][-1]["spec"] == case["expected_spec"]
                            and trace["handoffs"] == 1,
                        )
                        record["classification"] = {
                            "submitted": "submitted",
                            "needs_clarification": "clarification",
                            "unsupported": "refusal",
                            "failed": "safe_failure",
                        }.get(info["outcome"], "safe_failure")
                        if case["expected_spec"] is None:
                            record["correct"] = (
                                info["outcome"] in case["expected_outcomes"]
                                and not record["handoff"]
                                and trace["handoffs"] == 0
                            )
                        if case.get("required_question_field"):
                            record["correct"] &= any(
                                q["field"] == case["required_question_field"]
                                for q in (info["revisions"][-1]["questions"] or [])
                            )
                        if "rejected_answer" in case:
                            before = await asyncio.to_thread(
                                copilot_store.inspect, engine, identity
                            )
                            before_counts = await asyncio.to_thread(control_counts, engine)
                            rejected = await post(
                                f"/v2/copilot/requests/{identity}/clarifications",
                                case["rejected_answer"],
                                prefix + "." + case["id"] + ".answer",
                            )
                            after = await asyncio.to_thread(copilot_store.inspect, engine, identity)
                            after_counts = await asyncio.to_thread(control_counts, engine)
                            record["rejected_answer"] = {
                                "http_status": rejected.status_code,
                                "body": rejected.json(),
                                "counts_before": before_counts,
                                "counts_after": after_counts,
                            }
                            record["correct"] &= (
                                rejected.status_code == case["answer_http_status"]
                                and before == after
                                and before_counts == after_counts
                            )
                        if args.suite == "grounding" and case["expected_spec"] is not None:
                            reference = next(
                                m
                                for m in frozen["memo_runs"]["A"]
                                if m["expected_spec"] == case["expected_spec"]
                            )
                            await research.work(1, info["run_id"])
                            comparison = {}
                            for kind in ("results", "summary"):
                                actual, actual_sha = await asyncio.to_thread(
                                    research.read, info["run_id"], kind
                                )
                                expected_sha = reference["numerical_evidence"]["hashes"][kind]
                                comparison[kind] = (
                                    actual_sha == expected_sha and digest(actual) == expected_sha
                                )
                            record["manual_copilot_exact_numerical_reference"] = comparison
                            record["correct"] &= all(comparison.values())
                        if trace["handoffs"] != int(record["handoff"]):
                            raise ValueError("Durable sole-handoff count mismatch")
                        if any(
                            r["model_calls"] != len(r["calls"])
                            or r["model_calls"] > 2
                            or r["attempt_count"] > 3
                            for r in info["revisions"]
                        ):
                            raise ValueError(
                                "Durable model reservation/attempt accounting mismatch"
                            )
                    else:
                        counts_after = await asyncio.to_thread(control_counts, engine)
                        record.update(
                            handoff=False,
                            correct=response.status_code == case.get("expected_http_status")
                            and counts_before == counts_after,
                            rejection=response.json(),
                            classification="no_call_http_rejection",
                            counts_before=counts_before,
                            counts_after=counts_after,
                        )
                    result["cases"].append(record)
                    write(folder / "inside.json", result)
                if args.suite == "copilot":
                    clear = [r for r in result["cases"] if r["category"] == "clear"]
                    negative = [r for r in result["cases"] if r["category"] != "clear"]
                    passed = (
                        len(clear) == 20
                        and len(negative) == 40
                        and sum(r["correct"] for r in clear) >= 18
                        and not any(r["handoff"] for r in negative)
                    )
                    result.update(
                        clear_correct=sum(r["correct"] for r in clear),
                        negative_handoffs=sum(r["handoff"] for r in negative),
                    )
                else:
                    passed = len(result["cases"]) == 8 and all(
                        r["correct"] for r in result["cases"]
                    )
            elif args.suite == "memo":
                for case in frozen["memo_runs"][args.cohort]:
                    identity = case["run_id"]
                    if case["mode"] == "preexisting_explicit_enqueue":
                        response = await post(
                            f"/v2/research/runs/{identity}/memo",
                            {"schema": "memo-request-v2"},
                            prefix + "." + case["id"],
                        )
                        response.raise_for_status()
                    else:
                        pending = await asyncio.to_thread(memo.inspect, identity)
                        if pending["state"] != "queued" or pending["model_calls"] != 0:
                            raise ValueError("Frozen fresh memo has already been dispatched")
                    await finish(memo, identity)
                    info = await asyncio.to_thread(memo_store.inspect, engine, identity)
                    trace = await asyncio.to_thread(ledger, engine, identity, "memo")
                    if not call_inputs_match(trace["calls"], case["preflight"]):
                        raise ValueError("Actual memo call inputs differ from frozen review")
                    text, manifest = (
                        await asyncio.to_thread(memo.read, identity)
                        if info["state"] == "succeeded"
                        else (None, None)
                    )
                    summary, summary_hash = await asyncio.to_thread(
                        research.read, identity, "summary"
                    )
                    correct = (
                        text in case["expected_memo_variants"]
                        and summary == case["summary"]
                        and summary_hash == case["summary_sha256"]
                        and info["model_calls"] == len(trace["calls"])
                        and info["model_calls"] <= 2
                        and info["attempt_count"] <= 3
                    )
                    result["cases"].append(
                        {
                            "id": case["id"],
                            "run_id": identity,
                            "status": info,
                            "ledger": trace,
                            "memo": text,
                            "manifest": manifest,
                            "correct": correct,
                            "sentence_grounding": (
                                "exact comparison to independently reviewed frozen "
                                "three-paragraph render variants"
                            ),
                        }
                    )
                    write(folder / "inside.json", result)
                passed = len(result["cases"]) == 20 and all(r["correct"] for r in result["cases"])
            else:
                sequence = next(
                    s for s in fixture["clarification_sequences"] if s["id"] == args.cohort
                )
                response = await post(
                    "/v2/copilot/requests", sequence["request"], prefix + ".create"
                )
                response.raise_for_status()
                identity = response.json()["request_id"]
                for revision in range(6):
                    await finish(copilot, identity)
                    info = await asyncio.to_thread(copilot_store.inspect, engine, identity)
                    actual_calls = await asyncio.to_thread(ledger, engine, identity, "copilot")
                    for item in info["revisions"]:
                        calls = [c for c in actual_calls["calls"] if c["job_id"] == item["job_id"]]
                        if not call_inputs_match(calls, sequence["preflights"][item["revision"]]):
                            raise ValueError(
                                "Actual clarification inputs differ from frozen review"
                            )
                    if (
                        info["current_revision"] != revision
                        or len(info["revisions"]) != revision + 1
                        or info["revisions"][-1]["model_calls"] < 1
                    ):
                        raise ValueError("Actual clarification revision/response missing")
                    result["cases"].append(
                        {
                            "revision": revision,
                            "status": info,
                            "ledger": await asyncio.to_thread(ledger, engine, identity, "copilot"),
                        }
                    )
                    write(folder / "inside.json", result)
                    if revision < 5:
                        if info["outcome"] != "needs_clarification" or info["run_id"] is not None:
                            raise ValueError("Literal clarification became terminal too early")
                        answer = await post(
                            f"/v2/copilot/requests/{identity}/clarifications",
                            sequence["answers"][revision],
                            prefix + f".answer{revision}",
                        )
                        answer.raise_for_status()
                before = await asyncio.to_thread(copilot_store.inspect, engine, identity)
                trace_before = await asyncio.to_thread(ledger, engine, identity, "copilot")
                rejects = []
                for field, expected in (("sixth_answer", 422), ("stale_answer", 409)):
                    rejected = await post(
                        f"/v2/copilot/requests/{identity}/clarifications",
                        sequence[field],
                        prefix + "." + field,
                    )
                    rejects.append(
                        {
                            "case": field,
                            "http_status": rejected.status_code,
                            "body": rejected.json(),
                        }
                    )
                    if rejected.status_code != expected:
                        raise ValueError("Clarification rejection HTTP status mismatch")
                replay = await post(
                    f"/v2/copilot/requests/{identity}/clarifications",
                    sequence["answers"][0],
                    prefix + ".answer0",
                )
                if (
                    replay.status_code != 200
                    or replay.json()["revision"] != 1
                    or replay.json()["replayed"] is not True
                ):
                    raise ValueError("Old accepted answer replay did not preserve its revision")
                after = await asyncio.to_thread(copilot_store.inspect, engine, identity)
                trace_after = await asyncio.to_thread(ledger, engine, identity, "copilot")
                passed = (
                    before == after
                    and trace_before == trace_after
                    and before["outcome"] == sequence["expected_final_outcome"]
                    and before["revisions"][-1]["spec"] == sequence["expected_spec"]
                    and trace_after["handoffs"] == 1
                )
                result.update(rejections=rejects, replay=replay.json())
            result["functional"] = "passed" if passed else "failed"
            return result
        except BaseException as error:
            result.update(functional="failed", exception_type=type(error).__name__)
            raise
        finally:
            write(folder / "inside.json", result)
            await close_services(engine, bars, research)


def verify_container(cfg: dict[str, Any]) -> dict[str, Any]:
    expected = cfg["_private"]
    inventory = cfg["_postgres_inventory"]
    actual = json.loads(
        subprocess.check_output(["docker", "inspect", inventory["container_id"]], timeout=15)
    )[0]
    if (
        actual["Id"] != inventory["container_id"]
        or actual["Image"] != inventory["image"]
        or inventory["owner"] != OWNER
        or actual["Config"]["Labels"].get("marketlab.v2phase5.owner") != OWNER
        or actual["Mounts"] != [inventory["mount"]]
        or inventory["mount"]["Name"] != expected["volume"]
        or inventory["name"] != str(expected["container"]).lstrip("/")
        or actual["Name"].lstrip("/") != str(expected["container"]).lstrip("/")
        or not actual["State"]["Running"]
        or not any(m.get("Name") == expected["volume"] for m in actual["Mounts"])
        or actual["NetworkSettings"]["Ports"].get("5432/tcp")
        != [{"HostIp": "127.0.0.1", "HostPort": "55485"}]
    ):
        raise ValueError("Exact owned PostgreSQL container/mount/endpoint mismatch")
    volume = json.loads(
        subprocess.check_output(["docker", "volume", "inspect", expected["volume"]], timeout=15)
    )[0]
    if (
        volume["Name"] != expected["volume"]
        or volume["Labels"].get("marketlab.v2phase5.owner") != OWNER
    ):
        raise ValueError("Exact owned PostgreSQL volume label mismatch")
    return {
        "id": actual["Id"],
        "name": actual["Name"],
        "image": actual["Image"],
        "labels": actual["Config"]["Labels"],
        "mounts": actual["Mounts"],
        "started_at": actual["State"]["StartedAt"],
    }


def verify_redis(cfg: dict[str, Any]) -> dict[str, Any]:
    expected = cfg["_redis_inventory"]
    actual = json.loads(
        subprocess.check_output(["docker", "inspect", expected["container_id"]], timeout=15)
    )[0]
    if (
        expected["owner"] != OWNER
        or expected["redis_url"] != cfg["redis_url"]
        or actual["Id"] != expected["container_id"]
        or actual["Name"].lstrip("/") != expected["name"]
        or actual["Image"] != expected["image"]
        or expected["image"]
        != "sha256:57e4255cc971b1c8d6f8a6ca283ac01bc3ecdd914273ef6bfaede87aaecd6541"
        or expected["owner_label"] != "marketlab.owner"
        or actual["Config"]["Labels"].get(expected["owner_label"]) != OWNER
        or actual["Mounts"] != expected["mounts"]
        or not actual["State"]["Running"]
        or actual["NetworkSettings"]["Ports"].get("6379/tcp")
        != [{"HostIp": "127.0.0.1", "HostPort": "56395"}]
    ):
        raise ValueError("Exact owned Redis identity/image/mount/label/endpoint mismatch")
    volume = json.loads(
        subprocess.check_output(["docker", "volume", "inspect", expected["volume"]], timeout=15)
    )[0]
    if (
        volume["Name"] != expected["volume"]
        or volume["Labels"].get(expected["owner_label"]) != OWNER
        or not any(m.get("Name") == expected["volume"] for m in actual["Mounts"])
    ):
        raise ValueError("Exact owned Redis volume label mismatch")
    return {
        "id": actual["Id"],
        "image": actual["Image"],
        "mounts": actual["Mounts"],
        "started_at": actual["State"]["StartedAt"],
    }


def command(
    argv: list[str],
    output: Path,
    *,
    env: dict[str, str] | None = None,
    input_file: Path | None = None,
) -> None:
    # Child commands inherit the containing private Job. No commands contain secrets.
    with output.open("xb") as target:
        with input_file.open("rb") if input_file else open(os.devnull, "rb") as source:
            subprocess.run(
                argv,
                cwd=ROOT,
                env=env,
                stdin=source,
                stdout=target,
                stderr=subprocess.STDOUT,
                timeout=300,
                check=True,
            )


def migrate(cfg: dict[str, Any], revision: str, folder: Path, label: str) -> None:
    command(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        folder / f"{label}-migration.log",
        env=environment(cfg),
    )


def filesystem(root: Path) -> dict[str, dict[str, Any]]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise ValueError("Owned filesystem inventory encountered a link")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = {
                "bytes": path.stat().st_size,
                "sha256": sha(path),
            }
    return result


def database(engine: Any) -> dict[str, Any]:
    import v2_phase4_snapshot

    return dict(v2_phase4_snapshot.snapshot(engine))  # type: ignore[no-untyped-call]


def create_database(cfg: dict[str, Any], name: str) -> None:
    import sqlalchemy as sa

    if not re.fullmatch(r"v2p5_eval_[a-z0-9_]{1,48}", name):
        raise ValueError("Owned database name rejected")
    engine = sa.create_engine(
        cfg["database_url"].set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    try:
        with engine.connect() as connection:
            if connection.execute(
                sa.text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": name}
            ).first():
                raise ValueError(
                    "Evaluation database must be newly owned; never overwrite or resume"
                )
            connection.exec_driver_sql('CREATE DATABASE "' + name + '"')
    finally:
        engine.dispose()


def backup_restore(
    cfg: dict[str, Any], folder: Path, label: str, *, copy_root: bool
) -> dict[str, Any]:
    import sqlalchemy as sa
    import v2_phase4_snapshot

    verify_container(cfg)
    name = cfg["database_name"] + "_" + label
    if len(name) > 63:
        raise ValueError("Owned restore database name exceeds PostgreSQL bound")
    create_database(cfg, name)
    dump = folder / f"{label}.dump"
    # PostgreSQL local socket authentication in this exact owned container; no password in argv.
    with dump.open("xb") as output:
        subprocess.run(
            [
                "docker",
                "exec",
                cfg["_private"]["container"],
                "pg_dump",
                "-U",
                "phase5",
                "-Fc",
                "-d",
                cfg["database_name"],
            ],
            stdout=output,
            stderr=subprocess.PIPE,
            timeout=300,
            check=True,
        )
    command(
        [
            "docker",
            "exec",
            "-i",
            cfg["_private"]["container"],
            "pg_restore",
            "-U",
            "phase5",
            "--exit-on-error",
            "--no-owner",
            "-d",
            name,
        ],
        folder / f"{label}-restore.log",
        input_file=dump,
    )
    original = sa.create_engine(cfg["database_url"])
    restored = sa.create_engine(cfg["database_url"].set(database=name))
    try:
        before, after = database(original), database(restored)
        normalized = v2_phase4_snapshot.compare(before, after, restored)  # type: ignore[no-untyped-call]
        result: dict[str, Any] = {
            "database": name,
            "dump_sha256": sha(dump),
            "dump_bytes": dump.stat().st_size,
            "source_snapshot_sha256": digest(before),
            "restored_snapshot_sha256": digest(after),
            "server_check_normalizations": normalized,
            "database_verified": True,
        }
        if copy_root:
            root = cfg["storage_path"]
            before_files = filesystem(root)
            required = sum(v["bytes"] for v in before_files.values())
            if shutil.disk_usage(folder).free < required + 50 * 1024**3:
                raise ValueError("Backup copy plus unchanged physical headroom unavailable")
            backup = contained(folder / f"{label}-root")
            shutil.copytree(root, backup)
            if filesystem(backup) != before_files or filesystem(root) != before_files:
                raise ValueError("Filesystem backup or quiescence mismatch")
            result.update(root=str(backup), files_sha256=digest(before_files), bytes=required)
            write(folder / f"{label}-files.json", before_files)
        write(folder / f"{label}-backup-restore.json", result)
        return result
    finally:
        original.dispose()
        restored.dispose()


def copy_register(engine: Any, root: Path, alias: str, source: dict[str, Any]) -> dict[str, Any]:
    import sqlalchemy as sa

    from marketlab.datasets.publication import dataset_versions
    from marketlab.datasets.v2 import catalog, core
    from marketlab.datasets.v2.artifacts import verify_dataset

    path = ROOT / source["retained_manifest"]
    manifest = read(path)
    artifact = path.parent / manifest["artifact"]["path"]
    if (
        not path.resolve().is_relative_to(ROOT)
        or path.is_symlink()
        or artifact.parent != path.parent
        or artifact.is_symlink()
        or sha(artifact) != manifest["artifact"]["sha256"]
        or artifact.stat().st_size != manifest["artifact"]["bytes"]
        or manifest["dataset_version_id"] != source["dataset_version_id"]
    ):
        raise ValueError("Retained source package verification failed")
    legacy = "legacy_catalog_receipt" in source
    if legacy:
        records = read(ROOT / source["legacy_catalog_receipt"])["catalog"]
        registration = next(
            r for r in records if r["dataset_version_id"] == source["dataset_version_id"]
        )
        if sha(path) != registration["manifest_sha256"]:
            raise ValueError("Legacy retained registration does not match immutable manifest")
        relative = registration["manifest_path"]
    else:
        verify_dataset(path.parent)
        metadata = manifest["instrument"]
        body = {
            k: metadata[k]
            for k in (*[x for x in core.SEMANTIC if x != "instrument_id"], "display_name")
        }
        core.add_instrument(engine, body, "p5.restore." + alias)
        relative = f"datasets-v2/{source['dataset_version_id']}/manifest.json"
    destination = root / relative
    if not destination.resolve().is_relative_to(root.resolve()) or destination.exists():
        raise ValueError("Restore destination must be new and contained")
    destination.parent.mkdir(parents=True, exist_ok=False)
    package_files = [path, artifact]
    if not legacy:
        package_files.append(path.parent / "quality.json")
    for source_file in package_files:
        target = destination.parent / source_file.name
        shutil.copyfile(source_file, target)
        if sha(target) != sha(source_file):
            raise ValueError("Copied immutable source package hash mismatch")
    with engine.begin() as connection:
        if legacy:
            row = dict(registration)
            row["trade_date"] = date.fromisoformat(row["trade_date"])
            row["published_at"] = datetime.fromisoformat(row["published_at"])
            connection.execute(dataset_versions.insert().values(**row))
        else:
            identity, quality = manifest["identity"], manifest["quality"]
            table = sa.Table("v2_dataset_versions", sa.MetaData(), autoload_with=connection)
            row = {
                "dataset_version_id": manifest["dataset_version_id"],
                "instrument_id": source["instrument_id"],
                "semantic_sha256": identity["instrument_semantic_sha256"],
                "trade_date": date.fromisoformat(source["trade_date"]),
                **{
                    k: identity[k]
                    for k in (
                        "source_sha256",
                        "metadata_sha256",
                        "schema_version",
                        "transform_version",
                        "lock_sha256",
                    )
                },
                "logical_sha256": quality["logical_sha256"],
                "manifest_sha256": sha(destination),
                "manifest_relative_path": relative,
                "row_count": quality["accepted_rows"],
                "observed_from": datetime.fromisoformat(
                    quality["observed_from"].replace("Z", "+00:00")
                ),
                "observed_through": datetime.fromisoformat(
                    quality["observed_through"].replace("Z", "+00:00")
                ),
                "published_at": datetime.now(UTC),
            }
            connection.execute(table.insert().values(**row))
    verified = catalog.inspect_version(engine, root, source["dataset_version_id"])
    return {
        "version": source["dataset_version_id"],
        "manifest_sha256": sha(destination),
        "manifest": relative,
        "verified_manifest_sha256": digest(verified),
        "retained_source_sha256": sha(path),
    }


async def numerical_reference(
    research: Any, body: dict[str, Any], folder: Path, key: str
) -> dict[str, Any]:
    from v2_phase3_acceptance import independent_reference, verified_oracle

    from marketlab.research.v2.spec import ResearchSpec

    spec = ResearchSpec.create(body)
    rows = await asyncio.to_thread(research.bars._catalog, tuple(spec.dataset_versions))
    inputs: dict[str, list[dict[str, Any]]] = {identity: [] for identity in spec.instrument_ids}
    metadata = {r["instrument_id"]: r["metadata"] for r in rows}
    for row in rows:
        bars = await asyncio.to_thread(
            verified_oracle, research.bars, row, spec.history_start, spec.end
        )
        inputs[row["instrument_id"]].extend(bars["5m"])
    for values in inputs.values():
        values.sort(key=lambda item: item["start"])
    expected = await asyncio.to_thread(independent_reference, body, inputs, metadata)
    run_id, replayed = await research.submit(spec, key)
    if replayed or await research.work(1, run_id) != 1:
        raise ValueError("Fresh numerical preparation did not execute exactly once")
    info = await asyncio.to_thread(research.inspect, run_id)
    if info["state"] != "succeeded" or info["attempt_count"] != 1:
        raise ValueError("Actual numerical prerequisite failed")
    hashes = {}
    for kind, oracle in zip(("results", "summary"), expected, strict=True):
        actual, actual_sha = await asyncio.to_thread(research.read, run_id, kind)
        if actual != oracle or actual_sha != digest(oracle):
            raise ValueError("Independent complete Decimal numerical prerequisite mismatch")
        hashes[kind] = actual_sha
        write(folder / f"{run_id}-{kind}.json", actual)
    return {
        "run_id": run_id,
        "spec": body,
        "hashes": hashes,
        "attempt_count": 1,
        "reference": (
            "unchanged independent Phase3 generalized Decimal adapter and R4 oracle; "
            "raw source bars independently scanned"
        ),
    }


async def prepare(args: argparse.Namespace, cfg: dict[str, Any], folder: Path) -> dict[str, Any]:
    import sqlalchemy as sa

    from marketlab.datasets.v2 import admission, catalog, core, jobs
    from marketlab.datasets.v2 import service as ingestion

    literal = read(args.fixtures)
    planned = read(args.plan)
    if planned["fixtures_sha256"] != sha(args.fixtures) or planned["source_files"] != sources():
        raise ValueError("Approved preparation source/fixture identity changed")
    container_before = await asyncio.to_thread(verify_container, cfg)
    if cfg["storage_path"].exists():
        raise ValueError("Preparation requires a fresh nonexistent owned storage root")
    redis_before = await asyncio.to_thread(verify_redis, cfg)
    required = planned["minimum_copy_and_backup_bytes"] + planned["physical_headroom_bytes"]
    if shutil.disk_usage(folder).free < required:
        raise ValueError(
            "Selected source+backup copies and unchanged 50GiB physical headroom unavailable"
        )
    await asyncio.to_thread(create_database, cfg, cfg["database_name"])
    await asyncio.to_thread(backup_restore, cfg, folder, "empty", copy_root=False)
    await asyncio.to_thread(migrate, cfg, "0010_v2_browser_imports", folder, "0010")
    cfg["storage_path"].mkdir(parents=True, exist_ok=False)
    engine, bars, research, _, memo = services(cfg)
    result: dict[str, Any] = {
        "schema": "phase5-evaluation-prepared-v1",
        "fixtures_sha256": sha(args.fixtures),
        "source_files": sources(),
        "bindings": {},
        "registrations": {},
        "memo_runs": {"A": {}, "B": {}},
        "functional": "incomplete",
        "models_dispatched": 0,
        "config_sha256": sha(args.config),
    }
    try:
        for alias, source in literal["sources"].items():
            if source["retained_manifest"] is None:
                continue
            if (
                sha(ROOT / source["retained_manifest"])
                != planned["retained_sources"][alias]["manifest_sha256"]
            ):
                raise ValueError("Planned retained manifest changed before preparation")
            if "legacy_catalog_receipt" in source and (
                sha(ROOT / source["legacy_catalog_receipt"])
                != planned["retained_sources"][alias]["legacy_catalog_sha256"]
            ):
                raise ValueError("Planned retained registration receipt changed")
            record = await asyncio.to_thread(
                copy_register, engine, cfg["storage_path"], alias, source
            )
            result["registrations"][alias] = record
            result["bindings"][alias] = source["dataset_version_id"]
            write(folder / "prepared.json", result)
        hostile = literal["hostile_metadata"]
        with engine.connect() as connection:
            before_metadata = core.instrument(connection, hostile["instrument_id"])
        await asyncio.to_thread(
            core.update_instrument,
            engine,
            hostile["instrument_id"],
            {
                "expected_revision": before_metadata["revision"],
                "display_name": hostile["display_name"],
            },
            "p5.hostile-display-metadata",
        )
        with engine.connect() as connection:
            after_metadata = core.instrument(connection, hostile["instrument_id"])
        if before_metadata["semantic_sha256"] != after_metadata["semantic_sha256"]:
            raise ValueError("Owned display-only probe changed instrument semantics")
        result["owned_hostile_metadata"] = {
            "instrument_id": hostile["instrument_id"],
            "before": core.wire(before_metadata),
            "after": core.wire(after_metadata),
        }
        receipt = await asyncio.to_thread(admission.initialize, engine, cfg["storage_path"])
        result["initial_capacity"] = receipt
        if "ethbtc_mar01" not in result["bindings"]:
            source = literal["sources"]["ethbtc_mar01"]
            verified_metadata = cfg["ethbtc_metadata"]
            if verified_metadata != {
                "venue_id": "binance",
                "market": "spot",
                "source_symbol": "ETHBTC",
                "base_asset": "ETH",
                "quote_asset": "BTC",
                "display_name": "ETH/BTC",
                "trade_id_order": "numeric",
                "adapter": "binance_daily",
            }:
                raise ValueError(
                    "Exact operator-verified official ETH/BTC semantic metadata required"
                )
            semantic_receipt = read(contained(Path(cfg["ethbtc_metadata_receipt"])))
            if (
                semantic_receipt.get("metadata_sha256") != digest(verified_metadata)
                or semantic_receipt.get("verified") is not True
                or sha(Path(cfg["ethbtc_metadata_receipt"]))
                != cfg["ethbtc_metadata_receipt_sha256"]
            ):
                raise ValueError(
                    "Independent actual registry evidence is required before acquisition"
                )
            official_response = contained(Path(semantic_receipt["source_path"]))
            if (
                sha(official_response) != semantic_receipt["source_sha256"]
                or semantic_receipt["source_url"]
                != "https://data-api.binance.vision/api/v3/exchangeInfo?symbol=ETHBTC"
            ):
                raise ValueError("Saved official ETHBTC evidence changed")
            symbols = read(official_response)["symbols"]
            expected_symbol = {
                "symbol": "ETHBTC",
                "baseAsset": "ETH",
                "quoteAsset": "BTC",
                "status": "TRADING",
                "isSpotTradingAllowed": True,
            }
            if len(symbols) != 1 or any(symbols[0].get(k) != v for k, v in expected_symbol.items()):
                raise ValueError(
                    "Saved official ETHBTC metadata does not prove the reviewed mapping"
                )
            await asyncio.to_thread(
                core.add_instrument, engine, verified_metadata, "p5.ethbtc.registry"
            )
            submission = await asyncio.to_thread(
                jobs.submit,
                engine,
                {
                    "schema": "daily-ingestion-v2",
                    "adapter": "binance_daily",
                    "instrument_ids": [source["instrument_id"]],
                    "from_date": "2025-03-01",
                    "before_date": "2025-03-02",
                },
                "p5.ethbtc.official",
            )
            submission_id = submission.get("submission_id", submission.get("id"))
            if not submission_id:
                raise ValueError("Official ingestion did not identify its durable submission")
            await asyncio.to_thread(
                ingestion.work,
                engine,
                cfg["storage_path"],
                max_jobs=1,
                submission_id=submission_id,
                wait_seconds=0,
            )
            status = await asyncio.to_thread(jobs.inspect_submission, engine, submission_id)
            published = [
                job["result_version"] for job in status["jobs"] if job["state"] == "succeeded"
            ]
            if len(published) != 1:
                write(folder / "ethbtc-ingestion-failure.json", status)
                raise ValueError(
                    "Actual official ETHBTC prerequisite not published; no synthetic substitution"
                )
            manifest = await asyncio.to_thread(
                catalog.inspect_version, engine, cfg["storage_path"], published[0]
            )
            if manifest["source"]["kind"] != "official_archive":
                raise ValueError("ETHBTC source is not official Binance data")
            result["bindings"]["ethbtc_mar01"] = published[0]
            result["registrations"]["ethbtc_mar01"] = {"submission": status, "manifest": manifest}
        bound = replace_versions(literal, result["bindings"])
        for cohort in ("A", "B"):
            for case in bound["memo_cases"]:
                if case["mode"] != "preexisting_explicit_enqueue":
                    continue
                entry = await numerical_reference(
                    research, case["expected_spec"], folder, "p5.pre." + cohort + "." + case["id"]
                )
                entry["origin"] = (
                    "genuine current-source numerical execution at schema0010; "
                    "not historical-binary output"
                )
                result["memo_runs"][cohort][case["id"]] = entry
                write(folder / "prepared.json", result)
        # No writer remains; retain a verified dump+filesystem snapshot BEFORE migration.
        result["preupgrade_backup"] = await asyncio.to_thread(
            backup_restore, cfg, folder, "preupgrade", copy_root=True
        )
        rehearsal = dict(
            cfg,
            database_name=result["preupgrade_backup"]["database"],
            database_url=cfg["database_url"].set(database=result["preupgrade_backup"]["database"]),
        )
        await asyncio.to_thread(
            migrate, rehearsal, "0011_v2_copilot_memos", folder, "rehearsal0011"
        )
        restored_cfg = dict(rehearsal, storage_path=Path(result["preupgrade_backup"]["root"]))
        restored_engine, restored_bars, restored_research, _, _ = services(restored_cfg)
        try:
            for version in result["bindings"].values():
                await asyncio.to_thread(
                    catalog.inspect_version, restored_engine, restored_cfg["storage_path"], version
                )
            for cohort in result["memo_runs"].values():
                for entry in cohort.values():
                    for kind, expected in entry["hashes"].items():
                        actual, value_sha = await asyncio.to_thread(
                            restored_research.read, entry["run_id"], kind
                        )
                        if value_sha != expected or digest(actual) != expected:
                            raise ValueError("Isolated backup restore/readback failed")
            with restored_engine.connect() as connection:
                if (
                    connection.execute(sa.text("SELECT count(*) FROM v2_memo_jobs")).scalar_one()
                    != 0
                ):
                    raise ValueError("Migration silently backfilled memo work")
            result["rehearsal_verified"] = True
        finally:
            await close_services(restored_engine, restored_bars, restored_research)
        await asyncio.to_thread(migrate, cfg, "0011_v2_copilot_memos", folder, "actual0011")
        result["postupgrade_capacity"] = await asyncio.to_thread(
            admission.initialize, engine, cfg["storage_path"]
        )
        for cohort in ("A", "B"):
            for case in bound["memo_cases"]:
                if case["mode"] != "fresh_automatic_pending":
                    continue
                entry = await numerical_reference(
                    research, case["expected_spec"], folder, "p5.fresh." + cohort + "." + case["id"]
                )
                pending = await asyncio.to_thread(memo.inspect, entry["run_id"])
                if pending["state"] != "queued" or pending["model_calls"] != 0:
                    raise ValueError(
                        "Fresh numerical memo was not atomically queued without dispatch"
                    )
                entry["origin"] = (
                    "genuine current-source numerical execution at schema0011; "
                    "automatic unspent pending memo"
                )
                result["memo_runs"][cohort][case["id"]] = entry
                write(folder / "prepared.json", result)
        if await asyncio.to_thread(verify_container, cfg) != container_before:
            raise ValueError("Owned PostgreSQL identity changed during prerequisite preparation")
        if await asyncio.to_thread(verify_redis, cfg) != redis_before:
            raise ValueError("Owned Redis identity changed during prerequisite preparation")
        result["functional"] = "passed"
        return result
    except BaseException as error:
        result.update(functional="failed", exception_type=type(error).__name__)
        raise
    finally:
        write(folder / "prepared.json", result)
        await close_services(engine, bars, research)


def preparation_history(engine: Any) -> dict[str, Counter[str]]:
    from sqlalchemy import text

    from marketlab.inference import INFERENCE_LOCK

    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        connection.execute(text("SET LOCAL statement_timeout='15s'"))
        connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
        if connection.execute(
            text(
                "SELECT 1 FROM pg_stat_activity WHERE datname=current_database() "
                "AND pid<>pg_backend_pid() AND state<>'idle' UNION ALL "
                "SELECT 1 FROM pg_locks WHERE locktype='advisory' AND granted "
                "AND database=(SELECT oid FROM pg_database WHERE datname=current_database()) "
                "AND classid=:hi AND objid=:lo UNION ALL "
                "SELECT 1 FROM v2_admission_tickets WHERE state<>'released'"
            ),
            {"hi": (INFERENCE_LOCK >> 32) & 0xFFFFFFFF, "lo": INFERENCE_LOCK & 0xFFFFFFFF},
        ).first():
            raise ValueError("Owned prerequisite database must be quiescent")
        if connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() != (
            "0011_v2_copilot_memos"
        ):
            raise ValueError("Existing preparation requires current schema without migration")
        history = {}
        for table in (
            "v2_research_submissions",
            "v2_research_selections",
            "v2_research_runs",
            "v2_research_attempts",
            "v2_research_results",
            "v2_research_operations",
            "v2_research_reservations",
            "v2_admission_tickets",
            "v2_copilot_requests",
            "v2_copilot_revisions",
            "v2_copilot_jobs",
            "v2_copilot_attempts",
            "v2_copilot_calls",
            "v2_memo_jobs",
            "v2_memo_attempts",
            "v2_memo_calls",
            "v2_memo_results",
            "v2_memo_operations",
            "copilot_requests",
            "copilot_revisions",
            "copilot_jobs",
            "copilot_attempts",
            "memo_jobs",
            "memo_attempts",
            "memo_results",
        ):
            rows = (
                connection.execute(text(f"SELECT to_jsonb(t)::text FROM {table} t LIMIT 10001"))
                .scalars()
                .all()
            )
            if len(rows) > 10000:
                raise ValueError("Bounded preparation history exceeded")
            history[table] = Counter(rows)
        return history


def verify_preparation_history(
    before: dict[str, Counter[str]], after: dict[str, Counter[str]], fresh: set[str]
) -> None:
    numerical = {
        "v2_research_submissions",
        "v2_research_selections",
        "v2_research_runs",
        "v2_research_attempts",
        "v2_research_results",
        "v2_research_reservations",
        "v2_admission_tickets",
        "v2_memo_jobs",
    }
    if before.keys() != after.keys():
        raise ValueError("Preparation history tables changed")
    for table, old in before.items():
        if old - after[table] or (table not in numerical and old != after[table]):
            raise ValueError("Historical rows or model evidence changed")
    for table in (
        "v2_research_runs",
        "v2_research_results",
        "v2_research_attempts",
        "v2_memo_jobs",
    ):
        new = list((after[table] - before[table]).elements())
        if len(new) != len(fresh) or {json.loads(row)["run_id"] for row in new} != fresh:
            raise ValueError("Preparation added unexpected numerical or memo rows")


async def prepare_existing(
    args: argparse.Namespace, cfg: dict[str, Any], folder: Path
) -> dict[str, Any]:
    from marketlab.datasets.v2.common import V2Error
    from marketlab.memos.v2 import store as memo_store

    plan, previous = read(args.plan), read(args.prepared)
    development_path = contained(args.bound)
    development = read(development_path)
    current = sources()
    previous_sources = previous["source_files"]
    evaluator = "scripts/v2_phase5_model_eval.py"
    allowed = {evaluator, "src/marketlab/copilot/v2/model.py"}
    development_sources = development["source_files"]
    archive = contained(development_path.with_name("evaluator-before-restore-readback.py"))
    derivation = {
        "archive": archive.relative_to(ROOT).as_posix(),
        "before_sha256": sha(archive),
        "after_sha256": current[evaluator],
    }
    if (
        plan["schema"] != "phase5-v7-prepare-existing-v1"
        or plan["source_files"] != current
        or plan["config_sha256"] != sha(args.config)
        or plan["prepared_sha256"] != sha(args.prepared)
        or plan["development_sha256"] != sha(development_path)
        or plan["development_supervisor_sha256"] != sha(development_path.with_name("result.json"))
        or read(development_path.with_name("result.json"))["state"] != "passed"
        or development["functional"] != "passed"
        or plan["development_evaluator_derivation"] != derivation
        or development_sources.get(evaluator) != derivation["before_sha256"]
        or development_sources | {evaluator: current[evaluator]} != current
        or len(development["cases"]) != 8
        or not all(case["correct"] for case in development["cases"])
        or previous["functional"] != "passed"
        or previous["fixtures_sha256"] != sha(args.fixtures)
        or previous["config_sha256"] != sha(args.config)
        or previous_sources.keys() != current.keys()
        or {p for p in current if current[p] != previous_sources[p]} != allowed
    ):
        raise ValueError("Exact reviewed development and existing preparation inputs required")
    fixture = read(args.fixtures)
    validate_fixture(fixture)
    cases = replace_versions(fixture, previous["bindings"])["memo_cases"]
    engine, bars, research, _, memo = services(cfg)
    result: dict[str, Any] = {
        "schema": previous["schema"],
        "functional": "failed",
        "source_files": current,
        "fixtures_sha256": previous["fixtures_sha256"],
        "config_sha256": previous["config_sha256"],
        "bindings": previous["bindings"],
        "registrations": previous["registrations"],
        "memo_runs": {"A": {}, "B": {}},
        "models_dispatched": 0,
        "reuse_provenance": {
            "prepared_sha256": sha(args.prepared),
            "development_sha256": sha(development_path),
            "development_evaluator_derivation": derivation,
            "source_derivation": {p: [previous_sources[p], current[p]] for p in sorted(allowed)},
        },
    }
    try:
        before = await asyncio.to_thread(preparation_history, engine)
        write(folder / "preserved-before.json", before)
        backup = await asyncio.to_thread(backup_restore, cfg, folder, "pv7before", copy_root=True)
        result["current_backup"] = backup
        retained = [entry for group in previous["memo_runs"].values() for entry in group.values()]
        old = {entry["run_id"] for entry in retained}
        if len(retained) != 40 or len(old) != 40:
            raise ValueError("Expected forty distinct retained numerical results")
        restored_cfg = dict(
            cfg,
            database_name=backup["database"],
            database_url=cfg["database_url"].set(database=backup["database"]),
            storage_path=contained(Path(backup["root"])),
        )
        restored_engine, restored_bars, restored_research, _, _ = services(restored_cfg)
        try:
            if await asyncio.to_thread(preparation_history, restored_engine) != before:
                raise ValueError("Restored preparation history differs from source")
            for entry in retained:
                for kind in ("results", "summary"):
                    _, actual = await asyncio.to_thread(
                        restored_research.read, entry["run_id"], kind
                    )
                    if actual != entry["hashes"][kind]:
                        raise ValueError("Restored numerical prerequisite differs")
            result["restored_numerical_readbacks"] = len(retained)
        finally:
            await close_services(restored_engine, restored_bars, restored_research)
        fresh: set[str] = set()
        for cohort in ("A", "B"):
            for case in cases:
                entry = previous["memo_runs"][cohort][case["id"]]
                if entry["spec"] != case["expected_spec"]:
                    raise ValueError("Retained numerical spec differs from literal fixture")
                if case["mode"] == "preexisting_explicit_enqueue":
                    run = entry["run_id"]
                    try:
                        await asyncio.to_thread(memo_store.inspect, engine, run)
                    except V2Error as error:
                        if error.code != "not_found":
                            raise
                    else:
                        raise ValueError("Retained numerical prerequisite is no longer job-free")
                    for kind in ("results", "summary"):
                        _, actual = await asyncio.to_thread(research.read, run, kind)
                        if actual != entry["hashes"][kind]:
                            raise ValueError("Retained numerical prerequisite differs")
                else:
                    if not fresh and await asyncio.to_thread(preparation_history, engine) != before:
                        raise ValueError("Owned history changed before fresh preparation")
                    historical = entry
                    entry = await numerical_reference(
                        research,
                        case["expected_spec"],
                        folder,
                        f"p5.pv7.fresh.{cohort}.{case['id']}",
                    )
                    run = entry["run_id"]
                    pending = await asyncio.to_thread(memo.inspect, run)
                    if (
                        run in old | fresh
                        or entry["hashes"] != historical["hashes"]
                        or pending["state"] != "queued"
                        or pending["attempt_count"] != 0
                        or pending["model_calls"] != 0
                        or pending["execution"] != memo.execution
                    ):
                        raise ValueError("New numerical memo prerequisite differs")
                    fresh.add(run)
                result["memo_runs"][cohort][case["id"]] = entry
                write(folder / "prepared.json", result)
        if len(old) != 40 or len(fresh) != 20:
            raise ValueError("Expected twenty retained and twenty fresh numerical results")
        after = await asyncio.to_thread(preparation_history, engine)
        write(folder / "preserved-after.json", after)
        verify_preparation_history(before, after, fresh)
        files_before = read(folder / "pv7before-files.json")
        files_after = await asyncio.to_thread(filesystem, cfg["storage_path"])
        if any(files_after.get(path) != identity for path, identity in files_before.items()):
            raise ValueError("Retained package or numerical artifact changed")
        result.update(
            functional="passed",
            selected_preexisting=20,
            selected_fresh=20,
            original_histories_unchanged=True,
            retained_files_verified=len(files_before),
        )
        return result
    finally:
        write(folder / "prepared.json", result)
        await close_services(engine, bars, research)


async def inside(args: argparse.Namespace, cfg: dict[str, Any], folder: Path) -> int:
    if not os.environ.get("MARKETLAB_P5_OWNED_NONCE"):
        raise ValueError("Actual operations must be launched through the owned supervisor")
    operation = (
        (prepare_existing(args, cfg, folder) if args.prepared else prepare(args, cfg, folder))
        if args.command == "prepare"
        else bind(args, cfg)
        if args.command == "bind"
        else develop(args, cfg, folder)
        if args.command == "develop"
        else score(args, cfg, folder)
    )
    task = asyncio.create_task(operation)

    async def stop() -> None:
        while not task.done():
            if (folder / "controller-stop.json").exists():
                task.cancel()
                return
            await asyncio.sleep(0.1)

    watcher = asyncio.create_task(stop())
    try:
        result = await task
        name = (
            "bound.json"
            if args.command == "bind"
            else "prepared.json"
            if args.command == "prepare"
            else "inside.json"
        )
        write(folder / name, result)
        return 0 if result.get("functional", "passed") == "passed" else 1
    finally:
        watcher.cancel()
        try:
            await watcher
        except asyncio.CancelledError:
            pass


def supervise(args: argparse.Namespace) -> int:
    from v2_phase4_lifecycle import OwnedJob, supervisor_peak_commit

    target = args.bound if args.command == "score" else args.plan
    approved = approval(
        args.approval,
        args.command,
        target,
    )
    cfg = config(args.config)
    if approved.get("config_sha256") != sha(args.config):
        raise ValueError("Independent approval must bind the exact private owned configuration")
    if approved.get("postgres_receipt_sha256") != cfg["_private_sha256"]:
        raise ValueError("Independent approval must bind the exact owned PostgreSQL receipt")
    folder = contained(args.output)
    folder.mkdir(parents=True, exist_ok=False)
    initial_source = sources()
    receipt: dict[str, Any] = {
        "schema": "phase5-evaluation-invocation-v1",
        "command": args.command,
        "suite": args.suite,
        "cohort": args.cohort,
        "source_files": initial_source,
        "approval_sha256": sha(args.approval),
        "target_sha256": sha(target),
        "started_utc": datetime.now(UTC).isoformat(),
        "functional": "incomplete",
        "lifecycle": "incomplete",
        "owned_sampled_resource": "incomplete",
        "external_service_model_resource": "not_measured_by_this_runner",
        "upstream_inference_cancellation": "not_established_by_client_cancellation",
        "forced_cleanup": False,
        "sample_schedule": {
            "interval_seconds": SAMPLE,
            "maximum_gap_seconds": MAX_GAP,
            "coverage": (
                "private non-breakaway Job aggregate active process count and peak "
                "committed memory, including every owned descendant"
            ),
        },
    }
    write(folder / "execution.json", receipt)
    began = time.monotonic()
    job = OwnedJob()
    stamps: list[float] = []
    sample_errors = []
    stop_sampling = threading.Event()

    def sample() -> None:
        planned = time.monotonic()
        with (folder / "samples.jsonl").open("xb") as output:
            while not stop_sampling.is_set():
                actual = time.monotonic()
                try:
                    observation = {
                        "planned_elapsed": planned - began,
                        "actual_elapsed": actual - began,
                        "active": job.active(),
                        "peak_committed_bytes": job.peak_commit(),
                    }
                    stamps.append(actual)
                    output.write(canonical(observation))
                    output.flush()
                except BaseException as error:
                    sample_errors.append(type(error).__name__)
                planned += SAMPLE
                stop_sampling.wait(max(0, planned - time.monotonic()))

    worker: Any = None
    sampler = threading.Thread(target=sample, name="phase5-owned-job-sampler")
    argv = [
        sys.executable,
        str(Path(__file__).resolve()),
        args.command,
        "--inside",
        "--fixtures",
        str(args.fixtures.resolve()),
        "--config",
        str(args.config.resolve()),
        "--output",
        str(folder),
        "--approval",
        str(args.approval.resolve()),
    ]
    for flag, value in (
        ("--plan", args.plan),
        ("--prepared", args.prepared),
        ("--bound", args.bound),
    ):
        if value:
            argv += [flag, str(value.resolve())]
    if args.command == "score":
        argv += ["--suite", args.suite, "--cohort", args.cohort]
    env = environment(cfg)
    env["MARKETLAB_P5_OWNED_NONCE"] = uuid4().hex
    try:
        sampler.start()
        with (folder / "runner.log").open("xb") as output:
            worker = job.spawn(argv, cwd=ROOT, env=env, output=output)
            receipt["owned_runner"] = worker.record()
            deadline = time.monotonic() + 36000
            while worker.poll() is None and time.monotonic() < deadline:
                time.sleep(0.1)
            if worker.poll() is None:
                write(
                    folder / "controller-stop.json",
                    {
                        "reason": "bounded invocation deadline",
                        "nonce": env["MARKETLAB_P5_OWNED_NONCE"],
                    },
                )
                try:
                    worker.wait(150)
                except subprocess.TimeoutExpired:
                    receipt["forced_cleanup"] = True
                    job.terminate()
            job.wait_empty(30)
        receipt["owned_runner"] = worker.record()
        receipt["final_active"] = job.active()
        receipt["owned_peak_committed_bytes"] = job.peak_commit()
        receipt["supervisor_peak_committed_bytes"] = supervisor_peak_commit()
        receipt["lifecycle"] = (
            "passed"
            if not receipt["forced_cleanup"]
            and worker.returncode in {0, 1}
            and receipt["final_active"] == 0
            else "failed"
        )
        name = (
            "bound.json"
            if args.command == "bind"
            else "prepared.json"
            if args.command == "prepare"
            else "inside.json"
        )
        if (folder / name).is_file():
            receipt["functional"] = read(folder / name, 256 * 1024**2).get("functional", "passed")
        if worker.returncode != 0:
            receipt["functional"] = "failed"
    except BaseException as error:
        receipt.update(functional="failed", exception_type=type(error).__name__)
        if worker and worker.poll() is None:
            write(
                folder / "controller-stop.json",
                {"reason": "supervisor exception", "nonce": env["MARKETLAB_P5_OWNED_NONCE"]},
            )
            try:
                worker.wait(150)
                job.wait_empty(30)
            except (subprocess.TimeoutExpired, TimeoutError):
                receipt["forced_cleanup"] = True
                job.terminate()
        raise
    finally:
        if job.active():
            receipt["forced_cleanup"] = True
            job.terminate()
        # Keep samples through positive native group drain and the final observation.
        time.sleep(SAMPLE)
        stop_sampling.set()
        if sampler.ident is not None:
            sampler.join(5)
        receipt["sample_errors"] = sample_errors
        receipt["sample_count"] = len(stamps)
        receipt["maximum_observed_gap_seconds"] = max(
            (b - a for a, b in zip(stamps, stamps[1:], strict=False)), default=0
        )
        receipt["owned_sampled_resource"] = (
            "passed"
            if (
                len(stamps) >= 2
                and not sample_errors
                and not sampler.is_alive()
                and receipt["maximum_observed_gap_seconds"] <= MAX_GAP
                and 0
                < receipt.get("owned_peak_committed_bytes", 0)
                + receipt.get("supervisor_peak_committed_bytes", 0)
                < CEILING
            )
            else "failed"
        )
        receipt["source_unchanged"] = sources() == initial_source
        receipt["ended_utc"] = datetime.now(UTC).isoformat()
        receipt["elapsed_seconds"] = time.monotonic() - began
        try:
            job.close()
            receipt["owned_handles_closed"] = True
        except BaseException as error:
            receipt["owned_handles_closed"] = False
            receipt["handle_close_exception_type"] = type(error).__name__
            receipt["lifecycle"] = "failed"
        receipt["state"] = (
            "passed"
            if receipt["source_unchanged"]
            and all(
                receipt[k] == "passed"
                for k in ("functional", "lifecycle", "owned_sampled_resource")
            )
            else "failed"
        )
        write(folder / "result.json", receipt)
    return 0 if receipt["state"] == "passed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "prepare", "bind", "score", "develop"))
    parser.add_argument("--fixtures", type=Path, default=FIXTURE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--bound", type=Path)
    parser.add_argument(
        "--suite", choices=("copilot", "memo", "clarification", "faults", "grounding")
    )
    parser.add_argument("--cohort", choices=("A", "B"))
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.command == "plan":
        return plan(args)
    if not args.config or not args.approval or (args.command != "score" and not args.plan):
        parser.error("Owned configuration and exact independent approval/plan required")
    if args.command == "bind" and not args.prepared:
        parser.error("Binding requires the actual prepared numerical prerequisite receipt")
    if args.command == "prepare" and bool(args.prepared) != bool(args.bound):
        parser.error("Existing preparation requires both the prior preparation and development")
    if args.command == "score" and (not args.bound or not args.suite or not args.cohort):
        parser.error("Scoring requires a frozen bound corpus, suite and separate cohort")
    if args.inside:
        target = args.bound if args.command == "score" else args.plan
        approved = approval(args.approval, args.command, target)
        cfg = config(args.config)
        if (
            approved.get("config_sha256") != sha(args.config)
            or approved.get("postgres_receipt_sha256") != cfg["_private_sha256"]
        ):
            raise ValueError("Owned child configuration changed after reviewed launch")
        return asyncio.run(inside(args, cfg, contained(args.output)))
    return supervise(args)


if __name__ == "__main__":
    raise SystemExit(main())
