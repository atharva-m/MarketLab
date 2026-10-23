# Week 3: transactional synthetic trade persistence

The approved milestone stores synthetic in-memory batches using the unchanged
[week 2 contract](week2-trades.md). The pure parsers and fixtures retain their existing behavior.

## Migration and storage

Run `alembic upgrade head` in the locked Python 3.13 project environment. Revision
`0002_trades` follows the unchanged empty `0001_baseline` and creates `trades` with exactly
five non-null fields: `trade_id VARCHAR(64)` as its primary key, `symbol VARCHAR(20)`,
`executed_at TIMESTAMP WITH TIME ZONE`, and `price`/`quantity NUMERIC(20,8)`.
Decimals retain their exact numeric value across the full contract range; storage uses eight
fractional places, so the original number of trailing zeros is not preserved. PostgreSQL stores
the timestamp instant; retrieval selects it under transaction-local UTC before driver decoding,
preserving microseconds and the full year 1 through 9999 contract range. The caller's pooled
session timezone is restored when the read transaction ends. The original
input timezone offset is not stored. Validation remains in the existing parsers and schema;
write through the service to enforce the complete week 2 contract.

`alembic downgrade 0001_baseline` drops the trade table and its contents. It is a destructive
reset intended only for disposable environments. Upgrading an existing week 2 database adds
the trade table while retaining the baseline and infrastructure.

## Python API

```python
import json
from sqlalchemy import create_engine
from marketlab.config import Settings
from marketlab.trades import get_trade, import_trades_csv, import_trades_json, synthetic_trades

settings = Settings()
engine = create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
try:
    batch = synthetic_trades(3, seed=42)
    payload = json.dumps([trade.model_dump(mode="json") for trade in batch])
    assert import_trades_json(engine, payload) == 3
    assert get_trade(engine, batch[0].trade_id) == batch[0]
finally:
    engine.dispose()
```

`import_trades_json(engine, payload)` and `import_trades_csv(engine, payload)` accept a
SQLAlchemy synchronous PostgreSQL/psycopg `Engine` and text already in memory. They return the
number committed. Each call owns one database transaction. The entire batch is parsed and
validated before opening a connection. Empty JSON arrays and header-only valid CSV return zero
without contacting PostgreSQL. CSV headers and JSON fields use the existing canonical contract.

Malformed inputs, invalid records and duplicate IDs within the input raise the unchanged
`TradeParseError`. An ID already stored raises `DuplicateTradeError`; the primary key also
arbitrates concurrent imports without a separate existence query. Both failure paths commit no
records from the batch. An import never overwrites a stored trade, and failed imports leave
subsequent calls usable. Other database failures propagate after transaction rollback.
Repeated imports of the same fixture seed intentionally conflict because fixture IDs repeat.

`get_trade(engine, trade_id)` performs only exact, case-sensitive ID lookup and returns the
frozen `Trade`, normalized to UTC, or `None` when absent. It binds the ID as a SQL parameter.
No HTTP import routes, file readers, providers, listing, filters, analytics, jobs, cache behavior,
frontend, copilot or memos are added.

## Verification

Run `.\scripts\check.ps1` for Ruff, strict source mypy and offline tests. For real PostgreSQL,
set `MARKETLAB_DATABASE_URL` to a disposable instance, apply `alembic upgrade head` through
the project `.venv`, then run `.\scripts\check.ps1 -Integration`. Existing Compose migration
startup and CI apply the new revision automatically without infrastructure changes.

Integration tests verify the actual migration column types and primary key, then clone its
table definition into a unique test schema for each persistence case. Those schemas are removed
in fixture cleanup; public trade records are not changed. Cases cover both JSON and CSV,
maximum/minimum decimal boundaries, negative input offsets, microseconds, UTC retrieval with
a non-UTC database session, year 1/9999 boundaries without leaking session timezone changes,
missing/case-sensitive IDs, cross-batch conflicts at every position,
rollback, unchanged existing records, invalid/intra-batch duplicate inputs and empty imports.
Offline tests confirm invalid and empty batches never open database connections. PostgreSQL
tests skip when the explicit environment URL is absent; skipped integration is not a pass.
The existing Ollama compatibility smoke remains a separate, explicit local hardware check.
