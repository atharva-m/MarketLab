# V2 Phase 2: Binance instruments and durable ingestion

Status: PHASE 2 COMPLETE; full local acceptance, owned cleanup and independent
read-only closeout review passed with no unresolved blocking finding. The pre-code
contract and scoped repairs were reviewed before their implementation.
Date: October 28, 2026 (America/New_York).

## 1. Authority and phase boundary

The user approved the detailed Binance-only Phase 2 proposal: update contributor
instructions/roadmap, write this contract BEFORE code, implement through coder
`gpt-6.1-sol/high`, obtain independent read-only review by
`gpt-6-astra/medium`, resolve findings, and run full actual acceptance. Pre-code
review precedes runtime edits/operations. No commit/push, original-service rollout,
purchase, or system-change authority follows. [Phase 1](phase-1-contract.md),
[compatibility](compatibility-matrix.md), and [acceptance](acceptance-matrix.md)
remain normative except the phase allocation clarifications here. Record actual
outcomes in [verification](phase-2-verification.md).

Deliver Binance spot registry, additive v2 ingestion/catalog tables, CLI and shared
services, official daily ingestion, Binance-origin canonical CSV/Parquet imports,
local staging, durable workers, verified publication/readback, and preservation.
Identity is `binance:spot:<official source symbol>`; reject other venues/markets,
venue/symbol aliases, malformed/opaque source IDs and provider fallback. Legacy
`binance_spot` remains in legacy bytes; only verified read adaptation maps it.

No new HTTP endpoints, browser upload capabilities, UI features, generalized
bars/research/cache semantics, model/prompt/memo changes, object storage,
multi-host/auth/customer quotas, scheduling, or automatic GC. Phase 4 supplies
public discovery/uploads. Phase 3 integrates selected-snapshot identity checking
into numerical selection. Phases 3-9 remain proposals. Preserve independent
synthetic `/trades` and all legacy runtime contracts; v2 datasets do not silently
become eligible for legacy analytics.

Reuse locked Python 3.13, SQLAlchemy/psycopg/Alembic, httpx, PyArrow and stdlib
SQLite/CSV/Decimal/hash/JSON. No dependency/lock or original-service configuration
change. If existing dependencies cannot meet a mandatory bound, record a blocker
and obtain a scoped amendment; never weaken validation or edit locks silently.

## 2. Source facts and implementation ownership

Read-only inspection at HEAD `b8ededa67c7bebec3380ecab08dabad791deacdc` found migration
head `0007_memos`, v1 registration in `0003_dataset_versions`, and fixed January/
BTC/ETH CHECKs in `0004_ingestion_jobs`. Current source, normalization, job,
publication and CLI modules implement v1, not the future behavior described here.

Implement v2 modules under `src/marketlab/datasets/v2/` with explicit v2 dispatch
in `dataset_cli.py`, forward revision `0008_v2_ingestion` after `0007_memos`,
focused unit/integration tests and acceptance tooling under existing trees.
Never edit old migrations. Read full retained R1/R2 contracts before runtime
changes. Legacy helper extraction is permitted only with exact old signatures,
outputs, identities and tests; otherwise keep v2 separate. Update usage docs for
actually delivered commands. No frontend/application lock changes.

## 3. Strict inputs and immutable identity

Use Phase 1 grammars/date range 1970-01-01 through 9999-12-30, canonical JSON
(sorted keys, compact separators, ASCII escaping, no nonfinite values, terminal
LF), strict 64 KiB UTF-8 control JSON with duplicate/unknown-key rejection, and
keys `[A-Za-z0-9_.-]{1,128}`. Booleans never satisfy integer fields. Bound date
expansion before allocation. Official days must be completed past UTC days at
admission/execution; canonical data may describe the current UTC day as observed
only. No float timestamp conversion or local-time inference.

