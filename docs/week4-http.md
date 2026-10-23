# Week 4: synthetic trade HTTP interface

This milestone exposes the unchanged [week 2 contract](week2-trades.md) through the
[week 3 PostgreSQL service](week3-persistence.md). It uses the same schema, parsers and
transaction boundaries, with no migration or dependency changes. Run locally with the
existing loopback-bound Compose stack or the README's host API command.

## Requests and responses

| Endpoint | Request | Success |
| --- | --- | --- |
| `POST /trades/import/json` | Raw UTF-8 JSON array; `Content-Type: application/json` | `200 {"imported": N}` |
| `POST /trades/import/csv` | Raw UTF-8 CSV with all five canonical headers; `Content-Type: text/csv` | `200 {"imported": N}` |
| `GET /trades/{trade_id}` | Exact, case-sensitive ID in the path | `200` with the five canonical trade fields |

Each import is limited to **1 MiB = 1,048,576 bytes**. The adapter counts actual streamed
bytes, including whitespace and CSV headers, so absent or incorrect `Content-Length` and
chunked bodies cannot bypass the limit. A body exactly at the limit proceeds to normal
parser validation. Both formats require UTF-8; media-type matching ignores case and allows
parameters such as `charset=utf-8`. Content is always decoded as UTF-8.

JSON decimal fields must be strings. The entire batch passes through its existing parser
before opening a PostgreSQL connection. Valid empty JSON arrays and header-only CSV return
zero without database access, even if PostgreSQL is unavailable. A nonempty import owns one
transaction and never overwrites existing trades. The synchronous service runs in worker
threads. The app creates a lazy dedicated synchronous engine at startup and disposes its
pool at shutdown; the existing asynchronous health engine retains its lifecycle.

Retrieval returns decimal strings without exponent notation and timestamps in UTC, for example:

```json
{
  "trade_id": "SYN-HTTP-1",
  "symbol": "SYN.A",
  "executed_at": "2025-01-03T05:29:59.123456Z",
  "price": "999999999999.99999999",
  "quantity": "0.00000001"
}
```

PostgreSQL's eight-place decimal scale preserves exact numeric values, but may add trailing
zeros. Original trailing-zero counts and input timezone offsets are not stored. Lookup does
not normalize or case-fold IDs. A path ID which is not present, including one that could
never pass the trade contract, returns `404`; no separate path-ID validation is added.

## Synthetic examples

These PowerShell examples target the local API. Run each nonempty import once or change its
ID before repeating; stored IDs intentionally conflict. Requests contain raw data, with no
multipart encoding or file-upload endpoint.

```powershell
$json = @'
[{"trade_id":"SYN-HTTP-1","symbol":"SYN.A","executed_at":"2025-01-02T23:59:59.123456-05:30","price":"999999999999.99999999","quantity":"0.00000001"}]
'@
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/trades/import/json -ContentType 'application/json; charset=utf-8' -Body $json

$csv = @'
trade_id,symbol,executed_at,price,quantity
SYN-HTTP-2,SYN.B,2025-01-03T05:29:59.123456Z,1.25,2
'@
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/trades/import/csv -ContentType 'text/csv; charset=utf-8' -Body $csv

Invoke-RestMethod http://127.0.0.1:8000/trades/SYN-HTTP-1
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/trades/import/json -ContentType 'application/json' -Body '[]'
```

The import responses are `{"imported":1}`, `{"imported":1}` and `{"imported":0}`.
Adjust the port when the local API uses a configured nondefault port. `/docs` and
`/openapi.json` describe both raw request body formats and the retrieval response.

## Errors

Errors use `{"detail": "..."}` and retain the existing `X-Request-ID` and route metrics.

| HTTP status | Condition |
| --- | --- |
| `404` | No trade with that exact ID |
| `409` | At least one batch ID is already stored; entire transaction rolls back |
| `413` | Actual import body exceeds 1 MiB; parsing and persistence do not run |
| `415` | Missing or unsupported Content-Type for that import endpoint |
| `422` | Malformed JSON/CSV or UTF-8, invalid records, or duplicate IDs within the batch |
| `503` | SQLAlchemy database operation fails; response is `Trade database unavailable` |

Invalid and conflicting batches commit zero records. An empty body is invalid; use `[]`
for JSON or the canonical CSV header for an empty batch. Unsupported media types are
rejected before reading the body. Oversized supported bodies are rejected before decoding
or parsing. Parser errors may include the one-based invalid record number. Responses never
include SQL, connection URLs or database credentials. Unexpected errors retain the existing
generic `500 Internal server error` contract. Existing request logs omit bodies and queries.

## Verification and boundaries

Use the locked Python 3.13 `.venv`. Run `.\scripts\check.ps1` for lint, formatting,
strict source typing and offline tests. For real database coverage, set
`MARKETLAB_DATABASE_URL` to a **disposable** PostgreSQL instance, migrate it with
`.\.venv\Scripts\uv.exe run --locked alembic upgrade head`, then run
`.\scripts\check.ps1 -Integration`. Tests require the explicit environment variable;
the settings `.env` default alone does not enable integration. A skipped integration
test is not a pass. The existing separate Ollama smoke remains unchanged.

HTTP unit coverage includes malformed input, invalid and duplicate records without database
access, empty imports, missing/case-sensitive IDs, decimal/time serialization, content types,
size boundaries, absent and incorrect Content-Length, chunked bodies, worker-thread execution,
engine shutdown, OpenAPI and redacted database failures with request IDs and metrics.
PostgreSQL HTTP tests clone the actual migrated table into unique temporary schemas, exercise
both formats through the real service, and remove those schemas afterward. They verify exact
decimal/UTC round trips, invalid batch isolation, stored-ID conflicts in all three positions,
cross-format conflicts, complete rollback and successful use after a rejected batch.

Scope excludes uploads, external providers, listing, filtering, analytics, updates/deletes,
background jobs, cache behavior, frontend and authentication changes. Existing local-only
hosting, health, observability, infrastructure and CI behavior remain in place.
