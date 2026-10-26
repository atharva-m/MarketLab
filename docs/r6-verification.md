# R6 verification

**R6 COMPLETE** under the approved [contract](r6-memos.md), October 25, 2026.
Implementation, independent source/evidence review, full local acceptance and
ownership-checked cleanup passed. The initial closeout excluded commit/push;
later October 26 publication authority superseded that restriction. Verified R6
and its verifier follow-up were published as `c94ef4bce9dd292730c8884761c787f799bac2d1`.
The first two hosted runs failed as recorded below; corrective runtime commit
`0e054bd41d987e85df4cb1dcf75f62e6aa049fb6` subsequently passed hosted CI.
R7-R9 remain unauthorized. All local failures and limitations below remain part
of the observed outcome.

## Source, implementation and review

The contract and ROADMAP.md/AGENTS.md approval were written before runtime/test
implementation. R6 adds migration 0007_memos, independent memo jobs/attempts/
results, atomic numerical-publication enqueue, explicit old-run enqueue, bounded
three-paragraph application-owned claims with model wording selection, immutable
supplemental manifests, separate API/CLI and shared copilot-priority inference.
The constrained model chooses between approved wording variants; it does not
generate unrestricted prose or numeric claims. Numerical substitution and factual
predicates are application-owned.

Frozen runtime execution identity before actual-model acceptance:
- HEAD: 7e270bc9db94e2117964a3b257e559bcf69e6410, dirty working tree.
- Source SHA-256: c9a6c63d1af3299060f211682614d2eba66c680345a3af31a02ab9e5d337aabc.
- Lock SHA-256: 730f02bec94d1f824a2cadf74f60cf5dcc246faa55004d5d060b92931224618f.

Evidence: ignored artifacts/r6/frozen-execution.json and replayable runtime
source/public-lock bundle frozen-runtime-source-c9a6.zip (48 files; archive hash
in frozen-runtime-source.json). This is a dirty-source
execution, not a published clean R6 revision. Dependencies/lock/deployment remain
unchanged. Existing installed qwen3.5:4b-q8_0 digest is
e15635ee93129fd2086640926e900c37589c5167561104abc3914bd6644c7e07.
Peak memory is unmeasured. The Docker system-clock discrepancy persists; no
system clock fix or maintenance was attempted.

Ollama used CUDA on the NVIDIA GeForce RTX 4070 Laptop GPU; the owned server
log records all 33/33 model layers offloaded to GPU. This is model-inference
evidence, not evidence that the historical data pipeline uses a GPU. Historical
Parquet/checksum/logical verification, DuckDB reads and Decimal80 research
preparation execute on the CPU. The cold thirty-minute failure below occurred
in ResearchService.prepare before new durable submission or memo inference,
not while Ollama was generating. Evidence: artifacts/r6/ollama-stderr.log.
No GPU-enablement or runtime/dependency change was made.

Independent read-only reviewer gpt-6-astra/medium found and the prescribed coder
gpt-6.1-sol/high resolved transport-failure retry classification, strict enqueue
UUID validation, direct memo execution admission, bounded observability gaps and
missing cancellation/nonpreemption tests. New drain tests caught a real defect:
a thread exception during cancellation could replace CancelledError. Explicit
cancellation propagation now drains the thread, sets lost ownership and prevents
publication. Final runtime review found no blocking source issue. Subsequent independent
acceptance review audited actual model outputs, native artifacts, registered
hashes and numerical references and found no blocking issue.

## Locked checks and actual failures

- Twenty initial memo offline cases passed; after UUID/corpus coverage tests,
  independent reviewer reran 22 memo plus 81 retained copilot cases: 103 passed.
- First full offline run passed 756 cases before the two additional memo cases.
- First full PostgreSQL run passed 184 and failed one retained copilot assertion
  expecting capacity contention to consume an attempt/retry. R6 expressly changes
  admission to occur before claim. The test now requires queued state, zero
  attempts and zero model calls while capacity is busy, retaining eventual success.