Registry request fields are exactly `venue_id`, `market`, `source_symbol`,
`base_asset`, `quote_asset`, `display_name`, `trade_id_order`, `adapter`.
Require `binance`, `spot`, `numeric`, `binance_daily` respectively.
`canonical_file` is an import mode sharing the same instrument semantics.
Registration requires operator-verified Binance asset metadata; no symbol
splitting. Only display_name/enabled may change with expected revision. Conflicting
semantics require a separately reviewed repair proposal. Seed only verified legacy
BTCUSDT/BTC/USDT and ETHUSDT/ETH/USDT mappings.

Official request fields are exactly `schema=daily-ingestion-v2`,
`adapter=binance_daily`, `instrument_ids` (1..2 distinct, canonicalized sorted),
`from_date`, `before_date`. Cartesian instrument/day children must total 1..62.
Operation/key canonical request replay returns the original resource IDs and
captured execution identity; it never recaptures a new build or upgrades queued
work. Conflicting canonical request reuse fails. The service separately pins
execution contract/source fingerprint/transform/lock in each submission.
Execution fingerprint hashes a sorted relative-path/SHA-256 inventory of v2
runtime modules, all reused legacy dataset execution helpers, dataset_cli dispatch
and uv.lock; docs/tests/Git dirty state do
not participate. The exact file inventory is versioned with the contract. Worker
admission recomputes it and rejects mismatch without consuming an attempt.

Canonical metadata remains Phase 1's exact `canonical-trade-import-v1` schema.
Use its bounded source_reference text plus separate retained conversion evidence;
no additional manifest keys. Supplied quote quantity is copied exactly, never
calculated. Caller source names/hashes do not prove venue authenticity. Reject
declared/known non-Binance origins; never claim arbitrary files were independently
authenticated. Mechanical validation checks shape/types/declared hashes and
registry scope. Detecting fabricated numeric IDs, relabeled origin, or a supplied
number secretly computed as price times quantity requires retained provider
reference comparison; arbitrary well-formed files cannot prove those facts. Do
not claim universal fraud/origin detection. P2 acceptance compares every canonical
row to its verified official reference and rejects discrepancies there. Caller
paths are local inputs, never durable worker dependencies.

Normalized `spot-trades-v2` fields: instrument_id string, source_trade_id string,
executed_at timestamp(us, UTC), price/quantity/quote_quantity decimal128(38,18),
nullable boolean maker/match flags; supplied-quote provenance in manifest.
Numeric IDs are canonical unsigned text in 0..2^63-1. Phase 1 logical JSON row
encoding and numeric ID order are authoritative. Identical duplicate IDs collapse;
conflicting duplicates/empty input fail. Count all rows/logical bytes before
deduplication. Record raw/accepted/duplicate counts and observed bounds without
provider-completeness inference.

Official v2 parsing retains strict seven-column ZIP/checksum-before-parse. Provider
spot timestamps are milliseconds before 2025-01-01 and microseconds from that date;
validate against the declared UTC day and reject mixed/incompatible encoding.
Keep legacy parsing unchanged. Canonical CSV uses explicit manifest RFC3339-UTC
or integer seconds/milliseconds/microseconds; Parquet uses exact timestamp(us,
UTC), decimal128(38,18), string IDs and bool/null. Reject lossy casts, floats,
exponent/NaN/excess decimal precision, non-UTC/naive/submicrosecond timestamps,
nested/extra/duplicate fields and unbounded metadata. CSV allows optional UTF-8
BOM, exact headers and no embedded record newlines.

Dataset identity hashes exactly source_sha256, metadata_sha256,
instrument_semantic_sha256, trade_date, schema_version=`spot-trades-v2`,
transform_version=`binance-spot-trades-v2`, lock_sha256 using canonical JSON.
Canonical metadata hash excludes only source_name/source_reference. Internal
official metadata uses schema=`binance-daily-source-v2`, format=`binance_zip`,
timestamp_encoding=`unix_milliseconds` before 2025-01-01 or
`unix_microseconds` from that date, quote_quantity_mode=`supplied`,
coverage_claim=`observed_only`, instrument_id and trade_date from the pinned job,
and source_sha256 over the exact downloaded ZIP bytes verified by its official
checksum;
it is not an accepted canonical import schema. Labels/jobs/location/retrieval/Git
dirty state are provenance, not identity inputs. ZIP/CSV/Parquet identities differ
with source bytes even when logical rows equal. Corrections create immutable
daily alternatives; old bytes remain unchanged.
The official internal metadata object has exactly schema, instrument_id,
trade_date, format, timestamp_encoding, quote_quantity_mode, source_sha256 and
coverage_claim. No retrieval URL/time or display text enters that object.

