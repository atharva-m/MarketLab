# V2 Phase 3: actual verification

Status: PHASE 3 LOCAL COMPLETE; independent closeout review passed. October 29, 2026
(America/New_York). The user approved the detailed Phase 3 proposal and explicitly
prohibited commit/push. Authority is recorded in [AGENTS](../../AGENTS.md) and
the [pre-code contract](phase-3-research.md). Earlier Phase 2 outcomes remain in
[their verification](phase-2-verification.md).

Final-source quality/backend, retained legacy, independent actual numerical,
cold, native crash/cache and rebuilt package gates passed after independent
review of the corrections below. Final database dumps/restores, owned cleanup
and post-cleanup preservation also passed. Independent technical review found no
unresolved blocker before cleanup; final independent documentation/post-cleanup
review also passed with no unresolved blocking finding. The final checkpoints
below supersede earlier pending operational-gate
statements; all failed invocations remain historical.

## Pre-code source inspection

Initial checkout HEAD was `c44ea13778b01a84721e51677bd8a7e296202bfe`, with clean
tracked/untracked Git status before Phase 3 edits. Read-only inspection confirmed
migration head `0008_v2_ingestion`, fixed legacy request dates/symbols and USDT
units, separate legacy durable research tables, shared application BarService,
and Phase 2 union/verified catalog and SQLite selection helpers. Source files,
Phase 1/current matrices and R3/R4 contracts informed the prospective contract.

The coder updated authority/roadmap and authored the contract before any Phase 3
runtime edits. Independent pre-code review is pending. The parent owns fresh
ignored preservation evidence under `artifacts/v2-phase3-20261029`. The parent
reported 287/287 protected hashes matching the Phase 2 inventory, all five
original/README containers running with zero restarts (the three original
health-bearing services healthy), both API health endpoints 200 and readiness
dependencies up. Initial sandbox-denied Docker/localhost invocations remain
failed; only elevated read-only retries established those outcomes. In particular
`endpoints-before.json` has failed status0/null and is not success evidence;
`endpoints-before-elevated.json` records the successful retry. These are observed
baseline checks, not continuous uptime or Phase 3 acceptance. No application test,
data acquisition, migration, provisioning or numerical gate is claimed here.

## Initial independent pre-code review and corrections

Independent read-only reviewer `gpt-6-astra/medium` returned two blocking P1
findings on the first contract draft: publication wording allowed immutable rename
before the fenced run transaction, and a separate research capacity ledger/lock
could overcommit space concurrently with Phase 2 ingestion. This review was not a
pass. The coder corrected the contract before runtime implementation:

* Full artifact verification occurs outside the transaction, followed by run-row
  and advisory locks, live token/owner/lease/cancellation checks, then immutable
  rename/adoption and atomic result/attempt/run registration. A stale-worker
  pre-rename race is mandatory acceptance.
* Both admissions use the existing exact `v2-space:<str(root.resolve())>` lock and
  combined outstanding reservations across ingestion/research ledgers and
  filesystems. Phase 2 integration is narrowly scoped to this preservation
  requirement; all hard ceilings and retained conservative charges remain intact.
  Concurrent admissions and retained failures are mandatory regressions.

The reviewer preliminarily accepted a performance optimization after full
integrity verification: inclusive disjoint numeric-ID ranges prove no repeated
IDs for the same instrument when bound to catalog/manifest/artifact hashes and
file signatures. Overlaps still require bounded exact merge/SQLite checks. The
contract now includes this design and stale-proof/boundary regressions. No
unverified-footer or metadata-only shortcut is authorized.

One documentation patch invocation failed its expected-line match before applying
any file changes; the corrected patch then succeeded. This was a tooling failure,
not a runtime test outcome. Initial link inspection and `git diff --check` passed;
independent rereview of these corrections passed with no unresolved blocking
finding, as reported by the parent. Runtime implementation was then authorized
to begin under the frozen contract. No runtime edits or operational mutations
occurred before that rereview passed. Contract hash receipts are retained under
`artifacts/v2-phase3-20261029` before runtime edits.

## Implementation and focused verification checkpoint

After passed pre-code rereview, the contract/authority hashes were frozen in
`artifacts/v2-phase3-20261029/contract-freeze.json` before runtime edits.
The coder implemented additive `0009_v2_research`, isolated v2 spec/numerical
projection/store/service/routes/CLI, shared capacity accounting and application
lifecycle. One delegated coder owned only generalized analytics and its tests,
then reviewer regressions. No dependencies, locks, model/prompt configuration,
original services or historical migrations changed.

Parent-owned disposable PostgreSQL/Redis use exact labeled resources recorded in
`owned-resources.json`; no original containers were changed. Fresh and populated
0009 rehearsal and pre-upgrade backup/restore passed: 24 existing tables' rows and
207 existing constraints remained exact, with seven new tables. The first
migration harness invocation failed its asymmetric constraint filter (207 vs206);
that invocation remains failed. The corrected direct comparison passed in
`migration-verified.json`. Parent copied 148 retained input files/2,982,488,140
bytes with exact hashes and restored separate actual/legacy acceptance databases.
No new download or actual numerical campaign is claimed by that preparation.

The initial implementation review identified error mapping/retry, provenance
compatibility, divergent orphan comparison, shared helper fingerprint coverage,
strict submicrosecond/deep-JSON rejection and cooperative worker shutdown gaps.
Corrections preserve safe v2 errors, narrow transient retry, source/lock/protocol
compatibility before claim, persisted execution provenance, deterministic staged
artifact comparison, shared helper inclusion in the existing dataset fingerprint,
strict timestamp grammar, bounded parser errors and stop/drain signal handling.
Shared Windows extended/plain paths now normalize to the same capacity lock.

