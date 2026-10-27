# MarketLab

The user has authorized publication of verified R8: commit/push, hosted CI
verification, and fixes only for actual R8-related CI failures through the
prescribed coder/reviewer workflow. Publication and hosted results are pending;
[verification](docs/r8-verification.md) will record the exact SHA and run outcomes.
This supersedes earlier no-commit/push wording only for R8 publication. Original
services remain untouched; R9 and unrelated work remain excluded. Raw artifacts,
data, credentials, environments and weights stay outside Git.

The October 27 [R8 adoption amendment](docs/r8-adoption.md) authorizes the tested
9B Q4_K_M/null-guard interpreter in production code and fresh remaining acceptance.
R8 completed under that amendment and its reviewed technical resource supplement.
Both fixed copilot quality cohorts scored 19/20 clear and zero unsafe handoffs;
the second invocation remains FAILED for resource coverage, and the separate
unchanged technical repeat passed. Both memo cohorts passed 20/20; production
clarification reached the fifth answer and rejected further work without mutation.
Final checks passed 990 offline/200 PostgreSQL, 18 components/33 browsers, current recovery,
monitoring/live/package and exact cleanup/preservation gates. Fresh cold all 62
passed in 265.429132 s with all retained hashes exact. See the
[actual verification](docs/r8-verification.md) for complete evidence and limits.
The historical unknown-cause service-uptime gap remains unresolved.

The source default is now qwen3.5:9b-q4_K_M with the pinned approved digest; the
shared selection also feeds memo workers. Explicit model overrides must carry the
matching MARKETLAB_COPILOT_MODEL_DIGEST; mismatched name/digest pairs fail
identity verification safely. There is no
automatic model fallback or pull. The copilot uses prompt-v4 with num_predict=-1 under the existing 120-second
limit; memos retain prompt-v1
and their 2048-token prediction budget. Older
4B failures and experimental results remain separate evidence, and no commit or
push is authorized.


## Original October 26 R8 acceptance: historical incomplete closeout

The approved [R8 contract](docs/r8-evaluation.md) covers repeated actual-model
evaluations, owned recovery tests, pipeline/cache/model/queue/resource benchmarks
and local operational dashboards. R1-R7 behavior and historical evidence remain
preserved in the exercised checks; final service continuity is unverified. R8
remains INCOMPLETE: the required actual-model five-round clarification case failed
safely at revision 3 initially and revision 4 in the one predeclared supplemental
invocation. Neither reached the fifth-answer/sixth-round boundary. No model/prompt
change or forced state was used. See [actual R8 verification](docs/r8-verification.md).
No commit/push is authorized, and R9 remains backlog.

Two fully measured frozen copilot campaigns each scored 18/20 clear requests,
zero unsafe submissions among 40 negatives, 24 expected negative outcomes and
16 safe failures. Two actual memo campaigns each passed 20/20 under the retained
application grounding rules. Three fresh 1M and three fresh 10M pipelines matched
exact reference hashes; corrected cache/model benchmarks and actual cache faults,
native-time recovery and process-boundary checks passed. The corrected boundary
run passed in 94.0449324s after a retained first harness failure of 16.911s.
Fresh cold all-62 acceptance reconciled 230,311,900 trades and every retained hash
in 266.5237983s including its cleanup. The isolated 19-panel dashboard was rendered
and queried, with actual CLI-worker visibility verified separately.

Final checks passed 939 offline cases (196 PostgreSQL cases deselected), Ruff
lint/format over 161 files, strict mypy over 50 sources and all 279 protected file
hashes. Earlier full acceptance passed 195 real PostgreSQL cases, 18 frontend
components and 33 browser cases; that earlier pass does not replace the final
196-case PostgreSQL suite, which could not run. At final inspection the Docker
engine pipe and original/owned process listeners were absent for an unknown reason.
No restart or final resource cleanup was performed in response to this final
outage. Final database dump, service identity/continuity verification and ownership-checked cleanup are BLOCKED and unverified.
Independent final source/documentation review found no blocking finding;
acceptance closeout remains incomplete. No overall R8 pass, completed cleanup or
hosted R8 result is claimed. All failed
and incomplete invocations and historical limitations remain in verification.

The optional [monitoring stack](monitoring/README.md) runs separately from the
existing services. Its provisioned dashboard distinguishes separate API/worker
registries from read-only durable job aggregates. Missing/stale telemetry is
unavailable. The monitoring-service memory panel measures Prometheus only;
Windows worker memory and full process-tree/model measurements use the separate
resource sampler with recorded collection skew and explicit scope limits.

