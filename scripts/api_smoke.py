"""Smoke check a running API using only the Python standard library."""

import argparse
import json
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    for path in ("/health/live", "/health/ready", "/health/dependencies", "/metrics"):
        request = urllib.request.Request(
            args.url.rstrip("/") + path, headers={"X-Request-ID": "api-smoke"}
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode()
            assert response.status == 200, (path, response.status)
            assert response.headers["X-Request-ID"] == "api-smoke"
            if path in {"/health/ready", "/health/dependencies"}:
                assert json.loads(body)["status"] in {"ready", "degraded"}
            elif path == "/metrics":
                assert "marketlab_http_requests_total" in body
        print(json.dumps({"path": path, "status": "passed"}))


if __name__ == "__main__":
    main()
