# Week 6: exact-symbol trade filtering

`GET /trades` accepts an optional `symbol` parameter over the existing five-field synthetic trade
contract. Omitting it preserves week 5 unfiltered browsing. The route and listing service use the
existing PostgreSQL table without migrations, indexes or dependency changes. Deployment stays local.

## Request and response

| Query parameter | Behavior |
| --- | --- |
| `symbol` | Optional exact symbol: 1–20 ASCII characters, starting with `A`–`Z`, then `A`–`Z`, digits, `.` or `-` |
| `limit` | Integer page size, default `100`, inclusive range `1`–`500` |
| `after_id` | Optional exclusive trade-ID boundary; need not identify an existing record |

The symbol pattern is the same `^[A-Z][A-Z0-9.-]{0,19}$` used by `Trade`. There is no trimming,
case conversion, substring/prefix matching or symbol list support. For example, `SYN.A` matches
only `SYN.A`; `SYN.AA` and `XSYN.A` do not match. Empty strings, lowercase letters, whitespace,
non-ASCII characters and comma-separated symbols return `422` before database access. A valid
symbol absent from storage returns `200 {"items": [], "next_after_id": null}`.

The unchanged trade-ID syntax, explicit PostgreSQL `C` collation on ascending ordering and the
exclusive boundary comparison are described in [week 5 browsing](week5-browsing.md). The boundary
may be an ID belonging to another symbol or an ID that does not exist.

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/trades?symbol=SYN.A&limit=25'
Invoke-RestMethod 'http://127.0.0.1:8000/trades?symbol=SYN.A&limit=25&after_id=SYN-001'

$symbol = [Uri]::EscapeDataString('SYN.A')
$page = Invoke-RestMethod "http://127.0.0.1:8000/trades?symbol=$symbol&limit=25"
$page.items
while ($null -ne $page.next_after_id) {
    $boundary = [Uri]::EscapeDataString($page.next_after_id)
    $page = Invoke-RestMethod "http://127.0.0.1:8000/trades?symbol=$symbol&limit=25&after_id=$boundary"
    $page.items
}
```

Example response with another matching record beyond the page:

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

SQL applies exact symbol equality and the optional ID boundary before fetching at most `limit + 1`
matching rows. At most `limit` are returned. The extra matching row determines whether another page
exists. `next_after_id` is the final returned matching ID when another matching row exists, and
`null` otherwise, including an exactly full final page. Nonmatching rows cannot shorten a page or
cause a cursor. Decimal fields remain plain strings and timestamps remain UTC.

Clients must retain the same `symbol` across pages. The cursor is an ID boundary and does not
encode the filter. Changing the symbol starts a different selection at the supplied boundary.
Each request reads current committed data, with no snapshot across pages. Newly committed matching
IDs beyond the boundary can appear on later pages; new IDs before or at it are omitted from that
traversal. Uncommitted imports remain invisible. Returned pages are bounded; this milestone makes
no large-dataset query-performance guarantee and adds no index.

## Errors, OpenAPI and Python service

| Status | Condition |
| --- | --- |
| `200` | Successful filtered or unfiltered page, including no matches |
| `422` | Invalid symbol or pagination parameter, before database access |
| `503` | Database failure, with `{"detail": "Trade database unavailable"}` |

Validation uses FastAPI's structured `detail` array. Database failures expose no SQL, connection
URLs or credentials. Request IDs and route metrics remain in effect. `/docs` and `/openapi.json`
document symbol validation, parameters, response shape, ordering, pagination and error behavior.

`marketlab.trades.list_trades(engine, limit=100, after_id=None, symbol=None)` returns the existing
`TradePage`. Direct calls reject invalid symbols/page sizes/boundaries with `ValueError` before
connecting. The HTTP route continues to run the synchronous service in a worker pool.

## Verification

Use Python 3.13 and the existing locked `.venv`:

```powershell
.\scripts\check.ps1
$env:MARKETLAB_DATABASE_URL = 'postgresql+psycopg://USER:PASSWORD@127.0.0.1:PORT/DISPOSABLE_DB'
.\.venv\Scripts\uv.exe run --locked alembic upgrade head
.\scripts\check.ps1 -Integration
```

Use a disposable PostgreSQL database. Integration tests clone the migrated public trade table into
unique temporary schemas and remove those schemas afterward. An explicit database environment
variable enables integration; the `.env` default alone does not. A skipped test is not a pass.
See [week 6 verification](week6-verification.md) for actual results and limitations.
