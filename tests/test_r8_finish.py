"""Acceptance helpers reject ownership drift and preserve independent intervals."""

import copy
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path("scripts").resolve()))
import r8_finish as finish


def evidence():
    return SimpleNamespace(data={}, flush=lambda: None)


def container(owner="owned", running=False):
    return {
        "Id": "a" * 64,
        "Name": "/owned-pg",
        "Image": "sha256:fixture",
        "Config": {"Labels": {"marketlab.r8.owner": owner}},
        "HostConfig": {
            "PortBindings": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55442"}]}
        },
        "Mounts": [],
        "State": {"Running": running},
    }


def test_dump_rejects_owner_before_any_start(tmp_path, monkeypatch):
    profile = replace(finish.resource_profile("legacy"), base=tmp_path)
    saved = container(profile.owner)
    (tmp_path / "owned-postgres.json").write_text(json.dumps(saved))
    monkeypatch.setattr(finish, "resource_profile", lambda name: profile)
    monkeypatch.setattr(finish, "inspect", lambda identity: container("unowned"))
    monkeypatch.setattr(
        finish, "docker", lambda *args: pytest.fail("Docker mutation before owner check")
    )
    with pytest.raises(RuntimeError, match="label mismatch"):
        finish.dump(evidence(), "r8-dump", legacy=True)


def test_legacy_dump_starts_and_restops_only_exact_owned_id(tmp_path, monkeypatch):
    profile = replace(finish.resource_profile("legacy"), base=tmp_path)
    saved = container(profile.owner)
    (tmp_path / "owned-postgres.json").write_text(json.dumps(saved))
    (tmp_path / "connection-private.json").write_text(
        json.dumps(
            {
                "owner": profile.owner,
                "database_url": "postgresql+psycopg://marketlab:secret@127.0.0.1:55442/marketlab",
            }
        )
    )
    monkeypatch.setattr(finish, "BASE", tmp_path)
    monkeypatch.setattr(finish, "resource_profile", lambda name: profile)
    state = copy.deepcopy(saved)
    monkeypatch.setattr(finish, "inspect", lambda identity: copy.deepcopy(state))
    operations = []

    def docker(*args):
        operations.append(args)
        state["State"]["Running"] = args[0] == "start"
        return ""

    def run(args, **kwargs):
        if "pg_dump" in args:
            kwargs["stdout"].write(b"PGDMP-exact-owned-database")
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(finish, "docker", docker)
    monkeypatch.setattr(finish, "port_free", lambda port: None)
    monkeypatch.setattr(finish.subprocess, "run", run)
    proof = evidence()
    finish.dump(proof, "r8-dump", legacy=True)
    assert operations == [("start", saved["Id"]), ("stop", "--time", "10", saved["Id"])]
    assert proof.data["dump"]["restored_owned_stopped_state"]
    assert proof.data["dump"]["sha256"] and proof.data["dump"]["bytes"] > 0
    assert "secret" not in json.dumps(proof.data)


def test_cleanup_requires_dump_and_current_endpoint_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(finish, "BASE", tmp_path)
    monkeypatch.setattr(finish, "PROFILE", replace(finish.PROFILE, base=tmp_path))
    (tmp_path / "owned-postgres.json").write_text(json.dumps({"Id": "owned"}))
    with pytest.raises(RuntimeError, match="endpoint baseline"):
        finish.cleanup(evidence(), "r8-clean")
    with pytest.raises(RuntimeError, match="verified full owned database dump"):
        finish.dump_verified(finish.PROFILE)


def test_dump_receipt_needs_success_and_matching_file_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(finish, "BASE", tmp_path)
    monkeypatch.setattr(finish, "PROFILE", replace(finish.PROFILE, base=tmp_path))
    (tmp_path / "owned-postgres.json").write_text(json.dumps({"Id": "owned"}))
    dump = tmp_path / "owned.dump"
    dump.write_bytes(b"not the recorded content")
    (tmp_path / "r8-one-finish-dump.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "dump": {
                    "scope": finish.PROFILE.name,
                    "container_id": "owned",
                    "path": str(dump),
                    "sha256": "0" * 64,
                },
            }
        )
    )
    with pytest.raises(RuntimeError, match="verified full"):
        finish.dump_verified(finish.PROFILE)