- New memo PostgreSQL tests initially exposed the cancellation-propagation defect
  above (8 passed before failure); fixed focused memo/copilot suite passed 30.
- First scripts/check.ps1 attempt failed lint while a second coder was still
  writing operational tooling. No runtime/test execution was claimed for that
  incomplete check. The tooling was subsequently formatted and checked.
- Earlier full locked check (artifacts/r6/full-checks-second.log): Ruff lint/format,
  strict mypy (47 source files), 758 offline cases and 188 real PostgreSQL cases
  passed. PostgreSQL elapsed 78.40s, offline 11.27s. Deprecation warnings from
  retained Starlette/httpx test integration remain; no skipped tests are counted
  as passes. Deselections separate the two suites.

Initial sandbox uv interpreter-cache access was denied and asynchronous app
checks stopped responding in sandboxed invocations; those invocations were
interrupted, not called passes. Elevated runs using the existing locked environment
passed. Apparent later full-check progress lag was tool output delay: the actual
completed log showed all 188 PostgreSQL tests passed, so no service restart or
unsupported environment change was performed.

The initial 14 new PostgreSQL cases include atomic enqueue/rollback, historical replay,
concurrent claims, forced-clock/lease tests, transport retry/two-call budget,
third-attempt checkpoint recovery, numerical availability during model failure,
corruption, cancellation/deadline thread draining, shared priority/nonpreemption
and three actual child-process terminations before publication, after rename/
before commit and after commit. Forced lease expiry in these tests is distinct
from the actual-time durability acceptance below. A later fifteenth memo case
fully stages a supplement, expires/reclaims the owner, rejects stale publish and
finish with no registered/ready artifact, then completes under the current owner
from checkpoint without another model call; its targeted real DB run passed.

## Actual model and operational acceptance

Actual twenty-summary model evaluation passed 20/20 valid generations in 63.308s
on the frozen installed model/source, each within one call (Ollama 0.40.9). Parent independent audit
read all twenty complete memos and checked 77 scalar facts directly against
summary paths without importing the production renderer. Dates, units, coverage,
nulls, correlation signs, sparse selections, clusters, paragraph counts and hashes
passed; no unsupported causal/predictive/recommendation claim was observed.
Evidence: artifacts/r6/r6-final-memo-model.json and separate
artifacts/r6/independent-model-audit.json. Raw model evidence retains its original
audit-pending status; the subsequent independent audit is a distinct record.
This passes the constrained R6 model gate, not unrestricted prose generation.

The twenty-summary corpus was frozen before the first
actual model evaluation: tests/fixtures/r6_summaries.json SHA-256
e17a6dc91e807f2014ac8f260184844855cdd3ffee5e5f430ad32ee27e0e4bea.
It contains all workflows, both assets, sparse selections, positive/negative/
exact-zero correlation, zero-variance null, gaps, a single evaluation observation,
zero-denominator VWAP and a nonempty cluster touching evaluation boundaries.
Actual-time memo durability passed in 242.65s on an owned isolated schema:
100 immediate claims, actual 10s/30s retry gates, two genuine 10s heartbeat waits,
three genuine 60s lease-expiry cycles, stale heartbeat/reserve/checkpoint/fail
rejection, no fourth execution and no third model call. No eligibility or lease
timestamps were edited. The owned schema was removed. Evidence:
artifacts/r6/r6-final-durability-live.json.

The retained R5 actual 60-prompt gate passed in 413.341s using unchanged prompt-v3
and corpus: 18/20 correct clear specs, zero unsafe submissions among 40 negatives,
25 expected clarification/refusal outcomes and 15 safe failures. Those 15 failures
are not successful clarification/refusal. Evidence:
artifacts/r6/r6-final-model-evaluation.json. Historical R5 tooling and artifacts
were not overwritten; invocation-local resource/output bindings point to R6.

