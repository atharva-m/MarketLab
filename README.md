# MarketLab

Week 2 adds an in-memory trade contract, deterministic synthetic fixtures and JSON/CSV
parser validation, running Python 3.13. The week 1 foundation includes an app factory,
health probes, request observability, an empty migration baseline and local infrastructure.
Ingestion, market domain database tables, jobs, analytical queries, caching behavior and UI come later.

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
generation. Database connections also have a five-second driver timeout (configurable through
`MARKETLAB_DATABASE_CONNECT_TIMEOUT_SECONDS`), including migrations and integration tests.
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

`alembic upgrade head` installs the empty `0001_baseline`; only Alembic's bookkeeping table is
created. Compose waits for PostgreSQL, runs this migration and then starts the API. CI syncs
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
a disposable database containing only the empty baseline. They skip when `MARKETLAB_DATABASE_URL`
is absent; a skip is not an integration pass.
