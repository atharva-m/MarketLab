"""Preserve the explicitly active no-dotenv bootstrap in direct test children."""

import os
import sys
from pathlib import Path


def command(*arguments: str) -> list[str]:
    if os.environ.get("MARKETLAB_PHASE6_BOOTSTRAP_ACTIVE") == "guarded-python-v1":
        return [
            sys.executable,
            "-I",
            "-S",
            str(Path(__file__).parent / "s3/guarded_python.py"),
            "--",
            *arguments,
        ]
    return [sys.executable, *arguments]


def script_command(path: Path, *arguments: str) -> list[str]:
    if os.environ.get("MARKETLAB_PHASE6_BOOTSTRAP_ACTIVE") == "guarded-python-v1":
        # Preserve __file__ and argv[0] for the authored temporary script while
        # keeping the bootstrap active outside the repository source tree.
        return command(
            "-c",
            "import runpy,sys; path=sys.argv.pop(1); sys.argv[0]=path; "
            "runpy.run_path(path,run_name='__main__')",
            str(path),
            *arguments,
        )
    return command(str(path), *arguments)
