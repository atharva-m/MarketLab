# R2 verification — complete

Verification dates: October 23-24, 2026 (America/New_York); approval October 23.

Approved scope implementation, full local regressions, actual historical gates,
independent core/final evidence review and owned-resource cleanup passed. No
unresolved local acceptance blocker remains. At implementation closeout no
commit/push had been performed or authorized. The later October 24 publication
authorization and actual hosted CI outcomes are recorded below.

The prescribed coder is GPT-6.1 Sol, high; independent reviewer GPT-6 Astra,
medium. An additional prescribed coder owns the new job acceptance tests.
Python 3.13 and existing locked dependencies are retained. New manifests record
Git HEAD `bbf4fdb6a7e5dee0549a46d61c9497f878adbed4`, dirty state true, and unchanged
uv.lock SHA-256 `730f02bec94d1f824a2cadf74f60cf5dcc246faa55004d5d060b92931224618f`.
This is provenance for uncommitted working-tree execution, not an R2 commit. R1 historical results
remain in r1-verification.md; they are not counted as new R2 passes.

## Completed full regression checks

The final locked `.\scripts\check.ps1 -Integration` passed:

- Ruff lint and formatting (64 files) passed.
- Strict mypy passed for 19 source files.
- **557 offline tests passed**, zero skips (9.06 seconds).
- **124 real PostgreSQL tests passed**, zero skips (32.74 seconds).
- `git diff --check` passed; only expected Windows line-ending warnings appeared.

These totals include the existing R1/legacy suites and 41 new offline / 35 new
PostgreSQL cases. Initial sandbox-only offline execution stalled without results;
its exact owned pytest process identities were checked and stopped before this
completed escalated locked run. It is not counted as a pass. Existing non-failing
Starlette/TestClient deprecation warnings remain. Full log is ignored
artifacts/r2/full-checks.log.

## Current evidence

- Additive migration 0004_ingestion_jobs applied to isolated owned PostgreSQL.
- All 13 existing R1 dataset PostgreSQL cases passed after the core change.
- New focused job suite: all 41 offline and 35 PostgreSQL cases passed.
  The independent reviewer reran all 76 successfully, without skips.
- Five actual CLI subprocess outcomes passed: three legacy trade lookup/listing/
  missing-ID cases and historical ingest/inspect through durable inline jobs.
  Historical ingest retains its original two-key successful output and the original
  R1 dataset identity with 1,516,556 rows. HTTP health/import/list/transactional
  invalid-batch assertions also passed. The retained original R1 artifact passed
  complete manifest/Parquet readback with unchanged manifest hash and identity.
  Evidence: artifacts/r2/legacy-results.json and dataset-cli-results.json.
- Actual initial ingestion completed all 62 official daily partitions with full
  registered-artifact readback. A separate fresh-key source download/recheck
  completed all 62 partitions with the same exact dataset versions; the catalog
  remains at 62 versions. All 124 monthly jobs succeeded on attempt 1.

## Resource isolation and evidence

Owned container marketlab-r2-postgres-20261023, full ID
9619cafb2b439e019b60bd105248c798c7d0810bf60f6fc6e1d648cb5ee64773,
label marketlab.r2.owner=r2-20261023, tmpfs PostgreSQL, random IPv4 loopback port
57393. Original services were inventoried first; no existing database was used.
Ignored artifacts/r2/resource-ownership.json records identity/mounts. Cleanup completed after all verification/review; see the final cleanup record
below. Market data/artifacts remain ignored.

## Resolved execution issues and review findings

Initial sandbox TCP was denied; escalated migrations/PostgreSQL checks passed.
Initial strict mypy and formatting findings were repaired before focused checks.
Reviewer identified source-routing ambiguity, hidden transient DB classification,
synchronous client/limit claim races, graceful shutdown and inline resume/retry
requirements. Core fixes preserve source modes/input identity, inspect chained safe
DB error codes, isolate inline claims, drain worker signal shutdown, and provide
explicit inline resume with bounded durable retries. During review the disposable
public source-mode CHECK was synchronized with the revised 0004 migration to allow
isolated inline calls. The final migration itself was then exercised on fresh/
populated isolated schemas with real constraints and preservation checks; the
manual test-resource update is not a substitute for that migration acceptance.
Each material fix received focused regression coverage and passed the final
complete suites documented above.

