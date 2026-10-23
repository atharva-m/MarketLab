# Week 5 verification

Date: October 23, 2026. Environment: Windows, project `.venv`, Python 3.13.7,
unchanged locked dependencies. Implementation uses the requested coder (GPT-6.1 Sol,
high), followed by independent read-only review (GPT-6 Astra, medium).

## Implemented scope

`AGENTS.md` records the approved week 5 scope. `GET /trades` and the small synchronous
listing service add bounded browsing with default 100 and range 1–500. PostgreSQL
`C` collation is explicit in ordering and the exclusive boundary comparison. Queries
fetch at most `limit + 1` records; page cursors use the final visible ID only when
another record exists. The response reuses canonical decimal-string/UTC serialization.
The boundary follows the existing trade-ID syntax and may identify no stored record.

OpenAPI, README and the browsing contract document parameters, examples, errors and
current committed data semantics. Week 1–4 behavior remains covered by regression
checks. No migration, infrastructure, CI, lockfile, dependency or Ollama smoke changes
were made. The five-field Trade contract retains the same validation and serialization.

## Check results

The complete `.\scripts\check.ps1 -Integration` passed via `uv run --locked`:

- Ruff lint and formatting (35 Python files).
- Strict mypy (12 source files).
- **246 offline tests passed**, zero skips; 43 integration tests deselected.
- **43 real PostgreSQL integration tests passed**, zero skips; 246 offline tests deselected.

This includes all existing week 1–4 tests and 41 new offline plus nine new integration
listing cases. Offline checks cover explicit `C` collation on ordering/comparison,
parameterized boundaries, SQL `LIMIT limit + 1` at page sizes 1, 100 and 500, no
offset, cursor generation, full/partial/empty pages, invalid parameters before database
access, worker-thread execution, decimal/time serialization, OpenAPI, request IDs,
metrics and database-error redaction.

Real PostgreSQL tests exercise the new route and service against a fresh migrated
database: mixed-case and punctuation ordering, all page sizes through the same data,
nonexistent and beyond-end boundaries, default/maximal page limits with 501 records,
year 1/year 9999 timestamp boundaries under Honolulu/Kiritimati session timezones,
exact decimal limits, commits between pages and a real missing-table SQL error
mapped to generic `503`. Existing import, rollback, exact-ID, schema and readiness
integration tests also passed.

Integration used an isolated `postgres:17-alpine` container,
`marketlab-w5-postgres-20261023`, on random loopback port 63686. Fresh Alembic upgrade
succeeded through `0002_trades`. Tests cloned the migrated table into per-test schemas
and removed them afterward. After the full run, SQL confirmed revision `0002_trades`,
zero rows in `public.trades` and zero leftover `test_trades_*` schemas. The original
Compose API, PostgreSQL and Redis containers remain healthy and were not modified.

The initial focused run had three failing test assertions that assumed a particular
SQLAlchemy bind-parameter number for `LIMIT`; adding a boundary renumbers that bind.
The assertions now verify the literal query limit and boundary parameterization
separately, and the complete checks above include this correction. Initial sandbox
attempts could not persist uv interpreter-cache files or access Docker; the complete
checks and Docker operations succeeded with execution-tool escalation.

Independent read-only review found that the PowerShell traversal example initially
emitted items only after fetching a subsequent page. The example now emits the first
page's items before entering the loop, covering empty, single-page and multiple-page
results. The reviewer verified this correction and reported no remaining actionable
findings. The reviewer's separate pytest rerun encountered temporary-directory
permission errors rather than product assertion failures; it is not counted as a
passing run. The coder's complete offline/integration run reported above passed.
No full-suite rerun was needed for this documentation-only correction.

After review, cleanup verified the disposable container's exact ID and ownership
label, then removed only that container and its anonymous volume. No owned container
or volume remained. The original `marketlab-api-1`, `marketlab-postgres-1` and
`marketlab-redis-1` containers retained IDs `b379ae85c220`, `8656644dd0ac` and
`bec035733c30` respectively and remained healthy. `git diff --check` passed after
the final documentation changes.

## Additional local checks completed

The user subsequently authorized production-image, live TCP, outage/recovery and live
Ollama checks. These completed on October 23, 2026, using execution-tool escalation
for Docker and host networking. No application changes were needed.

