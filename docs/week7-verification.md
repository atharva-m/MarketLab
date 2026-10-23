# Week 7 verification

Date: October 23, 2026. Environment: Windows, project `.venv`, Python 3.13.7,
unchanged locked dependencies. Implementation uses the requested coder (GPT-6.1 Sol,
high); independent read-only review by GPT-6 Astra, medium follows implementation.

## Implemented scope

`AGENTS.md` records the approved week 7 scope. The existing `GET /trades` route and
`list_trades` service accept optional inclusive `executed_from` and exclusive
`executed_before`, either alone or together as `[from, before)`. A shared helper
reuses the existing trade timestamp validator's exact syntax and UTC normalization,
including UTC overflow handling; the five-field trade contract is unchanged.
Malformed bounds and ranges with `from >= before` return `422` before database access.

SQL combines time bounds with the existing exact symbol and exclusive ID boundary
before the existing `limit + 1` fetch. The cursor derives from matching records only.
ID ordering and boundary comparison retain explicit PostgreSQL `C` collation; time
filters do not reorder results. Existing limits, decimal strings, UTC serialization,
generic database `503` responses and current committed data semantics remain intact.
README, OpenAPI and the week 7 contract document syntax, positive-offset URL encoding,
one-sided and combined filters, full traversal, retaining filters, errors and limits.
No migration, index, dependency, lockfile, infrastructure or CI changes were made.

## Actual checks

The complete `.\scripts\check.ps1 -Integration` passed with `uv run --locked`:

- Ruff lint and formatting passed (40 Python files already formatted).
- Strict mypy passed for 12 source files.
- **359 offline tests passed**, zero skips; 71 integration tests deselected.
- **71 real PostgreSQL integration tests passed**, zero skips; 359 offline tests deselected.
- `git diff --check` passed.

This retains all prior regression cases and adds 73 offline plus 20 integration
cases. Offline coverage checks strict malformed timestamp rejection for both bounds,
UTC overflow, invalid/equal/reversed ranges including equivalent offsets, service
rejection before connecting, timezone normalization, SQL time predicates before
`LIMIT` with sizes 1/100/500, retained `C` ordering/comparison, route parameter
forwarding and worker execution, UTC/decimal serialization, empty pages, redacted
errors, request IDs/metrics and the OpenAPI contract.

Real PostgreSQL cases combine each one-sided bound and two equivalent two-sided
ranges with optional symbol selection, page sizes 1/2/3/500, interleaved nonmatching
times and symbols, mixed-case/punctuation IDs deliberately ordered differently from
timestamps, exact inclusive/exclusive microsecond boundaries, full/final/empty
pages, nonexistent and excluded-record boundaries and omitted-time compatibility.
The offset range includes a positive `+05:30` offset passed via the HTTP client's
query encoder. Year 1/year 9999 time-filter queries preserve exact UTC and decimal
values under Honolulu and Kiritimati sessions and restore session timezone state.

A separate writer holds matching/nonmatching rows uncommitted during an HTTP read;
they remain invisible until commit. Later pages include the newly committed match
beyond the cursor and exclude the row before it, the other symbol, the timestamp
below the inclusive lower bound and the timestamp at the exclusive upper bound.
A real missing-table failure returns only the generic `503` body for valid time
filters while malformed/overflow/range-invalid queries still return `422`.

Integration used isolated `postgres:17-alpine` container
`marketlab-w7-postgres-20261023` on random loopback port 54162, with ownership label
`marketlab.week7.owner=week7-20261023`. Fresh Alembic migration succeeded through
`0002_trades`. Each test cloned the migrated table into a unique private schema and
removed it afterward. Final SQL confirmed revision `0002_trades`, zero rows in
`public.trades` and zero leftover `test_trades_*` schemas. Original Compose API,
PostgreSQL and Redis container IDs `b379ae85c220`, `8656644dd0ac` and `bec035733c30`
matched the initial inventory and remained healthy after the checks.

