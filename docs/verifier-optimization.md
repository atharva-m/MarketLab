# Authorized post-R6 verifier optimization contract

The user authorized optimizing the cold verifier and bounded CPU parallelism so
an actual fresh 62-partition cross-asset numerical workflow finishes within thirty
minutes, preserving every check/hash and R1-R6 behavior. This design is recorded
before runtime/test implementation. Prescribed coder gpt-6.1-sol/high and independent
read-only reviewer gpt-6-astra/medium apply. NO COMMIT/PUSH. R7-R9 remain unauthorized.
Parent review of these implementation details preceded code. Implementation,
full checks, actual cold/Linux acceptance and owned cleanup have passed; final
independent closeout review is recorded below. No commit/push was performed.

The later October 26 publication authority below supersedes the initial
no-commit/push restriction for the verified R6/verifier scope only. Historical
local closeout statements and evidence remain unchanged.

## Evidence and scope

Retain the completed R6 evidence and its cold combined preparation failure. The
old verifier performed Python row traversal, repeated Decimal conversion, JSON
serialization and logical hashing. A median 3,538,701-row ETH partition took
35.967s wall/35.344s process CPU, approximately one core on a 32-logical-CPU host.
R5's successful sequence prepared BTC then ETH in one BarService before its
cross-asset request; that is not a cold combined-month timing measurement.

Change only complete Parquet content verification, its analytical worker lifecycle
and shared compute admission, plus scoped tests/acceptance/documentation. Keep
normalization/writer output, dataset/schema/transform identities, decimal scale,
timestamps, logical/file hashes, numerical definitions/results, all manifests and
registered identities unchanged. No migrations, dependency/lock/deployment changes,
downloads/pulls, provider fallback, model/prompt changes, original-service restarts,
system/clock/GPU configuration, scheduling, warm-up feature or persistent trust cache.

## Exact native verification

Retain mandatory physical SHA-256 and byte-size verification before Parquet parsing,
exact Arrow schema/timezone comparison, all actual null rejection, venue/symbol
equality, nonnegative strictly ascending numeric IDs across and within batches,
UTC microsecond day bounds, positive finite decimal values, boolean types, total
row count, observed minimum/maximum and the identical canonical logical SHA-256.
Arithmetic or parsing errors remain safe failures. No rows/checks are skipped.

Use existing PyArrow native compute on fixed batches of at most 16,384 rows.
Every column is checked for actual nulls even when the declared schema is
nonnullable. Strict adjacent ID comparisons avoid subtract/overflow. Parent/child
batch boundaries preserve order; empty files/batches reconcile using old rules.

Canonical bytes remain exactly the independent legacy _logical_record encoder:
array order venue,symbol,id,microseconds,price,quantity,quote,maker,best; numeric
IDs/times; quoted positive decimals with exactly eighteen fractional digits;
integer booleans 0/1; compact commas/quotes; ASCII and one newline per row.

Raw decimal-to-string casts are insufficient: Arrow emits exponent notation for
small values. Reinterpret decimal128(38,18)'s unchanged coefficient buffer as
decimal128(38,0), cast that exact unscaled integer to text, left-pad to at least
nineteen digits and split before the last eighteen digits. Join the integer and
fraction with a dot using native kernels. Positive-value validation precedes this
formatting. No binary float or Decimal rounding is introduced. A read-only probe
matched legacy fixed formatting for 1e-18, 1e-17, 1e-7, 0.1, 1 and the largest
twenty-integer/eighteen-fraction value; comprehensive differential tests remain
required before acceptance.

Build canonical row strings with native concatenation after validated fixed
venue/symbol values. Feed only the logical data-buffer slice identified by the
Arrow offsets into SHA-256, respecting array offsets and actual lengths rather
than hashing buffer capacity/padding. This reproduces the same byte stream without
Python per-record object/JSON construction. Normalization's original encoder stays
unchanged and supplies an independent test oracle.

## Bounded process and compute lifecycle

Each reused BarService owns one lazy verification pool, maximum TWO spawned
verification children, and one shared TWO-permit compute budget. Child verification
AND native DuckDB execution consume that same budget: never two verifiers plus a
third expensive query. Existing two-read application admission, one-second
admission bound, native one-thread/512MiB/2GiB/60s DuckDB limits, coalescing and
cache policy remain intact. Library callers must reuse a single matching service
per application process as in R3. This is a cooperating per-application-process
bound, not a host-wide daemon, cross-host scheduler or aggregate limit across
independently created application processes.

