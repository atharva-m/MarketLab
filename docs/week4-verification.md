# Week 4 verification

Date: October 23, 2026. Environment: Windows, project `.venv`, Python 3.13.7,
unchanged locked dependencies. Implementation used the requested coder (Sol 6.1,
high), followed by independent read-only review (Astra, medium).

## Implemented scope

`AGENTS.md` now records the approved week 4 scope and 1 MiB limit. The HTTP adapter
adds raw JSON/CSV imports and exact-ID retrieval over the existing week 3 service.
It counts actual streamed bytes, preserves transaction semantics and exact decimal/
UTC serialization, maps input/conflict/database errors, and runs synchronous work
in the worker pool. A lazy synchronous engine is owned and disposed by app lifespan.
OpenAPI and the week 4 contract document request formats, examples and errors.
No database migration, parser, trade schema, dependency, lockfile, infrastructure,
CI, authentication or Ollama smoke implementation changed.

## Final checks

The final `.\scripts\check.ps1 -Integration` run passed through `uv run --locked`:

- Ruff lint and formatting (33 Python files).
- Strict mypy (12 source files).
- **205 offline tests passed**, zero skips; 34 integration tests deselected.
- **34 real PostgreSQL integration tests passed**, zero skips; 205 offline tests
  deselected. These comprise the existing 22 cases and 12 new HTTP cases.

The new offline HTTP cases cover invalid/malformed UTF-8, JSON and CSV, duplicate
IDs, valid empty batches without database access, supported/unsupported content
types, exact limit and one-byte excess, incorrect and absent Content-Length,
chunked bodies, early stop after exceeding the limit, worker-thread execution,
engine disposal, OpenAPI bodies, decimal/UTC serialization, missing/case-sensitive
IDs and database-error redaction with request IDs and metrics.

Integration used a separate disposable `postgres:17-alpine` container,
`marketlab-w4-postgres-20261023`, on random loopback port 50425. Fresh Alembic
upgrade succeeded through `0002_trades`. The fixture moved unchanged into shared
`tests/conftest.py`, so persistence and HTTP tests clone the actual migrated table
into unique schemas and remove each schema afterward. HTTP cases verify JSON/CSV
round trips at the decimal boundaries with microseconds and UTC normalization,
case-sensitive/missing lookups, invalid/intra-batch duplicate isolation, valid
empty imports, stored-ID conflicts in every batch position, cross-format
conflicts, complete rollback and subsequent successful import.

After the final run, SQL confirmed `0002_trades`, zero rows in `public.trades`
and zero leftover test schemas. The user's existing Compose containers, database
and volumes were not modified. The disposable container was stopped and removed
after verification. `git diff --check` passed.

## Review and execution notes

Independent review identified a JSON integer exceeding Python's digit limit:
`json.loads` raises plain `ValueError` for an otherwise small body containing a
5000-digit integer. The HTTP adapter now returns generic `422` for this condition,
after the `DuplicateTradeError` handler so stored conflicts remain `409`. The pure
week 2 parser stays unchanged. A regression test and manual HTTP check confirm
`422`; final checks above include the fix.
The independent reviewer rechecked the handler ordering, regression coverage and
unchanged parser, and reported no remaining actionable findings.

The first integration run exposed a test assertion comparing decimal text before
and after PostgreSQL's documented eight-place scale padding. The assertion now
compares full validated `Trade` values, verifying exact values without requiring
original trailing-zero counts. No service change was needed.

Initial sandbox attempts hit existing uv-cache permissions, Docker access denial
and a stalled worker-thread HTTP probe. The probe was stopped. All complete checks
and the manual HTTP reproduction succeeded using execution-tool escalation.

## Additional local checks completed

The user subsequently authorized the remaining container, live HTTP and Ollama
checks. They completed on October 23, 2026, using execution-tool escalation for
Docker and host networking. No implementation changes were needed.

- `docker compose config --quiet` passed, followed by an actual production image
  build through the unchanged Dockerfile and `uv sync --locked --no-dev`, tagged
  `marketlab:week4-local-check`. The image uses Linux Python 3.13.17; its API runs
  as UID 10001 with the configured `--loop asyncio` command.
- The separate Compose project `marketlab-w4-local-20261023` used its own image
  tag, network, volumes and random loopback ports: API 52934, PostgreSQL 52260
  and Redis 52258. An empty interpolation environment file and a local override
  avoided changing the repository's Compose configuration or existing stack.
  Fresh startup applied both migrations and reported all services healthy.
