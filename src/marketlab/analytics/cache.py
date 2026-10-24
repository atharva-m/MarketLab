"""Optional Redis cache with bounded values, deadlines and a small circuit breaker."""

import asyncio
import hashlib
import json
import random
import time
from collections.abc import Callable
from typing import Any, Literal

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from redis.exceptions import RedisError

CACHE_SCHEMA = "cache-v1"
MAX_VALUE = 1024 * 1024
CacheKind = Literal["bars", "summary"]
CacheStatus = Literal["HIT", "MISS", "BYPASS"]


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def cache_key(kind: CacheKind, identity: object, parameters: object) -> str:
    digest = hashlib.sha256(canonical({"identity": identity, "parameters": parameters})).hexdigest()
    return f"marketlab:{CACHE_SCHEMA}:{kind}:{digest}"


class AnalyticsMetrics:
    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        registry = registry or CollectorRegistry()
        self.outcomes = Counter(
            "marketlab_cache_requests_total", "Cache results", ["outcome"], registry=registry
        )
        self.failures = Counter(
            "marketlab_cache_failures_total", "Redis command failures", registry=registry
        )
        self.circuit = Gauge(
            "marketlab_cache_circuit_open", "Redis bypass circuit", registry=registry
        )
        self.coalesced = Counter(
            "marketlab_bar_coalesced_total", "Shared identical reads", registry=registry
        )
        self.duration = Histogram(
            "marketlab_bar_query_seconds", "DuckDB execution seconds", registry=registry
        )
        self.active = Gauge(
            "marketlab_bar_active", "Active expensive analytical reads", registry=registry
        )
        self.overload = Counter(
            "marketlab_bar_overload_total", "Rejected analytical admission", registry=registry
        )
        self.timeouts = Counter(
            "marketlab_bar_timeouts_total", "Interrupted DuckDB deadlines", registry=registry
        )


class ResponseCache:
    """Cache schema validation is supplied by the immutable result's owner."""

    def __init__(
        self,
        url: str | None,
        metrics: AnalyticsMetrics,
        *,
        clock: Callable[[], float] = time.monotonic,
        jitter: Callable[[int, int], int] = random.randint,
    ) -> None:
        self.client: Redis | None = (
            Redis.from_url(
                url,
                socket_connect_timeout=0.1,
                socket_timeout=0.1,
                retry=Retry(NoBackoff(), 0),
                retry_on_timeout=False,
                max_connections=8,
                decode_responses=False,
            )
            if url
            else None
        )
        self.metrics = metrics
        self.clock = clock
        self.jitter = jitter
        self.failures = 0
        self.open_until = 0.0
        self.probing = False
        self.generation = 0
        self.lock = asyncio.Lock()

    async def _enter(self) -> int | None:
        async with self.lock:
            if self.client is None or self.probing:
                return None
            if self.open_until:
                if self.clock() < self.open_until:
                    return None
                self.probing = True
            return self.generation

    async def _finish(self, success: bool, generation: int) -> None:
        async with self.lock:
            if not success:
                self.metrics.failures.inc()
            if generation != self.generation:
                return
            if success:
                self.failures = 0
                self.open_until = 0
                self.metrics.circuit.set(0)
            else:
                self.failures += 1
                if self.probing or self.failures >= 3:
                    self.open_until = self.clock() + 10
                    self.generation += 1
                    self.metrics.circuit.set(1)
            self.probing = False

    async def _command(self, operation: Callable[[], Any]) -> tuple[bool, Any]:
        generation = await self._enter()
        if generation is None:
            return False, None
        try:
            async with asyncio.timeout(0.1):
                result = await operation()
        except (RedisError, OSError, TimeoutError):
            await self._finish(False, generation)
            return False, None
        except asyncio.CancelledError:
            await self._finish(False, generation)
            raise
        await self._finish(True, generation)
        return True, result

    async def get(
        self, key: str, validator: Callable[[Any], bool]
    ) -> tuple[dict[str, Any] | None, bool]:
        if self.client is None:
            return None, False
        # Redis returns at most cap+1 bytes, so even a hostile oversized entry is
        # bounded before transport/JSON parsing. GETRANGE is a single atomic command.
        available, value = await self._command(
            lambda: self.client.getrange(key, 0, MAX_VALUE)  # type: ignore[union-attr]
        )
        if not available or not value:
            return None, available
        try:
            if not isinstance(value, bytes) or len(value) > MAX_VALUE:
                return None, True
            envelope = json.loads(value)
            if (
                set(envelope) != {"schema", "key", "body", "sha256"}
                or envelope["schema"] != CACHE_SCHEMA
                or envelope["key"] != key
                or hashlib.sha256(canonical(envelope["body"])).hexdigest() != envelope["sha256"]
                or not validator(envelope["body"])
            ):
                return None, True
            return envelope["body"], True
        except (TypeError, ValueError, KeyError, RecursionError):
            return None, True

    async def put(
        self,
        key: str,
        body: dict[str, Any],
        kind: CacheKind,
        *,
        validator: Callable[[Any], bool] | None = None,
    ) -> bool:
        if kind == "summary" and (validator is None or not validator(body)):
            return False
        if self.client is None:
            return False
        payload = canonical(
            {
                "schema": CACHE_SCHEMA,
                "key": key,
                "body": body,
                "sha256": hashlib.sha256(canonical(body)).hexdigest(),
            }
        )
        if len(payload) > MAX_VALUE:
            return False
        ttl = self.jitter(810, 990) if kind == "bars" else self.jitter(3240, 3960)
        available, stored = await self._command(lambda: self.client.set(key, payload, ex=ttl))  # type: ignore[union-attr]
        return available and bool(stored)

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()