Library scripts use the standard `if __name__ == "__main__":` startup guard
required by spawned processes and await service close on shutdown. Repository
application/CLI entry points already guard startup; importing runtime modules
alone never starts a verification pool.

Use an explicit spawn context on Windows and Linux, maximum two submitted
unfinished process tasks, no os.cpu_count-sized pool, nested process pool or
unbounded executor queue. A version flight may be shared by concurrent requests
with identical complete catalog identity and preflight file signatures. A read
has at most five versions and starts the next task only when shared capacity is
available. Parent waiters use bounded polling under existing request/attempt
deadlines; capacity remains occupied until the actual child/query finishes.

Top-level child entry points accept only trusted local root/relative manifest
path, version/hash identity and a cancellation IPC receiver. They recheck safe
paths and perform complete manifest/artifact verification. No Engine, DB connection,
HTTP/cache client, model, request text or application credentials enter job payloads.
Worker initialization removes application configuration environment variables before
processing, constructs no Settings/client, limits Arrow CPU and IO pools to one,
and uses nonthreaded Parquet decoding. Parent configuration is not changed.

Working data is bounded by the fixed schema/batch and at most two active jobs;
manifest input remains <=1MiB. Record real per-worker peak RSS when available.
These algorithmic/native limits are not an OS-enforced whole-application RSS
guarantee. Report parent/child measurements honestly and do not call snapshots
or sums of asynchronous peaks a measured simultaneous peak.

Cancellation uses per-job one-way IPC, checked at file-hash chunks and bounded
batch/native-kernel boundaries. A canceled waiter detaches without canceling
another active waiter's shared work. Last-waiter cancellation signals/stops the
job and drains its real future/process work before releasing its compute permit.
Canceled/failed verification cannot install a cache entry or proceed to SQL/cache
serving; catalog identity and both file signatures are rechecked before insertion.
No verification bypass on retry, timeout, broken worker or cancellation.

Close stops submissions, cancels pending/exclusive jobs, drains all real tasks,
closes IPC and shuts down/reaps both spawned children on normal/error/cancel paths.
Worker parent-death handling is bounded and tested; no orphan compute processes.
A broken pool fails safely without serial/weaker fallback; explicit service
close/recreation supports recovery. Spawn imports cannot start services/workers
recursively. Pool creation is lazy, so startup and old result/memo reads remain
model/Git/process-pool independent.

## Catalog and cache preservation

Parent reads only committed catalog rows and validates request coverage before
dispatch. Child verifies the exact registered manifest hash. Parent repeats every
retained catalog-to-manifest comparison (status/source hash/count/venue/symbol/date)
and checks catalog identity/file signatures after completion. Only successful,
uncanceled results enter the existing bounded 128-version metadata-keyed cache.
Every request still checks catalog/file metadata before a Redis hit. Restart or
changed identities/files require full verification. No persistent trusted stamp,
rewritten manifest, relaxed schema/hash check or OS cache manipulation.

BarService exposes bounded diagnostic snapshots (not high-cardinality HTTP metric
labels): configured limits/start method, active/peak shared compute, submitted/
completed/coalesced/canceled verification counts, up to 128 version/hash/count/
worker PID/timing/peak-RSS records, and close/broken state. Acceptance observes
actual 62 unique completed checks with their expected logical hashes and row sum.

## Acceptance and actual evidence

Before code, record this authority in ROADMAP.md/AGENTS.md and obtain parent design
review. Then implement, test, independent read-only review, resolve findings and
freeze source before actual acceptance. Do not overwrite historical R5/R6 evidence.

Offline differential tests compare native canonical bytes and complete logical
hashes to an independent unchanged legacy encoder, including tiny/exponent-prone
decimals, maximum precision, zero/negative values, actual nulls in each field,
bad schemas/timezones/days, negative/int64/duplicate/reversed/batch-boundary IDs,
empty/truncated/corrupt files, size/hash/count/bounds mismatch and varied batch
sizes/order. Complete old normalization/ingestion API/output tests remain.

Real child-process/lifecycle tests cover two-worker/two-compute peaks across
verification and SQL, bounded submitted work, concurrent same-version coalescing,
one-waiter/last-waiter cancellation, deadline draining, parent death, killed/broken
worker failure/recreation and shutdown reaping. Test Windows and an owned packaged
Linux spawn/lifecycle/bar-read smoke with existing images and no pulls. All retained
offline/PostgreSQL/format/lint/mypy suites and focused R1-R6 API/CLI/cache/old-result/
memo/source-compatibility checks remain required; original services are untouched.