For an explicitly configured worker, opt in with a distinct loopback export port:

```powershell
$env:MARKETLAB_METRICS_PORT = '59110'
.\.venv\Scripts\python.exe -m marketlab.inference_cli worker --max-jobs 1
Remove-Item Env:MARKETLAB_METRICS_PORT
```

`MARKETLAB_METRICS_PORT=0` disables worker export. The separate durable collector
uses its own bounded read-only connections and cached snapshots:

```powershell
.\.venv\Scripts\python.exe -m marketlab.monitoring --port 59109
```

Acceptance tooling is explicit and restricted to inventoried owned services:
`scripts/r8_acceptance.py`, `scripts/r8_clarification.py`,
`scripts/r8_benchmark.py`, `scripts/r8_cache_faults.py`, `scripts/r8_recovery.py`,
`scripts/r8_boundaries.py` and `scripts/r8_cold.py`. Each invocation needs a fresh `r8-` evidence prefix; inspect
`--help` and the contract before running. Generated fixtures, private connection
manifests, source snapshots and results stay ignored under `artifacts/r8`.
Run model evaluations and timed benchmarks sequentially. The first 1M diagnostic
retains a successful numerical result but receives no acceptance credit because
mandatory memory coverage was incomplete and scheduling was concurrent.

## R7 local research workspace

