"""Live R3 cache failure/eviction and retained-interface acceptance.

Requires the exact owned R3 services recorded in artifacts/r3/resource-ownership.json.
Never stops, flushes or fills any other Redis server.
"""

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import zipfile
from datetime import date
from pathlib import Path
from uuid import uuid4

import httpx
import redis
import sqlalchemy as sa

from marketlab.datasets.publication import _verify_manifest, ingest_archive

BASE = Path("artifacts/r3")
ROOT = Path("artifacts/r2/historical-storage").resolve()


def save(name: str, value: object) -> None:
    (BASE / name).write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


def owned_redis() -> str:
    evidence = json.loads((BASE / "resource-ownership.json").read_text(encoding="utf-8-sig"))
    recorded = next(
        item
        for item in evidence
        if "redis" in item["name"]
        and os.environ["MARKETLAB_REDIS_URL"]
        == f"redis://127.0.0.1:{item['ports']['6379/tcp'][0]['HostPort']}/0"
    )
    actual = json.loads(subprocess.check_output(["docker", "inspect", recorded["id"]]))[0]
    assert actual["Id"] == recorded["id"]
    assert actual["Name"] == recorded["name"]
    assert actual["Config"]["Labels"]["marketlab.r3.owner"] == "r3-20261024"
    port = actual["NetworkSettings"]["Ports"]["6379/tcp"][0]
    assert port["HostIp"] == "127.0.0.1"
    assert os.environ["MARKETLAB_REDIS_URL"] == f"redis://127.0.0.1:{port['HostPort']}/0"
    return recorded["id"]