The cold target is a FRESH process and BarService with zero verified versions,
fresh/empty owned Redis, and NO preliminary profile/bar verification. Restore only
trusted catalog metadata from retained snapshots into owned PostgreSQL; full
artifact/logical verification must occur inside the timed workflow before use.
OS filesystem cache state is uncontrolled and explicitly reported; do not flush
OS caches. Time normal full-January cross-asset submit (including prepare), durable
execution and verified results/summary readback together: total <1800 seconds.
All 62 partitions/230,311,900 records must be actually verified, each expected
logical/file hash retained, numerical payload hashes must match the independent
R4 reference and R6 automatic memo enqueue must remain correct without Ollama.
Existing application preparation/attempt timeouts stay 1800 seconds each; the
acceptance whole-workflow target is stronger, not a raised runtime deadline.

Record source/lock/dependency/hardware/cache conditions, actual monotonic timings,
parent/child CPU and measured memory where available, process limits/lifecycle and
all actual failures. Preserve dataset/numerical/memo/config/migration hashes,
original service IDs/images/start/restart/health including pre-existing optional
Ollama degradation. Parent supplies ownership-checked resources/baselines/cleanup.
Only actual cold success plus unchanged hashes, full checks, independent review
and cleanup completes this follow-up; no warm-sequence substitution or hidden
retry may stand in for the cold gate. Honest blockers remain incomplete.

Put actual outcomes in this contract/verification follow-up, README and roadmap.
No commit/push, hosted CI, R7-R9 or unrelated optimization authority follows.

## Implementation and interim verification

The prescribed parent design review approved this contract before implementation.
Native batch validation and canonical byte construction now preserve the original
normalization writer unchanged. A lazy spawn pool shares its two compute permits
with DuckDB; bounded version flights coalesce identical work. Last-waiter
cancellation drains the child, broken workers fail the shared budget closed until
service recreation, and whole-service close drains worker and cache cleanup even
under repeated cancellation. Worker parent-death detection exits only that owned
child. Parent catalog/file rechecks precede metadata-cache insertion.

Independent read-only review identified and the coder resolved a new arrival
joining an already canceled flight, permit reuse before broken siblings were
reaped, incomplete cancellation shielding around close, and test-helper cleanup
that could wait indefinitely after an assertion. These corrections add no weaker
verification fallback or timeout extension.

Targeted elevated Windows verification passed 45 cases in 28.96s: independent
legacy-byte differential/corruption/native-checkpoint checks, real spawned pool
and DuckDB contention, coalescing, cancellation/deadline draining, post-child
catalog/manifest/Parquet mutation rejection, killed-worker recovery and active/idle
parent-death cleanup. Eight additional exact-schema/timezone/empty/truncation cases
then passed; the final optimization collection contains 53 cases. Strict mypy
passed 48 sources and focused Ruff checks passed. Whole retained suites and actual
cold/Linux acceptance were pending at this interim record; final suite outcomes
follow below.

A development-only median ETH partition probe verified the original logical and
physical hashes for 3,538,701 rows in 6.059s wall/5.828s process CPU. The earlier
serial diagnostic took 35.967s/35.344s. These uncontrolled local filesystem-cache
observations establish a representative improvement, not the final cold-month
gate. The probe recorded 117,202,944 bytes worker-lifetime peak RSS; simultaneous
whole-application memory was not measured.

An initial restricted-process focused run displayed two failures and hung before
tracebacks. Only its exact verified pytest launcher/actual Python processes were
stopped; the process inventory is retained. Restricted process inspection could
not see the spawned Python processes, but no captured traceback established the
hang's cause. Treat that run as inconclusive, not a passing result or a proven
sandbox diagnosis. The subsequent elevated diagnostic pool run passed 11 cases
in 12.28s with no faulthandler timeout, followed by the elevated 45-case pass.
Ignored evidence is under `artifacts/verifier-opt/`, including
`focused-hang-processes.json`, `pool-diagnose.log`, `focused-elevated.log` and
`native-probe.json`. Parent-death helper's initial venv-redirector PID assumption
also failed; the corrected test records actual parent/child identities and waits
for both active and idle worker exit. Historical R6 evidence remains unchanged.

Runtime was frozen before full suites and actual acceptance as dirty execution
source `f12cf32c7a33b8b81691cebd40195a6d174cc113be4aa35190dd209ccb3e1035`,
HEAD `7e270bc9db94e2117964a3b257e559bcf69e6410`, with the unchanged lock hash
`730f02bec94d1f824a2cadf74f60cf5dcc246faa55004d5d060b92931224618f`.
The exact source archive and per-file manifest are
`artifacts/verifier-opt/frozen-source-f12cf32c7a33.{zip,json}`.

