# MarketLab

Week 7 adds optional execution-time bounds to week 6 exact-symbol filtering on the bounded,
read-only synthetic trade browsing from week 5.
The week 4 HTTP imports and exact-ID retrieval build on week 3 transactional PostgreSQL persistence
and the week 2 contract on Python 3.13.
The week 1 foundation includes an app factory, health probes, request observability and local
infrastructure. External ingestion, jobs, analytical queries, caching behavior
and UI come later.

## Synthetic trade contract

The canonical execution fields and strict parser behavior are documented in
[the week 2 contract](docs/week2-trades.md). All checked-in trade samples are synthetic.
No service is required to validate or parse a batch:

```python
import json
from marketlab.trades import parse_trades_json, synthetic_trades

trades = synthetic_trades(3, seed=42)
payload = json.dumps([trade.model_dump(mode="json") for trade in trades])
assert parse_trades_json(payload) == trades
```

Run `.\scripts\check.ps1` for the existing quality checks and all unit tests, including
trade parser, validation, fixture and property tests.

## Transactional synthetic trade persistence

[The week 3 service contract](docs/week3-persistence.md) documents the migration and Python API.
After `alembic upgrade head`, imports validate the complete in-memory batch through the existing
parsers and commit it in one transaction. A conflicting stored ID rejects the whole batch.
Exact-ID retrieval returns a `Trade` or `None`; empty imports return zero without connecting.
All examples and tests use synthetic inputs.

## Synthetic trade HTTP interface

[The week 4 HTTP contract](docs/week4-http.md) documents raw JSON/CSV requests, exact-ID lookup,
error responses and verification. `POST /trades/import/json` accepts an `application/json` array;
`POST /trades/import/csv` accepts `text/csv`. Each import is atomic and accepts at most **1 MiB
(1,048,576 bytes)**, counted from the actual streamed body. Success returns `{"imported": N}`.
`GET /trades/{trade_id}` returns one trade with exact decimal strings and a UTC timestamp.

[The week 5 browsing contract](docs/week5-browsing.md) documents `GET /trades?limit=100&after_id=SYN-001`.
It returns `{"items": [...], "next_after_id": "..."}` in ascending, case-sensitive PostgreSQL `C`
order. The default page size is 100, with a range of 1–500; the cursor is an exclusive ID boundary
and is `null` at the end. Each page reads current committed data. See
[week 5 verification](docs/week5-verification.md) for checks and limitations.

[The week 6 filtering contract](docs/week6-filtering.md) adds the optional exact `symbol` parameter:
`GET /trades?symbol=SYN.A&limit=25`. The filter follows the existing symbol syntax without
normalization or partial matching and applies before pagination. Retain the same symbol across
pages; omitting it preserves unfiltered browsing. See [week 6 verification](docs/week6-verification.md)
for actual checks and limitations.

[The week 7 time-filtering contract](docs/week7-time-filtering.md) adds optional inclusive
`executed_from` and exclusive `executed_before`, separately or as `[from, before)`. For example:
`GET /trades?symbol=SYN.A&executed_from=2025-01-01T00:00:00Z&executed_before=2025-02-01T00:00:00Z&limit=25`.
Bounds reuse the strict trade timestamp syntax (seconds and timezone required, at most six
fractional digits), normalize to UTC and combine with symbol and ID boundaries before pagination.
Retain all filters across pages. Results stay in ID order, and each page reads current committed
data without a cross-page snapshot. Invalid bounds or `from >= before` return `422` before database
access; database failures retain the generic `503`. Omitting time bounds preserves week 6 behavior.
See [week 7 verification](docs/week7-verification.md) for actual checks and limitations.

## Windows quick start

Install Python 3.13 with the Windows `py` launcher and start Docker Desktop with Linux containers.
From the repository root, run:

```powershell
.\scripts\bootstrap.ps1 -Start
```

The script creates `.venv`, installs uv 0.13.5 if needed, copies `.env.example` to `.env` if absent,
syncs the locked dependencies, builds the image, starts Compose and verifies the API. It leaves
an existing `.env` intact. Docker Compose v2 with `--wait` support is required.

```powershell
.\scripts\check.ps1
$env:MARKETLAB_DATABASE_URL = 'postgresql+psycopg://marketlab:marketlab@127.0.0.1:5432/marketlab'
.\scripts\check.ps1 -Integration
```

The check script gives each pytest run a fresh directory under ignored `artifacts/pytest`, avoiding
collisions and Windows permissions on shared system temporary folders.
Host service URLs use `127.0.0.1` because published Compose ports bind to IPv4; `localhost` may
resolve to IPv6 first. Existing `.env` files should use the same host addresses.

For a host API process, start only infrastructure and migrate before serving:

```powershell
docker compose up -d --wait postgres redis
.\.venv\Scripts\uv.exe run --locked alembic upgrade head
.\.venv\Scripts\uv.exe run --locked uvicorn marketlab.app:create_app --factory --reload --loop asyncio:SelectorEventLoop --no-access-log
```

