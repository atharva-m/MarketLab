# Week 6 verification

Date: October 23, 2026. Environment: Windows, project `.venv`, Python 3.13.7,
unchanged locked dependencies. Implementation uses the requested coder (GPT-6.1 Sol,
high), followed by independent read-only review by GPT-6 Astra, medium.

## Implemented scope

`AGENTS.md` records the approved week 6 scope. The existing `GET /trades` route and
`list_trades` service accept optional exact `symbol` filtering with the same symbol
pattern used by `Trade`. Invalid symbols are rejected before database access. There
is no trimming, case conversion, partial matching or symbol list support. SQL applies
symbol equality before the bounded `limit + 1` fetch, and only matching records
determine the page and cursor. Omitting symbol preserves unfiltered browsing.

Explicit `C` collation for trade-ID ordering and boundary comparison, exclusive
nonexistent boundaries, decimal strings, UTC timestamps and generic database `503`
responses remain in place. README, OpenAPI and the week 6 filtering contract document
filtered traversal, retaining the symbol across pages, errors and current committed
data semantics. No migration, index, dependency, lockfile, infrastructure or CI changes
were made. The five-field trade contract's validation and serialization are unchanged.

## Check results

The complete `.\scripts\check.ps1 -Integration` passed with `uv run --locked`:

- Ruff lint and formatting passed.
- Strict mypy passed for 12 source files.
- **286 offline tests passed**, zero skips; 51 integration tests deselected.
- **51 real PostgreSQL integration tests passed**, zero skips; 286 offline tests deselected.
- `git diff --check` passed.

These retain all week 1–5 regression cases and add 40 offline plus eight integration
cases. Offline checks cover parameterized SQL equality before `LIMIT`, explicit `C`
ordering/comparison and `limit + 1` at sizes 1/100/500 with and without symbols or
boundaries; invalid symbols before connection; route argument forwarding and worker
execution; empty results; decimal/time serialization; generic errors; observability
and the symbol's OpenAPI constraints.

Real PostgreSQL checks exercise interleaved matching/nonmatching symbols and related
symbol names; mixed-case and punctuation ID ordering; page sizes 1/2/3/500; full,
final and empty pages; nonexistent and nonmatching-symbol boundaries; omitted-filter
compatibility; year 1/year 9999 UTC timestamps under Honolulu/Kiritimati sessions;
exact decimal limits; and real missing-table failures mapped to redacted `503`.
Invalid symbol queries still return `422` while that table is unavailable. A writer
holds uncommitted rows while a separate HTTP read runs; the rows remain invisible,
and later reads see newly committed matching rows beyond the prior boundary. Rows
before the boundary and nonmatching rows are omitted from that traversal.

Integration used an isolated `postgres:17-alpine` container,
`marketlab-w6-postgres-20261023`, on random loopback port 62583, labeled with the week 6
ownership value. Fresh Alembic migration succeeded through `0002_trades`. Tests cloned
the migrated trade table into per-test schemas and removed them afterward. Final SQL
confirmed revision `0002_trades`, zero rows in `public.trades` and zero leftover
`test_trades_*` schemas. The original Compose API/PostgreSQL/Redis containers retained
IDs `b379ae85c220`, `8656644dd0ac` and `bec035733c30` and remained healthy.

Initial sandbox attempts could not persist uv interpreter-cache files or access
Docker; execution-tool escalation allowed the complete checks above. The first
focused offline run passed 80 cases and failed one new OpenAPI assertion that assumed
nullable string length constraints were outside `anyOf`. The test was corrected to
the actual schema structure; the complete passing run includes that correction.

Independent read-only review found no actionable findings. This was an inspection
of implementation, tests and documentation; the reviewer did not rerun checks.

After review, cleanup verified the disposable container's full ID and ownership
label, checked that its single anonymous volume was attached only to that container,
and removed only the owned container and volume. Post-cleanup inventories confirmed
no owned container or volume remained. The original API/PostgreSQL/Redis container
IDs listed above still matched and all three services remained healthy. Final
`git diff --check` passed. No full-suite rerun was needed for this documentation-only
review/cleanup update.

## Additional local checks completed

The user subsequently authorized production-image, live TCP, outage/recovery and
installed Ollama checks. These completed on October 23, 2026, with the requested
coder and execution-tool escalation for Docker and host networking. No application
changes were needed. The following results are additional checks; the full offline
and PostgreSQL integration suite counts above are from the earlier week 6 run.

- `docker compose config --quiet` passed for the isolated configuration. The
  unchanged production Dockerfile built successfully with `uv sync --locked --no-dev`
  into the separate tag `marketlab:week6-local-check`. The image runs Linux Python
  3.13.17 as UID 10001 with the configured Uvicorn `--loop asyncio --no-access-log`
  command. Host harnesses used the project's Python 3.13.7 `.venv` and existing
  dependencies.
- The isolated Compose project `marketlab-w6-local-20261023` used its own network,
  volumes and image, with random loopback ports API 49889, PostgreSQL 49890 and Redis
  49891. An override and empty interpolation environment file under ignored
  `artifacts/week6-local/` preserved repository configuration. Fresh migrations
  reached `0002_trades`; PostgreSQL, Redis and API became healthy.
- The real TCP harness passed **168 HTTP checks**: 113 healthy, 11 Redis-down,
  11 Redis-recovered, 22 PostgreSQL-down and 11 PostgreSQL-recovered. Each request
  checked its preserved `X-Request-ID` response header. The unchanged
  `scripts/api_smoke.py` also passed its four endpoint checks while healthy, during
  the Redis outage and after final PostgreSQL recovery; these 12 checks are separate
  from the 168-check harness count.
