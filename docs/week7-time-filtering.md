# Week 7: execution-time bounds

`GET /trades` adds optional execution-time bounds over the existing five-field synthetic trade
contract and PostgreSQL listing service. Omitting both preserves [week 6](week6-filtering.md).
The table, schema, indexes, dependencies and local deployment scope are unchanged.

## Parameters and validation

| Parameter | Behavior |
| --- | --- |
| `executed_from` | Optional inclusive execution-time lower bound |
| `executed_before` | Optional exclusive execution-time upper bound |
| `symbol` | Optional exact symbol, using the unchanged strict week 6 syntax |
| `after_id` | Optional exclusive trade-ID boundary; the ID need not exist |
| `limit` | Default `100`, inclusive range `1`–`500` |

Either time bound works alone. Together they define `[executed_from, executed_before)` and require
`executed_from < executed_before` after UTC normalization. An equal instant represented with
different offsets is still an invalid range. Syntax exactly reuses the trade timestamp validator:

- `YYYY-MM-DDTHH:MM:SS`, optionally followed by `.` and one to six fractional digits.
- Uppercase `T` and an explicit timezone: uppercase `Z` or numeric `+HH:MM` / `-HH:MM`.
- Valid calendar/time values, numeric offset hours `00`–`23` and minutes `00`–`59`.
- No trimming, lowercase separators, missing seconds/timezone, epoch numbers or excess precision.

Bounds normalize to UTC. Malformed timestamps, invalid dates and times, UTC overflow beyond Python's
year 1–9999 range and invalid ranges return `422` before database access. Encode a literal `+` in a
URL as `%2B`; an unencoded plus is decoded as a space by standard query-string handling. For example,
`2025-01-01T05:30:00%2B05:30` is equivalent to `2025-01-01T00:00:00Z`.

## Filtered traversal

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/trades?executed_from=2025-01-01T00:00:00Z&limit=25'
Invoke-RestMethod 'http://127.0.0.1:8000/trades?executed_before=2025-02-01T00:00:00Z&limit=25'
Invoke-RestMethod 'http://127.0.0.1:8000/trades?executed_from=2025-01-01T05:30:00%2B05:30&limit=25'

$symbol = [Uri]::EscapeDataString('SYN.A')
$from = [Uri]::EscapeDataString('2025-01-01T00:00:00Z')
$before = [Uri]::EscapeDataString('2025-02-01T00:00:00Z')
$query = "symbol=$symbol&executed_from=$from&executed_before=$before&limit=25"
$page = Invoke-RestMethod "http://127.0.0.1:8000/trades?$query"
$page.items
while ($null -ne $page.next_after_id) {
    $boundary = [Uri]::EscapeDataString($page.next_after_id)
    $page = Invoke-RestMethod "http://127.0.0.1:8000/trades?$query&after_id=$boundary"
    $page.items
}
```

The response remains `{"items": [...], "next_after_id": "..."}`. Decimal prices and quantities
remain plain strings; timestamps serialize in UTC. A successful selection with no matches returns
HTTP `200` with `{"items": [], "next_after_id": null}`.

SQL combines both optional time conditions, exact symbol equality and the exclusive ID boundary
before fetching at most `limit + 1` matching records. At most `limit` records are returned. The extra
matching record determines whether a next page exists; only matching records determine the cursor.
`next_after_id` is the final returned ID when another matching record exists, and `null` otherwise,
including an exactly full terminal page. Nonmatching records cannot shorten pages or create cursors.

Results remain ordered by ascending case-sensitive `trade_id` using explicit PostgreSQL `C`
collation for ordering and boundary comparison. They are **not ordered by execution time**.
The supplied ID boundary may belong to an excluded trade or identify no stored trade.

Clients must retain the same symbol and both time bounds across pages. The cursor contains only an
ID boundary and does not encode filters. Each request reads current committed data, without a
snapshot across requests. Newly committed matching IDs beyond the cursor can appear on a later
page; IDs at or before it are omitted from that traversal. Uncommitted imports remain invisible.
Bounded returned pages do not imply a large-dataset query-performance guarantee; no index was added.

## Errors, OpenAPI and service

| Status | Condition |
| --- | --- |
| `200` | Successful page, including no matches |
| `422` | Invalid pagination, symbol, timestamp or time range before database access |
| `503` | Database failure: `{"detail": "Trade database unavailable"}` |

Malformed parameter validation uses FastAPI's structured `detail` array. An invalid time range uses
`{"detail": "executed_from must be earlier than executed_before"}`. Database failures expose no
SQL, connection credentials or database details. Existing request IDs and metrics remain in effect.
`/docs` and `/openapi.json` describe the optional date-time parameters, strict syntax, inclusivity,
filter retention, ID ordering, response envelope and errors.

```python
list_trades(
    engine,
    limit=100,
    after_id=None,
    symbol="SYN.A",
    executed_from="2025-01-01T00:00:00Z",
    executed_before="2025-02-01T00:00:00Z",
)
```

Direct service calls accept strict timestamp strings or aware `datetime` values, normalize them to
UTC and reject invalid bounds/ranges with `ValueError` before connecting. The synchronous route
continues to execute in FastAPI's worker pool.

## Verification

Use Python 3.13 and the existing locked `.venv`:

```powershell
.\scripts\check.ps1
$env:MARKETLAB_DATABASE_URL = 'postgresql+psycopg://USER:PASSWORD@127.0.0.1:PORT/DISPOSABLE_DB'
.\.venv\Scripts\uv.exe run --locked alembic upgrade head
.\scripts\check.ps1 -Integration
```

Integration requires an explicitly configured disposable migrated PostgreSQL instance; a skip is
not a pass. Tests clone the migrated table into unique private schemas and remove them afterward.
See [actual week 7 verification](week7-verification.md) for results and limits.
