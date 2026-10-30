"""Actual Phase 3 gates on explicitly owned resources; never original services.

Every invocation retains a unique directory, source inventories and honest failure.
The Decimal bar oracle and retained R4 reference do not use production calculations.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import inspect
import json
import multiprocessing
import os
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import redis
import sqlalchemy as sa

from marketlab.analytics.bars import BarService as LegacyBars
from marketlab.analytics.v2 import BarsRequest
from marketlab.datasets.v2 import capacity, core, jobs
from marketlab.datasets.v2 import service as ingestion
from marketlab.datasets.v2.common import canonical_json, parse_json, safe_path, sha256_file
from marketlab.research.service import ResearchService as LegacyResearch
from marketlab.research.spec import ResearchSpec as LegacySpec
from marketlab.research.v2.service import ResearchService
from marketlab.research.v2.spec import ResearchSpec

PROJECT = Path(__file__).resolve().parents[1]
BASE = PROJECT / "artifacts/v2-phase3-20261029"
_CRASH_OWNERSHIP: dict[str, Any] = {}
RETAINED = {
    "btc_official": "1bb27751caeb4974731dc40e77d174b0e6945f86f0d459025cf3d5cfcda459c2",
    "sol_official": "db545ab86156c1f200813bdf1d25f83f73b64205c2a909d28236ca8a5bf4ca34",
    "sol_csv": "5df7db9b0c46ff8e2d06f31189361fd3bd61c0efe5f2b692badf25cbbfd85a17",
    "sol_parquet": "dd6a8a00466035a84d062e1e3c19ea9d0f3130520017e6b222cff20a9ad3ec07",
}


def marker(path: Path, boundary: str) -> None:
    save(
        path,
        {
            "boundary": boundary,
            "pid": os.getpid(),
            "utc": stamp(datetime.now(UTC)),
            **_CRASH_OWNERSHIP,
        },
    )
    threading.Event().wait()


def process_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "phase3_owned_process_control", PROJECT / "scripts/v2_phase3_processes.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def child_context(plan: dict[str, Any], plan_path: Path) -> dict[str, Any]:
    assert plan["owner"] == "v2-phase3-20261029"
    assert plan_path.resolve().is_relative_to(BASE.resolve())
    for key in ("ready", "start", "marker"):
        assert Path(plan[key]).resolve().parent == plan_path.resolve().parent
    current = process_module().inventory()[os.getpid()]
    plan_hash = sha256_file(plan_path)
    _CRASH_OWNERSHIP.update(birth=current["identity"], plan_sha256=plan_hash)
    ready = {"pid": os.getpid(), **_CRASH_OWNERSHIP}
    save(Path(plan["ready"]), ready)
    return ready


async def child_readiness(plan: dict[str, Any], plan_path: Path) -> None:
    ready = await asyncio.to_thread(child_context, plan, plan_path)
    deadline = time.monotonic() + 60
    while not await asyncio.to_thread(Path(plan["start"]).exists):
        if time.monotonic() >= deadline:
            raise RuntimeError("Owned parent did not authorize worker start")
        await asyncio.to_thread(time.sleep, 0.05)
    assert json.loads(await asyncio.to_thread(Path(plan["start"]).read_bytes)) == ready


def boundary_plan(
    config_path: Path, case: Path, plan: dict[str, Any], invocation: str, mode: str = "crash-child"
) -> tuple[Any, ...]:
    assert mode in {"crash-child", "process-probe-child"}
    assert case.resolve().is_relative_to(BASE.resolve())
    plan = dict(
        plan,
        owner="v2-phase3-20261029",
        ready=str(case / "ready.json"),
        start=str(case / "start.json"),
    )
    path = case / "plan.json"
    save(path, plan)
    command = [
        sys.executable,
        str(PROJECT / "scripts/v2_phase3_acceptance.py"),
        mode,
        "--config",
        str(config_path),
        "--plan",
        str(path),
        "--invocation",
        invocation,
    ]
    allowed = {
        str(Path(sys.executable).resolve()),
        str(Path(getattr(sys, "_base_executable", sys.executable)).resolve()),
    }
    return command, plan, allowed, sha256_file(path)


async def run_boundary(
    config_path: Path, case: Path, plan: dict[str, Any], invocation: str, mode: str = "crash-child"
) -> dict[str, Any]:
    command, prepared, allowed, plan_hash = await asyncio.to_thread(
        boundary_plan, config_path, case, plan, invocation, mode
    )
    return await process_module().run(command, prepared, case, allowed, save, plan_hash)


async def crash_child(value: dict[str, Any], plan: dict[str, Any]) -> None:
    import marketlab.analytics.v2.bars as bar_module
    import marketlab.research.numerics as numerical_module
    from marketlab.research.v2 import store

    plan_path = Path(sys.argv[sys.argv.index("--plan") + 1])
    await child_readiness(plan, plan_path)
    engine = sa.create_engine(value["database_url"])
    base = LegacyBars(engine, Path(value["storage_path"]), value["redis_url"])
    research = ResearchService(base)
    boundary = plan["boundary"]
    target = Path(plan["marker"])
    if boundary == "claimed":
        original = research.prepare

        async def prepared(*args: Any, **kwargs: Any) -> Any:
            marker(target, boundary)
            return await original(*args, **kwargs)

        research.prepare = prepared  # type: ignore[method-assign]
    elif boundary == "snapshot":
        original_check = bar_module._check

        def checked(cancelled: threading.Event) -> None:
            original_check(cancelled)
            frame = inspect.currentframe()
            if frame and frame.f_back and frame.f_back.f_code.co_name == "numeric_bounds":
                marker(target, boundary)

        bar_module._check = checked
    elif boundary == "numerical":
        original_prepare = numerical_module.prepare

        def numerical(*args: Any, **kwargs: Any) -> Any:
            result = original_prepare(*args, **kwargs)
            marker(target, boundary)
            return result

        numerical_module.prepare = numerical
    elif boundary == "staged":
        original_stage = research.stage

        def staged(*args: Any, **kwargs: Any) -> Any:
            result = original_stage(*args, **kwargs)
            marker(target, boundary)
            return result

        research.stage = staged  # type: ignore[method-assign]
    elif boundary == "renamed":
        original_finish = store.finish

        def finished(*args: Any, **kwargs: Any) -> Any:
            marker(target, boundary)
            return original_finish(*args, **kwargs)

        store.finish = finished
    elif boundary == "committed":
        original_publish = research.publish

        def published(*args: Any, **kwargs: Any) -> Any:
            result = original_publish(*args, **kwargs)
            marker(target, boundary)
            return result

        research.publish = published  # type: ignore[method-assign]
    await research.work(1, plan["run_id"])
    raise AssertionError("Crash boundary was not reached")


async def crashes(value: dict[str, Any], folder: Path, config_path: Path) -> dict[str, Any]:
    import r4_reference as independent

    from marketlab.research.v2 import store

    root = Path(value["storage_path"])
    engine = sa.create_engine(value["database_url"])
    base = LegacyBars(engine, root, value["redis_url"])
    research = ResearchService(base)
    version = "db545ab86156c1f200813bdf1d25f83f73b64205c2a909d28236ca8a5bf4ca34"
    spec = ResearchSpec.create(
        request(
            "market_profile",
            ["binance:spot:SOLUSDT"],
            [version],
            "2025-03-01T00:00:00Z",
            "2025-03-01T01:00:00Z",
            "2025-03-02T00:00:00Z",
        )
    )
    with engine.connect() as connection:
        row = core.one(
            connection, "SELECT * FROM v2_dataset_versions WHERE dataset_version_id=:id", id=version
        )
        metadata = core.wire(core.instrument(connection, "binance:spot:SOLUSDT"))
    assert row is not None
    day = datetime(2025, 3, 1, tzinfo=UTC)
    oracle = await asyncio.to_thread(
        oracle_bars,
        root / row["manifest_relative_path"].rsplit("/", 1)[0] / "trades.parquet",
        day,
        day + timedelta(days=1),
    )
    old = dict(spec.body(), schema="research-spec-v1", symbols=["SOLUSDT"])
    old.pop("instrument_ids")
    expected = independent.reference_payload(old, {"SOLUSDT": oracle["5m"]})
    expected_v2 = [reference_v2(body, {"binance:spot:SOLUSDT": metadata}) for body in expected]
    expected_hashes = [hashlib.sha256(canonical_json(body)).hexdigest() for body in expected_v2]
    save(
        folder / "fixtures.json",
        {
            "boundaries": ["claimed", "snapshot", "numerical", "staged", "renamed", "committed"],
            "request": spec.body(),
            "expected": expected_v2,
            "expected_sha256": expected_hashes,
            "budget": {
                "claimed_native_kills": 3,
                "lease_seconds": 60,
                "expected_attempts": 3,
                "expected_state": "failed",
                "fourth_claim": False,
            },
        },
    )
    results = []
    try:
        for boundary in ("claimed", "snapshot", "numerical", "staged", "renamed", "committed"):
            case = folder / boundary
            case.mkdir()
            run, _ = await research.submit(spec, "p3-crash-" + folder.name + "-" + boundary)
            marker_path = case / "marker.json"
            plan = {"boundary": boundary, "run_id": run, "marker": str(marker_path)}
            evidence = await run_boundary(config_path, case, plan, folder.name)
            before = store.inspect(engine, run)
            expected_registered = 1 if boundary == "committed" else 0
            with engine.connect() as connection:
                registered_count = core.execute(
                    connection, "SELECT count(*) FROM v2_research_results WHERE run_id=:id", id=run
                ).scalar_one()
            assert registered_count == expected_registered
            assert before["attempt_count"] == 1
            final = root / "research-v2" / run
            before_artifacts = artifact_hashes(final) if final.exists() else None
            if boundary in {"renamed", "committed"}:
                assert before_artifacts is not None
            if boundary != "committed":
                assert before["state"] == "running"
                # Wait native database lease expiry; do not shorten or force state.
                while True:
                    with engine.connect() as connection:
                        alive = core.execute(
                            connection,
                            "SELECT lease_until>clock_timestamp() "
                            "FROM v2_research_runs WHERE run_id=:id",
                            id=run,
                        ).scalar_one()
                    if not alive:
                        break
                    await asyncio.sleep(0.25)
            with engine.connect() as connection:
                retained = [
                    dict(r)
                    for r in core.execute(
                        connection,
                        "SELECT * FROM v2_research_reservations "
                        "WHERE run_id=:id AND state<>'released'",
                        id=run,
                    ).mappings()
                ]
            assert len(retained) == 1
            assert retained[0]["purpose"] == "attempt" and str(retained[0]["run_id"]) == run
            assert tuple(
                retained[0][k] for k in ("scratch_bytes", "spill_bytes", "output_bytes")
            ) == (capacity.SCRATCH, capacity.SPILL, capacity.OUTPUT)
            retained_before = core.wire(retained)
            # Exact spawned child dead and lease expired (or committed): verify
            # invocation ownership before cleaning only its transient ledger paths.
            for row in retained:
                capacity.release(
                    engine,
                    root,
                    {
                        "reservation_id": str(row["reservation_id"]),
                        "owner": str(row["owner"]),
                        "relative_path": row["relative_root"],
                    },
                )
            attempted = await research.work(1, run)
            after = store.inspect(engine, run)
            assert after["state"] == "succeeded"
            assert after["attempt_count"] == (1 if boundary == "committed" else 2)
            assert attempted == (0 if boundary == "committed" else 1)
            with engine.connect() as connection:
                assert (
                    core.execute(
                        connection,
                        "SELECT count(*) FROM v2_research_results WHERE run_id=:id",
                        id=run,
                    ).scalar_one()
                    == 1
                )
                released = core.one(
                    connection,
                    "SELECT * FROM v2_research_reservations WHERE reservation_id=:id",
                    id=retained[0]["reservation_id"],
                )
            assert released and released["state"] == "released"
            assert sum(released[k] for k in ("scratch_bytes", "spill_bytes", "output_bytes")) == 0
            for kind, expected_body, expected_hash in zip(
                ("results", "summary"), expected_v2, expected_hashes, strict=True
            ):
                body, actual_hash = research.read(run, kind)
                assert body == expected_body and actual_hash == expected_hash
            after_artifacts = artifact_hashes(final)
            if boundary in {"renamed", "committed"}:
                assert before_artifacts == after_artifacts
            save(
                case / "receipt.json",
                {
                    "before": before,
                    "after": after,
                    "registered_before": registered_count,
                    "terminated_pid": evidence["pid"],
                    "native_expiry": True,
                    "retained_before": retained_before,
                    "released_after": released,
                    "artifacts_before": before_artifacts,
                    "artifacts_after": after_artifacts,
                    "expected_sha256": expected_hashes,
                },
            )
            results.append({"boundary": boundary, "id": run, "attempts": after["attempt_count"]})
        budget_run, _ = await research.submit(spec, "p3-budget-" + folder.name)
        budget = []
        for attempt in (1, 2, 3):
            case = folder / ("budget-" + str(attempt))
            case.mkdir()
            marker_path = case / "marker.json"
            mark = await run_boundary(
                config_path,
                case,
                {"boundary": "claimed", "run_id": budget_run, "marker": str(marker_path)},
                folder.name,
            )
            current = store.inspect(engine, budget_run)
            assert current["state"] == "running" and current["attempt_count"] == attempt
            while True:
                with engine.connect() as connection:
                    alive = core.execute(
                        connection,
                        "SELECT lease_until>clock_timestamp() "
                        "FROM v2_research_runs WHERE run_id=:id",
                        id=budget_run,
                    ).scalar_one()
                if not alive:
                    break
                await asyncio.to_thread(time.sleep, 0.25)
            with engine.connect() as connection:
                retained = [
                    dict(r)
                    for r in core.execute(
                        connection,
                        "SELECT * FROM v2_research_reservations "
                        "WHERE run_id=:id AND state<>'released'",
                        id=budget_run,
                    ).mappings()
                ]
            assert len(retained) == 1
            assert tuple(
                retained[0][k] for k in ("scratch_bytes", "spill_bytes", "output_bytes")
            ) == (capacity.SCRATCH, capacity.SPILL, capacity.OUTPUT)
            capacity.release(
                engine,
                root,
                {
                    "reservation_id": str(retained[0]["reservation_id"]),
                    "owner": str(retained[0]["owner"]),
                    "relative_path": retained[0]["relative_root"],
                },
            )
            budget.append({"attempt": attempt, "killed_pid": mark["pid"], "native_expiry": True})
        assert await research.work(1, budget_run) == 0
        exhausted = store.inspect(engine, budget_run)
        assert exhausted["state"] == "failed" and exhausted["attempt_count"] == 3
        with engine.connect() as connection:
            assert (
                core.execute(
                    connection,
                    "SELECT count(*) FROM v2_research_results WHERE run_id=:id",
                    id=budget_run,
                ).scalar_one()
                == 0
            )
        save(
            folder / "budget-receipt.json",
            {"crashes": budget, "terminal": exhausted, "fourth_claim": False},
        )
        return {"boundaries": results, "native_third_crash_budget": budget_run}
    finally:
        await research.close()
        await base.close()
        engine.dispose()


def save(path: Path, value: Any) -> None:
    path.write_bytes(canonical_json(core.wire(value)))


def config(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    assert value["owner"] == "v2-phase3-20261029"
    url = sa.engine.make_url(value["database_url"])
    assert (url.host, url.port) == ("127.0.0.1", 55450)
    assert url.database in {"marketlab", "v2p3_actual", "v2p3_legacy"}
    assert value["redis_url"] == "redis://127.0.0.1:56392/0"
    assert Path(value["storage_path"]).resolve().is_relative_to(BASE.resolve())
    ledger = json.loads((BASE / "owned-resources.json").read_text(encoding="utf-8-sig"))
    assert len(ledger) == 2
    observed = json.loads(
        subprocess.check_output(
            ["docker", "inspect", *[r["Id"] for r in ledger]], text=True, timeout=30
        )
    )
    for expected, current in zip(ledger, observed, strict=True):
        assert current["Id"] == expected["Id"] and current["Name"] == expected["Name"]
        assert current["Image"] == expected["Image"] and current["Mounts"] == expected["Mounts"]
        assert current["Config"]["Labels"] == expected["Labels"]
        assert current["NetworkSettings"]["Ports"] == expected["Ports"]
        assert (
            current["State"]["Running"] and current["State"]["StartedAt"] == expected["StartedAt"]
        )
        assert expected["Labels"] == {"marketlab.v2phase3.owner": "v2-phase3-20261029"}
    return value


def inventory() -> dict[str, Any]:
    paths = sorted(
        p
        for folder in ("src", "scripts", "tests", "docs/v2")
        for p in (PROJECT / folder).rglob("*")
        if p.is_file() and p.suffix in {".py", ".md"}
    )
    paths += [PROJECT / "uv.lock", PROJECT / "AGENTS.md", PROJECT / "ROADMAP_v2.md"]
    files = {p.relative_to(PROJECT).as_posix(): sha256_file(p) for p in paths}
    return {
        "head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True
        ).strip(),
        "files": files,
        "sha256": hashlib.sha256(canonical_json(files)).hexdigest(),
    }


def stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def artifact_hashes(path: Path) -> dict[str, str]:
    return {
        name: sha256_file(path / name)
        for name in ("manifest.json", "spec.json", "results.json", "summary.json")
    }


def reference_v2(body: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    names = {value["source_symbol"]: key for key, value in metadata.items()}

    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            return {names.get(k, k): walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        return value

    result = walk(body)
    result.update(
        schema=body["schema"].replace("-v1", "-v2"),
        definition="research-numerics-v2",
        instrument_ids=sorted(metadata),
        instruments=metadata,
        coverage_claim="observed_only",
    )
    first = metadata[sorted(metadata)[0]]
    result["units"] = {
        "price": first["quote_asset"],
        "quote_volume": first["quote_asset"],
        "returns": "ratio",
        "base_volume": {i: m["base_asset"] for i, m in metadata.items()},
    }
    if result["workflow"] == "cross_asset":
        result["comparison_order"] = sorted(metadata)
    return result


def independent_module() -> Any:
    path = PROJECT / "scripts/r4_reference.py"
    specification = importlib.util.spec_from_file_location(
        "retained_independent_r4_reference", path
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def independent_reference(
    spec: dict[str, Any],
    inputs: dict[str, list[dict[str, Any]]],
    metadata: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Adapt the unchanged independent R4 engine using ordered private calculation labels."""
    identities = sorted(spec["instrument_ids"])
    if len(identities) != (2 if spec["workflow"] == "cross_asset" else 1) or set(inputs) != set(
        identities
    ):
        raise ValueError("Independent reference selection mismatch")
    pinned = {identity: metadata[identity] for identity in identities}
    if len({m["quote_asset"] for m in pinned.values()}) != 1:
        raise ValueError("Independent reference quote mismatch")
    # These are private positional labels required by the retained R4 oracle,
    # never registry aliases or relabeled source data. Canonical ID order fixes
    # left-minus-right semantics independently of submitted request order.
    aliases = dict(zip(identities, ("BTCUSDT", "ETHUSDT")[: len(identities)], strict=True))
    old = dict(spec, schema="research-spec-v1", symbols=list(aliases.values()))
    old.pop("instrument_ids")
    independent = independent_module()
    result, summary = independent.reference_payload(
        old, {aliases[i]: inputs[i] for i in identities}
    )
    reverse = {alias: identity for identity, alias in aliases.items()}
    outputs = []
    for original in (result, summary):
        body = dict(original)
        for key in ("history", "profiles"):
            if key in body:
                if set(body[key]) != set(reverse):
                    raise ValueError("Independent reference output labels mismatch")
                body[key] = {reverse[alias]: value for alias, value in body[key].items()}
        body["units"] = {
            "price": pinned[identities[0]]["quote_asset"],
            "quote_volume": pinned[identities[0]]["quote_asset"],
            "returns": "ratio",
            "base_volume": {i: pinned[i]["base_asset"] for i in identities},
        }
        body.update(
            schema=original["schema"].replace("-v1", "-v2"),
            definition="research-numerics-v2",
            instrument_ids=identities,
            instruments=pinned,
            coverage_claim="observed_only",
        )
        if spec["workflow"] == "cross_asset":
            body["comparison_order"] = identities
        outputs.append(body)
    return outputs[0], outputs[1]