Focused analytics passed 85 v2/legacy cases (36 new/49 legacy), with Ruff and
strict mypy clean. Review regression tests passed 25 cases, including nine initial
real-PG durable/provenance/orphan/fence cases and added simultaneous capacity
admission in both directions, retained-byte blocking and cooperative claim drain.
The first research/ingestion PG run had 18 passes/one invalid test-fixture failure
that violated preserved reservation ownership CHECKs. Its next focused run had
19 passes/one test-fixture accounting failure caused by treating already retained
source bytes as an outstanding reservation; the fixture was corrected to use a
native outstanding reservation. Both failed invocations remain retained.

Initial sandbox async invocations hung in Python's local socketpair creation and
were explicitly interrupted; faulthandler recorded socket accept before test
execution. The elevated retry passed all 16 research parser/projection/HTTP tests.
These permission/interrupted invocations remain failures; they are not numerical
deadline failures. The final combined focused run passed 60 cases in 26.09s,
including all research/parser/HTTP/reviewer cases and retained ingestion integration
cases. Ruff over `src`, `scripts`, and `tests` passed, all 161 Python files in
that scoped invocation were formatted, and strict
mypy passed 72 source files. All raw results stay ignored under the Phase 3
evidence root.

Independent source review reported the seven runtime findings resolved. The actual
numerical/native-crash harness passed independent review after exact Docker
ownership checks, four explicit retained dataset IDs and official/CSV/Parquet
provenance, fresh-key numerical repeats, post-close worker drain, independently
frozen crash output hashes, exact conservative charges and no-overwrite assertions
were added. Main harness SHA256 at scoring freeze is
`571a771aca12150bd5cdc9b66b49989f7c71ef38b26d248373912877d27aa5cf`.
Runtime/scripts/tests are frozen for final suites and actual campaigns. The separate
real Redis cache harness is authored and awaits independent review/execution.

Pending: P3-01 legacy hashes/v2 projection; P3-02 actual
new-date/instrument/format/Decimal-oracle runs; final P3-03 invalid selections and
limits mapping; P3-04 actual cache/recovery/native crashes;
P3-05 fresh legacy cold all-62; full current-source quality/database/package/
frontend regressions; dump/restore, protected/service preservation, owned cleanup
and independent closeout. Focused source checks do not establish actual acceptance.

No Phase 3 completion, hosted CI, model execution, original-service rollout,
commit or push is claimed. Retain all future failed/incomplete invocation identities
and source/evidence distinctions when appending outcomes.

## Redis prerequisite correction before scored acceptance

The first parent-created disposable Redis used 128 MiB/default persistence and
therefore failed the retained R3 prerequisite (256 MiB, allkeys-lru, no persistence).
No scored actual campaign had run against that setup. Preserve its initial ledger,
stopped owned container/volume and setup evidence; this is a failed prerequisite,
not a passing cache or performance result.

The parent verified ownership, stopped only that disposable Redis and created
replacement `/marketlab-v2p3-redis-r3` on the same owned loopback port 56392, using
the same installed image. `redis-setup-correction.json` records exact container
identity, owned volume/labels/ports and observed `maxmemory=268435456`,
`maxmemory-policy=allkeys-lru`, `save=""`, `appendonly=no`. The active private
configs and ownership ledger point to the replacement. Original services remained
untouched. The cache harness's exact expected name was updated; its ID/image/
mount/port/label checks remain strict. Main numerical harness code and runtime
source were unchanged by this prerequisite correction.

## First complete suite failure and narrow migration correction

The first complete invocation `full-d27e2d58` failed: offline passed 1,211 cases
with 231 PostgreSQL cases deselected; PostgreSQL passed 229 and failed two stale
migration-head assertions that still expected `0008_v2_ingestion`. Repository-wide
Ruff also reported 14 E501 lines in the new migration's SQL text. The earlier
passing Ruff invocation covered only src/scripts/tests and had omitted migrations;
it was not a passing repository-wide lint result. Preserve the first full run.

The coder wrapped only whitespace in `0009_v2_research` SQL, preserving every
SQL token and quoted literal. The intermediate correction still had two E501
lines; those were then wrapped and retained as an intermediate failed check.
`migration-lint-before.json`, `migration-lint-after.json`, and
`migration-lint-final.json` retain exact identities. Final migration source hash is
`df1c902fd1301e9d59fe79d409cc362c46512434219a6bedf9a72efe64c1498d`;
pre/post SQL token SHA256 is unchanged at
`c3686573b5c416bee20b517776d2336acab7fc02752ad5a40e70362558c60603`.
No runtime formula, limit, state protocol or DDL semantics changed.

The two existing migration tests now expect head 0009; the exact table-set test
adds precisely the seven new research tables while retaining every old table,
column/type/nullability/primary-key assertion. Targeted real PostgreSQL checks
passed two cases (15 unrelated cases deselected) in 3.49s. Full `ruff check .`,
repository formatting (241 files) and strict mypy (73 sources) passed. Independent
narrow rereview, corrected migration rehearsal/package rebuild and final complete
suite/actual acceptance remain pending. No actual scored run preceded this repair.

## Actual legacy-selection failure and bounded verifier repair

