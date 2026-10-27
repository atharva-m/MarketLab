# MarketLab project history

Historical acceptance, publication authority, failures and incidents belong here
and in the linked verification reports. The README focuses on current setup,
configuration and usage.

These excerpts were relocated from README.md on October 27, 2026. Wording is
retained, apart from relative link destinations. Statements such as "pending",
"unauthorized" and "incomplete" describe the observation or authority at that
entry; later scoped approvals and results may supersede them. They are not new
execution authority. Current contributor instructions remain in
[AGENTS.md](../AGENTS.md), and milestone sequencing remains in [ROADMAP.md](../ROADMAP.md).

## Detailed evidence index

| Scope | Detailed record |
| --- | --- |
| R1 immutable historical datasets | [R1 verification](r1-verification.md) |
| R2 durable ingestion | [R2 verification](r2-verification.md) |
| R3 bars and caching | [R3 verification](r3-verification.md) |
| R4 research and clock follow-up | [R4 verification](r4-verification.md), [clock incident and workaround](r4-clock.md) |
| R5 copilot | [R5 verification](r5-verification.md) |
| R6 memos and verifier | [R6 verification](r6-verification.md), [verifier follow-up](verifier-optimization.md) |
| R7 workspace and browsers | [R7 verification](r7-verification.md) |
| R8 evaluations and adoption | [R8 verification](r8-verification.md), [adoption contract](r8-adoption.md), [clarification experiments](clarification-experiment.md) |

The latest R8 report records implementation publication at 3fc8584 and successful
hosted run 40548949738. Its 196 PostgreSQL passes plus four skips remain distinct
from the local 200-case pass. The documentation-only publication outcome is not
newly verified by this relocation.

Later success does not erase failed invocation identities, the second R8 copilot
resource failure, the unknown-cause historical uptime gap, the clock discrepancy,
Windows Firefox cache-path limitations, or model/cancellation/memory limits.
Raw evidence, archives, data, credentials, environments and weights remain outside Git.

## R8 first pipeline diagnostic

The first 1M diagnostic retains a successful numerical result but receives no
acceptance credit because mandatory memory coverage was incomplete and scheduling
was concurrent. See [R8 verification](r8-verification.md).

## R8 acceptance and publication records