The first full offline attempt completed 528 tests but had 283 setup errors from
Windows access denial in the shared system pytest temporary directory, before
those test bodies ran. This was not a full-suite pass. The original log and
quality record remain `offline-first-temp-permission.log` and
`quality-checks-first.json`; a distinct full rerun uses a fresh owned workspace
temporary directory. No runtime change was made in response.

The full locked rerun passed 811 offline cases in 38.97s (40.138s runner time),
including all 53 optimization cases, and all 189 real PostgreSQL cases in
127.87s (129.004s runner time). Migration to head passed in 1.087s. Ruff lint,
all-file formatting and strict mypy passed. These retained suites cover R1-R6
normalization, HTTP/CLI/cache contracts, durable state/fencing/publication,
numerical results and memo compatibility; the actual cold and packaged Linux
performance/lifecycle gates are separate.

## Actual cold all-62 workflow

The first frozen-source cold acceptance passed in **272.814s** (about four minutes
33 seconds), including service/pool cleanup. The ordinary cross-asset workflow
started in a fresh process with a new BarService, zero verified versions, no
spawned workers and empty owned Redis. No BTC/ETH profile or other Parquet
verification preceded it in that process. Operating-system filesystem-cache state
was uncontrolled and was not flushed; this is application-cold acceptance.

Preparation took 270.169s, prepare-plus-submission 270.202s, durable execution
2.497s, results/summary readback 0.025s and cleanup 0.168s. Existing preparation
and attempt deadlines stayed 1800s; the measured whole-workflow result also met
the stronger 1800s total gate. The numerical run succeeded on attempt 1. R6 memo
work was atomically queued with zero attempts/calls without starting Ollama.

All 62 unique partitions and 230,311,900 trades completed full verification, with
each original manifest SHA-256, physical Parquet SHA-256, logical SHA-256 and row
count matching the pinned reference metadata. Results and summary payloads and
their hashes matched the independent retained R4 cross-asset reference exactly:

- Results: `33724830e4f00c3a7365514407cd02fcc478d8f92f32336bf968f5cf849263a6`.
- Summary: `6a2bc6c1188f6024bb5340f63ded0698fde80c6caaa1652a5ea343e0a191cf81`.

Two actual spawned workers processed the 62 partitions; peak unfinished submitted
jobs and the shared verification/DuckDB compute peak were both two. There were
zero failed/canceled verifications. Both workers were reaped, active compute was
zero and no multiprocessing children remained after close. Frozen source and
lock identities stayed unchanged throughout the run. Evidence is
`artifacts/verifier-opt/verifier-cold-first-cold.json` and its progress/log files.

Worker PID 7552 verified 32 partitions/118,380,231 rows with 199.969s summed job CPU
and 206.175s summed job wall time; lifetime peak RSS was 122,912,768 bytes. Worker
PID 36888 verified 30 partitions/111,931,669 rows with 189.922s CPU and 195.490s
summed job wall time; lifetime peak RSS was 124,076,032 bytes. Parent process CPU
over the timed workflow was 41.375s. These are separately scoped measurements:
job wall times overlap, per-worker RSS peaks are not summed, and simultaneous
whole-application peak memory remains unmeasured. The intentional two-compute
bound does not attempt to occupy all 32 logical CPUs. Native byte construction
removes the earlier Python per-row overhead while retaining exact checks.

This successful follow-up is separate from the unchanged historical R6 source's
1800s cold preparation failure and ordered profile-then-cross-asset success. It
establishes this measured bounded cold workload, not a universal hardware/cache
latency guarantee. Packaged Linux acceptance, final preservation and resource
cleanup were pending when this cold result was recorded; later outcomes follow.

## Packaged Linux and preservation

The owned no-pull/no-network-build Linux overlay passed its spawn/bar-read/lifecycle
smoke using the existing locked local image, without a Git checkout. One actual
spawned child fully verified a 1,151,908-row registered partition and its original
manifest/physical/logical hashes. Twelve five-minute bars for its first hour
matched the independent retained daily reference; the read was a Redis MISS.
Configured pool/compute limits were two, with one observed worker and compute
peak one for this single-partition smoke. Close reaped that worker and left zero
active compute/children. This tests Linux spawn/read/normal-close behavior;
Windows active/idle parent-death behavior is separately tested above.

