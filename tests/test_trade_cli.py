import io
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from marketlab import trade_cli
from marketlab.app import create_app
from marketlab.config import Settings


def record(trade_id: str = "A", **changes: str) -> dict[str, str]:
    return {
        "trade_id": trade_id,
        "symbol": "SYN.A",
        "executed_at": "2025-01-02T00:00:00.123456Z",
        "price": "999999999999.99999999",
        "quantity": "0.00000001",
        **changes,
    }


def page(ids: list[str], cursor: str | None = None) -> dict[str, object]:
    return {"items": [record(key) for key in ids], "next_after_id": cursor}


def run_pages(
    payloads: list[dict[str, object]], argv: list[str]
) -> tuple[list[dict[str, object]], list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payloads[len(requests) - 1])

    output = io.StringIO()
    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url="http://127.0.0.1"
    ) as client:
        trade_cli.browse(client, trade_cli.parse_args(argv), output)
    return [json.loads(line) for line in output.getvalue().splitlines()], requests


def test_filters_encoded_and_retained_with_only_cursor_changing() -> None:
    argv = [
        "--limit",
        "1",
        "--after-id",
        "0",
        "--symbol",
        "SYN.A",
        "--executed-from",
        "2025-01-02T05:30:00+05:30",
        "--executed-before",
        "2025-01-02T19:00:00-05:00",
        "--max-pages",
        "3",
    ]
    expected = [page(["A"], "A"), page(["Z"], "Z"), page(["a"])]
    observed, requests = run_pages(expected, argv)
    assert observed == expected
    assert len(requests) == 3
    for request, boundary in zip(requests, ["0", "A", "Z"], strict=True):
        assert dict(request.url.params) == {
            "limit": "1",
            "after_id": boundary,
            "symbol": "SYN.A",
            "executed_from": "2025-01-02T05:30:00+05:30",
            "executed_before": "2025-01-02T19:00:00-05:00",
        }
        assert "%2B05%3A30" in str(request.url)
        assert request.extensions["timeout"] == dict.fromkeys(
            ["connect", "read", "write", "pool"], 10.0
        )


@pytest.mark.parametrize("payload", [page([]), page(["A"]), page(["A", "B"])])
def test_final_empty_partial_and_exactly_full_pages_stop(payload: dict[str, object]) -> None:
    observed, requests = run_pages([payload], ["--limit", "2", "--max-pages", "10"])
    assert observed == [payload]
    assert len(requests) == 1


@pytest.mark.parametrize("cap", [1, 2])
def test_page_cap_preserves_resumable_cursor(cap: int) -> None:
    pages = [page(["A"], "A"), page(["B"], "B")]
    argv = ["--limit", "1"] + (["--max-pages", str(cap)] if cap != 1 else [])
    observed, requests = run_pages(pages, argv)
    assert observed == pages[:cap]
    assert observed[-1]["next_after_id"] == ["A", "B"][cap - 1]
    assert len(requests) == cap


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--symbol", "SYN.A"],
        ["--executed-from", "2025-01-01T00:00:00Z"],
        ["--executed-before", "2025-01-03T00:00:00Z"],
    ],
)
def test_defaults_and_optional_filters(argv: list[str]) -> None:
    _, requests = run_pages([page(["A"])], argv)
    assert requests[0].url.params["limit"] == "100"
    assert "after_id" not in requests[0].url.params


@pytest.mark.parametrize(
    "argv",
    [
        ["--max-pages", "0"],
        ["--max-pages", "-1"],
        ["--max-pages", "1.5"],
        ["--limit", "0"],
        ["--limit", "501"],
        ["--port", "0"],
        ["--port", "65536"],
        ["--after-id", "bad id secret"],
        ["--after-id", "A\n"],
        ["--symbol", " SYN.A"],
        ["--symbol", "syn.a"],
        ["--executed-from", "2025-01-01"],
        ["--executed-before", "0001-01-01T00:00:00+01:00"],
        [
            "--executed-from",
            "2025-01-01T00:00:00Z",
            "--executed-before",
            "2024-12-31T19:00:00-05:00",
        ],
        ["--unknown", "secret"],
        ["--port", "secret"],
    ],
)
def test_invalid_arguments_are_redacted_before_client_creation(
    argv: list[str], capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected(**kwargs: object) -> None:
        pytest.fail("client must not be created")

    monkeypatch.setattr(trade_cli.httpx, "Client", unexpected)
    with pytest.raises(SystemExit) as error:
        trade_cli.main(argv)
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "trade-cli: invalid command-line arguments; use --help\n"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"items": [], "next_after_id": "A"},
        page(["B", "A"]),
        page(["A", "A"]),
        page(["A"], "B"),
        page(["A"], "A"),
        page(["0"]),
        page(["A", "B", "C"]),
        {**page(["A"]), "extra": "secret"},
        {"items": [{**record(), "price": 1.5}], "next_after_id": None},
        {
            "items": [{**record(), "executed_at": "2025-01-01T19:00:00-05:00"}],
            "next_after_id": None,
        },
        {"items": [record(symbol="SYN.B")], "next_after_id": None},
        {"items": [record(executed_at="2024-01-01T00:00:00Z")], "next_after_id": None},
        {"items": [record(executed_at="2025-01-03T00:00:00Z")], "next_after_id": None},
        {"items": [record(price="1.000000000")], "next_after_id": None},
        {"items": [record(trade_id="_bad")], "next_after_id": None},
    ],
)
def test_inconsistent_or_malformed_page_is_not_printed(payload: dict[str, object]) -> None:
    with pytest.raises(trade_cli.ClientError, match="malformed or inconsistent"):
        run_pages(
            [payload],
            [
                "--limit",
                "2",
                "--after-id",
                "0",
                "--symbol",
                "SYN.A",
                "--executed-from",
                "2025-01-01T00:00:00Z",
                "--executed-before",
                "2025-01-03T00:00:00Z",
            ],
        )