Verified R8 was committed and pushed as
`3fc858464e4929c3b66c91ba057a6da86e89308b` (47 audited files; raw evidence/data,
credentials, environments and weights excluded). [Hosted CI run 40548949738](https://github.com/atharva-m/MarketLab/actions/runs/40548949738)
passed for that exact revision: 990 offline tests on both Ubuntu and Windows,
196 PostgreSQL tests with four expected local-evidence skips, 18 components and 33
browser cases, plus existing build/API/Redis-outage/cleanup checks. No CI fix was
needed. The four skipped source-compatibility cases passed locally in the 200-case
suite and require the ignored historical snapshot absent from a fresh checkout.
See [verification](r8-verification.md) for the distinct local acceptance and
hosted scopes. The following documentation-only publication is pending at this
entry. Original services remain untouched; R9 and unrelated work remain excluded.

The October 27 [R8 adoption amendment](r8-adoption.md) authorizes the tested
9B Q4_K_M/null-guard interpreter in production code and fresh remaining acceptance.
R8 completed under that amendment and its reviewed technical resource supplement.
Both fixed copilot quality cohorts scored 19/20 clear and zero unsafe handoffs;
the second invocation remains FAILED for resource coverage, and the separate
unchanged technical repeat passed. Both memo cohorts passed 20/20; production
clarification reached the fifth answer and rejected further work without mutation.
Final checks passed 990 offline/200 PostgreSQL, 18 components/33 browsers, current recovery,
monitoring/live/package and exact cleanup/preservation gates. Fresh cold all 62
passed in 265.429132 s with all retained hashes exact. See the
[actual verification](r8-verification.md) for complete evidence and limits.
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

The approved [R8 contract](r8-evaluation.md) covers repeated actual-model
evaluations, owned recovery tests, pipeline/cache/model/queue/resource benchmarks
and local operational dashboards. R1-R7 behavior and historical evidence remain
preserved in the exercised checks; final service continuity is unverified. R8
remains INCOMPLETE: the required actual-model five-round clarification case failed
safely at revision 3 initially and revision 4 in the one predeclared supplemental
invocation. Neither reached the fifth-answer/sixth-round boundary. No model/prompt
change or forced state was used. See [actual R8 verification](r8-verification.md).
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



## R7 acceptance and publication records

The approved [R7 contract](r7-ui.md) adds a local React workspace over the
retained R1-R6 services. Implementation/full local acceptance passed: 853 offline,
193 PostgreSQL, 18 frontend component and 33 browser cases. The actual fresh
all-62 browser workflow passed in 526.988s with exact retained hashes. Independent
review and owned cleanup passed; original artifacts/services were preserved.
Actual outcomes and limitations
are in [R7 verification](r7-verification.md), including the safe failed
ambiguous model case and initial Windows Firefox startup failures. A later
[Windows Firefox follow-up](r7-verification.md#windows-firefox-physical-cache-configuration-fix-october-26-2026)
passed all 11 cases with pristine binaries using Playwright's process-only
physical-cache path setting; its default logical MSIX path remains affected.
No R7 commit/push or hosted CI had occurred at local closeout. Verified R7 was
later published as `cb98663eb0edd9726b5336a5933d035c12002c5c`;
[hosted CI 40388784506](https://github.com/atharva-m/MarketLab/actions/runs/40388784506)
passed for that exact revision. Hosted checks remain separate from local model/
month/cold/Windows-cache evidence. R8 was backlog at that publication; its current
authority is above. R9 remains backlog.



## Original roadmap and week labels

R1 restored the historical research roadmap with checksum-verified one-day Binance Spot
BTCUSDT ingestion, immutable Parquet publication and a separate PostgreSQL dataset catalog.
See [the approved recovery roadmap](../ROADMAP.md), [R1 contract](r1-datasets.md) and
[actual R1 verification](r1-verification.md). Historical week labels below describe
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



## R3 publication record

See [R3 contract](r3-analytics.md) and [R3 verification](r3-verification.md)
for exact errors, limits, completed local acceptance evidence and subsequent
publication/hosted CI outcomes. Verified implementation commit `54f15d3` passed
[hosted CI run 40072552311](https://github.com/atharva-m/MarketLab/actions/runs/40072552311)
with 606 offline tests on each quality platform and 132 real PostgreSQL tests on Linux.



## R3 local acceptance record

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



## R4 acceptance and clock incident records

See the [R4 contract](r4-research.md) for exact fields, numerical definitions,
bounds and errors, and [R4 verification](r4-verification.md) for actual checks
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
[partial mitigation, incident and recovery](r4-clock.md). Guest NTP conflict
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
[clock fix](r4-clock.md#root-cause-and-application-fix-october-25-2026).

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
see [R4 verification](r4-verification.md).



## R5 acceptance and publication records

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



## R5 model evaluation record

The recorded R5 60-case evaluation achieved 18/20 correct clear specs and zero
unsafe submissions across 40 negative cases; 25 negative cases received the
expected clarification/refusal and 15 failed safely. See verification for model
limitations and earlier failed evaluations.



## R5 publication authority record

The later R5 publication approval authorizes commit/push of the verified scope,
hosted CI checks, actual R5-only fixes through the prescribed coder/reviewer
workflow and publication of actual outcomes. Verification records the exact
published revision and observed hosted results. Local acceptance remains
separate; artifacts/data, credentials, environments and weights stay outside Git.



## R6 acceptance and hosted recovery records

R6 is complete with full local acceptance, independent review and owned cleanup
under [the memo contract](r6-memos.md). [Verification](r6-verification.md)
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



## R6 cold acceptance and verifier follow-up records

The full-month acceptance passed through explicit BTC/ETH profile requests then
cross-asset research using normal verified caches. An earlier cold combined
cross-asset preparation hit the unchanged thirty-minute bound before acceptance;
that failure remains documented. Ollama inference used CUDA; historical integrity
verification, DuckDB and Decimal research preparation used CPU. No GPU data-pipeline
or cold combined-month performance guarantee follows. The known Docker clock
issue persists; the application claim workaround is preserved.

The user subsequently authorized a scoped [cold verifier optimization](verifier-optimization.md)
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
[R6 verification](r6-verification.md).