Populated migration acceptance independently passed on an owned isolated schema:
actual 0006_copilot upgraded to 0007_memos with 770 rows across twelve retained
R1-R5 tables and the synthetic trades table preserved exactly, including table
definitions. Eighteen invalid real FK/state/attempt/model-call constraint probes
were rejected; memo FKs were verified on real migrated tables. LIKE-based test
clones do not carry FKs and are not the evidence for these probes. The owned
schema was removed. Evidence:
artifacts/r6/r6-op-migration-first-migration.json.

Live operational acceptance passed on owned resources:
- Actual TCP API/CLI, memo enqueue/ready/replay, shared copilot priority, retained
  legacy interfaces and real owned Redis stop/start outage: 23.920s. Cached and
  bypass numerical bodies matched and Redis recovered. Evidence:
  artifacts/r6/r6-op-interfaces-first-interfaces.json.
- Shared lifecycle/nonpreemption, busy capacity with zero budget consumption,
  client cancellation and short injected post-dispatch timeout/draining:
  13.827s. Evidence: artifacts/r6/r6-op-lifecycle-second-lifecycle.json and
  separate owned Ollama observations. This proves cooperating client admission
  and local cleanup, not universal upstream active-token cancellation.
- Actual packaged image overlay/startup and old-result read without model/Git
  checkout: 10.001s. Owned overlay container/image removed after identity/label
  checks. Evidence: artifacts/r6/r6-op-package-second-packaged.json.

Earlier operational helper failures remain recorded: the first 0.25s lifecycle
probe expired before chat dispatch and could not establish inference timeout;
the corrected probe injects 0.05s at POST chat dispatch. The first package helper
built the image but failed an obsolete Docker inspect IP-field assumption before
creating a container; that image was cleaned and the explicit network lookup
corrected. These are harness failures, not successful runtime acceptance.
The first-failure JSON files remain alongside later passing evidence.

The first cold combined full-month cross-asset preparation hit the unchanged
R4 1800s deadline with TimeoutError before durable acceptance; no fresh run ID
was created. That workflow phase lasted 1828.554s including the five successful
retained memo generations. The five published supplements remain ready and
unchanged. Evidence: artifacts/r6/r6-final-month.json and month-final.log.
This failed cold request is not a successful full-month numerical run.

A distinct, explicit acceptance sequence passed in 2438.450s: ordinary BTC
profile submission/execution, ordinary ETH profile submission/execution, then a
fresh cross-asset request through the same BarService. All three fresh durable
numerical runs succeeded on attempt one and every result/summary payload hash
matched the retained independent R4 reference. Each single-asset profile used
its 31 partitions; cross-asset used all 62 January partitions, covering the union
of 230,311,900 trades. Existing five retained memo scenarios
(BTC/ETH profiles, cross-asset and BTC/ETH clusters) replayed without resetting
attempts or regenerating content. The two new profiles and new cross-asset run
each exercised atomic numerical-success enqueue and generated a ready memo.
Every request retained the existing thirty-minute bounds. This uses existing
workflows and their normal integrity/response caches; it adds no production
cache-warmer, skips no verification and extends no timeout. Therefore this is
ordered normal-workflow acceptance, not a cold combined-month performance pass.
Evidence: artifacts/r6/r6-ordered-month.json and month-ordered.log. The recorded
aggregate duration is exact; the final thirty-second progress checkpoints are
not treated as exact individual preparation durations.

Parent independently audited all eight complete memo texts and 44 scalar facts
against summaries without importing the production renderer, with units/null/
sign/paragraph/hash checks. Reviewer separately verified all eight native memo
files and all three fresh numerical result/summary reference hashes. No
unsupported causal/predictive/recommendation claims were found. Evidence:
artifacts/r6/independent-month-audit.json and reviewer acceptance report.

Final full locked checks passed: Ruff lint/format (126 files), strict mypy
(47 sources), 758 offline tests in 12.29s and 189 real PostgreSQL tests in 79.51s.
No tests were skipped; deselections separate offline/integration suites. Evidence:
artifacts/r6/full-checks-final.log. The fifteenth memo database case above is
included in this final count.

