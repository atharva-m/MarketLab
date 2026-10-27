"""Pressure tests refuse Redis policies outside the preserved bounded contract."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path("scripts").resolve()))
import r8_cache_faults as faults


def test_exact_owned_redis_policy_is_accepted():
    faults.verify_configuration(
        {
            "maxmemory": "268435456",
            "maxmemory-policy": "allkeys-lru",
            "save": "",
            "appendonly": "no",
        }
    )


@pytest.mark.parametrize(
    "change",
    [
        {"maxmemory": "0"},
        {"maxmemory-policy": "noeviction"},
        {"save": "900 1"},
        {"appendonly": "yes"},
    ],
)
def test_pressure_refuses_changed_resource_or_persistence_policy(change):
    config = {
        "maxmemory": "268435456",
        "maxmemory-policy": "allkeys-lru",
        "save": "",
        "appendonly": "no",
    }
    with pytest.raises(RuntimeError, match="cache policy differs"):
        faults.verify_configuration({**config, **change})
