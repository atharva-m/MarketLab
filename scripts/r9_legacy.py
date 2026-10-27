"""Live TCP/CLI retained-contract checks against the exact owned R9 API only."""

import argparse
import json
import subprocess
import sys
from uuid import uuid4

import httpx


def run(port: int) -> dict:
    assert port == 58007, "Expected owned R9 API port"
    result = {"status": "running", "port": port, "cli": []}
    tag = "R9." + uuid4().hex[:8].upper()
    symbol = tag + ".LEGACY"
    records = [
        {
            "trade_id": tag + "." + suffix,
            "symbol": symbol,
            "executed_at": f"2025-01-01T00:00:0{index}Z",
            "price": "1.23000000",
            "quantity": "2.00000000",
        }
        for index, suffix in enumerate(("A", "Z", "a"), 1)
    ]
    with httpx.Client(
        base_url=f"http://127.0.0.1:{port}", timeout=15, trust_env=False, follow_redirects=False
    ) as client:
        for route in ("/health/live", "/health/ready", "/health/dependencies", "/metrics"):
            response = client.get(route, headers={"X-Request-ID": "r9-live-legacy"})
            assert response.status_code == 200, (route, response.status_code)
            assert response.headers["X-Request-ID"] == "r9-live-legacy"
        assert client.post("/trades/import/json", json=records).json() == {"imported": 3}
        assert client.get("/trades", params={"symbol": symbol}).json() == {
            "items": records,
            "next_after_id": None,
        }
        assert (
            client.get("/trades", params={"symbol": symbol, "after_id": tag + ".B"}).json()["items"]
            == records[1:]
        )
        assert client.get("/trades", params={"symbol": symbol.lower()}).status_code == 422
        assert client.get("/trades/" + records[0]["trade_id"].lower()).status_code == 404
        selected = client.get(
            "/trades",
            params={
                "symbol": symbol,
                "executed_from": "2025-01-01T00:00:02Z",
                "executed_before": "2025-01-01T00:00:03Z",
            },
        ).json()
        assert selected == {"items": [records[1]], "next_after_id": None}
        assert client.get("/trades/" + records[0]["trade_id"]).json() == records[0]
        rollback_id = tag + ".rollback"
        invalid = [records[0] | {"trade_id": rollback_id}, records[1] | {"price": "bad"}]
        assert client.post("/trades/import/json", json=invalid).status_code == 422
        assert client.get("/trades/" + rollback_id).status_code == 404
        conflicting = [records[0] | {"trade_id": rollback_id}, records[0] | {"price": "2.00000000"}]
        assert client.post("/trades/import/json", json=conflicting).status_code == 409
        assert client.get("/trades/" + rollback_id).status_code == 404
        assert (
            client.post(
                "/trades/import/json", content=b"[]", headers={"Content-Type": "text/plain"}
            ).status_code
            == 415
        )
        assert (
            client.post(
                "/trades/import/json",
                content=(b" " * 1048577),
                headers={"Content-Type": "application/json"},
            ).status_code
            == 413
        )
        csv_id = tag + ".csv"
        csv = (
            "trade_id,symbol,executed_at,price,quantity\n"
            + f"{csv_id},{symbol},2025-01-01T00:00:04Z,1.23000000,2.00000000\n"
        )
        csv_response = client.post(
            "/trades/import/csv", content=csv.encode(), headers={"Content-Type": "text/csv"}
        )
        assert csv_response.status_code == 200 and csv_response.json() == {"imported": 1}, (
            csv_response.text
        )
        for args, exit_code in (
            (["--trade-id", records[0]["trade_id"]], 0),
            (["--trade-id", tag + ".missing"], 1),
            (
                [
                    "--symbol",
                    symbol,
                    "--limit",
                    "1",
                    "--executed-from",
                    "2025-01-01T00:00:01Z",
                    "--executed-before",
                    "2025-01-01T00:00:04Z",
                    "--max-pages",
                    "3",
                ],
                0,
            ),
            (["--trade-id", records[0]["trade_id"], "--symbol", symbol], 2),
        ):
            completed = subprocess.run(
                [sys.executable, "-m", "marketlab.trade_cli", "--port", str(port), *args],
                capture_output=True,
                text=True,
                timeout=40,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            assert completed.returncode == exit_code, completed.stderr
            if exit_code == 0 and "--trade-id" in args:
                assert json.loads(completed.stdout) == records[0]
            elif exit_code == 0:
                pages = [json.loads(line) for line in completed.stdout.splitlines()]
                assert [item for page in pages for item in page["items"]] == records
                assert pages[-1]["next_after_id"] is None
            else:
                assert completed.stdout == "" and "Traceback" not in completed.stderr
            result["cli"].append({"arguments": args, "exit_code": exit_code})
    result.update(
        status="passed",
        http=[
            "health/metrics/request-id",
            "JSON/CSV import",
            "transaction rollback/conflict",
            "C-order/exclusive nonexistent boundary",
            "exact case",
            "inclusive/exclusive UTC filtering",
            "1 MiB/content-type bounds",
        ],
        owned_record_prefix=tag,
    )
    return result


def main():
    from r9_common import Invocation, owned_process, prefix, settings

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=prefix, required=True)
    args = parser.parse_args()
    with Invocation(args.prefix, "legacy") as evidence:
        settings()
        evidence.data["owned_api"] = owned_process("api", 58007)
        evidence.data["result"] = run(58007)


if __name__ == "__main__":
    main()