After independent narrow rereview, the corrected migration was rehearsed again
on fresh/populated copies with verified backup/restore: 24 existing tables and
207 existing constraints remained exact. The rebuilt owned package image passed.
Complete invocation `full-3d389a04` then passed repository Ruff/format/mypy,
1,211 offline and 231 real PostgreSQL cases, with source-before equal to
source-after. This passing source remains separate from the repair below.

Actual invocation `p3-legacy-01` FAILED in 174.57s: generalized selection passed
31/62 missing legacy versions to the native verifier in one call, exceeding its
unchanged five-partition batch limit. The actual-data gate `p3-actual-01` was
explicitly interrupted before repair to preserve a coherent source interval.
It had just created the BTCUSDT February 28 ingestion submission; its consumed
attempt and expired lease were preserved for normal recovery, without resets.
Parent retained exact process/interruption receipts. Neither invocation is a pass.

The coder changed only generalized bar preparation to call the same native
verifier sequentially in batches of at most five, aggregating manifests before
the unchanged catalog/signature/identity checks and cache installation. Every
batch shares the same cancellation signal and caller deadline; the native limit,
compute permits and dataset modules are unchanged. No dataset edit interfered
with the parent-owned ingestion recovery.

Three real PostgreSQL regressions passed in 37.44s using genuine controlled
legacy archive ingestion and native full verifier subprocesses: 31 registered
daily versions, 62 versions across both instruments, and cancellation after the
first five-version batch. They assert exact batch sizes/coverage, full verified
manifests, unchanged repeat-cache behavior, zero active permits and no second
batch/cache installation after cancellation. These are controlled fixtures, not
the retained all-62 actual numerical acceptance. All 85 v2/legacy bar regressions
passed in 2.34s. An intermediate formatting check failed on new test signatures;
after correction, repository Ruff, all 242 files' formatting and strict mypy
(73 sources) passed. Independent repair review and final-source full/actual reruns
remain pending; earlier passes do not waive the failed actual gate.

## Interrupted-ingestion accounting and acceptance preparation efficiency

The interrupted BTCUSDT February 28 job
`1d462afc-837a-4a1a-89e6-c55453a9afe0` retained its first attempt and native lease
expiry. Normal recovery then failed capacity admission on attempt two; this remains
failed work with its consumed budget. No attempt/key/state reset or limit change
was performed. Earlier shell-quoting and missing-idempotency-column inspection
probes also failed and remain in the parent tool transcript.

After independent review and exact ownership/path/reference inspection, the
parent's cleanup helper passed in `interrupted-storage-cleanup.json`. It deleted
only the 731,901,952-byte partial `normalize.sqlite` from that interrupted attempt.
The official source ZIP/checksum remained exact at 101,093,731 bytes. Only that
owned attempt's output reservation became released with zero bytes; its scratch
reservation retained the actual source bytes with zero unconsumed reservation.
Job/attempt history and all historical Phase 2 records remained unchanged.
Cleanup is separate from successful ingestion; the failed invocation is retained.

Read-only profiling also found redundant acceptance preparation: the harness fully
reconciled every v2 catalog artifact before ingestion and repeated the scan after
ingestion, then native numerical preparation repeated those same verifications.
The initial unscored scan took approximately nine minutes; interruption occurred
during subsequent normalization. Those elapsed observations are not a controlled
speedup or a numerical pass.

The reviewed design correction confines discovery to SHA-checked, <=64 KiB
manifests for the four explicit retained IDs and approved instrument/days, with
bounded alternatives. Full native `prepare_selection` remains mandatory for every
selected official and canonical version before any oracle read or scored run;
it uses the normal capacity reservation/deadline and native signature-bound
verification cache. The harness never seeds that cache. Independent oracles read
only those verified paths and compare complete catalog/file signatures before
and after reading. Cold execution remains a separate fresh-process path.

Five controlled orchestration/hash/bounded-discovery/stale-binding regressions
passed in 0.42s. Repository Ruff, formatting of 243 files and strict mypy of
73 sources passed. Main harness hash after this correction is
`726984445b112a9dc974de105068e60bc1e10a7d1d59bcb1e3f250bef8bb482e`.
Independent final repair/harness rereview and final-source complete/actual reruns
remain pending at this checkpoint. All tracked files are then frozen for those
campaigns; no earlier result substitutes for their actual outcomes.

## Second actual invocation: retained ingestion passes and oracle transport correction

Invocation `p3-actual-02` completed all five missing approved official-day
ingestions and full native preparation of all selected official/canonical
versions. It then remained CPU-active in the first independent bar oracle, with
no first-day oracle receipt or numerical score completed. The parent stopped only
its exact owned processes at 2026-10-29 23:56:46 UTC. The sidecar
`p3-actual-02-interruption.json` retains the successful prerequisite work and
explicit interruption. This invocation is not a numerical acceptance pass; its
ingestion/preparation evidence remains separate from subsequent attempts.

Read-only metadata inspection found 11,344,216 trades in the first BTCUSDT
February 28 partition and 37,754,118 trades across the seven official oracle days.
Two bounded probes inspected only the same first 1,000 rows, without a heavy
duplicate oracle or campaign mutation. Receipts are
`oracle-bounded-probe-20261029T235535.json` and
`oracle-column-probe-20261029T235549.json`. In that sample, full Arrow-to-Python
conversion took 0.79898s, the UTC timestamp column alone 0.71796s, and all exact
oracle aggregation operations 0.00393s. Timestamp comparison/hash/offset calls
were each below 0.0005s; other columns converted in 0.0002–0.0010s each. The
timestamp became `datetime.datetime` with `zoneinfo.ZoneInfo('UTC')`.
Exact int64-microsecond conversion plus UTC reconstruction took approximately
0.00078s for that bounded sample. These samples identify timestamp conversion
overhead; they are not a controlled full-campaign speedup or a completion estimate.

