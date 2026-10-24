# Week 9 exact-ID CLI lookup

Week 9 adds `--trade-id ID` to the existing local read-only CLI. Start and migrate
an API as described in README, then use Python 3.13 with locked dependencies:

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.trade_cli --trade-id SYN-001
.\.venv\Scripts\uv.exe run --locked python -m marketlab.trade_cli --port 8010 --trade-id SYN-001
```

Lookup sends exactly one `GET /trades/SYN-001` request and prints the existing
five-field trade object on one stdout line. Example synthetic response:

```json
{"trade_id":"SYN-001","symbol":"SYN.A","executed_at":"2025-01-02T00:00:00.123456Z","price":"1.23000000","quantity":"0.00000001"}
```

The JSON is compact; decimal and UTC timestamp string values retain their wire
representation, including trailing decimal zeros. Lookup returns an object;
browsing continues to return page envelopes as described in the
[week 8 contract](week8-cli.md).

## Arguments and validation

`--trade-id` follows the existing ID syntax: 1–64 ASCII characters, starting with
an ASCII letter or digit, followed by ASCII letters, digits, `.`, `_`, `:` or `-`.
Matching is exact and case-sensitive, without trimming or normalization.
`--port` remains an integer from 1–65535, default 8000. The CLI does not read `.env`;
set the port to the local API's configured `API_PORT` or host Uvicorn port.

Lookup rejects explicitly supplied `--limit`, `--after-id`, `--symbol`,
`--executed-from`, `--executed-before` and `--max-pages`. This includes options
that equal browsing defaults. For example, this fails before HTTP access:

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.trade_cli --trade-id SYN-001 --limit 100
```

Invalid IDs, ports and incompatible options exit 2 with the existing safe argument
diagnostic. `--help` exits 0 without contacting the API. Omitting `--trade-id`
preserves browsing defaults, filters, bounded traversal and resume cursors.

## Responses and failures

Lookup requires HTTP 200, `application/json`, exactly the existing five fields,
valid trade values with string wire types, a UTC timestamp and a returned ID
identical to the requested ID. A different ID, including a case difference, is
an inconsistent response. Validation completes before anything is printed.

Exit 0 means lookup succeeded. Missing IDs (HTTP 404), other HTTP statuses,
connection or timeout failures, and malformed or inconsistent responses exit 1,
with no stdout and a safe diagnostic on stderr. Diagnostics exclude request
values, response bodies, SQL and connection details. A missing ID reports:

```text
trade-cli: local API returned HTTP 404
```

The client uses IPv4 loopback at `http://127.0.0.1:PORT`, disables environment
proxies and redirects, makes no automatic retry, and retains ten-second connect,
read, write and pool timeouts. These are operation inactivity timeouts, not a
whole-command wall-clock cap. Output-write failures also exit 1; a failing output
sink may already have received bytes before reporting a write error.

Browsing still may print earlier valid pages before a later failure. Its output
is partial on failure; inspect the exit status and retain all filters when
resuming from the last successful envelope. Pages read current committed data,
with no cross-page snapshot or large-dataset query-performance guarantee.

No API, OpenAPI, database, dependency, lockfile or deployment contract changes.
See [actual verification results](week9-verification.md).
