"""Offline acceptance protocol guards; synthetic observations earn no live credit."""

import hashlib
import importlib.util
import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

spec = importlib.util.spec_from_file_location(
    "phase7_acceptance", Path(__file__).resolve().parents[1] / "scripts/v2_phase7_acceptance.py"
)
assert spec is not None and spec.loader is not None
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def config():
    return {
        "schema": "phase7-acceptance-v1",
        **runner.identities(),
        "namespace_sha256": "a" * 64,
        "inventory_sha256": "b" * 64,
        "backup_sha256": "c" * 64,
        "hosts": [
            {
                "host_id": str(uuid4()),
                "ssh_target": f"operator@host{i}.invalid",
                "machine_identity_sha256": str(i) * 64,
                "adapter_config_sha256": str(i + 2) * 64,
                "actual_host": True,
                "container": False,
            }
            for i in (1, 2)
        ],
        "cases": [
            {"kind": kind, "input_sha256": f"{i:064x}", "expected_sha256": "f" * 64}
            for i, kind in enumerate(
                ["research"] * 20 + ["official_ingestion", "canonical_ingestion", "copilot", "memo"]
            )
        ],
    }


def test_transport_preserves_default_argv_without_private_ssh_config(monkeypatch):
    monkeypatch.delenv("MARKETLAB_PHASE7_SSH_CONFIG", raising=False)
    monkeypatch.delenv("MARKETLAB_PHASE7_SSH_CONFIG_SHA256", raising=False)

    def command(argv, payload, timeout):
        assert argv == [
            "ssh",
            "-oBatchMode=yes",
            "-oConnectTimeout=10",
            "-oStrictHostKeyChecking=yes",
            "--",
            "operator@host.invalid",
            "marketlab-v2-phase7-adapter",
        ]
        assert payload == b'{"action":"preflight"}\n' and timeout == 5
        return b'{"status":"synthetic"}'

    monkeypatch.setattr(runner, "bounded_process", command)
    assert runner.transport(
        {"ssh_target": "operator@host.invalid"}, {"action": "preflight"}, 5
    ) == {"status": "synthetic"}


def private_config(tmp_path):
    blocks = []
    for alias in ("peer", "jump"):
        blocks.append(
            f"Host {alias}\nHostName 127.0.0.1\nPort 55207\nUser operator\n"
            f"IdentityFile {(tmp_path / 'key').as_posix()}\n"
            f"UserKnownHostsFile {(tmp_path / 'known_hosts').as_posix()}\nHostKeyAlias {alias}\n"
            "BatchMode yes\nStrictHostKeyChecking yes\nIdentitiesOnly yes\nIdentityAgent none\n"
            "GlobalKnownHostsFile none\nForwardAgent no\nUpdateHostKeys no\nRequestTTY no\n"
            "HostKeyAlgorithms ssh-ed25519\n"
        )
    return (blocks[0] + "ProxyJump jump\n" + blocks[1]).encode("ascii")


def bind_private_config(monkeypatch, path, payload):
    path.write_bytes(payload)
    monkeypatch.setenv("MARKETLAB_PHASE7_SSH_CONFIG", str(path))
    monkeypatch.setenv("MARKETLAB_PHASE7_SSH_CONFIG_SHA256", hashlib.sha256(payload).hexdigest())