After coherent interruption and independent design review, the coder changed
only the independent oracle's timestamp decoding: require exact
`timestamp[us,tz=UTC]`, reject null timestamps, cast that column to int64 and
reconstruct `epoch_UTC + timedelta(microseconds=<integer>)`. No floats, production
oracle helper, numerical formula, Decimal context, ordering, bucket rule or
16,384-row batch bound changed. Application runtime/datasets and locked dependencies
are unchanged.

Focused equivalence checks compare every decoded timestamp/decimal and complete
1m/5m output against the original Arrow conversion, including microsecond ties,
numeric 2/10 ordering, minute/five-minute/day boundaries and filtering. They also
reject wrong units/timezones/nulls. Those checks plus the existing harness binding
tests passed 14 cases in 0.48s. An initial pre-format lint invocation reported two
long test lines; formatting corrected them. Repository Ruff, all 244 Python files'
formatting and strict mypy of 73 sources passed. Independent correction rereview
and a fresh scored actual invocation remain pending; prior runtime-suite/package
evidence is unchanged and remains separately identified.

## Third actual invocation: generalized independent-reference adapter

Invocation `p3-actual-03` FAILED before frozen expectation publication or numerical
scoring. All seven independent daily oracle receipts and full native preparation
were retained. The failure was an acceptance-harness `KeyError('ETHUSDT')`:
the unchanged R4 independent comparison oracle uses literal BTCUSDT/ETHUSDT input
keys, while the generalized campaign supplied BTCUSDT/SOLUSDT. This is a failed
invocation, not a numerical result. No application runtime or original R4 reference
was changed to address it.

The corrected harness uses a private positional adapter around the unchanged
independent R4 oracle. It sorts qualified instrument identities, assigns private
calculation labels BTCUSDT to the left and ETHUSDT to the right, then remaps only
history/profile/base-volume keys and pins actual base/quote units and metadata.
Those internal labels are not registry aliases or relabeled source datasets.
Request order cannot reverse left-minus-right semantics. No arbitrary string
replacement, global monkeypatch or production numerical helper is used. The
original independent reference SHA256 remains
`3ffa16191fac3f7a61a85dfbddc914096e9457b1bf48071e2a70fc67d0f26b31`.

Eight focused controlled regressions passed in 1.86s: all three BTC/SOL workflows,
asymmetric comparison returns and reversed requests, exact nested history/profile/
summary projection, non-USDT units and literal display metadata, arbitrary
qualified IDs, quote mismatch, unchanged BTC/ETH reference output equality and
the negative original hardcode. These fixtures supplement actual acceptance.

A separate read-only `p3-reference-preflight-01` passed complete expectation
generation for all nine actual campaign selections using the seven retained daily
oracle receipts, in 1.543505s with source-before equal to source-after. It includes
both cluster/profile instruments, BTC/SOL comparison, BTC February 1, SOL March 1,
and exact canonical CSV/Parquet alternatives. `frozen-campaign-preflight.json`
retains every request, complete independently derived v2 result/summary, exact
hashes and source-oracle hashes. It is explicitly not runtime acceptance and does
not replace fresh native verification/oracles and a new frozen campaign before
scoring in the next actual invocation.

The actual scoring path now compares complete v2 expected outputs and their exact
hashes; retained legacy projection checks remain intact. Repository Ruff,
formatting of 245 files and strict mypy of 73 sources passed. Independent adapter/
preflight review and the fresh actual numerical gate remain pending. Runtime,
datasets, original reference files and dependencies remained unchanged throughout.

## Actual generalized numerical campaign passed; first crash harness failure

Fresh invocation `p3-actual-04` PASSED in 1,162.335117s: all 20 actual 1m/5m bar
comparisons matched independent oracles; all nine numerical workflow selections
and nine fresh-key repeats matched complete independent v2 results/summary and
exact hashes. This includes the approved BTC/SOL multi-day profiles/clusters,
same-quote comparison, BTC February 1, SOL March 1 and exact official/CSV/Parquet
equivalence. Full fresh native input verification and new expectation freezing
preceded scoring. Earlier failed/interrupted invocations remain retained.

The subsequent native crash invocation `p3-crashes-01` FAILED in 48.695367s at a
harness assertion: Windows venv launcher PID 46712 differed from the actual
interpreter/marker PID 48308. The parent checked exact ancestry and command/plan,
then stopped only those two owned processes. The receipt
`p3-crashes-01-owned-child-stop.json` retains identities; the attempt/reservation
and failure remain preserved for separately reviewed normal recovery. This was
not a passing native crash boundary campaign or verified cleanup by disappearance.

The harness-only correction adds readiness before claim, native parent/birth
identity and exact command/plan/executable checks for the actual interpreter,
then binds boundary markers to that interpreter's birth identity and plan hash.
Both the six-boundary and three-crash-budget loops use the same controller.
Windows termination uses a handle whose creation time is rechecked; verified
interpreter descendants drain before their exact launcher is reaped. There is
no generic tree kill. Finally paths perform the same owned cleanup on failures.
Unmatched descendants are never killed; an observed Windows conhost exits
naturally after its owned interpreters drain, and any surviving unmatched process
fails the gate instead of being broadly terminated. R8's retained native process
inventory supplies parent/birth observations without enumerating unrelated
command lines. Per-PID command inspection occurs only after ancestry/birth proof.

