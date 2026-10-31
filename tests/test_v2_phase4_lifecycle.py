"""Small actual Windows lifecycle coverage for the Phase 4 acceptance owner."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/v2_phase4_lifecycle.py"
SPEC = importlib.util.spec_from_file_location("phase4_lifecycle_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
pytestmark = pytest.mark.skipif(os.name != "nt", reason="Actual Windows Job containment")


@pytest.fixture
def job():
    owner = MODULE.OwnedJob()
    try:
        yield owner
    finally:
        if owner.active():
            owner.terminate()
        owner.close()


def launch(job, tmp_path, code):
    with (tmp_path / "worker.log").open("ab") as output:
        return job.spawn(
            [str(Path(sys.executable).resolve()), "-c", code],
            cwd=tmp_path,
            env=dict(os.environ),
            output=output,
        )


def test_normal_completion_retains_counter_after_exit(job, tmp_path):
    child = launch(job, tmp_path, "payload=bytearray(8*1024**2)")
    assert child.wait(10) == 0
    job.wait_empty(10)
    assert child.birth > 0 and child.record()["exit_code"] == 0
    assert job.peak_commit() >= 8 * 1024**2
    assert MODULE.supervisor_peak_commit() > 0


def test_startup_failure_leaves_empty_group(job, tmp_path):
    invalid = tmp_path / "invalid.exe"
    invalid.write_bytes(b"This is not an executable")
    with (tmp_path / "startup.log").open("ab") as output:
        with pytest.raises(OSError):
            job.spawn([str(invalid)], cwd=tmp_path, env=dict(os.environ), output=output)
    assert job.active() == 0


def test_worker_crash_has_explicit_exit_and_drains(job, tmp_path):
    child = launch(job, tmp_path, "import os; os._exit(7)")
    assert child.wait(10) == 7
    job.wait_empty(10)
    assert job.active() == 0 and job.peak_commit() > 0


def test_cancellation_stops_cooperatively(job, tmp_path):
    child = launch(
        job,
        tmp_path,
        "from pathlib import Path; import time\nwhile not Path('stop').exists(): time.sleep(.01)\n",
    )
    (tmp_path / "stop").write_text("stop")
    assert child.wait(10) == 0
    job.wait_empty(10)


def test_shutdown_timeout_can_only_terminate_owned_group(job, tmp_path):
    child = launch(job, tmp_path, "import time; time.sleep(60)")
    with pytest.raises(subprocess.TimeoutExpired):
        child.wait(0.1)
    job.terminate()
    assert child.wait(10) == 91
    assert job.active() == 0 and job.peak_commit() > 0


def test_descendant_is_contained_after_parent_exit(job, tmp_path):
    child = launch(
        job,
        tmp_path,
        "import subprocess,sys; subprocess.Popen([sys.executable,'-c',"
        "'import time; time.sleep(1)'])",
    )
    assert child.wait(10) == 0
    job.wait_empty(10)
    assert job.active() == 0 and job.peak_commit() > 0