## 4. Forward database schema

Use new `v2_` tables only. UUIDs are PostgreSQL UUID; hashes varchar(64) with
lowercase-hex CHECK; dates DATE; timestamps TIMESTAMPTZ using clock_timestamp();
counts/bytes/tokens BIGINT; revisions/attempts INTEGER; snapshots JSONB with
canonical hash and 64 KiB serialized bound before insert/read. FKs RESTRICT,
never cascade deletion. `?` below means nullable; other columns are NOT NULL.
No raw trade rows enter PostgreSQL.

| Table | Concrete columns and keys |
| --- | --- |
| `v2_instruments` | instrument_id varchar(109) PK; venue_id varchar(32), market varchar(8), source_symbol varchar(64), base_asset/quote_asset varchar(32), display_name varchar(80), trade_id_order varchar(8), adapter varchar(32), semantic_sha256 hash, enabled bool, revision int, created_at/updated_at timestamps; UNIQUE venue_id/market/source_symbol and instrument_id/semantic_sha256 |
| `v2_operations` | operation varchar(32), protocol varchar(48), idempotency_key varchar(128) composite PK; request_sha256 hash, resource_id UUID?, response_json JSONB, created_at timestamp |
| `v2_ingestion_submissions` | submission_id UUID PK, request_sha256 hash, request_json JSONB, contract varchar(48), execution_sha256/lock_sha256 hashes, transform_version varchar(48), from_date/before_date dates, instrument_count/child_count int, created_at timestamp |
| `v2_canonical_imports` | import_id UUID PK, instrument_id FK registry, semantic_sha256 hash composite registry FK, trade_date date, metadata_json JSONB, metadata_sha256/source_sha256 hashes, format varchar(8), declared_bytes/received_bytes bigint, generation_id UUID UNIQUE, source_relative_path text UNIQUE, state varchar(16), revision int, staging_owner UUID?, staging_lease_until timestamp?, submission_id UUID? UNIQUE FK submissions, error_code varchar(64)?, created_at/updated_at timestamps |
| `v2_ingestion_jobs` | job_id UUID PK, submission_id FK submissions, instrument_id FK registry, semantic_sha256 hash composite registry FK, instrument_snapshot JSONB, trade_date date, source_mode varchar(16), import_id UUID? UNIQUE FK imports, state varchar(16), revision/attempt_count int, fencing_token bigint, owner UUID?, lease_until timestamp?, eligible_at timestamp, cancel_requested bool, result_version hash? FK datasets, error_code varchar(64)?, created_at/updated_at timestamps; UNIQUE submission/instrument/day |
| `v2_ingestion_attempts` | job_id FK jobs + attempt_number int composite PK; fencing_token bigint, owner UUID, execution_sha256 hash, started_at timestamp, ended_at timestamp?, outcome varchar(16), error_code varchar(64)?; UNIQUE job/token |
| `v2_dataset_versions` | dataset_version_id hash PK, instrument_id FK registry, semantic_sha256 hash composite registry FK, trade_date date, source_sha256/metadata_sha256/logical_sha256/manifest_sha256 hashes, schema_version/transform_version varchar(48), lock_sha256 hash, manifest_relative_path text UNIQUE, row_count bigint, observed_from/observed_through/published_at timestamps |
| `v2_storage_reservations` | reservation_id UUID PK, import_id UUID? FK imports, job_id UUID? FK jobs, fencing_token bigint?, kind varchar(16), reserved_bytes/retained_bytes/ceiling_bytes bigint, state varchar(16), relative_path text UNIQUE, created_at/updated_at timestamps |