No peak memory measurement has been captured; no peak claim is made. Hosted CI
was not run during local implementation closeout. Publication/CI verification is
now complete with actual passing hosted results below; no Ollama/caching/analytics
claim is made.


## Acceptance coverage

| Gate | Actual result |
| --- | --- |
| Submission | 62 children, exact date/symbol validation, canonical key reuse/conflict and concurrent key submission passed |
| Database | Fresh migration plus populated R1 upgrade/downgrade preservation passed; actual CHECK/unique/FK constraints tested |
| Claims/leases | Real SKIP LOCKED held-row and simultaneous claims, DB-time renewal/expiry, three-crash budget and stale mutation fencing passed |
| Retries | Three-attempt transient budget, permanent/unknown stop, HTTP guidance, real 55P03 publication timeout recovery passed |
| Inline compatibility | Supplied client cannot be stolen, transient then success uses same job, explicit crash resume/reuse and source mismatch rejection passed |
| Publication | Existing R1 same/changed-source/concurrent/corruption tests passed; job/catalog atomic rollback and stale/lost-heartbeat gates passed |
| Process recovery | Actual killed subprocesses after claim, during staging, after rename/before commit and after commit recovered without incomplete discovery |
| Shutdown | Stop flag drains current publication and leaves following job queued; force-kill uses lease recovery |
| Historical month | All 62 initial partitions plus all 62 fresh-key downloads/readbacks/reuses passed; 62 catalog versions |
| Independent review | All actionable findings resolved; 76 new tests and original R1 focused tests independently passed; final evidence review passed |

The review found and tests now cover a renewal-loss race immediately before the
success update; lost ownership rolls back catalog/job success and leaves only an
adoptable orphan. Source Retry-After accepts delta-seconds and HTTP-date, capped
at 3,600 seconds. These are implemented behaviors, not skipped gates.


## Actual initial January publication

Official daily archives/checksums were downloaded for each symbol/day in
[2025-01-01T00:00:00Z, 2025-02-01T00:00:00Z). All 62 checksum-verified jobs
published complete Parquet and were independently reopened via catalog inspection
for full schema/hash/logical/count readback. Every initial job succeeded on attempt
1. No exact duplicates or conflicts occurred; raw and accepted totals match.

| Measurement | BTCUSDT | ETHUSDT | Total |
| --- | ---: | ---: | ---: |
| Daily partitions | 31 | 31 | 62 |
| Raw/accepted rows | 135,946,515 | 94,365,385 | 230,311,900 |
| Downloaded ZIP bytes | 1,201,892,703 | 901,948,538 | 2,103,841,241 |
| Expanded CSV bytes | 10,425,765,378 | 7,098,248,143 | 17,524,013,521 |
| Published Parquet bytes | 1,732,856,545 | 1,172,244,306 | 2,905,100,851 |
| Accumulated ingestion seconds | 4,348.6670 | 2,908.7372 | 7,257.4042 |

These durations include each job's download/normalization/pre-publication
verification/publication and exclude its additional independent post-publication
readback. Jobs ran concurrently, so accumulated seconds are not wall time or a
performance benchmark. Peak memory was not measured. The largest actual daily row
count was BTCUSDT January 20 with 11,597,937 records, below the retained 20-million
limit. Requested partition coverage does not prove gap-free exchange coverage.

The initial worker executed two jobs and exited; a new worker process resumed the
same persistent submission, with a second explicitly launched local worker sharing
remaining claims. All jobs and dataset identities remained durable. Per-partition
source URLs/checksums, archive/expanded/Parquet sizes, counts, logical/file hashes,
version IDs and durations are retained in ignored historical-events.jsonl and
initial-status.json. Final catalog/status snapshots were captured before
owned database cleanup. Source bytes/artifacts are not Git content.

