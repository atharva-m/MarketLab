# Week 3 verification

Date: October 23, 2026. Environment: Windows, project `.venv`, Python 3.13.7,
existing locked dependencies. Implementation used Sol 6.1 high; independent read-only
review used Astra medium. The initial week 3 implementation required no dependency, lockfile,
week 1 application/infrastructure, health endpoint, CI workflow or week 2 parser/schema changes.
The separately authorized Redis diagnostic follow-up below changes the container's event-loop
selection while preserving the existing health implementation and contract.

## Implemented scope

- Updated `AGENTS.md` to the approved week 3 persistence milestone and retained the
  explicit coder/reviewer workflow.
- Added `0002_trades` after the unchanged baseline, storing the five canonical fields
  with a primary key, exact `NUMERIC(20,8)` values and timezone-aware timestamps.
- Added synchronous Python JSON/CSV import functions using the existing in-memory
  parsers and engine-owned transactions; stored ID conflicts reject the whole batch.
- Added exact-ID retrieval, migration schema assertions, synthetic persistence tests,
  service documentation and current README migration/integration instructions.

## Relevant checks

The final `.\scripts\check.ps1 -Integration` invocation passed with `uv run --locked`:

- Ruff lint and formatting.
- Strict mypy for 11 source files.
- **163 unit tests passed**, including the unchanged 159 week 2 unit tests and four
  new offline empty/invalid import cases. No unit tests skipped.
- **22 real PostgreSQL integration tests passed**, including the two existing
  readiness/migration checks and 20 persistence cases. No integration tests skipped.
  Each pytest invocation deselected the other category by design.

Integration ran against a separate disposable PostgreSQL 17 Alpine container with a
random loopback host port. The user's existing Compose database and volumes were not
migrated or modified. Alembic successfully upgraded from a fresh database through both
revisions. Persistence cases cloned the actual migrated table into unique schemas and
removed them afterward. A SQL check confirmed zero public trade rows and zero leftover
test schemas. Downgrade to `0001_baseline` restored only `alembic_version`; re-upgrade
restored `trades` and revision `0002_trades` successfully. The disposable container
and its anonymous test volume were removed after final review.

Coverage includes both formats, minimum/maximum exact decimals, negative timezone
offsets, microseconds, UTC retrieval under non-UTC database sessions, missing and
case-sensitive IDs, cross-batch conflicts at every position, entire-batch rollback,
unchanged stored records, subsequent successful imports, invalid/intra-batch duplicate
inputs and empty batches without connections or writes.

Initial sandbox attempts were unable to use Docker/host TCP, and the offline suite
stalled in the existing app tests. The stalled process was terminated; the complete
locked check above succeeded with execution-tool escalation. An initial real persistence
run exposed strict Pydantic rejecting SQLAlchemy RowMapping; retrieval now converts it
to a dictionary before schema validation. The final complete checks include this fix.

## Independent review

Astra identified one actionable timestamp-boundary issue: a non-UTC database session
can render a valid UTC year 1 instant as BC, or a year 9999 instant as year 10000,
before psycopg can decode it. Retrieval now sets UTC locally to its read transaction
before selecting. Eight integration regressions cover years 1/9999, Honolulu/Kiritimati
sessions and both input formats, and confirm that lookup restores the caller's pooled
session timezone. The final complete checks above include this correction. Astra
re-reviewed the fix and confirmed no remaining actionable findings.

## Remaining local regression checks completed

On October 23, 2026, Sol 6.1 high ran the previously outstanding local checks with
execution-tool escalation for Docker and host networking. All checks below passed;
no implementation fixes were needed.

- `docker compose config --quiet` and an actual API image build using the repository
  Dockerfile, `uv 0.13.5` and `uv sync --locked --no-dev`. The rebuilt Linux image
  used Python 3.13.17 and ran the API as the configured non-root UID 10001.
- A separate Compose project, `marketlab-w3-regression-20261023`, used a separate
  image tag, network and volumes, an empty interpolation environment file, and
  random loopback ports (API 32771, PostgreSQL 32770, Redis 32769). The original
  `marketlab` project's services, database and persistent volumes were untouched.
- Fresh container startup completed both migrations and reported the API,
  PostgreSQL and Redis healthy. A direct SQL query confirmed `0002_trades`.