The first focused probe run had eight passes/two failures because cleanup treated
an already naturally exited Windows conhost as a surviving unexpected descendant.
Both owned interpreter processes drained; those failed receipts remain retained.
The corrected focused run passed ten cases in 12.29s, including real Windows
venv launcher/interpreter marker control and an intentionally wrong-plan-hash
failure that drains both interpreters before any database claim. Pure regressions
reject reused identities, foreign commands/plans and unowned processes. A final
combined harness regression rerun passed 32 cases in 13.95s, including process,
reference, timestamp and input-binding checks. Repository Ruff, formatting of
247 files and strict mypy of 73 sources passed. No application,
database protocol, dependency or original-service change was made. Native crash
acceptance still requires a fresh actual invocation after independent review.

## Failed-crash recovery and process-control robustness supplement

The parent independently reviewed and executed exact recovery of failed crash
run `2dc07942-6bef-422f-a6c0-18243418ea53`. Its stopped processes, expired first
lease and exact empty owned reservation root were verified before reconciliation;
normal attempt two then succeeded and matched the frozen independent hashes.
`p3-crashes-01-recovery.json` retains before/after identities and results. This
does not relabel the original crash invocation as passing or reset its history.

Independent process-controller review requested two final failure-path guards.
The harness now rechecks native inventory when a candidate disappears or changes
birth during command/termination checks, skips only that vanished/reused identity
and continues cleaning other verified owners. Live candidates whose commands
cannot be verified are preserved and reported after verified processes drain;
no reused or unverified PID is killed. If launcher birth cannot be observed,
the parent waits on its exact Popen handle for the child's pre-claim 60s bootstrap
fuse plus headroom (75s), records the exit, and performs no blind termination.
An overrun fails explicitly with the unverified launcher identity retained.

Six added controlled race/fuse scenarios and the prior native Windows probes
passed 16 focused cases in 13.32s. They cover disappearing candidates, reused
births during inspection and termination, continued cleanup of other owners,
preserved live unverified candidates, successful fuse drain and fuse overrun.
Repository Ruff, formatting of 247 files and strict mypy of 73 sources passed.
Application runtime and database code remained unchanged. All tracked files are
then frozen for independent rereview and the fresh actual crash campaign.

## Native crash campaign passed; first cache prerequisite-parser failure

Fresh invocation `p3-crashes-02` PASSED in 704.6355s. All six actual process
boundaries recovered through native ownership/lease/fencing rules; independently
frozen numerical hashes, conservative reservation charges and publication/adoption
checks passed. Three further actual claimed-process deaths exhausted the unchanged
three-attempt budget and rejected a fourth execution. Exact worker/launcher
control and drain receipts remain with each boundary. This is separate from the
retained failed first crash invocation and its subsequent normal recovery.

The first actual cache invocation `p3-cache-01` FAILED in 6.1277s with
`AttributeError` before its configuration checkpoint or any cache scoring. Its
only final progress entry removed an empty set of owned target/pressure keys.
No Redis restart or application runtime change occurred. The cause was the
harness assuming CONFIG GET returned byte keys/values: the installed client
callback returns text keys/values even with decode_responses=false.

The bounded read-only `cache-config-type-probe.json` inspected only the four
approved non-secret configuration fields on owned port 56392 and recorded types,
not values. It confirmed dict entries were str/str. The harness now accepts exact
str or strict UTF-8 bytes for those fields, rejects null/number/coerced/duplicate/
missing/unknown responses and retains the unchanged exact R3 configuration check.
Failure evidence now contains bounded filename/line/function and exception-type
stacks (including bounded causes), without messages, source expressions, values
or locals. No production cache behavior or settings changed.

Ten focused normalization/diagnostic regressions passed in 0.52s. Repository
Ruff, formatting of 248 files and strict mypy of 73 sources passed. Independent
harness rereview and a fresh actual cache invocation remain pending; the failed
cache invocation is retained and is not a cache-acceptance pass.

## Second cache invocation: partial checks and Docker transition evidence

Invocation `p3-cache-02` FAILED in 124.268s at a harness assertion equating Docker
stop stdout with the full expected container ID. Before failure it passed the
configuration, MISS/HIT, corruption, schema/instrument/version isolation and
native eviction checks, including 315 observed evictions. Those are partial
observations, not a passing cache campaign or outage numerical score.
The finally path restored only the exact owned Redis and verified its unchanged
configuration; the parent refreshed the active ledger from that restart receipt.
Original services and application runtime were unchanged.

The failed invocation did not retain the stop command's actual stdout. Its
format/content and the cause of the mismatch are therefore unknown; no shortened
ID, name, warning or other explanation is asserted. The corrected harness records
bounded stdout plus size/hash and CLI return code in a unique per-transition
receipt. Successful stop/start now requires return code zero and native Docker
inspection of the exact ID, labels, image, mounts, loopback host bindings and
required running state. Stdout is diagnostic data and supplies no ownership or
state authority. Both transition directions use this same guard; existing exact
pre-mutation and finally-restoration checks remain intact.

Twenty-two focused cache-harness regressions passed in 0.72s. Controlled tests
exercise short-ID/name/informational stdout forms without claiming those were
observed in the failed invocation; wrong IDs, states, labels, mounts, ports and
nonzero CLI exits still fail. Oversized diagnostic stdout is truncated to 4,096
characters with its full size/hash retained. Repository Ruff, formatting of
248 files and strict mypy of 73 sources passed. Independent rereview and a fresh
actual cache campaign remain pending. No parent helper or application code changed.

## Actual owned-package failure and scoped v2 provenance correction