def test_transport_passes_exact_private_ssh_config_and_preserves_fixed_command(
    monkeypatch, tmp_path
):
    path = tmp_path / "ssh_config"
    bind_private_config(monkeypatch, path, private_config(tmp_path).replace(b"\n", b"\r\n"))

    def command(argv, payload, timeout):
        assert argv == [
            "ssh",
            "-F",
            str(path),
            "-oBatchMode=yes",
            "-oConnectTimeout=10",
            "-oStrictHostKeyChecking=yes",
            "--",
            "peer",
            "marketlab-v2-phase7-adapter",
        ]
        assert payload == b'{"action":"preflight"}\n' and timeout == 5
        return b'{"status":"synthetic"}'

    monkeypatch.setattr(runner, "bounded_process", command)
    assert runner.transport({"ssh_target": "peer"}, {"action": "preflight"}, 5) == {
        "status": "synthetic"
    }


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (b"ProxyJump jump", b"ProxyCommand arbitrary"),
        (b"ProxyJump jump", b"Include another-file"),
        (b"ProxyJump jump", b"Match exec"),
        (b"ProxyJump jump", b"ProxyJump unknown"),
        (b"ProxyJump jump", b"ProxyJump peer"),
        (b"ForwardAgent no", b"ForwardAgent yes"),
        (b"Host peer\n", b"Host peer\v"),
        (b"HostName 127.0.0.1", b"HostName shell;command"),
    ],
)
def test_private_ssh_config_rejects_unbound_or_unsafe_routes(monkeypatch, tmp_path, old, new):
    bind_private_config(
        monkeypatch, tmp_path / "ssh_config", private_config(tmp_path).replace(old, new)
    )
    with pytest.raises(ValueError):
        runner.private_ssh_config("peer")


def test_private_ssh_config_rejects_missing_binding_changed_bytes_and_unreviewed_target(
    monkeypatch, tmp_path
):
    path = tmp_path / "ssh_config"
    bind_private_config(monkeypatch, path, private_config(tmp_path))
    with pytest.raises(ValueError, match="alias is absent"):
        runner.private_ssh_config("different")
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="changed"):
        runner.private_ssh_config("peer")
    monkeypatch.delenv("MARKETLAB_PHASE7_SSH_CONFIG_SHA256")
    with pytest.raises(ValueError, match="together"):
        runner.private_ssh_config("peer")


def observation(cfg, task):
    host = cfg["hosts"][task.get("host_index", 0)]
    other = cfg["hosts"][1 - task.get("host_index", 0)]
    return {
        "status": "observed",
        "host_id": host["host_id"],
        "jobs_started": 1,
        "model_calls_before": 0,
        "model_calls_after": 0,
        "attempts": [
            {
                "job_id": str(uuid4()),
                "worker_instance_id": str(uuid4()),
                "host_id": host["host_id"],
                "attempt_number": 1,
                "fencing_token": 1,
                "committed": True,
            }
        ],
        "result_sha256": "f" * 64,
        "readback_sha256": "f" * 64,
        "readback_host_id": other["host_id"],
        "object_version_id": "synthetic-version",
        "terminal_catalog_agree": True,
    }


def test_complete_plans_pin_twenty_independent_numerical_inputs_and_three_fault_repetitions():
    cfg = config()
    tasks = runner.plan(cfg, "functional")
    assert len(tasks) == 24
    assert [t["host_index"] for t in tasks[:20]].count(0) == 10
    faults = runner.plan(cfg, "faults")
    assert len(faults) == len(runner.BOUNDARIES) * 3
    assert all(sum(t["boundary"] == b for t in faults) == 3 for b in runner.BOUNDARIES)


@pytest.mark.parametrize(
    "change",
    [
        "same_host",
        "same_machine",
        "container",
        "duplicate_input",
        "loopback",
        "ssh_options",
        "missing_hash",
    ],
)
def test_configuration_rejects_fake_hosts_and_unfrozen_inputs(change):
    cfg = config()
    if change == "same_host":
        cfg["hosts"][1]["host_id"] = cfg["hosts"][0]["host_id"]
    elif change == "same_machine":
        cfg["hosts"][1]["machine_identity_sha256"] = cfg["hosts"][0]["machine_identity_sha256"]
    elif change == "container":
        cfg["hosts"][1]["container"] = True
    elif change == "duplicate_input":
        cfg["cases"][1]["input_sha256"] = cfg["cases"][0]["input_sha256"]
    elif change == "loopback":
        cfg["hosts"][1]["ssh_target"] = "operator@127.0.0.1"
    elif change == "ssh_options":
        cfg["hosts"][1]["ssh_target"] = "-oProxyCommand=bad"
    else:
        del cfg["backup_sha256"]
    with pytest.raises(ValueError):
        runner.validate_config(cfg)