- The existing `scripts/api_smoke.py` passed `/health/live`, `/health/ready`,
  `/health/dependencies` and `/metrics`, including preserved `X-Request-ID` and
  Prometheus metrics. `/docs` and `/openapi.json` also returned HTTP 200.
  Readiness was `ready`, with PostgreSQL, storage, Redis and the host Ollama
  service all `up`; this also verified container-to-host Ollama connectivity.
- Stopping only the disposable Redis service preserved HTTP 200 across the smoke
  checks. Readiness became `degraded`, Redis reported `down`, and the three other
  dependencies stayed `up`. Restarting Redis restored `ready` with all checks `up`,
  and the smoke script passed again.
- The project Python 3.13.7 `.venv` ran `uv run --locked pytest -m integration
  --basetemp artifacts/week3-local-regression/pytest-integration -q` against the
  rebuilt stack's disposable database: **22 passed, 163 deselected, zero skips**.
  Subsequent SQL checks confirmed zero public trade rows and zero leftover test
  schemas, with revision still `0002_trades`.
- The unchanged `scripts/ollama_smoke.py` passed against the installed host Ollama
  0.40.9 and `qwen3.5:4b-q8_0` (4.2B, Q8_0). It generated and Pydantic-validated
  `{"status":"ok","value":2}` in 5.6142 seconds, with context length 8192.
  Model digest was
  `e15635ee93129fd2086640926e900c37589c5167561104abc3914bd6644c7e07`.
  No models were downloaded or updated. The script reported 5,112,709,774 bytes
  each for loaded model size and VRAM allocation; these are snapshots, not peak
  memory measurements.

The Redis outage did produce a diagnostic caveat in container logs: repeated
`Future exception was never retrieved` messages with `socket.gaierror: [Errno -2]
Name or service not known`. The readiness requests still completed in approximately
three seconds under the configured dependency timeout, and the application recovered after
Redis restarted. Code inspection found the existing Redis probe awaited inside
`asyncio.timeout`, without an application-created detached task. A late DNS failure
after cancellation in the Linux uvloop/runtime is a possible explanation, not a
confirmed root cause. The logs from that run are therefore not error-free. No functional week 3
regression or concrete application fix was established in that initial run. The separately
authorized investigation below subsequently confirmed the cause and resolved the warning.

The disposable project, its containers, network, named/anonymous volumes and separate
image tag were removed after verification. The three original services remained
healthy. Local JSON records and Compose logs are retained only under ignored
`artifacts/week3-local-regression/`; no credentials, model weights or generated
artifacts were added to version control.

## Redis DNS warning investigation and fix

On October 23, 2026, Sol 6.1 high investigated the warning and implemented the fix;
Astra medium independently reviewed it. The locked Linux runtime is uvloop 0.23.0,
Redis 6.4.0 and Python 3.13.17. Redis opens its connection through
`asyncio.open_connection`. In the installed uvloop source, `create_connection`
creates DNS futures and awaits `asyncio.wait(fs)` without cancelling or retrieving
those futures if the surrounding connection is cancelled. The readiness deadline
can therefore return before an unsuccessful DNS lookup completes, leaving the
late `socket.gaierror` unobserved.

A controlled reproduction used two disposable containers on a separate Docker network.
Each cancelled `asyncio.open_connection` to an absent DNS name after 50 milliseconds,
then waited 12 seconds and collected discarded futures. With the same locked image,
uvloop reported one `Future exception was never retrieved` context containing a
`gaierror`; the standard asyncio loop reported zero unhandled contexts.

The Dockerfile now explicitly selects Uvicorn's `--loop asyncio`, which handles
this cancellation correctly. No exception handler or log filter suppresses the
warning, and health endpoint code, dependency settings and the lockfile are unchanged.
The README explains the runtime choice and retains the Windows
`asyncio:SelectorEventLoop` launch command required by psycopg. The regression test
reads the actual Dockerfile launch command, uses its selected Uvicorn loop factory,
and holds a synthetic DNS failure until readiness has returned the same degraded
`TimeoutError` result. It then releases the lookup and verifies that the late failure
does not reach the loop's unhandled-exception handler.

Final checks for this fix:

- Windows Python 3.13.7 project `.venv`, locked dependencies: Ruff lint/format,
  strict mypy and **164 unit tests passed**, zero skips. The previous 163 tests
  remain unchanged. **22 PostgreSQL integration tests passed**, zero skips, against
  the separate migrated database.
