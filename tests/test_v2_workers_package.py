"""Actual copied-source package CLI lifecycle on the owning Windows/Linux host."""

import importlib.util
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from test_v2_workers_integration import (  # noqa: F401
    browser_engine,
    model_engine,
    research_engine,
    storage_engine,
    v2_engine,
    worker_engine,
)

from marketlab import workers
from marketlab.datasets.v2 import admission
from marketlab.datasets.v2.core import execute

pytestmark = pytest.mark.integration


def test_real_source_package_cli_heartbeat_restart_and_missing_lock_fail_closed(
    worker_engine,  # noqa: F811
    tmp_path,
    monkeypatch,
):
    project = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "phase7_package_runner", project / "scripts/v2_phase7_acceptance.py"
    )
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)

    def run_local(command, timeout):
        if os.name == "nt":
            return runner.windows_cli(command, timeout)
        return runner.bounded_process(command, b"", timeout, local_cli=True)

    package, root = tmp_path / "package", tmp_path / "storage"
    root.mkdir()
    shutil.copytree(project / "src", package / "src", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(project / "uv.lock", package / "uv.lock")
    bootstrap = package / "tests/s3/guarded_python.py"
    bootstrap.parent.mkdir(parents=True)
    shutil.copyfile(project / "tests/s3/guarded_python.py", bootstrap)
    host, root_id = str(uuid4()), str(uuid4())
    workers.provision(worker_engine, host, "packaged-owned-host", root_id, root)
    admission.initialize(worker_engine, root)
    with worker_engine.connect() as connection:
        schema = execute(connection, "SELECT current_schema()").scalar_one()
    url = worker_engine.url.update_query_dict({"options": "-csearch_path=" + schema})
    monkeypatch.setenv("MARKETLAB_DATABASE_URL", url.render_as_string(hide_password=False))
    monkeypatch.setenv("MARKETLAB_STORAGE_PATH", str(root))
    monkeypatch.setenv("MARKETLAB_STORAGE_BACKEND", "local")
    monkeypatch.setenv("MARKETLAB_REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setenv("MARKETLAB_OLLAMA_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("MARKETLAB_WORKER_ROOT_ID", root_id)
    monkeypatch.setenv("MARKETLAB_METRICS_ENABLED", "false")
    command = [
        sys.executable,
        "-I",
        "-S",
        str(bootstrap),
        "--",
        "-m",
        "marketlab.research_cli",
        "v2",
        "worker",
        "--max-runs",
        "1",
        "--run",
        str(uuid4()),
        "--wait-seconds",
        "12",
        "--worker-root",
        root_id,
    ]
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run_local, command, 30)
        first = None
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            with worker_engine.connect() as connection:
                rows = list(
                    execute(
                        connection,
                        "SELECT * FROM v2_worker_instances WHERE root_id=:id AND state='ready'",
                        id=root_id,
                    ).mappings()
                )
            if rows:
                first = dict(rows[0])
                break
            if future.done():
                future.result()
                pytest.fail("Packaged worker exited without ready registration")
            time.sleep(0.05)
        assert first is not None
        live_heartbeat = False
        while not future.done() and time.monotonic() < deadline:
            with worker_engine.connect() as connection:
                fresh = (
                    execute(
                        connection,
                        "SELECT heartbeat_at,state FROM v2_worker_instances WHERE instance_id=:id",
                        id=first["instance_id"],
                    )
                    .mappings()
                    .one()
                )
            if fresh["state"] == "ready" and fresh["heartbeat_at"] > first["heartbeat_at"]:
                live_heartbeat = True
                break
            time.sleep(0.05)
        assert live_heartbeat, "Independent heartbeat was not observed while the CLI remained ready"
        assert b'"attempted_runs": 0' in future.result(timeout=25)
    with worker_engine.connect() as connection:
        stopped = dict(
            execute(
                connection,
                "SELECT * FROM v2_worker_instances WHERE instance_id=:id",
                id=first["instance_id"],
            )
            .mappings()
            .one()
        )
        assert stopped["state"] == "stopped"
        assert stopped["heartbeat_at"] > first["heartbeat_at"]
        assert stopped["source_sha256"] == workers.source_identity()[0]
    command[command.index("--wait-seconds") + 1] = "1"
    assert b'"attempted_runs": 0' in run_local(command, 20)
    with worker_engine.connect() as connection:
        instances = list(
            execute(
                connection,
                "SELECT instance_id,state FROM v2_worker_instances WHERE root_id=:id",
                id=root_id,
            ).mappings()
        )
        assert len(instances) == 2 and all(row["state"] == "stopped" for row in instances)
        assert len({row["instance_id"] for row in instances}) == 2
        assert execute(connection, "SELECT count(*) FROM v2_research_attempts").scalar_one() == 0
        assert execute(connection, "SELECT count(*) FROM v2_copilot_calls").scalar_one() == 0
        assert execute(connection, "SELECT count(*) FROM v2_memo_calls").scalar_one() == 0
    # Keep the lock as retained diagnostic evidence; a missing required lock
    # must fail before another instance or attempt is registered.
    (package / "uv.lock").rename(package / "uv.lock.retained")
    with pytest.raises(ValueError):
        run_local(command, 20)
    with worker_engine.connect() as connection:
        assert (
            execute(
                connection, "SELECT count(*) FROM v2_worker_instances WHERE root_id=:id", id=root_id
            ).scalar_one()
            == 2
        )