CHECKs: registry fixed venue/market/order/adapter, field grammars/generated ID,
revision>=0, valid display text; dates within supported range; submissions
from_date<before_date, instrument_count 1..2, child_count 1..62 and
child_count=instrument_count*(before_date-from_date). Imports have positive declared
bytes<=4 GiB, received bytes in 0..declared, format CSV/Parquet, revision>=0,
allowlisted states, owner+lease iff staging. Jobs have attempts 0..3, token>=0,
revision>=0, allowlisted states, owner+lease iff running, result iff succeeded,
source_mode official/canonical and import_id iff canonical. Attempts have number
1..3, token>0, outcome running iff ended_at NULL. Datasets have positive rows<=20M,
observed bounds within day/nondecreasing and fixed v2 schema/transform. Reservations
have nonnegative counts, reserved+retained<=ceiling, positive ceiling, exact owner
relation (import-only source or job+token output/scratch) and allowlisted states.
Nullable hashes validate when present. Error codes never contain exceptions.
Exact job states are queued/running/retry_wait/succeeded/failed/cancelled; exact
attempt outcomes running/succeeded/transient/permanent/expired/cancelled. Import
states are staging/queued/running/retry_wait/succeeded/failed/cancelled.
Reservation kinds are source/output/scratch and states reserved/retained/released;
released requires reserved_bytes=retained_bytes=0 after verified reconciliation.

Indexes: registry `(enabled,instrument_id)` and `(base_asset,quote_asset,instrument_id)`;
datasets `(instrument_id,trade_date,dataset_version_id)`; jobs
`(state,eligible_at,lease_until,job_id)` and `(submission_id,job_id)`; imports
`(state,staging_lease_until,import_id)`; reservations `(state,reservation_id)` and
owner IDs. Preserve all existing definitions. Legacy mapping uses no old-row FK.

Cross-row invariants: lock submission, validate/capture registry snapshots, insert
the exact expected unique instrument/day child set atomically, verify cardinality
before commit. No append/delete-child interface. Canonical submissions have one
instrument/day/child. Under fence verify success result matches job instrument/
day/semantic hash and manifest. Enforce token monotonicity, terminal immutability
and immutable registry semantics in every service mutation. Direct-SQL tests cover
row-local DDL constraints. Superuser SQL is outside cooperating-worker guarantees.

## 5. Local staging, limits and accounting

CLI import is a local create-copy-verify-finalize service operation; HTTP upload
tokens/renewals remain deferred. Request hash binds manifest and declared actual
file length, never input path. Allocate import/generation and safe server path,
reserve source bytes, then copy one opened regular nonsymlink input in bounded
chunks to exclusive generation staging. Reject size/hash mismatch; independently
verify staged copy before enqueue. Replacement/mutation cannot change enqueued
bytes; worker rehashes staged source. Paths never enter remote job arguments.

Import states: staging -> queued -> running -> retry_wait, then
succeeded/failed/cancelled; retry_wait may return running. Every transition
increments revision. Staging owns a 60s lease with independent 10s heartbeat.
The verified-upload milestone is local only: there is no durable uploaded state
in this CLI phase. Finalization under the current staging owner/unexpired lease
locks import, creates its submission/job and transitions directly to queued in
one transaction. A crash after copy verification but before commit leaves leased
staging, which expires terminally failed; fresh import/key is required. A crash
after commit replays the linked job. This narrows the local CLI lifecycle only;
Phase 4 HTTP upload/finalize lifecycle remains separately specified. No CLI
renewal/resume. Lost-response same-key replay returns original IDs/current status;
it cannot recopy, mint generation, reset failure or extend a lease.

Retain Phase 1 bounds: official 512 MiB compressed/4 GiB expanded/4096-byte
checksum; canonical 4 GiB source AND decoded logical bytes; 20M input rows,
4096-byte CSV record, 64 KiB metadata; normalized Parquet 4 GiB and manifest/
quality report each 64 KiB; submission <=62 children; worker 1..62 jobs with
waiting 0..3600s. Count duplicate logical bytes before collapse. Inspect bounded
Parquet footer/row-group metadata before allocations; stream bounded batches.