Initial sandbox access to Docker was denied and uv could not persist interpreter
cache files. Execution-tool escalation enabled the checks above. The first focused
offline run passed all 154 listing tests, with 37 integration cases deselected;
initial lint/format checks identified six line-length/format issues. Formatting and
the descriptions were corrected before the complete passing check run. No failing
functional test was observed.

Independent read-only review by GPT-6 Astra, medium found no actionable findings
in the implementation, tests or documentation. The reviewer independently ran
`git diff --check`, which passed; the review did not rerun the toolchain, pytest
suites or database checks.

After review, cleanup verified the disposable container's full ID and ownership
label and confirmed its single anonymous volume was attached only to that owned
container. Cleanup removed that container and volume. Post-cleanup queries found
no owned container or anonymous volume remaining. Original API/PostgreSQL/Redis
container IDs listed above still matched and all three services remained healthy.
Final `git diff --check` passed. No full-suite rerun was needed for this
documentation-only review/cleanup update.

## Additional local checks completed

The user subsequently authorized production-image, live TCP HTTP, dependency
outage/recovery and installed Ollama checks. These completed on October 23, 2026,
using the prescribed coder workflow. No application changes were needed. These
are additional checks; the 359 offline and 71 real PostgreSQL integration results
above belong to the earlier implementation run and were not rerun for this
evidence/documentation-only follow-up.

- `docker compose config --quiet` passed for the isolated configuration. The
  unchanged production Dockerfile built with `uv sync --locked --no-dev` into
  separate image `marketlab:week7-local-check`. Runtime inspection confirmed Linux
  Python 3.13.17, UID 10001 and the existing Uvicorn `--loop asyncio --no-access-log`
  command. Host harnesses used the project's Python 3.13.7 `.venv` and existing
  dependencies. Initial sandbox Docker access was denied; execution-tool escalation
  enabled these checks.
- Isolated Compose project `marketlab-w7-local-20261023` used its own network,
  volumes and image, with loopback ports API 62679, PostgreSQL 62680 and Redis 62681.
  An override and empty interpolation environment file under ignored
  `artifacts/week7-local/` preserved repository configuration. Fresh Alembic
  migrations reached `0002_trades`; PostgreSQL, Redis and API became healthy.
- The real TCP harness passed **534 HTTP checks**: 245 healthy, 74 Redis-down,
  74 Redis-recovered, 67 PostgreSQL-down and 74 PostgreSQL-recovered. Every request
  asserted its preserved `X-Request-ID` response header. Saved request parameters
  were copied when recorded and checked against separate snapshots after each
  phase, including mutable traversal cursor updates. The unchanged
  `scripts/api_smoke.py` separately passed four endpoint checks while healthy,
  during Redis outage and after final PostgreSQL recovery: 12 additional checks.
- Time-filter coverage included each one-sided bound, two-sided ranges, positive
  and negative equivalent offsets encoded by the HTTP client, year 1/year 9999
  endpoints, exact inclusive/exclusive microsecond boundaries and an empty time
  interval selection. Mixed-case and punctuation IDs were deliberately out of
  timestamp order. Traversals used page sizes 1/2/3/500 and checked exact returned
  IDs, envelope, matching-only cursor, exactly full terminal pages and UTC/decimal
  serialization. Combined symbol/time/ID conditions covered interleaved excluded
  symbols and timestamps, missing and partial symbols, nonexistent boundaries,
  boundaries belonging to excluded records and boundaries beyond the final match.
- Both time parameters independently rejected 19 malformed or overflowing values,
  including missing seconds/timezone, lowercase separators, whitespace, excessive
  precision, invalid calendar/time values and offsets, epoch text and UTC overflow.
  Three equal/reversed ranges included equivalent instants represented with
  different offsets. These same 41 invalid queries returned `422` in every phase,
  including while PostgreSQL was stopped, providing live evidence of validation
  before database access.
- A two-sided, exact-symbol first page was followed by another committed HTTP
  import. Its next page saw the new matching ID beyond the cursor and excluded
  newly committed rows before the cursor, for another symbol, below the inclusive
  lower bound and at the exclusive upper bound. This checks current committed
  data between requests; it does not claim an overlapping transaction or a
  cross-page snapshot. Overlapping uncommitted imports remain covered by the
  earlier 71-test PostgreSQL integration run.
