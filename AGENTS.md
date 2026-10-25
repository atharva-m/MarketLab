# MarketLab contributor instructions

Historical completed scope is R2 in [ROADMAP.md](ROADMAP.md) and [R2 contract](docs/r2-jobs.md): durable PostgreSQL jobs and fenced publication for Binance Spot BTCUSDT/ETHUSDT daily trades covering [2025-01-01T00:00:00Z, 2025-02-01T00:00:00Z), 62 daily partitions. User approved this scope, documentation updates, prescribed coder/reviewer workflow, acceptance verification and honest results/blocker documentation. R1 is complete and must be preserved. R2 implementation, full verification, independent review and owned-resource cleanup are complete; see docs/r2-verification.md. The initial implementation request excluded commit/push. On October 24, 2026 the user subsequently authorized committing/pushing the verified R2 changes, checking hosted CI, fixing actual R2-only CI failures and documenting/publishing actual outcomes. Hosted CI passed for the reviewed documentation fix commit d22523aaafc2182fc411c1615ad615e0be24c771 in run 40067854743 after the initial formatting failure recorded in docs/r2-verification.md. Never commit archives/artifacts/data, credentials, environments or weights. R1-R4 are complete; R5 is now authorized under the current milestone below. R6-R9 remain unauthorized. Historical week 1-9 labels remain repository increments, not completion of original plan milestones. Read the full approved R2 contract and retained R1 contract before changes.

Retained R2 preservation requirements (R3 adds no schema): before R2 migration/code, document schema constraints, state transitions and fencing/publication protocol. Use existing locked Python 3.13 dependencies. Add additive submission/job/attempt schema; FOR UPDATE SKIP LOCKED claims, 10-second heartbeat, 60-second leases, monotonically increasing fencing tokens, three total attempts including crashes. Use database time. Match current owner/token/unexpired lease for mutations; stale workers cannot publish. Stage and fully verify artifacts before short bounded publication transactions; atomically register catalog and job success under current ownership. Retain R1 version advisory locks and orphan verification/adoption without overwrite. Only catalog-registered versions are discoverable.

Submission keys are idempotent for the same canonical request; conflicting reuse fails. Fresh keys permit source rechecks; identical source/transform/lock reuses R1 dataset identity and changed bytes create a new immutable version. Preserve R1 synchronous CLI/library entry points and output shape, routing through durable machinery without requiring a separate worker. Add separate bounded range submission, worker and job inspection commands. Partial month completion is explicit. Preserve exact normalization, source provenance, checksum-before-parse, historical identity, decimals/microseconds, stable numeric ordering, duplicate/conflict behavior and existing limits: 512 MiB compressed, 4 GiB expanded, 20 million rows, finite timeouts. No arbitrary URLs, paid providers, credentials, automatic fallback or hidden HTTP retry multiplication. Do not rewrite prior manifests or include job metadata in version identity.

Run offline and real PostgreSQL migration/preservation, submission, concurrent claim, lease/fencing, retry budget, process crash/recovery, publication rollback/visibility and corruption acceptance tests. R2 acceptance required actual official 62-partition ingestion, restart/resume, full readback/hash/count reconciliation, repeated submission and fresh-key same-source reuse. Record actual bytes/rows/attempts/times and measured peak memory only when available; unavailable provider/day leaves monthly acceptance incomplete. Run full locked lint/format/mypy/offline/PostgreSQL and focused legacy live API/CLI checks. Use isolated disposable resources, preserve user services/data, inspect ownership before cleanup. Update README, contract, verification and roadmap with actual outcomes. Never commit archives/artifacts/data, credentials, environments or weights.
Preserve every existing week 1–9 behavior: scaffold, environment, infrastructure, health, observability, CI, Ollama smoke, parsers/fixtures, five-field synthetic trade contract and existing trades table/global ID identity, transactional imports, exact-ID HTTP and CLI retrieval, content-type checks and streamed 1 MiB import limits. Preserve listing defaults/bounds, exclusive after_id including nonexistent boundaries, PostgreSQL C collation for case-sensitive ordering/comparison, exact symbols, strict timestamps, inclusive/exclusive time filtering, pre-database validation, matching-only pagination, decimal strings, UTC serialization and redacted errors. Preserve CLI option conflicts, loopback/configurable port, finite timeouts, disabled environment proxies/redirects, one-page defaults, bounded traversal, filter retention, cursor consistency, resume behavior and partial-output documentation. Pagination remains current-committed reads without a snapshot or performance guarantee.

