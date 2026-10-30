# V2 Phase 3: generalized Binance numerical research

Status: PHASE 3 LOCAL COMPLETE; INDEPENDENT CLOSEOUT REVIEW PASSED. Date: October 29, 2026
(America/New_York). This contract was written before runtime implementation.
Requirements below remain normative; observed outcomes belong in
[verification](phase-3-verification.md).

## 1. Authority and boundaries

The user approved the detailed Phase 3 proposal, contributor/roadmap updates,
pre-code design, coder `gpt-6.1-sol/high`, independent read-only reviewer
`gpt-6-astra/medium`, implementation, full local acceptance and preservation.
Resolve blocking pre-code findings before runtime changes; resolve implementation
findings before closeout. NO COMMIT OR PUSH. Preserve all historical authority and
failed invocations. [Phase 1](phase-1-contract.md), [compatibility](compatibility-matrix.md),
[acceptance](acceptance-matrix.md), [Phase 2](phase-2-ingestion.md),
[R3](../r3-analytics.md) and [R4](../r4-research.md) remain normative except this
explicit phase allocation: Phase 3 delivers numerical HTTP endpoints; Phase 4
delivers public discovery/UI/uploads; Phase 5 delivers generalized model/memos.

Deliver registered Binance spot instrument/date selection, exact bars, existing
market_profile/cross_asset/volatility_cluster research, v2 durable execution,
cache isolation, independently verified immutable outputs, CLI and numerical HTTP
adapters. Preserve all original interfaces and synthetic trades behavior.
No new workflows/formulas, forecasting, strategies, currency conversion, alternate
venues/derivatives/providers, UI/discovery/uploads, model/prompt/memo changes,
dependencies/locks, storage backend, multi-host/auth/customer quotas, scheduling,
GC, original-service configuration/rollout, purchases or unrelated system changes.
Reuse locked Python 3.13, existing SQLAlchemy/Alembic/PyArrow/DuckDB/Redis and stdlib.

## 2. Inspected source and module ownership

Read-only inspection at clean HEAD `c44ea13778b01a84721e51677bd8a7e296202bfe`
found migration head `0008_v2_ingestion`. Legacy `research/spec.py` and
`analytics/bars.py` validate January BTC/ETH; `research/numerics.py` hardcodes USDT
units; `research/store.py` owns separate legacy state; `datasets/v2/catalog.py`
provides union reads, full inspection and a SQLite selected-identity checker.
`app.py` constructs one shared BarService. These are inspected facts, not tests.

Implement v2 under `src/marketlab/analytics/v2/` and
`src/marketlab/research/v2/`, with explicit dispatch in `research_cli.py`, additive
routers/application lifecycle, revision `0009_v2_research` after `0008_v2_ingestion`,
tests and `scripts/v2_phase3_acceptance.py`. Keep legacy parser/canonicalizer,
numerical envelopes and durable tables unchanged. Reuse immutable arithmetic
helpers; any helper extraction must preserve signatures, evaluation order, old
payload bytes and tests. Prefer a v2 adapter around the existing calculation with
instrument-keyed bars and explicit unit/schema projection to copying formulas.
Do not allow a v2 spec to bypass the old public parser on legacy entry points.

## 3. Strict selection and canonical request

`research-spec-v2` has exactly schema, workflow, instrument_ids, dataset_versions,
start, end, history_start, interval, metrics, parameters and predicates. Shape,
allowlists, empty parameters and typed fixed cluster predicates are exactly R4;
only `symbols` becomes `instrument_ids` and the fixed month becomes registered
coverage. Strict UTF-8 JSON <=64 KiB rejects duplicate/unknown keys, nonfinite
values, booleans as integers, coercions and oversized/deep structures. Canonical
JSON is sorted keys, compact separators, ASCII escaping, no nonfinite values,
one terminal LF. Instrument/version/metric arrays are sorted unique sets.