- Healthy coverage included OpenAPI's optional `symbol`, exact matches among
  interleaved `SYN.A`, `SYN.B` and related `SYN.AA` records, no partial matches for
  `SYN`, a valid missing symbol, mixed-case and punctuation ID order, complete
  filtered traversal with page size 17, full terminal pages, and exclusive
  nonexistent/nonmatching/beyond-end boundaries. Omitted-filter default 100 and
  maximum 500 pages and page-size-73 full traversal retained week 5 behavior. Nine
  invalid symbols covered empty, lowercase, leading/trailing spaces, comma lists,
  punctuation/space, excessive length, Unicode and a newline, all returning `422`.
- A filtered first page was followed by another committed HTTP import. The next
  page saw the newly committed matching row beyond its cursor, excluded a newly
  committed matching row before that cursor and excluded a nonmatching row beyond
  it. This verifies current committed data between requests; it does not claim a
  cross-page snapshot or overlapping transaction test. Overlapping transactions
  remain covered by the earlier PostgreSQL integration run.
- Prior HTTP behavior checked JSON/CSV imports and exact retrieval, decimal strings
  and UTC timestamps, case-sensitive/missing IDs, invalid pagination, duplicate
  rollback in both formats, unsupported media types, exact 1 MiB empty JSON and
  oversized fixed-length/chunked JSON and CSV bodies. The initial dataset contained
  513 synthetic records, followed by five deliberate commit-between-pages records.
- Stopping only isolated Redis produced HTTP 200/degraded readiness with Redis
  down and PostgreSQL, storage and host Ollama up. Unfiltered listing, exact lookup
  and all five exact-symbol queries returned the expected data. Restart restored
  ready dependency states and the same read results.
- Stopping only isolated PostgreSQL produced HTTP 503/not_ready with PostgreSQL
  down. Default/bounded and filtered/bounded-filtered listings, exact lookup and a
  nonempty import returned only `{"detail":"Trade database unavailable"}` with
  HTTP `503`. Valid empty JSON/CSV imports still returned zero and invalid
  pagination plus all nine invalid symbols returned `422`. Recovery restored
  readiness, filtered results, unfiltered order/cursor and exact decimal/UTC data.
- Logs collected after an additional 12-second recovery delay contained no
  unhandled future/task warnings, `gaierror` messages, tracebacks or unexpected
  error lines. PostgreSQL's two duplicate-key errors were expected from deliberate
  rollback checks; Alpine initialization's `no usable system locales were found`
  warning was expected. Final SQL confirmed `0002_trades`, 518 deliberate synthetic
  rows in the isolated public trade table and zero `test_trades_*` schemas.
- The unchanged `scripts/ollama_smoke.py` passed against already installed host
  Ollama 0.40.9 and `qwen3.5:4b-q8_0` (4.2B, Q8_0), validating
  `{"status":"ok","value":2}` in 5.6429 seconds, including a 5.3288-second model
  load. Model digest:
  `e15635ee93129fd2086640926e900c37589c5167561104abc3914bd6644c7e07`.
  No model download or update was performed. Container readiness separately
  verified host Ollama connectivity. Memory values are snapshots, not peaks.

Independent evidence review identified a recorder issue in the ignored harness:
it retained mutable request-parameter dictionaries by reference, so later cursor
updates changed some earlier entries in the saved `params` metadata. HTTP requests
and their live response assertions were unaffected; the original five phase
records are preserved with this metadata limitation. The recorder now copies
parameters when recording each request. A separate, read-only supplemental run
passed **39 HTTP checks**, including complete `SYN.A`, `SYN.B` and `SYN.AA`
traversals with page size 17, terminal pages and explicit assertions that every
saved parameter snapshot matches the request and the first page has no cursor.
It performed no mutations. Its evidence is retained separately as
`supplemental-filtered-recheck.json`; the 168-check original count is unchanged.
The independent reviewer verified the recorder correction and supplemental
evidence, resolved the finding and reported no remaining actionable findings.
This was a read-only review of the harness, saved results, logs and report,
rather than an independent rerun of the checks.

Original-container IDs and healthy states matched before the build and after the
checks: API `b379ae85c220`, PostgreSQL `8656644dd0ac`, Redis `bec035733c30`. The
original PostgreSQL data was not accessed. Harnesses, phase records, logs, model
output, ownership snapshots and `evidence-summary.json` are retained only under
ignored `artifacts/week6-local/`.

After review, cleanup verified the isolated containers' Compose ownership labels,
resource names and image tag; it also verified that the anonymous Redis volume was
attached only to owned containers. Cleanup removed all four isolated containers
(including the completed migration container), the network, both named volumes,
the anonymous Redis volume and the separate image tag. `cleanup-evidence.json`
records empty post-cleanup container/network/volume inventories, no remaining
anonymous volume, image-tag removal and matching healthy original-container IDs
before and after cleanup. Final `git diff --check` passed. No full-suite rerun was
needed for this evidence/documentation-only follow-up.

## Limits

Hosted GitHub Actions and a separate Linux unit/integration suite have not been
rerun for week 6. The earlier Windows offline/integration suites and the additional
Linux production build, live TCP/outage checks and installed-model smoke described
above passed. No commit or deployment to the original local Compose stack was
performed. Bounded returned pages do not imply a large-dataset query-performance
guarantee; no index was added.
