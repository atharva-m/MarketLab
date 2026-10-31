"""Exact public-child identity and conservative unresolved-launch semantics."""

import os
import subprocess

import pytest

from marketlab.datasets.v2 import native_children, native_identity
from marketlab.datasets.v2.common import V2Error


def test_independently_queried_owned_native_child_birth():
    process = subprocess.Popen(
        [native_identity.current()["executable"], "-c", "import time; time.sleep(15)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        identity = native_identity.child(process.pid)
        assert identity["pid"] == process.pid
        assert native_identity.alive(identity)
        assert not native_identity.dead(identity)
    finally:
        process.terminate()
        process.wait(timeout=10)
    assert native_identity.dead(identity)


def test_native_child_lookup_rejects_parent_as_child():
    with pytest.raises(V2Error):
        native_identity.child(native_identity.current()["pid"])


def test_pending_spawn_never_proves_childless_death(monkeypatch):
    identity = native_identity.current()
    value = {
        "schema": "native-ticket-v1",
        "process": identity,
        "children_pending": True,
        "children": [],
    }
    monkeypatch.setattr(native_identity, "dead", lambda item: True)
    assert native_children.pending(value)
    assert not native_children.dead(value)


def test_dead_parent_with_live_known_child_retains_slot(monkeypatch):
    identity = native_identity.current()
    child = dict(identity, pid=identity["pid"] + 1)
    value = {
        "schema": "native-ticket-v1",
        "process": identity,
        "children_pending": False,
        "children": [child],
    }
    monkeypatch.setattr(native_identity, "dead", lambda item: item["pid"] == identity["pid"])
    assert not native_children.dead(value)
    monkeypatch.setattr(native_identity, "dead", lambda item: True)
    assert native_children.dead(value)


def test_same_host_new_boot_can_reconcile_unresolved_launch(monkeypatch):
    value = {
        "schema": "native-ticket-v1",
        "process": native_identity.current(),
        "children_pending": True,
        "children": [],
    }
    monkeypatch.setattr(native_identity, "rebooted", lambda identity: True)
    assert native_children.dead(value)


@pytest.mark.parametrize(
    "change",
    [
        {"schema": "unknown"},
        {"children_pending": 1},
        {"children": [{}]},
        {"children": [dict()] * 9},
        {"unknown": True},
    ],
)
def test_malformed_child_envelope_cannot_release_admission(change):
    value = {
        "schema": "native-ticket-v1",
        "process": native_identity.current(),
        "children_pending": False,
        "children": [],
    } | change
    assert native_children.envelope(value) is None
    assert not native_children.dead(value)


def linux_stat(pid, parent=0, birth=73):
    fields = ["S", str(parent)] + ["0"] * 17 + [str(birth)]
    return f"{pid} (python) " + " ".join(fields)


@pytest.fixture
def linux_proc(monkeypatch):
    files = {
        "/proc/sys/kernel/random/boot_id": "12345678-1234-4321-8765-123456789abc",
        "/proc/self/stat": linux_stat(os.getpid(), 1, 88),
        "/proc/1/stat": linux_stat(1),
        "/etc/machine-id": None,
    }
    links = {"/proc/self/ns/pid": "pid:[4026532401]", "/proc/1/ns/pid": "pid:[4026532401]"}

    def reading(path):
        if files[path] is None:
            raise FileNotFoundError(path)
        return files[path]

    monkeypatch.setattr(native_identity, "_linux_text", reading)
    monkeypatch.setattr(os, "readlink", lambda path: links[path])
    return files, links


def test_linux_missing_machine_id_uses_validated_native_namespace_domain(linux_proc):
    host, boot = native_identity._linux_host_boot()
    assert len(host) == 32 and boot == linux_proc[0]["/proc/sys/kernel/random/boot_id"]
    assert native_identity._linux_host_boot() == (host, boot)


@pytest.mark.parametrize("change", ["namespace", "init-birth", "boot", "machine-id"])
def test_linux_domain_never_aliases_another_namespace_or_boot(linux_proc, change):
    files, links = linux_proc
    before = native_identity._linux_host_boot()[0]
    if change == "namespace":
        links["/proc/self/ns/pid"] = links["/proc/1/ns/pid"] = "pid:[4026532402]"
    elif change == "init-birth":
        files["/proc/1/stat"] = linux_stat(1, birth=74)
    elif change == "boot":
        files["/proc/sys/kernel/random/boot_id"] = "22345678-1234-4321-8765-123456789abc"
    else:
        files["/etc/machine-id"] = "a" * 32
    assert native_identity._linux_host_boot()[0] != before


@pytest.mark.parametrize(
    "path,value",
    [
        ("/proc/sys/kernel/random/boot_id", "malformed"),
        ("/proc/sys/kernel/random/boot_id", "00000000-0000-0000-0000-000000000000"),
        ("/proc/sys/kernel/random/boot_id", None),
        ("/proc/self/stat", linux_stat(999999999)),
        ("/proc/1/stat", linux_stat(1, birth=0)),
        ("/proc/1/stat", "malformed"),
    ],
)
def test_linux_required_native_proc_evidence_fails_closed(linux_proc, path, value):
    linux_proc[0][path] = value
    with pytest.raises(OSError):
        native_identity._linux_host_boot()


@pytest.mark.parametrize("value", ["pid:[0]", "malformed", "pid:[4026532402]"])
def test_linux_foreign_or_malformed_proc_namespace_is_rejected(linux_proc, value):
    linux_proc[1]["/proc/1/ns/pid"] = value
    with pytest.raises(OSError):
        native_identity._linux_host_boot()


def test_linux_foreign_domain_never_queries_local_reused_pid(monkeypatch):
    identity = dict(native_identity.current(), platform="Linux", host="a" * 32)
    monkeypatch.setattr(native_identity.platform, "system", lambda: "Linux")
    monkeypatch.setattr(native_identity, "_host_boot", lambda: ("b" * 32, identity["boot"]))

    def forbidden(pid):
        raise AssertionError("Foreign namespace must not query a local PID")

    monkeypatch.setattr(native_identity, "_process", forbidden)
    assert not native_identity.dead(identity)
    assert not native_identity.rebooted(identity)


def test_linux_same_domain_pid_reuse_is_checked_by_birth(monkeypatch):
    identity = dict(native_identity.current(), platform="Linux", host="a" * 32)
    monkeypatch.setattr(native_identity.platform, "system", lambda: "Linux")
    monkeypatch.setattr(native_identity, "_host_boot", lambda: (identity["host"], identity["boot"]))
    monkeypatch.setattr(
        native_identity,
        "_process",
        lambda pid: {
            "birth": str(int(identity["birth"]) + 1),
            "executable": identity["executable"],
        },
    )
    assert native_identity.dead(identity)
