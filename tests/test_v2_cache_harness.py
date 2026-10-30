"""Redis callback type normalization and bounded value-free failure evidence."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def harness(monkeypatch):
    project = Path(__file__).resolve().parents[1]

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    acceptance = load("phase3_cache_test_acceptance", project / "scripts/v2_phase3_acceptance.py")
    monkeypatch.setitem(sys.modules, "v2_phase3_acceptance", acceptance)
    return load("phase3_cache_harness_test", project / "scripts/v2_phase3_cache.py")


@pytest.mark.parametrize("mode", ["str", "bytes", "mixed"])
def test_configuration_callback_accepts_exact_text_and_bytes_without_coercion(harness, mode):
    expected = harness.EXPECTED_CONFIGURATION
    raw = {}
    for index, (key, value) in enumerate(expected.items()):
        raw[key.encode() if mode == "bytes" or (mode == "mixed" and index % 2) else key] = (
            value.encode() if mode == "bytes" or (mode == "mixed" and index % 2 == 0) else value
        )
    assert harness.configuration_text(raw) == expected


@pytest.mark.parametrize(
    "failure", ["duplicate", "null", "integer", "invalid_utf8", "missing", "unknown"]
)
def test_configuration_callback_rejects_ambiguous_or_wrong_typed_response(harness, failure):
    raw = dict(harness.EXPECTED_CONFIGURATION)
    if failure == "duplicate":
        raw[b"save"] = b""
    elif failure == "null":
        raw["save"] = None
    elif failure == "integer":
        raw["maxmemory"] = 268435456
    elif failure == "invalid_utf8":
        raw["save"] = b"\xff"
    elif failure == "missing":
        raw.pop("save")
    else:
        raw["unexpected"] = b"private"
    with pytest.raises(ValueError):
        harness.configuration_text(raw)


def test_diagnostic_retains_locations_and_types_without_message_values_or_locals(harness):
    secret = "DO-NOT-RECORD-PRIVATE-VALUE"

    def failed():
        private_local = {"credential": secret}
        try:
            raise ValueError(private_local)
        except ValueError as error:
            raise RuntimeError(secret) from error

    try:
        failed()
    except RuntimeError as error:
        record = harness.diagnostic(error)
    assert [r["error_type"] for r in record] == ["RuntimeError", "ValueError"]
    assert all(
        set(frame) == {"filename", "line", "function"} for r in record for frame in r["frames"]
    )
    assert any(frame["function"] == "failed" for r in record for frame in r["frames"])
    encoded = json.dumps(record)
    assert secret not in encoded and "credential" not in encoded and "private_local" not in encoded
    assert all(len(r["frames"]) <= 32 for r in record)


def controlled_docker(harness, monkeypatch, action, stdout, fault=None, returncode=0):
    expected = {
        "Id": "a" * 64,
        "Name": "/marketlab-v2p3-redis-r3",
        "Image": "sha256:" + "b" * 64,
        "Mounts": [],
        "Labels": {"marketlab.v2phase3.owner": harness.OWNER},
        "Ports": {"6379/tcp": [{"HostIp": "127.0.0.1", "HostPort": "56392"}]},
    }
    observed = {
        "Id": expected["Id"],
        "Name": expected["Name"],
        "Image": expected["Image"],
        "Mounts": [],
        "Config": {"Labels": dict(expected["Labels"])},
        "HostConfig": {"PortBindings": expected["Ports"]},
        "NetworkSettings": {"Ports": expected["Ports"] if action == "stop" else {}},
        "State": {"Running": action == "stop", "StartedAt": "owned-start"},
    }
    calls = []

    def docker(*arguments):
        assert arguments == ("inspect", expected["Id"])
        calls.append("inspect")
        return json.dumps([observed])

    def run(arguments, **kwargs):
        assert arguments[0:2] == ["docker", action] and arguments[-1] == expected["Id"]
        calls.append(action)
        observed["State"]["Running"] = action == "start"
        observed["NetworkSettings"]["Ports"] = expected["Ports"] if action == "start" else {}
        if fault == "identity":
            observed["Id"] = "c" * 64
        elif fault == "state":
            observed["State"]["Running"] = action != "start"
        elif fault == "labels":
            observed["Config"]["Labels"] = {}
        elif fault == "mounts":
            observed["Mounts"] = [{"foreign": True}]
        elif fault == "ports":
            observed["HostConfig"]["PortBindings"] = {}
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")

    monkeypatch.setattr(harness, "docker", docker)
    monkeypatch.setattr(harness.subprocess, "run", run)
    return expected, calls


@pytest.mark.parametrize("action", ["stop", "start"])
@pytest.mark.parametrize(
    "stdout", ["a" * 12 + "\n", "/marketlab-v2p3-redis-r3\r\n", "controlled CLI information\n"]
)
def test_transition_uses_returncode_and_native_identity_state_not_stdout(
    harness, tmp_path, monkeypatch, action, stdout
):
    expected, calls = controlled_docker(harness, monkeypatch, action, stdout)
    observed = harness.transition(action, expected, tmp_path)
    assert observed["Id"] == expected["Id"] and observed["State"]["Running"] is (action == "start")
    assert calls == ["inspect", action, "inspect"]
    receipt = json.loads(next(tmp_path.glob("docker-*.json")).read_bytes())
    assert receipt["stdout"] == stdout and receipt["exact_identity_and_state_verified"]


@pytest.mark.parametrize("fault", ["identity", "state", "labels", "mounts", "ports"])
def test_transition_still_rejects_wrong_owned_identity_and_running_state(
    harness, tmp_path, monkeypatch, fault
):
    expected, _ = controlled_docker(harness, monkeypatch, "stop", "a" * 64, fault=fault)
    with pytest.raises(AssertionError):
        harness.transition("stop", expected, tmp_path)
    receipt = json.loads(next(tmp_path.glob("docker-*.json")).read_bytes())
    assert (
        "inspection_error_stack" in receipt and "exact_identity_and_state_verified" not in receipt
    )


def test_transition_nonzero_exit_and_bounded_stdout_are_retained(harness, tmp_path, monkeypatch):
    expected, calls = controlled_docker(harness, monkeypatch, "stop", "x" * 5000, returncode=1)
    with pytest.raises(RuntimeError, match="CLI transition failed"):
        harness.transition("stop", expected, tmp_path)
    receipt = json.loads(next(tmp_path.glob("docker-*.json")).read_bytes())
    assert len(receipt["stdout"]) == 4096 and receipt["stdout_truncated"]
    assert receipt["stdout_characters"] == 5000 and receipt["returncode"] == 1
    assert calls == ["inspect", "stop"]
