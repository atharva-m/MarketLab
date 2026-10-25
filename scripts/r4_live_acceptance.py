"""Real R4 summary-cache/API/CLI acceptance on recorded owned resources only.

Uses a private provider-shaped 15-bar fixture and storage root, preserving all
retained market data. Ollama is deliberately unavailable for the owned API.
"""

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import r3_live_acceptance
import redis
import sqlalchemy as sa
from r4_reference import encoded, reference_payload, stamp

from marketlab.analytics.cache import MAX_VALUE, AnalyticsMetrics, ResponseCache
from marketlab.config import Settings
from marketlab.datasets.publication import _verify_manifest, ingest_archive

BASE = Path("artifacts/r4")
ROOT = (BASE / "live-storage").resolve()


def save(name: str, value: Any) -> None:
    (BASE / name).write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


def owned_redis() -> str:
    evidence = json.loads((BASE / "resource-ownership.json").read_text(encoding="utf-8-sig"))
    recorded = next(item for item in evidence if "redis" in item["Name"])
    actual = json.loads(subprocess.check_output(["docker", "inspect", recorded["Id"]]))[0]
    assert actual["Id"] == recorded["Id"] and actual["Name"] == recorded["Name"]
    assert actual["Config"]["Labels"]["marketlab.r4.owner"] == "r4-20261024"
    port = actual["NetworkSettings"]["Ports"]["6379/tcp"][0]
    assert port["HostIp"] == "127.0.0.1"
    assert os.environ["MARKETLAB_REDIS_URL"] == f"redis://127.0.0.1:{port['HostPort']}/0"
    assert actual["HostConfig"]["Memory"] == 512 * 1024 * 1024
    # Verify the fixture database is the other explicitly recorded owned service.
    postgres = next(item for item in evidence if "-pg-" in item["Name"])
    actual_pg = json.loads(subprocess.check_output(["docker", "inspect", postgres["Id"]]))[0]
    assert actual_pg["Id"] == postgres["Id"]
    assert actual_pg["Config"]["Labels"]["marketlab.r4.owner"] == "r4-20261024"
    pgport = actual_pg["NetworkSettings"]["Ports"]["5432/tcp"][0]
    url = Settings().sqlalchemy_url
    assert pgport["HostIp"] == "127.0.0.1"
    assert url.host == "127.0.0.1" and url.port == int(pgport["HostPort"])
    return actual["Id"]


def fixture() -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    ROOT.mkdir(parents=True, exist_ok=True)
    source = BASE / "live-fixture"
    source.mkdir(exist_ok=True)
    archive = source / "BTCUSDT-trades-2025-01-01.zip"
    beginning = datetime(2025, 1, 1, tzinfo=UTC)
    prices = ["100"] * 12 + ["100", "110", "99"]
    rows, bars = [], []
    for index, price in enumerate(prices):
        when = beginning + timedelta(minutes=5 * index)
        micros = int(when.timestamp()) * 1_000_000
        rows.append(f"{index + 1},{price},1,{price},{micros},True,True\n")
        value = f"{price}.000000000000000000"
        bars.append(
            {
                "start": stamp(when),
                "end": stamp(when + timedelta(minutes=5)),
                "open": value,
                "high": value,
                "low": value,
                "close": value,
                "base_volume": "1.000000000000000000",
                "quote_volume": value,
                "trade_count": 1,
                "vwap": value,
            }
        )
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("BTCUSDT-trades-2025-01-01.csv", "".join(rows))
    checksum = source / "source.CHECKSUM"
    checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + "  " + archive.name)
    settings = Settings()
    engine = sa.create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
    try:
        manifest = ingest_archive(
            engine, ROOT, archive, checksum, symbol="BTCUSDT", trade_date=date(2025, 1, 1)
        )
        assert (
            ingest_archive(
                engine, ROOT, archive, checksum, symbol="BTCUSDT", trade_date=date(2025, 1, 1)
            )
            == manifest
        )
    finally:
        engine.dispose()
    spec = {
        "schema": "research-spec-v1",
        "workflow": "market_profile",
        "symbols": ["BTCUSDT"],
        "dataset_versions": [manifest["dataset_version_id"]],
        "start": "2025-01-01T01:00:00Z",
        "end": "2025-01-01T01:15:00Z",
        "history_start": "2025-01-01T00:00:00Z",
        "interval": "5m",
        "metrics": ["profile"],
        "parameters": {},
        "predicates": {},
    }
    return spec, bars, manifest


