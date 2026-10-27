"""Fixed acceptance profiles never select arbitrary endpoints or evidence roots."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path("scripts").resolve()))
import r8_common as common


def test_fixed_adoption_profile_and_unknown_selection():
    profile = common.resource_profile("adoption-20261027")
    assert profile.base == Path("artifacts/r8-adoption-20261027")
    assert profile.owner == "r8-adoption-20261027"
    assert (profile.postgres_port, profile.redis_port, profile.ollama_port) == (55444, 56386, 11443)
    assert profile.ollama_url == "http://127.0.0.1:11443"
    with pytest.raises(ValueError, match="Unknown fixed"):
        common.resource_profile("../../original")


def test_profile_rejects_other_base_before_read_or_docker(tmp_path):
    with pytest.raises(RuntimeError, match="evidence base"):
        common.owned_settings(tmp_path)


def test_owner_must_be_exact_owner_label(tmp_path, monkeypatch):
    profile = common.ResourceProfile("fixture", tmp_path, "owned", 55444, 56386, 11443)
    monkeypatch.setattr(common, "PROFILE", profile)
    monkeypatch.setattr(common, "OWNER", profile.owner)
    private = {
        "owner": "owned",
        "database_url": "postgresql+psycopg://user@127.0.0.1:55444/marketlab",
        "redis_url": "redis://127.0.0.1:56386/0",
        "ollama_url": profile.ollama_url,
    }
    (tmp_path / "connection-private.json").write_text(json.dumps(private))
    saved = {"Id": "fixture", "Name": "/owned", "Image": "sha256:fixture"}
    actual = {
        **saved,
        "State": {"Running": True},
        "Config": {"Labels": {"unrelated.label": "owned"}},
        "NetworkSettings": {"Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55444"}]}},
    }
    monkeypatch.setattr(common, "recorded", lambda *args: saved)
    monkeypatch.setattr(common, "command", lambda *args: json.dumps([actual]))
    with pytest.raises(RuntimeError, match="ownership mismatch"):
        common.owned_settings(tmp_path)
