# V2 Phase 4 verification

## Publication authorization and pending hosted validation (October 31, 2026)

The user explicitly authorized committing/pushing the locally completed reviewed
Phase 4 work, checking exact-SHA hosted CI and narrowly fixing actual failures
through coder `gpt-6.1-sol/high` and independent read-only reviewer
`gpt-6-astra/medium`. This includes the unpublished user backup commit
`402f3af1ac59cb4c16682d04511579e7145f0c02` above remote baseline
`4972113f007358029a25b7cee1a1ed00a471e6f6`. Independent publication-content review
covered the full 52-file unpublished scope, and root's final repository Ruff and
format checks passed (270 files). These are publication preparation results;
no commit/push or hosted result is claimed at this checkpoint.

Record the actual published SHA, run URL and job outcomes after observation.
Retain failures and distinguish hosted checks from local actual-data, numerical,
resource, backup and preservation evidence. No excluded data/media/credential
file, dependency/limit change, original-service rollout or Phase 5 work belongs
in this publication scope. The local-closeout statements below preserve their
earlier no-publication checkpoint and are superseded only by this explicit
authorization.

## First publication failed; scoped native-identity repair (October 31, 2026)

Reviewed Phase 4 was committed and pushed as
`1760ee5c33b70d1562768c09def443c02103512e`.
[Hosted run 41219190349](https://github.com/atharva-m/MarketLab/actions/runs/41219190349)
failed Ubuntu quality at mypy with eight Windows-only `winreg`/`ctypes` attribute
errors. Integration recorded 26 failures, 238 passes and four historical-input
skips; the failing cases all reached the nonprivileged `/proc/1/ns/pid` permission
denial and the resulting unavailable native-admission identity. Raw logs remain
in `ci-job-124589998845/job-124589998845.log` and
`ci-job-124589998790/job-124589998790.log` under the completion artifacts directory.
The failed run remains failed and is not replaced by local passes.

The repair changes only `native_identity.py`, focused regression coverage and
publication documentation. Windows API guards now use mypy-recognized
`sys.platform` conditions with the same supported-platform runtime ctypes ABI.
Linux validates one bounded, strictly parsed NSpid row containing exactly the
current PID. The [Linux status manual](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html)
defines the values from the proc mount's namespace through nested inner domains;
a singleton matching PID establishes a matching current proc view independently
of PID 1's ptrace-gated namespace link. A readable PID-1 link still must match;
only PermissionError may rely on the mandatory independent proof. Missing,
malformed, duplicate or multi-namespace status remains unavailable. Validated
boot, self namespace inode, PID-1 birth, optional machine ID and the existing v1
canonical hash encoding are preserved exactly, so existing same-domain tickets
retain their identities; foreign-domain death remains unproven. No identity rows
or historical charges are rewritten and no migration is needed.

Focused corrected checks passed 37 native-domain/child tests in 0.45 seconds,
eleven native-self/malformed-identity tests in 0.73 seconds, configured
`mypy --platform linux` across 79 source files, Windows-target module typing,
Ruff and format. The initial combined local pytest invocation had a new oracle
failure because its expected canonical digest omitted the existing trailing
newline; it was interrupted after partial output. Only that test expectation
was corrected. The final focused tests passed without changing test eligibility,
application limits, dependencies, workflow settings or hosted runner privilege.
No unrelated browser-I/O repair or broad suite rerun is claimed from that attempt.

The finite actual probe used two newly owned, network-none containers from the
existing immutable image, executing identity checks as UID 65534 with capabilities
dropped and no new privileges. Both reproduced actual PID-1 namespace permission
denial, validated current/same/live identity and exact child live-to-dead behavior,
and rejected an actual foreign namespace as dead/alive/rebooted. Evidence is
`ci-linux-native-validation.json` and `ci-linux-domain-a.json`/`ci-linux-domain-b.json`;
the executed module SHA256 is
`4639283554749ae2263bdf3148cd317bac8d100456d29ac4129ea81a8c19b0f4`.
Only the two exact label/image-checked probe containers were removed. Their inert
PID-1 holders ignored cooperative termination and exited 137 after Docker's
ten-second stop limit; this is bounded probe cleanup, not normal application
shutdown evidence. The existing image and original services were not changed.

Independent code review passed with no runtime blocker; final outcome/documentation
review and a new published-SHA hosted result are pending at this checkpoint.
`publication-preservation-01` separately matched all 287 protected hashes and
five original service/image/endpoint observations after publication. That is
point-in-time preservation, not continuous uptime. The source inventory and
local acceptance below retain their original source identities; this narrow
Linux portability correction has its own focused and future hosted evidence.

Status: PHASE 4 LOCALLY COMPLETE, October 31, 2026. The simplified actual
three-engine campaign and exact 4 GiB transport/accounting gates passed.
Source-qualified regression gates, final seventeen-database dump/restores, both
package-volume exports, owned cleanup and protected/original preservation passed.
Independent implementation, acceptance, backup/export and cleanup outcome reviews
found no unresolved blocking finding. No commit, push, hosted Phase 4 validation,
deployment or Phase 5 authority is claimed. Earlier failed and interrupted
outcomes remain retained; the checkpoints below preserve their earlier states.

## Final local closeout (October 31, 2026)

`final-backup-completed/receipt.json` passed after rechecking all seventeen
previously verified source/restore snapshot pairs and dump hashes. The narrowly
corrected package-volume export produced two verified host exports containing
240,563,247 and 191,229,130 bytes. The completed backup receipt SHA256 is
`efad73f4de63be8ada99c881976a1b0a2ae6269e4de654323628c7f91c8a5114`.
Independent read-only review verified the completed backup and export evidence.
The first failed backup receipt, partial output, both `export-diagnostic-01` and
`export-diagnostic-02`, and the old operational helper bytes in
`closeout-source-before-export-fix.py` remain retained. The export correction
changed only closeout tooling and did not invalidate browser/numerical results.

`final-cleanup/receipt.json` passed after checking exact ownership and the
completed backup hash. It removed only four owned containers, four volumes, one
network and three owned application images. Before/after preservation passed
for all 287 protected files and all five original service identities/images/
endpoints; original images and the byte-exact README GIF remained preserved.
These snapshots establish the observed interval, not continuous uptime. All
host data, both retained upload files (successful exact 4 GiB and failed partial),
source/output bytes, dumps, exports, logs and failure evidence remain retained.
Historical database states and retained charges were not reset or forgiven.
Independent operational outcome review passed with no unresolved blocker.

The earlier scaffolding cleanup archived and verified 647 redundant loose
helper/draft files before deleting their loose copies. Its archive, original-path
index and deletion inventory remain retained. Earlier cleanup removed fourteen
contained bytecode directories with 164 `.pyc` files; the separate
`completion-bytecode-cleanup.json` records three later helper `.pyc` removals.
No data/evidence/archive/credential/environment/weight/generated-media file was
added to Git. The user-created backup
`402f3af1ac59cb4c16682d04511579e7145f0c02` remains HEAD; this completion effort
made no commit or push.

`final-source.json` inventories 160 executable/test files. Its canonical
files-map SHA256 is
`d9ad84b024d12367067f84a178070b47f5d00c9a14574d8972ea1c0cad53ee05`.
It preserves 151 exact source-04 files plus the explicitly reviewed Vite forward
correction. Reused source-qualified gates include 1,375 offline cases/one skip,
268 PostgreSQL cases, locked quality and packaged API/CLI checks; generalized
actual numerical/oracle/repeat results, all five retained legacy scenarios and
the fresh cold all-62 gate; and the recorded upload protocol/crash/expiry,
cache/recovery and resource-race campaigns. The Vite correction passed affected
frontend build/types/lint, 29 component and 90 mocked browser cases. The new
actual three-engine and exact-size outcomes below supply their own functional,
lifecycle and declared resource evidence. These scopes remain distinct; no
continuous peak, whole-host memory or unmeasured numerical-resource claim follows.

The retired disposable acceptance containers/volumes/network/images are no
longer provisioned. Retained private configurations and resource manifests
describe those historical targets and cannot be treated as live endpoints.
Future replay requires newly owned reprovisioning/restoration and a fresh reviewed
resource/configuration baseline; original services remain excluded. No new
model dispatch, dependency/lock change, original-service rollout, or deployment
occurred. Phase 4 is locally complete under the approved completion amendment.

## Current completion reset outcomes (October 31, 2026)

`browser-actual-01/receipt.json` passed all three gates without forced cleanup.
Its actual Chromium/Firefox/WebKit flows ran from 05:02:04.672 through
06:32:16.303 UTC, with three official submissions, six complete canonical
CSV/Parquet imports, fifteen exact numerical/chart cases, and twenty-four
successful targeted workers. Independent outcome review verified 158 source
bindings, original selected-version/oracle assertions and all three engines.
The workload Job ended empty, held handles closed, and source identities matched.
Its 1,084 service samples have a maximum recorded gap of 6.044 seconds. The
declared mixed non-simultaneous resource envelope was 2,498,179,891 bytes, below
8 GiB; this is Job/process committed-memory high-water accounting plus named
service sampled maxima, not RSS or a whole-host peak. This result is separate
from the earlier failed measured browser campaign and supplies no retroactive
credit to it.

`browser-boundary-01` failed before upload because its exact-label canonical
format selector did not locate the current form. Its lifecycle and resource
gates passed independently, with no forced cleanup. A one-line boundary-only
correction reused the format combobox locator already proven by the successful
canonical flows. The actual-flow functions and main engine loop stayed
byte-exact; independent review approved the correction without repeating the
successful ninety-minute campaign. The exact pre-correction JavaScript bytes
remain at `browser-boundary-01/browser-source-before-selector.mjs`.

Independent review subsequently approved the narrow timeout correction described
below, and root launched `browser-boundary-03` with explicit
`--vite-sha256 e5c3f1c5788f425a47c98348667ed4d1a787b5edf65a5dc54c951a4445fe63a1`.
The original source-04 Vite hash remains recorded alongside the 151 unchanged
files; no claim of 152-file byte equality follows from this forward correction.
The subsequent exact-size result and closeout checkpoint follow. No original
service, model, dependency, commit, or push change follows.

`browser-boundary-03/receipt.json` passed functional, cooperative lifecycle, and
resource gates with no forced cleanup, an empty workload Job, and closed held
handles. Actual UI file selection, incremental hashing, and upload reached
`uploaded` with declared and received lengths of exactly 4,294,967,296 bytes.
The browser rejected the 4-GiB-plus-one file before an import-create request;
the corresponding API declaration returned 422. Supported cancellation then
left the exact-size import cancelled with no ingestion job or publication. The
declared mixed resource envelope was 1,126,327,484 bytes, below 8 GiB. This is a
source-derived transport fixture; no canonical validity, normalization, or new
Binance dataset is claimed.

The read-only `boundary-accounting-after.json` independently hashed both the
retained server file and fixture and verified the cancelled generation, source
reservation, retained charge, released admission ticket, and root inventory.
Both files contain exactly 4,294,967,296 bytes with **file-content SHA256**
`8c9be32517ff0829b055282947e5358a7c5d6ab7c8369af0616c7e6ef18ef8c5`.
The bytes and full charge remain retained, with no refund or publication. This
content hash is distinct from the checker receipt's own hash.

`accounting-after.json` covers all seventeen owned databases and records all
436 observed admission tickets released. Retained source/failure reservations
and historical memo/copilot records remain preserved. `final-inventory` passed
with zero blockers and matched protected/original-service observations. The
owned package-2 API had already stopped cooperatively with exit zero and no
forced termination; no original service was a stop target.

The final backup attempt verified matching dumps and isolated restores for all
seventeen source databases, then failed its package-volume `docker cp` export.
The failed receipt and partial output are retained; no cleanup followed that
failure. A narrow export correction/continuation may reuse those verified dumps
after rechecking them. Overall backup/export completion, final ownership-checked
cleanup/preservation and final outcome review remain pending at this checkpoint.
No overall backup or Phase 4 completion is inferred from the seventeen successful
database subchecks.

October 31 transport correction checkpoint: the successful actual three-engine
campaign remains tied to its recorded source. The later exact-4-GiB attempt
`browser-boundary-02` encountered an observed backend `ClientDisconnect` after
335,957.149 ms, retaining 4,294,930,176 bytes (37,120 short of 4 GiB). Root stopped
the waiting runner and retained the interrupted outcome with no final
lifecycle/resource pass. Root's separate accounting audit verified the retained
generation/source charge, released upload slot, and ready root without a refund.
See `browser-boundary-02/interruption.json` and
`accounting-boundary02-interrupted.json` in the completion artifacts directory.

Read-only inspection of the actual locked Vite/Node configuration established
`requestTimeout=300000`, `headersTimeout=60000`, and connection-check interval
30000, while both proxy timeouts and browser XHR allowed 1860000 ms. Local Node
v22.19.0 source and the
[Node request-timeout documentation](https://nodejs.org/download/release/v22.19.0/docs/api/http.html#serverrequesttimeout)
confirm the independent incoming-request deadline. This configuration mismatch
is observed; its causal role in that specific disconnect remains an inference
because the original browser HTTP 408 was not captured.

The narrow correction sets the native Vite HTTP/1 incoming deadline to the same
31-minute transport constant. Actual-server inspection after the change observed
all three deadlines at 1860000 ms with unchanged header/check intervals. The
boundary harness now watches PUT response/network failure immediately, then
uses the ordinary UI rendering wait. The runner permits only an explicitly
pinned Vite forward hash and records 151 exact source-04 files plus old/new Vite
hashes. Backend, formulas, application upload guards, resource limits, and locks
are unchanged; the successful actual-flow JavaScript functions are byte-exact.

Affected frontend checks passed: build including TypeScript, lint, 29 component
cases and all 90 mocked Chromium/Firefox/WebKit cases in 44.4 seconds. An initial
TypeScript union-property error and a sandbox temporary-file rename denial
(six suites, zero tests run) remain recorded; a property guard and process-local
workspace TEMP/TMP resolved their respective checks. Both fixed owned ports bound
freely after the browser fixture drained. `timeout-correction.json` groups
source identities, before/after inspections, commands/results and the retained
failure/retry references; raw Vitest and browser logs/reports remain beside it.
Independent correction review and a fresh 4-GiB outcome are pending at this
checkpoint. No new dependency/framework, original-service change, commit, or push.

Historical report opening date: October 30, 2026 (America/New_York). The current
completion reset and outcomes above are dated October 31; historical checkpoints
below retain their original pending/failure states and scope limitations.

October 31 completion reset: the user authorized the
[completion amendment](phase-4-completion.md), implementation through coder
`gpt-6.1-sol/high` and independent read-only reviewer `gpt-6-astra/medium`, and
cleanup of unnecessary earlier files with executed evidence/data preserved.
The amendment is documented before its implementation; independent pre-code
review and all new execution/cleanup outcomes remain pending. It supersedes
conflicting harness/closeout requirements without regrading earlier failures or
claiming a new acceptance pass. The user-created backup commit is `402f3af`;
the amendment grants no commit or push authority.

Independent pre-code review of the completion amendment passed with no blocking
finding before the simplified runner was authored. Root's fresh source reuse
baseline verified all 152 source-04 executable files exact; see
`artifacts/v2-phase4-completion-20261031/source04-reuse-baseline.json`. The
retained current-source gates remain scope-qualified evidence, not a new pass.

The simplified Windows lifecycle helper passed six actual native cases (normal
completion and retained post-exit Job memory counter, startup failure, worker
crash, cooperative cancellation, timeout cleanup, and descendant containment
after parent exit) in 1.89 seconds. Focused Ruff/format and JavaScript syntax
checks passed. These are helper checks, not the actual-data campaign.

The first smoke's sandbox loopback denial and subsequent ambiguous connect-based
port preflight occurred before workload dispatch. A direct bind now checks the
two fixed owned ports. `browser-smoke-01` then passed Chromium catalog/readback
but failed Firefox launch through the logical cache path with `spawn UNKNOWN`;
the cause is not asserted. Its unforced workload drain and sampled resource
envelope of 968,108,080 bytes remain recorded separately from that functional
failure. Its original lifecycle classification is retained under that version's
rules. No new browser installation or application-source change followed.

`browser-smoke-02` explicitly used the previously exercised physical installed
cache path and passed all three engines' actual catalog/capability readbacks,
cooperative lifecycle/drain, and the new resource metric at 2,066,247,154 bytes.
This is a short real-stack smoke, with no imports or numerical work; the full
actual-data and exact-4-GiB gates remain pending. Later focused corrections
retain the distinction between functional failure and safe completed drain,
record handle-close failures, and enforce the documented service cadence.
Independent implementation review and the final campaigns remain pending.

Root verified a checksummed archive and every decompressed member before removing
647 redundant loose historical source/draft files. Fourteen contained bytecode
directories containing 164 `.pyc` files were also removed. The archive and index
are `artifacts/v2-phase4-completion-20261031/earlier-scaffolding.zip` and
`earlier-scaffolding-index.json`; action inventories are `scaffolding-cleanup.json` and
`bytecode-cleanup.json`. Executed JSON receipts, logs, measurements, data, private
configuration, dumps, and historical source bytes remain retained. The new
runner has no execution dependency on those archived helper sources. No commit
or push occurred, and Phase 4 remains incomplete.

The user approved Phase 4 scope, contributor/roadmap updates, pre-code contract,
implementation through coder `gpt-6.1-sol/high`, independent read-only reviewer
`gpt-6-astra/medium`, and full local acceptance. No commit or push is authorized.
The normative [contract](phase-4-ui-imports.md) precedes runtime implementation.

## Initial documentation work

Read-only inspection established existing Phase 2 CLI-only staging, the shared
Phase 2/3 capacity helper/root lock, v2 numerical HTTP adapters, locked frontend
dependencies and legacy fixed-date/symbol/unit UI assumptions. Updated AGENTS.md
and ROADMAP_v2.md prospectively and wrote the Phase 4 contract. These are design
records, not runtime acceptance or original-service uptime evidence.

No Phase 4 runtime code, migration execution, application tests, data operation,
service provisioning, commit or push has occurred in this documentation step.
Fresh source/protected/service baselines, independent design review, implementation,
all actual acceptance, backup/restore, final preservation and cleanup remain
pending. Record their actual receipts and all failed invocations here as work
proceeds; never infer a pass from contract text.

## Review and acceptance ledger

### Initial independent pre-code review: blocking findings retained

Independent read-only reviewer `gpt-6-astra/medium` identified three design
blockers in the initial contract: the logical 100 GiB baseline was described as
a rehearsal without mandatory runtime root binding/readiness; native slot recovery
lacked persisted host/boot/PID-birth identity and a concrete death/drain verifier;
and coverage alternatives lacked an explicit response bound/page protocol.
The initial design review therefore did not pass. No runtime code or operations
were started. Contract-only corrections now define root-bound unready/verified
inventory activation and restart/unmanaged-write reconciliation, persisted exact
process identities with fail-closed slot recovery, and bounded coverage preflight
with existing per-day alternative cursors. Independent rereview is pending.

Root reported a fresh read-only baseline: 287/287 protected hashes and all five
original/README service fields/images matched Phase 3; endpoints returned 200.
Receipt: `artifacts/v2-phase4-20261030/preservation-before-elevated.json` with
source-before inventories and `prerequisites-before.json`. The sandbox-denied
initial invocation is retained separately, not converted into a successful check.
Prerequisites inventory reported 148 retained inputs (2,982,488,140 bytes), eight
retained dumps with prior restore evidence, seven actual versions, canonical CSV
191,229,130 bytes and Parquet 16,422,824 bytes, and all three browser engines.
Free bytes measured D: 112,247,279,616; C: 155,077,189,632. This is a point-in-time
prerequisite observation; it is not Phase 4 migration, fresh restore, browser or
runtime acceptance, and not continuous uptime proof.

The following table preserves an earlier checkpoint. Subsequent outcome
entries and the opening status describe subsequent progress; pending items in
this historical table are not claims about the latest state.

| Gate | Observed state |
| --- | --- |
| Pre-code independent review | Initial three blockers resolved; independent rereview passed before contract freeze/runtime edits |
| Runtime implementation and independent review | Core/frontend and Linux native identity repair reviewed; actual packaged CLI inventory defect corrected/reviewed as source 04; final acceptance incomplete |
| Fresh preservation/input/resource baseline | 287 protected hashes and five original/README service snapshots matched; final preservation pending |
| Disposable fresh/populated migration and restore | Corrected exact migration passed new fresh/populated rehearsal, preserved old rows/indexes/273 constraints; verified preupgrade restore; earlier failures retained |
| Discovery/defaults and three-engine actual browser flow | Final mocked 90 passed; actual 01ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œ03 failed preflight, actual 04 published six official days and one exact profile/chart but failed selector/resource coverage; uploads/three-engine completion pending |
| Upload durability/security/accounting/resource matrix | Protocol 01 failed missing process coverage; explicit accounting/drain preserved; event/live-proof sampler correction independently rereviewed, eight disposable probes passed; actual retry/crash/resource matrix pending |
| Final-source backend/frontend/quality/package suites | Frontend 29/90 passed; frozen source 03 backend 1375 plus one skip/264 PostgreSQL passed; source 04 offline 1375 plus one skip and 268 PostgreSQL passed via native observer with wrapper failure retained; source 04 package API/CLI/outage/export checks passed; full closeout pending |
| Retained/generalized numerics, cache/recovery, cold all-62 | New Phase 4 campaigns not run; retained Phase 3 evidence is a prerequisite only |
| Final backups/preservation/owned cleanup/closeout review | Not run |

Phase 4 remains incomplete. Historical Phase 1ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œ3 outcomes and failed publications
remain in their original reports and are not claimed as Phase 4 acceptance.


## Pre-code rereview and immutable contract checkpoint

Independent read-only `gpt-6-astra/medium` rereview resolved the three initial
blocking findings before runtime implementation. The parent froze the reviewed
contract/authority/roadmap/verification bytes in
`artifacts/v2-phase4-20261030/contract-freeze.json` at
`2026-10-30T04:20:55.0604040Z`, with checkout HEAD
`4972113f007358029a25b7cee1a1ed00a471e6f6`. The Phase 4 contract SHA-256 was
`6490407bb182c69e843c12b84d654f4125b17aeebac585f43a5f99274dbd78e9`.
The earlier pending-review paragraphs describe their historical checkpoint;
this passed rereview supersedes their pending state, not their failed findings.

## Owned resources and pre-upgrade preparation

After the passed pre-code freeze, exact absent-name/port/image checks preceded
creation of two disposable containers, two labeled volumes, and one labeled
network. PostgreSQL uses loopback 55452, Redis 56394; image IDs were the existing
pinned local PostgreSQL 17 and Redis 7 images, with no pull or original-service
operation. Sanitized ownership records are `owned-resources.json`,
`owned-volumes.json`, and `owned-network.json` under the ignored Phase 4 root.
Private connection records stay ignored and are not reproduced here.
`provision-invocation-01.json` passed; the owned Docker filesystem reported
946,225,111,040 available bytes. This does not prove later capacity admission.

The first restore/copy invocation failed because the restored legacy catalog
referenced an older numerical manifest absent from the Phase 3 isolated storage
copy. It remains failed in `migration-pre0010/receipt.json`. The continuation
verified the existing restored rows, recovered missing historical artifacts from
the retained R9 source root, and copied with source/destination hash equality.
No source artifact or catalog row was changed. Recovery of 120 older files and
all selected artifact identities is recorded in
`migration-pre0010-resume/receipt.json`. Twenty unavailable historical reservation
paths remain explicitly listed with their charges preserved; their absence was
not treated as permission to release or erase history.

Actual and legacy acceptance databases use distinct owned storage roots.
The populated pre-upgrade database was dumped and restored into a separate owned
database, with exact row, constraint, and index snapshots. Its fresh dump SHA-256
is `cb928e113c8750166e9de4a04491dfae2f3ef5febed1bd9019f5dcc2dacccc97`.
At that checkpoint all three restored databases were at `0009_v2_research`;
D: free space was 108,172,333,056 bytes. Actual/legacy upgrades and runtime root
initialization remain pending; completed historical reads are not new acceptance.

## Migration failures, exact-source reviews, and successful rehearsal

The first execution preflight expected reviewed SHA
`df79e9b3ea8308f48f5f71553edf8e44e9ff2e8c570b11a4f572e9cd995494be`
but observed `367b38070f48a34c5830d87f68ca2a192cf406c726d4fd401c1c35b44b916629`.
The guard stopped before any database operation. The failed receipt is
`migration-reviewed-01-preflight-failed.json`; the current bytes received a
separate independent review before the next invocation.

`migration-reviewed-02` passed fresh migration but failed the populated restore
with `Unexpected import constraint count`. PostgreSQL's restored state-membership
CHECK casts each ARRAY item to text; a newly parsed equivalent CHECK casts the
whole ARRAY to text[]. Exact expression matching therefore found only two of
three expected constraints. `rollback-and-expression-audit.json` retains both
observed expressions and proves the populated transaction rolled back completely:
revision 0009 and all pre-upgrade rows, constraints, and indexes remained exact.
The earlier freshly migrated database remains retained under its original name.

The coder added only the reviewed exact known-equivalent expression form and
independent review approved migration SHA
`92f65d021d65983fbe86a240fe3d0cf7e1480232754ebfa4e8c8771ded75594c`.
`migration-reviewed-03/receipt.json` passed on a newly named fresh database and
the rolled-back populated copy. Old row values were exact after projecting only
the additive default `transport=cli` column; all old indexes and 273 old
constraints were preserved. Exactly three approved import-state constraints were
replaced by the expected transport/owner constraints; five tables were additive.
Roots were unready. The helper's two fresh-database name substitutions and hashes
are retained in `migration-helper-matcher02-freeze.json`; its initial occurrence-
count assertion failure happened before any helper file write or DB operation.

`full-suite-migration-01/receipt.json` then passed the fresh isolated full-suite
`marketlab` database upgrade to 0010 with 36 public tables and no ready root.
No original database was targeted. The dedicated empty browser acceptance
`v2p4_browser` database was separately prepared. Its first migration invocation
failed authentication because an empty explicit password overrode the private
URL password; `browser-preparation-01` remains failed. The corrected explicit
owned password retry passed in `browser-preparation-02`, with zero datasets,
imports, or root bindings. No API was started and no fixture data was registered.

## Incremental implementation and review outcomes

The first independent backend implementation review returned nine actionable
findings. Corrections and complete independent rereview remain in progress;
this is not a backend approval or completion claim. Independent frontend review
returned four findings; corrections and a further cached-operation replay fix
were independently rereviewed with no unresolved frontend blocker, as reported
by the parent. These review outcomes do not replace actual browser acceptance.

Early backend checks were returned in tool outputs rather than standalone raw
log files. The coder retained an honest summary in
`backend-incremental-observations.json`, explicitly marking absent invocation
UTC/source hashes/raw files. These are incremental observations, not frozen-source
acceptance. They include sandbox-denied uv cache operations; initial Ruff runs
reporting 97, then 13, then one error; a four-module mypy pass; 18 focused unit
passes and one POSIX symlink skip on Windows; six PostgreSQL setup errors against
the intentionally unmigrated suite DB; six setup errors from a test fixture's
`%I` driver adapter; and six real PostgreSQL passes after that fixture correction.
The Windows junction/identity gate remains separately required.

The initial full mypy invocation reported four errors in three files. The same
summary records a later corrected mypy pass across 78 source files. Raw
`backend-integration-fourth.log` retains nine passes and one failure: the new
bound-root legacy ingestion regression encountered a Windows extended-path
inventory rejection. `backend-integration-fifth.log` records ten real PostgreSQL
passes after the safe extended-root enumeration correction. Neither later pass
changes the earlier failures or establishes full backend acceptance.

Frontend evidence retains the initial sandbox temporary-file EPERM failures,
initial type/lint corrections, and all unsuccessful mocked browser runs.
`frontend-browser-mocked-01` failed (34 failures/44 passes with interrupted cases,
including Firefox launch UNKNOWN and UI assertions); `-02` and `-03` also remain
failed. Logical browser-cache launches and the physical installed cache remain
distinct invocation facts; no global installation or dependency change followed.
`frontend-full-03/receipt.json` passed typecheck, lint, 29 component cases, and
build with its recorded unchanged source inventory.
`frontend-browser-mocked-04/receipt.json` passed 90 cases across Chromium,
Firefox, and WebKit in 44.0 seconds of reported Playwright time; its UI port was
released. Those tests mock API responses. Real official ingestion and 191 MB CSV/
16 MB Parquet browser upload-through-publication/research/chart flows have not run.

## Pending actual acceptance and closeout

The dedicated browser input manifest records retained source paths/hashes and
metadata, the six-child official BTC/SOL February 28 through March 2 campaign,
and the additional BTC February 1 day. Browser data must enter through the real
UI/adapters/durable workers; no forced catalog fixture registration is acceptance.
The prepared numerical wrapper and literal-adaptation receipts retain the old
harness/reference hashes and exact cold/legacy/numerical assertions, but no new
Phase 4 actual, legacy, or cold campaign has run.

Full frozen-source backend/frontend/package checks, actual three-engine flows,
native upload/crash/accounting/resource races, all retained numerical scenarios,
fresh cold all-62, final dump/restores, final preservation, exact ownership cleanup,
and independent closeout review remain mandatory and pending. Original services
remain outside all operational targets. No commit, push, hosted Phase 4 result,
model call, or original-service rollout is claimed. Phase 4 remains incomplete.


## Later implementation review and backend gate checkpoint

This section records the later checkpoint and supersedes earlier pending states
only where an explicit result follows. Earlier failed invocations remain retained.
The parent reported that independent `gpt-6-astra/medium` core rereviews passed
following iterative corrections to root inventory/readiness, conservative byte
accounting, exact writer/generation ownership and epoch races, native owner and
child-process admission, verifier/bar-worker drain, and HTTP request controls.
Those review reports came through the parent; no standalone raw reviewer transcript
is claimed in these artifacts. The first nine findings and subsequent correction
reviews remain history, not an initial clean approval.

Retained raw checks include 101 unit passes/one skip (`backend-unit-core.log`),
17 real PostgreSQL passes (`backend-integration-sixth.log`), three focused drain
passes, 24 audit/child integration passes, 27 snapshot integration passes with one
deselection, and five ownership-race passes. The real dead-owner upload regression
passed in 62.82s with an actual native process exit and natural lease interval
(`backend-real-dead-upload.log`); it supplements, rather than replaces, the
mandatory separate upload crash matrix.

`backend-unit-http.log` retains 22 passes, one skip and two errors: an oversized
parameter generated a Windows pytest environment variable beyond 32,767
characters. The corrected bounded test identity passed 23/one skip in
`backend-unit-http-second.log`. The native-child unit invocation first recorded
33 passes/one skip/one failure because the Windows fixture selected a redirector
rather than the actual interpreter image; the validator rejected that mismatch.
`backend-native-child-unit-second.log` records 35 passes/one skip after the fixture
correction. The POSIX symlink skip on Windows remains explicit. Initial mypy
assignment/Any errors and Ruff findings remain in their raw logs; later
`backend-mypy-preacceptance.log` passed 79 source files and
`backend-ruff-ownership.log` passed. No dependency or limit relaxation is claimed.

The first broad backend checkpoint recorded 1,347 offline passes/one skip and
252 PostgreSQL passes/two failures. Both PostgreSQL failures expected literal
migration head 0009 after the authorized 0010 upgrade; their raw failures remain
in `backend-full-postgres-first.log`. Later broad checks recorded:

- `backend-final-offline.log`: 1,359 passed, one Windows POSIX-input skip,
  264 PostgreSQL cases deselected, 88.57s.
- `backend-final-{ruff,format,mypy}.log`: Ruff passed; 262 files already formatted;
  mypy passed 79 source files.
- `backend-final-postgres.log`: 263 passed/one failure, 324.37s. The exact legacy
  expected-table set omitted the five authorized additive tables. The test-only
  expected-set correction is pinned in `backend-final-test-correction.json`;
  existing semantic assertions were retained.
- `backend-final-postgres-second.log`: 264 passed, 335.21s. This is an observed
  result, **not final-source acceptance**: the coder reported Linux identity
  changes during the run, cached modules/live file reads may have mixed revisions,
  and no complete final before/after equality receipt exists. The read-only
  `backend-postgres-second-source-observation.json` independently observes current
  native-identity bytes differing from the initial source/freeze receipts. A new
  frozen-source broad gate is required after the scoped repair.

The parent froze reviewed runtime 01 in `runtime-reviewed-freeze-01.json`, SHA-256
`2700a49884c0edb7cd56991da2181a452efe0f686cacb08e24ae0843d98abf51`.
`backend-final-runtime-check.json` observed all 152 runtime entries unchanged at
its own earlier checkpoint. That observation does not validate later changed
Linux source or establish continuity across all subsequent checks.

## Latest frontend and acceptance-harness checks

`frontend-full-final-04/receipt.json` passed typecheck, lint, all 29 component
cases and production build with before/after frontend hashes equal.
`frontend-browser-mocked-final-05/receipt.json` passed all 90 Chromium/Firefox/
WebKit mocked cases in 43.5s Playwright time, unchanged frontend source, and
verified UI port release. These are mocked regressions, not actual import,
official ingestion, numerical results or chart acceptance.

The separate exact-process identity fixture passed acceptance of an independently
queried owned child and rejection of wrong birth/executable/argv/foreign host
(`browser-identity-probe-01`). Browser lifecycle review required stronger
containment because ancestry observed after controller death cannot establish
orphan drain. The corrected helper assigns a private Windows Job while the root
is suspended, disallows breakaway and proves active count zero on drain.
`browser-job-probe-01` and `-02` retain actual disposable cooperative, early-parent-
exit/unseen-child and unresponsive-child cases. Forced termination is an expected
probe condition and would fail a normal actual campaign's cooperative drain gate.

The ignored upload harness received separate actionable review findings: API
orphan drain after root exit, a startup failure before Holder readiness, and
sampling that could incorrectly pass an empty/missing member set. The corrected
helpers use the reviewed suspended-assignment private Job containment, tolerate
unassigned readiness during exact-owned startup cleanup, and require nonempty
PID/birth memory coverage plus maximum one-second sampling gaps. Actual disposable
`upload-containment-probe-26cedd42/receipt.json` passed four fixture cases,
including missing/wrong-birth/empty-coverage rejection. These probes access no
application API/database/data and do not establish the actual fault/resource
campaign. Earlier helper hashes/preparation receipts remain historical.

A relative-path status-print failure after writing the first browser harness
freeze is retained in `browser-harness-freeze-01-failed.json`; no runtime dispatch
occurred. Subsequent absolute-path freezes remain separate receipts. No retained
Phase 3 helper/evidence was edited to prepare these Phase 4 wrappers.

## Additional owned migrations, readiness and failed actual-browser attempts

`actual-legacy-upgrade-01/receipt.json` verified unchanged reviewed migration SHA
`92f65d021d65983fbe86a240fe3d0cf7e1480232754ebfa4e8c8771ded75594c`, exact
pre-0010 actual/legacy snapshots, and original retained dump hashes. Fresh dumps
were restored into separately named owned databases with exact rows/constraints/
indexes before upgrading the acceptance copies. Both upgrades preserved old row
values after only additive `transport=cli` projection, every old index and 273
old constraints; exactly the three approved import checks changed. Fresh dump
hashes are `5ebb05513f15bd46104455ad954fb12cc8687f1030784bb4e6b34842689cdd98`
(actual) and `7ef8ad39b8a322245c6a270f3802b69aa7cd8183fe198bf77403e8f2b7bc1e95`
(legacy). Their pre-0010 restore databases remain retained. The dedicated fault
database was freshly migrated, empty and uninitialized; its API did not start.
No actual/legacy/fault root initialization or numerical campaign occurred.

Only the fresh browser root was explicitly initialized in
`browser-root-initialize-01/receipt.json`, with zero files/retained/reserved bytes,
epoch 1, and source equality checked around the operation. The first owned API
`p4-api-actual-01` returned live/capabilities responses but required readiness
failed PostgreSQL with `InterfaceError`. Its independent native probe observed
default Proactor-loop failure and Selector-loop success. Its clean cooperative
exit receipt is a shutdown result, not a passed startup-readiness gate.

Independent review approved the narrow ignored launcher correction using an
explicit Windows Selector event loop for Uvicorn's serve coroutine. No global
policy, production app or dependency changed. `selector-helper-correction.json`
retains the first text-matcher assertion failure before write and the old/new
helper hashes; the reviewed new helper SHA is
`8f49eb41837540e8751ad557422e4b37e8231d37c521559b728bb9ab813630f2`.
Runtime freeze 02 (`runtime-reviewed-freeze-02-selector-helper.json`, SHA
`944ce57b7d99b5fad510d2b53f79705f17c27bf23c9679c5bca08ca7f8aa3905`) retained
runtime 01 file bytes and updated only the helper entry hash.

API `p4-api-actual-02` initially passed live, required readiness, capabilities and
registry responses (all 200), with exact recorded native PID 6992/birth
134378122364667994. Actual browser attempt 01 then failed before browser/worker
dispatch: the Vite harness imported a raw Windows path, yielding
`ERR_UNSUPPORTED_ESM_URL_SCHEME`. `browser-actual-01/ui.log` and invocation receipt
retain that error and an incomplete cleanup assertion; private UI Job active
count nevertheless reached zero. `browser-esm-probe-01.json` separately proved
raw-path rejection, file-URL import success and exact path round-trip. The narrow
harness correction received independent review and a new separate freeze.

Actual browser attempt 02 failed its exact API identity preflight before UI,
browser or worker dispatch. Subsequent read-only diagnostics established API
6992 absent, native death true, and loopback 55176 refusing connections; passing
the exact integer birth reproduces the guard error. This is **not** a birth
representation mismatch. `p4-api-actual-02/identity-diagnostic-01.json` and
`exit-diagnosis-01.json` preserve evidence and prior file hashes. Its tool session
51255 was unavailable and its receipt still says `running`, with no final exit
record/stdout/stderr file. Exit cause is **unknown**. Tool-session/agent lifetime
loss is a hypothesis only. No unverified process was terminated or restarted.
No actual browser data, worker or numerical workflow has been dispatched.

## Packaged Linux identity blocker and current hold

The owned labeled image build passed as `marketlab-v2p4:20261030`, exact image ID
`sha256:b270f3613515e4894bd6f908f04edba1c8662418efa42e20e6854d25ebc0c9c9`;
`package-final-image.json` binds runtime freeze 01 and unchanged Dockerfile/lock
hashes. Build success did not establish runnable packaged admission.
The actual no-checkout container probe failed native admission identity because
`/etc/machine-id` was absent (`package-native-probe-output.json`). Its owned
stopped probe container was removed only after exact ownership/image/exit checks
(`package-native-probe-cleanup.json`); the failed output and application image
remain retained. No original image/container was a target.

At this checkpoint the parent commissioned a scoped Linux native identity repair
with independent pre-code/code review and new frozen-source checks. The parent
reported 51 focused unit passes/one skip, mypy 79 files and Ruff passing during
that repair; those reported tool outcomes have not been independently promoted
here into a final frozen-source result. Repair rereview/new freeze, new broad
backend checks, rebuilt package/probe acceptance and a root-owned durable API
restart with retained logs remain pending. Runtime/browser/fault/numerical
campaigns are held; original services remain outside all operational targets.

## Read-only final-backup and cleanup preparation

`final-backup-cleanup-plan-01.json` is a **read-only inventory and future plan**,
not an executed final backup/restore or cleanup. It rechecked exact owned
PostgreSQL/Redis IDs, images, labels, mounts and loopback ports; both owned volumes,
the network and its only owned attachments; and the owned application image.
It enumerated 11 non-system owned databases, including historical fresh/rehearsal
and pre-upgrade restore copies, with revisions and sizes. All require retained
final dumps and independent exact restores before cleanup; existing dumps remain
checksummed and untouched. The PostgreSQL `postgres` administrative database was
listed separately rather than treated as acceptance data.

The plan preserves every workspace storage/source/evidence/config/dump path,
including inherited Phase 2/3/R9 sources and all failed bytes/history. Future
cleanup must recheck exact identities/ownership and private-process drain,
verify every final backup/restore and final preservation, and target only owned
resources without prune or wildcard deletion. Existing PostgreSQL/Redis and
original application images remain preserved. Nothing in this plan authorizes
cleanup before mandatory acceptance and closeout review pass. Phase 4 remains
incomplete; no commit, push, hosted result or original-service rollout occurred.


### Concurrent checkpoint additions

While this report was being updated, `browser-actual-03/invocation.json` recorded
another failed preflight (AssertionError, 1.24s). The frontend coder reported an
exact target-command mismatch before dispatch and the target API absent on its
subsequent inspection. A possible interpreter-flag/recorded-argv mismatch is a
reported hypothesis requiring retained native argv evidence; it is not an
established cause and does not authorize weakening identity checks. No actual
browser/data pass is claimed. The parent owns subsequent restart/repair decisions.

`final-source-path-retention-inventory-01.json` additionally records 1,324 exact
source/destination/root paths from prerequisite and historical copy receipts; all
were present during this read-only stat inventory. It references prior verified
content hashes and does not claim a fresh full-content preservation pass. Every
listed path, all twenty unavailable historical reservation identities and their
charges, and all existing evidence/dumps remain retention targets. No cleanup or
final dump/restore was performed.


## Source 03 Linux repair and final gates

The scoped Linux identity correction was independently reviewed, then frozen in
`runtime-reviewed-freeze-03-linux-native.json`, SHA-256
`857b6dad9de30b570bce07cb4eb4205b9ca763caeaa65add2018d05208b46348`.
`backend-nativefix-source-before.json` and `backend-nativefix-source-after.json`
retain the source interval: all 152 frozen entries matched, with zero mismatches.
`backend-nativefix-offline.log` passed 1,375/one POSIX-input skip in 95.31s;
`backend-nativefix-postgres.log` passed 264 in 325.84s, with no local historical-
input skips. Ruff and mypy across 79 source files passed. The first format check
failed on a Python example in documentation; that example alone was corrected,
and the second format log reported 262 files already formatted. These results
validate source 03, not the subsequent source 04 CLI correction. The older mixed-
source 264-pass run remains explicitly source-qualified and is not promoted.

The repaired owned image `marketlab-v2p4-nativefix:20261030` has exact ID
`sha256:bdeef1b64e026567a844de6cd1c0e1999b95c9eb4598f7ca66518dd174ea4cab`.
Its actual isolated Linux probe passed self identity, separately launched child
identity/ancestry and child death despite absent machine-id; host/package source
SHA `482513c40683344763b8aade876b6f69a4f62c23ee4c8961ad1f0f3576033175`
and lock SHA matched exactly (`package-nativefix-identity-parity.json`). Package
Git provenance honestly remained unavailable/null. Exact stopped probe containers
were ownership/image checked before removal; both old failed/probe image history
and application images remain retained. Native probe success is distinct from
packaged API/CLI/data acceptance.

## Correction to API 03 diagnosis and partial actual browser 04

The earlier concurrent API 03 follow-up was an unverified report, **not valid
native death evidence**. Root's retained
`p4-api-actual-03/root-command-diagnosis.json` independently observed API 52296
alive with the exact native integer birth. Actual argv included root's `-u`
interpreter flag, which reconstructed `ready.argv` omitted; that extra token
caused the exact command mismatch. Strict checking of that known launch flag
explained the mismatch without relaxing application process identity. Two earlier
root diagnostics used a string birth or the wrong helper argument position;
those failed calls made no stop and do not prove death. API 03 was then stopped
cooperatively with the exact verified nonce and exited normally, as its final
receipt records. API 02's abrupt unknown loss remains a separate unresolved fact.

Root launched API 04 without the extra flag; the same browser harness verified
its exact native command and all four required HTTP responses returned 200.
`browser-actual-04` then performed actual UI registry/official submission and a
durable six-child BTCUSDT/SOLUSDT February 28 through March 2 ingestion campaign.
All six jobs succeeded once. One Chromium official market-profile research run
succeeded once, with exact independent numerical projection and bar equality;
its run JSON and actual chart screenshot remain retained. No model calls were
needed. These are observed partial actual passes, not a completed browser gate.

Actual 04 ultimately **failed**: its timestamp combobox filter timed out after
120s, and required resource coverage had two sampling gaps above one second
(maximum 1.8418s). The raw browser error, screenshots, memory samples and
`sampler-gap-diagnosis.json` remain retained. No canonical upload completed and
Firefox/WebKit actual flows were not reached. Controller and UI private Jobs
cooperatively drained to active zero without forced fallback, all worker intents
resolved, and API 04 subsequently exited cooperatively. A later clean shutdown
does not turn this failed invocation into acceptance.

Independent review approved the narrow selector and decoupled resource sampler
corrections. The installed native CPU/birth/memory sample path stayed distinct
from slower optional GPU/WDDM observations; missing native memory/birth data still
fails closed. `browser-sampler-diagnostics-01` retains wrong-birth/unavailable-
memory rejection and actual timing diagnostics. Earlier unsuccessful stress
probe invocations remain intact. The final
`browser-actual-sampler-probe-05/receipt.json` passed all three engines' rendered
selector checks with mocked API reads, 209 complete native samples and maximum
0.266s gap, while two owned CPU fixtures each allocated 64 MiB. All private Jobs
reached zero and UI port released. It accessed no actual API/database/data; it
is a harness stress fixture and does not replace actual three-engine imports.
Its actual interval is recorded, rather than inferred as overlap with every
other campaign.

## Actual fault protocol failure and reviewed event capture correction

Only the fresh owned `v2p4_upload_faults` root was initialized for the fault
campaign (`fault-root-initialize-01`), under source 03 with exact reviewed helper
hashes, no prior rows/files and no active writers. Root ID is
`87caca3c-9360-4236-9001-1b88a91bfc84`, epoch 1, zero initial charges. No original
resource was involved.

`p4-upload-protocol-01` exercised real HTTP controls using explicitly controlled
transport fixtures, but its mandatory memory coverage gate failed: private Job
native total was four processes while 250ms polling observed only three distinct
PID/births. The missing fourth identity is **unknown**; it must not be relabeled
as a verifier, Git or other process without evidence. There were 111 samples,
110 nonempty samples, no sampled inventory errors and maximum gap 0.267s; none
of those facts waives completeness. The old API startup checked LIVE only, so
required readiness was not established by that invocation. The run remains
failed despite its later clean drain.

`failure-audit.json` retains equal source-before/after hashes, API exit 0,
private Job active zero/no members/no forced fallback, and final real-service
states: 17 cancelled imports/one terminally failed import, two cancelled jobs/
one failed job, zero active admission tickets, 807 retained bytes and zero
reserved data bytes. No DB state was forced and no failed bytes were deleted.
Subsequent expiry, five-boundary native crash, 4 GiB, quota/slot/physical resource
and root-lifecycle modes have not yet run. No full upload matrix pass is claimed.

The independently reviewed ignored API child correction uses the same explicit
Windows Selector runner as the browser helper (SHA
`55a1bc0a88389407ce3e7759cd38782d41e1007d4d37f4eb354a3a892c0ed02e`).
Startup now requires LIVE and required READY HTTP 200. The event sampler is a
new owned adapter rather than a modification to the shared browser Job helper:
completion-port association precedes assignment/resume, root CreateProcess
handles are retained synchronously while suspended, and child notification
handles must prove exact Job membership, native birth, executable and RSS.
Handles stay retained through drain. Events are only a capture aid: native total
must still equal valid distinct captured identities and NEW_PROCESS notifications,
with 250ms target/maximum one-second polling gap and explicit failures for missing,
late-unopenable, wrong-birth, access-error or dropped observations.

The first sampler review found post-exit zero-RSS identities could count without
immutable initial-live evidence. The first correction's manifest overstated a
pre-query check that was not actually inserted. Independent rereview caught that
specific mismatch; both prior manifests/bytes and probe outcomes remain retained.
Final adapter SHA
`382c0830eeb71c6ecb8e15b9bd606b225a8aa77b347910641bcf833c9902cfa5`
has an actual native alive check at entry **and** after the memory query, with
immutable initial-live proof required by coverage. Child handles request
SYNCHRONIZE for native wait queries; an earlier stricter probe failure exposing
the omitted access bit remains retained. No threshold was lowered.

`fault-event-probe-99682ec6/receipt.json` passed eight disposable process cases
on equal before/after helper hashes, including a short child gone before first
poll, controlled access/stale-birth/drop failures, and an actual delayed child
notification released only after a separately held exact-Job native handle
proved death. That post-exit-only identity was rejected and coverage failed as
expected; a focused check proved no memory query occurred for the dead handle.
All event threads/capture handles and Jobs drained. These are harness probes,
not actual fault acceptance. The parent reported independent rereview passed
final bytes, then wrote `upload-reviewed-freeze-04-cli-events.json` for source 04;
actual retries remained held while new broad backend gates ran.

## Actual package CLI defect and reviewed source 04

The first actual package attempt failed its API health/lifecycle harness before
normalization (`package-actual-01/accept.log` and failure receipts). Independent
helper corrections and separate readiness probes followed. A root preflight
quoting SyntaxError occurred before any Python/DB operation and is explicitly
retained in `package-clearance-01-failure.json`; the saved-script retry passed.
Later actual package attempt 02 exposed a **production CLI source-inventory
defect**, not a harness-only mismatch: the CLI retained the actual 191,229,130-byte
canonical SOL CSV and its conservative charge, then retired active-path ownership
without registering the file inventory. Admission correctly marked the root
unready; the normalization job remained queued with attempt count zero.

`package-actual-01/attempt-02/read-only-accounting-diagnosis.json` preserves the
unready binding, missing file receipt, retained exact source/charge and waiting
job. No reconciliation, reset, forced catalog registration or retry altered that
failed database. The old volume's actual source was exported and independently
hash-verified to `failed-volume-export`: SHA
`892e93a11d0c6e6b3339e10ab2b4ac5c6a04d6cc511a78c02d0026381828f9d5`,
191,229,130 bytes. `failed-volume-export-verified.json` explicitly records no
volume removal or database-state change. Its database, volume, source and failure
history remain final backup/retention targets.

The narrow runtime correction inventories and reconciles exact positively drained
CLI source bytes before admission release. Focused tests verify successful/replay
behavior, exact partial-write retention and withholding release after inventory
failure. The initial focused run had three Windows default-temp setup errors;
a workspace-temp retry passed three cases, then a fourth gate was added and all
four passed (`backend-cli-inventory-focused-03.log`, 3.43s). Focused Ruff/format/
mypy passed. The parent reported independent rereview passed, then froze source
04 in `runtime-reviewed-freeze-04-cli-inventory.json`, SHA
`9a4bf6d40125065e060a0b5cf56b6712a0c73812ec14adcc64b040ee1e0aed84`.

At this checkpoint source 04 Ruff, format (262 files) and mypy (79 files) logs
passed; its offline log recorded 1,375 passes/one skip in 86.31s. The PostgreSQL
run was subsequently interrupted at 47%, leaving its partial log and no final
receipt; no new full-source interval completion is claimed here. Root reported
execution session 12421 unavailable to both the coder and root. An elevated
process inventory found no Python/uv, but no exact recorded PID/birth exists for
that query, so it is not direct native proof of a particular process death or
exit cause. Cause remains unknown; a root-owned rerun was being prepared. The
interrupted invocation remains incomplete rather than a test failure or pass. The source 04 owned image build passed as
`marketlab-v2p4-cli-inventory:20261030`, exact ID
`sha256:b2a0fea85e88f20976c2405e02b0b88a6df7ff0cc4078354d3517c17e8458b74`
(`package-cli-inventory-image.json`); old images remain retained. New packaged
actual acceptance requires a separately named database/root/container and complete
reviewed source 04 gates. Frontend was preparing a separate tiny fixture-only
upload smoke on an isolated DB/root with serialized owned ports; preparation is
not an executed test or actual-data acceptance.

## Read-only numerical initialization preparation under source 04

New `prepare_numerical_roots.py` and
`numerical-preparation-review-manifest-04.json` prepare exact commands and guards;
only their **plan** actions ran. The owned actual/legacy databases remain 0010
with no root binding, zero active admission tickets and no running ingestion or
research. Plan receipts are `p4-numerical-{actual,legacy}-plan-01/receipt.json`.
Supported safe inventory stat traversal observed actual 297 files/1,165,908,679
bytes and legacy 356 files/2,906,688,882 bytes. This is a read-only stat inventory,
not a new full file-content verification or initialized-ready claim.

Actual historical storage rows retain 77,309,804,544 reserved bytes, including
scratch reservations; the runtime's unchanged logical DATA projection includes
12,885,295,104 pending data bytes. Thus the prospective actual logical baseline
is 14,051,203,783 bytes and legacy 2,906,688,882 bytes, both under the unchanged
100 GiB ceiling. Every historical storage/research reservation row must remain
exact, including unavailable historical paths; scratch reservation history is
not refunded by excluding it from the logical DATA projection. The plan observed
103,435,444,224 workspace free bytes; physical/per-run guards still apply when
work is eventually attempted. No parallel-heavy-work allowance is inferred.

The prepared initialization path rechecks exact container ownership/ports/mounts,
source 04 bytes, absent first binding and quiescence; retains a fresh custom dump
and complete row/constraint/index snapshots; restores to separately named absent
owned `v2p4_actual_preinit04_restore` or `v2p4_legacy_preinit04_restore`; and only
then calls the supported explicit production `admission.initialize`. It will
require old table/reservation rows, constraints/indexes and filesystem stat
inventory unchanged, exact retained/pending-byte receipt, ready binding and equal
runtime bytes. Neither initialization path nor backup/restore mutation has run.
These two prospective restore names require review/explicit operational clearance.

The old wrapper and source/evidence remain untouched. A new wrapper and literal
adaptation preserve the old numerical/cold assertions and formulas; their sole
additional retained-source change allows exactly the read-only Phase 3
`p3-actual-05` oracle directory, instead of erroneously requiring it inside the
new Phase 4 root. Nine retained oracle/selection/invocation files are hash-bound.
`numerical-source-review-candidate-04.json` binds source 04, current broader
source, wrapper/adapted/helper hashes and retained oracle inputs. Static compile
and module-load checks passed; this candidate has not been independently
approved or used for a numerical run.

Prepared order is explicit actual/legacy initialization, retained-oracle
preflight, nine generalized actual numerical campaigns with fresh-key repeats,
five retained legacy scenarios/v2 projections, then serialized cold all-62 with
unchanged assertions and drain. Cold flush targets only owned Redis 56394/DB0
and therefore requires every other owned consumer quiesced. The wrapper honestly
records memory unmeasured. Root clarified that numerical scoring can retain this
limit while the separate mandatory actual resource gate supplies required
measurements; this preparation does not add a new supervisor acceptance blocker.
Existing reviewed exact-owned process/drain controls remain mandatory, and any
necessary supervision should prefer the retained reviewed Phase 3 mechanism. No new numerical,
cache/recovery or cold workload has run. Phase 4 remains incomplete, with no
commit/push, hosted claim or original-service operation.


The parent reported source 04 package helper revision 03 independently passed,
with no fresh package resource provisioning at this checkpoint. Root-owned
PostgreSQL rerun, approved actual fault retry, and tiny fixture smoke remained
separately sequenced work; none is inferred from this preparation packet.


Root accepted the exact two prospective pre-initialization restore database names
within owned preparation, subject to independent helper review. The corrected
`numerical-preparation-review-manifest-04a.json` preserves the prior packet and
clarifies separate numerical scoring versus mandatory actual resource measurement.
No initialization or numerical execution followed this clarification.


### Numerical target guard correction and PostgreSQL retry observation

Independent numerical-helper review found one blocker: configuration checked
the owned container ledger but passed unchecked `postgres_container` to future
Docker backup/restore commands. The correction binds that field to the inspected
owned PostgreSQL name, exact recorded container ID and loopback port 55452; all
future pg_dump/createdb/pg_restore execs use the verified ID. Seven pure checks
passed correct-target acceptance and rejection of changed configured name, ID,
container name, port, public bind and owner label, with zero Docker/DB calls.
The prior helper remains byte-exact in an ignored backup; the new narrow diff,
probe and `numerical-preparation-review-manifest-04b-pg-target.json` are retained.
A refreshed source candidate binds the corrected helper; independent rereview
remains pending, and no initialization/backup/restore/numerical command ran.

The root-owned PostgreSQL retry spawned its runner, but its recorder failed
before persisting the original Popen completion/receipt. This remains a recorder
failure, not a PostgreSQL assertion result. The separate read-only native observer
retained exact runner/child births, executable and argv in
`backend-source04-postgres-retry-01-observer-attached.json`; the partial test log
continued beyond the previous 47% point. At this update no observed completion/
exit-code receipt was yet promoted here. Original failed/partial logs remain
retained; final test, source equality and exact process drain must be reported
from the independent completion observation when available.


## Source 04 PostgreSQL native completion observed

`backend-source04-postgres-retry-01.log` completed with 268 passes, 1,376
non-integration cases deselected and six warnings in 326.95s. The original retry
wrapper remains failed: it called the Python-child identity helper on the uv
launcher and failed before recording Popen completion. Root's separate native
observer independently opened exact birth/argv/executable-checked handles for
uv/runner/interpreters, observed all four exit codes zero and all native processes
dead, and retained matching runtime/test bytes in
`backend-source04-postgres-retry-01-observer-completed.json`. This establishes
the test result and exact observed drain without converting the wrapper into a
successful invocation. The initial 47% interruption and its unknown cause also
remain retained.

`backend-source04-consolidated.json` records all 152 frozen runtime entries exact,
unchanged test source, Ruff/format/mypy passing, 1,375 offline passes/one skip,
and the independently observed 268 PostgreSQL passes. These are final source 04
backend checks, distinct from actual browser/resource/numerical acceptance.

## Successful source 04 package checks and retained timing limit

The fresh source 04 package environment uses database
`marketlab_phase4_package_2`, container `marketlab-v2p4-package-2`, volume
`marketlab-v2p4-package-data-2` and the reviewed image
`sha256:b2a0fea85e88f20976c2405e02b0b88a6df7ff0cc4078354d3517c17e8458b74`.
An initial provision attempt found owned port 55179 occupied by the older package
namespace. Root verified the exact old namespace/process/data state, stopped
only the old owned container to release that port, and retained its database,
volume and verified 191,229,130-byte export without reconciliation or deletion.
The first preflight mount assertion failure is separately retained; the observed
exact mount was inspected before proceeding. Receipt:
`package1-owned-stop-release55179.json`.

`package-actual-02/attempt-01/package-source04-consolidated.json` records passing
actual packaged API/CLI checks: canonical CSV stage/replay/normalization, Parquet
HTTP generation/finalize/normalization, full logical equivalence, pinned bars and
market-profile results/summary equal independent Decimal references, HTTP replay
and CLI result parity, queued official/research cancellation with zero extra
attempts, idle worker SIGTERM/native drain, API shutdown/restart/replay, and no
memo/model work. The package source/lock identities and honestly unavailable
no-checkout Git provenance remain recorded. These checks supplement the separate
complete browser and retained numerical campaigns.

The exact owned Redis outage returned BYPASS for bars/summary while preserving
independent content, then restored the same Redis container ID. Post-restoration
checks observed MISS followed by HIT for both caches with exact content. No
original Redis/service was targeted. Native final API/worker/monitor drain and
zero live admission/running work were recorded. All 12 retained package volume
files, totaling 240,563,247 bytes, were exported to host evidence and fully
size/SHA verified (`retained-export-verified.json`). Container/volume/database
resources remain present; final dumps/restores and closeout cleanup are pending.

The outage receipt ends at 07:56 UTC, while cache recovery/drain/export receipts
resume at 14:38–14:39 UTC. This interval contains an unexplained pause; neither
continuous observation/uptime nor controlled latency/resource-peak results are
claimed across it. Parent descriptions of a model/session pause do not establish
a continuous monitored interval or repair the missing observations. Earlier
package health-route, Linux identity, source-inventory and provisioning failures
remain failed and retained.

## Dedicated tiny three-engine browser fixture smoke

A separately owned `v2p4_browser_fixture` database/root was freshly migrated and
explicitly initialized before smoke testing, with no prior browser database/root
reset. Its isolated adapter retains the reviewed serialized loopback UI/API ports
55175/55176 and source 04; original browser resources remain separate.
`browser-fixture-provision-01/receipt.json` records zero pre-initialization
catalog/import/root rows, migration Job active zero, exact original owned
PostgreSQL/Redis identities and empty-root initialization.

Fixture smoke 01 published its 16-row CSV, then failed a harness form-remount
race before the Parquet create. Actual failed diagnostics and the retained CSV
publication remain intact. The offline rendered reproduction established that
Start fresh exposed a transient form before the hash-route keyed remount, clearing
filled fields and triggering native form validation. The narrow helper correction
waits for the exact route/stable document/registered option and verifies field
values/validity. It passed independent review and three mocked-engine diagnostic
reproductions; it changed no runtime or full actual browser runner behavior.

`browser-actual-fixture-smoke-02/invocation.json` passed in 29.52s with actual
Chromium, Firefox and WebKit: six tiny CSV/Parquet publications, three pre-finalize
cancellations and three reload recoveries. All six worker births were sampled;
controller/UI private Jobs cooperatively drained to zero and the UI port released.
Root subsequently reported the exact fixture API exited zero. Fixture inputs
were the first 16 real rows of the verified retained SOL source, prepared under
explicit new-source identities; they are **not** a full-day canonical upload,
official ingestion, numerical/chart or complete-capacity acceptance substitute.
The full actual browser 05 campaign was running separately at the next parent
checkpoint; no result is inferred from its progress or from this fixture pass.

## Numerical initialization failure and scoped approved lifecycle correction

The first authorized actual-root initialization attempt
`p4-numerical-actual-init-01` failed in its container startup preflight before any
DB initialization/backup/restore mutation. The original baseline Redis StartedAt
no longer matched after the explicitly authorized package outage, even though
its exact container ID/image/mounts/ports/labels were unchanged. The strict guard
correctly stopped; that failed invocation remains retained. Actual and legacy
numerical initialization still have not run.

`authorized-redis-lifecycle-package-outage-01.json` pins only that observed
same-ID Redis transition from `2026-10-30T04:22:52.154252934Z` to
`2026-10-30T07:56:19.564350294Z`, together with exact unchanged configuration,
read-only PING and hashes of the successful outage and restored MISS/HIT content
receipts. The helper and new retained numerical adaptation accept precisely that
pinned transition, preserve PostgreSQL's original-start guard, and reject any
arbitrary later Redis restart. Thirteen pure lifecycle/regex checks passed with
no Docker/DB/API calls. The old helper/adaptation and failed initialization are
retained byte-exact. No formula, numerical assertion or resource ceiling changed.

Root also found that retrying the old fault protocol would reuse fixed logical
idempotency keys from cancelled protocol 01 imports. Before any retry, a narrow
helper correction put an explicit immutable per-invocation namespace in the shared
controller support module and applied its deterministic key mapping centrally in
request(). Equal logical keys remain equal for body-conflict/replay checks and
across API crash restart; different invocations map differently. Canonical imports
by the resource helper share the same namespace; worker/API children do not
synthesize separate control keys. Capability filenames and logical case labels
remain unchanged. Eleven fake-transport pure checks passed; the generated 74-byte
keys match the production `[A-Za-z0-9_.-]{1,128}` constraint. No actual protocol,
expiry, crash or resource retry ran during this correction.

Independent read-only review passed the combined
`ops-helper-namespace-lifecycle-review-packet-01.json`. Root approved numerical
candidate 04c for later serialized work and wrote
`upload-reviewed-freeze-05-invocation-namespace.json` for future fault runs. These
are helper approvals/source freezes, not runtime campaign results. The full
browser campaign retained exclusive heavy-work priority; all numerical/fault
operations remained held.

## Refreshed final resource and backup plan: read-only, 14 databases

`final-backup-cleanup-plan-03.json` re-enumerated the current exact owned inventory
while the browser campaign ran. It used only Docker metadata and light database
names/revisions/sizes; it ran no data-content hash scan, backup, restore, export,
worker mutation or cleanup. The preceding plan-02 invocation stopped on its
incorrect prospective `/data` mount assertion, before DB inventory or mutations;
that failed receipt and script remain retained. Exact inspection established both
package volumes mount at `/data/marketlab`; the separate plan-03 retry passed.

The observed inventory has **14 non-system databases**, four owned containers,
four owned volumes, one network and three retained application images. The old
failed package container is stopped; the successful package container remains
present/running with its application workers drained. Both PostgreSQL/Redis
containers retain exact owned identities, and the network has no foreign
attachment. The 14 source databases are:

`marketlab`, `marketlab_phase4_package`, `marketlab_phase4_package_2`,
`v2p4_actual`, `v2p4_actual_pre0010_restore`, `v2p4_browser`,
`v2p4_browser_fixture`, `v2p4_fresh`, `v2p4_fresh_matcher02`, `v2p4_legacy`,
`v2p4_legacy_pre0010_restore`, `v2p4_populated`, `v2p4_preupgrade_restore`,
`v2p4_upload_faults`.

The PostgreSQL administrative `postgres` database is listed separately. No new
numerical pre-initialization restore database exists yet. Future successful
initializations/verification restores will increase the inventory, so exact names
must be re-enumerated immediately before final backup rather than reusing any old
nine/eleven/fourteen count as a permanent allowlist.

For every listed source database the plan contains exact argv and stream paths
for custom-format `pg_dump`, separately absent owned restore creation and
`pg_restore --exit-on-error`, targeting only the exact verified owned PostgreSQL
container ID. It requires a fresh dump checksum and complete original versus
restored row/constraint/index/revision/accounting/catalog comparison. All command
entries remain **unexecuted**. Each restore database remains an explicitly named
retained verification artifact rather than a cleanup shortcut.

Both package volumes and host exports remain retention targets: old package one
file/191,229,130 bytes and successful package 12 files/240,563,247 bytes. Existing
full-SHA export receipts are referenced, not freshly rehashed during this light
inventory. Final quiesced volume inventories must match host export path/size/SHA
before any removal. Failed package state must not be restarted/reconciled merely
to obtain another export. All host data roots, inherited sources, credentials,
private configs, evidence, dumps, exports and failures stay ignored and retained.
Future cleanup is limited to exact ownership-checked IDs/names after mandatory
acceptance, final backup/restore/export/preservation and closeout review pass;
no prune, wildcard deletion or original service/image target is permitted.

Phase 4 remains incomplete. Required full actual browser, fault/resource/expiry/
crash, retained/generalized numerical/cold, final preservation/backup/restore and
closeout gates cannot be inferred from these source/package/fixture passes.
No commit or push occurred.

## Browser actual 05: retained functional results, failed overall campaign

`browser-actual-05/invocation.json` records an operator-interrupted failure after
4,121.904213s on runtime source 04. Chromium completed the six official BTC/SOL
daily publications, each on attempt one, the full retained canonical CSV and
Parquet imports, and three market profiles with exact independent oracles and
bounded charts. The retained per-case JSON/screenshots establish those functional
observations. The campaign did not submit a comparison POST or finish the other
engines/workflows; no overall actual-browser pass follows. The controller and UI
private Jobs drained to zero without forced termination; root separately observed
the exact API exit zero. The stop reason and all completed/failed case evidence
remain retained.

The offline actual-React reproduction
`browser-offline-research-transition-03/diagnosis.json` observed that counting
instrument checkboxes before metadata loaded could yield zero, skip selection,
leave only SOL selected and produce no comparison POST. Waiting for registered
options and asserting the exact two selections produced the comparison POST in
the corrected diagnostic. This demonstrates a harness readiness race offline;
it is an inference about the interrupted actual campaign, not an observed trace
of that campaign's original checkbox state. Runtime code was unchanged.

Resource coverage **failed**. `memory-failure-summary-01.json` retained 15,893
samples, 46 samples with native errors (80 error instances), and two excessive
gaps of 1.0029367s and 1.2513317s. The native-error samples temporally overlapped
optional GPU queries, which does not prove the missing process identities or
explain every failure. Root reported approximately 3.41 GB harness total memory;
this is not a valid measured application peak or a BTC batch resource pass.
The separate 600-call native-inventory fixture observed retained ctypes classes
grow from 2 to 1,202, RSS by 10,555,392 bytes and private memory by 11,194,368
bytes. It proves that fixture's class-growth behavior, not the entire cause of
the long campaign's memory growth/errors. Its private Job drained to zero and
the retained R8/process helper sources stayed exact.

Root approved a separate functional-case audit and a fresh measured actual
campaign across Chromium/Firefox/WebKit using full SOL official/CSV/Parquet and
all five research cases, with optional GPU sampling disabled prospectively and a
cached native observer undergoing implementation review. These are future gates;
no resource credit, full three-engine pass or BTC batch peak is claimed here.

## Upload protocol and native crash checkpoints

`p4-upload-protocol-02/receipt.json` passed 19 controlled HTTP transport cases on
the reviewed per-invocation-key/event-sampler freeze 05. Its API memory receipt
records 117 samples, maximum gap approximately 0.2672777s, and complete four-native
process/four-event coverage. These fixtures exercise protocol failures/replays/
races; actual-source and full-capacity gates remain distinct. Protocol 01's
unknown-fourth-process coverage failure and retained charges remain intact.

The retained canonical Parquet actual-HTTP/native-death runs
`p4-upload-crash-before-claim-01`, `p4-upload-crash-during-write-01` and
`p4-upload-crash-after-bytes-01` passed their respective before-claim, during-write
and after-verified-bytes boundaries. Their receipts preserve native death,
recovery, exact source identity and natural lease behavior without database
state/lease forcing. These three passes do not establish the remaining two
commit boundaries.

`p4-upload-crash-before-finalize-01` failed with WinError 10048 at the ordinary
post-drain bind check. Later read-only diagnosis proved all four exact native
processes dead, private Job active zero, no current port-55178 listener and a
successful ordinary bind. TCP state at the original failure was not observed;
transient release/TIME_WAIT is only a plausible inference. The failed invocation,
import bytes and charges were retained without reset or refund. An independently
reviewed helper-only correction adds a bounded 90-second availability wait,
retrying only WinError 10048, after unchanged native Job drain proof. It changes
neither socket-reuse/system settings nor process/resource gates. Four native
port/error probes passed; root wrote `upload-reviewed-freeze-06-port-release.json`.
That approval is not a successful actual before-finalize retry.

At this checkpoint `p4-upload-expiry-01/receipt.json` is still running. Root's
`expiry-initialization-overlap-01.json` authorizes only tiny-body natural expiry
alongside initialization of a separate retained root, with no heavy numerical/
normalization/resource benchmark or Redis lifecycle change. Expiry memory covers
only its declared API Job, not shared PostgreSQL/Redis; initialization has no
performance claim. No natural-expiry completion is inferred.

## Numerical pre-initialization restore mismatch and separate approved retry

`p4-numerical-actual-init-02` created a fresh custom dump and the separately owned
`v2p4_actual_preinit04_restore`, then stopped at strict restore equality before
root initialization. Read-only diagnosis observed all 37 table row hashes/counts,
indexes and revision equal, identical constraint identities, and exactly seven
CHECK text differences: PostgreSQL deparsed array-wide varchar-to-text casts as
per-element casts on restore. The source still exactly matched its retained
before snapshot and had zero capacity-root bindings. This failed restore and
dump (SHA256 `51a279c9053e124931c602d1335008d6fad679f3b843a89270d17d057a759af3`)
remain retained. The measured non-system database inventory at that diagnosis was
15, including this new failed-initialization restore; future restores increase it.

Independent review passed `numerical-restore-review-packet-05.json` and the
separate `prepare_numerical_roots_candidate05.py`, SHA256
`19ae00c125551be5376709cb9f251e40376fc9e20bd7a86fe870fe7a3c0c0da1`.
It reuses the unchanged, hash-pinned strict closeout comparator: all table hashes/
counts, indexes and revision stay exact; constraint schema/table/name/type/key/
reference/deferrability/validation/local/inheritance flags must match. Only the
seven observed CHECK identities may differ in text, and each must exactly equal
PostgreSQL's reparsing of the source expression on a restore-only TEMP LIKE table
with ON COMMIT DROP. No regex normalization, dropped definition or source schema
change is allowed. Twenty-four pure mocked comparator/rejection checks passed
before any retry SQL.

Root invoked this separate candidate directly for
`p4-numerical-actual-init-03`, using the new
`v2p4_actual_preinit04_restore_02` and preserving the failed prior restore/dump.
At this checkpoint its retained database-restored and seven-CHECK server-reparse
proof files exist; root reports initialization still running, with no final
receipt yet. No initialization success or numerical campaign result is claimed.
Final inventory must include both restore databases and any later legacy/cache/
closeout restores rather than reusing the old 14/15 count.

The original `prepare_numerical_roots.py` remains unchanged at SHA256
`5da292731c84ce607811475bc1b75548ecb13c71bbe508c46fb0c4067e2f454e`.
Numerical wrapper/cache/closeout imports continue to use its approved configuration
and exact-lifecycle guards; the separate initializer does not replace that module.
`numerical-downstream-bindings-check-05.json` rechecked all 220 candidate-04c bound
files with zero mismatches. Candidate 04c therefore has no observed source-binding
mismatch from this initializer correction; later actual preflight remains required.

## Closeout orchestration prepared and reviewed, not executed

Independent preparatory rereview passed `closeout-helper-review-packet-02.json`
after three blockers were corrected: package exports are bound to exact planned
container/image/volume and prior-export identities before any probe mount;
host/container traversal fails closed for unreadable/missing/unsafe roots or
subtrees; and resource comparison includes Running/StartedAt/RestartCount plus
fresh exact native namespace-empty proof before graceful stop/removal. Failed
package one must remain stopped. Forty-two pure/static checks passed with no
external backup, restore, protected-file scan, volume export or cleanup calls.

The separate backup and cleanup authorization templates remain false. No closeout
operation has run. Actual successful numerical-cache outage/restoration would
require a new explicit hash-bound exact same-ID lifecycle acceptance before later
strict consumers; the currently accepted package restart is not permission for a
future Redis start. All mandatory gates, final source/data/preservation evidence,
verified dumps/restores/exports and root/independent closeout approval remain
required. Phase 4 is incomplete; original services and protected artifacts remain
outside every operational target. No commit or push occurred.

## Completed retained-root initialization and natural expiry

The later final receipts establish that `p4-numerical-actual-init-03` and
`p4-numerical-legacy-init-01` both **passed**. Each used the independently approved
separate candidate-05 initializer, retained a fresh checksummed dump and isolated
metadata restore, and proved the seven CHECK differences by exact restore-only
server reparse before production inventory initialization. Historical table and
charge rows, constraints/indexes, filesystem stat inventory and runtime identities
remained exact under the helper's assertions. The earlier failed actual-init-01
and actual-init-02 invocations and their dump/restore evidence remain intact.

The actual root initialized epoch one with 297 files, 1,165,908,679 retained bytes
and 12,885,295,104 reserved data bytes; its dump SHA256 is
`1296397d4580e9f043ed4921f96d8eeec533357fa7a06c6e14e450c65dcb9892`
and isolated restore is `v2p4_actual_preinit04_restore_02`. The legacy root
initialized epoch one with 356 files, 2,906,688,882 retained bytes and zero reserved
data bytes; its dump SHA256 is
`fa3678ed2cfa7fc012103a9757c67c67732ade23b671ff447258600691446db8`
and isolated restore is `v2p4_legacy_preinit04_restore`. All three pre-initialization
restore databases, including the failed init-02 `v2p4_actual_preinit04_restore`,
must remain in the next exact closeout inventory. Initialization neither deletes
historical bytes nor releases their charges, and is not a numerical-result gate.

`p4-upload-expiry-01/receipt.json` passed the unchanged natural fifteen-minute
database-token expiry, observing the original expiry at
`2026-10-30T16:25:28.870779Z` with 897 timing observations over 901.6691605s.
This was not a shortened-expiry fixture or forced database transition. The API
memory receipt records 3,551 nonempty samples, maximum gap 0.2704900s and complete
coverage of four native processes/four validated events; observed summed RSS
peaked at 146,132,992 bytes within that declared process scope.

The expiry interval explicitly overlapped separate actual/legacy root
initializations under `expiry-initialization-overlap-01.json` and supplement 03.
Supplement 02 also records the bounded native helper probe at approximately
16:14:46–16:14:57 UTC: 787 inventory calls and eleven self-counter points, no
API/DB/data/GPU/system mutation. That whole probe failed an immediate fixture
Job-zero assertion and then drained without forced cleanup; the failed probe
remains failed. Its time bounds are filesystem/native-event bounds, not invented
active-clock measurements. Expiry retained all native coverage/timing assertions,
but supplies no exclusive-host or shared PostgreSQL/Redis memory/performance
claim. Initialization supplies no performance comparison.

## Generalized numerical actual-source gate passed; legacy still running

`p4-numerical-preflight-01/invocation.json` passed in 1.9545474s, validating the
nine retained scenarios, seven retained independent-oracle source receipts and
expected result identities. Its receipt explicitly says this preflight is not
runtime acceptance.

`p4-numerical-actual-01/invocation.json` then **passed** in 1,236.8165544s with
20 independent actual bar checks, all nine generalized numerical scenarios and
nine fresh-key repeats. All eighteen runs completed on attempt one; the paired
result hashes matched the independent Decimal oracles and the repeated specs.
The receipt records `independent_oracle: true`; its 220 source-before/source-after
entries match exactly. Retained per-run status/results/summary and source/oracle
receipts remain separate from browser observations and from fixture tests.

Both numerical receipts honestly record memory **unmeasured**. They establish
correctness/replay outcomes, not resource peaks or an isolated throughput
comparison. The prospective actual/legacy-initialization overlap declaration
retains those limits; the final legacy initialization receipt in fact ended before
the actual numerical preflight began. No resource guard or numerical assertion
was relaxed. At this checkpoint `p4-numerical-legacy-01/invocation.json` remains
`running`, with no final receipt; the five retained legacy scenarios and cold
all-62 gate are not credited from that progress.

Closeout still requires the pending actual gates and full drain, a fresh exact
owned database/resource inventory, final preservation, verified dumps/restores
and package-volume exports, followed by independent review and separate root
cleanup authorization. The prepared cache/recovery packet has no actual cache
outcome yet. If its authorized Redis stop/start succeeds, retain/index every raw
receipt and create a new explicit lifecycle receipt binding the immutable accepted
package-before start to the observed same-ID/configuration new start, PING,
outage numerical parity, restored MISS/HIT and overall success/native drain.
That new lifecycle must be independently accepted by strict downstream consumers;
the old package receipt and helper bindings must not be silently rewritten or
their StartedAt guards removed. Failed cache runs still require retained failure
evidence and verified restoration. No closeout operation ran during this
documentation checkpoint. Phase 4 remains incomplete; no commit or push occurred.

## Retained legacy and cold all-62 gates completed

`p4-numerical-legacy-01/invocation.json` subsequently **passed** all five retained
legacy scenarios and their five v2 projections in 619.5852646s total
(618.9768945s including the internal drain). The retained result identities match
the original scenarios. `post-close-drain.json` records zero live owned children,
zero active compute and a closed verifier with zero submitted work remaining.
All 220 source-before/source-after entries match exactly. Memory remains explicitly
unmeasured; this is correctness/compatibility evidence, not a measured resource
or isolated throughput result.

`p4-numerical-cold-01/invocation.json` **passed** the unchanged fresh cold all-62
gate from `2026-10-30T17:03:40.844907Z` through
`2026-10-30T17:09:08.498953Z`: 327.6540615s total and 327.0360798s including the
internal drain. It covered 230,311,900 retained trades, exact legacy results,
one numerical attempt and a memo left queued with zero model calls. The final
drain records no live owned children, no active compute and a closed idle verifier;
all 220 source entries remain exact. Memory is unmeasured. This local Phase 4
rerun remains distinct from historical Phase 3/hosted passes and does not erase
any earlier failed invocation.

Root has now started `p4-num-recovery-01-source04`; its `start.json` records
`status: running` at 17:09:53.668780Z. No final recovery invocation outcome exists
at this checkpoint, so no recovery/cache result or Redis lifecycle transition is
inferred from the running process.

## Measured browser helper stress 02: passing component, failed whole probe

`browser-actual-sampler-probe-measured-02/compact-classification-01.json` records
the whole probe **failed** because controller command inspection of PID 15176
raised an unclassified RuntimeError. A process-exit/inspection race is inferred,
not an observed cause; a memory sample containing that PID is not proof that the
failed command inspection succeeded. The failure remains retained.

Its separate memory component passed: 207 complete samples, no native-error
samples, maximum gap 0.2667621s, maximum span 0.0639702s and total inclusive
memory 1,273,020,416 bytes, including the observer. The fixed 8 GiB fixture bound
passed. All three mocked-engine DOM/selector renders passed; all private Jobs
ended at zero and the UI port released. These component passes do not convert
the failed whole probe into an acceptance pass.

The explicit overlap declaration records the legacy correctness run on the host
during this helper fixture, with GPU telemetry disabled and no actual API/DB/data/
hash-I/O verifier used by the probe. Its approximately 17:02:23–17:03:19 UTC
interval partially overlaps the legacy gate, which ended at 17:02:45 UTC. No
exclusive-host performance, actual full-day browser resource peak or mandatory
three-engine actual campaign credit is claimed. Recovery/cache, remaining actual
browser/fault/resource gates and final preservation/backup/restore/closeout remain
pending. Phase 4 is incomplete; no commit or push occurred.

## Numerical recovery passed; cache configuration prerequisite failed

`p4-num-recovery-01-source04/invocation.json` **passed** in 980.3380576s from
17:09:53.668780 through 17:26:14.006822 UTC. The six native boundaries were
claimed, snapshot, numerical, staged, renamed and committed. The first five
recovered on attempt two; committed recovered without an extra attempt. The
separate three-crash budget case exhausted its budget without a fourth claim.
The receipt records all native descendants drained and exact runtime-before/
runtime-after identities; the campaign retained its protected/original-service
preservation evidence. The independently approved helper manifest remains
distinct from the actual completed outcome, and historical recovery/fault failures
remain retained.

`p4-num-cache-01-source04` then **failed** its initial configuration assertion in
6.716989s, before the cache matrix, Redis restart or configuration mutation.
`configuration-diagnostic-01.json` observed the exact owned Redis ID
`b5354a3023a61fcf87eea9e44c66d1e019f43a620de9b782f9717d1adb8de4f0`,
unchanged package-restart StartedAt, successful PING, maxmemory 134,217,728 bytes
(128 MiB), default save schedule `3600 1 300 100 60 10000`, appendonly `no` and
allkeys-lru. The frozen harness expected maxmemory 268,435,456 bytes (256 MiB)
and an empty save schedule. This is an observed prerequisite mismatch, not a
cache-behavior pass or an application defect established by the unrun matrix.

A scoped helper correction is undergoing independent review to capture the exact
baseline, temporarily set only maxmemory/save for the authorized fixture, reapply
those two fields after the planned restart, and restore the exact baseline in
finalization. No future correction approval, execution, cache pass or accepted
new Redis lifecycle is claimed from that plan. The failed initial invocation and
its read-only diagnosis remain intact; its original Redis configuration/start
were not changed.

## Supported cancellation of the retained failed finalize case

After independent approval of `fault-leftover-cancel-approved.json` and separate
root clearance, `p4-upload-leftover-cancel-01/receipt.json` **passed** the supported
API cancellation of exactly import `8a536944-6f02-402f-ac13-7f688b67afe9` and
generation `f16c1c7e-b70d-48c8-bc84-b1401806f48f`. The import changed from uploaded
revision two to cancelled revision three and the generation became cancelled.
The 16,422,824-byte actual Parquet source, charges, reservations and tickets stayed
unchanged, with root staged-slot count zero before and after. No finalize/job,
source deletion, refund, reconciliation or readiness reset was substituted for
the cancellation. The owned API drain receipt records exit zero and no failure.

The cancellation does not convert `p4-upload-crash-before-finalize-01` into a
pass; that invocation remains failed with all original bytes/charges/evidence.
Remaining actual browser/upload/resource/cache gates and final preservation,
backup/restore/export/review/ownership-checked cleanup still keep Phase 4
incomplete. No runtime/helper/DB/process operation was performed by this
documentation checkpoint, and no commit or push occurred.

## Remaining native upload commit boundaries and root lifecycle passed

`p4-upload-crash-before-finalize-02` **passed** from 17:33:26.818034 to
17:33:39.958674 UTC, and `p4-upload-crash-after-finalize-01` **passed** from
17:34:34.280735 to 17:34:46.871191 UTC. Both receipts bind reviewed fault freeze
06, SHA256 `ea6890f8c329a93f30c7ae95e10277014574991ac194ad1b7c752d16272be69a`,
and retain actual Parquet HTTP/native-crash/recovery evidence and complete owned
API drain. Together with the earlier three passes, these establish the five
specified native upload crash boundaries. The original before-finalize-01
post-drain bind failure remains failed; the later successful invocation does not
replace its source/import/charge/diagnostic history.

`p4-upload-root-lifecycle-01` **passed** from 17:36:41.033485 to 17:36:42.900307
UTC on the same freeze. It observed fail-closed mismatch, unmanaged-write and
signature checks followed by supported reconciliation on the owned root, through
production readiness/admission. No original resource or manual database-state
edit was used. The identity-reuse case is an explicit fixture, not proof that
Windows actually reused an OS process identity during the run.

## Cache and observer follow-up still blocked before acceptance

Independent review blocked cache configuration candidate 02 **before execution**:
its in-matrix native-child guard would reject the legitimate idle verifier pool.
The narrow guard correction remains pending. No Redis configuration mutation,
restart, matrix pass or new accepted lifecycle follows from this candidate.
The original configuration-failure receipt and all old helper versions remain
retained.

`browser-observer-control-probe-01` **failed** after 24 completed observer cases
when concurrent fixture stop-file replacement raised PermissionError. Twenty-three
fixture Job-zero counts were observed; the last fixture's explicit Job-zero was
not observed. A later exact native follow-up found its holder/leaf identities
absent. Closing the held kill-on-close Job and later process absence are not
substitutes for that missing original Job-zero observation.

The reviewed probe-only stop-request correction used immutable exclusive-create
nonce files with exact-payload idempotence and independent final drain attempts.
The separate `browser-observer-control-probe-02` nevertheless **failed** after
30 cases: a deliberately injected `job.members` function was not restored before
fixture cleanup. Native active-zero was observed, but the members list was still
the injected fixture output, so the whole probe failed. Both failures and their
receipts remain intact. Observer/control runtime behavior was not changed by
these probe fixes; the next probe-only correction is undergoing review, with no
future retry or acceptance pass claimed here.

Mandatory measured actual-browser/resource/cache and final preservation/backup/
restore/export/closeout gates remain outstanding. Phase 4 is incomplete. This
checkpoint changed only verification prose; no commit or push occurred.

## Further cache attempts: failures retained, baseline restored

Cache configuration candidates 02 and 03 remain blocked historical preparations.
Independent review subsequently passed candidate 04. The actual
`p4-num-cache-02-source04` invocation then **failed before CONFIG SET** because
the default UID-zero `readlink /proc/1/exe` query was denied. Its read-only
diagnostic observed the exact Redis PID one running as UID 999/GID 1000; a
separate target-account query succeeded. There were zero configuration intents,
no restart and no baseline change in this failed invocation. Candidate 05's
narrow target-account/native identity correction subsequently passed independent
review; it did not relabel the earlier failure or weaken exact identity checks.

The actual `p4-num-cache-03-source04` invocation **failed** after 157.4045064s.
It applied/verified the reviewed temporary two-field configuration and completed
initial MISS/HIT, corruption, isolation and native eviction-pressure checks
(512 one-MiB payloads), then stopped at the pool-bootstrap guard before STOP.
Those completed subchecks do not make the whole cache matrix pass.

Its separate `configuration-final-baseline-restored.json` **passed**: native
clients drained before restoration; maxmemory returned to 134,217,728 bytes,
the original `3600 1 300 100 60 10000` save schedule returned, appendonly remained
`no` and policy remained allkeys-lru. The exact Redis container ID and StartedAt
`2026-10-30T07:56:19.564350294Z` match before/after. No actual Redis restart occurred
in this attempt. Temporary cache configuration can cause eviction; baseline
restoration is configuration/identity recovery, not a claim that evicted cache
entries were restored. The whole failed matrix and all mutation/restoration
receipts remain retained. A further narrow pool-bootstrap guard correction is
pending review; no future matrix success or new lifecycle is claimed.

## Observer fixture passes and subsequent stress failure

`browser-observer-control-probe-03/compact-verification-01.json` **passed** all
35 owned native fixture cases. Every held Job recorded active zero and native
empty membership, all injections were restored before cleanup, and all 1,380
metadata/snapshot handle opens had matching closes. Forty concurrent captures,
600 cached captures and 64 concurrent nonce stop requests were exercised without
forced cleanup; ctypes class count remained 22 before/after. This bounded native
fixture had no API/DB/application/browser/GPU workload and leaves probe 01/02
failed with their original evidence.

The pure cleanup regression 01 **failed** after 17 cases because its extracted
fixture globals lacked `json`. The corrected regression 02 **passed** 20 cases
with exact AST extraction of the cleanup being tested. These are pure helper
checks, not actual browser/resource acceptance.

`browser-actual-sampler-probe-observer-01` nevertheless **failed** overall in
57.432665s. All three mocked-engine renders passed, all four private Jobs ended
at zero and the UI port released. Controller inspection retained two errors:
PID 53568 was not a private member at inspection, and PID 16956 was not live at
present validation. Memory coverage was incomplete across 208 samples, including
two process-counter errors in one sample. Its bounded gap/span and memory total
cannot supply actual resource credit after those coverage failures.

The compact failure analysis records no controller capture, birth/executable
identity or memory row for PID 53568. It therefore does not classify that PID as
an owned process or establish a terminal-process race as its observed cause.
Other retained process-death context does not repair this missing identity. A
future coverage proposal is undergoing review only; no stress retry or actual
three-engine resource pass is inferred. Phase 4 remains incomplete. This
checkpoint performed no operational change, large sample scan, commit or push.

## Actual cache matrix passed; exact new lifecycle adoption remains pending

Independent review passed configuration helper 06 with precise admission for
dormant, live-idle and known-closed verifier states. The distinct
`p4-num-cache-04-source04/invocation.json` **passed** all ten steps in
207.1056187s, from 18:24:37.096787 to 18:28:04.202392 UTC: configuration, MISS/HIT,
corruption/binding checks, instrument/version isolation, native eviction pressure,
owned Redis stop, outage independence, restoration, recovery and owned-key
cleanup. The pressure fixture submitted 512 one-MiB values (512 MiB cumulative).
Its 64 RSS samples peaked at 228,458,496 bytes, below the unchanged 512 MiB guard;
this declared process measurement is not a whole-host/application resource peak.

All native clients/descendants drained, all 152 runtime identities remained exact,
and the campaign's protected/original-service preservation checks passed. Its
separate final-baseline-restored receipt passed: maxmemory 134,217,728 bytes,
original save schedule `3600 1 300 100 60 10000`, appendonly `no` and allkeys-lru
were restored. The exact Redis ID remained
`b5354a3023a61fcf87eea9e44c66d1e019f43a620de9b782f9717d1adb8de4f0`,
with newly observed StartedAt `2026-10-30T18:27:39.346662611Z` after the planned
restart. Earlier cache-01/02/03 failures and baseline-restoration evidence remain
failed/retained, separate from this new pass.

The completed receipt explicitly requires the active lifecycle ledger to be
refreshed. Raw evidence indexing and independent acceptance/adoption of this new
exact lifecycle by downstream strict guards remain pending. This pass does not
silently replace the old package-start acceptance or remove StartedAt checks.

## First upload resource campaign failed its API sampling gate

`p4-upload-resources-01/receipt.json` records the whole invocation **failed**.
`memory-gap-diagnostic-01.json` retained 428 API samples and three gaps exceeding
one second: 1.2603517s, 1.2761987s and 1.0200060s. Their cause is unestablished.
There were no native sampling errors and event-process coverage was complete;
the slot and physical sub-samplers passed. Those component results do not repair
the API gap failures or produce an overall resource pass.

All thirteen owned Jobs recorded active zero, including the intentionally killed
slot-zero process (exit 91); other process exits were zero. The functional body
reached its end, but API close failed its measurement gate, so no functional
result was returned into the invocation receipt. No overall success or cleanup
completion is inferred. Published source bytes remain retained, and unclaimed
queued jobs require a separately guarded exact supported cancellation later.
No cancellation, reset or deletion was performed by this documentation update.
Measured actual-browser/resource and final lifecycle/preservation/backup/restore/
closeout work still leave Phase 4 incomplete. No commit or push occurred.

## Snapshot observer preparation and mocked stress passed

After independent review, `browser-snapshot-native-probe-01` **passed** 49 owned
native fixture cases. Every held Job recorded exact active-zero/empty native
membership; all fault facades were restored before cleanup, with no forced stop
or stop error. All 1,464 metadata/snapshot handle opens had matching closes.
The receipt includes forty concurrent and 600 cached captures, unchanged ctypes
class count (22) and zero measured private-memory growth in that bounded fixture.
Two exit-transition positives retained RSS captured while the same native handle
was live before/after the counter read, then required exact terminal/birth and
complete confirmation-snapshot proof. Missing required identity/membership
remained a rejection. This is helper fixture evidence, not actual browser memory
acceptance; all earlier probe/stress failures remain failed and retained.

The snapshot integration's twenty pure cleanup cases also passed with the actual
finally globals audited. Its reviewed freeze verification matched the full
25-entry dependency map. `browser-actual-sampler-probe-snapshot-01` then **passed**
mocked Chromium/Firefox/WebKit rendering and CPU-fixture stress from
18:44:44.826982 through 18:45:48.705054 UTC. It retained 229 complete required
native samples, maximum gap 0.2667989s, maximum span 0.0320832s and inclusive
observed memory 1,337,868,288 bytes (observer maximum 57,753,600 bytes), below the
fixed 8 GiB bound. All four Jobs ended active-zero/empty/closed and the UI port
released, with no forced stop, unresolved launch, stop error or inspection error.

One optional PID-only auxiliary diagnostic remained explicitly incomplete. It
supplies no identity, RSS, terminal, lifetime or memory credit. Required worker
captures and all required sampler reads remain mandatory and complete; this
qualification does not reinterpret the earlier unclassified PID 53568 failure.
GPU telemetry was disabled. The declared possible overlap was a separate
read-only lifecycle audit; no exclusive-host/performance claim follows. Mocked
API/fixture success remains separate from actual-data acceptance, shared
PostgreSQL/Redis memory and true peak proof.

## Browser 05 functional-only reservation audit passed

Root reports independent approval of the reservation-path audit before its
read-only execution. `browser05-functional-only-verification-03-reservation-path.json`
records `functional_evidence_verified_RESOURCE_FAILED` for the six completed
Chromium cases: six-day official delivery, full CSV/Parquet delivery and three
profiles. The audit derives each exact attempt directory from its retained
job/fence/scratch reservation and binds attempt/submission/worker identities,
source transport/checksum/catalog/manifest evidence, server-upload identities
and exact numerical oracles. It preserves the earlier failed audit/helper/plan
and their mismatched prospective path/count assumptions.

This approval covers only completed functional evidence. The audit explicitly
retains whole-browser-05 `failed`, resource `failed`, `resource_credit: false`
and `fresh_evidence_required: true`. It does not complete the missing comparison/
cluster/other-engine work or supply resource credit for the old BTC campaign.

## Cache lifecycle extension approved; fresh measured browser running

`closeout-cache-lifecycle-approved-07.json` records independent read-only review
passed with no blocking findings for the actual cache-04 lifecycle extension.
It binds the exact cache lifecycle candidate and six helper identities, including
the unchanged original closeout, snapshot and root-preparation helpers and runtime
source 04. This is extension review approval only. It does not execute backup or
cleanup, certify all mandatory gates, or replace the required overall closeout
review and separate root authorization. The original operational guards and
retained old lifecycle evidence remain intact.

`browser-actual-measured-01-root-preflight.json` records runtime 04, reviewed
snapshot harness freeze, ready owned browser root, no running work in configured
owned databases, exact owned service checks and bindable Phase 4 ports. The
distinct `browser-actual-measured-01/invocation.json` is **running**, started at
18:49:07.624287 UTC; its real UI/API/worker campaign uses no mocked routes.
Root owns the controller/API sessions and holds exclusive actual-work sequencing.
The current browser result also says running, with no final outcome. No final
three-engine actual-browser, aggregate resource or closeout pass is claimed from
that progress. This checkpoint changed only verification prose and performed no
live service/native/dataset operation or large sample scan. Phase 4 remains
incomplete; no commit or push occurred.

## Measured actual browser: Chromium completed, campaign still running

The current `browser-actual-measured-01/browser.json` records Chromium **passed**
its two actual CSV/Parquet imports and five research runs in 2,259.919s. Firefox
is still running. This is a completed engine checkpoint, not a final whole
three-engine campaign outcome or aggregate resource pass; final measurement and
all-process drain have not been inferred from intermediate case files.

Root retained two exact-birth/executable API CPU observations at
19:10:11.5582916 and 19:11:12.2316330 UTC. Their counters rose from 767.171875 to
819.109375 CPU seconds: 51.9375 CPU seconds across approximately 60.6733 elapsed
seconds. This showed process activity during a quiet reporting interval, but CPU
activity alone did not prove research dispatch or numerical execution. Later
worker-seven progress and the separately completed Chromium case evidence
resolved the progress uncertainty. The CPU samples are not memory acceptance,
continuous liveness or throughput evidence.

Root also reports two full-page screenshots reviewed with resizing as sampled
visual QA only. They do not establish continuous observation, uninterrupted
rendering or completion of unobserved browser actions. Runtime source 04 and
the active reviewed browser harness remain unchanged.

## Further static preparation approvals do not replace actual gates

Resource-isolation candidate 02 was independently blocked because phase-local
holder tracking could be cleared before proved native drain, allowing outer
pending cancellation despite a potentially live preclaim child. Candidate 03
corrected the drain ordering and passed static review, with 27 fake/pure cases.
`resource-isolation-approved-03.json`, SHA256
`81367b1190e27fe421de3de762f14a872fe89984cb691bd328e7ca46d6f6d15f`,
explicitly grants static review only: native fixtures require a separately
reviewed exact entry and root clearance, actual resource acceptance is false,
and no mutation of old resource-01 is authorized. Native/actual resource results
remain pending.

A separate, unused optional browser diagnostic candidate 02 passed eighteen
pure fake-page/timer/write cases and static syntax checks. Candidate 01's
2,500-entry general-event cap could omit the desired dispatch event; that finding
and the earlier cp1252 pure-test failure remain retained. The new prospective
dedicated bounded dispatch records/overflow checks were not integrated into the
running harness and supply no retrospective actual dispatch/root-cause evidence.
The later pure extraction syntax failure and corrected pure-test source also
remain separate retained history.

Independent review passed the static `closeout-evidence-index-draft-05.json`,
which adds direct migration/restore/initialization bindings and exact 26-file
frontend/source-04 correspondence to the retained draft 04. It remains an
evidence index with all acceptance/authorization/quiescence flags false and four
pending gates, not an overall acceptance or cleanup authorization. The browser
campaign remains exclusive and in progress. Phase 4 is incomplete; this checkpoint
changed only verification prose and performed no live operational change,
commit or push.

## Registry-backed mock 01 failed memory completeness despite functional pass

`browser-actual-sampler-probe-census-registry-01/receipt.json` records the actual
mock run **failed**, with root command exit one, SHA256
`4be6453bc63204227ca7321e8fcf423a049d5179d673b51dcdcfcbb96f7ef29f`.
All three rendered engines' functional cases passed, both fixture workers had
complete required coverage, and the four-event immutable registry/final-rehash
gate passed. Those component passes do not override ten incomplete memory
samples out of 212 or provide resource acceptance.

Root's bounded classification identifies pre-counter scope changes at indexes
1 and 84, post-counter unproved ancestry for PID 53808 at indexes 72 through 77,
and following cadence/null flags at indexes 2 and 85. Maximum transaction gap
was approximately 0.267254s, non-null capture gap 0.274712s and span 0.05767s;
the observed aggregate 1,312,768,000 bytes remains uncredited because completeness
failed. No failed sample was removed/regraded and no threshold was relaxed. A
source-based diagnosis/prospective core proposal remains pending, with no retry
or actual-browser run authorized by this result. The ancillary root summary
command's TypeError when computing a maximum over a None gap, and its truncated
print, are diagnostic failures only and do not change measurement evidence.

Fresh preflight preservation matched 287 protected files and all five original
services. Both original UI/controller Jobs recorded active-zero/empty membership,
cleanup errors were empty, the UI port released and the full dependency map
remained exact. Independent review in `browser-launch-mock01-drain-approved.json`
passed **current-workload drain only**, binding the later post-exit receipt
SHA256 `0adacc5b3dd1fa7ebbb031971deabd5e980554b4176fe24af5b4faf511f01349`:
three full original identities dead and the checker command terminal/exit zero.
One auxiliary candidate retains Job-group-only evidence with no individual
identity/measurement credit. Closed-handle flags remain bookkeeping. Whole mock,
resource and whole-host credit remain false; all prior failures stay retained.
Phase 4 is incomplete; this documentation checkpoint performed no live operation,
commit or push.

## Resource fixture execution, exact resolver and cancellation checkpoints

The actual native-control fixture `p4-resource-native-03` **failed**: eight
Seed.close calls lacked the required `cancel_active` argument, and two native
handle failures remained unexplained. The final failed receipt and cleanup
assertion remain retained. Root's later direct native follow-up found 27 exact
identities dead; that later drain evidence does not turn the failed invocation
into a pass or classify the missing native-handle observations.

The corrected separate `p4-resource-native-04` **passed**, with independent
outcome review `resource-native-outcome-approved-04.json`, SHA256
`56c53193b68f6e3c304ffa09cb9170655465b8738700ff4e48afc431b3c01c0a`.
The tiny shared-service fixture `p4-upload-resource-shared-service-02` also
**passed**, with outcome review
`resource-shared-service-outcome-approved-02.json`, SHA256
`d5cefee4cc1abf69d8a3a32ab8e8343e490a446f34792210ba282cb59248f787`.
An earlier shared-service launch stopped before invocation/API/job creation
because root clearance omitted `configuration_sha256` and raised KeyError; that
failed clearance and preflight receipt remain preserved. Native-control and tiny
shared-service fixture passes remain prerequisites, not the full actual-resource
campaign or an actual-data resource-peak substitute.

Exact-eight read-only resolver 01 failed its SQL join/schema assumption; resolver
02 then failed its metadata-hash assertion. Resolver 03 **passed** under separate
independent review, with actual receipt
`resource01-pending-readonly-03/receipt.json`, SHA256
`2735312ef11737974c1f375b8940522970c3b786ea135f297ca63ef147b65da8`.
Its correction uses production `metadata_hash` semantics together with full
metadata equality, rather than assuming the file's byte hash is its semantic
metadata identity. The two failed queries/diagnostics and all old plans remain
retained. Resolution itself was read-only and supplied the exact eight-item
baseline for separately authorized cancellation.

`resource01-cancel-apply-01/receipt.json` **passed**, SHA256
`5dc458ffba527916f76143b5d14d756dc0abbd75740b0a060b6103b5cf338493`,
with independent outcome review SHA256
`ff42ff77acbfbc1b407148a1b2312b425870734946a056f4b6ff23bd7b6ef933`.
Six exact revision-zero requests were cancelled at revision one with zero
attempts/fences. Two historical cancellations/provenance records and all four
ledger fingerprints remained unchanged. Thirteen exact root-absence proofs,
287 protected-file matches and all five original-service matches passed; the
owned API exited zero with its private Job empty, no forced stop or cleanup
error and exact source 04. This supported cancellation supplies no resource or
final-closeout credit and does not reset the failed resource-01 campaign.

## Full resource 02 running; audit and census preparations remain limited

Fresh `resource02-preflight-02/receipt.json`, SHA256
`df1dce367c1c8ba276888cfc5115876682d0349ef9440e16c1485188f6dfef6b`,
measured 100,604,911,616 bytes free on the D: root and conservative seed headroom
23,278,684,248 bytes against unchanged charges/reservations. Other filesystems
were not measured. The old preflight-01 `C_free` label incorrectly repeated the
D: observation; C: was unmeasured, and the new receipt omits that misleading
field. The separate `resource02-preflight-preservation-01` snapshot passed
protected/original-service checks as point observations, not continuous uptime.
The full `p4-upload-resources-02/receipt.json` now says **running** under root's
separate clearance. No resource-02 outcome is credited while it runs.

Final-host audit candidate 03 was blocked on outside-producer lineage: observing
a same-PID valid/dead identity did not prove the original wrapper's creation-bound
birth/domain/image. Candidate 04 passed independent static review and 96 pure
checks while preserving that limit. Every applicable physical profile must
retain `outside_original_producer_lineage_unproved`; an input cannot override it.
No actual audit, root audit clearance, sealed ledger, composite claim or universal
`all_owned_host_processes_listed` assertion exists from this preparation, and no
old validator or failed browser/resource result was upgraded.

A new browser census helper remains draft/pure preparation only. The prior
whole-browser and resource failures remain failed, with no retrospective regrade.
Phase 4 remains incomplete. This checkpoint changed verification prose only,
with no live operations, broad hash/sample scan, commit or push.

## Full resource 02 passed with explicit fixture and measurement scope

`p4-upload-resources-02/receipt.json` **passed** from
21:25:22.052266 to 21:28:21.481277 UTC, SHA256
`6c1ebae4978b5c175fd2fa88598b354fb98941c6c48a91ec096f4c088e41f685`.
Independent outcome review `resource02-outcome-approved-01.json`, SHA256
`671c8381955c4a41358b472132ac97cb0b670f40f37757a113300da8027861b0`,
passed the `resource_races` gate without browser-resource, exact-4-GiB or final
closeout credit. The failed resource-01 campaign and all its retained evidence
remain failed and separate.

The campaign exercised four staged uploads with the fifth rejected at 429,
eight pending-slot reservations and dead-owner replacement, the unchanged
100 GiB logical reservation ceiling, and unchanged physical precompute rejection.
The logical ceiling case reserves capacity; it does not upload 100 GiB. The
eight-slot case is a pending/admission fixture, not eight completed actual
numerical computations. A real retained 16,422,824-byte Parquet source was seeded
through the same owned shared service; the physical-guard research request
remained at attempt zero. No filesystem or limit was mocked/relaxed, and the
parent did not perform the seed computation outside its exact owned child.

Three sampling streams retained 765 samples with maximum gap approximately
0.269619s. Their conservative sum of stream maxima was 1,524,391,936 bytes, below
the fixed 8 GiB bound. This is scoped sampled memory including the declared
processes, not a simultaneous measured sum or true peak/whole-host claim.
All thirteen private Jobs drained, including one planned forced dead-owner
termination. Reviewed source/helper identities remained exact.

Cleanup addressed only the eight new exact targets, disjoint from the old eight:
seven queued requests were cancelled and one already-cancelled request's existing
attempt was preserved. Retained ledger fingerprints remained exact. This
supported scoped cleanup neither deletes retained source bytes nor repairs or
reclassifies the original failed campaign. It is not final host/resource cleanup.

## Browser census and parent-absence proposals still preparatory

The new browser census core has 126 pure/static cases and native/mocked probe
plans, but independent implementation review remains pending. The separate
original-parent PID-absence candidate has 49 pure checks and is likewise pending
independent review, with no actual native query or integration performed.
Neither preparation supplies new browser/resource coverage, original creation
lineage, historical universal process accounting or final drain credit.

The prior whole-browser/resource failure remains failed; a new accepted measured
browser gate, exact 4 GiB transport gate and final drain/preservation/backup/
restore/export/review/cleanup remain outstanding. Phase 4 is incomplete. This
checkpoint changed only verification prose and ran no live operations or broad
sample/hash scans. No commit or push occurred.

## Census native fixture failures retained; native 06 narrowly qualified

`browser-census-native-probe-02` failed its bootstrap import of MarketLab before
leaf launch. The original Job-zero and later exact controller-death observations
remain retained; they do not establish unobserved handle closure. Probe 03 passed
baseline, then failed the genuine-87 single case's exact-classified-set assertion.
The failed raw measurement was not persisted, leaving its cause unproven; later
evidence recorded both drains and seven full identities dead.

Probe 04 passed its first four cases, including genuine-87 single/batch, then
failed the required-root-exit case. Premature fixture stop allowed descendant
53176's counter read to raise OSError; the raw evidence, including parent 27340,
was retained. All five drains and sixteen full native identities were later
proved dead. Probe 05 passed baseline/single, then failed genuine-87 batch with
a PermissionError serialized as a generic scope-census failure. Its read-only
diagnosis locates the failure before the second leaf's assertion persistence,
but cannot establish the failing file operation, errno/winerror or OS cause.
All three probe-05 drains passed without force/errors. No antivirus, sharing,
permission-retry or application-core cause/repair is inferred from those limits.

The separate probe 06 added reviewed fixture control-I/O evidence and **passed**
sixteen native cases. Independent outcome qualification
`browser-census-native06-outcome-approved-01.json`, SHA256
`5355186006e51ab59cc2a24012980df4f5cd8759f09c4864e0bfb732790fcec4`,
binds its producing helper, raw assertion/measurement/drain evidence and unchanged
source 04. This is native-helper qualification only, with no actual-browser
resource credit. Every earlier native/pure preparation failure remains retained.

## Subsequent census mock failed before engine rendering; drain qualified

The first root port preflight failed before freeze/campaign creation: connect
code 10035 on the proposed UI/API ports was unknown and did not prove absence.
The separate mock-03 entry reached a real failed run in
`browser-actual-sampler-probe-census-01`. Its browser receipt records an EPERM
rename of the fixture `worker-launches.json` temporary file, with zero rendered
engines; the wrapper receipt records `state: failed`, `error_type: ExceptionGroup`
and approximately 107.827s from 22:48:13.680843 to 22:50:01.507968 UTC. The
controller's source deadline is 100 seconds; wrapper cleanup can take longer.
No 240-second deadline or unobserved OS cause is claimed. Fixture cancellation
and sampler/cleanup outcomes do not make the whole mock a pass.

`mock-census01-drain-approved-01.json` passed independent review for **current
failed-workload physical drain only**: two full identities dead, the original
same UI/controller Jobs active-zero/empty/closed, and no cleanup errors. Sixteen
partial records remain qualified; the observer assertion remains unresolved,
individual inventory and whole-host/resource credit remain false. The later
`mock-census01-checker-completion-01.json` records the two synchronous read-only
checker tool calls exited zero; it supplies no native checker-self/descendant
identity or historical coverage claim. Whole mock failure is unchanged.

## Partial profile and original-session carrier applications

`profile-apply-01` and `profile-apply-02` completed read-only physical-group
applications **with unresolved scope**, not a composite final-host audit.
Independent profile-02 outcome review, SHA256
`1e3c616e71123d2c11741746817e05f153e9001bf52b901d0c88f6696b532847`,
covers fifteen original API0 Job-containment proofs and 130 verified evidence
files. Outside supervisors and selected mandatory native checks remain
unresolved. Tiny-02 API0, custom leftover-cancel API0 and pre-event protocol-01
API families remain unsupported by that profile. Individual inventory,
composite readiness and cleanup authority remain false; worker/API group
positives do not fill those gaps.

Original-session carrier 01 was blocked by CWD slash mismatch before reading
sources. Carrier 02 wrote a partial metadata index with explicit gaps. Carrier
03 was blocked on lexer handling and remains blocked. The separate carrier-04
parser/wrapper correction passed 147 pure checks (109 parser plus 38 wrapper),
then completed metadata extraction from exactly two old frozen prefixes.
Independent actual outcome review binds
`original_session_carrier04_actual_root04.json`, SHA256
`480ab34f6773b9b1080f741e694e5b8eef93efc4a01b26bdced3eeee5fa1d751`.
The index has 1,769 calls and 978 explicit gaps across 22 sessions: eleven have
terminal tool-result observations and eleven were still active at their old
cutoff. This is metadata extraction, with no command-completion, native-drain,
resource or complete-coverage credit. All failed sources and prior receipts stay
retained.

Runtime source 04 remains unchanged. No new actual-browser or exact 4 GiB pass,
final universal drain, backup/restore or cleanup is claimed. Phase 4 remains
incomplete; this checkpoint changed verification prose only and performed no
service/native query, broad scan, commit or push.

## Immutable launch registry qualified in a bounded native fixture

Launch-registry candidate 01 was blocked on cleanup behavior; candidate 02 was
then blocked because pending diagnostic evidence was not durably persisted.
Candidate 03 passed independent static review
(`browser-launch-registry-code-approved-03.json`, SHA256
`8877cf5186631cbcf8e3578af8410d5cd8fc558cb39de393ebda111c0118e439`)
with 61 Python and fourteen JavaScript checks. Earlier blocked candidates and
pure failures remain retained.

The separately reviewed native fixture included nineteen cleanup-fault checks.
`browser-launch-native-probe-01/receipt.json` **passed** in 2.719551s, SHA256
`4d30140968198c97ded70ecd73b0a3967250a90272d0547a5cc19d031a5e57ea`.
It observed four immutable publication events, held the first payload through
later publication without changing its hash, launched/drained two leaves, and
recorded original Job active-zero/empty membership with no cleanup errors. Its
179 dependency bindings remained exact. The later post-exit receipt, SHA256
`f8313ac2bb0e74085d5a0902566655a67d60b7a66bdfff86e1ce8d60ca9f936d`,
proved four full native identities dead; the checker command completed.

Independent outcome review
`browser-launch-native01-outcome-approved.json`, SHA256
`4a0cc88ab710b33ca3e22534c12816acb16da520b6f3319079735659e3b04388`,
passed this native launch-publication qualification only. Closed-handle flags
remain bookkeeping and do not independently prove CloseHandle success. There is
no browser, sampler, actual-data or resource acceptance credit from this fixture;
new mocked integration remains pending. Prior whole-browser and other failed
invocations remain failed. Source 04 and original services are unchanged.
Phase 4 is incomplete; this documentation checkpoint performed no live operation,
commit or push.

## Native/shared-service/resolver preparation approved; execution pending

`resource-native-approved-03.json`, SHA256
`816a922a6f1fb1b0e35063e2f1bd09cc21d4ba7d2165f7e95f5761f68f6670ce`,
records independent static review passed for native fixture 03, with 29 fake/
static checks passed. Candidate 02's blocker remains retained: a generic
AssertionError from Seed.start could incorrectly count as the expected rejection
without exact stage/payload proof. The corrected review is native-control fixture
preparation only, not an observed native outcome or resource acceptance pass.

`resource-shared-service-approved-01.json`, SHA256
`f8502a5a3f4fc27177fd2c26cdf13194da58babc03d34fa10540e98e61fa264c`,
records independent static review passed with 25 fake/static checks. It is a
prospective tiny shared-service fixture; execution still requires reviewed actual
native-03 results and separate root clearance. No actual shared-service/native
fixture outcome or new execution clearance is claimed here.

`resource01-pending-resolve-approved-01.json`, SHA256
`88df6b9e03dcc9cf0e71c64006742a56d77c9e80ec159311b7460ecef5d44b64`,
records independent review passed for exact-eight read-only identity resolution,
with 34 fake/pure checks. Its scope explicitly permits no mutation. Earlier
static/syntax/fixture failures remain retained; no actual database resolution
query, cancellation or old-resource-01 state change has occurred under this
preparation checkpoint.

The current actual browser receipt still records Chromium passed all five runs
and Firefox running after four completed runs, with its cluster case in progress
per root's checkpoint. No overall three-engine or resource pass is inferred.
All outstanding actual gates, final native drain and closeout requirements remain
pending. Phase 4 is incomplete. This documentation-only update performed no live
operations and no commit or push.

## Measured actual browser 01 completed functional cases but failed overall

`browser-actual-measured-01/invocation.json` ended **failed** after
5,775.0298391s, from 18:49:07.624287 to 20:25:22.654129 UTC. Its separate
`browser.json` records all three engines' functional cases passed: fifteen
research runs, six full CSV/Parquet imports and the actual official flows, with
24 targeted workers and no browser functional errors. These functional outcomes
do not override the failed controller/measurement gates or establish overall
browser/resource acceptance.

Controller inspection retained four failures: PIDs 20336, 47428 and 26412 were
absent from the raw-before snapshot before capture, and PID 38960 was not live
before capture. All required worker captures were present, but the four failed
inspections were not regraded as optional diagnostics. Seventeen separate
optional PID-only diagnostics remain explicitly incomplete. No forced stop or
unresolved launch occurred; controller/UI Jobs ended active zero and the UI port
released.

Root's bounded memory summary reports 22,536 samples, including one incomplete
sample (index 623 at 18:51:50.104538 UTC) with native-handle-unavailable errors for
PIDs 33880 and 52520. Maximum gap was 0.2706236001s and maximum span 0.0997591s;
the observed inclusive aggregate was 1,622,896,640 bytes, including an observer
maximum of 290,234,368 bytes. An empty top-level errors array does not make that
incomplete native sample complete. The six failed PIDs across controller and
memory observations have no captured actual identity/RSS and were not known
required roots/workers. Neither inference nor later process absence supplies the
missing evidence. Whole-run and resource status remain **failed**, with zero
resource credit. Independent review requires a prospective capture-transaction
repair and a new measured resource campaign; there is no retrospective regrade.

The root-owned API cooperatively stopped with exit zero.
`browser-actual-measured-01-post-exit-01.json`, SHA256
`763eeeee6d52e9e190e63e9d80fbceb560a50535e1c8aea7cc38bc0ada3caf95`,
records 25 full native identities dead and private Jobs active zero. Three
partial wrapper/native observations returning None are qualified separately;
`historical_all_owned_host_processes_listed` is false. This establishes the
declared current-workload drain, not historical complete-process coverage or a
resource pass.

Two exact worker-23 CPU observations at 20:19:37.9266506 and 20:20:47.3740032 UTC
rose from 1,040.5625 to 1,108.953125 CPU seconds: 68.390625 CPU seconds across
69.4473526 elapsed seconds. They establish activity only, not the cause of the
long case timing, dispatch/result correctness or memory acceptance. The timing
cause remains unknown.

## Closeout inventory/plan refresh helper statically reviewed only

`closeoutplanrefresh-helper-approved-04.json`, SHA256
`a38f8a9d4625a7bbd409b124adfc5413c02d3d6de348a5572c83103dc6783d99`,
records independent static review passed, with 47 pure/static checks in the
latest retained probe. It binds the existing plan, exact lifecycle supplement,
runtime and helper identities. No actual refreshed inventory, plan execution,
backup, cleanup or final acceptance follows from this preparatory approval.
Every earlier browser/resource failure remains retained. Phase 4 is incomplete;
this documentation checkpoint performed no live operations or large sample scan,
commit or push.

## Registry mock failed measurement; prospective correction remains unqualified

`browser-actual-sampler-probe-census-registry-01/receipt.json` (SHA256
`4be6453bc63204227ca7321e8fcf423a049d5179d673b51dcdcfcbb96f7ef29f`)
records a failed whole mock. All three rendered engines, both fixture workers
and immutable launch publication passed their functional checks, but ten of 212
process samples were incomplete. Those samples receive no resource credit.
The original UI/controller Jobs drained; independent review accepted only the
current-workload drain and three exact full identities dead in
`browser-launch-mock01-drain-approved.json` (SHA256
`d54126b7f8e64f8ce3d4c7f7a272fe7049d94272f4c9895d5f92b7e251fac180`).
This does not establish whole-host completeness or qualify an actual browser run.

The prospective fixed-cohort sampler design passed independent review in
`browser-census-fixed-cohort-design-approved-01.json` (SHA256
`5ad2e6841c1a835f140be86aa4ac202b7744fc026b540cbc66abb1056d5e2d0a`).
Its completed-worker clarification was frozen before dependent code in
`browser-census-completed-worker-precode-amendment-01.json` (SHA256
`a91b0c9becbff03814dd7eb1e1903b6b54490d892b801e43cc347ab1256cb7d7`).
Every original selected identity must receive a successful live measurement or
an individually proven permitted terminal exclusion. Late arrivals require
explicit identity and original Job proof, receive no numeric credit, and must
enter the next census if alive. Reports describe the surviving declared cohort
and sampled lower bound, never an instantaneous whole-Job total or true peak.
Fixed roots, two mock/24 actual worker obligations, cadence, span/gap limits and
the inclusive 8 GiB limit remain mandatory. New code, native qualification and
mock review remain pending; no historical failed sample is reclassified.

## Closeout mapping remains incomplete

The first combined family mapping completed its bounded integrity checks but
retained a blocking API/Seed join defect: a structured discharge object was
compared with an obligation-ID string. Its affected positive arrays were cleared;
the original 36 separately reviewed proofs remain intact. The independent
outcome is `family-profile-map01-outcome-reviewed-blocked.json` (SHA256
`af8bb98a8705d6686a179696737c0e40198cf9dfcb09ed5a09448ce0dcd7880e`).
A new version is being prepared; this grants no native audit, composite
acceptance or cleanup authority.

The static-command provider passed 81 synthetic checks and independent review
only as a pure provider. `original-session-static-provider01-approved.json`
(SHA256 `d2d01c08ee7dcb1464044682506b0b9df464a41f2cd70bd0d27ddb4d8cb743ad`)
accepts zero actual exclusions. Historical source-at-call and execution context
must be established independently; current source hashes and caller-supplied
trust objects are insufficient. Bounded provenance discovery is preparatory.
All unresolved capable-launch coverage remains blocking. No original service
operation, commit or push occurred in this documentation checkpoint.

## Subsequent bounded mapping and sampler review

The corrected combined mapping completed all 65 read-only slots with no entry
errors and intact source fences. Independent review verified 241 file hashes,
all saved slot bodies, and the corrected structured API/Seed join. Receipt
`family-profile-map-02/receipt.json` has SHA256
`3be3d634d688d1625d200e94cc3f6c42124ed7855821d591c4997e8409934fcc`;
root session 9224 completed with exit zero. The outcome approval is
`family-profile-map02-outcome-approved.json` (SHA256
`dea54d4bd311c8237faa82b111ae4d19428319fa0146c187644b2789593c59a9`).
All 65 results retain unresolved scope; none grants native, resource, complete
host inventory or cleanup credit. The earlier defective mapping remains retained.

One independently reviewed bounded provenance discovery read only the two
previously frozen task-record prefixes. It completed with zero matching
standalone calls and seven explicit missing-call gaps. Receipt SHA256 is
`178eaac08e7984ef7f387f96ad380d16b6b108b6e0b4c32b58b089ae1769e42c`.
The seven files remain unbound artifact candidates, not seven asserted launches
or accepted static exclusions. This zero-result discovery will not be repeated
as a substitute for concrete capable-launch reconciliation.

The first fixed-cohort core passed 99 injected tests, but independent review
found a blocking bound defect. The retained-handle count omitted metadata for
initial OpenProcess87 exclusions; an injected case accepted 1,023 metadata
identities against the approved 512 bound. Transient PID-validation and Toolhelp
snapshot handles also need capacity within the native-handle limit. The blocked
review is `browser-cohort-core01-review-blocked.json` (SHA256
`59d4b3d04860f339f1f41043cc8c25169730253ed6e6dcf782215cf50b7d6006`).
New versioned code and boundary tests are required; old files and failures remain.
A fifteen-case native qualification plan is conditionally approved for authoring
against the corrected, independently reviewed core. It authorizes no native run
yet. Actual-browser acceptance, exact 4 GiB upload and final closeout remain
incomplete. No application-source change, original-service operation, commit or
push occurred in this checkpoint.

## Corrected sampler approved; qualification and audit still pending

Core02 resolved the combined-metadata and transient-handle bound defect. Its
111 injected cases passed, and the independent reviewer separately reran twelve
boundary/poison cases successfully. `browser-cohort-core02-approved.json`
(SHA256 `5d05686b6e8b92814edb4a2e5bf8f252952daceda0087aa7ececa09c967e7b64`)
approves these exact code bytes for subsequent fixture qualification, not an
actual native or browser result. Core01 remains blocked and unchanged.

The new native fixture's fifteen planned groups expand into seventeen physical
case entries. Its 72 pure checks passed; native execution has not occurred at
this checkpoint. The pending mock draft passed 125 pure integration checks and
early independent review, but deliberately cannot launch without reviewed actual
native results and a final frozen dependency map. These are preparatory checks,
not replacements for actual acceptance.

The first finite closeout audit passed 71 pure/fake checks. Independent review
then found that its executed native-identity imports were not bound to the
verified checkout module origins/hashes. The blocked review is retained in
`final-phase4-readonly-audit01-review-blocked.json` (SHA256
`750faee3a1f1e5024cc16b0bbdd3a3ddfb14e5bc730cd90f732c8f7a4cecba31`).
New versioned corrections and wrong-origin tests are required. No actual native
or service query used this audit. Its later-launch cutoff, live resource checks,
source-specific unresolved scopes and auditor post-exit proof remain pending.
No original services changed, and no commit or push occurred.

## First corrected-core native fixture failed; current workload drained

`browser-cohort-native-probe-01/receipt.json` (SHA256
`7f3060849dec24b1152abb5baebbcc1f1921a6390c0d769d6c492878bfd29203`)
records fifteen passed physical cases and a failed sixteenth case. The final
growth case did not run. The repeated-deferral case failed its initial positive
measurement with a census-stage TimeoutError: zero committed census generations,
zero counter attempts and a 0.7873498-second transaction. Its intended negative
injection was never reached. Root session 67687 ended with exit one.

The fixture wrapper had retained original C0 evidence before requesting a new
leaf and awaiting creator/full-readiness markers with a 0.75-second guard. The
exact throwing operation and which marker was unavailable at the deadline were
not retained. Later readiness records do not prove timely readiness, and no OS
or scheduling cause is established. The invocation remains failed with no native
qualification or resource credit.

All sixteen started cases retained successful unforced original-Job, creator and
scope drains. Source hashes matched afterward. Root's post-exit check verified
55 exact full identities dead; independent review checked 622 file hashes and
261 original identity references. The limited outcome approval is
`browser-cohort-native01-outcome-failed-reviewed.json` (SHA256
`77d6033e24f826ce2aac1c3f45a50bed90b31d61f9d8f3b33614b4209e95cfdb`).
This is current-workload drain evidence, not complete historical host coverage.

The prospective fixture-only correction was independently approved for authoring
in `browser-cohort-native02-proposal-approved.json` (SHA256
`3a5a208de5dc8df804d812bf10f2a23f2721688f71479f5f6ce25d09ce6427c6`).
It retains the 0.75-second acknowledgement and original sampler limits, awaits
immutable creator acknowledgement inside the callback, and requires bounded
full readiness/source/identity validation after measurement before a case passes.
Later checks cannot fill missing original enrollment evidence. New code review
and a fresh native run remain pending. All original failures remain preserved;
no original services changed and no commit or push occurred.

## Native02 qualified; subsequent mock remains failed

The revised native fixture passed all seventeen physical cases across fifteen
groups in 40.557785 seconds. Independent review verified all seventeen unforced
Job/creator/scope drains, 729 retained file hashes and 58 exact full identities
dead with 276 original reference joins. Source bindings remained exact. The
approved native-only outcome manifest is
`browser-cohort-native02-outcome-approved.json` (SHA256
`19b75f85a37b7a182f7c2a1ce01ece1d9952bf31563692cf5b9beca3ef375bb7`).
This does not grant browser or resource acceptance; native01 remains failed.

Fresh `browser-cohort-mock03-preflight-01/preflight.json` (SHA256
`4dc92900f0efe3ef3b1422b4d48c1834bc56d59115a7d5b3c08f930fb8f65df1`)
matched 287 protected hashes, five original service identities/images/endpoints
and 152 runtime files. Ports 55175 and 55176 each explicitly refused one bounded
connection attempt. This is point evidence, not continuous uptime proof.

The first mock command used a relative integration-plan argument where an
absolute path is required. It failed before dynamic helper imports, native
queries or Job construction; only the failed receipt and cleanup stop markers
were created. The failure is preserved in
`browser-cohort-mock03-prelaunch-failed-reviewed.json` (SHA256
`21fcfb9041437c8c53c03223d4fc08d59e4e1927b1b253e364ce2695104dddae`).
Independent review accepted a fresh invocation with absolute arguments and the
same exact reviewed code/freeze; no guard was relaxed.

That fresh invocation, `browser-actual-sampler-probe-census-cohort-04`, completed
three engines and both fixture workers but **failed** its memory gate. Sample 85
of 214 rejected PID 44092 as `unknown_live_arrival`. It was absent from original
global/selected/Job observations and the pre-counter observations. The later
raw population still omitted it while the controller Job listed it, leaving its
observed parent unset. No target enrollment or counter read occurred. Fourteen
original cohort brackets completed; this disagreement between sequential
observations does not prove the target's native identity, cause or lifetime
memory. The maximum transaction and committed-capture gaps were approximately
0.268036 and 0.277100 seconds, respectively. The observed aggregate
1,320,521,728 bytes receives no resource credit.

Independent review verified both original Jobs empty/drained without forced
cleanup, all 1,226 before/after bindings exact, and three selected full identities
dead. The large memory file was hashed but explicitly excluded from post-exit
identity extraction. The limited failed-outcome approval is
`browser-cohort-mock04-outcome-failed-reviewed.json` (SHA256
`8f6e1c063e5b07ef18c653e679e25cdf5b3c730d9caf29913a1d61fc46ee969c`).
A prospective parent-unobserved amendment requires review before new code;
mock04 remains failed and grants no retry, actual-browser or resource credit.

## Parent-unobserved native qualification; mock05 failed

The prospective parent-unobserved amendment and core03 passed independent
pre-code/code review. It preserves immutable initial cohorts, native identity
and same-held-Job proof, original counter brackets, worker obligations and all
resource limits. Missing observed parents remain unknown; they are never
invented or used to infer ancestry. The nine targeted native03 cases passed in
24.323477 seconds. Independent review verified their source bindings and drains
and 36 exact full identities dead. The native-only outcome manifest is
`browser-cohort-native03-outcome-approved.json` (SHA256
`a798cb0a6d4679be0e6210801f84b1b603d89c1435a54a139d0491b0e9a8aa97`).
The older seventeen native02 cases remain evidence for their older source.

The independently reviewed mock05 candidate bound 1,685 files. Fresh preflight
`browser-cohort-mock05-preflight-01/preflight.json` (SHA256
`6dd19ab5bd6679e6ea6bfc927e3ef0be7f9b3b5f3022a6a37d26ca0f4eefa003`)
matched all 287 protected hashes, five original service identities/images/
endpoints and 152 runtime files. This is an observed interval only.

`browser-actual-sampler-probe-census-cohort-05` **failed** (root terminal
`f9d28c`, exit 1). Three engines completed their mocked flows and two fixture
workers satisfied their recorded obligations, but two of 213 samples were
incomplete. Sample index 1 rejected PID 43252 with
`moved_or_new_membership_for_C0`; its initial raw ancestry included the process
while the controller Job membership was empty. Sample index 2 recorded
`actual_committed_capture_gap_exceeded` after the aborted sample. These remain
failures; successful mocked interactions do not establish resource acceptance.
The failed receipt SHA256 is
`de2643b3671c1a3ce01ccf1fc4a68f9b4ce26fbea33efe6db567f4b782744022`;
the memory receipt SHA256 is
`ccb4af681daa9d3fb325391bb4ab300c639b9bd3ab0392244987b850324381c0`.

The receipt records both owned Jobs empty, cleanup errors empty, and dependency
bindings unchanged. Root post-exit inspection (`9ad638`, exit 0) confirmed the
three exact full identities from twenty small invocation JSON files dead, with
six retained origins. The large memory file was hashed and explicitly excluded
from identity extraction. This bounded check is retained in
`browser-cohort-mock05-postexit.json` (SHA256
`d11e59b6f7530b3f18940457a6584297725223fb3cfbf11ce2a05ae647890bc6`).
Independent failed-outcome review and prospective launch diagnosis remain
pending. No actual-browser resource credit follows. Actual-data browser
qualification, exact-4-GiB acceptance and final backup/restore/cleanup remain
incomplete. No original services were changed and no commit or push occurred.

Independent read-only review subsequently confirmed mock05's limited failed
outcome: all 1,685 source/evidence bindings rehashed exactly, all six identity
origins matched, and both held Jobs were empty and closed with no unresolved
controller drain error. The reviewer accepted the retained root dead-identity
observations without claiming a new native query. The bounded outcome is
`browser-cohort-mock05-outcome-failed-reviewed.json` (SHA256
`82ec642c3c711b61117134e4c06b1011fe2503929b96fe298c7467afa0f05b67`).
The sample-2 cadence error follows the missing committed capture from sample 1;
the maximum non-null recorded capture gap was approximately 0.276697 seconds.
A controller assignment window is consistent with the source launch sequence;
its exact assignment timestamp was not recorded and is not asserted as observed.

The finite audit04 adapter also passed independent code-only review: 139 new
and 113 inherited regressions, eighteen packet file hashes and twenty-seven
source pins. It adds only the two approved durable anchor joins, preserves
zero-byte reserved/absorbed charge history, and requires every selected full
identity to satisfy its checks before any permitted partial-parent probe.
`final-phase4-readonly-audit04-code-approved.json` has SHA256
`536922a2e463e31e9b270ed4e4ee783e1c4636afa531423a7d9f01c6c3df0cc6`.
No live query ran. A fresh resource baseline, complete later-launch cutoff,
reviewed execution plans and root clearances remain required; unresolved
historical scopes and final cleanup restrictions are unchanged.

The narrow mock06 launch-order proposal passed independent pre-code review
(`fdc361`, exit 0). Approval
`browser-cohort-mock06-launch-order-proposal01-approved.json` has SHA256
`9b7b1041403dc20f1cb062727caf2217abd6dce7b0ec4fb1061b74d979bbcf4d`.
It stages, assigns and strictly verifies the controller before sampling, then
requires the original first complete sample of that exact controller before
releasing the existing start barrier. It explicitly excludes controller
bootstrap from measured coverage while keeping application launches inside the
measured interval. Core sampling rules, limits, original start deadline and
controller completion lifetime remain unchanged. This approval permits new
harness authoring only; code review and fresh mock qualification are pending.

## Mock07 launch order verified; resource gate still failed

Independent mock06 review found the first-sample proof existed only in memory
before start release, contrary to the approved proposal. That version was not
executed. New mock07 persists the proof with flush/fsync before release and
fails closed on persistence errors or the unchanged deadline. Independent review
verified all 1,704 bindings and 165 checks (`55fa9a`, exit 0). Fresh preflight
matched protected files, original services and runtime, with both test ports
refused; its SHA256 is
`de4ab8cc86bae06d647e0d42847b3c914d9db213c1c7198ebce75c2be143e61d`.

`browser-actual-sampler-probe-census-cohort-07` nevertheless **failed** (root
session 49104, terminal `c0a795`, exit 1). All three mocked browser flows and both
worker obligations completed, but sample index 207 of 211 failed enrollment
image query for PID 30016 with native error 5; index 208 recorded the subsequent
missing-capture cadence failure. The maximum non-null transaction/capture gaps
were approximately 0.267584/0.273528 seconds. The image-query failure's cause is
not established. No failed sample or whole run receives resource credit.
Receipt SHA256:
`5293d361b6046ee73644c2af2b3575143d460d2481f9c1ca989723f87d1d762f`.
Memory SHA256:
`a0347fee26497058a657147047b447ad0a768c576eb762d20f35ee80a6a2aae4`.

Both owned Jobs were recorded empty/closed, cleanup errors were empty and all
dependency bindings remained exact. Root post-exit inspection (`40a4ab`, exit 0)
confirmed three selected full identities dead with six exact origins from 21
small JSON files; one large memory file was hashed and excluded from extraction.
`browser-cohort-mock07-postexit.json` has SHA256
`9ce1a2d22eec3d65e9507fec8391b1ff93ab2e3cedd43c2115894fc10826681b`.
Independent outcome review and any prospective correction remain pending.

Independent closeout scope review clarified that a complete current inventory
of relevant owned processes/resources may establish current cleanup safety
without reconstructing every historical tool-process chain. Historical gaps
remain limitations; actual capable unknowns block cleanup. The finite inventory
plan is approved for bounded authoring only, including actual-schema pending/
active/draining and unfinished-intake coverage, exact stopped-container states,
retained charges and queued memos with zero model authority. No live final audit
or cleanup occurred. Scope ruling SHA256:
`27c9bc0bdb2354126b8df8b811dc2aaa38e64c7870178622ed2053fabb785a48`;
authoring approval SHA256:
`fc76d4090a42b349ef41c743c2b81c0808990c7768e2bc2d8b04cc434eba4065`.

Independent review then verified mock07's failed outcome, all 1,704 bindings,
exact first-sample persistence/release ordering, unforced Job drains and bounded
post-exit origins. Outcome manifest
`browser-cohort-mock07-outcome-failed-reviewed.json` has SHA256
`1cf565cf0927b5843a245aa78d3d2ce0c10dafc7c12542ae6ea3a7fe56d26596`.
The failed sample attempted no counters and closed all five enrolled handles.
An optional disappeared lifecycle PID remained uninspected and uncredited; the
held-Job drain proof is separate. Error 5 proves neither termination nor cause.

The target was a previously measured known worker. Its exact completion ledger
entry was committed after the failed sampling decision; this cannot retroactively
satisfy the old decision rule. A prospective known-worker-only terminal enrollment
amendment is being prepared. It must require contemporaneous native proof from
the original held handle and existing prior committed live coverage. Any later
completion can satisfy only a separate final obligation, never missing original
ownership, identity, terminal or measurement evidence. No amendment code or new
acceptance is claimed at this checkpoint.

The known-worker terminal-enrollment proposal subsequently passed independent
pre-code review (`8386ae`, exit 0). Approval
`browser-cohort-known-worker-terminal-enrollment-proposal01-approved.json`
has SHA256 `01e77037118dc83a8d029df1ec396c16ca7a30374a8db5fc83e9a150f39cac75`.
It permits authoring only. Genuine image-failure reproduction is required in the
six-case native qualification; injected failure remains separately labeled. No
assumed error code, hidden retry or retrospective mock07 credit is permitted.
Core review, native review/outcome and fresh mock acceptance remain pending.

Core04 passed independent code review: 191 no-write checks, all 204 authored
checks inspected, and old evidence/runtime bindings verified. Approval
`browser-cohort-core04-approved.json` has SHA256
`8723b23ca080db517f679332936f14783452f0529cc554b01c97d3c2a263c2ae`.
This permits the six-case native fixture's authoring, not native acceptance.

Pending actual-master03 structure review passed 65 independent checks and its
direct-assembly block. It separates lifecycle/publication evidence from Job/
creator cleanup, bounds its read-only six-file SQL audit, and preserves its
original controller deadline. Approval SHA256:
`4e9648e96f32c43a979a17967f561c2333557d6668176b0a20b4e1982fa86a6b`.
Pending mock08 structure review passed 193 independent checks; its old startup
barrier is exact and all four native core imports are required. Approval SHA256:
`2ef6326b36f2c6463ed783184e6d162048743ee9e8b398c01e2ba7b79b2639e7`.
Both remain blocked before execution until actual qualification descriptors,
final source roles and full binding manifests are reviewed in new final versions.
