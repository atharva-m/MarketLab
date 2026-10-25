# MarketLab

R1 restored the historical research roadmap with checksum-verified one-day Binance Spot
BTCUSDT ingestion, immutable Parquet publication and a separate PostgreSQL dataset catalog.
See [the approved recovery roadmap](ROADMAP.md), [R1 contract](docs/r1-datasets.md) and
[actual R1 verification](docs/r1-verification.md). Historical week labels below describe
repository increments, not completion of the original 14-week research schedule.
Week 9 adds exact-ID lookup to the local read-only command-line client.
Week 8 adds bounded, filtered trade browsing.
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

## Local trade browsing CLI

Use the existing project environment to print one JSON page envelope per line when browsing:

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.trade_cli --symbol SYN.A --limit 25
.\.venv\Scripts\uv.exe run --locked python -m marketlab.trade_cli --port 8000 --limit 25 --symbol SYN.A --executed-from '2025-01-01T00:00:00Z' --executed-before '2025-02-01T00:00:00Z' --max-pages 4
```

The client defaults to `http://127.0.0.1:8000` and one page. Set `--port` to your local API's
configured `API_PORT`; the CLI does not read `.env`. Explicit `--max-pages N` bounds traversal,
retaining every filter and changing only `after_id`. It stops at a null cursor or the cap;
the last printed cursor remains available to resume with `--after-id` and the same filters.
Decimal strings and UTC timestamps retain their wire values. Requests use finite timeouts.
Failures return a nonzero exit status and a safe stderr diagnostic. Output can contain earlier
pages when a later request fails, so treat it as partial unless the process succeeds. Each page
reads current committed data without a cross-page snapshot.

For one exact, case-sensitive ID, use `--trade-id`:

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.trade_cli --trade-id SYN-001
.\.venv\Scripts\uv.exe run --locked python -m marketlab.trade_cli --port 8010 --trade-id SYN-001
```

Lookup makes one request to the existing exact-ID endpoint and prints one five-field JSON
object, preserving decimal and UTC timestamp strings. It accepts `--port` but rejects every
explicit browsing option, including `--limit 100` and `--max-pages 1`. Invalid IDs fail before
HTTP access. Missing IDs and HTTP, connection, timeout or malformed-response failures return
nonzero with a safe stderr diagnostic and no stdout.

See [the week 8 browsing contract](docs/week8-cli.md),
[the week 9 lookup contract and examples](docs/week9-cli.md), and
[actual week 9 verification](docs/week9-verification.md). The HTTP/OpenAPI contracts are unchanged.

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

`alembic upgrade head` applies `0001_baseline`, `0002_trades`, R1 `0003_dataset_versions` and R2 `0004_ingestion_jobs`, creating the historical catalog and durable ingestion job tables as well as Alembic's bookkeeping
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
a disposable database migrated to `0004_ingestion_jobs`. Persistence tests clone the migrated trade
table into temporary schemas and remove those schemas afterward. Week 4 HTTP integration tests
and week 5–8 browsing/filtering/CLI tests use the same isolation and real PostgreSQL service. They skip when
`MARKETLAB_DATABASE_URL` is absent; a skip is not an integration pass. Apply migrations to the
disposable database before running `scripts/check.ps1 -Integration`.

## Historical dataset publication (R1)

Use a disposable/migrated PostgreSQL instance for experiments and set
`MARKETLAB_DATABASE_URL` as described above. `MARKETLAB_STORAGE_PATH` selects the
shared artifact root (default ignored `data/`). Never commit historical archives
or generated artifacts. Migrate the selected database, then run:

```powershell
.\.venv\Scripts\uv.exe run --locked alembic upgrade head
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli ingest --symbol BTCUSDT --date 2025-01-01
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli inspect --version <returned-version-id>
```

The original R1 scope accepted only that symbol/day. Current R2 extends this to
BTCUSDT/ETHUSDT January 2025 through durable jobs (see below). Ingestion downloads
the official archive/checksum with
finite bounds. It publishes complete verified Parquet/manifest files before
transactionally registering a dataset. Same verified input and transform/lock
identity reuses the published version; changed source bytes produce another one.
Inspection verifies registered hashes, schema, row counts and logical content.
The synthetic `/trades` API and trade CLI are independent and retain their contracts.
No durable worker, analytical query/cache, research workflow, copilot or memo is
implemented by R1. See the contract for failure handling and orphan inspection.


## R2 durable historical ingestion

R2 adds local PostgreSQL jobs, attempts, leases and fenced immutable publication
for BTCUSDT/ETHUSDT January 2025. Apply `alembic upgrade head` to the intended
local database; existing historical ingest/inspect commands remain synchronous.

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli submit --symbols BTCUSDT ETHUSDT --from-date 2025-01-01 --before-date 2025-02-01 --key january-2025
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli worker --max-jobs 62 --wait-seconds 60
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli jobs --submission <submission-id>
```

