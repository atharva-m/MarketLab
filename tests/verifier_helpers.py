"""Top-level controlled workers for real spawn lifecycle tests only."""

import json
import os
import signal
import time
from pathlib import Path

from marketlab.analytics.verification import _verify_file
from marketlab.datasets.normalize import VerificationCancelled


def crash_gate_verify(payload, receiver):
    # A crash test must not depend on inherited graceful-signal state. SIGKILL
    # still kills the selected POSIX worker with SIGTERM ignored and blocked.
    # Its sibling explicitly restores normal signals so stdlib cleanup can reap
    # it even if the test launcher inherited a blocked/ignored SIGTERM.
    root, _, version, _ = payload
    control = Path(root) / "control"
    control.mkdir(exist_ok=True)
    target = control / (version + ".crash-target")
    if os.name != "nt":
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGTERM})

    def record(phase):
        (control / (version + "." + phase + "-" + str(os.getpid()))).write_text(
            json.dumps({"pid": os.getpid(), "phase": phase, "at": time.monotonic()})
        )

    def wait_phase(checkpoint, phase, seconds):
        deadline = time.monotonic() + seconds
        while not checkpoint.exists():
            if receiver.poll():
                receiver.close()
                raise VerificationCancelled("controlled crash fixture cancelled")
            if time.monotonic() >= deadline:
                record("expired-" + phase)
                receiver.close()
                raise RuntimeError("controlled crash " + phase + " checkpoint expired")
            time.sleep(0.005)

    # Startup and the active gate are different phases. A slow second spawn must
    # not spend the first worker's gate budget or turn an old entry file into
    # false evidence of two live, unfinished calls.
    record("starting")
    if (control / (version + ".delay-entry")).exists():
        wait_phase(control / (version + ".allow-entry"), "startup", 30)
    record("entered")
    wait_phase(control / "crash-arm", "readiness", 30)
    if os.name != "nt" and target.exists():
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM})
    record("armed")
    budget = control / "crash-gate-seconds"
    seconds = float(budget.read_text()) if budget.exists() else 10
    if not 0 < seconds <= 10:
        receiver.close()
        raise RuntimeError("invalid controlled crash gate budget")
    wait_phase(control / (version + ".release"), "active", seconds)
    return _verify_file(payload, receiver)


def gate_verify(payload, receiver):
    root, _, version, _ = payload
    control = Path(root) / "control"
    control.mkdir(exist_ok=True)
    (control / (version + ".entered-" + str(os.getpid()))).write_text("entered")
    deadline = time.monotonic() + 10
    while not (control / (version + ".release")).exists():
        if time.monotonic() >= deadline:
            receiver.close()
            raise RuntimeError("controlled release checkpoint expired")
        if receiver.poll():
            (control / (version + ".cancelled")).write_text("cancel observed")
            drain_deadline = time.monotonic() + 10
            while not (control / (version + ".drain")).exists():
                if time.monotonic() >= drain_deadline:
                    receiver.close()
                    raise RuntimeError("controlled drain checkpoint expired")
                time.sleep(0.005)
            receiver.close()
            raise VerificationCancelled("controlled verification cancelled")
        time.sleep(0.005)
    return _verify_file(payload, receiver)
