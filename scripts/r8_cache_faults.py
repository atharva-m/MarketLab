"""Actual owned Redis corrupt-envelope, oversize and LRU acceptance.

Reuses the retained R3/R4 pressure method and unchanged production cache paths.
No Redis configuration, original service, retained artifact or historical harness
is changed. Run only when other owned workloads have stopped.
"""

import argparse
import asyncio
import hashlib
from pathlib import Path
from uuid import uuid4

from r8_benchmark import isolated
from r8_common import Invocation, owned_settings, recorded, validate_prefix
from r8_recovery import operational_adapter
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff

from marketlab.analytics.bars import BarService
from marketlab.analytics.cache import (
    MAX_VALUE,
    AnalyticsMetrics,
    ResponseCache,
    cache_key,
    canonical,
)
from marketlab.research.service import ResearchService


def verify_configuration(value: dict[str, str]) -> None:
    if value != {
        "maxmemory": "268435456",
        "maxmemory-policy": "allkeys-lru",
        "save": "",
        "appendonly": "no",
    }:
        raise RuntimeError("Owned Redis cache policy differs from preserved contract")


async def main(prefix: str) -> None:
    with Invocation(prefix, "cache-faults") as evidence:
        settings = owned_settings()  # Validates actual IDs/images/labels/ports before Redis writes.
        evidence.data["redis_container"] = recorded("redis")["Id"]
        evidence.data["historical_methods"] = {
            name: hashlib.sha256(await asyncio.to_thread(Path(name).read_bytes)).hexdigest()
            for name in ("scripts/r3_live_acceptance.py", "scripts/r4_live_acceptance.py")
        }
        client = Redis.from_url(
            settings.redis_url.get_secret_value(),
            decode_responses=True,
            socket_timeout=3,
            socket_connect_timeout=3,
            retry=Retry(NoBackoff(), 0),
            retry_on_timeout=False,
        )
        pressure = "r8:owned:pressure:" + uuid4().hex + ":"
        target = None
        bars = research = None
        try:
            configuration = await client.config_get(
                "maxmemory", "maxmemory-policy", "save", "appendonly"
            )
            verify_configuration(configuration)
            evidence.data["redis_configuration"] = configuration
            evidence.data["redis_container_memory_limit_bytes"] = recorded("redis")["HostConfig"][
                "Memory"
            ]
            with isolated(prefix) as (_, engine, root, _):
                adapter = operational_adapter()
                spec = await asyncio.to_thread(adapter.fixture, engine, root)
                bars = BarService(engine, root, settings.redis_url.get_secret_value())
                research = ResearchService(bars)
                run_id = await adapter.successful(research, spec, prefix + "-numerical")
                expected, summary_sha = research.read(run_id, "summary")
                payload_sha = hashlib.sha256(canonical(expected)).hexdigest()
                target = cache_key(
                    "summary",
                    {"run": run_id, "sha256": summary_sha},
                    {"definition": "research-numerics-v1"},
                )

                async def read(expected_outcome: str) -> None:
                    body, outcome = await research.summary(run_id)
                    assert body == expected and outcome == expected_outcome
                    assert hashlib.sha256(canonical(body)).hexdigest() == payload_sha

                await read("MISS")
                await read("HIT")
                ttl = await client.ttl(target)
                assert 3240 <= ttl <= 3960
                await client.set(target, b'{"invalid":true}')
                await read("MISS")
                await client.set(target, b"x" * (MAX_VALUE + 1024))
                await read("MISS")
                evidence.data["corrupt_and_oversized_envelopes"] = ["MISS", "MISS"]
                policy = ResponseCache(settings.redis_url.get_secret_value(), AnalyticsMetrics())
                oversize_key = "r8:owned:oversize:" + uuid4().hex
                oversized = {"fixture": "x" * (MAX_VALUE + 1)}
                try:
                    stored = await policy.put(
                        oversize_key,
                        oversized,
                        "summary",
                        validator=lambda value: value == oversized,
                    )
                    assert not stored and not await client.exists(oversize_key)
                    evidence.data["oversized_write"] = {
                        "body_bytes": len(canonical(oversized)),
                        "stored": False,
                        "scope": "Production write policy with owned oversized fixture",
                    }
                finally:
                    await policy.close()
                    await client.delete(oversize_key)
                before = int((await client.info("stats"))["evicted_keys"])
                payload = b"r8-owned-pressure" * 65536
                rss_samples = []
                for index in range(512):
                    await client.set(pressure + str(index), payload)
                    if index % 8 == 0:
                        rss = int((await client.info("memory"))["used_memory_rss"])
                        rss_samples.append({"index": index, "rss_bytes": rss})
                        assert rss < 512 * 1024 * 1024, (
                            "Owned Redis pressure exceeded observed headroom"
                        )
                after = int((await client.info("stats"))["evicted_keys"])
                assert after > before and not await client.exists(target)
                await read("MISS")
                await read("HIT")
                evidence.data["lru_eviction"] = {
                    "evicted_keys_before": before,
                    "evicted_keys_after": after,
                    "target_absent_before_recomputation": True,
                    "responses": ["MISS", "HIT"],
                    "pressure_values": 512,
                    "value_bytes": len(payload),
                    "rss_samples": rss_samples,
                    "memory_scope": "Observed Redis RSS; no true peak or cgroup cap guarantee",
                }
                assert research.read(run_id, "summary") == (expected, summary_sha)
                evidence.data.update(
                    run_id=run_id,
                    summary_sha256=summary_sha,
                    payload_sha256=payload_sha,
                    summary_ttl=ttl,
                )
                evidence.flush()
                await research.close()
                await bars.close()
                research = bars = None
            evidence.data["owned_schema_removed"] = True
        finally:
            if research is not None:
                await research.close()
            if bars is not None:
                await bars.close()
            # Exact generated namespace only; never flush shared cache keys.
            batch = []
            async for key in client.scan_iter(match=pressure + "*", count=100):
                batch.append(key)
                if len(batch) == 100:
                    await client.delete(*batch)
                    batch = []
            if batch:
                await client.delete(*batch)
            if target is not None:
                await client.delete(target)
            await client.aclose()
            evidence.data["owned_pressure_keys_removed"] = True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True, type=validate_prefix)
    asyncio.run(main(parser.parse_args().prefix))