R2 permits scoped historical ingestion/job modules, local entry points, immutable storage and additive migrations. Existing HTTP route contracts, trade CLI, dependencies/lockfile and deployment configuration remain unchanged; R3 expressly permits its additive /v1/bars endpoint/OpenAPI description. R2 excluded bars/DuckDB analytics and Redis caching; these are now authorized only under R3 below. R4 now authorizes only the research scope in docs/r4-research.md. Continue to exclude copilot/memos, UI/authentication, scheduling, automatic garbage collection, pre-January downloads and multi-host deployment/storage replication guarantees.

Use the coder (gpt-6.1-sol, high) for implementation, then reviewer (gpt-6-astra, medium) for independent read-only review. The coder resolves actionable findings and runs relevant checks. The user explicitly authorizes this delegation workflow. Preserve explicit later user model overrides. Local agent configuration does not change an already-running chat's model.

## Historical completed milestone: R3

R3 implementation, full local acceptance, independent review and ownership-checked
cleanup are complete; see [R3 verification](docs/r3-verification.md). Full checks
passed 606 offline/132 PostgreSQL cases. All 62 January partitions reconciled
230,311,900 records per interval, 89,280 1m/17,856 5m bars and 124 daily hashes;
live outage/eviction, cross-day reads and R1/R2 preservation passed. No unresolved
R3 blocker remains. Keep this scoped implementation intact. The initial request
excluded commit/push. Later on October 24, 2026 the user explicitly authorized
committing/pushing the verified R3 changes, checking hosted CI, fixing actual
R3-only CI failures through the prescribed coder/reviewer workflow and documenting/
publishing actual outcomes. This supersedes the initial publication restriction
without authorizing R4-R9 or inclusion of artifacts/data, credentials, environments
or weights. Verified R3 was committed/pushed as 54f15d3c4312248f1ec8beda6bca805d4e37bb38;
[hosted CI run 40072552311](https://github.com/atharva-m/MarketLab/actions/runs/40072552311)
passed for that exact SHA: 606 offline tests on Ubuntu and Windows, 132 real
PostgreSQL tests on Linux, quality/build/API/optional-Redis-outage/cleanup checks.
No R3 CI fix was needed. Local month/bar-cache evidence is separate from hosted
smoke coverage; see docs/r3-verification.md. No R4-R9 authorization follows.

User approved October 24, 2026 the detailed R3 scope in [ROADMAP.md](ROADMAP.md) and [R3 contract](docs/r3-analytics.md), documentation updates before code, prescribed coder/reviewer implementation, full acceptance and honest results/blockers. The initial no-commit/push restriction is superseded only by the later R3 publication authorization above. Read and preserve full R1/R2 contracts. Implement on-demand deterministic UTC 1m/5m bars over explicit registered January BTCUSDT/ETHUSDT versions; exact decimal arithmetic, numeric tie order, no filled missing bars. Add only GET /v1/bars/OpenAPI plus scoped modules/settings; no migrations, persistent bars or job changes. Use bounded fixed-template DuckDB, two expensive reads/process, actual interruption/cleanup, strict catalog verification. Implement roadmap Redis TTL/jitter/1 MiB/100 ms/no-retry/three-failure ten-second bypass, coalescing, metrics and real outage/eviction verification. Summary-cache fixture support only; research summaries remain R4. Full 62-partition independent streaming reconciliation, retained suites and live compatibility are required; isolate resources and preserve original services/data. No dependencies/lock changes, artifact rewrites, warm-up, scheduling, GC, UI/models/research or multi-host claims. R4-R9 remain unauthorized. Never include market data/artifacts, credentials, environments or weights in Git.


## Historical completed milestone: R4

User approved October 24, 2026 the detailed R4 proposal and authorized ROADMAP.md/
AGENTS.md updates, the full [R4 contract](docs/r4-research.md) before code, prescribed
coder/reviewer implementation, full acceptance and honest actual outcomes. The
initial request excluded commit/push; the October 25 publication authority below
supersedes that restriction. This approval supersedes earlier R4 exclusions only within this
contract; R5-R9 remain unauthorized. Preserve full R1/R2/R3 contracts and evidence.

Implement strict research-spec-v1, five-minute-only market_profile, cross_asset and
volatility_cluster, explicit January dataset/history selection and warm-up, Decimal80
research-numerics-v1, deterministic immutable results/summary/provenance, separate
additive research submissions/runs/attempts/results schema, database-time fenced
execution (10s heartbeat/60s lease/three attempts), short atomic publication, bounded
manual HTTP/CLI submission and reads, shared R3 analytical admission and resilient
summary cache. Numerical rules, limits and acceptance are fully specified in the
R4 contract and must not be silently reinterpreted. No pre-January downloads, models,
memos, UI, strategy/backtesting, scheduling, GC, dependency/lock/deployment changes
or multi-host guarantees. All retained suites, real DB/crash/cache tests, independent
62-partition numerical reconciliation and repeatability are required. Use owned
disposable resources, preserve original services/data, verify ownership before
cleanup. Document actual outcomes/blockers in docs/r4-verification.md, README and
roadmap. Never commit artifacts/data, credentials, environments or weights.

R4 implementation, full local acceptance, independent source review and owned
resource cleanup passed; see [R4 verification](docs/r4-verification.md). Final
locked checks passed 655 offline/152 real PostgreSQL cases. Independent fresh
streaming reconciled all 62 January partitions/230,311,900 trades/17,856 five-minute
bars; ten durable runs matched all reference result/summary hashes, including fresh
key repeats. BTC/ETH clusters numbered 31/33. Real crash/fencing/migration/cache/
outage/eviction and retained live compatibility passed. All source hashes and
original service IDs/health were preserved; owned resources were removed.

Retain the explicitly documented DB-clock environment limitation: isolated and
quiescent diagnostics captured backwards PostgreSQL wall time causing temporary
future eligibility/no immediate claim. Final full suites passed, but the clock
issue is not fixed. No host clock, retained runtime or test eligibility semantics
was altered. The actual month used the pre-replay-status-fix dirty source hash;
final metadata-only fix/readback/full-suite evidence is distinguished in verification.
Peak memory is unmeasured. At local closeout hosted R4 CI was unrun and commit/push
was excluded; the later publication authority below governs current work. Keep
this implementation intact and do not infer R5-R9 authorization.

## Authorized post-R4 clock follow-up: partial mitigation, unresolved

The user authorized investigating/fixing the clock environment with prescribed
coder/reviewer work, preservation and actual verification, no commit/push. See
[clock follow-up and incident](docs/r4-clock.md). In that follow-up R1-R4 application
eligibility, leases/heartbeats, attempts, fencing and publication stayed unchanged
(claims only were changed later; see the claim fix below). Ubuntu
timesyncd was stopped/disabled while built-in PHC synchronization converged.
Large steps diminished and actual job/lease checks passed, but dense sampling
still found Docker initd backwards steps: the clock is NOT fully fixed. No safe
supported live control for that writer was identified; do not claim zero steps
from the coarse helper's 50ms sampling. No direct manual time/rate reset was issued.

An exploratory nsenter /initd --help attempted VM initialization and restarted
original containers, violating uptime preservation. Stale host forwards required
standard API/PostgreSQL/Redis recovery restarts. Same original IDs/images/volumes,
healthy host endpoints, original schema/trade count and Redis PING were verified;
uptime/cache continuity are not claimed. Owned probe/trace resources were cleaned.
Never run initd help/VM-init experiments. Preserve all historical failures and
report this incident honestly. Later Docker/vendor maintenance needs a separate
reviewed plan. R5-R9 remain unauthorized; no commit/push.

## Authorized clock claim fix: application-layer workaround, issue persists

On October 25, 2026 the user approved fixing the job code rather than the environment,
with no commit/push. Claude implemented it and an independent read-only Claude subagent
reviewed it; this overrides the coder/reviewer models for this fix only, because they
were unavailable in that session. Root cause: Docker Desktop /initd steps the shared
WSL2 clock about 1-2ms backwards every ~30s (upstream docker/desktop-feedback#761).
There is no setting to disable it, and newer releases are reported to step further,
so do not upgrade expecting a fix.

The approval lifts the earlier eligibility freeze for claims only. Queued R2/R4 work
is claimable from submission without a later wall-clock comparison. ingest_day
rechecks database time at most three times per attempt before reporting a due retry
as ineligible. Retry backoff and lease expiry still use clock_timestamp().
Leases/heartbeats, the three-attempt budget, fencing, publication, schema and
dependencies are unchanged.

Locked checks passed 655 offline/158 real PostgreSQL cases, and real clock acceptance
passed. The backward-clock issue persists. It was worked around at the application
layer rather than fixed at the system level: Docker Desktop, WSL, the host clock and
time-sync configuration are unchanged. Do not describe the clock as fixed. See
[clock fix](docs/r4-clock.md). R5-R9 remain unauthorized.

## Authorized R4 and clock-fix publication (October 25, 2026)

The user explicitly authorized committing/pushing the verified R4 changes and
application clock fix, then checking hosted CI. This supersedes the earlier
no-commit/push restrictions for this scope only. Preserve all historical failures,
the clock-follow-up incident and the distinction between month acceptance and
later source changes. Do not include artifacts/data, credentials, environments or
weights; R5-R9 remain unauthorized.

Fresh locked verification passed 655 offline/158 real PostgreSQL tests and live
acceptance in 249.827s: 1,000 immediate claims per job kind, real retry gates,
heartbeats, three lease-expiry cycles, stale-worker rejection and the attempt cap.
Independent read-only review found no blocking issue. The application works as
intended with the known Docker clock discrepancy; a 90-second server sample still
captured three backward steps, largest 2.788ms. Owned resources were removed and
original service IDs/start times/health were unchanged.

Verified R4 and the application clock fix were committed/pushed to origin/main as
2c0dd0bbf8ebfcac9dd6a5cbd5255d288f383d0c, including the existing R4 backup commit
f600ccb7e1fc1487f88328c2826d72f956631e52. [Hosted CI run 40167912094](https://github.com/atharva-m/MarketLab/actions/runs/40167912094)
passed for that exact revision: 655 offline tests on Ubuntu and Windows, 158 real
PostgreSQL tests on Linux, quality/build/API/optional-Redis-outage/cleanup checks.
No CI fix was needed. Hosted smoke is separate from local month reconciliation
and clock acceptance; see [R4 verification](docs/r4-verification.md).

## Current authorized milestone: R5 - complete (October 25, 2026)

The user approved the detailed R5 proposal, ROADMAP.md/AGENTS.md updates, full
[R5 contract](docs/r5-copilot.md) BEFORE code, prescribed coder gpt-6.1-sol high
then independent read-only reviewer gpt-6-astra medium, full acceptance and actual
outcomes. The initial implementation request excluded commit/push; the later
R5 publication authorization below now governs publication. This supersedes
historical R5/copilot exclusions only
within that contract; R6-R9 remain unauthorized. Preserve full R1-R4 contracts,
immutable artifacts and historical evidence.

R5 implementation, full locked verification, independent review, actual model/
month acceptance and ownership-checked cleanup passed; see
[R5 verification](docs/r5-verification.md). Strict durable interpretation and
clarification, additive schema, DB-time fenced execution (three attempts/two
reserved model calls), atomic same-service research handoff and bounded local
Ollama/API/CLI are complete. Final checks passed 736 offline/174 real PostgreSQL
cases. Frozen v3 met the model gates: 18/20 clear correct and zero unsafe
submissions among 40 negative cases; 25 negatives received expected clarification/
refusal and 15 failed safely. Do not claim unrestricted model understanding or
40/40 successful clarification/refusal.

Ten full-month runs (five copilot/five manual), all attempt 1, matched every
canonical spec/results/summary hash against retained independent R4 references
over 62 January partitions/230,311,900 trades, in 2473.395s. The tested dirty source
fingerprint, earlier failed v1/v2 evaluations (including one unsafe queued v2 run,
never numerically executed), harness/source-drift/orchestration failures and actual
client-cancellation versus model-load-abortion observations remain explicit in
verification. No active-token generation cancellation claim follows from the
final load-abortion log. Peak memory remains unmeasured; hosted CI is unrun.

All 124 original dataset files and 53 protected files (including 40 old research
files) retained their hashes. Owned resources were removed; original service IDs,
images/start times/restart counts/health and HTTP/Redis endpoints were preserved.
The Docker clock discrepancy persists; preserve the application workaround. No
dependencies/lock/deployment changes, downloads/model pulls, memos/UI/scheduling/
GC, Docker/WSL/initd/clock experiments or original-service restarts were added.
No artifacts/data/credentials/environments/weights belong in Git. R5 completion
provides no R6-R9 authority; publication requires the explicit later approval below.

## Authorized R5 publication (October 25, 2026)

After verified local closeout, the user explicitly authorized committing/pushing
verified R5, checking hosted CI, fixing actual R5-only CI failures through the
prescribed coder gpt-6.1-sol/high and independent read-only reviewer
gpt-6-astra/medium workflow, and documenting/publishing actual outcomes. This
supersedes earlier R5 no-commit/push restrictions for this publication scope only.
Preserve R1-R4, all local acceptance/source/model/cancellation/failure evidence,
the dirty-source fingerprint, model-quality limitations and unresolved system
clock discrepancy. Do not include archives/artifacts/data, credentials,
environments or weights in Git. R6-R9 remain unauthorized.

Publication and hosted CI outcomes have not yet been observed at this authority
update. Record the exact published SHA and actual hosted results in
[verification](docs/r5-verification.md); local acceptance is not a hosted CI pass.
Do not infer new feature/deployment authority from publication approval.
