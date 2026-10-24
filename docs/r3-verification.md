# R3 verification — complete

Approved October 24, 2026. The R3 contract was written before implementation.
Implementation, full local acceptance, independent review and ownership-checked
cleanup are complete. No unresolved local R3 acceptance blocker remains. The
initial implementation request excluded commit/push; later October 24 publication
and hosted CI authorization is recorded below. R1/R2 contracts and historical
evidence remain intact; R4-R9 are backlog.

The prescribed implementation coder is GPT-6.1 Sol, high. A second prescribed
coder owns the independent reference/live acceptance harnesses and isolated
resources. Independent read-only review uses GPT-6 Astra, medium. Python 3.13,
dependencies, uv.lock, deployment and existing ingestion/trade modules are unchanged.

## Completed locked regression checks

The final reviewed `.\scripts\check.ps1 -Integration` passed:

- Ruff lint and formatting: 75 files.
- Strict mypy: 24 source files.
- 606 offline tests passed, zero skips, in 9.98 seconds.
- 132 real PostgreSQL tests passed, zero skips, in 35.56 seconds.

These include the retained 557 offline/124 PostgreSQL cases plus 49 new offline
and eight new PostgreSQL cases. Deselections are the other marker selection, not
additional passes. Existing non-failing Starlette/TestClient deprecation warnings
remain. Log: ignored artifacts/r3/full-checks-reviewed.log. Final documentation
format/whitespace checks are repeated after evidence edits; their closeout is
recorded below.

The focused 49 offline cases also passed in 1.92 seconds. They cover exact decimal
arithmetic, timestamp/numeric-ID ordering, boundaries, missing buckets, direct
5m/combined 1m agreement, overflow, 38-digit VWAP ratios, canonical responses,
cache TTL/envelope/size bounds, coalescing and recovery. Native timeout and caller
cancellation tests run an actual expensive DuckDB query and assert native close,
removed temporary directory and released capacity. Cancellation here means the
asynchronous service task; TCP disconnect is not guaranteed immediate cancellation.

The eight new PostgreSQL cases cover catalog visibility/rollback, unregistered
orphans, mismatched/competing versions, unchanged catalog and integrity checks
before warm cache hits. The full retained suites preserve migrations, leases,
fencing, retries, crash recovery, publication and synthetic trade behavior.

## Resolved execution and review findings

An initial full run passed 589 offline and 128 of 132 PostgreSQL cases. Four new
integrity tests used ordinary Path.rglob beyond Windows path limits; the fixture
artifacts themselves were valid. The tests now use the retained extended-path
utility. The complete final run above passed all cases. An earlier attempted final
check stopped at formatting after a concurrent acceptance-script edit; scripts
were formatted and the complete final run followed. Neither failed run is a pass.

Independent review found five actionable issues, all resolved with regression
coverage:

- Last-waiter cancellation left a doomed in-flight read joinable during cleanup.
  Detach it before waiting, retain retiring tasks for shutdown and keep capacity
  until native work finishes.
- Malformed cached timestamps could raise instead of becoming a miss. Validate
  dictionary/string shapes and exact metadata integer types before parsing.
- An ordinary Redis GET transferred oversized values before checking their size.
  Atomic GETRANGE now transfers at most cap plus one byte before parsing.
- VWAP used the source field's 20-integer-digit representation bound. Its separate
  schema/validator now supports 38 integer digits, preserving valid quote/base
  ratios while retaining checked decimal(38,18) source sums.
- The asynchronous Redis client was given the synchronous Retry class. It now
  uses redis.asyncio.retry.Retry with zero retries and explicit 100 ms deadlines.

The reviewer requested stronger cleanup assertions and summary fixture identity
coverage; both were added. Summary puts require an explicit completeness validator;
fixtures prove run/schema key separation and reject incomplete states. Actual
research summaries remain R4 work. Independent review found no remaining actionable
findings and independently passed all 49 new offline/eight new PostgreSQL cases
plus 149 retained R1/R2 cases (101 offline/48 PostgreSQL). The reviewer independently
reconstructed all 124 daily and both five-day response hashes from the independent
reference, checked both midnight comparisons, and read the actual catalog/head/
private-schema state. It audited the 62 post-read integrity records; it did not
repeat the full 230-million-row streaming scan or source downloads.

## Actual live cache and compatibility acceptance

The final fresh-process live run after the asynchronous Retry fix passed against
isolated owned services. The initial request in that final rerun hit a retained
cache key; it is not a new cold-MISS measurement. An earlier clean run observed
MISS/HIT. The final run independently proved Redis restart and actual eviction
MISS then HIT with identical numerical bodies.

