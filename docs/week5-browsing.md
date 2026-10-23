# Week 5: bounded synthetic trade browsing

`GET /trades` lists the unchanged five-field synthetic trade contract from the existing
PostgreSQL store. Week 4 JSON/CSV imports and exact-ID lookup retain their behavior.
This milestone adds no migration or dependency changes and keeps local-only deployment.

## Request and response

| Query parameter | Behavior |
| --- | --- |
| `limit` | Integer page size, default `100`, inclusive range `1`–`500` |
| `after_id` | Optional exclusive ID boundary; need not identify an existing record |

An `after_id` must match the existing trade-ID contract: 1–64 ASCII characters, beginning
with a letter or digit, followed by letters, digits, `.`, `_`, `:`, or `-`.
Empty, overlong, whitespace-containing and non-ASCII boundaries return `422`.
Omit `after_id` to start at the beginning. IDs are never normalized or case-folded.

The service explicitly applies PostgreSQL `C` collation to both `ORDER BY trade_id` and
the `trade_id > after_id` comparison. For these ASCII IDs this is character-code order:
digits precede uppercase letters, uppercase precedes lowercase, and punctuation follows
its ASCII value. For example, `A`, `A-`, `A.`, `A:`, `A_`, `Z`, `a` is ascending.

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/trades'
Invoke-RestMethod 'http://127.0.0.1:8000/trades?limit=2&after_id=SYN-001'

$page = Invoke-RestMethod 'http://127.0.0.1:8000/trades?limit=2'
$page.items
while ($null -ne $page.next_after_id) {
    $boundary = [Uri]::EscapeDataString($page.next_after_id)
    $page = Invoke-RestMethod "http://127.0.0.1:8000/trades?limit=2&after_id=$boundary"
    $page.items
}
```

Example response when further records follow the visible page:

```json
{
  "items": [
    {
      "trade_id": "SYN-002",
      "symbol": "SYN.A",
      "executed_at": "2025-01-03T05:29:59.123456Z",
      "price": "999999999999.99999999",
      "quantity": "0.00000001"
    }
  ],
  "next_after_id": "SYN-002"
}
```

The service fetches at most `limit + 1` records, returns at most `limit` items, and uses
the additional record only to determine whether another page exists. If there is another
page, `next_after_id` is the last **returned** ID. Pass it as the next request's `after_id`.
An exactly full final page has `next_after_id: null`. No records, including a boundary
past the last ID, returns `200 {"items": [], "next_after_id": null}`.

Decimal values remain plain strings without exponent notation. Stored eight-place decimal
scale may add trailing zeros; original scale and timezone offset are not stored. Timestamps
are UTC, including supported year 1 and year 9999 boundaries under other session timezones.

Each request reads current committed data. Pagination does not provide a snapshot across
requests: a trade imported after one page can appear on a later page if its ID is beyond
the boundary; a newly imported ID before or at that boundary will not appear in that traversal.
This endpoint exposes no total count, filters or analytical operations.

## Errors, OpenAPI and Python service

| Status | Condition |
| --- | --- |
| `200` | Successful page, including an empty result |
| `422` | Invalid pagination parameter; the service does not access PostgreSQL |
| `503` | Database failure, with `{"detail": "Trade database unavailable"}` |

Validation errors use FastAPI's structured `detail` array. Database responses exclude SQL,
connection URLs and credentials. Request IDs, route metrics and the existing generic
unexpected-error handler remain in effect. `/docs` and `/openapi.json` describe query
constraints, page fields, errors, ordering and current-data semantics.

The synchronous `marketlab.trades.list_trades(engine, limit=100, after_id=None)` service
returns a `TradePage` containing a tuple of canonical `Trade` objects and `next_after_id`.
Direct calls reject invalid page sizes and boundaries with `ValueError` before connecting.
The HTTP route runs this service in the framework's worker pool.

## Verification setup

Use Python 3.13 and the existing locked `.venv`:

```powershell
.\scripts\check.ps1
$env:MARKETLAB_DATABASE_URL = 'postgresql+psycopg://USER:PASSWORD@127.0.0.1:PORT/DISPOSABLE_DB'
.\.venv\Scripts\uv.exe run --locked alembic upgrade head
.\scripts\check.ps1 -Integration
```

Use a disposable database. Tests clone the migrated `public.trades` table into unique
temporary schemas and remove those schemas afterward; they do not truncate shared data.
The explicit `MARKETLAB_DATABASE_URL` environment variable enables integration tests;
the `.env` default alone does not enable them. A skipped integration test is not a pass.
See [the verification record](week5-verification.md) for actual results and remaining limits.
