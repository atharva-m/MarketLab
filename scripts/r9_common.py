"""R9 evidence and ownership checks, without resource creation or cleanup."""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from pydantic import SecretStr

from marketlab.config import Settings
from marketlab.datasets.source import file_hash
from marketlab.research.service import execution_identity

PROJECT = Path(__file__).resolve().parents[1]
BASE = PROJECT / "artifacts/r9-20261027"
OWNER = "r9-20261027"
MODEL = "qwen3.5:9b-q4_K_M"
DIGEST = "56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def prefix(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"r9-[a-z0-9][a-z0-9-]{0,59}", value):
        raise ValueError("Expected bounded lowercase r9- invocation identity")
    return value


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)


def contained(path: Path, root: Path | None = None) -> Path:
    root = BASE if root is None else root
    resolved, resolved_root = path.resolve(), root.resolve()
    require(
        resolved != resolved_root and resolved.is_relative_to(resolved_root),
        "Path outside owned R9 root",
    )
    current = path.absolute()
    while current != current.parent:
        require(
            not current.is_symlink() and not current.is_junction(), "Linked paths are forbidden"
        )
        if current == root.absolute():
            break
        current = current.parent
    return resolved


def docker(*arguments: str) -> str:
    return subprocess.check_output(
        ["docker", *arguments],
        text=True,
        timeout=20,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def settings() -> Settings:
    private = read(BASE / "connection-private.json")
    require(private.get("owner") == OWNER, "R9 connection owner mismatch")
    url = sa.engine.make_url(private["database_url"])
    require(
        (url.host, url.port, url.database) == ("127.0.0.1", 55445, "marketlab"),
        "R9 PostgreSQL endpoint mismatch",
    )
    require(private["redis_url"] == "redis://127.0.0.1:56387/0", "R9 Redis endpoint mismatch")
    require(private["ollama_url"] == "http://127.0.0.1:11444", "R9 model endpoint mismatch")
    storage = contained(Path(private["storage_path"]))
    for kind, container_port, host_port in (
        ("postgres", "5432/tcp", "55445"),
        ("redis", "6379/tcp", "56387"),
    ):
        recorded = read(BASE / f"owned-{kind}.json")
        recorded = recorded[0] if isinstance(recorded, list) else recorded
        actual = json.loads(docker("inspect", recorded["Id"]))[0]
        require(
            actual["Id"] == recorded["Id"]
            and actual["Name"] == recorded["Name"]
            and actual["Image"] == recorded["Image"]
            and actual["State"]["Running"]
            and (actual["Config"].get("Labels") or {}).get("marketlab.r9.owner") == OWNER
            and actual["NetworkSettings"]["Ports"][container_port]
            == [{"HostIp": "127.0.0.1", "HostPort": host_port}],
            "R9 resource identity, label or binding mismatch",
        )
    return Settings(
        database_url=SecretStr(private["database_url"]),
        database_password=None,
        redis_url=SecretStr(private["redis_url"]),
        ollama_url=private["ollama_url"],
        storage_path=storage,
    )


def engine_for(configuration: Settings) -> sa.Engine:
    return sa.create_engine(
        configuration.sqlalchemy_url, connect_args=configuration.database_connect_args
    )


def environment(configuration: Settings) -> dict[str, str]:
    return {
        **os.environ,
        "MARKETLAB_DATABASE_URL": configuration.sqlalchemy_url.render_as_string(
            hide_password=False
        ),
        "MARKETLAB_DATABASE_PASSWORD": configuration.sqlalchemy_url.password or "",
        "MARKETLAB_REDIS_URL": configuration.redis_url.get_secret_value(),
        "MARKETLAB_STORAGE_PATH": str(configuration.storage_path),
        "MARKETLAB_OLLAMA_URL": configuration.ollama_url,
        "MARKETLAB_METRICS_PORT": "0",
    }


def resource_ids() -> dict[str, Any]:
    result = {}
    for kind in ("postgres", "redis"):
        item = read(BASE / f"owned-{kind}.json")
        row = item[0] if isinstance(item, list) else item
        result[kind] = {"id": row["Id"], "name": row["Name"], "image": row["Image"]}
    return result


def owned_process(kind: str, port: int) -> dict[str, Any]:
    """Recheck PID birth, executable, command and listener; a port alone is not ownership."""
    require(kind in {"ollama", "api", "ui", "collector", "worker"}, "Unknown owned process role")
    manifest = read(BASE / f"owned-{kind}.json")
    require(
        manifest.get("owner") == OWNER and manifest.get("port") == port,
        "Owned process role mismatch",
    )
    pid = manifest["pid"]
    require(type(pid) is int and pid > 0 and os.name == "nt", "Windows PID inventory required")
    command = (
        f"$p = Get-CimInstance Win32_Process -Filter 'ProcessId={pid}'; "
        f"$l = @(Get-NetTCPConnection -State Listen -LocalPort {port} -ErrorAction Stop); "
        "[pscustomobject]@{pid=$p.ProcessId;creation_time=$p.CreationDate.ToString('o');"
        "executable=$p.ExecutablePath;command_line=$p.CommandLine;"
        "listeners=@($l | Select-Object LocalAddress,OwningProcess)} | "
        "ConvertTo-Json -Depth 4 -Compress"
    )
    result = json.loads(
        subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", command], text=True, timeout=30
        )
    )
    require(
        result["pid"] == pid
        and datetime.fromisoformat(result["creation_time"])
        == datetime.fromisoformat(manifest["creation_time"]),
        "Owned process birth changed",
    )
    require(
        result["executable"].casefold() == manifest["executable"].casefold()
        and result["command_line"] == manifest["command_line"],
        "Owned process executable/source command changed",
    )
    require(
        any(
            row["OwningProcess"] == pid and row["LocalAddress"] == "127.0.0.1"
            for row in result["listeners"]
        ),
        "Owned process listener changed",
    )
    return {
        "pid": pid,
        "creation_time": result["creation_time"],
        "executable": result["executable"],
        "port": port,
    }