Reservations record unconsumed reserved plus retained actual bytes; streaming
transfers counters without reducing total charge. Source ceiling=declared bytes.
Reserve output 4 GiB+128 KiB per active attempt separately. Check physical free
space against outstanding reservations under a storage-root advisory transaction
lock before admission. Reserve/check bounded scratch separately (20 GiB per active
job, including SQLite/journals), monitor disk-backed writes and fail safely on
capacity loss. Reconcile actual output and release unused reservation only after
verified completion; retain charges for failed/losing bytes until verified explicit
cleanup. This is local physical-space accounting, not Phase 8 customer quotas.
No automatic deletion; cleanup checks exact ownership, terminal state, references
and filesystem inventory and reconciles counters only after verified removal.
Successful source evidence remains retained during acceptance.

## 6. Durable execution and publication

Claim exact v2 contract/source/lock/transform identity only; never claim or reset
v1 tasks. SKIP LOCKED candidates: canonical state mutations lock import first,
then job, then version advisory lock; official jobs use job then version.
Heartbeats may lock job alone because they never project import state. Never
acquire import after job. Use 10s lock and 15s statement/idle transaction limits.

Database-time lease=60s, independent heartbeat=10s. Claim/reclaim increments token
and attempt once; crashes consume attempts. End expired old attempt before new
ownership. Third expired attempt fails without fourth execution. Queued jobs stay
immediately eligible despite backward clock steps; retries/leases use
clock_timestamp(). Every mutation requires matching owner/token/unexpired lease;
loss stops bounded work and prevents publication. One job per worker process.

Retry classified network timeout/408/429/5xx and temporary DB/storage availability
within three total attempts: delays 10s then 30s, max with provider Retry-After
capped at 3600s. No hidden HTTP retries/proxies/redirects/day-provider substitution.
Validation/checksum/conflicting-ID/unsupported-type/corruption/unknown errors fail
permanently. Failed pre-enqueue staging consumes no normalization attempt.

Cancellation uses key and expected revision. Queued/retry jobs cancel without
claim; running sets durable cancel_requested and worker stops/drains then cancels
under fence. Dead-owner reclaim finalizes requested cancellation without another
attempt. Cancel/publication serialize on the same rows: success first yields
cancel conflict; accepted cancel first forbids success. Same operation replays;
stale fresh revisions conflict; terminal jobs cannot reset. Signals stop new claims
and drain/stop current bounded work without false upstream-cancellation claims.

Write safe-root-contained exclusive attempt artifacts, verify source/Parquet/
rows/count/logical hash/quality/manifest outside DB locks. Final path is
`datasets-v2/<version>/` with constant filenames, no raw symbol path segments.
No symlinks/traversal/overwrite. Use local no-overwrite publication discipline;
all full artifact I/O stays outside short DB transactions. Immediately before
registration recheck current fence/cancellation, register verified version + job
success + canonical import projection + reservation reconciliation in one commit.
Only committed catalog rows are discoverable. Stale attempts may leave files but
cannot register. Competing same-version publishers verify/reuse the registered
winner; never overwrite. A filesystem-before-commit crash leaves an orphan that
only a fresh fenced attempt can fully verify/adopt under identity lock. Commit-
before-response replays success. Registered corruption fails closed with no
automatic rebuild. No cross-system transaction/exactly-once filesystem claim.

## 7. CLI and read services

Prefix is `python -m marketlab.dataset_cli v2`. Existing subcommands stay exact.
JSON stdout/safe bounded stderr, exits 0 success, 2 syntax/validation, 1 operational/
conflict/not-found. Safe structured codes: invalid_request, unsupported_source,
idempotency_conflict, revision_conflict, capacity_exceeded, source_unavailable,
integrity_failure, incompatible_execution, not_found. No paths/SQL/records/secrets.