## Fresh-source reuse and final durable snapshot

All historical worker sessions exited successfully (initial second worker,
primary orchestrator and second recheck worker all exit 0). The final same-key
summary refresh performed no remaining ingestion work and confirmed both durable
submissions complete. Recheck downloaded another 2,103,841,241 archive bytes;
all published provider hashes matched, all 62 exact source/version mappings were
reused, and full pipeline readback reconciled the same 230,311,900 rows.
Accumulated recheck job time was 2,689.7358 seconds across concurrent workers,
including download and pipeline readback; it is not wall time or a benchmark.
Each recheck event separately records fresh retrieval timestamp/hash/size and
download duration, preserving the original immutable manifest provenance.

Ignored artifacts/r2/catalog-final.json saves migration head 0004_ingestion_jobs,
all 62 catalog registrations, both complete 62-job submissions, job/attempt rows,
and repeated-key identity proof. There are 125 succeeded jobs/125 attempts:
124 monthly jobs plus one separate synchronous historical CLI compatibility job.
The catalog remains at 62 versions. The public legacy table contains only the
three deliberate compatibility rows in this disposable database; zero private
test schemas remain. historical-results.json and evidence-audit.json both confirm
all 62 initial/recheck mappings, complete status and no failure events. No provider
or data-limit blocker occurred. These metadata snapshots and immutable artifacts
are retained locally; archives/market records are not tracked Git files.

A final document-encoding check found two newly inserted Windows cp1252 en-dash
bytes; these were converted to ASCII hyphens and all changed documents are now
strict UTF-8. This was documentation only; no application/test changes followed
the successful full regression run.


## Independent closeout and owned-resource cleanup

Independent read-only GPT-6 Astra, medium review found no remaining actionable
findings. It independently passed all 41 new offline / 35 new PostgreSQL cases and
the original R1 focused cases (60 offline / 13 PostgreSQL). Final evidence review
reconciled all 62 initial/fresh-source mappings, source retrieval/hash/size
agreement, all 62 catalog manifest hashes, 125 succeeded jobs with closed attempts,
head 0004, repeated-key identity and zero private test schemas. The reviewer did
not independently repeat the complete historical downloads or full 230-million-row
readback; those results are from the completed coder-run acceptance harness.

At 2026-10-24T05:38:12.7147958Z (October 24 America/New_York), cleanup verified the
exact owned container ID/name/ownership label, tmpfs storage and zero persistent
mounts, then removed only that container. Zero owned containers remain. Original
API/PostgreSQL/Redis container IDs b379ae85c220, 8656644dd0ac and bec035733c30 stayed
unchanged and healthy before/after. Original services/data were not used for
verification or altered. No persistent test volume existed. Immutable historical
artifacts, manifests, catalog/status snapshots and logs remain under ignored
artifacts/r2/. The disposable catalog itself was removed with its owned tmpfs
container; the saved snapshot preserves verification evidence. No production
catalog/deployment change is claimed. See resource-ownership.json and cleanup.json.

Final strict UTF-8 validation and git diff whitespace checks passed. Documentation
closeout followed successful application/tests without changing runtime code, so
no redundant full-suite rerun was made. Hosted CI was not run at this local
closeout, and peak memory remains unmeasured. R1 contracts/evidence remain intact;
R3-R9 are unauthorized backlog. Changes remained local and uncommitted/unpushed
at implementation closeout under the initial request.


## Later publication and hosted CI authorization

On October 24, 2026 the user explicitly authorized committing/pushing the verified
R2 changes, checking hosted CI, fixing actual failures within R2 and documenting
actual outcomes/blockers. This supersedes the earlier no-commit instruction and
does not authorize R3-R9 or inclusion of archives/artifacts/data, credentials,
environments or weights in Git. The initial working-tree provenance and local
verification above remain historical evidence, not hosted results.

The implementation commit/push and first hosted CI result are now observed below.
The passing replacement run is recorded below; local totals are not substituted
for hosted offline results, and scheduled/running checks are not represented as
passed.