A worker invocation is bounded; restart it to resume eligible queued/retry work.
The same submission key/request returns the original jobs; a new key rechecks
sources while identical bytes reuse immutable dataset versions. Workers drain
current work on SIGINT/SIGTERM; hard crashes recover after lease expiry. Partial
success is explicit; only registered datasets are discoverable. No monthly
completeness claim follows merely from observed timestamps. See the
[R2 contract](docs/r2-jobs.md) and [actual verification](docs/r2-verification.md).

## R3 deterministic historical bars

R3 adds `GET /v1/bars` over explicitly selected, catalog-registered January 2025
BTCUSDT/ETHUSDT versions. Existing ingestion, synthetic trades and CLIs retain
their contracts. No new migration or worker is required for reads.

```powershell
curl.exe --get "http://127.0.0.1:8000/v1/bars" `
  --data-urlencode "version=<64-lowercase-hex-version>" `
  --data-urlencode "symbol=BTCUSDT" `
  --data-urlencode "interval=1m" `
  --data-urlencode "start=2025-01-01T00:00:00Z" `
  --data-urlencode "end=2025-01-02T00:00:00Z"
```

Repeat `version` for each touched UTC day; select exactly one version per day.
Requests use aligned UTC boundaries, exclusive end, one symbol and `1m` or `5m`.
At most 1,440 expected buckets and five daily partitions are allowed. Missing
buckets remain absent; unavailable daily coverage is an error. OHLC uses execution
time with numeric trade ID ties; volumes sum exact normalized source decimals.
VWAP divides source quote/base volume with half-even rounding to 18 fractional
digits. JSON decimals are strings; results include pinned versions and coverage.
Sums exceeding decimal(38,18) fail explicitly; source quote/base ratios support
38 integer VWAP digits. No input or historical artifact is modified by a read.

`X-Cache` reports `MISS` after calculation/cache storage, `HIT` for a validated
entry, or `BYPASS` when caching is unavailable/oversized. Redis is optional for
results. Bars expire after 15 minutes with +/-10% jitter; whole entries are capped
at 1 MiB. Redis commands have 100 ms deadlines and no retries; three failures
trigger ten seconds of bypass. Identical reads coalesce per process. The existing
256 MiB allkeys-lru/no-persistence Redis configuration is retained.

Two expensive analytical reads, including cold integrity verification, may run per
process; admission waits at most one second. Each DuckDB query uses one thread,
a 512 MiB memory setting and at most 2 GiB private spill. Its 60-second deadline
interrupts native execution. First-read full artifact verification can take longer;
its results are reused while catalog/file identities remain unchanged. Cancellation
drains native work before releasing capacity. Memory settings are not peak RSS
measurements. Health, `/metrics` and ingestion remain available independently of
analytical capacity; cache metrics have bounded labels.

The asynchronous library interface is `marketlab.analytics.BarsRequest.create`
and `BarService(engine, storage_root, redis_url=None)`, followed by
`await service.read(request)` and `await service.close()`. Without `redis_url`,
reads compute with `BYPASS`. R3's completed-summary cache policy was fixture-tested;
the approved R4 below adds actual research calculations and summary endpoints.

See [R3 contract](docs/r3-analytics.md) and [R3 verification](docs/r3-verification.md)
for exact errors, limits, completed local acceptance evidence and subsequent
publication/hosted CI outcomes. Verified implementation commit `54f15d3` passed
[hosted CI run 40072552311](https://github.com/atharva-m/MarketLab/actions/runs/40072552311)
with 606 offline tests on each quality platform and 132 real PostgreSQL tests on Linux.

Library callers should reuse one BarService per application process/event loop and close it at shutdown. Limits/coalescing belong to that service; independent service instances do not share capacity. A TCP disconnect does not guarantee immediate endpoint-task cancellation; continuing work retains the documented bounds.


R3 local acceptance is complete: 606 offline/132 real PostgreSQL tests passed, and
all 62 retained January partitions reconciled 230,311,900 records per interval
into 89,280 1m/17,856 5m bars. Independent review, actual Redis outage/eviction,
cross-day comparisons and owned-resource cleanup passed. Peak memory was not
measured. At local closeout R3 remained uncommitted/unpushed and hosted CI was
unrun. The user subsequently authorized verified R3 commit/push, hosted CI and
actual R3-only fixes/outcome documentation; see the verification publication record.
The verified implementation was subsequently committed/pushed and its hosted CI
passed as linked above; no CI fix was needed. Hosted smoke does not repeat the
local retained-month or real cached-bar outage/eviction acceptance. R4 was subsequently
approved as described below; R5-R9 require separate authorization. Market
data/artifacts, credentials, environments and
weights remain excluded from Git.

## R4 deterministic manual research

R4 adds strict `research-spec-v1` requests for five-minute `market_profile`,
`cross_asset` and `volatility_cluster` workflows. Each request pins registered
January dataset versions, explicit UTC history/evaluation boundaries, typed
predicates and metrics. Missing bars stay missing. Profile/cross-asset require
12 preceding bars; clusters require 288 preceding valid volatility observations
(300 bars/25 hours with complete data). Requests never silently shorten their
period or download earlier history. Derived statistics use Decimal80 and versioned
definitions; they describe assets and do not represent strategy performance.

Apply `alembic upgrade head` to the intended database. The additive migration
creates separate research submissions/runs/attempts/results and preserves ingestion
and trade tables. Submit a strict spec file, execute a bounded local worker, inspect
state and retrieve immutable results:

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli submit --spec request.json --key my-research
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli worker --max-runs 1 --run RUN_UUID
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli inspect --run RUN_UUID
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli results --run RUN_UUID
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli summary --run RUN_UUID
```