Select one instrument, or exactly two distinct instruments for cross_asset, and
1..62 lowercase 64-hex registered versions. Identifiers are opaque qualified
`binance:spot:<source_symbol>` registry keys; no heuristic symbol split/aliases.
Pin one version per selected instrument and every UTC day touched by
`[history_start,end)`, including warm-up. No extra days/versions, preferred/latest
alternative, auto-download, truncation or implicit version replacement.
Both legacy and v2 catalog versions are eligible only after full artifact and
registry-semantic verification. Ambiguous hash present in both catalogs fails.
Disabled instruments remain readable/researchable using retained versions;
disable prevents new ingestion, not numerical readback. Missing registry mapping
or semantic mismatch fails closed. Cross_asset requires exact equal quote codes;
USD != USDT and no peg assumption/conversion follows.

Times require explicit UTC Z/+00:00 and exact five-minute alignment. Require
1970-01-01 <= history_start < start < end <= 9999-12-31; last touched day is at
most 9999-12-30. Use integer timedelta arithmetic, never float epoch conversion.
No new future-day assertion overrides already registered observed-only data.
At most 17,856 expected five-minute buckets across instruments including warm-up;
reject excessive ranges before expanding dates. Profile/comparison require at
least 12 preceding bars; clusters at least 300. Actual calculation must establish
R4 contiguous/valid warm-up eligibility before durable acceptance; a requested
duration alone is insufficient. Registered days and observed buckets remain
different facts. Missing evaluation buckets remain missing.

## 4. Snapshot identity preparation and bounded execution

Integrate Phase 2 identity checking into numerical preparation rather than
trusting caller versions or checking only the requested evaluation interval.
Verify all selected daily versions, including rows outside the requested time
slice. Trade identity is `(instrument_id,numeric source_trade_id)`. Canonical
payload equality includes UTC microsecond timestamp, all three exact decimal
fields and nullable flags. Conflicting repeated identities fail 409. Agreeing
identities contribute exactly once. Different instruments never collide. Since
verified daily rows belong to their declared UTC day and only one alternative per
day is selected, an agreeing identity across different selected days cannot
normally occur; still define dedup explicitly and test its primitive.

After full integrity verification proves each version's strict numeric ID order,
obtain actual first/last numeric IDs from that verified content. Inclusive ID
ranges for the same instrument that are disjoint prove absence of repeated IDs;
skip per-row identity insertion only for those proven disjoint ranges. Bind the
proof to the complete catalog identity, manifest hash, artifact hash and file
signature (size, mtime_ns, ctime_ns, inode), and recheck that binding before use.
Neither unverified Parquet statistics nor a cached version ID alone is proof.
Any changed binding requires full re-verification. Cross-instrument ranges never
participate in this comparison.

For overlapping ranges, use a bounded merge of verified sorted numeric ID streams
with exact canonical payload comparison on equal IDs, or owned SQLite scratch,
one instrument at a time. SQLite uses numeric ID primary key, 32-byte payload hash
and bounded source locators; matching hash/ID still requires exact original
canonical payload comparison. Stream Parquet batches <=16,384 rows; bound total
active merge buffers independently of stream count and never collect all trades.
SQLite cache is <=8 MiB, temp_store=FILE, journal_mode=OFF for disposable scratch,
max_page_count set before inserts; total selection scratch (DB/temp) is hard capped
at 20 GiB. A progress handler and batch checkpoints check cancellation/deadline;
release resources only after workers drain. Duplicate scans and the range fast
path cannot bypass full integrity verification, row or scratch bounds. Test
inclusive touching/overlapping/sparse ranges, poisoned/stale proof caches and exact
payload conflict handling against the full bounded checker.