- Preserved HTTP behavior included unfiltered default 100 and maximum 500 pages,
  complete page-size-73 traversal, exact-symbol traversals at size 17, strict
  invalid symbols/pagination, JSON/CSV import and exact-ID lookup, decimal strings
  and UTC timestamps, case-sensitive/missing IDs, duplicate rollback in both
  formats, unsupported media types, an exact 1 MiB empty JSON body and oversized
  fixed-length/chunked JSON and CSV bodies. The isolated dataset ended with 536
  deliberately synthetic records, including time-bound and commit-between-pages
  cases.
- Stopping only isolated Redis produced HTTP `200`/degraded readiness, with Redis
  down and PostgreSQL, storage and host Ollama up. Unfiltered, exact-symbol and
  time-filtered reads and exact-ID lookup retained expected results. Restart
  restored ready dependency states and the same reads.
- Stopping only isolated PostgreSQL produced HTTP `503`/not_ready. Unfiltered,
  exact-symbol, each one-sided bound, two-sided and fully combined filtered
  listings, exact-ID lookup and a nonempty import returned only
  `{"detail":"Trade database unavailable"}`. Empty JSON/CSV imports still returned
  zero; invalid pagination, symbol, timestamp and time-range queries still returned
  `422`. Recovery restored readiness, all filtered traversals, unfiltered ID
  order/cursor and exact decimal/UTC values.
- Logs collected after an additional 12-second recovery delay contained no
  unhandled future/task warnings, `gaierror`, tracebacks or unexpected error lines.
  PostgreSQL's two duplicate-key errors were expected from rollback checks;
  Alpine initialization's locale warning was expected. Final SQL confirmed
  revision `0002_trades`, 536 synthetic rows and zero `test_trades_*` schemas.
- The unchanged `scripts/ollama_smoke.py` passed against already installed host
  Ollama 0.40.9 and `qwen3.5:4b-q8_0` (4.2B, Q8_0), validating
  `{"status":"ok","value":2}` in 5.5771 seconds, including a 5.2677-second model
  load. Model digest:
  `e15635ee93129fd2086640926e900c37589c5167561104abc3914bd6644c7e07`.
  No model download or update was performed. Container readiness independently
  verified host Ollama connectivity. Recorded memory figures are snapshots,
  not peaks.

Original API/PostgreSQL/Redis IDs `b379ae85c220`, `8656644dd0ac` and `bec035733c30`
matched before the build and after the checks, and all remained healthy. The
original PostgreSQL data was not accessed. Harnesses, phase records, build/runtime
logs, model output, ownership snapshots and `evidence-summary.json` are retained
only under ignored `artifacts/week7-local/`.

Independent read-only review by GPT-6 Astra, medium found no actionable findings.
The reviewer inspected the harnesses, raw phase records, build/runtime evidence,
logs, model output and this report, reconciled the 534 HTTP checks and 12 separate
API smoke checks, and independently ran `git diff --check`. The review did not
rerun Docker, HTTP requests or model generation.

After review, cleanup verified Compose ownership labels, resource names and the
separate image tag for all isolated containers, network and named volumes, and
verified that the anonymous Redis volume was attached only to owned containers.
Cleanup removed all four isolated containers (including the completed migration
container), the network, both named volumes, the anonymous Redis volume and the
separate image tag. `cleanup-evidence.json` records empty post-cleanup inventories,
no remaining anonymous volume, image-tag removal and matching healthy original
API/PostgreSQL/Redis container IDs before and after cleanup. Ignored verification
evidence remains available. Final `git diff --check` passed. No full-suite rerun
was needed for this evidence/documentation-only follow-up.

## Limits

Hosted GitHub Actions and a separate Linux offline/integration test-suite run have
not been rerun for week 7. The earlier Windows offline/integration suites and the
additional Linux production build, live TCP/outage/recovery checks and installed
model generation described above passed. No changes were committed or deployed to
the original local Compose stack. Returned pages are bounded without a
large-dataset query-performance guarantee; no index was added.