HTTP equivalents are `POST /v1/research/runs` with an `Idempotency-Key` header and
JSON spec, then `GET /v1/research/runs/{run_id}`, `/results` and `/summary`.
Submission validates actual initial warm-up and can read all requested inputs;
it returns a durable queued identity. HTTP does not automatically start a worker.
Same key/canonical request returns the original run; a fresh key creates an
independent reproducibility run. Worker retries include crashes: three attempts,
database-time leases and fencing, immutable staged artifacts and atomic numerical
registration/success. Results do not depend on Ollama. Redis summaries retain R3's
one-hour jittered TTL, 1 MiB cap and bounded outage bypass. Research composes the
same bounded BarService; its `/v1/bars` contract is unchanged.

Use one shared BarService and ResearchService per application process/event loop;
close research before bars. New research execution captures Git revision, dirty
source fingerprint and lock hash from the source checkout; packaged images without
Git retain startup, existing APIs and registered numerical reads, but cannot create
new checkout-pinned research executions. No deployment configuration was changed.

See the [R4 contract](docs/r4-research.md) for exact fields, numerical definitions,
bounds and errors, and [R4 verification](docs/r4-verification.md) for actual checks
and limitations. R4 local acceptance/review/owned cleanup passed: 655 offline/152
real PostgreSQL cases, independent all-62-partition reconciliation and ten durable
workflow runs/repeats with matching hashes (31 BTC/33 ETH clusters). Retained R1-R3
behavior and original services/data were preserved. Isolated diagnostics captured
a recurring backwards DB-clock issue that can temporarily make immediate claims
ineligible; the final passing suite does not resolve that environment limitation.
Peak memory is unmeasured and hosted R4 CI is unrun. Nothing is committed/pushed;
R5-R9 remain unauthorized backlog.

The user subsequently authorized a scoped clock follow-up; see
[partial mitigation, incident and recovery](docs/r4-clock.md). Guest NTP conflict
removal reduced large distortion, and real unchanged claim/lease tests passed.
Dense sampling still found smaller Docker initd backwards steps; the clock is
not fully fixed. The coarse 50ms helper cannot prove that shorter steps ceased.

An exploratory initd help command unexpectedly restarted original containers;
stale host forwarding required standard recovery restarts. The same original IDs,
images and volumes are healthy again. Uptime was interrupted; Redis cache continuity
was not verified and is not claimed. Owned resources were cleaned. Application eligibility/fencing remains
unchanged; nothing was committed/pushed. A safe supported live control for the
remaining Docker clock writer was not identified.