## Initial hosted CI failure and scoped fix

The verified implementation was committed as
`8bfff40e8b431e2382640fb25e66b2d648520588` and pushed normally to `origin/main`.
Exactly the 16 scoped files were included; archives/artifacts/data, credentials,
dependencies/lockfile and deployment configuration were excluded.

[CI run 40067420625](https://github.com/atharva-m/MarketLab/actions/runs/40067420625)
was checked against that exact SHA. Actual outcomes:

- Ubuntu quality failed `ruff format --check .` on the Python fenced example at
  docs/r2-jobs.md:143. Ruff lint passed; mypy/offline pytest were skipped.
- Windows quality concluded **cancelled**, with its Ruff formatting step recorded
  failed on the same example. Mypy/offline pytest were skipped; this is not a pass.
- Linux integration **passed 124 PostgreSQL tests**, zero skips (25.92 seconds),
  plus locked setup, Compose validation, production API image build/startup, API
  smoke, healthy Redis/outage checks and cleanup. Its 557 deselected cases are
  not hosted offline passes.

The read-only inline-job discovery example was added after the successful local
full check. Later document closeout validated UTF-8 and Git whitespace, but did
not rerun Ruff for that new Python code fence. The locked formatter checks these
examples, so the earlier passing formatting result did not cover the late sample.
This was a missed final formatting check, not an application or dependency error.

The only fix reformats that documented Python example into Ruff's requested
multiline chaining layout. Repository-wide locked Ruff lint and formatting now
pass (64 files); no runtime/test/dependency/workflow changes were needed. A
sandbox uv-cache permission error during the rerun was resolved by the approved
escalated locked invocation, which passed. The first hosted run remains recorded
as failed; the subsequent passing replacement commit/run is recorded below.
Ignored artifacts/r2-ci/8bfff40e8b431e2382640fb25e66b2d648520588 contains the
run/job metadata and actual job logs, including hosted PostgreSQL count/timing.


## Passing replacement hosted CI

The reviewed example-format fix and failure record were committed/pushed as
`d22523aaafc2182fc411c1615ad615e0be24c771`.
[CI run 40067854743](https://github.com/atharva-m/MarketLab/actions/runs/40067854743)
completed successfully for this exact SHA. Retrieved run/job metadata and full job
logs verify:

| Hosted job | Actual result |
| --- | --- |
| Ubuntu quality | Ruff lint/format passed (64 files), strict mypy passed (19 source files), **557 offline tests passed** in 8.93 seconds |
| Windows quality | Ruff lint/format passed (64 files), strict mypy passed (19 source files), **557 offline tests passed** in 12.48 seconds |
| Linux integration | **124 real PostgreSQL tests passed** in 25.44 seconds, plus locked setup, Compose validation, production API image build/startup, API smoke, initially healthy Redis, actual Redis outage checks and cleanup |

No tests were skipped. The 124/557 deselected cases belong to the other pytest
marker selection and are not counted as passes. Only integration's
failure-conditional Logs step was skipped, as expected on success. The initial
Ubuntu failure/Windows cancellation remains preserved above; it is not relabeled
as passed. There is no remaining R2 hosted CI blocker.

The fix and this follow-up changed documentation only. No runtime/test,
dependency/lockfile, deployment or workflow changes were needed. The final local
locked Ruff lint/format checks were rerun after all documentation edits, including
Python fences, rather than relying on the earlier check before the example was
added. Actual hosted evidence is retained under ignored
artifacts/r2-ci/d22523aaafc2182fc411c1615ad615e0be24c771/.

Hosted CI does not repeat the actual provider month download or 230-million-row
readback; those are the separate completed local acceptance results above. It
does not run actual model generation. Peak memory remains unmeasured. Original
services/data and R1 behavior remain preserved; R3-R9 are unauthorized backlog.
Market data/artifacts, credentials, environments and model weights remain outside
Git. Final publication/evidence documentation is reviewed independently before
its authorized follow-up commit/push.