class LiveAPI:
    def __init__(self) -> None:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.log = (BASE / f"live-api-{self.port}.log").open("w", encoding="utf-8")
        env = os.environ.copy()
        env["MARKETLAB_STORAGE_PATH"] = str(ROOT)
        env["MARKETLAB_OLLAMA_URL"] = "http://127.0.0.1:1"
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "marketlab.app:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                "--loop",
                "asyncio:SelectorEventLoop",
                "--no-access-log",
            ],
            env=env,
            stdout=self.log,
            stderr=self.log,
        )
        self.client = httpx.Client(base_url=self.url, timeout=120, trust_env=False)
        for _ in range(100):
            try:
                if self.client.get("/health/live").status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        self.close()
        raise AssertionError("Owned API did not start")

    def close(self) -> None:
        self.client.close()
        if os.name == "nt":
            # The venv Python launcher owns a child interpreter on Windows.
            subprocess.run(
                ["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                check=False,
                capture_output=True,
            )
        else:
            self.process.terminate()
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.log.close()


def main() -> None:
    redis_id = owned_redis()
    cache = redis.Redis.from_url(os.environ["MARKETLAB_REDIS_URL"], socket_timeout=3)
    configuration = cache.config_get("maxmemory", "maxmemory-policy", "save", "appendonly")
    assert configuration == {
        "maxmemory": "268435456",
        "maxmemory-policy": "allkeys-lru",
        "save": "",
        "appendonly": "no",
    }
    catalog = json.loads(Path("artifacts/r2/catalog-final.json").read_text())["catalog"]
    first = next(item for item in catalog if item["symbol"] == "BTCUSDT")
    parameters = {
        "version": first["dataset_version_id"],
        "symbol": "BTCUSDT",
        "interval": "1m",
        "start": "2025-01-01T00:00:00Z",
        "end": "2025-01-02T00:00:00Z",
    }
    expected = json.loads((BASE / f"reference-{first['dataset_version_id']}.json").read_text())[
        "one"
    ]
    result: dict[str, object] = {
        "redis_configuration": configuration,
        "peak_memory": "not measured",
    }
    api = LiveAPI()
    stopped = False
    try:
        response = api.client.get("/v1/bars", params=parameters)
        assert response.status_code == 200, response.text
        assert response.json()["bars"] == expected
        body = response.json()
        result["initial_status"] = response.headers["x-cache"]
        response = api.client.get("/v1/bars", params=parameters)
        assert response.json() == body and response.headers["x-cache"] == "HIT"
        result["warm_status"] = "HIT"
        keys = list(cache.scan_iter(match="marketlab:cache-v1:bars:*"))
        target = None
        for key in keys:
            envelope = json.loads(cache.get(key))
            if envelope.get("body") == body:
                target = key
                break
        assert target is not None
        result["bar_ttl"] = cache.ttl(target)
        assert 1 <= cache.ttl(target) <= 990
        # Stop the primed cache, then read the same previously cached result repeatedly.
        subprocess.run(["docker", "stop", redis_id], check=True, capture_output=True)
        stopped = True
        outage = []
        for _ in range(4):
            started = time.perf_counter()
            response = api.client.get("/v1/bars", params=parameters)
            assert response.status_code == 200 and response.json() == body
            assert response.headers["x-cache"] == "BYPASS"
            outage.append({"status": "BYPASS", "seconds": time.perf_counter() - started})
        assert api.client.get("/health/ready").status_code == 200
        result["primed_cache_outage"] = outage
        subprocess.run(["docker", "start", redis_id], check=True, capture_output=True)
        stopped = False
        for _ in range(100):
            try:
                if cache.ping():
                    break
            except redis.RedisError:
                pass
            time.sleep(0.1)
        assert cache.dbsize() == 0  # No persistence survived the actual Redis restart.
        time.sleep(10.1)
        response = api.client.get("/v1/bars", params=parameters)
        assert response.json() == body and response.headers["x-cache"] == "MISS"
        response = api.client.get("/v1/bars", params=parameters)
        assert response.json() == body and response.headers["x-cache"] == "HIT"
        result["redis_restart"] = ["MISS", "HIT"]
        # Fresh application process must reverify source integrity before using cached body.
        api.close()
        api = LiveAPI()
        response = api.client.get("/v1/bars", params=parameters)
        assert response.json() == body and response.headers["x-cache"] == "HIT"
        result["application_restart"] = "HIT with identical response"
        # Avoid touching target while filling; allkeys-lru must actually evict it.
        before = cache.info("stats")["evicted_keys"]
        payload = b"r3-owned-pressure" * 65_536
        for index in range(512):
            cache.set(f"r3:owned:pressure:{index}", payload)
        after = cache.info("stats")["evicted_keys"]
        assert after > before and not cache.exists(target)
        response = api.client.get("/v1/bars", params=parameters)
        assert response.json() == body and response.headers["x-cache"] == "MISS"
        response = api.client.get("/v1/bars", params=parameters)
        assert response.json() == body and response.headers["x-cache"] == "HIT"
        result["eviction"] = {
            "evicted_keys_before": before,
            "evicted_keys_after": after,
            "target_absent_before_read": True,
            "responses": ["MISS", "HIT"],
            "pressure_values": 512,
            "pressure_value_bytes": len(payload),
        }
        # Remove only this harness's pressure keys after actual eviction assertions.
        pressure = list(cache.scan_iter(match="r3:owned:pressure:*"))
        if pressure:
            cache.delete(*pressure)
        run_id = uuid4().hex[:6].upper()
        legacy_symbol = "R3.LEGACY." + run_id
        legacy_ids = [f"R3.{run_id}.{suffix}" for suffix in ("A", "Z", "a")]
        rollback_id = f"R3.{run_id}.rollback"
        missing_id = f"R3.{run_id}.missing"
        trades = [
            {
                "trade_id": identifier,
                "symbol": legacy_symbol,
                "executed_at": "2025-01-01T00:00:00Z",
                "price": "1.23000000",
                "quantity": "2.00000000",
            }
            for identifier in legacy_ids
        ]
        response = api.client.post("/trades/import/json", json=trades)
        assert response.status_code == 200 and response.json() == {"imported": 3}
        assert api.client.get("/trades", params={"symbol": legacy_symbol}).json() == {
            "items": trades,
            "next_after_id": None,
        }
        invalid = [dict(trades[0], trade_id=rollback_id), dict(trades[1], price="invalid")]
        assert api.client.post("/trades/import/json", json=invalid).status_code == 422
        assert api.client.get("/trades/" + rollback_id).status_code == 404
        cli = []
        for arguments, exit_code in (
            (["--trade-id", legacy_ids[-1]], 0),
            (
                [
                    "--limit",
                    "1",
                    "--symbol",
                    legacy_symbol,
                    "--executed-from",
                    "2025-01-01T00:00:00Z",
                    "--executed-before",
                    "2025-01-02T00:00:00Z",
                    "--max-pages",
                    "3",
                ],
                0,
            ),
            (["--trade-id", missing_id], 1),
        ):
            completed = subprocess.run(
                [sys.executable, "-m", "marketlab.trade_cli", "--port", str(api.port), *arguments],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert completed.returncode == exit_code
            if arguments == ["--trade-id", legacy_ids[-1]]:
                assert json.loads(completed.stdout) == trades[-1]
            elif exit_code == 0:
                pages = [json.loads(line) for line in completed.stdout.splitlines()]
                assert pages == [
                    {"items": [trade], "next_after_id": trade["trade_id"] if index < 2 else None}
                    for index, trade in enumerate(trades)
                ]
            else:
                assert completed.stdout == "" and "HTTP 404" in completed.stderr
            cli.append({"arguments": arguments, "exit": completed.returncode})
        result["legacy_cli"] = cli
        result["legacy_http"] = ["health", "transactional import", "C-order listing", "rollback"]
        metrics = api.client.get("/metrics")
        assert metrics.status_code == 200 and "marketlab_cache_requests_total" in metrics.text
        result["metrics_exposed"] = True
        result["bar_body_sha256"] = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    finally:
        api.close()
        if stopped:
            subprocess.run(["docker", "start", redis_id], check=True, capture_output=True)
        cache.close()
    # Synchronous fixture ingestion and dataset CLI inspection retain durable R2 execution.
    fixture = BASE / "legacy-fixture"
    fixture.mkdir(exist_ok=True)
    archive = fixture / "BTCUSDT-trades-2025-01-01.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr(
            "BTCUSDT-trades-2025-01-01.csv", "1,10.00,2.00,20.00,1735689600000000,True,True\n"
        )
    checksum = fixture / "source.CHECKSUM"
    checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + "  " + archive.name)
    engine = sa.create_engine(os.environ["MARKETLAB_DATABASE_URL"])
    root = fixture / "storage"
    manifest = ingest_archive(
        engine, root, archive, checksum, symbol="BTCUSDT", trade_date=date(2025, 1, 1)
    )
    repeated = ingest_archive(
        engine, root, archive, checksum, symbol="BTCUSDT", trade_date=date(2025, 1, 1)
    )
    assert repeated == manifest
    env = os.environ.copy()
    env["MARKETLAB_STORAGE_PATH"] = str(root.resolve())
    inspected = subprocess.run(
        [
            sys.executable,
            "-m",
            "marketlab.dataset_cli",
            "inspect",
            "--version",
            manifest["dataset_version_id"],
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert inspected.returncode == 0 and json.loads(inspected.stdout) == manifest
    result["historical_compatibility"] = {
        "fixture_ingest_and_repeat": True,
        "dataset_cli_inspect": True,
        "rows": manifest["quality"]["accepted_rows"],
    }
    old_manifest = json.loads(Path("artifacts/r1/real-manifest.json").read_text())
    old_path = (
        Path("artifacts/r1/historical-storage/datasets")
        / old_manifest["dataset_version_id"]
        / "venue=binance_spot/symbol=BTCUSDT/date=2025-01-01/manifest.json"
    )
    old_hash = hashlib.sha256(old_path.read_bytes()).hexdigest()
    assert _verify_manifest(old_path, old_manifest["dataset_version_id"], old_hash) == old_manifest
    assert hashlib.sha256(old_path.read_bytes()).hexdigest() == old_hash
    result["retained_original_r1"] = {
        "version": old_manifest["dataset_version_id"],
        "manifest_sha256": old_hash,
        "full_readback": True,
        "unchanged": True,
        "rows": old_manifest["quality"]["accepted_rows"],
    }
    engine.dispose()
    save("live-complete.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