Stop the Compose API first if running the host API on the same port. Published API, PostgreSQL and
Redis ports bind to `127.0.0.1`. `.env.example` documents all settings. Change `API_PORT`,
`POSTGRES_PORT` or `REDIS_PORT` for Compose port conflicts, and update corresponding host URLs.
`POSTGRES_PASSWORD` controls the Compose database password; update `MARKETLAB_DATABASE_URL` for
host tools when changing it. Password characters embedded in database URLs must be URL encoded.
Alternatively set `MARKETLAB_DATABASE_PASSWORD` separately as a literal password; it overrides the
URL password safely. Compose uses this separate setting automatically. PostgreSQL
initial credentials apply only when creating its volume. Keep `.env` and local data uncommitted.

## Health and observability

| Endpoint | Contract |
| --- | --- |
| `/health/live` | 200 while the API process can answer; no dependency calls |
| `/health/ready` | 200 ready/degraded; 503 when PostgreSQL or storage fails |
| `/health/dependencies` | Same status contract, detailed required/optional checks |
| `/metrics` | Prometheus HTTP counts and duration histogram |
| `/docs` | OpenAPI documentation |

PostgreSQL uses `SELECT 1`. Storage writes, flushes, reads back and removes a temporary probe file.
Redis and Ollama are optional: an outage reports `degraded` and preserves readiness. Checks run
concurrently with a timeout per dependency. Ollama checks `/api/tags`, with no model download or
generation. The Linux container explicitly runs Uvicorn with `--loop asyncio`: the locked uvloop
runtime can leave a DNS future unobserved when a dependency timeout cancels a connection before
name resolution fails. The standard loop handles this cancellation without changing the health
responses or timeouts. Keep the explicit `asyncio:SelectorEventLoop` in the Windows launch command
for psycopg compatibility. Database connections also have a five-second driver timeout (configurable
through `MARKETLAB_DATABASE_CONNECT_TIMEOUT_SECONDS`), including migrations and integration tests.
PostgreSQL and API data use named volumes; Redis is an expendable cache configured
with 256 MiB, `allkeys-lru`, no snapshots and no append-only file.

Each completed request produces a JSON log with timestamp, method, path, response status,
duration and request ID. `X-Request-ID` is preserved for 1–128 ASCII letters, digits, `.`, `_`, `-`;
otherwise the API generates a new ID. Responses include that ID. Query parameters, request bodies
and connection credentials are excluded from request logs. Metrics use route templates to avoid
labels for each unknown URL. Run Uvicorn with `--no-access-log` to avoid duplicate plaintext logs.

## Ollama compatibility smoke

Ollama runs on the host. Containers use `http://host.docker.internal:11434`, overridable with
`OLLAMA_HOST_URL`; host tools use `http://127.0.0.1:11434`. The host service must be reachable from
Docker for that optional dependency to report up. Model installation is a separate explicit step:

```powershell
ollama pull qwen3.5:4b-q8_0
.\.venv\Scripts\uv.exe run --locked python scripts/ollama_smoke.py --output artifacts/ollama-smoke.json
```

The smoke script never pulls or updates models. It checks the server version and installed model,
requests a JSON schema constrained completion and validates it with Pydantic. The record includes
model digest, quantization, file size, wall latency, generation timing and available loaded model
memory/VRAM information from `/api/ps`, plus available/total physical RAM snapshots on Windows.
Missing memory fields are `null`; model allocations and host snapshots do not measure peak memory.
Failures produce a JSON record and nonzero
exit code. `--model`, `--url` and `--timeout` override defaults. First load may be slow.

## Migrations and CI

`alembic upgrade head` applies `0001_baseline` and `0002_trades`, creating Alembic's bookkeeping
table and the five-field `trades` table. Compose waits for PostgreSQL, runs migrations and then
starts the API. CI syncs
`uv.lock` with `--locked`, runs lint, formatting, strict source type checks and unit tests on Windows
and Linux, validates Compose, builds the image, applies migrations, tests real PostgreSQL and
smokes the deployed API. It also stops Redis and verifies degraded readiness. Ollama generation
is a local hardware compatibility check and is not required in hosted CI.

```powershell
docker compose logs --tail 100 api migrate postgres redis
docker compose down
```

`docker compose down` preserves persistent volumes. Removing volumes deletes local database and
storage contents; do so only when intentionally resetting the environment. Integration tests require
a disposable database migrated to `0002_trades`. Persistence tests clone the migrated trade
table into temporary schemas and remove those schemas afterward. Week 4 HTTP integration tests
and week 5–7 browsing/filtering tests use the same isolation and real PostgreSQL service. They skip when
`MARKETLAB_DATABASE_URL` is absent; a skip is not an integration pass. Apply migrations to the
disposable database before running `scripts/check.ps1 -Integration`.
