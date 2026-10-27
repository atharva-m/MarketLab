"""Harness ownership adaptation preserves historical files and strict guards."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path("scripts").resolve()))
import r8_recovery as recovery


def test_operational_adapter_changes_only_known_owner_literals_and_bindings():
    historical = Path("scripts/r6_operational.py")
    original = historical.read_bytes()
    adapter = recovery.operational_adapter()
    assert historical.read_bytes() == original
    assert adapter.BASE == recovery.BASE
    assert adapter.owned_settings is recovery.owned_settings
    assert adapter.adapter_provenance["identity_substitutions"] == {
        "marketlab.r6.owner": "marketlab.r8.owner",
        "r6-20261025": recovery.OWNER,
    }
    assert (
        adapter.adapter_provenance["original_sha256"]
        != adapter.adapter_provenance["adapted_sha256"]
    )


def test_unrecognized_historical_adapter_is_rejected():
    with pytest.raises(ValueError, match="Unsupported"):
        recovery.durability_adapter("arbitrary_module")


def test_changed_historical_owner_sites_cannot_silently_bypass_guard(monkeypatch):
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs: "# changed harness")
    with pytest.raises(RuntimeError, match="identity sites changed"):
        recovery.operational_adapter()


def test_native_timeout_phase_is_exposed_by_cli_parser(monkeypatch):
    called = []

    async def observed(prefix, phase):
        called.append((prefix, phase))

    monkeypatch.setattr(recovery, "run", observed)
    monkeypatch.setattr(
        sys, "argv", ["r8_recovery.py", "native-timeout-cli", "--prefix", "r8-parser-test"]
    )
    recovery.main()
    assert called == [("r8-parser-test", "native-timeout-cli")]


def test_timeout_endpoint_cannot_forward_to_original_or_external_model():
    with pytest.raises(ValueError, match="owned Ollama"):
        recovery.TimeoutEndpoint("http://127.0.0.1:11434")