The approved [R7 contract](docs/r7-ui.md) adds a local React workspace over the
retained R1-R6 services. Implementation/full local acceptance passed: 853 offline,
193 PostgreSQL, 18 frontend component and 33 browser cases. The actual fresh
all-62 browser workflow passed in 526.988s with exact retained hashes. Independent
review and owned cleanup passed; original artifacts/services were preserved.
Actual outcomes and limitations
are in [R7 verification](docs/r7-verification.md), including the safe failed
ambiguous model case and initial Windows Firefox startup failures. A later
[Windows Firefox follow-up](docs/r7-verification.md#windows-firefox-physical-cache-configuration-fix-october-26-2026)
passed all 11 cases with pristine binaries using Playwright's process-only
physical-cache path setting; its default logical MSIX path remains affected.
No R7 commit/push or hosted CI had occurred at local closeout. Verified R7 was
later published as `cb98663eb0edd9726b5336a5933d035c12002c5c`;
[hosted CI 40388784506](https://github.com/atharva-m/MarketLab/actions/runs/40388784506)
passed for that exact revision. Hosted checks remain separate from local model/
month/cold/Windows-cache evidence. R8 was backlog at that publication; its current
authority is above. R9 remains backlog.

The workspace browses catalog versions and durable jobs, submits bounded January
ingestion/research/copilot requests, displays numerical results and separately
retrieves memo status/content. Dataset selection is explicit, including warm-up
history; an existing version is never silently replaced with a newer one.
Catalog metadata listings are distinguished from fully verified artifact detail.
Chart windows obey the existing 1,440-bucket bound; exact strings in tables and
tooltips remain authoritative over approximate chart coordinates.

After the configured database is migrated, run the API from this checkout and
the separate frontend in two terminals:

```powershell
.\.venv\Scripts\uv.exe run --locked uvicorn marketlab.app:create_app --factory --host 127.0.0.1 --port 8000
```

```powershell
Set-Location frontend
npm ci
npm run dev
```

To keep an existing API on port 8000 running, use the dedicated local R7 test
port instead: start the checkout API with `--port 58007`, then set
`$env:MARKETLAB_R7_TEST_API_PORT = '58007'` in the frontend terminal before
`npm run dev`. The proxy accepts only its normal port 8000 or this fixed test port.

Open `http://127.0.0.1:5173`. The fixed local proxy defaults to API port 8000;
there is no public-hosting/authentication deployment in R7. Startup does not
launch workers. Use the same configured database/storage/source checkout for
the existing bounded worker commands, as appropriate:

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli worker --max-jobs 62
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli worker --max-runs 1 --run RUN_UUID
.\.venv\Scripts\uv.exe run --locked python -m marketlab.inference_cli worker --max-jobs 1
```

These commands are operator invocations, not a scheduler. Research validation can
take time before a durable run is returned. If a submission response is lost,
reuse the saved operation key/body; do not create a fresh operation merely to
check whether the original succeeded. Browser cancellation does not cancel a
durable job or establish upstream model cancellation. Memo failure or unavailable
Ollama does not change successful numerical results. Terminal memo jobs cannot be
reset or regenerated for the same run. A blank migrated database legitimately has
an empty catalog; use registered versions in the configured database/storage.
Ignored acceptance snapshots are not automatically restored into user services.

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
Peak memory is unmeasured. At local closeout hosted R4 CI was unrun and publication
was excluded; the later publication authorization below supersedes that restriction.
R5-R9 remain unauthorized backlog.

The user subsequently authorized a scoped clock follow-up; see
[partial mitigation, incident and recovery](docs/r4-clock.md). Guest NTP conflict
removal reduced large distortion, and real unchanged claim/lease tests passed.
Dense sampling still found smaller Docker initd backwards steps; the clock is
not fully fixed. The coarse 50ms helper cannot prove that shorter steps ceased.

An exploratory initd help command unexpectedly restarted original containers;
stale host forwarding required standard recovery restarts. The same original IDs,
images and volumes are healthy again. Uptime was interrupted; Redis cache continuity
was not verified and is not claimed. Owned resources were cleaned. Application eligibility/fencing remained
unchanged in that follow-up; nothing was committed/pushed. A safe supported live control for the
remaining Docker clock writer was not identified.

A later claim fix (October 25, 2026) works around the symptom at the application
layer rather than at the system level. **The backward-clock issue persists.** Docker Desktop's
/initd steps the shared WSL2 clock about 1-2ms backwards every ~30s (upstream
[docker/desktop-feedback#761](https://github.com/docker/desktop-feedback/issues/761)).
Queued R2/R4 work is now claimable from submission without a later wall-clock
comparison, and synchronous retries recheck database time a bounded number of times.
Leases, attempts, fencing and publication are unchanged. 655 offline/158 real
PostgreSQL cases and real clock acceptance passed. No system-level change was made:
Docker Desktop, WSL, the host clock and time-sync configuration are unchanged, and the
clock still steps backwards. See the
[clock fix](docs/r4-clock.md#root-cause-and-application-fix-october-25-2026).

Fresh verification on October 25 passed 655 offline/158 real PostgreSQL tests and
live claim/retry/heartbeat/lease/fencing acceptance in 249.827s. Independent review
found no blocking issue. The application works as intended with the known Docker
clock discrepancy. The owned test database was removed; original service IDs,
start times and health were preserved. The user then authorized committing/pushing
R4 and the application clock fix and checking hosted CI. Published implementation
commit `2c0dd0b` passed [hosted CI run 40167912094](https://github.com/atharva-m/MarketLab/actions/runs/40167912094):
655 offline tests on both Ubuntu and Windows, 158 real PostgreSQL tests on Linux,
plus quality/build/API/optional-Redis-outage/cleanup checks. No CI fix was needed.
Hosted smoke is separate from the local full-month and clock acceptance evidence;
see [R4 verification](docs/r4-verification.md).

## R5 durable inbound copilot

R5 is complete under its approved contract: final locked checks passed 736
offline/174 real PostgreSQL cases; independent review and owned cleanup passed.
Ten full-month copilot/manual runs matched all numerical references over all 62
January partitions. At local closeout no commit/push or hosted CI had occurred.
The user subsequently authorized verified R5 publication, hosted CI checks,
actual R5-only fixes and outcome documentation. Published implementation
`19a1363` passed [hosted CI run 40177491693](https://github.com/atharva-m/MarketLab/actions/runs/40177491693):
736 offline tests on Ubuntu and Windows, 174 real PostgreSQL tests on Linux, plus
quality/build/API/optional-Redis-outage/cleanup checks. No CI fix was needed.
Hosted smoke is separate from the actual local model/month acceptance and its
dirty-source provenance; see verification. R6-R9 remain unauthorized.

R5 adds an optional local natural-language entry point over the same validated
R4 research submission service. See [the contract](docs/r5-copilot.md) and
[actual verification and limitations](docs/r5-verification.md). Numerical
execution and result retrieval remain available without Ollama.

Apply the additive migration with `alembic upgrade head`. Create a JSON file:

```json
{
  "schema": "copilot-request-v1",
  "text": "Compute a descriptive OHLCV profile of Bitcoin using five-minute bars; metrics profile. Evaluation from 2025-01-01T01:00:00Z to 2025-01-02T00:00:00Z; history from 2025-01-01T00:00:00Z.",
  "dataset_versions": ["<explicit registered January BTCUSDT version>"],
  "context": {}
}
```

Replace the placeholder with the actual registered 64-character version. Supply
one version per required UTC day and symbol; a larger explicit selection is
permitted, and the application pins the exact needed subset. Clear text can be
combined with explicit `context` fields: workflow, symbols, start, end,
history_start, interval and metrics. Dates are UTC half-open bounds, bars 5m,
only January 2025. No implicit latest selection, dates, thresholds or downloads.

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.copilot_cli create --request request.json --key example-copilot
.\.venv\Scripts\uv.exe run --locked python -m marketlab.copilot_cli worker --max-jobs 1 --request REQUEST_UUID
.\.venv\Scripts\uv.exe run --locked python -m marketlab.copilot_cli inspect --request REQUEST_UUID
```

Equivalent HTTP endpoints are `POST /v1/copilot/requests`, `GET
/v1/copilot/requests/{request_id}` and `POST
/v1/copilot/requests/{request_id}/clarifications`; POST requires JSON and an
`Idempotency-Key`. Creation queues interpretation promptly. A separate bounded
copilot worker runs inference; existing research workers execute submitted
numerics. `submitted` includes a durable run ID and does not mean execution has
finished. Poll existing research inspection/results/summary endpoints for it.

Ambiguous input yields durable `needs_clarification` with field-specific
questions and no numerical run. Answer with the current revision, for example:

```json
{
  "schema": "copilot-answer-v1",
  "expected_revision": 0,
  "text": "Use this explicit history start.",
  "context": {"history_start": "2025-01-01T00:00:00Z"}
}
```

Use `copilot_cli answer --request REQUEST_UUID --answer answer.json --key
ANSWER_KEY`, then invoke the worker again. Up to five answer rounds are allowed.
Unrelated answers do not resolve prior ambiguity.
The original dataset selection stays fixed across answers; create a fresh request
to add or replace dataset versions. Answers can explicitly correct the research
period/history within that selection. Unsupported work returns
`unsupported`; bounded inference or validation failures produce safe durable
failure state. Same request/answer key and body replay, conflicting reuse fails.

Ollama uses existing `MARKETLAB_OLLAMA_URL`; optional
`MARKETLAB_COPILOT_MODEL` defaults to `qwen3.5:4b-q8_0` and
`MARKETLAB_COPILOT_MODEL_DIGEST` can require an installed digest. No automatic
model pull/update or fallback. One cooperating inference call at a time, 120s
deadline, two durably reserved calls per revision, three execution attempts
including crashes. Provenance pins model/source/settings and bounded response
evidence. Model output must pass independent conservative semantic checks and all
R4 shape/catalog/integrity/warm-up checks. Requests outside the recognized explicit
language may require structured clarification even when a human finds them clear.
The recorded R5 60-case evaluation achieved 18/20 correct clear specs and zero
unsafe submissions across 40 negative cases; 25 negative cases received the
expected clarification/refusal and 15 failed safely. See verification for model
limitations and earlier failed evaluations.

Each body is at most 64 KiB, each text 8 KiB, at most 62 selected versions. Total
model text/context/system/schema input is bounded to 6000 UTF-8 bytes with 2048
output tokens in the 8192 context; larger conversations fail clearly without
truncation. Never place credentials in prompts. Responses/prompts are durable
local request evidence but are omitted from normal logs and metric labels.

Existing numerical manifests/results are unchanged. Adding source changes R4
execution fingerprints: old completed results remain readable and incompatible
queued execution is rejected. The Docker clock discrepancy persists; R5 follows
the established database-time lease/retry and immediate queued-claim protocol.
The later R5 publication approval authorizes commit/push of the verified scope,
hosted CI checks, actual R5-only fixes through the prescribed coder/reviewer
workflow and publication of actual outcomes. Verification records the exact
published revision and observed hosted results. Local acceptance remains
separate; artifacts/data, credentials, environments and weights stay outside Git.

## R6 grounded research memos

R6 is complete with full local acceptance, independent review and owned cleanup
under [the memo contract](docs/r6-memos.md). [Verification](docs/r6-verification.md)
records the actual source, checks, failures and limitations. Final locked checks
passed 758 offline/189 PostgreSQL cases; actual bounded memo evaluation passed
20/20 and eight monthly memos were independently audited. The later October 26
approval authorized publication and actual CI fixes. R6 and its verifier follow-up
were published as `c94ef4bce9dd292730c8884761c787f799bac2d1`; the first
[hosted run](https://github.com/atharva-m/MarketLab/actions/runs/40269166877)
failed Ubuntu quality and integration, and Windows quality was canceled. Recovery
`6084ac58fa49c49015a4b552db68e3be14b6dc2a` then passed Ubuntu quality and Linux
integration in [run 40271353210](https://github.com/atharva-m/MarketLab/actions/runs/40271353210),
but Windows failed the worker-crash test again. A stdlib dynamic-spawn startup
race was confirmed. The reviewed public-API bootstrap correction was published as
`0e054bd41d987e85df4cb1dcf75f62e6aa049fb6` and
[hosted run 40276563068](https://github.com/atharva-m/MarketLab/actions/runs/40276563068)
passed: 819 offline cases on both Ubuntu and Windows, 189 PostgreSQL cases, and
build/API/Redis-outage/cleanup checks. Local model/month/cold evidence remains
separate from hosted coverage. No R6/verifier CI blocker remains; R7-R9 remain backlog.

Apply the locked `alembic upgrade head` to the intended database before using
R6; additive migration `0007_memos` preserves existing table definitions.
New numerical success atomically queues an independent memo job. Read numerical
results/summary immediately; Ollama or memo failure does not change their success.
Memo state is separate: pending, running, ready or failed. Memos use only verified
selected summary metrics and contain exactly three paragraphs covering
scope/coverage, descriptive findings and limitations. Application code supplies
the grounded claims and exact numeric placeholders; the installed local model
chooses bounded wording. This is not unrestricted prose generation or forecasting.

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.inference_cli worker --max-jobs 1
.\.venv\Scripts\uv.exe run --locked python -m marketlab.memo_cli inspect --run RUN_UUID
.\.venv\Scripts\uv.exe run --locked python -m marketlab.memo_cli read --run RUN_UUID --markdown
```

The shared bounded worker gives eligible copilot requests priority over pending
memos without interrupting an active call. The existing copilot worker stays
available. Research/ingestion workers remain separate. One cooperating client
inference call is admitted at a time; a disconnected client does not establish
that upstream server generation has stopped.

For a completed older run, `memo_cli enqueue --run RUN_UUID` or empty-body
`POST /v1/research/runs/{run_id}/memo` idempotently ensures memo work exists.
`GET` on that path returns separate state and verified ready content. Existing
research/copilot response shapes are preserved. Three execution attempts and two
reserved model calls bound retries; invoke the worker again when eligible.
Terminal failed jobs are not reset and ready memos are never overwritten.

The Markdown memo and supplemental manifest live in the run's separate memo
directory. Numerical manifests/results/summaries remain immutable. Reads verify
registered artifact hashes and summary lineage; a corrupt supplement leaves
numerical reads usable. No memo cache, model pull, automatic backfill or scheduler
is introduced.


The full-month acceptance passed through explicit BTC/ETH profile requests then
cross-asset research using normal verified caches. An earlier cold combined
cross-asset preparation hit the unchanged thirty-minute bound before acceptance;
that failure remains documented. Ollama inference used CUDA; historical integrity
verification, DuckDB and Decimal research preparation used CPU. No GPU data-pipeline
or cold combined-month performance guarantee follows. The known Docker clock
issue persists; the application claim workaround is preserved.

The user subsequently authorized a scoped [cold verifier optimization](docs/verifier-optimization.md)
that preserves exact dataset checks and canonical hashes. Native Arrow encoding
replaces Python per-row verification work; one lazy two-child spawn pool shares
two compute permits with DuckDB. Cancellation drains real work before reuse and
only current verified catalog/file identities enter the existing in-memory cache.
The actual fresh-process, empty-application-cache all-62-partition
submit/prepare/execute/readback passed in 272.814s, including cleanup, within the
unchanged thirty-minute bound. All 230,311,900 trades and original artifact/logical
hashes reconciled; numerical payloads matched independent R4 references exactly.
Full checks passed 811 offline/189 PostgreSQL cases. OS filesystem-cache state
was uncontrolled; simultaneous whole-application peak memory is unmeasured.
The earlier R6 cold failure remains historical evidence. Source identity,
packaged Linux and preservation/cleanup outcomes are recorded in the follow-up.
Publication follows the later October 26 approval. The old cold measurement is
retained. Corrected source bb4d698 passed its separate fresh cold workflow in
266.692s including cleanup, with exact hashes, two-worker readiness and Linux
spawn/read/close evidence. All 263 protected originals and original services were
preserved through owned cleanup. The first new diagnostic-wrapper failure remains
recorded; it was corrected without runtime changes and rerun in a fresh process.
Hosted failures and recovery are recorded in
[R6 verification](docs/r6-verification.md).

Library callers should reuse one `BarService` per application and await its
`close()` during shutdown. Scripts using spawned verification must guard startup
with `if __name__ == "__main__":`; repository CLIs and application entry points
already do so. Verification workers start lazily when unverified datasets are read.