Final owned database snapshot: artifacts/r6/r6-ordered-catalog-final.json,
migration 0007_memos, all fifteen application registration/history tables,
native storage root and frozen execution identity. Direct snapshot readback
verified all eight memo jobs/results ready, every memo attempt_count=1 and
model_calls=1. These are memo counters; the three fresh numerical attempts
are independently recorded as one each. The snapshot supports exact registered
artifact replay after owned service cleanup.

Validator rejection is not successful generation. Independent final acceptance
audit and owned service cleanup passed as recorded below.

Shared admission serializes cooperating application client calls. Timeout,
cancellation or a killed client can release that lock without proving upstream
active-token generation stopped. Record actual owned-server observations; do not
claim universal upstream no-overlap or token cancellation from a client close or
model-load-abortion log.

Independent review also assessed an API consistency edge: an unsafe artifact-path
DatasetError reaches the existing fixed-safe global HTTP 500 rather than the
research adapter's 422 mapping. It rejects access without raw disclosure or
numerical mutation. The R6 contract pins 422 for malformed UUID/body and requires
safe corruption failure, so this was nonblocking and the frozen runtime was
preserved.

## Preservation and cleanup

Parent captured 229 protected file hashes and original service IDs/images/start
times/restart counts/health before acceptance. Fresh comparison after actual
month acceptance found all 229 original file hashes unchanged; evidence:
artifacts/r6/preservation-after.json. Parent reran this full hash comparison
after cleanup; all 229 hashes still matched.
Owned R6 PostgreSQL/Redis containers and a hidden owned Ollama process used
existing images/weights only, with no pulls. No original-service restart, Docker/WSL/initd/clock experiment, numerical
manifest rewrite or source-data mutation occurred. The published supplements will remain as ignored immutable acceptance
evidence in their native run namespaces, with a matching owned-database snapshot.
There are eight ready supplements: five original retained-scenario runs plus
two fresh profiles and one fresh cross-asset run. They are additive directories;
original numerical files are not changed or deleted. Restoring the saved memo
job/result registrations supports exact replay;
regeneration never overwrites a published memo. Owned service/schema/process
cleanup is separate from retaining immutable evidence.
Artifacts/data/credentials/environments/weights remain outside Git. Hosted CI is
unrun and publication remains excluded.


Final ownership-checked cleanup passed (artifacts/r6/cleanup.json): exact owned
PostgreSQL/Redis containers and their anonymous volumes were removed after saved
IDs/labels were checked. The owned Ollama process tree was removed after PID,
creation time, executable and listening-port verification. Owned ports 55439,
56381 and 11437 closed. Earlier owned overlay image/container, API subprocesses
and disposable schemas were already removed. Native immutable artifacts and the
matching database/source snapshots were retained intentionally, not garbage
collected.

Original API/PostgreSQL/Redis container IDs/images/start times/restart counts
were unchanged and container health stayed healthy. Original HTTP live/ready
endpoints remained reachable and Redis PONG passed after cleanup. The original
ready response was exactly the same degraded state before and after R6: required
PostgreSQL/storage checks were up, Redis was up, and optional original Ollama was
down with ConnectError. This is preserved optional-dependency degradation, not an
all-dependencies-healthy claim. No original-service restart was performed or
observed in R6. All 229 original protected file hashes matched after cleanup. The inherited system-clock issue,
constrained-language/model-quality limits, unmeasured peak memory, upstream
cancellation limit and cold combined-month request failure remain unresolved
limitations; none is represented as a successful fix or unrestricted guarantee.
No R6 local acceptance blocker remains. No commit/push or hosted R6 CI occurred.

## Later authorized cold-verifier follow-up

The user subsequently authorized exact native verification and bounded CPU
parallelism under the pre-code [optimization contract](verifier-optimization.md).
Its frozen-source fresh-process all-62 cross-asset submit/prepare/execute/readback
passed in 272.814s, including cleanup, with every original dataset hash and exact
independent R4 numerical payload preserved. Full retained checks passed 811
offline/189 PostgreSQL cases. This later result is separate from the original
R6 source's cold failure and ordered acceptance above; those historical outcomes
are not rewritten. See the follow-up for source, application/OS cache conditions,
resource measurements, Linux/preservation/cleanup evidence and remaining limits.
No commit/push or unrelated milestone authority follows.

