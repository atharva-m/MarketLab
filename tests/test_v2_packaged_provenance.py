"""Exact source identity works without Git and fails closed on unreadable code/lock."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from test_v2_ingestion_integration import v2_engine  # noqa: F401
from test_v2_research import body
from test_v2_research_integration import fixture_version, research_engine  # noqa: F401

from marketlab.analytics.bars import BarService
from marketlab.app import create_app
from marketlab.datasets.v2.common import V2Error, digest, sha256_file
from marketlab.research.v2 import provenance
from marketlab.research.v2.service import ResearchService
from marketlab.research.v2.spec import ResearchSpec


@pytest.fixture
def package(tmp_path):
    project = Path(__file__).resolve().parents[1]
    target = tmp_path / "pkg"
    shutil.copytree(project / "src", target / "src", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(project / "uv.lock", target / "uv.lock")
    return target


def test_genuine_git_and_exact_inventory_are_independent():
    project = Path(__file__).resolve().parents[1]
    observed = provenance.execution_identity()
    files = {
        p.relative_to(project).as_posix(): sha256_file(p)
        for p in sorted((project / "src/marketlab").rglob("*.py"))
    }
    files["uv.lock"] = sha256_file(project / "uv.lock")
    assert observed["source_sha256"] == digest(files)
    assert observed["lock_sha256"] == files["uv.lock"]
    if shutil.which("git") and (project / ".git").exists():
        assert observed["git_provenance"] == "captured"
        assert type(observed["git_dirty"]) is bool and len(observed["git_revision"]) in {40, 64}


@pytest.mark.parametrize("mode", ["no_checkout", "no_git_binary"])
def test_real_copied_package_subprocess_without_git(package, mode):
    environment = dict(os.environ, PYTHONPATH=str(package / "src"))
    if mode == "no_git_binary":
        (package / ".git").mkdir()
        environment["PATH"] = str(Path(sys.executable).parent)
    script = """import json
from pathlib import Path
from marketlab.research.v2 import provenance
from marketlab.datasets.publication import _build
from marketlab.datasets.source import DatasetError
identity=provenance.execution_identity()
try:
 _build()
 legacy_failed=False
except DatasetError:
 legacy_failed=True
print(json.dumps({'identity':identity,'module':str(Path(provenance.__file__).resolve()),'legacy_failed':legacy_failed}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=package,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    identity = result["identity"]
    assert Path(result["module"]).is_relative_to(package / "src")
    assert identity["source_sha256"] == provenance.execution_identity()["source_sha256"]
    assert identity["git_revision"] is None and identity["git_dirty"] is None
    assert identity["git_provenance"] == "unavailable"
    assert identity["git_provenance_reason"] == (
        "checkout_unavailable" if mode == "no_checkout" else "git_unavailable"
    )
    if mode == "no_git_binary":
        assert result["legacy_failed"]


@pytest.mark.parametrize(
    "missing", ["src/marketlab", "src/marketlab/research/v2/service.py", "uv.lock"]
)
def test_missing_source_or_lock_fails_before_optional_git(package, monkeypatch, missing):
    path = package / missing
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    monkeypatch.setattr(
        provenance,
        "git_observation",
        lambda *args: pytest.fail("Mandatory identity must fail first"),
    )
    with pytest.raises(V2Error, match="source provenance is unavailable") as error:
        provenance.execution_identity(package)
    assert error.value.code == "unavailable"


@pytest.mark.parametrize("target", ["service.py", "uv.lock"])
def test_unreadable_source_does_not_become_git_fallback(package, monkeypatch, target):
    original = provenance.sha256_file

    def read(path):
        if path.name == target:
            raise OSError("private unreadable source path")
        return original(path)

    monkeypatch.setattr(provenance, "sha256_file", read)
    with pytest.raises(V2Error) as error:
        provenance.execution_identity(package)
    assert error.value.code == "unavailable" and "private" not in str(error.value)


def test_unreadable_source_subdirectory_fails_closed(package, monkeypatch):
    def walk(*args, **kwargs):
        kwargs["onerror"](PermissionError("private directory"))
        return []

    monkeypatch.setattr(provenance.os, "walk", walk)
    with pytest.raises(V2Error) as error:
        provenance.execution_identity(package)
    assert error.value.code == "unavailable" and "private" not in str(error.value)


def test_optional_git_decode_failure_cannot_mask_source_or_invent_clean_state(package, monkeypatch):
    (package / ".git").mkdir()

    def invalid(*args, **kwargs):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "private metadata")

    monkeypatch.setattr(provenance.subprocess, "run", invalid)
    identity = provenance.execution_identity(package)
    assert identity["git_revision"] is None and identity["git_dirty"] is None
    assert identity["git_provenance_reason"] == "git_inspection_unavailable"
    assert "private" not in json.dumps(identity)


@pytest.mark.asyncio
async def test_http_missing_provenance_returns_safe_503(tmp_path):
    app = create_app()

    async def submit(*args):
        provenance.execution_identity(tmp_path / "missing-private-source")

    app.state.v2_research_service = SimpleNamespace(submit=submit)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        response = await client.post(
            "/v2/research/runs", json=body(), headers={"Idempotency-Key": "provenance"}
        )
    assert response.status_code == 503 and response.json()["error"]["code"] == "unavailable"
    assert "missing-private-source" not in response.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_host_package_compatible_claim_wrong_source_skip_and_old_read(
    research_engine,  # noqa: F811
    package,
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "storage"
    version = fixture_version(research_engine, root, tmp_path)
    request = body()
    request["instrument_ids"] = ["binance:spot:BTCUSDT"]
    request["dataset_versions"] = [version]
    spec = ResearchSpec.create(request)
    base = BarService(research_engine, root)
    service = ResearchService(base)
    host = provenance.execution_identity()
    packaged = provenance.execution_identity(package)
    assert host["source_sha256"] == packaged["source_sha256"] and packaged["git_revision"] is None
    try:
        run, _ = await service.submit(spec, "host-submitted")
        service._execution = packaged
        assert await service.work(1, run) == 1 and service.inspect(run)["state"] == "succeeded"
        assert service.inspect(run)["fingerprint"]["execution"] == host
        saved = {kind: service.read(run, kind) for kind in ("results", "summary")}
        service._execution = host
        queued, _ = await service.submit(spec, "wrong-source")
        service._execution = dict(packaged, source_sha256="f" * 64)
        assert await service.work(1, queued) == 0 and service.inspect(queued)["attempt_count"] == 0
        service._execution = dict(packaged, lock_sha256="f" * 64)
        assert await service.work(1, queued) == 0 and service.inspect(queued)["attempt_count"] == 0

        def unavailable():
            raise V2Error("unavailable", "Research source provenance is unavailable")

        monkeypatch.setattr("marketlab.research.v2.service.execution_identity", unavailable)
        service._execution = None
        with pytest.raises(V2Error):
            await service.work(1, queued)
        assert service.inspect(queued)["attempt_count"] == 0
        for kind in ("results", "summary"):
            assert service.read(run, kind) == saved[kind]
    finally:
        await service.close()
        await base.close()