Preparation and every worker attempt reserve 20 GiB scratch plus 2 GiB DuckDB
spill plus 34 MiB output/control headroom before expensive work, with actual
free-byte checks on every distinct filesystem. Ingestion and research share the
existing exact `v2-space:<str(root.resolve())>` advisory-lock identity, acquired
through the same Phase 2 lock function on the same database. Under that lock,
admission must include unconsumed reservations in BOTH `v2_storage_reservations`
and `v2_research_reservations`, attributed to each measured filesystem, before
adding a new charge. Actual retained bytes already reduce filesystem free space;
do not subtract those bytes twice or drop any outstanding conservative reservation.
Normalize filesystem/root identity consistently and fail closed if the configured
root/filesystem cannot be reconciled with retained ledger paths. Lock all capacity
creation/reconciliation/release decisions using this common identity; no independent
research-only capacity lock may admit work beside ingestion. Scratch and spill
have distinct sublimits; require measured capacity for their sum. Retain charges
for crashed/failed leftover bytes until exact owned cleanup/reconciliation;
terminal state alone does not refund storage. Sequential instruments may reuse
scratch only after verified drain/removal. No production limit reduction to pass.

This approval includes the narrowly necessary Phase 2 reservation integration:
its existing admission helper must observe outstanding Phase 3 reservations under
the same lock, and Phase 3 admission observes Phase 2 reservations. Preserve all
Phase 2 ceilings, retained-byte accounting, owner/path checks and conservative
crash charges; no reset, refund, bypass or general ingestion refactor is authorized.
Support the pre-0009 schema explicitly without silently ignoring a missing ledger
after the new migration is expected. Add real concurrent ingestion/research
admission regressions in both ordering directions and retained-failure scenarios.

Share the application's existing two-compute-permit budget between legacy and v2
verification, snapshot scans and DuckDB work; do not create additive private pools.
Acquire one permit per active snapshot scan/SQL operation, one-second admission,
bounded pending work; avoid holding one permit while waiting for nested permits.
One active numerical attempt per worker instance. DuckDB retains one thread,
512 MiB memory setting, 2 GiB private spill and 60s actual query deadline.
Memory settings are not an RSS claim. Bars remain chunked to <=1,440 buckets and
five touched partitions. Preparation has a 1,800s total monotonic deadline;
each admitted attempt has its own 1,800s deadline including revalidation/output.
Cancellation signals and interrupts actual work, drains it and removes only
owned transient files before capacity release. No immediate TCP-disconnect
cancellation guarantee follows; explicit durable cancellation is authoritative.

## 5. Bars and numerical output semantics

V2 bars select instrument_id, repeated version, interval 1m/5m, UTC aligned
start/end; 1..5 versions, <=5 touched daily partitions, <=1,440 expected buckets.
Request coverage is exact for `[start,end)`. Verification and snapshot checks occur
before cache access. Use fixed bound SQL/trusted registered paths, disable external
access/extensions as R3, compare IDs numerically even when v2 stores text.
OHLC ties use `(executed_at,numeric source_trade_id)`; sums, supplied quote quantity,
overflow rejection and VWAP rounding remain exact R3. Empty buckets are omitted.

Keep all R4 Decimal80 arithmetic, ROUND_HALF_EVEN, chronological order, final
18-place serialization, normalized negative zero, observations/null reasons,
fixed cluster thresholds/predicates, warm-up exclusion and gap behavior. No float
fallback/fill/lookahead. Lexically sorted instrument IDs define the first-minus-
second comparison order; output explicitly records that order. Price and quote
volume units use pinned quote code; base volumes use pinned base code; ratios
remain dimensionless. Never derive asset codes from symbol spelling.

Use new definitions `bars-v2`, `research-numerics-v2`, `research-results-v2`,
`research-summary-v2`, `research-manifest-v2`. V2 envelopes contain instrument IDs,
units, pinned metadata/semantic hashes, versions and observed-only coverage.
Results/summary retain all R4 field meanings. A documented legacy projection
maps qualified BTC/ETH IDs to old symbols and removes only new metadata/provenance
and schema labels before comparing every value/count/null/bound. Legacy execution
still requires exact original payload hashes; v2 bytes need not share old hashes.