@pytest.mark.parametrize("max_jobs,max_seconds", [(0, 1), (63, 1), (1, 0), (1, 3601), (True, 1)])
def test_bounds_rejected_before_any_folder_or_transport(tmp_path, max_jobs, max_seconds):
    output = tmp_path / "absent"
    with pytest.raises(ValueError):
        runner.run(config(), "functional", output, True, max_jobs, max_seconds)
    assert not output.exists()


def test_plan_does_not_contact_transport_or_claim_acceptance(tmp_path):
    def forbidden(*args):
        pytest.fail("offline planning contacted a host")

    result = runner.run(config(), "functional", tmp_path / "plan", False, adapter=forbidden)
    assert result["status"] == "planned" and result["acceptance"] == "incomplete"
    assert result["jobs_started"] == 0


def test_handshake_rejects_same_namespace_with_wrong_lock_and_container():
    cfg = config()
    host = cfg["hosts"][0]
    value = {
        **host,
        **{
            k: cfg[k] for k in ("source_sha256", "lock_sha256", "runner_sha256", "namespace_sha256")
        },
        "mode": "distributed",
        "schema_revision": "0013_v2_workers",
        "ready": True,
        "boot_identity": "synthetic-boot",
    }
    runner.handshake(cfg, host, value)
    with pytest.raises(ValueError):
        runner.handshake(cfg, host, {**value, "lock_sha256": "0" * 64})
    with pytest.raises(ValueError):
        runner.handshake(cfg, host, {**value, "container": True})


@pytest.mark.parametrize(
    "change",
    [
        "stale_token",
        "duplicate_commit",
        "attempt_budget",
        "wrong_readback",
        "same_host_readback",
        "missing_version",
        "calls_refunded",
        "catalog",
        "orphan_released",
    ],
)
def test_observation_rejects_recovery_publication_and_accounting_violations(change):
    cfg = config()
    task = runner.plan(cfg, "functional")[0]
    value = observation(cfg, task)
    if change in {"stale_token", "duplicate_commit"}:
        old = deepcopy(value["attempts"][0])
        old["committed"] = change == "duplicate_commit"
        value["attempts"].insert(0, old)
        value["attempts"][1]["attempt_number"] = 2
        value["attempts"][1]["fencing_token"] = 1 if change == "stale_token" else 2
    elif change == "attempt_budget":
        value["attempts"][0]["attempt_number"] = 4
    elif change == "wrong_readback":
        value["readback_sha256"] = "0" * 64
    elif change == "same_host_readback":
        value["readback_host_id"] = value["host_id"]
    elif change == "missing_version":
        del value["object_version_id"]
    elif change == "calls_refunded":
        value["model_calls_before"], value["model_calls_after"] = 1, 0
    elif change == "catalog":
        value["terminal_catalog_agree"] = False
    else:
        value.update(unknown_native_work=True, data_bytes_before=1, data_bytes_after=0)
    with pytest.raises(ValueError):
        runner.validate_observation(task, value, {h["host_id"] for h in cfg["hosts"]})


def test_waiting_does_not_spend_attempt_or_model_budget():
    cfg = config()
    task = {"action": "inference", "scenario": "zero_wait_budget"}
    value = observation(cfg, task)
    value["attempts_started_while_waiting"] = 0
    value["attempts"] = []
    value["jobs_started"] = 0
    hosts = {h["host_id"] for h in cfg["hosts"]}
    runner.validate_observation(task, value, hosts)
    for changed in ({"model_calls_after": 1}, {"attempts_started_while_waiting": 1}):
        with pytest.raises(ValueError):
            runner.validate_observation(task, {**value, **changed}, hosts)


