"""Owned controller used only by the verifier parent-death process test."""

import json
import os
import sys
import threading
import time
from pathlib import Path

import marketlab.analytics.verification as verification


def held_worker(payload, receiver):
    """Control active/idle state while retaining the production worker initializer."""
    root, _, version, _ = payload
    try:
        entered = Path(root) / (version + ".entered.json")
        temporary = entered.with_suffix(".tmp")
        temporary.write_text(json.dumps({"pid": os.getpid(), "version": version}), encoding="utf-8")
        temporary.replace(entered)
        deadline = time.monotonic() + 40
        while not (Path(root) / "release-workers").exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("Owned test worker fail-safe expired")
            time.sleep(0.02)
        return {"manifest": {"version": version}, "record": {"pid": os.getpid()}}
    finally:
        receiver.close()


def main():
    root = Path(sys.argv[1])
    mode = sys.argv[2]
    identity = {"controller_pid": os.getpid(), "launcher_parent_pid": os.getppid()}
    identity_path = root / "controller.json"
    identity_temporary = identity_path.with_suffix(".tmp")
    identity_temporary.write_text(json.dumps(identity), encoding="utf-8")
    identity_temporary.replace(identity_path)
    verification._verify_file = held_worker
    pool = verification.VerificationPool(verification.ComputeBudget())
    requests = [
        verification.VerificationRequest(str(root), "unused", value * 64, "c" * 64, (), ())
        for value in ("a", "b")
    ]
    failures = []

    def run():
        try:
            pool.verify_many(requests, threading.Event())
        except BaseException as error:
            failures.append(repr(error))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        began = time.monotonic()
        while True:
            snapshot = pool.snapshot()
            entered_paths = [root / (value * 64 + ".entered.json") for value in ("a", "b")]
            entered = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in entered_paths
                if path.exists()
            ]
            if (
                len(snapshot["worker_pids"]) == 2
                and snapshot["active_submitted"] == 2
                and {record["pid"] for record in entered} == set(snapshot["worker_pids"])
            ):
                break
            if failures or time.monotonic() - began > 15:
                raise RuntimeError("Owned workers did not become active: " + repr(failures))
            time.sleep(0.02)
        if mode == "idle":
            (root / "release-workers").write_text("release", encoding="utf-8")
            thread.join(timeout=10)
            assert not thread.is_alive() and not failures
            snapshot = pool.snapshot()
            assert snapshot["active_submitted"] == 0 and snapshot["completed"] == 2
        else:
            assert mode == "active" and thread.is_alive()
        ready = root / "ready.json"
        temporary = ready.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({**identity, "mode": mode, "entered": entered, "snapshot": snapshot}),
            encoding="utf-8",
        )
        temporary.replace(ready)
        # Normal tests abruptly terminate this controller before cleanup. A
        # bounded fail-safe also releases/reaps work if its owning test fails.
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            time.sleep(0.1)
    finally:
        (root / "release-workers").write_text("release", encoding="utf-8")
        pool.close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