def inputs() -> dict[str, Path]:
    """External evidence inputs are explicit and hash-pinned, never copied implicitly."""
    manifest = read(BASE / "retained-inputs.json")
    require(manifest.get("schema") == "r9-retained-inputs-v1", "Retained input schema mismatch")
    names = set(manifest["files"])
    require(
        {"catalog", "references", "research_snapshot"}
        <= names
        <= {
            "catalog",
            "references",
            "research_snapshot",
            "memo_snapshot",
            "scenarios",
            "old_execution",
            "native_reference",
        },
        "Unexpected retained inputs",
    )
    result = {}
    for name, item in manifest["files"].items():
        path = Path(item["path"]).resolve()
        require(path.is_file() and not path.is_symlink(), "Retained input missing or linked")
        require(file_hash(path) == item["sha256"], "Retained input hash mismatch")
        result[name] = path
    return result


class Invocation:
    def __init__(self, identity: str, phase: str):
        self.identity = prefix(identity)
        BASE.mkdir(parents=True, exist_ok=True)
        self.path = contained(BASE / f"{identity}-{phase}.json")
        self.started = time.monotonic()
        self.data: dict[str, Any] = {
            "schema": "r9-invocation-v1",
            "invocation": identity,
            "phase": phase,
            "status": "running",
            "started_at": datetime.now(UTC).isoformat(),
            "command": sys.argv,
            "execution": execution_identity(),
            "lock_sha256": file_hash(PROJECT / "uv.lock"),
            "frontend_lock_sha256": file_hash(PROJECT / "frontend/package-lock.json"),
            "script_sha256": file_hash(Path(sys.argv[0])),
        }
        with self.path.open("x", encoding="utf-8") as stream:
            json.dump(self.data, stream, indent=2, default=str)

    def flush(self) -> None:
        save(self.path, self.data)

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        self.data.update(
            status="passed" if error is None else "failed",
            finished_at=datetime.now(UTC).isoformat(),
            seconds=time.monotonic() - self.started,
        )
        if error is not None:
            self.data.update(
                error_type=type(error).__name__,
                error="See protected command logs; no exception payload is copied",
            )
        self.flush()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