The actual owned-image v2 HTTP execution check returned HTTP 500: new v2 execution
called the legacy `_build` helper, whose mandatory Git subprocess was unavailable
inside the existing no-Git image. Logs and the original package invocation remain
retained under `package-failed-01`; parent ownership-checked cleanup preserved its
evidence and original services. This failed package gate prevents Phase 3 closeout.
Installing Git, changing dependencies/images globally or weakening source identity
was not used as a workaround.

The scoped correction is confined to `research/v2`: mandatory sorted all-source
Python inventory and uv.lock hashing are independent of optional Git observations,
matching the source/lock basis already used by v2 ingestion. Missing/unreadable
source directories, required modules or lock fail closed with safe unavailable
errors. Git revision/dirty are actual captured values when available; absent Git
or checkout produces explicit unavailable provenance, null revision/dirty and a
bounded reason. No fabricated clean revision or raw subprocess error is stored.
The legacy `_build` helper/contracts remain unchanged.

Source/lock/schema/numerics/bars/inventory compatibility remains mandatory before
claim; Git availability is not a compatibility input. A same-source no-Git worker
retains the submitted host provenance, while wrong/unavailable source or lock
leaves queued work unexecuted without spending attempts. Published historical
reads remain lazy and independent of current Git/source availability.

Initial focused verification passed nine cases in 9.02s, including real copied
package subprocesses without a .git checkout and without a Git binary, exact
source/lock hash equality, a genuine Git checkout, safe HTTP 503 for missing
provenance, and a real PostgreSQL host-to-no-Git claim plus old-output readback.
Additional unreadable-lock/subdirectory and retained reviewer regressions were
then run on the final correction; their final results are recorded below.
The initial lint invocation found a fixture-import F811 annotation placement,
which was corrected without runtime impact. Actual rebuilt-image acceptance and
fresh current-source complete/numerical/legacy/cold/crash/cache campaigns remain
mandatory; all prior passes keep their earlier execution fingerprints and are
not relabeled as passes on this changed runtime source.

Final focused correction/reviewer checks passed 37 cases in 18.52s, including
unreadable lock/subdirectory rejection and optional Git decoding failure without
fabricated provenance. Repository Ruff, formatting of 250 Python files and strict
mypy of 74 sources passed. Current v2 execution source SHA256 is
`29f533bcdeac1ea40937f1672d4b93d352cd147ef9469456e1959745caf6b3c6`, with unchanged
uv.lock hash `730f02bec94d1f824a2cadf74f60cf5dcc246faa55004d5d060b92931224618f`.
The real copied-package subprocesses establish no-Git/source-hash behavior;
they do not substitute for the mandatory rebuilt Docker/API/worker acceptance.
All tracked files are frozen for independent review and final-source reruns.

## Final-source runtime acceptance checkpoint

After independent review of the provenance correction, the parent reran all
mandatory runtime campaigns on the corrected source. These receipts were recorded
October 30 UTC, still October 29 in America/New_York. The execution identity is
source SHA256 `29f533bcdeac1ea40937f1672d4b93d352cd147ef9469456e1959745caf6b3c6`
and unchanged lock SHA256
`730f02bec94d1f824a2cadf74f60cf5dcc246faa55004d5d060b92931224618f`.
This is a dirty working-tree overlay on HEAD
`c44ea13778b01a84721e51677bd8a7e296202bfe`, not a published commit or hosted CI
result. Earlier runtime fingerprints retain their own outcomes.

Raw evidence below remains under ignored `artifacts/v2-phase3-20261029`.

| Gate | Final evidence | Observed outcome |
| --- | --- | --- |
| Locked quality/backend | `full-0bba06a1/receipt.json` and logs | Ruff over the repository, formatting and strict mypy passed; 1,282 offline cases passed in 86.67s and 235 real PostgreSQL cases passed in 253.17s, with the other group deselected in each invocation. |
| P3-01 retained numerical compatibility | `p3-legacy-03/invocation.json` | Passed in 637.946479s: all five retained legacy result/summary hashes exact, five v2 projections and five independent fresh-key repeats, covering all 62 versions/230,311,900 trades. |
| P3-02 actual generalized numerical campaign | `p3-actual-05/invocation.json` | Passed in 1,241.906374s: 20 exact independent 1m/5m bar checks, all nine workflow runs and nine fresh-key repeats with full result/summary hashes equal to independently frozen expectations. |
| P3-03 validation/boundary fixtures | Final offline/PostgreSQL suites | Numeric ID ordering/overlap, sparse/warm-up/cross-day boundaries, metadata/units/quotes, strict requests, source compatibility, bounds and fenced publication regressions passed; controlled fixtures remain distinct from actual production-capacity evidence. |
| P3-04 native recovery | `p3-crashes-03/invocation.json` and boundary receipts | Passed in 705.729876s: all six native process boundaries recovered with exact frozen output hashes, registered-result/no-overwrite checks and retained charges; three additional claimed-worker crashes exhausted the unchanged three-attempt budget. |
| P3-04 actual cache | `p3-cache-04/invocation.json` and progress/transition receipts | Passed in 133.801309s: MISS/HIT, corrupt/oversized/hostile entries, schema/instrument/version isolation, actual eviction, exact owned Redis outage, fresh numerical execution with unchanged hashes, recovery and owned-key cleanup. |
| P3-05 fresh cold legacy all-62 | `p3-cold-02/invocation.json` and post-close drain evidence | Passed in 257.632181s including cleanup/drain, below 1,800s; 230,311,900 trades, exact retained hashes, one numerical attempt, memo queued with zero model calls. |
| Rebuilt Docker/API/CLI/worker integration | `package-final/receipt.json` | All 31 checks passed, including legacy/API/trade CLI regressions, v2 submit/replay/status/results/summary/cancel, packaged worker, HTTP/CLI equality, active Linux SIGTERM completion/drain and owned Redis outage/recovery. |

