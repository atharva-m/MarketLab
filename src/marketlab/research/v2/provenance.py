"""Mandatory source/lock identity with separately optional, honest Git observations."""

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from marketlab.datasets.v2.common import V2Error, digest, sha256_file


def git_observation(project: Path) -> dict[str, Any]:
    def unavailable(reason: str) -> dict[str, Any]:
        return {
            "git_revision": None,
            "git_dirty": None,
            "git_provenance": "unavailable",
            "git_provenance_reason": reason,
        }

    if not (project / ".git").exists():
        return unavailable("checkout_unavailable")
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=project,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout
    except FileNotFoundError:
        return unavailable("git_unavailable")
    except (OSError, UnicodeError, subprocess.SubprocessError):
        return unavailable("git_inspection_unavailable")
    if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", revision) is None:
        return unavailable("git_metadata_invalid")
    return {
        "git_revision": revision,
        "git_dirty": bool(status),
        "git_provenance": "captured",
        "git_provenance_reason": None,
    }


def execution_identity(project: Path | None = None) -> dict[str, Any]:
    project = Path(__file__).resolve().parents[4] if project is None else project.resolve()
    source = project / "src/marketlab"
    try:
        if not source.is_dir() or source.is_symlink() or source.is_junction():
            raise OSError("Required source tree unavailable")
        paths = []

        def failed(error: OSError) -> None:
            raise error

        for directory, names, filenames in os.walk(source, onerror=failed, followlinks=False):
            for name in names:
                child = Path(directory) / name
                if child.is_symlink() or child.is_junction():
                    raise OSError("Linked source directory unsupported")
            for name in filenames:
                if name.endswith(".py"):
                    path = Path(directory) / name
                    if path.is_symlink():
                        raise OSError("Linked source file unsupported")
                    paths.append(path)
        files = {p.relative_to(project).as_posix(): sha256_file(p) for p in sorted(paths)}
        required = {
            "src/marketlab/app.py",
            "src/marketlab/analytics/v2/bars.py",
            "src/marketlab/research/v2/service.py",
            "src/marketlab/research/v2/spec.py",
            "src/marketlab/research/v2/numerics.py",
            "src/marketlab/research/v2/provenance.py",
        }
        if not required <= set(files):
            raise OSError("Required research source modules unavailable")
        lock = project / "uv.lock"
        if not lock.is_file() or lock.is_symlink():
            raise OSError("Required dependency lock unavailable")
        files["uv.lock"] = sha256_file(lock)
    except (OSError, ValueError) as error:
        raise V2Error("unavailable", "Research source provenance is unavailable") from error
    # As for Phase 2 packaged ingestion, exact readable source/lock bytes are
    # mandatory. A missing Git executable/checkout never invents a clean revision.
    return {
        **git_observation(project),
        "lock_sha256": files["uv.lock"],
        "schema": "research-spec-v2",
        "numerics": "research-numerics-v2",
        "bars": "bars-v2",
        "inventory": "all-marketlab-python-and-lock-v1",
        "source_sha256": digest(files),
    }