def test_failure_retains_evidence_without_retry_or_secret_exception(tmp_path):
    cfg = config()
    requests = []

    def broken(host, packet, timeout):
        requests.append(packet)
        raise RuntimeError("private adapter error sentinel")

    folder = tmp_path / "failure"
    with pytest.raises(RuntimeError):
        runner.run(cfg, "functional", folder, True, adapter=broken)
    assert len(requests) == 1
    result = json.loads((folder / "result.json").read_bytes())
    assert result["status"] == "incomplete" and result["failure_class"] == "RuntimeError"
    assert result["acceptance"] == "incomplete"
    assert result["remote_work_status"] == "unknown_requires_owning_host_reconciliation"
    assert "private adapter error sentinel" not in (folder / "result.json").read_text()
    assert (folder / "000-request.json").is_file()


def test_output_folder_is_never_reused(tmp_path):
    with pytest.raises(FileExistsError):
        runner.run(config(), "functional", tmp_path, False)


def test_config_rejects_unrelated_secret_fields_before_retaining_plan(tmp_path):
    cfg = config()
    cfg["database_url"] = "private sentinel"
    with pytest.raises(ValueError):
        runner.run(cfg, "functional", tmp_path / "absent", False)
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize(("now", "remaining", "drained"), [(44.0, 16.0, True), (61.0, 0.0, False)])
def test_compatibility_worker_drain_respects_original_visibility_deadline(
    monkeypatch, now, remaining, drained
):
    class DelayedWorker:
        stopped = False
        wait_seconds = None

        def join(self, timeout):
            self.wait_seconds = timeout
            self.stopped = timeout >= 15

    monkeypatch.setattr(runner.time, "monotonic", lambda: now)
    worker = DelayedWorker()
    runner.wait_visibility_worker(worker, started=0.0, seconds=60.0)
    assert worker.wait_seconds == remaining
    assert worker.stopped is drained


@pytest.mark.parametrize(
    ("phase", "retained"),
    [
        ("compatibility_worker_deadline", "compatibility_worker_deadline"),
        ("unreviewed-secret", None),
    ],
)
def test_adapter_failure_reports_only_allowlisted_visibility_phase(
    monkeypatch, capsys, phase, retained
):
    from io import BytesIO
    from types import SimpleNamespace

    def unavailable(*_):
        raise runner.VisibilityProbeError(phase)

    monkeypatch.setattr(runner, "remote_request", unavailable)
    monkeypatch.setattr(runner, "read_json", lambda _: {})
    monkeypatch.setattr(sys, "argv", ["adapter", "--adapter-config", "unused.json"])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=BytesIO(b"{}")))
    assert runner.main() == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    receipt = json.loads(captured.out)
    assert receipt["status"] == receipt["acceptance"] == "incomplete"
    assert receipt.get("phase") == retained


def test_visibility_validator_requires_bounded_actual_pages_and_zero_jobs():
    cfg = config()
    task = {"action": "visibility", "scenario": "operator_pagination"}
    value = {
        "status": "visibility_observed",
        "jobs_started": 0,
        "host_id": cfg["hosts"][0]["host_id"],
        "pages": [{"items": [], "next_cursor": None}],
    }
    hosts = {h["host_id"] for h in cfg["hosts"]}
    runner.validate_observation(task, value, hosts)
    for changed in (
        {"jobs_started": 1},
        {"pages": []},
        {"pages": [{"items": [], "next_cursor": "unread"}]},
    ):
        with pytest.raises(ValueError):
            runner.validate_observation(task, {**value, **changed}, hosts)


@pytest.mark.skipif(os.name != "nt", reason="Windows Job containment check")
def test_real_windows_cli_is_contained_and_output_overflow_terminates_owned_job():
    command = [sys.executable, "-I", "-S", "-c", "print('{}')"]
    assert runner.windows_cli(command, 10).strip() == b"{}"
    command[-1] = "import sys; sys.stdout.write('x'*1000000); sys.stdout.flush()"
    with pytest.raises((TimeoutError, ValueError)):
        runner.windows_cli(command, 10)