- A disposable copy of the production image installed only the locked development
  dependencies inside its own writable layer. Read-only mounts supplied the
  application source, tests, smoke scripts, Dockerfile and project configuration.
  Linux Ruff lint/format passed for those 22 Python files, strict mypy passed
  for 12 source files, **205 offline tests passed** and **34 real PostgreSQL
  integration tests passed**, zero skips. The test container removed itself;
  production containers did not receive development dependencies.
- The live TCP HTTP harness passed **64 checks** across five phases: 42 healthy,
  five Redis-down, five Redis-recovered, seven PostgreSQL-down and five
  PostgreSQL-recovered checks. Healthy checks covered health/metrics/request IDs,
  docs/OpenAPI raw bodies, JSON/CSV exact decimal and UTC round trips, missing and
  case-sensitive IDs, cross-format stored-ID conflicts and full rollback, invalid
  and duplicate batches, empty imports, unsupported/missing media types, malformed
  UTF-8 and payloads, the oversized-integer regression, JSON bodies exactly 1 MiB
  in fixed-length and chunked form, and oversized fixed-length/chunked requests
  for both formats. The live HTTP client correctly uses chunked transfer when
  Content-Length is absent; deliberately incorrect Content-Length remains covered
  by the in-process tests because the HTTP client enforces wire framing.
- Stopping only the isolated Redis service preserved HTTP 200/degraded readiness
  with Redis down and PostgreSQL, storage and host Ollama up. Trade retrieval
  continued working. Restarting Redis restored HTTP 200/ready and all dependencies
  up. The unchanged `scripts/api_smoke.py` passed while healthy, during the Redis
  outage and after final recovery, including preserved request IDs and metrics.
- Stopping only isolated PostgreSQL produced HTTP 503/not_ready with that required
  dependency down. GET and nonempty import returned generic `503 Trade database
  unavailable`; both valid empty formats still returned `200 {"imported": 0}`.
  Restart restored ready and exact retrieval of the original synthetic trade.
- Logs were collected after a further 12-second delay following recovery. There
  were zero unhandled future/task warnings, `gaierror` messages, tracebacks or
  unexpected errors. PostgreSQL logged 14 expected `trades_pkey` duplicate-key
  failures from live and integration conflict tests. An initial broad `ERROR`
  scan flagged those expected database diagnostics; classifying them separately
  established the clean unexpected-error result without suppressing any logs.
  Fresh Alpine database initialization also emitted its expected `no usable
  system locales were found` warning; this was not an unhandled runtime failure.
- SQL confirmed revision `0002_trades`, exactly the two deliberate live-smoke
  records in the isolated public trade table and zero leftover integration test
  schemas. The isolated volume is disposable; no public data was written to the
  user's original database.
- The unchanged `scripts/ollama_smoke.py` passed against the installed host Ollama
  0.40.9 and `qwen3.5:4b-q8_0` (4.2B, Q8_0), generating and validating
  `{"status":"ok","value":2}` in 12.2701 seconds, including an 11.9210-second
  model load. Digest:
  `e15635ee93129fd2086640926e900c37589c5167561104abc3914bd6644c7e07`.
  No model was downloaded or updated. Container readiness separately verified
  host Ollama connectivity through `/api/tags`. Memory fields in the JSON record
  are snapshots, not peak measurements.

Before and after these checks, the original `marketlab-api-1`,
`marketlab-postgres-1` and `marketlab-redis-1` containers retained IDs
`b379ae85c220`, `8656644dd0ac` and `bec035733c30` respectively and remained healthy.
Their containers, image tag, volumes and database were not modified. Local harness,
JSON records, build/startup/test logs, database summary and container-ID evidence
are retained only under ignored `artifacts/week4-local/`.

Independent read-only review of the harness, records, logs and report found no
actionable findings. After review, cleanup removed all four isolated containers,
their network, both named volumes, the Redis anonymous volume and the separate
image tag. `cleanup-evidence.json` records verified project membership, empty
post-cleanup resource lists and matching healthy original-container IDs before
and after cleanup. The final unchanged API smoke output is also retained in
`api-smoke-final.log`. `git diff --check` passed. No application fixes arose from
these additional checks.

## Limits

The Windows and Linux suites, production build, live TCP route checks, isolated
outage/recovery and live model compatibility checks above passed. Hosted GitHub
Actions was not run for week 4. No commit or deployment to the original stack was
performed. These are functional regression checks, not sustained-load benchmarks.