The final run verified:

- A primed response remains identical through Redis outage with BYPASS, then
  recaches after restart. Redis has no persistence.
- Application restart re-verifies artifacts before a retained HIT.
- Actual allkeys-lru pressure evicts the target key; its absence is checked before
  the next MISS/HIT. This is not a DEL-based simulation.
- Legacy HTTP health/import/filtering/C ordering/transaction rollback, three CLI
  subprocess outcomes and durable historical fixture ingestion/reuse/CLI inspection.
- Full original R1 artifact readback with unchanged identity/manifest.

A separate actual Redis audit stored a 4 MiB value and verified the production
GETRANGE requests bytes 0..1048576, returns only 1048577 bytes and rejects it.
It also inspected the asynchronous zero-retry/100 ms client configuration.
Evidence: ignored live-complete.json, live-final-async-retry.log and
native-cache-bounds.json under artifacts/r3/.

An initial disposable Redis resource used a random host port that changed after
restart. The harness detected the mismatch, replaced only that owned resource
with a fixed loopback mapping and reran acceptance successfully. This resource
setup issue is retained in live-resource-rerun.json. Original services were not
restarted or used for tests.

## Full January analytical reconciliation

The independent streaming reference has fully verified all 62 retained R2
partitions against saved catalog/manifest/artifact/logical hashes, schema, counts,
UTC day, historical identity and exact OHLCV reference calculations before
restoring registrations into the owned disposable catalog. Inputs total
230,311,900 accepted rows. This is an R3 retained-data check, not a new download.

All 62 daily production queries passed for both intervals, reconciling every bar
against the independent streaming reference. The final audit matched all 124
canonical response hashes. Each interval separately reconciles the same
230,311,900 input records; these are not twice as many distinct input trades.

| Measurement | BTCUSDT | ETHUSDT | Total |
| --- | ---: | ---: | ---: |
| Daily partitions | 31 | 31 | 62 |
| Input records reconciled per interval | 135,946,515 | 94,365,385 | 230,311,900 |
| 1m bars | 44,640 | 44,640 | 89,280 |
| 5m bars | 8,928 | 8,928 | 17,856 |
| Empty buckets | 0 | 0 | 0 |

The 124 first reads observed 123 MISS and one HIT retained from live acceptance;
all 124 warm repeats were HIT, with identical bodies and zero BYPASS. Saved source
catalog mappings remain unchanged. The disposable catalog has 65 registrations:
62 retained historical versions plus three separately generated compatibility
fixture versions. Its six jobs/attempts belong to fixture checks, not new monthly
ingestion. No private test schemas remain. Evidence is under ignored
artifacts/r3/reference-complete.json, month-progress.json, evidence-audit.json and
catalog-final.json.

Production acceptance used two processes with one active read each (two active
reads total) after initial single-process work. The 53 remaining-partition worker
phase took 1,101.676 seconds; it excludes the nine earlier completed partitions
and final cross-day/post-read checks. This is not a complete-run wall time or a
benchmark. The final cross-day invocation reuses completed daily checkpoints;
its own recorded wall_seconds describes only that invocation.

The largest partition, BTCUSDT January 20 with 11,597,937 records, passed both
intervals exactly. Its first 1m read plus warm repeat took 118.33 seconds including
full integrity verification; the subsequent 5m read plus warm repeat took 1.83
seconds. These are combined request timings, not isolated DuckDB timings. The
60-second deadline applies to DuckDB execution, not cold full verification. No
native query timeout or resource-limit failure occurred. Hardware was an Intel
Core i9-14900HX with 24 cores/32 logical processors, Python 3.13, existing locked
libraries, one DuckDB thread/query, 512 MiB memory setting and 2 GiB spill cap.

Final cross-day reads also passed: each symbol's five-day 5m query returned 1,440
bars matching daily reference concatenation; each midnight-crossing 1m query
returned ten matching bars. All four were MISS. Reversed input version order
produced the canonical day order. After analytical reads, all 62 source manifests
and Parquet files retained their recorded hashes. The final cross-day/post-read
invocation took 210.1456 seconds, excluding the earlier daily phases. Evidence:
ignored artifacts/r3/month-complete.json. This is not a complete-run benchmark.

Measured peak memory is unavailable. Hardware/configuration metadata is retained;
no peak or broad performance claim is made. Redis acceptance retained 256 MiB
allkeys-lru/no persistence with a 384 MiB disposable container memory limit,
providing 128 MiB configured headroom; this is configuration, not a peak measurement.

## Independent closeout and owned-resource cleanup