def test_failed_peer_readback_keeps_already_started_work_count(tmp_path):
    cfg = config()

    def adapter(host, packet, timeout):
        if packet["action"] == "preflight":
            return {
                **host,
                **runner.identities(),
                "request_id": packet["request_id"],
                "namespace_sha256": cfg["namespace_sha256"],
                "mode": "distributed",
                "schema_revision": "0013_v2_workers",
                "ready": True,
                "boot_identity": "synthetic",
            }
        if packet["action"] == "submit_work":
            return {**observation(cfg, packet), "request_id": packet["request_id"]}
        raise TimeoutError("synthetic peer readback failed")

    folder = tmp_path / "peer-failure"
    with pytest.raises(TimeoutError):
        runner.run(cfg, "functional", folder, True, adapter=adapter)
    retained = json.loads((folder / "result.json").read_bytes())
    assert retained["jobs_started"] == 1
    assert retained["scenarios_observed"] == 0
    assert retained["acceptance"] == "incomplete"


def test_explicit_batched_subset_retains_full_plan_and_earns_no_full_gate_credit(tmp_path):
    cfg = config()
    result = runner.run(cfg, "faults", tmp_path / "batch", False, start_index=31, count=8)
    packet = json.loads((tmp_path / "batch/frozen-plan.json").read_bytes())
    assert len(packet["full_plan"]) == 39 and len(packet["selected_tasks"]) == 8
    assert result["start_index"] == 31 and result["scenario_count"] == 8
    assert result["acceptance"] == "incomplete" and result["jobs_started"] == 0


@pytest.mark.parametrize("start,count", [(-1, 1), (39, 1), (0, 0), (0, 63), (38, 2), (True, 1)])
def test_invalid_explicit_batch_rejected_before_retaining_or_dispatching(tmp_path, start, count):
    with pytest.raises(ValueError):
        runner.run(config(), "faults", tmp_path / "absent", True, start_index=start, count=count)
    assert not (tmp_path / "absent").exists()


def test_frozen_host_config_rejects_changed_bindings_and_unlisted_peer_before_dispatch():
    import hashlib

    cfg = config()
    remote = {
        "schema": "phase7-host-adapter-v1",
        "host_id": cfg["hosts"][0]["host_id"],
        "root_id": str(uuid4()),
        "fault_bindings": {
            "after_claim:0": {
                "peer": {
                    "host_id": cfg["hosts"][1]["host_id"],
                    "ssh_target": cfg["hosts"][1]["ssh_target"],
                }
            }
        },
    }
    cfg["hosts"][0]["adapter_config_sha256"] = hashlib.sha256(runner.canonical(remote)).hexdigest()
    packet = {"allowed_hosts": cfg["hosts"]}
    runner.validate_host_scope(remote, packet)
    changed = deepcopy(remote)
    changed["root_id"] = str(uuid4())
    with pytest.raises(ValueError):
        runner.validate_host_scope(changed, packet)
    changed = deepcopy(remote)
    changed["fault_bindings"]["after_claim:0"]["peer"]["host_id"] = str(uuid4())
    cfg["hosts"][0]["adapter_config_sha256"] = hashlib.sha256(runner.canonical(changed)).hexdigest()
    with pytest.raises(ValueError):
        runner.validate_host_scope(changed, packet)


def test_full_fault_plan_rejects_78_possible_dispatches_before_any_contact(tmp_path):
    def forbidden(*args):
        pytest.fail("An over-budget plan contacted a host")

    with pytest.raises(ValueError):
        runner.run(config(), "faults", tmp_path / "absent", True, adapter=forbidden)
    assert not (tmp_path / "absent").exists()


