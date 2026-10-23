"""Browse local trade pages: python -m marketlab.trade_cli --help."""

import argparse
import json
import re
import sys
from collections.abc import Sequence
from typing import Any, Never, TextIO

import httpx
from pydantic import ValidationError

from marketlab.trades.schemas import (
    SYMBOL_PATTERN,
    TRADE_ID_PATTERN,
    TradePage,
    normalize_timestamp,
)

REQUEST_TIMEOUT_SECONDS = 10.0


class ClientError(Exception):
    """A safe diagnostic that never contains response bodies or request values."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        # argparse's default messages echo arbitrary user values to stderr.
        self.exit(2, "trade-cli: invalid command-line arguments; use --help\n")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = _Parser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000, help="local API port (default: 8000)")
    parser.add_argument("--limit", type=int, default=100, help="page size, 1-500 (default: 100)")
    parser.add_argument("--after-id", help="exclusive trade-ID boundary")
    parser.add_argument("--symbol", help="exact symbol, without normalization")
    parser.add_argument("--executed-from", help="inclusive timestamp with seconds and timezone")
    parser.add_argument("--executed-before", help="exclusive timestamp with seconds and timezone")
    parser.add_argument("--max-pages", type=int, default=1, help="positive page cap (default: 1)")
    args = parser.parse_args(argv)
    if not (1 <= args.port <= 65535 and 1 <= args.limit <= 500 and args.max_pages > 0):
        parser.error("invalid bounds")
    for value, pattern in [(args.after_id, TRADE_ID_PATTERN), (args.symbol, SYMBOL_PATTERN)]:
        if value is not None and re.fullmatch(pattern, value) is None:
            parser.error("invalid filter")
    try:
        lower = normalize_timestamp(args.executed_from) if args.executed_from is not None else None
        upper = (
            normalize_timestamp(args.executed_before) if args.executed_before is not None else None
        )
        if lower is not None and upper is not None and lower >= upper:
            raise ValueError("invalid time range")
    except ValueError:
        parser.error("invalid timestamp bounds")
    return args


def _validated_page(response: httpx.Response, params: dict[str, str | int]) -> dict[str, Any]:
    """Validate the existing wire contract and pagination without changing serialization."""
    try:
        if response.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
            raise ValueError("expected JSON")
        page = TradePage.model_validate_json(response.content)
        payload: dict[str, Any] = response.json()
        if len(page.items) > int(params["limit"]):
            raise ValueError("oversized page")
        previous = str(params["after_id"]) if "after_id" in params else None
        for trade, raw in zip(page.items, payload["items"], strict=True):
            if not all(isinstance(raw[name], str) for name in type(trade).model_fields):
                raise ValueError("invalid wire types")
            timestamp = raw["executed_at"]
            # Trade validation normalizes offsets; the wire response itself must already be UTC.
            if not (timestamp.endswith("Z") or timestamp.endswith("+00:00")):
                raise ValueError("non-UTC response")
            if previous is not None and trade.trade_id <= previous:
                raise ValueError("non-progressing IDs")
            if "symbol" in params and trade.symbol != params["symbol"]:
                raise ValueError("inconsistent symbol")
            if "executed_from" in params and trade.executed_at < normalize_timestamp(
                params["executed_from"]
            ):
                raise ValueError("inconsistent lower bound")
            if "executed_before" in params and trade.executed_at >= normalize_timestamp(
                params["executed_before"]
            ):
                raise ValueError("inconsistent upper bound")
            previous = trade.trade_id
        if page.next_after_id is not None and (
            not page.items
            or len(page.items) != int(params["limit"])
            or page.next_after_id != page.items[-1].trade_id
        ):
            raise ValueError("inconsistent cursor")
        return payload
    except (ValueError, TypeError, KeyError, ValidationError) as error:
        raise ClientError("malformed or inconsistent trade page") from error


def browse(client: httpx.Client, args: argparse.Namespace, output: TextIO) -> None:
    """Print complete validated pages, retaining filters and changing only the ID boundary."""
    params: dict[str, str | int] = {"limit": args.limit}
    for name in ("after_id", "symbol", "executed_from", "executed_before"):
        value = getattr(args, name)
        if value is not None:
            params[name] = value
    for _ in range(args.max_pages):
        try:
            response = client.get("/trades", params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        except httpx.RequestError as error:
            raise ClientError(
                "could not read the local API (connection or timeout failure)"
            ) from error
        if response.status_code != 200:
            raise ClientError(f"local API returned HTTP {response.status_code}")
        payload = _validated_page(response, params)
        print(json.dumps(payload, separators=(",", ":")), file=output, flush=True)
        if payload["next_after_id"] is None:
            return
        params["after_id"] = payload["next_after_id"]


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{args.port}",
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            browse(client, args, sys.stdout)
    except ClientError as error:
        print(f"trade-cli: {error}", file=sys.stderr)
        return 1
    except OSError:
        print("trade-cli: could not write output", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