The actual campaign used only the approved retained BTC Feb 1/SOL Mar 1 inputs,
the frozen official/CSV/Parquet SOL alternatives and the approved BTC/SOL Feb 28
through Mar 2 partitions. All selected artifacts were fully verified natively
before the independent oracle and frozen expectations. Repeats used fresh keys
and distinct runs/attempts; same-key replay alone was not the determinism gate.
The bars/numerics formulas and independent R4 reference remain unchanged.

The five final actual/legacy/cold/crash/cache receipts each record equal before
and after source inventories, with inventory SHA256
`028cb85347c4b36691961c9dd52bf10e516ddc0277499fcbe8add3904f754b5e`.
Their inventory includes documentation and harnesses and is distinct from the
runtime execution source hash above. The full-suite and package-build inventories
also remained equal within their own scopes. These documentation outcome updates
occurred only after those campaigns finished; they do not alter the frozen
runtime/harness bytes or retroactively change the recorded inventories.

The final suites retained one offline and six PostgreSQL Starlette/httpx
deprecation warnings; no dependency repair was made. General campaign memory
is explicitly unmeasured. Cache evidence samples Redis RSS only and does not
establish a whole-campaign or process-tree peak. Campaign timings are observed
invocation durations, not controlled performance comparisons.

### Rebuilt package provenance and historical package diagnostics

`package-build-provenance.json` records a successful 37.547717s rebuild with equal
before/after build inputs, producing image
`sha256:20a51a47752151b5c6e2a2c109415ce2779e191068c0bba2bec82c9835c0de5e`.
`package-identity-probe.json` confirms the host and actual image have identical
runtime/lock/schema/numerics/bars/inventory compatibility identities. Only Git
description differs: the host records the actual dirty HEAD; the image records
unavailable checkout provenance with null revision/dirty. This is explicit
provenance, not a fabricated clean package build.

The final packaged SOL Mar 1 official profile uses the exact passed request from
`p3-actual-05`; package/host full numerical hashes match. The package receipt pins
that actual invocation's SHA256
`19ad57046861f3581b369527d24ef06883f4e94fd541c9f7f9ea6b294db32fa0`.
The earlier `package-source-bridge-invalid-shape.json` is an invalid diagnostic:
its input shape was wrong and it supplies no acceptance authority. Corrected
bridge diagnostics established only the explicitly recorded harness differences
with unchanged runtime. The final rebuilt package instead uses strict source
equality against the new actual05 campaign. No invalid bridge is treated as valid.

The earlier `package-failed-01` HTTP 500 remains failed. The reviewed
`failed-package-resource-cleanup.json` removed only its exact two owned API
containers and owned network while retaining the owned PostgreSQL/Redis and all
evidence. That limited cleanup is not the final Phase 3 resource closeout.

### Frontend regression and current preservation

The frontend source remained unchanged. `frontend-fe09ec35/receipt.json` records
passing typecheck, lint, 20 component tests and build, followed by a failed browser
invocation with 44 passes and 22 Firefox launch failures at the known logical
MSIX cache path. The separate process-only physical-cache-path retry passed all
66 browser cases in 38.12s. Both failed and successful outputs/screenshots/traces
remain retained separately. No browser installation or global setting changed;
the successful retry does not erase the initial failure.

Initial attempts to read nonexistent `invocation.json` files for the full-suite
and frontend evidence were failed read-only tool probes. Their actual receipts
are named `receipt.json`; those corrected reads establish the results above.

`preservation-before-final-cleanup.json` matched all 287 protected file hashes and
all five original/README service identities and captured image/mount/start/
restart/health fields. Both original API health/readiness endpoints were 200 with
dependencies up. The existing README GIF remained exact. These snapshots establish
the observed interval only; historical clock, cancellation, resource and unknown
uptime limits remain intact.

### Final backups, reservations, owned cleanup and preservation

The parent completed `dump_all_owned_databases.py` with retained checksummed dumps
for all eight source databases. `all-databases-dump-verification.json` passed
isolated restores for marketlab, actual, legacy, fresh-final, both populated
copies and both pre-upgrade restore copies. Every restore matched rows/indexes
exactly and constraints after PostgreSQL reparsing. All dumps and restore
receipts remain under ignored local evidence; no database data entered Git.

`final-reservation-audit.json` verified 246 actual and 41 legacy research
reservation rows released, with zero charged bytes and zero running research.
This does not mean all historical ingestion charges are zero: the actual catalog
retains 15 reserved ingestion rows with 77,309,804,544 reserved bytes and
224,075,642 retained bytes, plus 31 retained rows with 970,681,091 retained bytes.
The earlier failed-capacity job/attempt history and historical ingestion charges
remain preserved. Retained files do not become cleanup permission.

The initial read-only audit query referenced a nonexistent actual_bytes column
and failed. A subsequent receipt serialization failed on Decimal totals, leaving
`final-reservation-audit-serialization-failed.json` as a partial failed artifact.
The corrected query used retained_bytes and explicit bigint totals, producing the
verified audit above. Neither failed probe is a passing reservation audit; no
state reset or charge refund was used to make the final audit pass.