def test_zero_wait_peer_dispatch_is_charged_separately_from_zero_actual_attempts(tmp_path):
    cfg = config()

    def adapter(host, packet, timeout):
        if packet["action"] == "preflight":
            return {
                **host,
                **runner.identities(),
                "request_id": packet["request_id"],
                "namespace_sha256": cfg["namespace_sha256"],
                "mode": "distributed",
                "schema_revision": "0013_v2_workers",
                "ready": True,
                "boot_identity": "synthetic",
            }
        return {
            "request_id": packet["request_id"],
            "host_id": host["host_id"],
            "status": "observed",
            "jobs_started": 0,
            "dispatches_started": 1,
            "model_calls_before": 0,
            "model_calls_after": 0,
            "attempts": [],
            "attempts_started_while_waiting": 0,
        }

    result = runner.run(
        cfg,
        "inference",
        tmp_path / "waiting",
        True,
        max_jobs=1,
        adapter=adapter,
        start_index=2,
        count=1,
    )
    assert result["jobs_started"] == 0 and result["dispatches_started"] == 1
    assert result["scenarios_observed"] == 1 and result["acceptance"] == "incomplete"


def synthetic_batch(cfg, folder, start, count, job_id=None):
    # The real runner writes complete paired transcripts. Only the transport is
    # synthetic: these unit fixtures dispatch no host, model or worker and earn
    # no live acceptance credit. Summary flags are never fabricated independently.
    def adapter(host, packet, timeout):
        if packet["action"] == "preflight":
            return {
                **host,
                **runner.identities(),
                "request_id": packet["request_id"],
                "namespace_sha256": cfg["namespace_sha256"],
                "mode": "distributed",
                "schema_revision": "0013_v2_workers",
                "ready": True,
                "boot_identity": "synthetic",
            }
        value = observation(cfg, packet)
        if job_id is not None:
            value["attempts"][0]["job_id"] = job_id
        return {
            **value,
            "request_id": packet["request_id"],
            "dispatches_started": 2,
            "fault_boundary": {"boundary": packet["boundary"]},
        }

    runner.run(cfg, "faults", folder, True, adapter=adapter, start_index=start, count=count)
    return folder


def test_batch_combiner_requires_all_disjoint_indices_without_claiming_acceptance(tmp_path):
    cfg = config()
    first = synthetic_batch(cfg, tmp_path / "first-synthetic", 0, 31)
    second = synthetic_batch(cfg, tmp_path / "second-synthetic", 31, 8)
    partial = runner.combine(cfg, "faults", [first], tmp_path / "partial-coverage")
    assert partial["status"] == "coverage_incomplete" and partial["missing_indices"] == list(
        range(31, 39)
    )
    complete = runner.combine(cfg, "faults", [first, second], tmp_path / "complete-coverage")
    assert complete["covered_indices"] == list(range(39)) and complete["missing_indices"] == []
    assert complete["status"] == "coverage_validated" and complete["acceptance"] == "incomplete"


