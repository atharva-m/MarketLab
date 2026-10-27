"""Safety boundaries for the R9 evidence adapters; no live services required."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("r9_common", SCRIPTS / "r9_common.py")
assert spec is not None and spec.loader is not None
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)


@pytest.mark.parametrize("value", ["../r9-x", "r9-../x", "R9-x", "r9-", "r9-x/y", "r9-" + "a" * 61])
def test_prefix_rejects_path_and_unbounded_identity(value):
    with pytest.raises(ValueError):
        common.prefix(value)


def test_containment_rejects_root_parent_and_sibling(tmp_path):
    root = tmp_path / "owned"
    root.mkdir()
    assert common.contained(root / "one/file.json", root) == root / "one/file.json"
    for candidate in (root, root / "../other", tmp_path / "owned-sibling/file"):
        with pytest.raises(RuntimeError):
            common.contained(candidate, root)


def test_owned_connections_refuse_wrong_endpoint_before_docker(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BASE", tmp_path)
    (tmp_path / "connection-private.json").write_text(
        json.dumps(
            {
                "owner": "r9-20261027",
                "database_url": "postgresql+psycopg://x:x@127.0.0.1:5432/marketlab",
                "redis_url": "redis://127.0.0.1:56387/0",
                "ollama_url": "http://127.0.0.1:11444",
                "storage_path": str(tmp_path / "storage"),
            }
        )
    )
    monkeypatch.setattr(
        common, "docker", lambda *args: pytest.fail("Original endpoint reached Docker")
    )
    with pytest.raises(RuntimeError, match="PostgreSQL endpoint"):
        common.settings()


def test_external_inputs_require_matching_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BASE", tmp_path)
    data = tmp_path / "data.json"
    data.write_text("{}")
    entry = {"path": str(data), "sha256": "0" * 64}
    (tmp_path / "retained-inputs.json").write_text(
        json.dumps(
            {
                "schema": "r9-retained-inputs-v1",
                "files": {name: entry for name in ("catalog", "references", "research_snapshot")},
            }
        )
    )
    with pytest.raises(RuntimeError, match="hash mismatch"):
        common.inputs()


def test_cold_dispatch_keeps_verifier_output_distinct(tmp_path, monkeypatch):
    handoff_spec = importlib.util.spec_from_file_location(
        "r9_handoff_test", SCRIPTS / "r9_handoff.py"
    )
    assert handoff_spec is not None and handoff_spec.loader is not None
    handoff = importlib.util.module_from_spec(handoff_spec)
    handoff_spec.loader.exec_module(handoff)
    observed = []

    class Envelope:
        def __init__(self, identity, phase):
            self.identity = identity
            self.path = tmp_path / f"{identity}-{phase}.json"
            self.path.write_text("{}")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    async def fake_cold(evidence):
        native = tmp_path / f"{evidence.identity}-cold.json"
        assert not native.exists()
        native.write_text("{}")
        observed.append((evidence.path.name, native.name))

    monkeypatch.setattr(handoff, "Invocation", Envelope)
    monkeypatch.setattr(handoff, "cold", fake_cold)

    def run_without_io(coroutine):
        # The dispatch regression needs no real event loop or socketpair.
        with pytest.raises(StopIteration):
            coroutine.send(None)

    monkeypatch.setattr(handoff.asyncio, "run", run_without_io)
    monkeypatch.setattr(
        sys, "argv", [str(SCRIPTS / "r9_handoff.py"), "cold", "--prefix", "r9-dispatch"]
    )
    handoff.main()
    assert observed == [("r9-dispatch-cold-envelope.json", "r9-dispatch-cold.json")]


@pytest.mark.parametrize(
    "path",
    [
        "demo/public/clip.json",
        "demo/captures/shot.png",
        "demo/media/audio.wav",
        "artifacts/evidence.json",
        "secrets/key.txt",
        "demo/private.zip",
        "demo/node_modules/pkg/index.js",
    ],
)
def test_overlay_excludes_media_evidence_and_installed_files(path):
    module_spec = importlib.util.spec_from_file_location(
        "r9_overlay_test", SCRIPTS / "r9_handoff.py"
    )
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    assert not module.source_allowed(Path(path))


def test_command_label_cannot_create_ntfs_alternate_stream(tmp_path, monkeypatch):
    module_spec = importlib.util.spec_from_file_location(
        "r9_command_test", SCRIPTS / "r9_handoff.py"
    )
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    monkeypatch.setattr(module, "BASE", tmp_path)

    def fake_run(command, **kwargs):
        kwargs["stdout"].write("verified log\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    evidence = SimpleNamespace(identity="r9-command", data={}, flush=lambda: None)
    log = module.checked(["test"], evidence, "test:e2e")
    assert log.name == "r9-command-test-e2e.log"
    assert log.read_text() == "verified log\n"
    assert evidence.data["commands"][0]["label"] == "test:e2e"


def test_pytest_temporary_path_preserves_windows_marker_budget(tmp_path, monkeypatch):
    module_spec = importlib.util.spec_from_file_location("r9_temp_test", SCRIPTS / "r9_handoff.py")
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    clone = tmp_path / "r9-clone-second-checkout"
    monkeypatch.setattr(module, "PROJECT", clone)
    temporary = module.pytest_temp("r9-fresh-checks-second", "offline")
    assert temporary.parent == clone / "artifacts/t"
    assert temporary.parent.is_dir() and not temporary.exists()
    assert len(temporary.name) == 8
    marker = temporary / "test_crash_gate_budget_starts0" / "control" / ("a" * 64 + ".crash-target")
    assert len(str(marker.relative_to(tmp_path))) < 180
    actual_clone = SCRIPTS.parent / "artifacts/r9-20261027/r9-clone-second-checkout"
    actual_marker = (
        actual_clone
        / "artifacts/t/12345678"
        / "test_crash_gate_budget_starts0"
        / "control"
        / ("a" * 64 + ".crash-target")
    )
    assert len(str(actual_marker)) < 260
    temporary.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="Fresh test temporary"):
        module.pytest_temp("r9-fresh-checks-second", "offline")


def test_fresh_pytest_temp_works_in_real_subprocess(tmp_path, monkeypatch):
    module_spec = importlib.util.spec_from_file_location(
        "r9_real_temp_test", SCRIPTS / "r9_handoff.py"
    )
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    clone = tmp_path / "c"
    monkeypatch.setattr(module, "PROJECT", clone)
    temporary = module.pytest_temp("r9-real-subprocess", "offline")
    source = tmp_path / "test_scratch.py"
    source.write_text(
        "def test_scratch(tmp_path):\n"
        "    proof = tmp_path / 'proof.txt'\n"
        "    proof.write_text('ok')\n"
        "    assert proof.read_text() == 'ok'\n"
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(source), "--basetemp=" + str(temporary)],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert list(temporary.rglob("proof.txt"))


def test_checkout_uses_short_owned_workspace_path(tmp_path, monkeypatch):
    module_spec = importlib.util.spec_from_file_location(
        "r9_checkout_test", SCRIPTS / "r9_handoff.py"
    )
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    monkeypatch.setattr(module, "PROJECT", tmp_path)
    destination = module.checkout_path("r9-fresh-short-clone")
    assert destination.parent == tmp_path / "artifacts/c"
    assert len(destination.name) == 8
    assert destination != module.checkout_path("r9-another-short-clone")


@pytest.mark.skipif(os.name != "nt", reason="Windows classic path preflight")
def test_retained_copy_preflight_refuses_long_target_before_creating_storage(tmp_path, monkeypatch):
    module_spec = importlib.util.spec_from_file_location("r9_copy_test", SCRIPTS / "r9_handoff.py")
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    source = tmp_path / "source"
    (source / "datasets/day").mkdir(parents=True)
    (source / "datasets/day/manifest.json").write_text("{}")
    destination = tmp_path / ("long" * 40) / "s"
    monkeypatch.setattr(module, "settings", lambda: SimpleNamespace(storage_path=destination))
    evidence = SimpleNamespace(identity="r9-copy-test", data={}, flush=lambda: None)
    with pytest.raises(RuntimeError, match="Windows budget"):
        module.copy_retained(source, evidence)
    assert not destination.exists()


def test_external_compatibility_harness_resolves_original_dataset_fixture(tmp_path, monkeypatch):
    module_spec = importlib.util.spec_from_file_location(
        "r9_fixture_test", SCRIPTS / "r9_handoff.py"
    )
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    monkeypatch.setattr(module, "BASE", tmp_path)
    original = (SCRIPTS.parent / "tests/test_r8_source_compatibility_integration.py").read_text()
    adapted, changes = module.compatibility_source(original, tmp_path / "unused-old-input.json")
    restored = adapted
    for before, after in reversed(list(changes.items())):
        restored = restored.replace(after, before)
    assert restored == original
    generated = tmp_path / "test_external_compatibility.py"
    generated.write_text(adapted)
    temporary = tmp_path / "plan"
    environment = {
        **os.environ,
        "PYTHONPATH": str(SCRIPTS.parent / "tests") + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--setup-plan",
            "-q",
            str(generated),
            "--basetemp=" + str(temporary),
        ],
        cwd=SCRIPTS.parent,
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "dataset_engine" in result.stdout
    assert "fixture 'dataset_engine' not found" not in result.stdout
