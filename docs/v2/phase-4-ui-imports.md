# V2 Phase 4: metadata-driven browser research and Binance imports

The October 31, 2026 [completion amendment](phase-4-completion.md) governs
remaining work and supersedes conflicting acceptance/harness/closeout provisions
in this historical pre-code contract. Product, accounting, compatibility, and
resource-limit requirements remain preserved. Actual outcomes remain in
[verification](phase-4-verification.md).

Status: PRE-CODE CONTRACT RECORD. Its initial review-pending checkpoint is
historical; independent pre-code rereview passed before runtime implementation,
as recorded in [verification](phase-4-verification.md#pre-code-rereview-and-immutable-contract-checkpoint).
Date: October 30, 2026 (America/New_York). This contract preceded Phase 4 runtime
edits; the original frozen bytes and review history remain retained. Requirements
remain normative. Actual outcomes belong in
[verification](phase-4-verification.md); no acceptance is claimed here.

## 1. Authority, delivery, and preservation

The user approved the detailed Phase 4 proposal and explicitly authorized updating
AGENTS.md/ROADMAP_v2.md, writing this contract before code, then implementation
through coder `gpt-6.1-sol/high` followed by independent read-only reviewer
`gpt-6-astra/medium`. Resolve blocking pre-code decisions before implementation;
resolve implementation findings before closeout. NO COMMIT OR PUSH.

Deliver a local browser flow: discovery -> official ingestion or canonical upload
-> durable status -> catalog -> explicit daily-version selection -> the existing
three numerical workflows -> charts, results, and provenance. Reuse Phase 2/3
services and durable workers. Public HTTP means a supported local application
interface, not authenticated Internet or customer deployment.

[Phase 1](phase-1-contract.md), [Phase 2](phase-2-ingestion.md),
[Phase 3](phase-3-research.md), [compatibility](compatibility-matrix.md), and
[acceptance](acceptance-matrix.md) remain normative. This contract activates their
Phase 4 interfaces and local admission ceilings only. Preserve all legacy API/CLI
shapes, exact outputs/artifacts/readers, formulas, cache isolation, source/lock
compatibility, failed invocations, and published CI history. Preserve independent
synthetic `/trades`, historical reports, and captured media; the README GIF stays
byte-exact. Label retained examples accurately instead of regenerating media.

No Phase 5 model/prompt/memo change, new workflow, dependency/lock change, other
venue/market/provider, object storage, multiple hosts, authentication/customer
isolation, scheduling, automatic GC, arbitrary column mapping, currency conversion,
original-service rollout, purchase, or unrelated system repair is authorized.
Use existing locked Python 3.13 and frontend dependencies. A mandatory requirement
unmet by them is a blocker requiring a prospective scoped amendment.

## 2. Local access and narrow HTTP adapters

Reuse `workspace.local_mutation` and the deployed local stack's fixed same-origin
API routes for every mutation, including raw PUT. Reject disallowed Origin and
Fetch Metadata before token claim or reading body/storage. Preserve existing
origin-less trusted local CLI behavior only where the existing local policy
permits it; browser UI always uses the same origin. No arbitrary origin CORS.
All access in local mode has the same stack-operator authority. No per-user
identity or authenticated creator/role guarantee is asserted; Phase 8 supplies
that. Capabilities explicitly report `auth_mode=local` and `storage_mode=local`.
An import capability additionally narrows byte upload to one import/generation;
it never grants catalog/storage reads, listing, deletion, or arbitrary paths.

Strict control JSON <=64 KiB rejects duplicate/unknown keys, nonfinite values,
coercions and booleans as integers. Preserve existing idempotency grammar and
canonical encoding. Mutations require Idempotency-Key except raw one-use PUT.
Dates/times/decimals/counts obey Phase 1/2/3; serialize exact counts and decimal
strings without floating-point loss. Request/query allowlists reject duplicates.

| Endpoint | Delivery |
| --- | --- |
| GET /v2/capabilities | Versioned schema/hash, implemented formats/adapters/workflows/intervals, effective named limits, local modes; Phase 5 functions unavailable |
| GET /v2/instruments and /{instrument_id} | Bounded registry metadata/readability/enabled state; venue/base/quote filters |
| POST /v2/instruments | Existing strict registration service; verified operator-supplied Binance symbol/base/quote metadata, no symbol splitting |
| PATCH /v2/instruments/{id} | Only display_name/enabled plus expected_revision; immutable semantic fields cannot change |
| GET /v2/datasets and /{version} | Bounded union catalog, instrument/day filters, provenance, verified detail/readability; ambiguous cross-catalog identity fails closed |
| GET /v2/coverage | One instrument, explicit [from_date,before_date) <=62 days; bounded alternatives/gaps, completeness-qualified observed bounds and observed_only disclaimer |
| POST /v2/ingestion/submissions | Existing daily-ingestion-v2 service, 1..2 instruments, <=62 Cartesian children |
| GET /v2/ingestion/submissions/{id} | Bounded child/attempt status, safe errors, counters and published versions |
| POST /v2/jobs/{id}/cancel | Existing revision-checked durable cancellation |
| POST /v2/imports | Exact {manifest,content_length}; reserve bytes/slot, create generation and upload capability |
| PUT /v2/imports/{id}/content | Exclusive exact-size API-proxied raw upload; never multipart form data |
| POST /v2/imports/{id}/upload | Exact {expected_revision}; explicit allowed renewal with fresh generation/reservation |
| POST /v2/imports/{id}/finalize | Exact {expected_revision,generation}; verified immutable source -> one durable job |
| POST /v2/imports/{id}/cancel | Exact {expected_revision}; cancel/drain transport or delegate linked job cancellation |
| GET /v2/imports/{id} | Revision/state, declared/received bytes, source hash, safe error, nullable job/submission/version; no upload token or paths |

Existing Phase 3 bars/run/status/results/summary/cancel adapters remain their exact
protocol. No v2 copilot/memo endpoints or implicit model dispatch are introduced.
Lists default 25/max100 with filter/endpoint/order-bound opaque cursors <=2048
bytes; current-committed traversal is not a snapshot. Do not scan all catalog
pages to calculate UI summaries. Coverage and status counts remain bounded.

Coverage retains the existing Phase 2 per-day shape: versions has at most 100
items, next_cursor identifies further alternatives, and observed_bounds_complete
is false with null aggregate observed bounds while incomplete. Continue that
day through GET /v2/datasets with the exact instrument/from/before filter and its
cursor. Before reading any manifests, one bounded SQL preflight selects at most
1,001 alternative identities across the requested <=62-day interval. More than
1,000 returns fixed `coverage_too_dense` 422 with no partial coverage response;
the user narrows the interval and/or explicitly pins from paginated datasets.
This does not reject the registered datasets themselves. Never silently truncate
alternatives, infer a gap or unique default from an incomplete page, or recursively
load every page. Recheck selected versions/actual coverage through the existing
Phase 3 snapshot preparation because current-committed pages are not a snapshot.

Use fixed safe error envelope `{error:{code,message,request_id}}`, never raw SQL,
paths, records, tokens, metadata, or exception messages. GET 200; durable create
201; same-key replay 200; invalid 422; unsupported media 415; oversized 413;
missing 404; revision/key/state/coverage conflict 409; admission 429 with bounded
Retry-After; catalog/storage unavailable 503; deadline 504; local origin denial
403. Preserve legacy error behavior on legacy routes.

## 3. Browser transport and canonical inputs

Accept exactly the canonical Binance-origin trade schema and manifest defined by
Phase 2: supplied quote quantity, numeric original IDs, exact decimal/timestamp
rules, one instrument/day/file, CSV or Parquet, retained source/conversion
provenance. No OHLCV-only inputs, metadata inference, non-Binance aliases,
derivatives, quote derivation, arbitrary table or column mapping. Source references
are inert provenance and never server fetch destinations. Caller-declared origin
is not independent authenticity evidence. Worker independently verifies staged
source and fully normalizes before registration.

Browser uses incremental SHA-256 in a dedicated worker over File.slice chunks
<=1 MiB, implementing standard SHA-256 with fixed-size state and a small chunk
buffer. Do not call SubtleCrypto.digest on a whole multi-GiB file or buffer it in
React memory. Validate against standard vectors and independent native hashes,
including chunk boundaries, empty input, the 4 GiB length-counter boundary and
cancellation.
Read no trade rows into DOM or logs. UI remains responsive during hashing.

Upload uses XMLHttpRequest.send(File/Blob) with known exact size, no request-body
ReadableStream, FormData, base64 or manual Content-Length. The browser supplies
Content-Length; scripts must not try to set that forbidden header. The generated
required_headers describe content type and import capability; create response also
declares the expected length. Raw API requires one valid nonduplicated decimal
Content-Length equal to the manifest length, rejects transfer ambiguity before
opening storage, and checks actual stream length/hash. Test real browser wire
behavior in all three engines before accepting the transport design; absence of
the required length is a blocker, never permission to accept unbounded chunks.

UI distinguishes hashing, transport progress, verified upload, queued/running
normalization and published dataset. Display safe actionable errors with request
ID, allowed renewal/reselection/cancel actions, and quota versus workload context.
Transport completion alone never means import success. File must be reselected
after refresh/interruption; status lookup remains durable. Store only operation
keys/resource IDs/revisions in browser persistence; keep capabilities in memory.
No persistent file handles or background auto-retry. Duplicate clicks reuse the
same operation key; changed input creates a new key.

Provide tracked canonical schema/CSV-header documentation and a deterministic
Parquet example-generation procedure. Generated data and sample conversions stay
under ignored artifacts. Explain Binance origin, supplied quote quantity, exact
UTC/day, and provenance requirements before upload.

## 4. Upload lifecycle, fencing and idempotency

Browser states are awaiting_upload -> uploading -> uploaded -> queued -> running
-> succeeded/failed/cancelled, with retry_wait for existing durable job retries.
Transport error/hash mismatch/lease expiry yields upload_failed; normalization
failure after finalize is terminal failed. Renewal only from upload_failed or
awaiting_upload with expired generation; never while its upload lease is live,
after uploaded/finalize or terminal. CLI keeps its existing staging -> queued
lifecycle and does not gain renewal/resume semantics.

Create captures immutable manifest, exact length/hash and instrument semantics;
revision starts 0. Capability expires in 15 minutes, uses >=256 random bits, and
is scoped to import/generation. Raw token is private and disclosed only in valid
issuance/replay responses; normal status/logs never contain it. Store only a token
hash for claim comparison and retain the original issuance response in the
private operation record for exact local replay; do not log that record. Creation
replay returns the original generation/expiry and cannot extend access or restore
a retired capability. Tokens must be compared in constant time.

PUT atomically checks token/expiry/current generation, claims exactly once and
sets owner/60s database-time lease, incrementing revision. Independent 10s owner
heartbeat renews it. Every post-claim replay/concurrent PUT returns 409 before
writing any bytes. Open one exclusive server-generated root-contained file; no
symlinks/traversal/client filenames/overwrites. Stream bounded chunks <=1 MiB;
never write bytes beyond declared length. Persist conservative charge before
acknowledging bytes; a write/accounting crash can overcharge but never undercharge.
Stop on disconnect, inactivity >30s, cancellation or ownership loss. Bounded I/O
must not block the ASGI event loop or starve heartbeat/other requests.

After exact length/SHA256, flush/fsync and verify path binding outside DB locks;
under import lock recheck live owner/generation/cancellation and commit uploaded,
clear lease and increment revision. A stale stream can never mark uploaded or
enqueue work. Failure retires generation and retains its bytes/charges. Native
crash recovery marks upload_failed after actual lease expiry without state forcing.
Expiry itself deletes no bytes. Recovery does not reopen/reuse a partial file.

Renewal locks import, checks revision/state/expiry, reserves the full new declared
length while every old generation remains charged, then records a fresh UUID,
path/token/expiry and awaiting_upload revision. Finalize verifies the current
uploaded immutable generation outside locks; inside import lock rechecks revision,
hash/size/path signature and inserts exactly one canonical submission/job using
existing Phase 2 publication/worker services. Wrong or partial bytes fail. Same-key
lost-response replay returns its original outcome even after later revisions;
conflicting reuse is 409. No source recopy is required if ownership is safely
transferred into the same staged generation; never double-count retained source.

Cancel/finalize serialize under import row. Before finalize, cancel invalidates
generation, signals/drains any stream and prevents upload/finalize success. After
finalize, use the existing import->job cancellation/publication boundary with no
second contradictory state machine. Terminal success/failed returns 409;
cancelled exact operation replay returns 200. Every durable state projection
increments import revision; heartbeat does not. Lock ordering remains import ->
job -> version; never acquire import after job. Full artifact I/O is outside short
transactions. No UI disconnect guarantee substitutes for durable cancellation.

## 5. Additive migration and accounting

Forward revision `0010_v2_browser_imports` follows `0009_v2_research`. Never edit
historical migrations. Extend only v2 import CHECKs/columns to support browser
states and distinguish transport `cli` (existing default) from `browser`; retain
all old row values and exact CLI behavior. Existing state/owner CHECKs must cover
owner+lease iff staging or uploading, with transport-specific state constraints.
Identify exact existing v2 constraints by catalog definitions before replacing
them; do not broadly drop checks or rely on guessed generated names.
Add generation history and admission rows; do not replace existing ledgers.

`v2_upload_generations`: generation UUID PK, import FK, immutable ordinal/relative
path UNIQUE, token hash, issuance/expiry DB timestamps, owner/lease, declared and
charged/received bytes, source hash, state issued/claimed/uploaded/failed/retired/
cancelled, source reservation FK UNIQUE, created/updated timestamps. Bound hashes,
states, nonnegative bytes<=declared<=4 GiB, valid owner/lease combinations, unique
(import,ordinal), immutable generation identity. Current generation is the import's
existing generation_id; finalized generation cannot be replaced. Private issuance
replay data uses bounded existing v2_operations, never normal status responses.
Index import/generation and state/lease/expiry. Missing/malformed ledger fails
closed. No foreign-key cascade cleanup.
Existing source accounting currently addresses every source row by import_id;
browser accounting must use exact generation/reservation identity so renewal
never rewrites/refunds an older source reservation. Preserve CLI single-generation
accounting and verify mixed CLI/browser populated upgrades.

Add a per-root local admission ledger keyed by exact normalized capacity root,
with bounded claims for staged-upload slots and active v2 ingestion/research
attempt slots. Slot identity binds exact import/generation or job/run/attempt,
owner and fencing identity. Acquire/release through the existing exact
`v2-space:<str(capacity_root(root))>` advisory transaction lock. Existing CLI and
browser canonical staging share four staged slots; slots end only on verified
transport drain/finalize/failure, not capability expiry alone. Queued jobs consume
no running slot. Both Phase 2 and Phase 3 v2 claim paths share eight running slots;
incompatible or capacity-waiting jobs spend no attempt. Heartbeats/leases/fencing
and three-attempt rules stay unchanged. Retained bytes remain charged after a
slot is safely released. No lease-only release while an owned process still runs.
An expired ownership lease alone is not proof of native-process drain. Hold an
unresolved slot conservatively until exact prior owned execution drains or its
death is verified. Stale workers stop on fence loss and cannot continue unaccounted
native work. Recovery waits for capacity without refunded/additional attempts.
Test bounded cooperative drain and unknown-owner fail-closed behavior; database
fencing alone is not an RSS/process cap.

Each ticket persists root-binding UUID, host and OS boot identity, PID plus native
creation/birth value, exact resolved executable, process role, random execution
nonce, owner, generation or job/run identity, prospective attempt/fence and state
pending/active/draining/released. Persist a verified self-identity before any file
writer or native numerical operation starts; unverified native identity rejects
admission. Worker subprocesses that can outlive their parent need separately
bound child identities and count/drain coverage, never parent-PID assumptions.
The API upload role binds its exact API process and generation owner.

Under root lock allocate a pending slot without work-row locks. Outside that
transaction acquire the normal import/job/run rows, verify current execution and
eligibility, then bind ticket/ownership before incrementing attempt/claiming
work. A failed bind does no work and releases only its unused pending ticket.
The same process can release a completed ticket only after its exact operation
and all bound native children stop and handles/threads drain. A restarted process
can release another ticket only through a bounded OS identity query proving the
original host/boot/PID-birth process is dead (or PID reused with different birth),
including all bound children, followed by root-locked recheck of immutable ticket
identity. Boot identity is corroborated with the local persisted host/root binding;
unknown host, unreadable identity, access denial or malformed native evidence
retains the slot and exposes safe capacity pressure. No DB lease timeout or empty
process search proves death. A live stale attempt retains its slot while a new
attempt, if otherwise eligible, needs an additional free slot. This bounds live
and unresolved owned native work together and prevents recovery from exceeding
eight by reclaiming a still-running stale process. Never terminate an unverified
process to create capacity. Native verifier uses bounded platform APIs (/proc on
Linux and birth-checked process handles on Windows), no shell/CIM timeout fallback.

The 100 GiB local committed+reserved data ceiling counts unique registered data
artifacts and retained staged/failed/orphan source/output bytes plus outstanding
data reservation. Do not double-count a registered artifact already represented
by a retained reservation or the same version reachable in the union catalog.
Initialize conservative charges from verified catalog/owned inventory during the
disposable migration rehearsal; uncertain retained bytes remain charged and can
block intake. Scratch/spill remain additional physical reservations under their
existing ceilings. Numerical outputs also remain physically charged; they must
not create an untracked bypass of the local ceiling. No customer-specific claim.

Runtime readiness is mandatory, not established by the rehearsal. Migration
creates an uninitialized `v2_capacity_roots` row/ledger contract; configuration
binds this database to exactly one normalized local root and UUID. A nonempty
database cannot silently bind another path. Intake, upload, staging and both v2
worker claims fail unavailable until that exact binding has a verified ready
inventory receipt under the current ledger schema. Historical completed reads
remain available independently where their existing artifact checks succeed.

Initialization/reconciliation sets root unready under root lock, quiesces and
verifies all cooperating writers/tickets have drained or retains an explicit
blocker, then inventories outside short DB locks. The receipt is immutable and
hashes the root binding, ledger schema, catalog/reservation identities, unique
root-contained artifact paths, sizes and verified content/signature identities,
and conservative unexplained retained/orphan charges. Include legacy/current
dataset artifacts, staged and failed generations, ingestion outputs/orphans and
legacy/current numerical result artifacts; exclude neither old registered data
nor legacy result bytes merely because they lack a v2 reservation. Count each
physical retained file once; add only unconsumed data reservations. Inventory
uses bounded directory traversal with on-disk bookkeeping rather than unbounded
RAM, rejects symlinks/out-of-root paths, and fails on missing/inconsistent
registered artifacts. Scratch/spill get their separate physical charges.

After verification, root-locked activation rechecks the unchanged catalog/ledger
and writer-quiescence epochs plus inventory path signatures, writes exact baseline
charges/receipt hash atomically, and marks ready. Any changed identity aborts
activation and requires fresh reconciliation. No concurrent reservation can pass
while unready. Existing bytes over 100 GiB make new admissions fail; never delete
or refund them to enable the feature. The operator procedure uses owned roots and
does not migrate or inspect an original service as an operational target.

All subsequent cooperating writes must reserve before creating bytes and reconcile
through that root ledger, including legacy ingestion/research writers against a
bound root; preserve their exact data/formula/protocol behavior. Before accepting
new intake after process restart, verify persisted binding/schema/receipt and
reconcile crash leftovers and unresolved process tickets. Any detected unmanaged
write, missing artifact, changed signature, moved root or ledger mismatch marks
unready and blocks new writers pending quiesced reconciliation. Run a bounded
startup/operator inventory audit before ready activation; do not claim continuous
external-writer protection between audits. This cooperating local-stack contract
does not stop arbitrary filesystem or superuser mutations, but never knowingly
continues admission with a stale baseline. Tests must cover preexisting unreserved
legacy data/results, restart, concurrent initialization, another root and later
unmanaged writes, with no quota bypass.

Physical admission continues checking actual free bytes plus outstanding ingestion
and research reservations under that same root lock; uploads use the existing
source ledger so renewals cannot create a private uncounted pool. Streaming moves
reserved to retained with no reduction in total charge. Output/scratch allocation
and success reconciliation preserve current ceilings; storage quota never raises
physical limits. Physical outstanding counts unconsumed reservations since actual
free space already reflects retained files; logical 100 GiB also includes retained
and committed data. Never double-count retained files in physical admission or
omit them from logical quota. Charge and slot transactions cannot form lock cycles: capacity
transactions acquire root lock before their own admission/reservation rows and
never wait for import/job/run rows. Reserve slots before work-row locks, recheck
ownership at claim, and release unused tickets only after exact owner/drain checks.
Never acquire root lock while holding an import/job/run row; refactor narrow v2
reservation call sites as necessary to meet this order while preserving atomically
safe admission, replay and fence checks. Actual contention/race tests are mandatory.

Retain failed generations and bytes until explicit ownership/terminal/reference/
inventory-checked cleanup. No auto expiry deletion, quota forgiveness, broad prune,
or migration of original data/services. Rehearse fresh/populated upgrades and
restore verified dumps to isolated resources; forward-only rollback means disable
intake/restore separately, not destructive downgrade.

## 6. Metadata-driven browser behavior

Instrument identity and units come from registered/pinned metadata, never symbol
splitting or hardcoded USDT. Empty catalog shows onboarding; one available
instrument preselects; multiple choices require selection. Disabled instruments
retain research/readability and visibly disallow new ingestion. Instrument
registration uses explicit operator-verified Binance metadata, no symbol search
against arbitrary providers. Display labels are inert escaped text.

Coverage queries follow the bounded/page-completeness protocol above. Dates
prefill only after an unambiguous contiguous
registered daily run is identified, fitting version/bucket bounds and reserving
required warm-up. If coverage alternatives, pagination incompleteness or equal
candidate ambiguity prevent a unique choice, require user resolution. Explicitly
pin each touched day's version; no preferred/latest replacement. User confirms
the complete selection before submit. Distinguish registered daily presence from
actual contiguous valid bar eligibility; server remains authoritative.

Persist selected instrument/version identities and bounded workflow fields through
refresh/navigation without implicit replacement. Revalidate stale metadata and
coverage; preserve original submitted specs. Display UTC inclusive start/exclusive
end, history/evaluation separation, observed_only limitation, gaps, warm-up,
counts/null reasons and ordered comparison units. Compare only exact equal quotes.
No auto-download, missing-bucket fill, cross-day interpolation or automatic workflow
splitting. New metadata cannot mutate historical pinned result units/labels.

Use existing three workflow schemas/metrics/predicates. At most 62 selected versions
and 17,856 five-minute buckets across instruments including history. Profile and
comparison require 12 actual eligible preceding bars; clusters 300. Show workload
estimate and useful limit errors before submit, while retaining server checks.
Charts independently support 1m/5m, <=1,440 buckets and <=5 partitions; make a
bounded chart-window choice explicit rather than silently truncating a research
range. Charts/readback use precisely pinned versions and retain null/missing bars.

Preserve legacy routes/tests and historical result rendering. Generalized UI uses
v2 adapters; legacy v1 readers do not silently acquire v2 data. Legacy copilot/memos
remain accurately scoped. V2 numerical views show generalized model/memo features
as unavailable until Phase 5 and enqueue no model work. Preserve keyboard use,
focus/error status, cancellation, responsive layouts and exact integer display.

## 7. Frozen acceptance, ownership and evidence

Before operations capture fresh source/dirty inventory, protected hashes, all five
original/README service identities/images/mounts/start/restarts/health/endpoints,
input fingerprints and exact owned resource ledger under ignored
`artifacts/v2-phase4-20261030`. No credentials enter tracked docs. Original services
are never migration/restart/cleanup targets. Retained data is read-only or verified
copies. Before cleanup inspect exact IDs/labels/process birth/argv/ports and
resolved paths. Retain every failure and its actual command/source/outcome.

Use explicitly owned isolated API/UI ports and process identities for Playwright;
never `reuseExistingServer` against an unknown server, including fixed legacy
5173. Browser acceptance covers Chromium, Firefox and WebKit with the actual API,
database, workers, files and catalog; mocked frontend tests supplement it.

Freeze requests/fixtures/hash receipts before actual scoring. Reuse verified
BTCUSDT 2025-02-01, SOLUSDT 2025-03-01 and equivalent canonical CSV/Parquet;
reuse BTCUSDT/SOLUSDT 2025-02-28 through 2025-03-02 for overlap/cluster history.
Preserve original raw fingerprints and source/conversion evidence. Actual official
submission uses the official adapter; canonical imports use real browser upload.
No arbitrary new instrument/day campaign or provider fallback. Missing prerequisites
leave the relevant gate incomplete.

Mandatory gates:

1. All three engines: actual official ingestion and CSV/Parquet upload -> status
   -> catalog -> explicit pinning -> market profile/comparison/clusters -> chart/
   numerical result/provenance. Exact normalization and numerical parity with
   CLI/shared services and retained independent Decimal references.
2. Empty/multiple catalogs, >100 alternatives/day and >1,000 alternatives/window,
   no incomplete-page default/gap inference, disabled retained instrument,
   gaps, no eligible warm-up, stale selection, quote mismatch, limits, safe
   metadata text, large counts, refresh/navigation, keyboard and responsive UI.
   No January/BTC/ETH/USDT assumptions outside accurately labeled legacy/examples.
3. Real upload boundaries: bad media/length/hash, short/overlong body, zero/exact/
   one-over size, concurrent/replayed PUT writing zero bytes, lost responses,
   duplicate finalize, expiry/renewal/retired token, every pre-finalize cancel
   state and finalize race, browser interruption and API process death before/
   during upload/after verified bytes/before finalize commit/after commit.
   Observe actual leases without shortening or forced DB state. Terminal imports
   cannot reset; no stale success, duplicate job or partial catalog publication.
4. Real concurrent upload/ingestion/research root-lock and admission contention;
   four staged/eight running/100 GiB boundary fixtures plus unchanged actual
   physical capacity rejection, old-generation retained charges, ledger tampering
   fail-closed, dead-owner recovery and no attempt spent merely waiting. Retain
   all production charges; lower-bound fixtures do not establish actual capacity.
   Measure bounded browser/server memory with declared process coverage/sampling.
   Include root readiness/bootstrap on existing unreserved legacy/current data
   and results, root mismatch, concurrent activation, restart/crash reconciliation,
   later unmanaged writes, verified native PID reuse, unreadable/dead/live stale
   owners and API death with active upload. Persist exact identity evidence.
5. Origin denial/token scoping, safe errors/logs/status, no arbitrary path/URL
   access, wrong expected revision/key conflicts; no direct storage capability.
6. Final-source locked quality/offline/real PostgreSQL, frontend component/types/
   lint/build/browser, rebuilt no-Git package/API/CLI/Redis outage regressions;
   fresh/populated migration/verified restores. Preserve historical-input skips.
7. All five retained legacy numerical scenarios exact; generalized final-source
   numerical/oracle checks, actual cache/recovery checks affected by integration;
   unchanged fresh legacy cold all-62 <1,800s including drain, 230,311,900 trades,
   exact hashes, one numerical attempt and legacy memo queued/zero calls.

No model campaign is required or authorized by Phase 4. Old passes are separately
versioned evidence and cannot replace current-source mandatory gates. Failed
invocations remain failed even if a later reviewed correction passes. Record
UTC/monotonic timing and the inherited clock/uptime/measurement limits honestly.

## 8. Closeout

Record implemented usage in `phase-4-usage.md`, actual invocation/evidence/review
outcomes in verification, and prospective versus completed status in roadmap and
AGENTS. Retain checksummed dumps and isolated restore receipts for each owned
source DB. Verify protected hashes and original services/images/endpoints again
before/after exact ownership cleanup. Reconcile owned processes/resources/ports,
storage/reservation/slot charges and unfinished work without forgiving retained
failure bytes. Retain all data/evidence/dumps; no generated media in Git.

Phase 4 is complete only when every mandatory gate passes on final source,
independent read-only review has no unresolved blocker, backup/restore and
preservation pass, and ownership-checked cleanup is reconciled. Missing evidence
or prerequisite is explicit incompleteness. No commit/push, hosted Phase 4 result,
original-service deployment or Phase 5 authority follows.