- `docker compose config --quiet` passed, followed by a production build through the
  unchanged Dockerfile and `uv sync --locked --no-dev`, tagged separately as
  `marketlab:week5-local-check`. The image runs Linux Python 3.13.17 as UID 10001,
  using the configured Uvicorn `--loop asyncio --no-access-log` command.
- The isolated Compose project `marketlab-w5-local-20261023` used its own image,
  network, volumes and random loopback ports: API 64131, PostgreSQL 64127 and Redis
  64128. An override and empty interpolation environment file under ignored
  `artifacts/week5-local/` preserved the repository's configuration and original stack.
  Fresh startup applied migrations through `0002_trades` and all services became healthy.
- The real TCP HTTP harness passed **84 checks**: 55 healthy, six Redis-down, six
  Redis-recovered, 11 PostgreSQL-down and six PostgreSQL-recovered. Healthy coverage
  included OpenAPI, empty listing, JSON/CSV import and exact lookup, decimal/UTC
  round trips, case-sensitive/missing lookups, 513 synthetic records, default 100
  and maximum 500 page sizes, complete traversal with page size 73, mixed-case and
  punctuation ordering, exclusive existing/nonexistent/beyond-end boundaries,
  an exactly full final page with a null cursor, invalid pagination, duplicate
  rollback for both formats, unsupported media types, exact 1 MiB empty JSON and
  oversized fixed-length/chunked JSON and CSV bodies. Every request verified the
  preserved `X-Request-ID` response header.
- Stopping only isolated Redis yielded HTTP 200/degraded readiness with Redis down
  and PostgreSQL, storage and host Ollama up. Bounded listing and exact lookup
  continued to return the expected data. Restart restored ready and healthy
  dependency states. The unchanged `scripts/api_smoke.py` passed while healthy,
  during the Redis outage and after final recovery.
- Stopping only isolated PostgreSQL yielded HTTP 503/not_ready with PostgreSQL
  down. Both default and bounded listing, exact lookup and nonempty import returned
  generic `503 Trade database unavailable`. Both valid empty import formats still
  returned zero, and invalid pagination still returned `422`. Restart restored
  readiness, listing order/cursor and the original exact decimal/UTC record.
- Logs were collected after a further 12-second recovery delay. There were no
  unhandled future/task warnings, `gaierror` messages, tracebacks or unexpected
  error lines. PostgreSQL logged two expected `trades_pkey` duplicate-key errors
  from the deliberate cross-batch conflict checks; these were classified separately.
  Fresh Alpine initialization also emitted its expected `no usable system locales
  were found` warning.
- Final SQL confirmed `0002_trades`, 513 deliberate synthetic live-check records in
  the isolated public trade table and zero leftover integration test schemas.
  Existing data in the original local PostgreSQL instance was not accessed or changed.
- The unchanged `scripts/ollama_smoke.py` passed against installed host Ollama
  0.40.9 and `qwen3.5:4b-q8_0` (4.2B, Q8_0), validating
  `{"status":"ok","value":2}` in 5.6006 seconds, including a 5.2941-second model
  load. Digest:
  `e15635ee93129fd2086640926e900c37589c5167561104abc3914bd6644c7e07`.
  No model was downloaded or updated. Container readiness separately verified host
  Ollama connectivity. Recorded memory values are snapshots, not peak measurements.

Original-container IDs and healthy states were captured before the build and after
the checks: API `b379ae85c220`, PostgreSQL `8656644dd0ac`, Redis `bec035733c30`.
All matched. Harnesses, phase records, model output, logs and evidence summary are
retained only under ignored `artifacts/week5-local/`.

Independent read-only review of the harness, phase records, logs and verification
report found no actionable findings. This was an evidence review, not another run
of the checks. After review, cleanup verified Compose ownership labels and resource
names, checked the anonymous volume was attached only to owned containers, and
removed the four isolated containers, network, both named volumes, Redis anonymous
volume and separate image tag. `cleanup-evidence.json` records empty post-cleanup
resource inventories and matching healthy original-container IDs before and after
cleanup. An initial cleanup inventory omitted the completed migration container;
its safety assertion stopped before any mutation. Including stopped containers in
the inventory resolved that harness issue. Final `git diff --check` passed.

## Limits

Hosted GitHub Actions and a separate Linux unit/integration suite have not been rerun
for week 5. The Windows offline/integration suites, Linux production build, live
TCP/outage checks and installed-model smoke described above passed. No commit or
deployment to the original local Compose stack was performed.
