"""Destructive closeout guards without touching Docker or retained evidence."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location(
    "phase4_closeout_tests", SCRIPTS / "v2_phase4_closeout.py"
)
assert spec and spec.loader
closeout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(closeout)
from v2_phase4_snapshot import exact_except_constraints, row_digest  # noqa: E402


def resources() -> dict[str, Any]:
    return {
        "containers": [
            {
                "Id": "owned",
                "Name": "/marketlab-v2p4-package",
                "Image": "image",
                "Labels": {closeout.LABEL: closeout.OWNER},
                "Mounts": [
                    {"Type": "volume", "Name": "owned-data", "Destination": "/data/marketlab"}
                ],
                "HostBindings": {},
                "Running": False,
                "StartedAt": "same",
                "RestartCount": 0,
                "NetworkMode": "owned-net",
                "Entrypoint": [],
                "Cmd": [],
            }
        ],
        "volumes": [{"Name": "owned-data", "Labels": {closeout.LABEL: closeout.OWNER}}],
        "networks": [
            {
                "Id": "net",
                "Name": "owned-net",
                "Labels": {closeout.LABEL: closeout.OWNER},
                "Containers": {"owned": {}},
            }
        ],
        "images": [
            {"Id": "image", "RepoTags": ["owned:tag"], "Labels": {closeout.LABEL: closeout.OWNER}}
        ],
    }


def protected() -> list[dict[str, Any]]:
    return [
        {
            "Id": "protected",
            "Image": "protected-image",
            "Mounts": [{"Type": "volume", "Name": "protected-data"}],
        }
    ]


@pytest.mark.parametrize("kind", ["containers", "volumes", "images"])
def test_protected_resources_rejected_even_with_owned_label(kind: str) -> None:
    value = resources()
    field, identifier = {
        "containers": ("Id", "protected"),
        "volumes": ("Name", "protected-data"),
        "images": ("Id", "protected-image"),
    }[kind]
    value[kind][0][field] = identifier
    with pytest.raises(RuntimeError, match="Protected"):
        closeout.validate_resources(value, protected())


@pytest.mark.parametrize("kind", ["containers", "volumes", "networks", "images"])
def test_missing_resource_ownership_rejected(kind: str) -> None:
    value = resources()
    value[kind][0]["Labels"] = {}
    with pytest.raises(RuntimeError, match="ownership"):
        closeout.validate_resources(value, protected())


def test_foreign_network_and_unowned_volume_rejected() -> None:
    value = resources()
    value["networks"][0]["Containers"]["foreign"] = {}
    with pytest.raises(RuntimeError, match="Foreign network"):
        closeout.validate_resources(value, protected())
    value = resources()
    value["containers"][0]["Mounts"][0]["Name"] = "different-volume"
    with pytest.raises(RuntimeError, match="Unowned attached"):
        closeout.validate_resources(value, protected())


@pytest.mark.parametrize(
    "field,value",
    [("Running", True), ("StartedAt", "new"), ("RestartCount", 1), ("Image", "other")],
)
def test_lifecycle_changes_block_action(field: str, value: Any) -> None:
    before = resources()
    after = copy.deepcopy(before)
    after["containers"][0][field] = value
    with pytest.raises(RuntimeError, match="lifecycle"):
        closeout.same_resources(before, after)


def test_foreign_volume_and_image_users_block_cleanup() -> None:
    value = resources()
    foreign = {"Id": "foreign", "Image": "other", "Mounts": [{"Name": "owned-data"}]}
    with pytest.raises(RuntimeError, match="foreign attachment"):
        closeout.validate_attachment_users(value, [*value["containers"], foreign])
    foreign.update(Image="image", Mounts=[])
    with pytest.raises(RuntimeError, match="foreign user"):
        closeout.validate_attachment_users(value, [*value["containers"], foreign])


def test_historical_queued_model_rows_do_not_request_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            "database": "legacy",
            "states": {
                "memo_jobs": [["ready", 10], ["retry_wait", 1]],
                "research_runs": [["queued", 1]],
            },
            "blockers": [],
        }
    ]
    monkeypatch.setattr(closeout, "work_inventory", lambda *args: rows)
    assert closeout.require_quiescent(None, ["legacy"]) == rows
    rows[0]["blockers"] = [{"table": "v2_admission_tickets", "active_or_owned_rows": 1}]
    with pytest.raises(RuntimeError, match="must drain"):
        closeout.require_quiescent(None, ["legacy"])


def test_artifact_paths_cannot_escape_or_target_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "workspace"
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True)
    monkeypatch.setattr(closeout, "ROOT", root)
    monkeypatch.setattr(closeout, "ARTIFACTS", artifacts)
    assert closeout.safe_artifact(artifacts / "receipt.json") == artifacts / "receipt.json"
    for value in (artifacts, root / "outside.json", artifacts / ".." / "outside.json"):
        with pytest.raises(RuntimeError):
            closeout.safe_artifact(value)


def backup_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[dict, dict, Path]:
    monkeypatch.setattr(closeout, "ROOT", tmp_path)
    monkeypatch.setattr(closeout, "ARTIFACTS", tmp_path / "artifacts")
    folder = tmp_path / "artifacts"
    folder.mkdir()
    inventory = {"databases": ["source"], "resources": resources()}
    path = folder / "inventory.json"
    path.write_text(json.dumps(inventory))
    dump = folder / "source.dump"
    dump.write_bytes(b"verified source")
    record = {
        "schema": "phase4-completion-backup-v1",
        "owner": closeout.OWNER,
        "state": "passed",
        "backup_verification_passed": True,
        "inventory_sha256": closeout.sha(path),
        "source_databases": ["source"],
        "databases": [{"source": "source", "dump": str(dump), "dump_sha256": closeout.sha(dump)}],
        "exports": [{"container": "owned", "image": "image", "volume": "owned-data"}],
    }
    return record, inventory, path


@pytest.mark.parametrize(
    "defect", ["missing_source", "duplicate_source", "missing_export", "failed"]
)
def test_incomplete_backup_cannot_authorize_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str
) -> None:
    record, inventory, path = backup_record(tmp_path, monkeypatch)
    if defect == "missing_source":
        record["databases"] = []
    elif defect == "duplicate_source":
        record["databases"] *= 2
    elif defect == "missing_export":
        record["exports"] = []
    else:
        record["state"] = "failed"
    with pytest.raises(RuntimeError):
        closeout.validate_backup(record, inventory, path)


def test_changed_dump_stops_cleanup_before_docker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record, inventory, path = backup_record(tmp_path, monkeypatch)
    Path(record["databases"][0]["dump"]).write_bytes(b"changed")
    receipt = path.parent / "backup.json"
    receipt.write_text(json.dumps(record))
    calls = []
    monkeypatch.setattr(closeout, "docker", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(RuntimeError, match="dump changed"):
        closeout.cleanup(Path("unused"), path, receipt, path.parent)
    assert calls == []


def test_verified_backup_binds_exact_package_volume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record, inventory, path = backup_record(tmp_path, monkeypatch)
    closeout.validate_backup(record, inventory, path)
    record["exports"][0]["volume"] = "other-volume"
    with pytest.raises(RuntimeError, match="source binding"):
        closeout.validate_backup(record, inventory, path)


def test_package_export_reads_exact_volume_and_writes_only_fresh_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(closeout, "ROOT", tmp_path)
    monkeypatch.setattr(closeout, "ARTIFACTS", tmp_path / "artifacts")
    folder = tmp_path / "artifacts" / "exports"
    folder.mkdir(parents=True)
    calls = []
    monkeypatch.setattr(closeout, "volume_inventory", lambda image, volume: [])
    monkeypatch.setattr(closeout, "docker", lambda *args, **kwargs: calls.append(args))
    result = closeout.export_packages(resources(), folder)
    assert len(result) == len(calls) == 1
    command = calls[0]
    assert command[0] == "run" and "cp" not in command
    assert "type=volume,source=owned-data,target=/source,readonly" in command
    destination = folder / "marketlab-v2p4-package"
    assert f"type=bind,source={destination},target=/export" in command
    assert "--read-only" in command and "none" in command and "--rm" in command
    assert result[0]["files"] == [] and result[0]["volume"] == "owned-data"


def test_snapshot_comparison_rejects_data_and_constraint_flag_changes() -> None:
    original = {
        "tables": {"public.t": {"sha256": "first", "count": 1}},
        "constraints": [["public", "t", "check", "CHECK (x>0)", "c", True]],
    }
    after = copy.deepcopy(original)
    after["tables"]["public.t"]["sha256"] = "different"
    with pytest.raises(AssertionError, match="data/definitions"):
        exact_except_constraints(original, after)
    after = copy.deepcopy(original)
    after["constraints"][0][-1] = False
    with pytest.raises(AssertionError, match="flags"):
        exact_except_constraints(original, after)
    after = copy.deepcopy(original)
    after["constraints"][0][3] = "CHECK ((x > 0))"
    assert len(exact_except_constraints(original, after)) == 1


def test_row_digest_preserves_boundaries_and_count() -> None:
    assert row_digest(["a", "bc"])["sha256"] != row_digest(["ab", "c"])["sha256"]
    assert row_digest(["a", "bc"])["count"] == 2