- The production image was rebuilt through the unchanged locked Docker build.
  The isolated `marketlab-redis-dns-20261023` Compose project used a separate image
  tag, network and volumes, plus random loopback ports (API 32775, PostgreSQL 32774).
  The actual API command included `--loop asyncio` and the process ran as UID 10001.
- Linux Python 3.13.17 in a disposable copy of that image passed Ruff lint/format,
  strict mypy and **164 unit tests**, zero skips. Development dependencies were
  installed only inside that disposable test container from the same lockfile.
- Healthy HTTP checks confirmed all four dependencies up, the unchanged status/body
  and request-ID contracts, liveness, metrics, docs and OpenAPI. Redis outage yielded
  HTTP 200/degraded with Redis `down`/`TimeoutError`; PostgreSQL, storage and Ollama
  remained up. Six readiness/dependency requests, including four concurrent requests,
  completed in 3.024–3.053 seconds with the configured three-second timeout; liveness
  remained under one second. Restarting Redis restored HTTP 200/ready.
- Logs were collected after waiting 12 seconds following the outage requests and
  another 12 seconds following recovery. They contained no unhandled future/task
  warnings, `gaierror` messages or tracebacks. The container healthcheck also exercised
  readiness during the outage and after recovery.
- A stopped PostgreSQL service still produced HTTP 503/not_ready with only that
  required dependency down; restart restored ready. The unchanged `api_smoke.py`
  passed after recovery. SQL confirmed revision `0002_trades`, zero public trade
  records and zero leftover test schemas.
- The unchanged live Ollama smoke passed again against the already installed
  `qwen3.5:4b-q8_0`, Ollama 0.40.9, in 5.5492 seconds, validating
  `{"status":"ok","value":2}`. No model was downloaded or updated. Container
  readiness also verified host Ollama `/api/tags` through the selected event loop.

An initial sandbox run hit uv cache permissions; the complete host checks passed
with execution-tool escalation. The first Linux test harness omitted the scripts
directory and produced four setup errors; mounting that directory and rerunning
the complete Linux suite yielded the clean result above. These were test execution
issues, with no application changes required.

Standard asyncio DNS lookups use executor threads, which can remain occupied until
the resolver finishes after a request times out. The checks establish the response
contract, bounded requests and clean delayed DNS completion for the exercised local
workload; they are not a sustained-load or comparative-throughput benchmark.
Local evidence is under ignored `artifacts/redis-dns-regression/`.

Astra's final independent read-only review found no actionable findings after
checking the code, outage/recovery records, logs and verification report. The
disposable Compose containers, both volumes, both test networks and the separate
image tag were removed. The original `marketlab` API, PostgreSQL and Redis services
remained healthy. `git diff --check` passed, and pre-existing week 3 work was preserved.

## Existing local deployment completed

On October 23, 2026, the existing `marketlab` Compose stack was rebuilt and restarted
to apply the Redis DNS fix and week 3 migration. `docker compose build api` passed,
followed by `docker compose up -d --no-build --wait --wait-timeout 120`. Compose
recreated only the migration runner and API; the original PostgreSQL and Redis
containers remained running.

Before deployment, PostgreSQL was at `0001_baseline` with only `alembic_version`.
The migration runner upgraded it to `0002_trades`; a subsequent database check
confirmed the new `trades` table with zero rows. The existing named volumes were
preserved: `marketlab_postgres_data` remained mounted at `/var/lib/postgresql/data`
and `marketlab_marketlab_data` at `/data/marketlab`. No volume was removed or replaced.
The running API command includes `--loop asyncio`.

The unchanged `scripts/api_smoke.py` passed liveness, readiness, dependency and
metrics checks, including request IDs. `/docs` and `/openapi.json` returned HTTP 200.
Readiness was `ready`, with PostgreSQL, storage, Redis and Ollama all `up`. Startup
and smoke-check logs showed no issues. These checks verify the applied local
deployment; the earlier isolated outage/recovery and live model-generation results
remain documented above.

## Limits

No final local check above was skipped or blocked; the Redis diagnostic caveat is
resolved by the follow-up. Hosted CI was not run; Windows and Linux local quality
checks, the Linux production image build and deployed container smoke checks passed.
The existing local Compose application now runs the rebuilt API with the Redis DNS
fix and migration `0002_trades`, with its original data volumes preserved. Decimal
numeric values and UTC instants are preserved, while original trailing-zero counts
and timezone offsets are not stored. Inputs
remain synthetic in-memory text with no external/provider ingestion.
