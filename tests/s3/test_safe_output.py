"""Synthetic-only redaction and anonymous-pipe guards; no AWS or config access."""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import pytest
from s3_safe_output import MemoryCapture, redact_text

import marketlab

pytestmark = pytest.mark.s3
SYNTHETIC = "Synthetic/Key+123="


def _offline_environment():
    env = {
        key: os.environ[key]
        for key in ("SystemRoot", "WINDIR", "ComSpec", "PATH", "PATHEXT", "TEMP", "TMP")
        if key in os.environ
    }
    env["MARKETLAB_PHASE6_OFFLINE_GUARD"] = "1"
    return env


def _spawn_guarded_child(queue):
    from marketlab.config import Settings

    assert Settings.model_config["env_file"] is None
    assert os.environ["MARKETLAB_PHASE6_BOOTSTRAP_ACTIVE"] == "guarded-python-v1"
    assert os.environ["MARKETLAB_PHASE6_OFFLINE_GUARD"] == "1"
    try:
        open(".env", "rb")
    except PermissionError:
        pass
    else:
        raise AssertionError("Spawned child dotenv denial missing")
    Settings()
    queue.put(("guarded", os.getpid()))


def test_raw_escaped_mixed_and_encoded_forms_are_removed(monkeypatch):
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", SYNTHETIC)
    monkeypatch.setenv("MARKETLAB_PHASE6_REDACTION_VALUES", json.dumps(["issued-token"]))
    forms = (
        SYNTHETIC,
        quote(SYNTHETIC, safe=""),
        SYNTHETIC.replace("/", r"\/"),
        "".join(rf"\u{ord(char):04x}" for char in SYNTHETIC),
        "".join(rf"\x{ord(char):02x}" for char in SYNTHETIC),
        "".join(f"%{ord(char):02x}" if i % 2 else char for i, char in enumerate(SYNTHETIC)),
        "".join(f"&#{ord(char)};" for char in SYNTHETIC),
        base64.b64encode(SYNTHETIC.encode()).decode(),
        "issued-token",
    )
    for form in forms:
        assert redact_text("before " + form + " after") == "before <redacted> after"


def test_in_memory_pipe_drains_then_redacts_without_disk(monkeypatch):
    monkeypatch.setenv("MARKETLAB_STORAGE_S3_SESSION_TOKEN", SYNTHETIC)
    capture = MemoryCapture(limit=1024)
    capture.writer.write(SYNTHETIC.encode())
    capture.finish()
    assert capture.sanitized() == "<redacted>"
    assert not capture.thread.is_alive() and not capture.overflow


def test_overflow_is_bounded_and_fails_closed():
    capture = MemoryCapture(limit=8)
    capture.writer.write(b"synthetic output beyond bound")
    with pytest.raises(AssertionError, match="exceeded its bound"):
        capture.finish()
    assert len(capture.buffer) == 8 and capture.overflow and not capture.thread.is_alive()


def test_cutoff_inside_secret_persists_only_fixed_diagnostic(monkeypatch):
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", SYNTHETIC)
    capture = MemoryCapture(limit=8)
    capture.writer.write(SYNTHETIC.encode())
    with pytest.raises(AssertionError, match="exceeded its bound"):
        capture.finish()
    assert capture.sanitized() == "Owned child output unavailable: bounded capture failed.\n"
    assert SYNTHETIC[:8] not in capture.sanitized()


def test_capture_read_error_drops_buffer_even_after_drain():
    capture = MemoryCapture()
    capture.writer.write(b"partial protected diagnostic")
    capture.finish()
    capture.read_error = True
    assert capture.sanitized() == "Owned child output unavailable: bounded capture failed.\n"


def test_explicit_bootstrap_guards_before_settings_and_child_entrypoint(tmp_path):
    root = Path(marketlab.__file__).resolve().parents[2]
    bootstrap = root / "artifacts/v2-phase6-s3-acceptance/guarded_python.py"
    code = """
import os
from marketlab.config import Settings
assert Settings.model_config['env_file'] is None
assert os.environ['MARKETLAB_PHASE6_BOOTSTRAP_ACTIVE'] == 'guarded-python-v1'
try:
    open('.env', 'rb')
except PermissionError:
    pass
else:
    raise AssertionError('dotenv denial missing')
Settings()
"""
    result = subprocess.run(
        [sys.executable, "-I", "-S", str(bootstrap), "--", "-c", code],
        cwd=tmp_path,
        env=_offline_environment(),
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0


def test_explicit_bootstrap_wraps_real_spawn_child_and_drains(tmp_path):
    root = Path(marketlab.__file__).resolve().parents[2]
    bootstrap = root / "artifacts/v2-phase6-s3-acceptance/guarded_python.py"
    code = f"""
import multiprocessing as mp
import sys
sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})
from test_safe_output import _spawn_guarded_child
context = mp.get_context('spawn')
queue = context.Queue()
child = context.Process(target=_spawn_guarded_child, args=(queue,))
child.start()
try:
    child.join(10)
    assert not child.is_alive(), 'Synthetic guarded spawn did not drain'
    assert child.exitcode == 0
    assert queue.get(timeout=2) == ('guarded', child.pid)
finally:
    if child.is_alive():
        child.terminate()
        child.join(2)
        raise AssertionError('Synthetic guarded spawn required termination')
    child.close()
    queue.close()
    queue.join_thread()
"""
    result = subprocess.run(
        [sys.executable, "-I", "-S", str(bootstrap), "--", "-c", code],
        cwd=tmp_path,
        env=_offline_environment(),
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0


def test_bootstrap_missing_isolated_flag_fails_closed_before_entrypoint(tmp_path):
    root = Path(marketlab.__file__).resolve().parents[2]
    bootstrap = root / "artifacts/v2-phase6-s3-acceptance/guarded_python.py"
    # Keep -S even in this negative case: never execute site/.pth startup just to
    # test a missing flag. The shared fail-closed condition also requires -S.
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            str(bootstrap),
            "--",
            "-c",
            "raise AssertionError('entrypoint ran')",
        ],
        cwd=tmp_path,
        env=_offline_environment(),
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode != 0
    assert b"requires isolated no-site startup" in result.stderr
    assert b"entrypoint ran" not in result.stderr and result.stdout == b""
