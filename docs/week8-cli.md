# Week 8 local trade browsing CLI

Run from the repository with Python 3.13 and locked project dependencies:

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.trade_cli --help
.\.venv\Scripts\uv.exe run --locked python -m marketlab.trade_cli
```

The second command requests one page from `http://127.0.0.1:8000/trades`, using
the existing default `limit=100`. Start and migrate the local API as described in
README first. No API, OpenAPI, persistence, dependency or deployment contract changes.

## Options

| Option | Behavior |
| --- | --- |
| `--port PORT` | Local API port, 1–65535; default 8000. Set this to your configured Compose `API_PORT` or host Uvicorn port. The CLI does not read `.env`. |
| `--limit N` | Records per page, 1–500; default 100. |
| `--after-id ID` | Exclusive ID boundary; need not identify a stored trade. |
| `--symbol SYMBOL` | Exact symbol with the existing case-sensitive syntax, without trimming or normalization. |
| `--executed-from TIMESTAMP` | Optional inclusive execution-time lower bound. |
| `--executed-before TIMESTAMP` | Optional exclusive execution-time upper bound. |
| `--max-pages N` | Positive integer page cap; default 1. |

ID/symbol syntax and timestamp validation follow the existing trade contract.
Timestamps require seconds and timezone, with at most six fractional digits and
a UTC-representable instant. Either time bound may be supplied alone. When both
are present, `from < before` is required after UTC normalization. Invalid options
fail before HTTP access. Input filters are sent without normalization; httpx URL
encoding preserves positive offsets such as `+05:30` as `%2B05%3A30`.

## Bounded traversal and resume

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.trade_cli --port 8010 --limit 1 --symbol SYN.A --executed-from '2025-01-02T05:30:00+05:30' --executed-before '2025-01-03T00:00:00Z' --max-pages 2
```

Example output for three matching synthetic IDs `A`, `Z` and `a`:

```json
{"items":[{"trade_id":"A","symbol":"SYN.A","executed_at":"2025-01-02T23:59:59.999999Z","price":"1.00000000","quantity":"2.00000000"}],"next_after_id":"A"}
{"items":[{"trade_id":"Z","symbol":"SYN.A","executed_at":"2025-01-02T00:00:00Z","price":"1.00000000","quantity":"2.00000000"}],"next_after_id":"Z"}
```

Resume with the final printed cursor and every original filter:

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.trade_cli --port 8010 --limit 1 --symbol SYN.A --executed-from '2025-01-02T05:30:00+05:30' --executed-before '2025-01-03T00:00:00Z' --after-id Z --max-pages 2
```

Within one invocation the client retains `limit`, symbol and time bounds and
changes only `after_id`. It prints each complete validated API envelope on one
stdout line, including the final cursor, preserving decimal and timestamp strings.
It stops at `next_after_id: null` or the page cap. Empty results print
`{"items":[],"next_after_id":null}` and succeed. An exactly full terminal page also
has a null cursor. Results follow ascending case-sensitive ID order under the
API's PostgreSQL `C` collation, even when timestamp order differs.

Each page reads currently committed data. An import committed between requests
can add a matching ID beyond the cursor to later pages; a newly imported ID
before the cursor is missed by that traversal. There is no cross-page snapshot.
Page and request-count bounds imply no large-dataset query-performance guarantee.

## Failures

Exit 0 means every requested page succeeded, including a cap reached before the
end. Exit 2 means invalid command-line arguments. Exit 1 means an HTTP, connection,
timeout, malformed/inconsistent response or output-write failure. Diagnostics go
to stderr and exclude request values, response bodies, SQL and connection details.
`--help` exits successfully without accessing the API.

HTTP status 200 and a valid JSON envelope are required. Redirects and other
statuses fail; requests never follow redirects. Requests target IPv4 loopback
on the selected port and do not use environment proxies. Each request uses
10-second connect, read, write and pool timeouts, with no automatic retry.
These are per-operation inactivity timeouts, not a whole-traversal wall-clock cap.

Before printing a page, the client checks the five-field wire contract, exact
decimal strings, UTC timestamps, page size, matching symbol/time filters,
strictly increasing IDs beyond the requested boundary and cursor consistency.
A non-null cursor must equal the last visible ID on a full page. Invalid or
non-progressing pages fail even when the page cap has been reached.

Earlier valid pages may already have printed if a later request fails. Output
is partial on failure; check the exit status before treating it as a successful
traversal. The failing page is not printed. The last successful envelope can
still provide a resume cursor with all original filters.