| Command | Flags and behavior |
| --- | --- |
| instrument-add | --request FILE --key KEY; strict registry create/replay |
| instrument-update | --instrument ID --request FILE --key KEY; expected_revision plus display_name and/or enabled only |
| instruments | optional --instrument ID detail; list --base ASSET --quote ASSET --limit N --cursor CURSOR |
| submit | --request FILE --key KEY; official range; submission_id, child count, replayed |
| import | --manifest FILE --file FILE --key KEY; staged source and one durable job; import/submission/job IDs, state, revision, replayed |
| imports | --import ID; safe staging/job counters/state/revision, no raw paths/records |
| jobs | --submission ID; <=62 jobs with attempts/revisions/errors/version IDs |
| cancel | --job ID --expected-revision N --key KEY; durable cancellation |
| worker | --max-jobs N [--submission ID] [--wait-seconds N]; jobs 1..62, wait 0..3600 |
| datasets | optional --instrument ID --from-date DATE --before-date DATE --limit N --cursor CURSOR; union catalog |
| inspect | --version HASH; full registered legacy/v2 artifact verification and explicit contract |
| coverage | --instrument ID --from-date DATE --before-date DATE; <=62 days, every alternative/gap/observed bound |

List pages default25/max100, cursor<=2048 binds command/filter/order and validates
strictly. Order instrument IDs and dataset instrument/date/contract/version
deterministically; current-committed traversal, not snapshot. Lists report
registered metadata; details fully verify. Reject ambiguous cross-contract hash
references that disagree rather than choosing the first reader.

Shared `validate_selection(engine, root, instrument_id, version_ids)` serves
P2-05: 1..62 explicit verified versions for one instrument, one alternative/day,
disk-backed numeric-ID checks across partitions. Repeated IDs must match exact
timestamp/decimals/flags or conflict. This computes no research and does not alter
v1 selection; legacy rows project for comparison without rewriting artifacts.

## 8. Frozen acceptance and prerequisite gates

Refresh source/dirty overlay, protected hashes, all five observed original/README
container fields/endpoints, backup identity, installed images/runtime/dependencies,
disk and exact owned resource ledger before operations. Use owned isolated DB/
storage/project; originals are observation targets only. Raw evidence remains
ignored under `artifacts/v2-phase2-20261028/`. Retain failures, prior evidence and
historical uptime/clock/model/cancellation/cache limits. Missing prerequisites
leave mandatory gates incomplete.

| Gate | Required actual proof |
| --- | --- |
| P2-01 | Full official BTCUSDT 2025-02-01 and SOLUSDT 2025-03-01 archives/checksums through v2 adapter, independent source digest checks, full normalization/readback counts/logical hashes; no substitute source/day |
| P2-02 | Externally convert that exact verified SOLUSDT day into canonical CSV and exact-schema Parquet; retain archive/checksum/conversion source/hashes; CLI import + separate workers; every logical row/count/hash equals official v2 reference; source identities distinct |
| P2-03 | All encodings/exact day boundaries/decimal/null flags; invalid precision/type/overflow/float/NaN/exponent/timezone/submicrosecond/header/footer/nesting, missing quote quantity, non-Binance manifests reject before publication; canonical-reference comparison rejects fabricated IDs/amounts but arbitrary well-formed source authenticity remains operator-declared |
| P2-04 | Same numeric ID across two Binance instruments isolated, 2/10 numeric order, opaque or malformed IDs/venue aliases/derivatives rejected; altered numeric IDs are detected by provider-reference comparison in the canonical acceptance cohort; labels preserve snapshots; disabled retained instrument readable but no new admissions |
| P2-05 | Replay/conflicting body, fresh-key source reuse, duplicates/conflicts/empty input, corrected immutable daily alternative, selected cross-day identity conflict; old bytes exact |
| P2-06 | Exact/one-over key/record/metadata/partition/row/file/decoded/output limits; real PG claim/fence/retry exhaustion/cancel-publication races/corruption/native lease expiry; actual crashes at staging, claimed-before-work, normalized-before-publication, filesystem-before-DB, DB-before-response; no stale/partial discovery |
| P2-07 | Fresh/populated disposable forward upgrade from 0007; old rows/CHECKs/artifacts exact, queued/terminal v1 state/budgets retained, legacy ingest/inspect/API/CLI shapes/identities unchanged, incompatible workers cannot steal work |
| P2-P | Protected current-baseline hashes exact, original/README services unchanged for observed interval, verified retained dumps and ownership-checked cleanup reconciled |
| P2-R | Independent exact-source technical review with no unresolved blocker; corrections reviewed and affected gates rerun |