def command(arguments: list[str], *, root: Path = ROOT) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["MARKETLAB_STORAGE_PATH"] = str(root)
    env["MARKETLAB_OLLAMA_URL"] = "http://127.0.0.1:1"
    completed = subprocess.run(
        [sys.executable, *arguments], env=env, capture_output=True, text=True, timeout=120
    )
    assert completed.returncode == 0, completed.stderr
    return completed


def submit_and_work(api: Any, spec: dict[str, Any], key: str) -> str:
    response = api.client.post("/v1/research/runs", json=spec, headers={"Idempotency-Key": key})
    assert response.status_code == 201, response.text
    run_id = response.json()["run_id"]
    repeated = api.client.post("/v1/research/runs", json=spec, headers={"Idempotency-Key": key})
    assert repeated.status_code == 200 and repeated.json() == {"run_id": run_id, "replayed": True}
    outcome = command(
        ["-m", "marketlab.research_cli", "worker", "--max-runs", "1", "--run", run_id]
    )
    assert json.loads(outcome.stdout) == {"attempted_runs": 1}
    state = api.client.get(f"/v1/research/runs/{run_id}")
    assert state.status_code == 200 and state.json()["state"] == "succeeded", state.text
    return run_id


def legacy(api: Any) -> dict[str, Any]:
    unique = uuid4().hex[:8].upper()
    symbol = "R4.LEGACY." + unique
    ids = [f"R4.{unique}.{suffix}" for suffix in ("A", "Z", "a")]
    trades = [
        {
            "trade_id": identity,
            "symbol": symbol,
            "executed_at": "2025-01-01T00:00:00Z",
            "price": "1.23000000",
            "quantity": "2.00000000",
        }
        for identity in ids
    ]
    response = api.client.post("/trades/import/json", json=trades)
    assert response.status_code == 200 and response.json() == {"imported": 3}
    assert api.client.get("/trades", params={"symbol": symbol}).json() == {
        "items": trades,
        "next_after_id": None,
    }
    invalid = [dict(trades[0], trade_id=f"R4.{unique}.rollback"), dict(trades[1], price="bad")]
    assert api.client.post("/trades/import/json", json=invalid).status_code == 422
    assert api.client.get(f"/trades/R4.{unique}.rollback").status_code == 404
    exact = command(["-m", "marketlab.trade_cli", "--port", str(api.port), "--trade-id", ids[-1]])
    assert json.loads(exact.stdout) == trades[-1]
    listing = command(
        [
            "-m",
            "marketlab.trade_cli",
            "--port",
            str(api.port),
            "--limit",
            "1",
            "--symbol",
            symbol,
            "--executed-from",
            "2025-01-01T00:00:00Z",
            "--executed-before",
            "2025-01-02T00:00:00Z",
            "--max-pages",
            "3",
        ]
    )
    pages = [json.loads(line) for line in listing.stdout.splitlines()]
    assert pages == [
        {"items": [trade], "next_after_id": trade["trade_id"] if index < 2 else None}
        for index, trade in enumerate(trades)
    ]
    missing = subprocess.run(
        [
            sys.executable,
            "-m",
            "marketlab.trade_cli",
            "--port",
            str(api.port),
            "--trade-id",
            f"R4.{unique}.missing",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert missing.returncode == 1 and missing.stdout == "" and "HTTP 404" in missing.stderr
    return {
        "transactional_import": True,
        "rollback": True,
        "C_order": True,
        "exact_id_cli": True,
        "filtered_paginated_cli": True,
        "missing_cli": True,
    }


async def oversize_write() -> dict[str, Any]:
    cache = ResponseCache(os.environ["MARKETLAB_REDIS_URL"], AnalyticsMetrics())
    key = "r4:owned:oversize:" + uuid4().hex
    body = {"fixture": "x" * (MAX_VALUE + 1)}
    try:
        stored = await cache.put(key, body, "summary", validator=lambda value: value == body)
        assert not stored
        assert cache.client is not None and not await cache.client.exists(key)
        return {
            "fixture_policy_check_against_real_redis": True,
            "body_bytes": len(encoded(body)),
            "stored": False,
        }
    finally:
        await cache.close()


def main() -> None:
    BASE.mkdir(exist_ok=True)
    redis_id = owned_redis()
    cache = redis.Redis.from_url(os.environ["MARKETLAB_REDIS_URL"], socket_timeout=3)
    configuration = cache.config_get("maxmemory", "maxmemory-policy", "save", "appendonly")
    assert configuration == {
        "maxmemory": "268435456",
        "maxmemory-policy": "allkeys-lru",
        "save": "",
        "appendonly": "no",
    }
    spec, bars, manifest = fixture()
    expected_result, expected_summary = reference_payload(spec, {"BTCUSDT": bars})
    r3_live_acceptance.BASE, r3_live_acceptance.ROOT = BASE, ROOT
    api = r3_live_acceptance.LiveAPI()
    stopped = False
    evidence: dict[str, Any] = {
        "redis_configuration": configuration,
        "storage": str(ROOT),
        "peak_memory": "not measured",
    }
    try:
        run_id = submit_and_work(api, spec, "r4-live-primary-" + uuid4().hex)
        corrupt_id = submit_and_work(api, spec, "r4-live-corrupt-" + uuid4().hex)
        evidence["runs"] = {"primary": run_id, "corruption_fixture": corrupt_id}
        route = f"/v1/research/runs/{run_id}"
        assert api.client.get(route + "/results").json() == expected_result
        response = api.client.get(route + "/summary")
        assert response.status_code == 200 and response.json() == expected_summary
        assert response.headers["x-cache"] == "MISS", response.headers
        response = api.client.get(route + "/summary")
        assert response.json() == expected_summary and response.headers["x-cache"] == "HIT"
        digest = hashlib.sha256(encoded(expected_summary)).hexdigest()
        from marketlab.analytics.cache import cache_key

        target = cache_key(
            "summary", {"run": run_id, "sha256": digest}, {"definition": "research-numerics-v1"}
        )
        assert cache.exists(target)
        ttl = cache.ttl(target)
        assert 3240 <= ttl <= 3960
        evidence["summary_cache"] = {"initial": ["MISS", "HIT"], "ttl": ttl}
        # An invalid or oversized real Redis envelope is discarded before returning it.
        cache.set(target, b'{"invalid":true}')
        response = api.client.get(route + "/summary")
        assert response.json() == expected_summary and response.headers["x-cache"] == "MISS"
        cache.set(target, b"x" * (MAX_VALUE + 1024))
        response = api.client.get(route + "/summary")
        assert response.json() == expected_summary and response.headers["x-cache"] == "MISS"
        evidence["corrupt_and_oversized_cached_envelope"] = ["MISS", "MISS"]
        evidence["oversized_write_policy"] = asyncio.run(oversize_write())
        # Corrupt only the independently published disposable corruption fixture.
        corrupt_route = f"/v1/research/runs/{corrupt_id}/summary"
        assert api.client.get(corrupt_route).json() == expected_summary
        assert api.client.get(corrupt_route).headers["x-cache"] == "HIT"
        (ROOT / "research" / corrupt_id / "summary.json").write_bytes(b'{"tampered":true}')
        assert api.client.get(corrupt_route).status_code == 422
        assert api.client.get(route + "/summary").json() == expected_summary
        evidence["artifact_corruption_before_primed_cache_hit"] = "422; primary result unchanged"
        subprocess.run(["docker", "stop", redis_id], check=True, capture_output=True)
        stopped = True
        outage = []
        for _ in range(4):
            started = time.perf_counter()
            response = api.client.get(route + "/summary")
            assert response.status_code == 200 and response.json() == expected_summary
            assert response.headers["x-cache"] == "BYPASS"
            outage.append({"status": "BYPASS", "seconds": time.perf_counter() - started})
        assert api.client.get(route + "/results").json() == expected_result
        readiness = api.client.get("/health/ready")
        assert readiness.status_code == 200
        assert readiness.json()["checks"]["redis"]["status"] == "down"
        assert readiness.json()["checks"]["ollama"]["status"] == "down"
        evidence["primed_summary_outage"] = outage
        evidence["ollama_unavailable"] = (
            "submission,worker,results,summary succeeded; optional health down"
        )
        subprocess.run(["docker", "start", redis_id], check=True, capture_output=True)
        stopped = False
        for _ in range(100):
            try:
                if cache.ping():
                    break
            except redis.RedisError:
                pass
            time.sleep(0.1)
        assert cache.dbsize() == 0
        time.sleep(10.1)
        for status in ("MISS", "HIT"):
            response = api.client.get(route + "/summary")
            assert response.json() == expected_summary and response.headers["x-cache"] == status
        evidence["redis_restart"] = ["MISS", "HIT"]
        api.close()
        api = r3_live_acceptance.LiveAPI()
        response = api.client.get(route + "/summary")
        assert response.json() == expected_summary and response.headers["x-cache"] == "HIT"
        evidence["application_restart"] = "HIT after artifact verification"
        before = cache.info("stats")["evicted_keys"]
        namespace = "r4:owned:pressure:" + uuid4().hex + ":"
        payload = b"r4-owned-pressure" * 65_536
        try:
            for index in range(512):
                cache.set(namespace + str(index), payload)
            after = cache.info("stats")["evicted_keys"]
            assert after > before and not cache.exists(target)
            for status in ("MISS", "HIT"):
                response = api.client.get(route + "/summary")
                assert response.json() == expected_summary and response.headers["x-cache"] == status
            evidence["LRU_eviction"] = {
                "before": before,
                "after": after,
                "target_evicted": True,
                "responses": ["MISS", "HIT"],
                "pressure_values": 512,
                "value_bytes": len(payload),
            }
        finally:
            pressure = list(cache.scan_iter(match=namespace + "*"))
            if pressure:
                cache.delete(*pressure)
        evidence["legacy"] = legacy(api)
        parameters = {
            "version": manifest["dataset_version_id"],
            "symbol": "BTCUSDT",
            "interval": "5m",
            "start": "2025-01-01T00:00:00Z",
            "end": "2025-01-01T01:15:00Z",
        }
        body = api.client.get("/v1/bars", params=parameters)
        assert body.status_code == 200 and body.json()["bars"] == bars
        assert api.client.get("/v1/bars", params=parameters).headers["x-cache"] == "HIT"
        evidence["bars_compatibility"] = {"bars": 15, "exact_fixture": True, "repeat": "HIT"}
        for kind, expected in (("results", expected_result), ("summary", expected_summary)):
            output = command(["-m", "marketlab.research_cli", kind, "--run", run_id])
            assert json.loads(output.stdout) == expected
        inspected = command(
            ["-m", "marketlab.dataset_cli", "inspect", "--version", manifest["dataset_version_id"]]
        )
        assert json.loads(inspected.stdout) == manifest
        evidence["historical_compatibility"] = {
            "fixture_ingest_repeat": True,
            "dataset_cli_inspect": True,
            "accepted_rows": 15,
        }
        metrics = api.client.get("/metrics")
        assert metrics.status_code == 200 and "marketlab_cache_requests_total" in metrics.text
        evidence["metrics"] = True
        evidence["results_sha256"] = hashlib.sha256(encoded(expected_result)).hexdigest()
        evidence["summary_sha256"] = digest
    finally:
        api.close()
        if stopped:
            subprocess.run(["docker", "start", redis_id], check=True, capture_output=True)
        cache.close()
        save("live-progress.json", evidence)
    old_manifest = json.loads(Path("artifacts/r1/real-manifest.json").read_text())
    old_path = (
        Path("artifacts/r1/historical-storage/datasets")
        / old_manifest["dataset_version_id"]
        / "venue=binance_spot/symbol=BTCUSDT/date=2025-01-01/manifest.json"
    )
    old_hash = hashlib.sha256(old_path.read_bytes()).hexdigest()
    assert _verify_manifest(old_path, old_manifest["dataset_version_id"], old_hash) == old_manifest
    assert hashlib.sha256(old_path.read_bytes()).hexdigest() == old_hash
    evidence["retained_original_R1"] = {
        "version": old_manifest["dataset_version_id"],
        "manifest_sha256": old_hash,
        "rows": old_manifest["quality"]["accepted_rows"],
        "full_readback_unchanged": True,
    }
    save("live-complete.json", evidence)
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