def test_original_historical_normalization_keeps_start_and_restarts():
    raw = {
        "Id": "one",
        "Name": "/service",
        "Image": "image",
        "State": {"StartedAt": "new-start", "RestartCount": 0},
    }
    raw["RestartCount"] = 2
    old = {
        "id": "one",
        "name": "/service",
        "image": "image",
        "started_at": "old-start",
        "restart_count": 0,
        "health": None,
    }
    assert finish.service_identity(raw) != finish.service_identity(old)


def test_environment_overrides_stale_dotenv_password():
    from marketlab.config import Settings

    settings = Settings(
        database_url="postgresql+psycopg://user:fresh@127.0.0.1:55444/marketlab",
        database_password=None,
    )
    assert finish.environment(settings)["MARKETLAB_DATABASE_PASSWORD"] == "fresh"


def test_cleanup_refuses_shared_volume_before_any_mutation(tmp_path, monkeypatch):
    current = replace(finish.resource_profile("adoption-20261027"), base=tmp_path / "new")
    legacy = replace(finish.resource_profile("legacy"), base=tmp_path / "old")
    monkeypatch.setattr(finish, "BASE", current.base)
    monkeypatch.setattr(finish, "PROFILE", current)
    monkeypatch.setattr(finish, "resource_profile", lambda name: legacy)
    monkeypatch.setattr(finish, "originals", lambda *args: None)
    monkeypatch.setattr(finish, "port_free", lambda *args: None)
    monkeypatch.setattr(finish, "dump_verified", lambda *args: "verified-dump")
    inventory = {}
    for index, profile in enumerate((legacy, current)):
        profile.base.mkdir()
        for offset, kind in enumerate(("postgres", "redis")):
            row = container(profile.owner)
            row["Id"] = str(index * 2 + offset + 1) * 64
            row["Name"] = "/" + profile.owner + "-" + kind
            if index == 0 and kind == "postgres":
                row["Mounts"] = [{"Type": "volume", "Name": "owned-data", "Source": "/owned/data"}]
            (profile.base / f"owned-{kind}.json").write_text(json.dumps(row))
            inventory[row["Id"]] = row
    (current.base / "current-interval-endpoints-before.json").write_text("{}")
    inventory["owned-data"] = {"Name": "owned-data", "Mountpoint": "/owned/data"}
    monkeypatch.setattr(finish, "inspect", lambda identity, *args: inventory[identity])
    monkeypatch.setattr(finish, "consumers", lambda *args: ["unowned-consumer"])
    monkeypatch.setattr(
        finish, "docker", lambda *args: pytest.fail("Mutation before shared-volume guard")
    )
    with pytest.raises(RuntimeError, match="unowned consumer"):
        finish.cleanup(evidence(), "r8-clean", apply=True)


def test_consumer_inventory_uses_full_ids(monkeypatch):
    calls = []
    monkeypatch.setattr(finish, "docker", lambda *args: calls.append(args) or "a" * 64)
    assert finish.consumers("volume", "owned-data") == ["a" * 64]
    assert "--no-trunc" in calls[0]


def test_same_profile_dump_for_replaced_container_is_rejected(tmp_path, monkeypatch):
    profile = replace(finish.PROFILE, base=tmp_path)
    monkeypatch.setattr(finish, "BASE", tmp_path)
    (tmp_path / "owned-postgres.json").write_text(json.dumps({"Id": "current-container"}))
    output = tmp_path / "database.dump"
    output.write_bytes(b"PGDMP-valid-old-dump")
    import hashlib

    (tmp_path / "r8-old-finish-dump.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "dump": {
                    "scope": profile.name,
                    "container_id": "old-container",
                    "path": str(output),
                    "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                },
            }
        )
    )
    with pytest.raises(RuntimeError, match="verified full"):
        finish.dump_verified(profile)