@pytest.mark.parametrize("defect", ["overlap", "source", "failed"])
def test_batch_combiner_rejects_overlaps_mixed_source_and_failed_batches(tmp_path, defect):
    cfg = config()
    first = synthetic_batch(cfg, tmp_path / "first-synthetic", 0, 31)
    second = synthetic_batch(
        cfg, tmp_path / "second-synthetic", 30 if defect == "overlap" else 31, 8
    )
    result = json.loads((second / "result.json").read_bytes())
    if defect == "source":
        result["source"]["source_sha256"] = "0" * 64
    elif defect == "failed":
        result["status"] = "incomplete"
    (second / "result.json").write_bytes(runner.canonical(result))
    with pytest.raises(ValueError):
        runner.combine(cfg, "faults", [first, second], tmp_path / "absent")
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize(
    "defect",
    [
        "missing",
        "truncated",
        "request_id",
        "boundary",
        "repetition",
        "observed_boundary",
        "attempt_budget",
        "dispatch_budget",
        "refund",
        "extra",
    ],
)
def test_combiner_revalidates_every_expected_pair_instead_of_summary_flags(tmp_path, defect):
    cfg = config()
    folder = synthetic_batch(cfg, tmp_path / "synthetic", 0, 1)
    request_path, response_path = folder / "002-request.json", folder / "002-response.json"
    original = response_path.read_bytes()
    (folder / "original-response.retained").write_bytes(original)
    request = json.loads(request_path.read_bytes())
    response = json.loads(original)
    if defect == "missing":
        response_path.rename(folder / "missing-response.retained")
    elif defect == "truncated":
        response_path.write_bytes(b"{")
    elif defect in {"boundary", "repetition"}:
        request[defect] = "stale_success" if defect == "boundary" else 2
        request_path.write_bytes(runner.canonical(request))
    elif defect == "extra":
        (folder / "099-response.json").write_bytes(original)
    else:
        if defect == "request_id":
            response["request_id"] = str(uuid4())
        elif defect == "observed_boundary":
            response["fault_boundary"]["boundary"] = "stale_success"
        elif defect == "attempt_budget":
            response["attempts"][0]["attempt_number"] = 4
        elif defect == "dispatch_budget":
            response["dispatches_started"] = 3
        else:
            response["model_calls_before"], response["model_calls_after"] = 1, 0
        response_path.write_bytes(runner.canonical(response))
    with pytest.raises((ValueError, FileNotFoundError)):
        runner.combine(cfg, "faults", [folder], tmp_path / "absent")
    assert not (tmp_path / "absent").exists()


def test_combiner_rejects_job_reuse_across_disjoint_batches(tmp_path):
    cfg = config()
    reused = str(uuid4())
    first = synthetic_batch(cfg, tmp_path / "first-synthetic", 0, 1, reused)
    second = synthetic_batch(cfg, tmp_path / "second-synthetic", 1, 1, reused)
    with pytest.raises(ValueError):
        runner.combine(cfg, "faults", [first, second], tmp_path / "absent")
    assert not (tmp_path / "absent").exists()


def test_transcript_rejects_impossible_planned_budget_before_reading_any_receipt(tmp_path):
    cfg = config()
    tasks = runner.plan(cfg, "faults")
    summary = {"max_jobs": 62, "max_seconds": 3600, "dispatches_planned": 78}
    with pytest.raises(ValueError, match="invocation bounds"):
        runner.validate_transcript(cfg, "faults", tasks, tmp_path, summary, set(), set())


@pytest.mark.parametrize("defect", ["missing_readback", "wrong_readback", "summary_count"])
def test_functional_combiner_requires_paired_peer_bytes_and_recomputed_counters(tmp_path, defect):
    cfg = config()

    def adapter(host, packet, timeout):
        if packet["action"] == "preflight":
            return {
                **host,
                **runner.identities(),
                "request_id": packet["request_id"],
                "namespace_sha256": cfg["namespace_sha256"],
                "mode": "distributed",
                "schema_revision": "0013_v2_workers",
                "ready": True,
                "boot_identity": "synthetic",
            }
        if packet["action"] == "readback":
            return {
                "request_id": packet["request_id"],
                "host_id": host["host_id"],
                "result_sha256": "f" * 64,
            }
        return {
            **observation(cfg, packet),
            "request_id": packet["request_id"],
            "dispatches_started": 1,
        }

    folder = tmp_path / "synthetic-functional"
    runner.run(cfg, "functional", folder, True, adapter=adapter, count=1)
    peer = folder / "003-response.json"
    if defect == "missing_readback":
        peer.rename(folder / "peer-response.retained")
    elif defect == "wrong_readback":
        value = json.loads(peer.read_bytes())
        value["result_sha256"] = "0" * 64
        peer.write_bytes(runner.canonical(value))
    else:
        value = json.loads((folder / "result.json").read_bytes())
        value["jobs_started"] = 2
        (folder / "result.json").write_bytes(runner.canonical(value))
    with pytest.raises(ValueError):
        runner.combine(cfg, "functional", [folder], tmp_path / "absent")
    assert not (tmp_path / "absent").exists()
