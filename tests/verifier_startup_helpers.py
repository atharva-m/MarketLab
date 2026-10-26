"""Spawn-safe controlled readiness tasks; production initializer stays unchanged."""

import json
import os
import threading
import time
from pathlib import Path

import marketlab.analytics.verification as module


def mark_entered(root):
    path = Path(root) / ("ready-entered-" + str(os.getpid()) + ".json")
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
    temporary.replace(path)


def gated_ready(root):
    mark_entered(root)
    deadline = time.monotonic() + 8
    while not (Path(root) / "release-readiness").exists():
        if module._STARTUP_BARRIER.broken:
            raise threading.BrokenBarrierError("controlled readiness aborted")
        if time.monotonic() >= deadline:
            raise RuntimeError("controlled readiness release expired")
        time.sleep(0.01)
    module._STARTUP_BARRIER.wait(timeout=10)
    return os.getpid()


def failing_ready(root):
    mark_entered(root)
    position = module._STARTUP_BARRIER.wait(timeout=10)
    if position == 0:
        raise RuntimeError("controlled readiness failure")
    deadline = time.monotonic() + 8
    while not module._STARTUP_BARRIER.broken:
        if time.monotonic() >= deadline:
            raise RuntimeError("controlled sibling abort expired")
        time.sleep(0.01)
    raise threading.BrokenBarrierError("controlled sibling drained")


def draining_ready(root):
    """Acknowledge abort but deliberately retain live work until test releases it."""
    mark_entered(root)
    deadline = time.monotonic() + 8
    while not module._STARTUP_BARRIER.broken:
        if time.monotonic() >= deadline:
            raise RuntimeError("controlled startup decision did not abort")
        time.sleep(0.01)
    (Path(root) / ("abort-observed-" + str(os.getpid()))).write_text("abort", encoding="utf-8")
    while not (Path(root) / "release-drain").exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("controlled startup drain release expired")
        time.sleep(0.01)
    raise threading.BrokenBarrierError("controlled readiness drained after decision")