def actual_requests(
    choices: dict[Any, Any], equivalents: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    campaigns = []
    for identity in ("binance:spot:BTCUSDT", "binance:spot:SOLUSDT"):
        versions = [
            choices[(identity, d)]["dataset_version_id"]
            for d in ("2025-02-28", "2025-03-01", "2025-03-02")
        ]
        for workflow in ("market_profile", "volatility_cluster"):
            campaigns.append(
                request(
                    workflow,
                    [identity],
                    versions,
                    "2025-02-28T00:00:00Z",
                    "2025-03-01T01:00:00Z",
                    "2025-03-03T00:00:00Z",
                )
            )
    campaigns.append(
        request(
            "cross_asset",
            ["binance:spot:BTCUSDT", "binance:spot:SOLUSDT"],
            [
                choices[(i, d)]["dataset_version_id"]
                for i in ("binance:spot:BTCUSDT", "binance:spot:SOLUSDT")
                for d in ("2025-02-28", "2025-03-01", "2025-03-02")
            ],
            "2025-02-28T00:00:00Z",
            "2025-03-01T01:00:00Z",
            "2025-03-03T00:00:00Z",
        )
    )
    for identity, day in (
        ("binance:spot:BTCUSDT", "2025-02-01"),
        ("binance:spot:SOLUSDT", "2025-03-01"),
    ):
        campaigns.append(
            request(
                "market_profile",
                [identity],
                [choices[(identity, day)]["dataset_version_id"]],
                day + "T00:00:00Z",
                day + "T01:00:00Z",
                stamp(datetime.fromisoformat(day).replace(tzinfo=UTC) + timedelta(days=1)),
            )
        )
    for row in equivalents:
        if row["dataset_version_id"] != RETAINED["sol_official"]:
            campaigns.append(
                request(
                    "market_profile",
                    ["binance:spot:SOLUSDT"],
                    [row["dataset_version_id"]],
                    "2025-03-01T00:00:00Z",
                    "2025-03-01T01:00:00Z",
                    "2025-03-02T00:00:00Z",
                )
            )
    return campaigns


def expected_campaign(
    campaigns: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    oracles: dict[str, Any],
    metadata: dict[str, dict[str, Any]],
) -> list[Any]:
    indexed = {r["dataset_version_id"]: r for r in rows}
    expected = []
    for body in campaigns:
        inputs = {i: [] for i in body["instrument_ids"]}
        for version in body["dataset_versions"]:
            inputs[indexed[version]["instrument_id"]].extend(oracles[version]["5m"])
        for bars in inputs.values():
            bars.sort(key=lambda b: b["start"])
        expected.append(independent_reference(body, inputs, metadata))
    return expected


def preflight(value: dict[str, Any], folder: Path, source: Path) -> dict[str, Any]:
    """Read-only expected-output generation from retained independent daily receipts."""
    assert source.resolve().is_relative_to(BASE.resolve()) and source.is_dir()
    selection = json.loads((source / "selection.json").read_bytes())
    assert len(selection) == 7
    engine = sa.create_engine(value["database_url"])
    try:
        rows = registered(engine, Path(value["storage_path"]))
        indexed = {r["dataset_version_id"]: r for r in rows}
        choices = {(r["instrument_id"], r["day"]): indexed[r["version"]] for r in selection}
        equivalents = [indexed[RETAINED[key]] for key in ("sol_official", "sol_csv", "sol_parquet")]
        for row, kind, format_name in zip(
            equivalents,
            ("official_archive", "canonical_file", "canonical_file"),
            ("binance_zip", "csv", "parquet"),
            strict=True,
        ):
            assert row["manifest"]["source"]["kind"] == kind
            assert row["manifest"]["metadata"]["format"] == format_name
            assert row["logical_sha256"] == indexed[RETAINED["sol_official"]]["logical_sha256"]
        oracles = {}
        hashes = {}
        for row in choices.values():
            path = source / (row["dataset_version_id"] + "-oracle.json")
            oracles[row["dataset_version_id"]] = json.loads(path.read_bytes())
            hashes[path.name] = sha256_file(path)
        for row in equivalents:
            oracles[row["dataset_version_id"]] = oracles[RETAINED["sol_official"]]
        with engine.connect() as connection:
            metadata = {
                i: core.wire(core.instrument(connection, i))
                for i in ("binance:spot:BTCUSDT", "binance:spot:SOLUSDT")
            }
        campaigns = actual_requests(choices, equivalents)
        assert len(campaigns) == 9 and {r["workflow"] for r in campaigns} == {
            "market_profile",
            "cross_asset",
            "volatility_cluster",
        }
        expected = expected_campaign(campaigns, rows, oracles, metadata)
        output_hashes = [
            [hashlib.sha256(canonical_json(b)).hexdigest() for b in pair] for pair in expected
        ]
        save(
            folder / "frozen-campaign-preflight.json",
            {
                "requests": campaigns,
                "expected": expected,
                "expected_sha256": output_hashes,
                "input_oracle_sha256": hashes,
                "source_invocation_sha256": sha256_file(source / "invocation.json"),
                "independent_r4_source_sha256": sha256_file(PROJECT / "scripts/r4_reference.py"),
                "not_runtime_acceptance": True,
            },
        )
        return {
            "campaigns": len(campaigns),
            "oracle_receipts": len(hashes),
            "expected_sha256": output_hashes,
            "not_runtime_acceptance": True,
            "source_oracles": str(source),
        }
    finally:
        engine.dispose()


def projected(body: dict[str, Any]) -> dict[str, Any]:
    names = {
        "binance:spot:BTCUSDT": "BTCUSDT",
        "binance:spot:ETHUSDT": "ETHUSDT",
        "binance:spot:SOLUSDT": "SOLUSDT",
    }

    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            return {names.get(k, k): walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        return value

    result = walk(
        {
            k: v
            for k, v in body.items()
            if k not in {"instrument_ids", "instruments", "comparison_order", "coverage_claim"}
        }
    )
    result["schema"] = result["schema"].replace("-v2", "-v1")
    result["definition"] = "research-numerics-v1"
    return result


def request(
    workflow: str, identities: list[str], versions: list[str], history: str, start: str, end: str
) -> dict[str, Any]:
    return {
        "schema": "research-spec-v2",
        "workflow": workflow,
        "instrument_ids": identities,
        "dataset_versions": versions,
        "history_start": history,
        "start": start,
        "end": end,
        "interval": "5m",
        "metrics": ["profile", "correlation", "close_change_difference"]
        if workflow == "cross_asset"
        else ["profile", "clusters"]
        if workflow == "volatility_cluster"
        else ["profile"],
        "parameters": {},
        "predicates": {"volatility_quantile": "0.9", "volume_multiple": "2", "min_bars": 2}
        if workflow == "volatility_cluster"
        else {},
    }


def oracle_rows(batch: pa.RecordBatch) -> Any:
    """Independent exact UTC decoding without repeated Arrow timezone construction."""
    index = batch.schema.get_field_index("executed_at")
    if index < 0 or batch.schema.field(index).type != pa.timestamp("us", tz="UTC"):
        raise ValueError("Oracle requires exact UTC microsecond timestamps")
    column = batch.column(index)
    if column.null_count:
        raise ValueError("Oracle requires non-null timestamps")
    values = [
        (current.cast(pa.int64()) if offset == index else current).to_pylist()
        for offset, current in enumerate(batch.columns)
    ]
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    for row in zip(*values, strict=True):
        result = dict(zip(batch.schema.names, row, strict=True))
        result["executed_at"] = epoch + timedelta(microseconds=result["executed_at"])
        yield result


def oracle_bars(path: Path, first: datetime, end: datetime) -> dict[str, list[dict[str, Any]]]:
    """Independent bounded streaming exact Decimal aggregation; no production bar helpers."""
    groups: dict[int, dict[datetime, dict[str, Any]]] = {60: {}, 300: {}}
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    with localcontext() as context:
        context.prec = 100
        for batch in pq.ParquetFile(path).iter_batches(batch_size=16384, use_threads=False):
            for row in oracle_rows(batch):
                instant = row["executed_at"]
                if not first <= instant < end:
                    continue
                order = (instant, int(row["source_trade_id"]))
                delta = instant - epoch
                seconds = delta.days * 86400 + delta.seconds
                for step, mapping in groups.items():
                    when = epoch + timedelta(seconds=(seconds // step) * step)
                    current = mapping.get(when)
                    if current is None:
                        current = {
                            "first": order,
                            "last": order,
                            "open": row["price"],
                            "close": row["price"],
                            "high": row["price"],
                            "low": row["price"],
                            "base": Decimal(0),
                            "quote": Decimal(0),
                            "count": 0,
                        }
                        mapping[when] = current
                    if order < current["first"]:
                        current.update(first=order, open=row["price"])
                    if order > current["last"]:
                        current.update(last=order, close=row["price"])
                    current["high"] = max(current["high"], row["price"])
                    current["low"] = min(current["low"], row["price"])
                    current["base"] += row["quantity"]
                    current["quote"] += row["quote_quantity"]
                    current["count"] += 1
        result = {}
        for step, mapping in groups.items():
            values = []
            for when, current in sorted(mapping.items()):
                values.append(
                    {
                        "start": stamp(when),
                        "end": stamp(when + timedelta(seconds=step)),
                        **{k: format(current[k], ".18f") for k in ("open", "high", "low", "close")},
                        "base_volume": format(current["base"], ".18f"),
                        "quote_volume": format(current["quote"], ".18f"),
                        "trade_count": current["count"],
                        "vwap": format(
                            (current["quote"] / current["base"]).quantize(
                                Decimal("0.000000000000000001"), rounding=ROUND_HALF_EVEN
                            ),
                            ".18f",
                        ),
                    }
                )
            result["1m" if step == 60 else "5m"] = values
        return result


def registered(engine: sa.Engine, root: Path) -> list[dict[str, Any]]:
    """Discover bounded hash-checked manifests; native preparation verifies contents later."""
    with engine.connect() as connection:
        rows = [
            dict(r)
            for r in core.execute(
                connection,
                "SELECT * FROM v2_dataset_versions WHERE dataset_version_id IN "
                "(:btc,:sol,:csv,:parquet) OR (instrument_id IN "
                "('binance:spot:BTCUSDT','binance:spot:SOLUSDT') AND "
                "trade_date>=DATE '2025-02-28' AND trade_date<DATE '2025-03-03') "
                "ORDER BY instrument_id,trade_date,dataset_version_id LIMIT 101",
                btc=RETAINED["btc_official"],
                sol=RETAINED["sol_official"],
                csv=RETAINED["sol_csv"],
                parquet=RETAINED["sol_parquet"],
            ).mappings()
        ]
    assert len(rows) <= 100, "Acceptance catalog alternatives exceed bounded discovery"
    for row in rows:
        path = safe_path(root, row["manifest_relative_path"])
        assert path.is_file() and path.stat().st_size <= 65536
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["manifest_sha256"]
        manifest = parse_json(raw)
        assert manifest["schema"] == "dataset-manifest-v2"
        assert manifest["dataset_version_id"] == row["dataset_version_id"]
        row["manifest"] = manifest
    return rows


async def native_preparation(
    research: ResearchService,
    identities: list[str],
    versions: list[str],
    first: datetime,
    before: datetime,
) -> list[dict[str, Any]]:
    reservation = await asyncio.to_thread(capacity.reserve, research.engine, research.root)
    stop = threading.Event()
    try:
        async with asyncio.timeout(1800):
            return await research.bars.prepare_selection(identities, versions, first, before, stop)
    finally:
        stop.set()
        await asyncio.to_thread(capacity.release, research.engine, research.root, reservation)


def binding(bars: Any, prepared: dict[str, Any]) -> None:
    current = bars._catalog((prepared["dataset_version_id"],))
    assert len(current) == 1
    assert (current[0]["catalog_identity"], current[0]["signature"]) == (
        prepared["catalog_identity"],
        prepared["signature"],
    ), "Verified oracle input binding changed"


def verified_oracle(
    bars: Any, prepared: dict[str, Any], first: datetime, before: datetime
) -> dict[str, list[dict[str, Any]]]:
    binding(bars, prepared)
    result = oracle_bars(prepared["path"], first, before)
    binding(bars, prepared)
    return result


async def execute_v2(
    research: ResearchService,
    body: dict[str, Any],
    expected: tuple[dict[str, Any], dict[str, Any]],
    folder: Path,
    key: str,
    repeat: bool = True,
) -> dict[str, Any]:
    spec = ResearchSpec.create(body)
    run, replayed = await research.submit(spec, key)
    assert not replayed
    assert await research.submit(spec, key) == (run, True)
    assert await research.work(1, run) == 1
    info = research.inspect(run)
    save(folder / (run + "-status.json"), info)
    assert info["state"] == "succeeded", info["error_code"]
    output = []
    for kind, reference in zip(("results", "summary"), expected, strict=True):
        actual, hashed = research.read(run, kind)
        save(folder / (run + "-" + kind + ".json"), actual)
        if reference["schema"].endswith("-v2"):
            assert (
                actual == reference
                and hashed == hashlib.sha256(canonical_json(reference)).hexdigest()
            ), (run, kind, "independent complete output/hash mismatch")
        else:
            assert projected(actual) == reference, (run, kind, "independent numerical mismatch")
        output.append(hashed)
    receipt = {
        "id": run,
        "hashes": output,
        "attempt_count": info["attempt_count"],
        "spec_sha256": spec.digest,
    }
    if repeat:
        second = await execute_v2(research, body, expected, folder, key + "-repeat", repeat=False)
        assert second["id"] != run and second["hashes"] == output
        assert second["attempt_count"] == info["attempt_count"] == 1
        receipt["fresh_key_repeat"] = second
    return receipt


async def legacy(value: dict[str, Any], folder: Path, cold: bool = False) -> dict[str, Any]:
    references_path = PROJECT / "artifacts/r4/reference-workflows.json"
    references = json.loads(references_path.read_text())
    frozen = (
        [r for r in references if r["spec"]["workflow"] == "cross_asset"][:1]
        if cold
        else references[:5]
    )
    save(
        folder / "fixtures.json",
        {"reference_sha256": sha256_file(references_path), "requests": [r["spec"] for r in frozen]},
    )
    root = Path(value["storage_path"])
    engine = sa.create_engine(value["database_url"])
    if cold:
        assert value["redis_url"] == "redis://127.0.0.1:56392/0"
        client = redis.Redis.from_url(value["redis_url"])
        client.flushdb()
        client.close()
    base = LegacyBars(engine, root, value["redis_url"])
    old = LegacyResearch(base)
    research = ResearchService(base)
    results = []
    started = time.monotonic()
    try:
        with engine.connect() as connection:
            counts = core.execute(
                connection,
                "SELECT count(*),sum(row_count) FROM dataset_versions WHERE venue='binance_spot'",
            ).one()
        assert counts == (62, 230311900)
        for index, reference in enumerate(frozen):
            spec = LegacySpec.create(reference["spec"])
            run, replayed = await old.submit(spec, "p3-legacy-" + folder.name + "-" + str(index))
            assert not replayed
            assert await old.work(1, run) == 1
            info = old.inspect(run)
            assert info["state"] == "succeeded" and info["attempt_count"] == 1
            for kind in ("results", "summary"):
                actual, hashed = old.read(run, kind)
                assert actual == reference[kind] and hashed == reference[kind + "_sha256"]
            with engine.connect() as connection:
                memo = core.one(
                    connection, "SELECT state,model_calls FROM memo_jobs WHERE run_id=:id", id=run
                )
            assert memo and memo["state"] == "queued" and memo["model_calls"] == 0
            result = {"legacy_id": run, "memo": memo}
            if not cold:
                body = dict(
                    reference["spec"],
                    schema="research-spec-v2",
                    instrument_ids=["binance:spot:" + s for s in reference["spec"]["symbols"]],
                )
                body.pop("symbols")
                result["v2"] = await execute_v2(
                    research,
                    body,
                    (reference["results"], reference["summary"]),
                    folder,
                    "p3-projection-" + folder.name + "-" + str(index),
                )
            results.append(result)
    finally:
        await research.close()
        await old.close()
        await base.close()
        engine.dispose()
    drain = {
        "compute": base.reader.compute.snapshot(),
        "verifier": base.reader.verifier.snapshot(),
        "live_owned_children": [
            p.pid
            for p in multiprocessing.active_children()
            if p.pid in base.reader.verifier.worker_pids
        ],
    }
    assert drain["compute"]["active"] == 0 and not drain["live_owned_children"]
    save(folder / "post-close-drain.json", drain)
    elapsed = time.monotonic() - started
    if cold:
        assert elapsed < 1800, elapsed
    return {"runs": results, "trade_count": 230311900, "elapsed_with_drain": elapsed, "cold": cold}


async def actual(value: dict[str, Any], folder: Path) -> dict[str, Any]:
    import r4_reference as independent

    root = Path(value["storage_path"])
    engine = sa.create_engine(value["database_url"])
    base = LegacyBars(engine, root, value["redis_url"])
    research = ResearchService(base)
    try:
        rows = await asyncio.to_thread(registered, engine, root)
        official = {
            (r["instrument_id"], str(r["trade_date"])): r
            for r in rows
            if r["manifest"]["source"].get("kind") == "official_archive"
        }
        # Manifest provenance mode is explicit, never infer from a symbol or filename.
        if not official:
            official = {
                (r["instrument_id"], str(r["trade_date"])): r
                for r in rows
                if r["manifest"]["source"].get("kind") == "official_archive"
            }
        required = [
            ("binance:spot:" + s, d)
            for s in ("BTCUSDT", "SOLUSDT")
            for d in ("2025-02-28", "2025-03-01", "2025-03-02")
        ]
        for identity, day in required:
            if (identity, day) in official:
                continue
            before = (datetime.fromisoformat(day) + timedelta(days=1)).date().isoformat()
            submitted = await asyncio.to_thread(
                jobs.submit,
                engine,
                {
                    "schema": "daily-ingestion-v2",
                    "adapter": "binance_daily",
                    "instrument_ids": [identity],
                    "from_date": day,
                    "before_date": before,
                },
                "p3-data-" + folder.name + "-" + identity.rsplit(":", 1)[1] + day,
            )
            outcome = await asyncio.to_thread(
                ingestion.work, engine, root, max_jobs=1, submission_id=submitted["submission_id"]
            )
            state = jobs.inspect_submission(engine, submitted["submission_id"])
            save(
                folder / (submitted["submission_id"] + "-ingestion.json"),
                {"outcome": outcome, "status": state},
            )
            assert state["jobs"][0]["state"] == "succeeded"
        rows = await asyncio.to_thread(registered, engine, root)
        # Freeze an explicit official manifest selection; ambiguity is a gate failure.
        choices = {}
        for identity, day in [*required, ("binance:spot:BTCUSDT", "2025-02-01")]:
            candidates = [
                r
                for r in rows
                if r["instrument_id"] == identity
                and str(r["trade_date"]) == day
                and r["manifest"]["source"].get("kind") == "official_archive"
            ]
            assert len(candidates) == 1, (
                identity,
                day,
                "official alternatives require explicit review",
            )
            choices[(identity, day)] = candidates[0]
        save(
            folder / "selection.json",
            [
                {
                    "instrument_id": i,
                    "day": d,
                    "version": r["dataset_version_id"],
                    "manifest_sha256": r["manifest_sha256"],
                }
                for (i, d), r in choices.items()
            ],
        )
        assert (
            choices[("binance:spot:BTCUSDT", "2025-02-01")]["dataset_version_id"]
            == RETAINED["btc_official"]
        )
        assert (
            choices[("binance:spot:SOLUSDT", "2025-03-01")]["dataset_version_id"]
            == RETAINED["sol_official"]
        )
        equivalents = [
            next(r for r in rows if r["dataset_version_id"] == RETAINED[name])
            for name in ("sol_official", "sol_csv", "sol_parquet")
        ]
        assert len({r["dataset_version_id"] for r in equivalents}) == 3
        for row, kind, format_name in zip(
            equivalents,
            ("official_archive", "canonical_file", "canonical_file"),
            ("binance_zip", "csv", "parquet"),
            strict=True,
        ):
            assert (
                row["instrument_id"] == "binance:spot:SOLUSDT"
                and str(row["trade_date"]) == "2025-03-01"
            )
            assert (
                row["manifest"]["source"]["kind"] == kind
                and row["manifest"]["metadata"]["format"] == format_name
            )
        prepared_rows = await native_preparation(
            research,
            ["binance:spot:BTCUSDT", "binance:spot:SOLUSDT"],
            [choices[key]["dataset_version_id"] for key in required],
            datetime(2025, 2, 28, tzinfo=UTC),
            datetime(2025, 3, 3, tzinfo=UTC),
        )
        prepared_rows.extend(
            await native_preparation(
                research,
                ["binance:spot:BTCUSDT"],
                [RETAINED["btc_official"]],
                datetime(2025, 2, 1, tzinfo=UTC),
                datetime(2025, 2, 2, tzinfo=UTC),
            )
        )
        for row in equivalents[1:]:
            prepared_rows.extend(
                await native_preparation(
                    research,
                    ["binance:spot:SOLUSDT"],
                    [row["dataset_version_id"]],
                    datetime(2025, 3, 1, tzinfo=UTC),
                    datetime(2025, 3, 2, tzinfo=UTC),
                )
            )
        prepared = {r["dataset_version_id"]: r for r in prepared_rows}
        selected_versions = {r["dataset_version_id"] for r in [*choices.values(), *equivalents]}
        assert set(prepared) == selected_versions
        save(
            folder / "native-preparation.json",
            [
                {
                    k: r[k]
                    for k in (
                        "dataset_version_id",
                        "manifest_sha256",
                        "signature",
                        "id_bounds",
                        "semantic_sha256",
                    )
                }
                for r in prepared_rows
            ],
        )
        oracles = {}
        for row in choices.values():
            first = datetime.combine(row["trade_date"], datetime.min.time(), UTC)
            oracle = await asyncio.to_thread(
                verified_oracle,
                research.bars,
                prepared[row["dataset_version_id"]],
                first,
                first + timedelta(days=1),
            )
            save(folder / (row["dataset_version_id"] + "-oracle.json"), oracle)
            oracles[row["dataset_version_id"]] = oracle
        reference_logical = choices[("binance:spot:SOLUSDT", "2025-03-01")]["logical_sha256"]
        for row in equivalents:
            assert row["logical_sha256"] == reference_logical
            oracles[row["dataset_version_id"]] = oracles[RETAINED["sol_official"]]
        campaigns = actual_requests(choices, equivalents)
        expected = expected_campaign(
            campaigns, rows, oracles, {r["instrument_id"]: r["metadata"] for r in prepared_rows}
        )
        save(
            folder / "frozen-campaign.json",
            {
                "requests": campaigns,
                "expected": expected,
                "oracle_source_sha256": sha256_file(Path(independent.__file__)),
            },
        )
        # Numerical scoring starts only after all independent expectations are frozen.
        bar_checks = 0
        for row in [*choices.values(), *equivalents]:
            first = datetime.combine(row["trade_date"], datetime.min.time(), UTC)
            for interval in ("1m", "5m"):
                result, _ = await research.bars.read(
                    BarsRequest.create(
                        versions=[row["dataset_version_id"]],
                        instrument_id=row["instrument_id"],
                        interval=interval,
                        start=first,
                        end=first + timedelta(days=1),
                    )
                )
                assert result["bars"] == oracles[row["dataset_version_id"]][interval]
                bar_checks += 1
        runs = []
        for index, (body, reference) in enumerate(zip(campaigns, expected, strict=True)):
            runs.append(
                await execute_v2(
                    research, body, reference, folder, "p3-actual-" + folder.name + "-" + str(index)
                )
            )
        return {"runs": runs, "bar_checks": bar_checks, "independent_oracle": True}
    finally:
        await research.close()
        await base.close()
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "actual",
            "legacy",
            "cold",
            "crashes",
            "crash-child",
            "preflight",
            "process-probe-child",
        ),
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--invocation", required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--oracles", type=Path)
    args = parser.parse_args()
    if args.action == "process-probe-child":
        assert args.plan is not None
        plan = json.loads(args.plan.read_bytes())
        asyncio.run(child_readiness(plan, args.plan))
        marker(Path(plan["marker"]), plan["boundary"])
        return 0
    if args.action == "crash-child":
        assert args.plan is not None and args.plan.resolve().is_relative_to(BASE.resolve())
        asyncio.run(crash_child(config(args.config), json.loads(args.plan.read_bytes())))
        return 0
    assert args.invocation.startswith("p3-") and all(
        c.isalnum() or c == "-" for c in args.invocation
    )
    folder = BASE / args.invocation
    folder.mkdir(exist_ok=False)
    before = inventory()
    started = time.monotonic()
    record = {
        "action": args.action,
        "invocation": args.invocation,
        "started_utc": stamp(datetime.now(UTC)),
        "source_before": before,
        "status": "running",
        "memory": "unmeasured",
    }
    save(folder / "invocation.json", record)
    try:
        value = config(args.config)
        if args.action == "preflight":
            assert args.oracles is not None
            result = preflight(value, folder, args.oracles)
        else:
            result = asyncio.run(
                actual(value, folder)
                if args.action == "actual"
                else crashes(value, folder, args.config)
                if args.action == "crashes"
                else legacy(value, folder, args.action == "cold")
            )
        if args.action == "cold":
            assert time.monotonic() - started < 1800
        record.update(status="passed", result=result)
        return 0
    except BaseException as error:
        record.update(status="failed", error_type=type(error).__name__)
        raise
    finally:
        record.update(
            finished_utc=stamp(datetime.now(UTC)),
            elapsed_seconds=time.monotonic() - started,
            source_after=inventory(),
        )
        save(folder / "invocation.json", record)


if __name__ == "__main__":
    raise SystemExit(main())
