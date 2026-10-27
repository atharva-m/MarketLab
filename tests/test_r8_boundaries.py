"""Offline ownership/fault-location checks for R8 real child boundaries."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import sqlalchemy as sa
from pydantic import SecretStr

sys.path.insert(0, str(Path("scripts").resolve()))
import r8_boundaries as boundary  # noqa: E402
from r8_common import NO_WINDOW, processes  # noqa: E402

from marketlab.config import Settings  # noqa: E402


def test_launcher_descendant_birth_is_required_not_arbitrary_ready_pid():
    inventory = {
        1: {"identity": 100, "parent": 0},
        2: {"identity": 101, "parent": 1},
        3: {"identity": 50, "parent": 0},
    }
    assert boundary.ready_is_owned({"pid": 2, "birth": 101}, inventory, 1, 100)
    assert not boundary.ready_is_owned({"pid": 3, "birth": 50}, inventory, 1, 100)
    assert not boundary.ready_is_owned({"pid": 2, "birth": 99}, inventory, 1, 100)
    assert not boundary.ready_is_owned({"pid": 2, "birth": 101}, inventory, 1, 99)


def test_child_context_rejects_other_schema_root_endpoint_before_claim(tmp_path, monkeypatch):
    monkeypatch.setattr(boundary, "BASE", tmp_path)
    monkeypatch.setattr(boundary, "execution_identity", lambda: {"source": "frozen"})
    schema = "r8_bench_" + "a" * 32
    root = tmp_path / "r8-fixture-storage"
    context = {
        "owner": boundary.OWNER,
        "mode": boundary.MODES[0],
        "schema": schema,
        "root": str(root),
        "execution": {"source": "frozen"},
    }
    url = sa.URL.create(
        "postgresql+psycopg",
        username="fixture",
        host="127.0.0.1",
        port=boundary.PROFILE.postgres_port,
        database="marketlab",
        query={"options": "-csearch_path=" + schema},
    )
    settings = Settings(
        database_url=SecretStr(url.render_as_string(hide_password=False)),
        database_password=None,
        storage_path=root,
        ollama_url=boundary.PROFILE.ollama_url,
    )
    path = tmp_path / "r8-context.json"
    assert boundary.validate_context(path, context, settings) == root
    for changed in (
        {"schema": "public"},
        {"root": str(tmp_path.parent)},
        {"owner": "original"},
        {"mode": "unknown"},
        {"execution": {"source": "changed"}},
    ):
        with pytest.raises(ValueError):
            boundary.validate_context(path, {**context, **changed}, settings)
    assert not list(tmp_path.iterdir())


def test_memo_rename_hook_matches_only_owned_staging_and_exact_run(tmp_path):
    root = tmp_path / "storage"
    target = root / "research" / "run" / "memo"
    assert boundary.memo_rename_matches(root / ".staging" / "memo-owned", target, root, "run")
    assert not boundary.memo_rename_matches(tmp_path / "memo-unowned", target, root, "run")
    assert not boundary.memo_rename_matches(root / ".staging" / "memo-owned", target, root, "other")
    assert not boundary.memo_rename_matches(
        root / ".staging" / "research-owned", target, root, "run"
    )


def test_native_venv_launcher_and_actual_interpreter_identity(tmp_path):
    ready, gate = tmp_path / "ready.json", tmp_path / "gate"
    code = (
        "import json,os,time;from pathlib import Path;"
        f"Path({str(ready)!r}).write_text(json.dumps({{'pid':os.getpid()}}));"
        f"gate=Path({str(gate)!r});deadline=time.monotonic()+10;"
        "\nwhile not gate.exists() and time.monotonic()<deadline:time.sleep(.02)"
        "\nos._exit(81 if gate.exists() else 1)"
    )
    process = subprocess.Popen([sys.executable, "-c", code], creationflags=NO_WINDOW)
    launcher = processes().get(process.pid)
    assert launcher is not None
    try:
        deadline = time.monotonic() + 5
        while not ready.exists():
            assert process.poll() is None and time.monotonic() < deadline
            time.sleep(0.02)
        pid = json.loads(ready.read_text())["pid"]
        inventory = processes()
        row = inventory[pid]
        assert boundary.ready_is_owned(
            {"pid": pid, "birth": row["identity"]}, inventory, process.pid, launcher["identity"]
        )
        gate.write_text("go")
        assert process.wait(timeout=10) == 81
    finally:
        if process.poll() is None:
            assert processes()[process.pid]["identity"] == launcher["identity"]
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    timeout=10,
                    check=True,
                    creationflags=NO_WINDOW,
                )
            else:
                process.kill()
            process.wait(timeout=10)


def test_older_orphan_cannot_join_reused_parent_pid_tree():
    inventory = {
        1: {"identity": 100, "parent": 0},
        2: {"identity": 101, "parent": 1},
        3: {"identity": 50, "parent": 1},
        4: {"identity": 51, "parent": 3},
    }
    assert set(boundary.owned_tree(inventory, 1, 100)) == {1, 2}
    assert not boundary.ready_is_owned({"pid": 3, "birth": 50}, inventory, 1, 100)


def test_real_memo_publisher_renames_before_public_result_insert_hook(tmp_path, monkeypatch):
    """Real publication/rename and SQLite transaction; PostgreSQL fences mocked.

    This checks fault placement, not PostgreSQL fencing (the owned live suite
    separately verifies real leases/fences/rollback). A real result INSERT must
    be reached with the complete final directory present and no committed row.
    """
    from marketlab.memos import store as memo_store
    from marketlab.memos.service import MemoService
    from marketlab.research import store as research_store

    class ControlledFault(Exception):
        pass

    root = (tmp_path / "storage").resolve()
    staging = root / ".staging" / "memo-fixture"
    staging.mkdir(parents=True)
    (staging / "manifest.json").write_text('{"fixture":true}')
    final = root / "research" / "run" / "memo"
    final.parent.mkdir(parents=True)
    assert staging.is_relative_to(tmp_path.resolve()) and final.is_relative_to(tmp_path.resolve())
    engine = sa.create_engine("sqlite://")
    memo_store.results.create(engine)
    memo = object.__new__(MemoService)
    memo.engine, memo.root = engine, root
    memo.verify = lambda directory, info: ({"artifact": {"sha256": "a" * 64}}, "fixture")
    monkeypatch.setattr(memo_store, "fence", lambda *args: None)
    monkeypatch.setattr(research_store, "bounded", lambda *args: None)
    monkeypatch.setattr(research_store, "advisory", lambda *args: None)
    monkeypatch.setattr(memo_store, "finish", lambda *args: None)
    original = sa.engine.Connection.execute
    reached = []

    def execute(connection, statement, *args, **kwargs):
        def fault():
            assert final.is_dir() and (final / "manifest.json").is_file()
            assert not staging.exists()
            reached.append("after_rename_before_insert")
            raise ControlledFault()

        boundary.before_memo_registration(statement, "memo_corrupt_orphan", fault)
        return original(connection, statement, *args, **kwargs)

    monkeypatch.setattr(sa.engine.Connection, "execute", execute)
    with pytest.raises(ControlledFault):
        memo.publish(memo_store.Claim("run", "owner", 1, 1), staging, {"summary_sha256": "b" * 64})
    assert reached == ["after_rename_before_insert"]
    with engine.connect() as connection:
        assert connection.scalar(sa.select(sa.func.count()).select_from(memo_store.results)) == 0
    assert final.is_dir() and (final / "manifest.json").is_file()
    engine.dispose()


def test_registration_fault_hook_does_not_intercept_other_statements():
    from marketlab.memos import store as memo_store
    from marketlab.research import store as research_store

    called = []

    def hook():
        called.append(True)

    for statement in (
        sa.select(memo_store.results),
        memo_store.jobs.update(),
        research_store.results.insert(),
    ):
        boundary.before_memo_registration(statement, "memo_corrupt_orphan", hook)
    boundary.before_memo_registration(memo_store.results.insert(), "memo_before_checkpoint", hook)
    assert not called
    boundary.before_memo_registration(memo_store.results.insert(), "memo_corrupt_orphan", hook)
    assert called == [True]