Cache keys bind schema/definition, canonical request, instrument semantic hashes,
selected dataset and manifest hashes, units and numerical execution contract.
Use existing validated cache-v1 envelope, 1 MiB cap, bar TTL 810..990s, summary
3240..3960s, 100ms command/connect timeout, no retries, three-failure/10s breaker,
bounded coalescing/labels and HIT/MISS/BYPASS meanings. Integrity checks precede
hits. Cache corruption/miss/eviction/outage cannot change numerical output or
prevent manual execution/readback. No cache population before verified completion.

## 6. Concrete forward schema

Revision `0009_v2_research` adds only the following tables; never edit prior DDL.
All hashes are varchar(64) CHECK lowercase hex; IDs/owners are UUID; timestamps
are timestamptz from database clock_timestamp(). JSON text stores canonical bytes,
with byte-size and valid-object checks enforced at registration and readback.

* `v2_research_submissions`: submission_id PK; idempotency_key varchar(128) UNIQUE
  CHECK ASCII `[A-Za-z0-9_.-]{1,128}`; request_sha256; spec_json text <=65,536
  bytes; contract varchar(48) CHECK research-spec-v2; fingerprint_json text
  <=131,072 bytes; fingerprint_sha256, execution_sha256, lock_sha256; created_at.
* `v2_research_selections`: submission_id FK submissions; instrument_id and
  semantic_sha256 composite FK v2_instruments; trade_date CHECK supported range;
  dataset_version_id hash; legacy_version_id nullable FK dataset_versions;
  v2_version_id nullable FK v2_dataset_versions; manifest_sha256; metadata_json
  text <=4,096 bytes; PK(submission_id,instrument_id,trade_date);
  UNIQUE(submission_id,dataset_version_id). Exactly one catalog FK is nonnull and
  equals dataset_version_id. Enforce 1..62 children and selected instrument/day
  equality atomically during registration, never via an unlocked count.
* `v2_research_runs`: run_id PK; submission_id UNIQUE FK submissions; state
  queued/running/retry_wait/succeeded/failed/cancelled; revision bigint >=0;
  attempt_count integer 0..3; fencing_token bigint >=0; owner/lease_until;
  eligible_at; cancel_requested boolean; result_id nullable UNIQUE;
  error_code varchar(64) allowlisted or null; created_at/updated_at.
  Owner and lease exist iff running. Succeeded iff result_id is nonnull;
  result_id must equal run_id and reference v2_research_results(run_id) through
  an initially deferred FK. Terminal cancelled requires cancel_requested=true.
* `v2_research_attempts`: run_id FK runs; attempt_number 1..3;
  fencing_token >0; owner; started_at/ended_at; outcome
  running/succeeded/transient/permanent/expired/cancelled; nullable error_code;
  PK(run_id,attempt_number), UNIQUE(run_id,fencing_token). Running iff no ended_at.
* `v2_research_results`: run_id PK/FK runs; manifest_relative_path UNIQUE safe
  relative text; manifest_sha256, results_sha256, summary_sha256; result_bytes and
  summary_bytes each 1..16 MiB; registered_at. Insert/read-only published rows.
* `v2_research_operations`: operation CHECK cancel, protocol CHECK research-spec-v2,
  idempotency_key same grammar, request_sha256, run_id FK runs, response_json text
  <=65,536 bytes, created_at; PK(operation,protocol,idempotency_key).
* `v2_research_reservations`: reservation_id PK; nullable run_id FK runs;
  owner UUID; purpose CHECK preparation/attempt; state CHECK active/retained/released;
  scratch_bytes/spill_bytes/output_bytes nonnegative bigint; safe relative root
  UNIQUE; created_at/updated_at; nullable released_at. Released iff released_at
  nonnull and all charges zero. No automatic release on lease expiry.