## Authorized publication (October 26, 2026)

After verified local R6 and cold-verifier closeout, the user explicitly authorized
committing/pushing this verified scope, checking hosted CI, fixing actual
scope-related CI failures through coder gpt-6.1-sol/high followed by independent
read-only reviewer gpt-6-astra/medium, and documenting/publishing actual outcomes.
This supersedes the earlier no-commit/push restrictions only for R6 and its
approved verifier follow-up. It grants no R7-R9, unrelated feature, deployment or
system/service/clock authority.

Preserve every local source/model/month/operational/performance/failure record
and the distinction between the original R6 source and the later frozen verifier
source. All immutable artifacts/data, archives, credentials, environments and
weights remain excluded from Git. The known clock discrepancy, constrained-model
limits, upstream cancellation uncertainty, OS-cache condition and unmeasured
aggregate peak memory remain explicit.

At that authority update, publication and hosted CI outcomes were pending.
Their actual later outcomes follow. The completed 811 offline/189 PostgreSQL
local suite and actual-model/cold acceptance remain separate evidence.

## Publication and initial hosted failure (October 26, 2026)

Verified R6 and the cold-verifier optimization were committed/pushed normally as
`c94ef4bce9dd292730c8884761c787f799bac2d1`, containing 38 audited scoped source,
test, migration, acceptance-tooling and documentation files. No artifacts/data,
archives, credentials, environments or weights were included. Runtime source
SHA-256 remains `f12cf32c7a33b8b81691cebd40195a6d174cc113be4aa35190dd209ccb3e1035`.
This does not relabel the earlier dirty-source model/month/cold executions as
new executions under the published commit.

