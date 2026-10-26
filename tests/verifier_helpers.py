"""Top-level controlled workers for real spawn lifecycle tests only."""

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
    target = Path(root) / "control" / (version + ".crash-target")
    if os.name != "nt":
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGTERM})
        if target.exists():
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM})
    return gate_verify(payload, receiver)


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