Index runs(state,eligible_at,created_at,run_id),
runs(state,lease_until,run_id), submissions(execution_sha256,created_at),
selections(dataset_version_id), attempts(run_id,started_at), and
reservations(state,reservation_id). Enforce success/result/attempt and selection
invariants inside bounded transactions; FK cycle is deferred only for atomic
success insertion. Application roles do not expose arbitrary mutation interfaces.

Rehearse fresh and populated upgrade against copied owned DBs, compare original
rows/CHECKs and verify dumps by isolated restore. Forward-only: no destructive
downgrade or original-service migration. Disable v2 intake without deleting tables.

## 7. Durable protocol and publication

Creation parses/canonicalizes, checks same-key replay before expensive work, fully
prepares new requests, then uses a namespaced advisory transaction lock to insert
submission, selected snapshots and one queued run atomically. Replay returns the
original run and captured fingerprint even after labels/source change; conflicting
key request is 409. Concurrent preparation losers release only verified owned
temporary resources. Fingerprint includes exact source/lock/protocol and ordered
dataset/manifest/metadata snapshots, never a newly selected alternative.

V2 execution source fingerprint covers sorted relative paths/SHA256 for all
`src/marketlab/**/*.py` plus uv.lock, with a versioned inventory algorithm.
Git revision/dirty overlay are honest provenance; exact source/lock identity is
the compatibility gate. Workers recompute before claim, require exact persisted
execution identity and skip/reject incompatible work without spending attempts.
Lazy provenance capture permits packaged startup and historical reads without Git.

Package provenance clarification after the observed owned-image acceptance
failure: v2 execution independently requires a complete readable sorted Python
source inventory and readable uv.lock. Missing/unreadable required source/lock
fails closed with a safe unavailable error before durable acceptance/claim.
Git is optional descriptive provenance: capture real revision/dirty state when
available; otherwise record null revision/dirty, explicit unavailable state and
a bounded reason. Never invent a clean revision or let Git availability alter
source/lock/schema/numerics/bars/inventory compatibility. Host/package workers
with identical source/lock bytes retain the submitted provenance while executing;
incompatible queued work still spends no attempt. Legacy `_build` behavior and
legacy execution contracts remain unchanged. Rebuilt actual no-Git package and
fresh current-source acceptance are mandatory before closeout.

Claim uses SKIP LOCKED and DB time, queued work immediately due, retries due by
eligible_at, expired leases reclaimable. Lock order is run row, run advisory lock,
result row; cancellation follows run row then operation advisory lock. Reservation
transactions use the common `v2-space:<str(root.resolve())>` capacity advisory
lock described above and never wait for run rows;
acquire reservations before claim or outside run-lock transactions. Recheck run
ownership after reservation; release unused ownership only after cleanup. Use
10s lock and 15s statement/idle-transaction timeouts. No full file reads under locks.
Every durable run transition increments revision; heartbeat renews ownership
without revision change. Lease 60s, heartbeat 10s on separate connection,
monotonic fencing, three attempts including crashes. Retry waits 10s then 30s for
narrow transient catalog/timeout/capacity failures; validation/integrity/arithmetic/
unknown failures are terminal. No refunded attempts or hidden inner retries.

Cancel requires strict `{expected_revision:<nonnegative integer>}` and operation
key. Queued/retry work cancels immediately; running work records request and
increments revision, signals cooperative drain, then transitions cancelled under
fence. Publication rechecks cancellation while holding run lock: accepted cancel
prevents success; already committed success/failed returns 409. Exact operation
replay returns original outcome; cancelled fresh request returns current cancelled
state only with matching revision. Cancellation never creates another run.