After independent review cleared the completed evidence, cleanup at
2026-10-24T06:56:57.8990143Z (02:56:57 America/New_York) checked exact container
IDs, ownership label marketlab.r3.owner=r3-20261024 and tmpfs/no persistent mounts,
then removed only the three owned containers:

- PostgreSQL f5b95fdb98dc6f5c577342d1243d7b986bfb256e7c03a0c0c6276b3ab26fca76.
- Main Redis ee80506962f327e50644365a09a927ee5c579e3c149494563d6eb7e4526169f1.
- Auxiliary live Redis f55765264de7563daa439260a1a51484b1fe1124af1870435ca1c16a18634a77.

Zero owned containers or API processes remain. The initial owned anonymous volume
was verified absent. Original API b379ae85c220, PostgreSQL 8656644dd0ac and Redis
bec035733c30 stayed at the same IDs and healthy before/after. Original services/data
were not used for acceptance or altered. Records: ignored artifacts/r3/
pre-cleanup.json and cleanup.json.

Historical R1/R2 artifacts and all R3 reference/results/catalog/job snapshots/logs
remain under ignored artifacts/. The disposable catalog was removed with its
owned tmpfs PostgreSQL; this does not claim a production catalog restoration.
The local acceptance working tree was based on HEAD
bbcc0569177e302982b4693004a07e530cafa4c1 plus then-uncommitted R3 changes,
not an R3 commit. Final locked Ruff lint/format,
strict UTF-8 and git diff whitespace checks passed after documentation closeout.
No runtime changes followed the successful complete regression run. At this local
implementation closeout hosted CI had not run and no commit/push had occurred
under the initial request. Later publication authorization and actual outcomes
are recorded below. R4-R9 remain unauthorized.


## Later publication and hosted CI authorization

Later on October 24, 2026, after the completed local implementation/verification,
independent review and owned-resource cleanup, the user explicitly authorized
committing/pushing the verified R3 changes, checking hosted CI, fixing actual
R3-only CI failures through the prescribed coder/reviewer workflow and documenting/
publishing actual results and blockers. This supersedes the initial no-commit/push
instruction without authorizing R4-R9 or inclusion of archives/artifacts/data,
credentials, environments or weights in Git.

The local closeout above remains historical evidence. At the publication-authority
documentation update no R3 commit/push or hosted result had yet been observed.
Actual later publication and hosted evidence are recorded below; local totals do
not substitute for hosted tests.


## Published R3 and passing hosted CI

The verified R3 changes were committed/pushed normally to origin/main as
`54f15d3c4312248f1ec8beda6bca805d4e37bb38`, exactly 15 scoped source, test, acceptance-script and
documentation files. No market archives/artifacts/data, credentials, environments
or weights were included. Dependencies/lockfile, deployment, workflows and retained
R1/R2 ingestion/trade modules were unchanged.

[hosted CI run 40072552311](https://github.com/atharva-m/MarketLab/actions/runs/40072552311)
completed successfully for that exact SHA. Retrieved run/job metadata and full
job logs confirm:

| Hosted job | Actual result |
| --- | --- |
| Ubuntu quality | Ruff lint/format passed (75 files), strict mypy passed (24 sources), 606 offline tests passed in 6.80 seconds |
| Windows quality | Ruff lint/format passed (75 files), strict mypy passed (24 sources), 606 offline tests passed in 14.44 seconds |
| Linux integration | 132 real PostgreSQL tests passed in 26.78 seconds, plus locked setup, Compose validation, API image build/startup, API smoke, healthy Redis/optional-outage smoke and cleanup |

No tests were skipped. The 132/606 deselections are the complementary marker
selection, not additional passes. Only integration's failure-conditional Logs
step was skipped, as expected on success. No R3 CI failure or fix was required.
Exact metadata and logs are retained under ignored
artifacts/r3-ci/54f15d3c4312248f1ec8beda6bca805d4e37bb38/.

Hosted CI does not repeat the actual 62-partition/230,311,900-row retained-data
reconciliation or the real R3 primed-bar-response outage/eviction harness. Its
Redis outage step verifies optional-dependency health/API smoke. The stronger bar
response outage/eviction, month, cross-day and unchanged-artifact evidence remain
the separate completed local gates above. No actual model generation or measured
peak memory claim follows from CI.

No unresolved R3 publication/CI blocker remains. This outcome update changes
only documentation; no runtime, test, dependency, deployment or workflow fix was
needed. Final locked lint/format, strict UTF-8 and whitespace checks were repeated
after these documentation edits. R4-R9 remain unauthorized; market data/artifacts,
credentials, environments and weights stay outside Git.