[Hosted CI run 40269166877](https://github.com/atharva-m/MarketLab/actions/runs/40269166877)
failed for that exact revision:

| Hosted job | Observed outcome |
| --- | --- |
| Ubuntu quality | Failed: 810 offline passed, one worker-crash test failed; 189 integration deselected. |
| Linux integration | Failed: 188 PostgreSQL cases passed, one synchronous retry test failed; 811 offline deselected. |
| Windows quality | Canceled by matrix fail-fast; 802 reported passes are partial evidence, not a completed quality pass. |

Ubuntu lint/format (134 files) and strict mypy (48 sources) passed before its
offline failure. Integration passed Compose validation, image build and startup;
later API/Redis smoke steps did not run after the test failure. Cleanup ran.
Exact hosted logs are retained under ignored `artifacts/r6-ci/` with the run and
job IDs. This initial failed run remains a failure even if recovery later passes.

The ingestion test patched `publication.time.sleep`, mutating the shared stdlib
module. POSIX subprocess timeout polling during Git provenance reads then added
two unrelated 0.001-second calls to its retry-wait list. Its three HTTP calls were
correct; the observed waits were `[9.992866, 0.001, 0.001]`. The test-only fix replaces
the publication module's `time` binding with a local sleep adapter in all three
related synchronous-retry cases. Exact HTTP/sleep/attempt assertions remain intact.
Owned real PostgreSQL validation passed 12 synchronous cases (2.38s) and all 40
durable-job integration cases (20.92s). A Linux subprocess probe reproduced the
global polling leakage and verified exactly one application wait with the local
adapter. Its first environment probe lacked the current source in the old base
image; the corrected read-only source mount passed without pulls/dependency changes.
Evidence and ownership-checked cleanup are in `artifacts/r6-ci/jobs-sleep-fix/`.
The owned PostgreSQL/anonymous volume and probe containers were removed; original
service identities/start times/restarts/health, HTTP endpoints and Redis PONG
were preserved.

The Ubuntu worker-crash test sent POSIX SIGTERM without establishing that the
owned worker had exited; its controlled release checkpoint expired. The proposed
test-only correction uses forced crash semantics on POSIX and observes the exact
owned process sentinel before retaining broken-pool, SQL-fencing, reaping and
recreation assertions. Windows uses its existing forced SIGTERM behavior.
Post-fix normal validation passed 811 Windows offline cases (38.76s). After the
final sentinel refinement, Windows pool validation passed 11 cases (12.09s) and
the Linux pool/parent-death group passed 13 (22.09s). A separate final Linux
launcher probe with inherited blocked SIGTERM passed its targeted case (13.83s):
the sentinel was ready, the exited worker was temporarily a `/proc` zombie, and
its exit code was -9. This distinguishes actual exit from `kill(pid, 0)`, which
still succeeds for a zombie until reaping; the final close assertion continues
to require reaping. The original hosted worker's signal state was not captured
and is not inferred from these injected local conditions.

Earlier local probe failures remain recorded: the first fixture changed both
workers and interfered with stdlib sibling cleanup; that exact owned container
was recorded and stopped. The fixture now alters only the selected target and
normalizes its sibling. An earlier exit probe incorrectly required PID
disappearance before reaping, and its first diagnostic then hit a disappearing
proc-file race. Initial Linux collection also encountered an unavailable Windows
Hypothesis native module; corrected runs used existing Linux-compatible pytest/
asyncio packages without installs or downloads. These were test/probe failures,
not changes to production signal handling or verifier semantics.

Independent read-only review approved both final test fixes. Ruff lint/format
(134 files), strict mypy (48 sources) and diff whitespace checks passed. Exact
normal/abnormal logs and `pool-cleanup-final.json` remain in `artifacts/r6-ci/`;
both owned CI resource inventories were empty after cleanup. These local passes
do not establish a replacement hosted pass.

That first recovery changed only tests/documentation; runtime source, dependencies,
lockfile, deployment, numerical definitions and recorded local acceptance were
unchanged. Its actual publication and next hosted outcome follow below.

## Second hosted attempt and necessary startup correction (October 26, 2026)

Reviewed recovery was committed/pushed as
`6084ac58fa49c49015a4b552db68e3be14b6dc2a`.
[Replacement run 40271353210](https://github.com/atharva-m/MarketLab/actions/runs/40271353210)
passed Ubuntu quality (811 offline, 19.75s) and Linux integration (189 PostgreSQL,
79.29s), including API/optional-Redis-outage/cleanup checks. Windows quality again
failed the worker-crash test (810 passed/one failed), reporting the controlled
release timeout after exit observation. This second run is not an overall pass.

Further direct evidence confirmed a Python 3.13 executor dynamic-spawn race: its
manager's captured wait set could omit the newly spawned worker's sentinel.
Death of that unobserved worker did not promptly trigger broken-pool handling
without another event. Earlier signal/readiness explanations and test-only
corrections did not establish or solve this production ordering issue. The
confirmation JSON/logs remain under `artifacts/r6-ci/`.

The parent and independent reviewer approved a necessary runtime design within
the existing actual-CI-fix authority; it was recorded BEFORE code in
[the optimization contract](verifier-optimization.md). A lazy public-API bootstrap
uses exactly two barrier readiness tasks in distinct worker PIDs, reserves both
shared compute permits atomically, and dispatches no real file task until both
complete. Startup decision bounds never release permits before actual draining.
No private executor hooks, larger pool, skipped checks, dependency/lock/deployment
change or altered numerical identity is authorized.

New focused lifecycle/regression tests, independent review, source freeze and
full locked/offline/PostgreSQL checks plus actual fresh cold62/Linux acceptance
are required on the corrected source. The original c9a6 model/month record and
f12cf32/272.814s cold record remain historical; they are not acceptance on the new
runtime. New owned evidence/resources are isolated under
`artifacts/r6-ci/executor-startup-fix/`, with a fresh 263-file protection baseline.
Correction/reverification and a subsequent overall hosted pass remain pending.

## Executor-startup correction locally reverified (October 26, 2026)

The reviewed public-API two-worker bootstrap is implemented and frozen as runtime
source `bb4d69804069735dd258d1f6550b7fb1772339d61c547cd4df0c9c3cf0a4476f` on dirty
HEAD 6084ac58. Full locked checks passed 819 offline (48.32s), 189 PostgreSQL
(122.92s), Ruff lint/format (136 files) and mypy (48 sources). Six startup tests
include cancellation/close/failure/recreation and a decision-timeout test proving
occupied capacity is held until actual tasks drain. Independent read-only review
accepted final source/tests, documentation and actual acceptance/cleanup evidence.

New actual cold acceptance passed in 266.692329s including cleanup, under the same
1800-second bounds: all 62 partitions/230,311,900 rows and every manifest/physical/
logical hash reconciled, and the independent R4 result/summary hashes matched.
Readiness completed in two distinct spawned workers before observed file work,
shared/unfinished peaks stayed two, and close reaped all children. Run
62fd8392-1deb-40ba-9408-52e8904ce03f used numerical attempt one and autoqueued a memo
with zero calls. This was fresh application/cache state, with no preliminary
profile and no OS cache flush; aggregate memory peak remains unmeasured.

The first new cold harness run remains FAILED despite correct numerical output:
its ignored post-close diagnostic wrongly expected readiness Futures to persist.
A reviewed wrapper-only correction carried forward actual pre-close PID proof
for the same instance and required the Futures to be released. A separate fresh
process/key produced the passing result above; runtime and tracked harness were
unchanged between attempts. Both native numerical registrations/artifacts and
their distinct overall acceptance statuses are preserved in the final owned
database snapshot.

Sequential Linux readiness/spawn/read/cleanup smoke passed with exact independent
bars/hashes. All 263 protected originals matched after ownership-checked cleanup;
owned containers/anonymous volumes/ports were removed and original service IDs,
start times/restarts/health, HTTP/Redis and optional-Ollama degradation stayed
unchanged. The post-cleanup source hash still matched bb4d698. Detailed timings,
resources, failed readiness-only probes and final evidence are in
[the optimization follow-up](verifier-optimization.md) and ignored
`artifacts/r6-ci/executor-startup-fix/`. Original c9a6 model/month, f12cf32 cold,
both hosted failures, clock discrepancy and model/cancellation limits remain
historical evidence. Corrective publication/hosted verification was pending at
that local record; the actual outcome follows.

## Corrective publication and hosted CI passed (October 26, 2026)

The independently reviewed startup correction was committed/pushed normally as
`0e054bd41d987e85df4cb1dcf75f62e6aa049fb6`, with ten audited scoped runtime/test/
documentation files and no artifacts/data, archives, credentials, environments
or weights. [Hosted run 40276563068](https://github.com/atharva-m/MarketLab/actions/runs/40276563068)
passed for that exact revision:

| Hosted job | Actual tests | Pytest time |
| --- | --- | --- |
| Ubuntu quality | 819 offline passed | 31.00s |
| Windows quality | 819 offline passed | 39.87s |
| Linux integration | 189 PostgreSQL passed | 89.94s |

Quality lint/format/mypy and integration build/startup, API health/metrics,
initially healthy Redis, actual optional-Redis-outage/degraded readiness and
cleanup checks passed. Exact run/job logs remain ignored under `artifacts/r6-ci/`.
No R6/verifier publication or CI blocker remains.

This hosted pass does not rerun or relabel the dirty-6084/bb4d698 local 266.692s
cold execution, original c9a6 model/month acceptance or f12cf32 cold record. Both
earlier failed hosted runs and the first failed new cold harness remain failures;
all earlier failed diagnostic attempts remain recorded. Preserved artifacts/services, known clock discrepancy,
constrained-model limits, upstream cancellation uncertainty, uncontrolled OS cache
and unmeasured aggregate peak memory remain unchanged. R7-R9 remain unauthorized.