Stage spec/results/summary/manifest under unique attempt-owned roots; each result
and summary <=16 MiB, spec <=64 KiB, manifest <=1 MiB. Hash/readback all artifacts,
flush/fsync and perform full staging or existing-orphan verification outside the
publication transaction. THEN acquire the bounded run-row lock and namespaced
run advisory lock, recheck the current token/owner/live lease and cancellation
flag, and only after those checks rename immutable staging to
`research-v2/<run_id>` or adopt the previously verified identical orphan. Recheck
the verified path/signature binding without full reads under lock; if an unexpected
destination appeared or changed, abort and verify outside the transaction before
retrying. Register the result and mark attempt/run success atomically in this
same transaction. A stale/cancelled worker must never rename or adopt an artifact
after losing the fence. Orphan after a fenced rename/before commit remains
undiscoverable; compatible retry fully verifies and adopts identical
request/fingerprint artifacts without overwrite. Divergent/corrupt orphan fails.
Add a race that pauses a worker immediately before the publication lock/rename,
lets its lease expire or cancellation win, then resumes it; zero filesystem or
database publication by that stale worker is required. Published reads verify registered
manifest and all artifacts before serving; source/model availability is irrelevant.
No GC, deletion of original artifacts, storage migration or power-loss guarantee.

## 8. Interfaces and errors

Only numerical endpoints are added: GET `/v2/bars`, POST `/v2/research/runs`, GET
`/v2/research/runs/{id}`, `/{id}/results`, `/{id}/summary`, POST `/{id}/cancel`.
Use strict media/body limits, existing local origin protection and safe Phase 1
error envelope `{error:{code,message,request_id}}`. Fixed allowlisted codes include
invalid_request, coverage_gap, revision_conflict, unsupported_source,
integrity_failure, capacity_exceeded, incompatible_execution, not_found,
not_ready, cancelled, deadline_exceeded and unavailable. Never echo raw SQL,
paths, credentials, source rows, metadata or arbitrary exceptions.

GET success 200; create 201 `{id,state,replayed:false}`, replay 200/replayed=true;
validation 422, unsupported media 415, oversized control 413, absent resource 404,
state/key/coverage/identity conflict 409, admission 429 with bounded Retry-After,
catalog/storage unavailable 503, actual deadline 504. Status returns revision,
state/attempts, safe error, pinned spec/fingerprint and numerical availability;
memo availability is false with unsupported contract, never a v2 memo job.

`python -m marketlab.research_cli v2` adds submit --spec FILE --key KEY,
worker --max-runs 1..62 [--run ID] [--wait-seconds 0..3600], inspect/results/summary
--run ID, cancel --run ID --expected-revision N --key KEY, and bars --instrument ID
--version HASH (repeat) --interval 1m|5m --start UTC --end UTC. CLI stdout is safe
JSON, stderr fixed errors; exit 0 command success, 2 syntax/validation,
1 operational/conflict failure. Worker exit 0 is not a claim that every run
succeeded: inspect durable state. SIGINT/SIGTERM stop new claims and drain work.

## 9. Frozen acceptance and evidence

Before first actual operation, capture fresh source/dirty inventory, all protected
hashes, five original/README container fields/images/mounts/start/restarts/health
and endpoints, owned resource ledger and retained input identities. Parent owns
initial snapshots under ignored `artifacts/v2-phase3-20261029`; no credentials in
tracked docs. Reuse retained data read-only or verified copies in owned roots.
Keep every invocation with UTC/monotonic timing, source/lock/protocol, commands,
expected/actual counts/hashes, resources and failure; never replace a failed pass.

Freeze deterministic request/reference fixture bytes and hash inventory before
scored actual calculation. New oracle code must use independent streaming Decimal
arithmetic and cannot import production bars/numerics or derive its expected values
from production responses. R4 reference reuse is allowed only after confirming
its independence. Fixed campaigns:

1. P3-01: all 62 retained January versions, BTC/ETH profile plus cross_asset
   Jan 1 01:00..Feb 1 with Jan 1 history; BTC/ETH clusters Jan 2 01:00..Feb 1
   with Jan 1 history. All five v1 result/summary hashes exact to retained
   reference; five v2 projections compare every value/count/null/bound. Fresh-key
   repeats retain deterministic numerical content.