`acceptance-closeout-ready.json` pins eight acceptance receipt hashes, verifies
current runtime equality to the passed campaigns and records independent
`gpt-6-astra/medium` technical review with no unresolved blocker before cleanup.
The parent then ran exact ownership-checked cleanup. `cleanup-result.json` passed:
five owned containers, three owned volumes, one owned network and the one
remaining owned application image were removed. Owned ports 55450, 56392, 58005,
58006 and 55174 were free. Original images remained present. All raw inputs,
evidence, copied datasets, dumps and remaining charged failure files were
retained; this final cleanup performed no local filesystem deletion or prune.

After cleanup, `preservation-after-final-cleanup.json` matched 287/287 protected
hashes and all five original/README service identities and captured fields with
zero mismatches. Original live/readiness endpoints returned 200. The README GIF
remained exact. Observed snapshots do not establish continuous uptime or erase
historical unknown-cause uptime/clock limits.

Local runtime acceptance and operational closeout have passed. Final independent
read-only `gpt-6-astra/medium` documentation/post-cleanup review passed with no
unresolved blocking finding, confirming the eight-database restore, reservation,
cleanup, preservation and historical-limit evidence. Phase 3 is locally complete.
No commit, push, hosted Phase 3 result,
original-service rollout, model/prompt/dependency change or Phase 4 authority
follows.

## Publication authorized; exact-SHA hosted validation pending

After the verified local closeout above, the user explicitly authorized committing
and pushing the reviewed Phase 3 changes, checking hosted CI for the exact
published SHA and addressing actual Phase 3 CI failures through coder
`gpt-6.1-sol/high` followed by independent read-only reviewer
`gpt-6-astra/medium`. The new authority is recorded at the top of
[AGENTS](../../AGENTS.md); earlier no-commit/push statements describe the prior
local-acceptance scope and remain historical.

Publication, the published SHA and its hosted CI outcome are pending at this
entry. Local completion, the dirty source fingerprint and the actual-data/model-
independent numerical/resource/crash/package evidence above do not establish a
hosted pass. Record the actual published SHA and exact-SHA job outcomes separately,
retaining every failed invocation and any scoped review/correction. No artifacts,
data, archives, credentials, environments, weights or generated media belong in
this publication; the existing README GIF remains exact. Original services and
all historical limits remain preserved. No Phase 4 or original-service rollout
authority follows.

## First published SHA: hosted Windows harness failure and scoped repair

The reviewed Phase 3 changes were published as
`6bb5afd526e5c74e2e46c2121aa4ef856326c21e`.
[Hosted run 40996059380](https://github.com/atharva-m/MarketLab/actions/runs/40996059380)
finished with four jobs passing and the Windows offline job failing. Ubuntu
passed 1,280 offline cases with two explicit skips. Windows passed 1,280 cases
with one skip and one failure in
`test_actual_venv_launcher_worker_marker_and_failure_cleanup[False]`.
Integration passed 231 real PostgreSQL cases with four historical-input skips;
frontend passed 20 components and 66 browsers, and demo passed 11 tests. Locked
quality/build and existing package/API/Redis-outage checks passed in their
respective jobs. The unchanged 50 GiB native integration prerequisite passed
with 133,756,080,128 bytes free on both measured filesystems. Hosted skips and
coverage remain distinct from the fuller retained local acceptance above.

The failed Windows trace records `subprocess.TimeoutExpired` after 20s while
PowerShell/CIM queried the ready owned worker PID 5992. It does not establish why
that shell/CIM operation stalled. No identity mismatch, plan mismatch or numerical
application failure is inferred. The complete failed logs remain under
`hosted/40996059380/logs.zip` and the exact failed job log. The published staged
audit also records Git line-ending normalization only for `src/marketlab/app.py`
and `scripts/v2_phase3_acceptance.py`. Earlier local raw-byte execution/evidence
fingerprints remain their original observations, not byte-identical claims about
the normalized published checkout.

The narrowly scoped repair replaces only the Windows harness command reader's
PowerShell/CIM subprocess with a single bounded native
`NtQueryInformationProcess` command-line query and `QueryFullProcessImageNameW`
on the same limited-query process handle. Creation time on that handle must match
the expected birth before and after the read; native inventory still checks
parent/birth on both sides. Returned size, Unicode header, even lengths, pointer
alignment and the entire pointed payload must fit inside the fixed allocation
before any dereference. Unsupported/access-denied/insufficient-buffer responses,
malformed UTF-16, unavailable executable and changed birth fail closed; handles
close on every acquired-handle path. Existing exact argv/executable/plan checks,
readiness fuse, verified worker-before-launcher termination and native drain
assertions remain unchanged. There is no marker-only identity fallback or blind
process-tree kill.

The final focused invocation passed 43 cases in 7.94s, including actual Windows
venv launcher/worker readiness, marker and failure-path drain with a guard that
forbids spawning a query shell. Controlled regressions cover invalid status,
header/length/pointer bounds, Unicode, image bounds, reused handle birth and
handle closure. Repository Ruff, formatting of 250 files and strict mypy of
74 sources passed. The earlier 38-case/7.95s and 43-case/7.90s focused iterations
remain separate logs under `hosted/native-process-focused-*`. Initial sandbox
tests failed temporary-directory creation and an async invocation was interrupted;
the successful actual-worker checks used an elevated retry with a unique owned
workspace temporary directory. These failures are not successful focused runs.

No application/dependency/limit/workflow/original-service behavior changed and
no tests were skipped to fix this failure. Independent repair review, publication
of the repair and its new exact-SHA hosted outcome remain pending at this entry.