The Linux worker recorded 1.951s job wall/1.250s CPU and 190,775,296 bytes lifetime
peak RSS. Overall Linux smoke duration and simultaneous memory were not measured.
The exact owned overlay container/image were removed after ID/label checks.
Evidence is `artifacts/verifier-opt/verifier-linux-first-linux.json` and its
build/container logs; no original image, service or dataset was modified.

Parent independent preservation compared all 257 protected dataset/numerical/memo/
configuration/migration files and found every original byte hash unchanged in
`artifacts/verifier-opt/preservation-after.json`. The final source check confirmed
the same frozen `f12cf32c7a33b8b81691cebd40195a6d174cc113be4aa35190dd209ccb3e1035`.
The separately owned PostgreSQL/Redis final snapshot and cleanup were still
pending at that preservation record; their actual outcomes follow below.

## Final owned cleanup and outcome

The final 16-table owned database snapshot is
`artifacts/verifier-opt/cold-catalog-final.json`: 62 dataset registrations, one
successful attempt-1 numerical run/result and one queued memo with zero calls.
Immutable numerical artifacts and ignored source/reference/acceptance evidence
are retained; no automatic garbage collection or deletion of original data occurs.

Ownership-checked cleanup passed in `artifacts/verifier-opt/cleanup.json`. Exact
saved PostgreSQL/Redis container IDs, names and owner labels were checked before
the containers and their anonymous volumes were removed. Port bindings had been
verified earlier by the acceptance preflight; cleanup confirmed owned ports
55440 and 56382 closed. The
Linux overlay resources and spawned workers were already removed/reaped.
Original API/PostgreSQL/Redis IDs, images, start times and restart counts stayed
unchanged with healthy containers. HTTP live/ready endpoints remained reachable
and original Redis returned PONG. Readiness preserved the same existing degraded
state: required PostgreSQL/storage up, Redis up and optional Ollama down with
ConnectError. No original-service restart or system/clock change was performed.

The first cleanup guard reported a false original-service mismatch before any
deletion: Windows PowerShell 5.1 wrapped a decoded JSON array into one nested
`System.Object[]`, whereas PowerShell 7 returned three individual objects.
The read-only `diagnose_cleanup.ps1` confirmed wrapped/direct counts 1/3 on 5.1
and 3/3 on 7, with independently unchanged service identities. The ignored
cleanup helper switched to direct array assignment; the verified rerun passed.
This was a cleanup-helper representation failure, not an actual service change.
The original failure and diagnosis remain recorded; no runtime/source fingerprint
or acceptance limit changed.

The guard diagnosis is saved in `cleanup-first-guard.json`. After successful
cleanup, all 257 protected original file hashes were compared again and remained
identical (`preservation-after.json`, 1.814s). The earlier pre-cleanup comparison
is retained separately as `preservation-after-before-cleanup.json`.

All scoped functional/performance/retained-suite gates passed. The known Docker
clock discrepancy, application-process-only concurrency scope, standard guarded
spawn startup requirement, uncontrolled OS cache and unmeasured simultaneous
application peak memory remain explicit. The measured result is not a universal
latency guarantee. Historical R5/R6 model limits and all earlier failures remain
unchanged. Independent read-only review accepted the final source/tests,
documentation and actual cold/Linux/snapshot/preservation/cleanup evidence with
no blocking finding. This authorized follow-up is complete. After
documentation-only edits, checks
passed Ruff lint, formatting (134 files), strict mypy (48 sources) and
`git diff --check`; the execution fingerprint remained frozen and unchanged.
No commit/push, hosted CI, dependencies/lock/deployment changes or R7-R9 authority
is claimed.

## Authorized publication (October 26, 2026)

The user subsequently authorized committing/pushing verified R6 and this scoped
verifier optimization, checking hosted CI, fixing actual scope-related CI failures
through coder gpt-6.1-sol/high and independent read-only reviewer
gpt-6-astra/medium, and documenting/publishing actual outcomes. This supersedes
the earlier no-commit/push restrictions for this publication scope only. R7-R9,
unrelated optimization/features, deployment and system/service/clock changes
remain unauthorized. Never include artifacts/data, archives, credentials,
environments or weights in Git.

The frozen dirty execution source, exact local measurements, all failures and
preservation/cleanup evidence remain the local acceptance record. Publication
and hosted CI outcomes are pending at this authority update. Record the exact
published SHA and observed hosted run/results here and in
[R6 verification](r6-verification.md); the local cold pass and full retained
suites do not establish a hosted CI pass.