2. P3-02: verified BTCUSDT Feb 1 and SOLUSDT Mar 1 actual data; SOL official/CSV/
   Parquet each produce identical projected bars/research numerical content with
   distinct pinned identities/provenance. Add only approved BTCUSDT and SOLUSDT
   Feb 28, Mar 1, Mar 2 (six instrument/day partitions), reusing already verified
   SOL Mar 1 where available. Actual profile/comparison evaluation Mar 1
   01:00..Mar 3 with Feb 28 00:00 history; clusters Mar 1 01:00..Mar 3 with
   Feb 28 00:00 history. Single-day BTC Feb 1/SOL Mar 1 profile evaluation
   01:00..next midnight, history midnight. Independently reconcile every 1m/5m
   bar and selected workflow field. Missing required official archive blocks;
   no unreviewed replacement dates/provider. No arbitrary new instrument campaign.
3. P3-02/03 fixtures: numeric ID 2/10 timestamp ties, shuffled batches, sparse
   days and cross-day edges, exact decimal rounding/overflow, no missing-bar fill,
   warm-up gaps/eligibility, equal quote and USD/USDT mismatch, same IDs across
   instruments, disagreeing repeated IDs, explicit alternatives, label changes,
   disabled retained instruments, mismatched/unregistered versions, invalid media/
   fields/alignment/predicates, exactly/one-over partition/bucket/output bounds.
4. P3-04: actual Redis MISS/HIT/corruption/eviction/outage/recovery; semantic/
   instrument/dataset/schema cache isolation; actual PostgreSQL concurrent
   creation/claims, real-time lease/retry/third-crash exhaustion, incompatible
   worker and cancellation races, including a stale worker immediately before
   fenced rename, plus concurrent Phase 2 ingestion/Phase 3 research capacity
   admission under their shared lock with conservative retained charges.
   Native process kills at (a) claimed before
   preparation, (b) snapshot scan active, (c) numerical calculation active,
   (d) staged verified artifacts, (e) rename before DB commit, (f) committed
   success before response. Harness-only failpoints, normal worker recovery,
   no production sleeps/lease shortening/state forcing. Verify no stale success,
   partial visibility, orphan overwrite, duplicate result or refunded charge.
5. P3-05: fresh owned cold all-62 through unchanged legacy research/memo path,
   total including full verification/worker drain <1800s, 230,311,900 trades,
   exact retained hashes, one numerical attempt; memo queued with zero calls.
   No v2 memo requirement, actual model campaign or inference.

Run final-source locked full offline, real PostgreSQL, Ruff/format/mypy, package/
Docker/API/CLI/Redis outage/live legacy and frontend component/build/browser
regressions applicable to app integration. Record historical-input skips separately.
Current-source actual numerical/cache/crash evidence is mandatory; mocks and old
passes cannot replace it. Measure memory only with sampling interval/process
coverage; otherwise label unmeasured. Controlled lower resource fixtures are
distinct from unchanged actual production bounds.

## 10. Closeout and completion rule

Retain verified database dumps and isolated restore receipts for every owned
source DB before cleanup. Compare all original rows/CHECKs and protected artifacts;
all captured service fields/endpoints must match for the observed interval.
Inspect exact resource labels/IDs/process command lines and resolved owned paths
before cleanup. Preserve raw inputs/evidence, original services/images and weights;
no broad prune, local/system cleanup or inferred cleanup from absent processes.
Reconcile owned processes/ports/containers/volumes/networks/images/reservations,
retain failed byte charges when bytes remain and document limits honestly.

Complete only after every mandatory gate passes on final source, independent
read-only review has no unresolved blocking finding, backups/preservation and
owned cleanup verify. Missing prerequisite/failure leaves Phase 3 incomplete.
Append actual outcomes in verification and usage/status docs; historical failed
invocations, uptime/clock/cache/cancellation/resource limits remain intact.
No commit/push, hosted result, original-service rollout or Phase 4 authority follows.