@pytest.mark.parametrize(
    "failure", ["connection", "timeout", "http", "redirect", "json", "media", "repeat"]
)
def test_main_failure_is_safe_and_previous_output_is_partial(
    failure: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    requests: list[httpx.Request] = []
    real_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=page(["A"], "A"))
        if failure == "connection":
            raise httpx.ConnectError("password=secret", request=request)
        if failure == "timeout":
            raise httpx.ReadTimeout("password=secret", request=request)
        if failure in {"http", "redirect"}:
            return httpx.Response(
                503 if failure == "http" else 307,
                text="secret SQL",
                headers={"Location": "https://example.com/secret"},
            )
        if failure == "json":
            return httpx.Response(
                200, content=b"secret SQL", headers={"Content-Type": "application/json"}
            )
        if failure == "media":
            return httpx.Response(200, text="secret SQL")
        return httpx.Response(200, json=page(["A"], "A"))

    def factory(**kwargs: object) -> httpx.Client:
        assert kwargs == {
            "base_url": "http://127.0.0.1:8123",
            "timeout": 10.0,
            "follow_redirects": False,
            "trust_env": False,
        }
        return real_client(transport=httpx.MockTransport(handler), **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(trade_cli.httpx, "Client", factory)
    assert trade_cli.main(["--port", "8123", "--limit", "1", "--max-pages", "3"]) == 1
    captured = capsys.readouterr()
    assert [json.loads(line) for line in captured.out.splitlines()] == [page(["A"], "A")]
    assert captured.err.startswith("trade-cli: ")
    assert "secret" not in captured.err
    assert "Traceback" not in captured.err
    assert len(requests) == 2


def test_module_invocation_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "marketlab.trade_cli", "--help"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0
    assert "--max-pages" in result.stdout
    assert result.stderr == ""


@pytest.mark.integration
@pytest.mark.parametrize("between_pages", [False, True])
def test_postgres_cli_combined_filter_traversal(
    trade_engine: Engine, tmp_path: Path, between_pages: bool
) -> None:
    app = create_app(Settings(storage_path=tmp_path, _env_file=None))
    app.state.trade_engine = trade_engine
    with TestClient(app) as client:
        # TestClient lifespan installs its own engine; retain the private-schema fixture.
        app.state.trade_engine = trade_engine
        records = [
            record("A", executed_at="2025-01-02T23:59:59.999999Z"),
            record("Z"),
            record("A-", symbol="SYN.B"),
            record("a"),
            record("A.", executed_at="2025-01-01T23:59:59.999999Z"),
            record("A:", executed_at="2025-01-03T00:00:00Z"),
        ]
        assert client.post("/trades/import/json", json=records).json() == {"imported": 6}

        class ImportBetweenPages(io.StringIO):
            def __init__(self, import_records: Callable[[], None]) -> None:
                super().__init__()
                self.import_records = import_records
                self.printed = 0

            def flush(self) -> None:
                self.printed += 1
                if self.printed == 1 and between_pages:
                    self.import_records()

        def import_records() -> None:
            added = [
                record("0"),
                record("B"),
                record("C", symbol="SYN.B"),
                record("D", executed_at="2025-01-01T23:59:59.999999Z"),
                record("E", executed_at="2025-01-03T00:00:00Z"),
            ]
            assert client.post("/trades/import/json", json=added).json() == {"imported": 5}

        output = ImportBetweenPages(import_records)
        trade_cli.browse(
            client,
            trade_cli.parse_args(
                [
                    "--limit",
                    "1",
                    "--after-id",
                    "00",
                    "--symbol",
                    "SYN.A",
                    "--executed-from",
                    "2025-01-02T05:30:00+05:30",
                    "--executed-before",
                    "2025-01-02T19:00:00-05:00",
                    "--max-pages",
                    "10",
                ]
            ),
            output,
        )
        pages = [json.loads(line) for line in output.getvalue().splitlines()]
        assert [item["trade_id"] for chunk in pages for item in chunk["items"]] == (
            ["A", "B", "Z", "a"] if between_pages else ["A", "Z", "a"]
        )
        assert pages[-1]["next_after_id"] is None
        for chunk in pages:
            assert chunk["items"][0]["price"] == "999999999999.99999999"
            assert chunk["items"][0]["quantity"] == "0.00000001"
            assert chunk["items"][0]["executed_at"].endswith("Z")