Lower-limit fixtures may exercise identical checks cheaply but must be labeled;
never call them physical 4 GiB/20M stress passes. Real maximum tests are required
where fixtures cannot establish allocation/resource behavior. Record durations,
bytes/scratch/rows/attempts and memory sampling interval/PID coverage; absent
memory measurement stays unmeasured. No Phase 3 cold research or Phase 5 inference
campaign is added here. Existing finite source/worker bounds remain mandatory.

Run full locked Ruff lint/format, strict mypy, offline and real PostgreSQL suites,
focused v2 CLI/staging/catalog/migration checks, legacy live API/CLI/package checks,
and unchanged frontend type/lint/component/build/browser compatibility checks.
Use existing harnesses only with owned resources; never CI Compose commands
against originals. Existing demo checks are separate, no new render. Historical
counts/skips are not new passes; hosted CI is unclaimed without publication.

Prerequisites: exact official archives and operator metadata, retained legacy
references/source snapshots, usable Docker/owned PG and required Redis/API
compatibility resources, separate disk and installed locked Python/frontend/
browser/package tools. Missing prerequisites are blockers, not permission for
accounts/purchases, original restarts or Docker/WSL/clock/GPU/global changes.

## 9. Rollback and completion

Rehearse verified backup/forward migration/readback on disposable resources first.
Before v2 writes old binaries may use the additive DB's legacy surface; after v2
writes disable intake and retain all new tables/files, or restore a verified
coordinated backup to a separate owned environment. No populated-table downgrade.
Inspect exact IDs/labels/mounts/paths/ports before cleanup and verify deletion of
owned resources only. Absent processes are not verified cleanup.

Finish only when mandatory gates pass, independent review has no blocker,
preservation and cleanup pass, and verification/roadmap/authority record actual
outcomes. Contract/tooling availability is not acceptance. No commit/push or
later-phase implementation authority follows.


## Resource-validation implementation supplement (October 28, 2026)

The authorized resource gate found that bounded Parquet footer/rowgroup metadata
alone did not bound decoder allocation: the retained isolated capped-process
probe showed a page-size declaration could reach Arrow allocation before the
post-decode batch check. The failed probe and interrupted first actual invocation
remain failures. Before decoding any Parquet column, validate bounded compact-
Thrift page headers, finite parser recursion/containers/strings/varints/header
bytes, page compressed/uncompressed sizes, dictionary/DataPage V1/V2 shapes, file
containment and cumulative column/rowgroup sizes against metadata. Reject pages
above the 64 MiB rowgroup ceiling or inconsistent totals before Arrow decoding.
This is a scoped defensive implementation correction to the approved ingestion
resource bound; no dependencies, locks, original-service or system settings change.
Independent review and a fresh runtime identity with affected actual-data/crash/
regression acceptance are required. The original pre-code snapshot stays intact.


## Exact UTC row conversion implementation supplement (October 28, 2026)

Read-only bounded profiling on the second source found repeated optional-import
lookups during Arrow UTC timestamp-to-Python conversion; the page preflight and
per-row validation were separately measured and were not the dominant cost.
Before the next source freeze, preserve exact Arrow timestamp(us, UTC) schema
admission, cast only its physical microseconds to int64 for Python conversion,
and reconstruct UTC datetime with integer epoch/timedelta arithmetic. Other
columns, row order, decimal values, flags and canonical logical bytes remain
unchanged. Reject null/out-of-range timestamp values safely. Apply this bounded
conversion to canonical Parquet normalization, artifact verification and selected
snapshot reads. No new optional timezone dependency or lock change is permitted.
CLI/control datetime serialization must normalize to UTC before ISO formatting;
pure date values stay dates. Independently review equivalence, UTC/non-UTC and
schema/resource tests, retain the interrupted second invocation, then rerun the
complete actual-data campaign and affected regressions on one fresh final source.
