"""Private, immutable S3 case snapshots; never load credentials or dotenv files.

The live launcher must supply the reviewed DB-identity digest and an existing
owned evidence directory. Retained schemas are backed up/restored once after the
campaign; this hook never reconciles, refunds, deletes, or calls object storage.
"""

import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path

import pytest
from s3_safe_output import redact_text
from sqlalchemy import text

from marketlab.storage.materialize import CACHE
from marketlab.storage.recovery import database_identity

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "artifacts/v2-phase6-s3-acceptance"
CAPTURED = pytest.StashKey[set[str]]()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity_digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def private_snapshot(snapshot, schema):
    if snapshot["large_objects"]:
        raise AssertionError("Unexpected unscoped large objects in owned database")
    result = {"schemas": [schema], "large_objects": []}
    for key in ("tables", "sequences"):
        result[key] = {
            name: value for name, value in snapshot[key].items() if name.startswith(schema + ".")
        }
    for key in (
        "triggers",
        "domain_constraints",
        "columns",
        "constraints",
        "indexes",
        "views",
        "functions",
        "enums",
    ):
        result[key] = [row for row in snapshot[key] if row[0] == schema]
    result["extensions"] = [row for row in snapshot["extensions"] if row[2] == schema]
    if schema + ".v2_storage_objects" not in result["tables"]:
        raise AssertionError("Owned storage schema is unavailable")
    return result


def redact(value):
    # Defensive output filtering only; the launcher must also redact its captured
    # pytest output before persistence. No environment mapping is ever emitted.
    def clean(item):
        if isinstance(item, str):
            return redact_text(item)
        if isinstance(item, dict):
            return {clean(key): clean(part) for key, part in item.items()}
        if isinstance(item, list):
            return [clean(part) for part in item]
        return item

    return clean(value)


def capture(engine, request):
    if os.environ.get("MARKETLAB_PHASE6_OWNED_S3") != "confirmed-disposable-prefix":
        raise AssertionError("Owned S3 launch qualification is missing")
    expected = os.environ.get("MARKETLAB_PHASE6_S3_DATABASE_IDENTITY_SHA256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise AssertionError("Owned database identity qualification is missing")
    destination = Path(os.environ.get("MARKETLAB_PHASE6_S3_EVIDENCE_DIR", "")).absolute()
    resolved = destination.resolve()
    if not resolved.is_relative_to(EVIDENCE.resolve()) or not destination.is_dir():
        raise AssertionError("Owned S3 evidence directory is unavailable")
    for component in (destination, *destination.parents):
        if component.is_symlink() or component.is_junction():
            raise AssertionError("Owned S3 evidence directory is linked")
    with engine.connect() as connection:
        identity = database_identity(connection)
        schema = connection.execute(text("SELECT current_schema()")).scalar_one()
        if identity_digest(identity) != expected or not re.fullmatch(
            r"test_v2_[0-9a-f]{32}", schema
        ):
            raise AssertionError("Owned private database/schema qualification failed")
    captured = request.config.stash.setdefault(CAPTURED, set())
    if schema in captured:
        return
    captured.add(schema)
    # storage_engine's own finalizer has already called CACHE.close(). Logical
    # tickets/reservations may remain unresolved intentionally in fault cases.
    with CACHE._lock:
        entries = [entry for entry in CACHE._entries.values() if entry.space.engine is engine]
        if entries or CACHE._inflight:
            raise AssertionError("Owned case cache scope did not drain")
    helper = ROOT / "scripts/v2_phase4_snapshot.py"
    spec = importlib.util.spec_from_file_location("phase6_s3_reused_snapshot", helper)
    if spec is None or spec.loader is None:
        raise AssertionError("Existing snapshot helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    snapshot = private_snapshot(module.snapshot(engine), schema)
    with engine.connect() as connection:
        if (
            database_identity(connection) != identity
            or connection.execute(text("SELECT current_schema()")).scalar_one() != schema
        ):
            raise AssertionError("Owned snapshot identity changed")
    sources = {
        str(path.relative_to(ROOT)): sha(path)
        for path in (Path(__file__), ROOT / "tests/test_v2_ingestion_integration.py", helper)
    }
    payload = redact(
        {
            "schema": "phase6-s3-case-snapshot-v1",
            "case_sha256": identity_digest(request.node.nodeid),
            "database_identity": identity,
            "private_schema": schema,
            "schema_retained": True,
            "cache_scope_drained": True,
            "native_writer_drain_proved_here": False,
            "unresolved_durable_state_preserved": True,
            "sources": sources,
            "snapshot": snapshot,
        }
    )
    raw = json.dumps(payload, sort_keys=True, indent=2).encode()
    path = resolved / (schema + ".json")
    with path.open("xb") as stream:
        stream.write(raw)
    with (resolved / (schema + ".sha256")).open("x", encoding="ascii") as stream:
        stream.write(hashlib.sha256(raw).hexdigest() + "\n")


def pytest_fixture_post_finalizer(fixturedef, request):
    if (
        fixturedef.argname != "storage_engine"
        or request.node.get_closest_marker("s3") is None
        or fixturedef.cached_result is None
        or fixturedef.cached_result[0] is None
    ):
        return
    try:
        capture(fixturedef.cached_result[0], request)
    except Exception:
        # Never echo DB/SDK exception text or selected AWS values. v2_engine keeps
        # the schema regardless, so failed capture still retains durable evidence.
        raise AssertionError("Owned S3 case snapshot failed; private schema retained") from None


def pytest_terminal_summary(terminalreporter):
    counts = {
        name: len(terminalreporter.stats.get(name, []))
        for name in ("passed", "failed", "error", "skipped", "deselected", "xfailed", "xpassed")
    }
    terminalreporter.write_line("PHASE6_CASE_COUNTS " + json.dumps(counts, sort_keys=True))
