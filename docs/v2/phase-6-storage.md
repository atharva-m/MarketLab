# Phase 6 pre-code contract for shared artifact storage

The November 4, 2026 authority covers design and independent review. Runtime
implementation requires separate authorization. This contract supplements the
[Phase 1 protocol](phase-1-contract.md#9-storage-and-publication-protocol-phase-6),
[compatibility matrix](compatibility-matrix.md) and
[acceptance matrix](acceptance-matrix.md). Completion requires P6-01 through
P6-04 and the applicable final-source regression checks below.

## Scope and reuse

Keep local storage as the default. Add one optional S3-compatible namespace to
the existing single-stack runtime. Use one storage adapter for newly published
legacy and v2 datasets, research and memos, including manifests and all
registered package members, and for v2 browser and CLI staged canonical sources.
Official source downloads, normalization, intermediate computations and native
process ownership remain local. Existing database-only copilot records stay in
PostgreSQL. Reuse validators, numerical kernels, API/CLI contracts, durable
leases/fences, cancellation, admission and memo grounding. Storage is private
and configured by the operator. Phase 7 worker distribution, Phase 8 access
control, direct-to-bucket browser uploads and scheduled cleanup are excluded.

Use low-level operations from one reviewed S3 SDK. The later implementation
authorization must explicitly cover its pinned lockfile additions and any
unavoidable transitive changes. Include the storage package in the ingestion
execution inventory and use the existing all-source inventory for v2 research,
copilot and memo execution. Verify legacy execution fingerprints and packaged
source inventories include the actual adapter and lock bytes. Capture storage
protocol and namespace binding for new execution where they affect write
compatibility. Existing queued jobs retain their exact compatibility rules.
Artifacts moved between backends retain IDs, recorded fingerprints, bytes and
manifest hashes. Fresh executions record their actual source and lock.

## Storage reference and schema

One package corresponds to one existing catalog owner, or one staged source
generation. A complete copy contains the same member names and bytes as the
verified package. The original manifest and registration still define identity
and the validator still checks schema and logical content. Location is a
database reference, never a field added to historical manifests.

Use one additive Alembic revision `0012_v2_storage` following
`0011_v2_copilot_memos`. The tables below specify the logical schema. All
listed columns are required unless explicitly nullable. Use restrictive FKs,
UTC `timestamptz` for timestamps and existing ID types for referenced columns.

| Table | Columns and invariants |
| --- | --- |
| `v2_storage_packages` | `package_id uuid PK`. Exactly one non-null owner FK from `legacy_dataset_id` → `dataset_versions`, `v2_dataset_id` → `v2_dataset_versions`, `legacy_research_id` → `research_results`, `v2_research_id` → `v2_research_results`, `legacy_memo_id` → `memo_results`, `v2_memo_id` → `v2_memo_results`, `upload_generation_id` → `v2_upload_generations`, `cli_import_id` → `v2_canonical_imports`. Unique each owner FK. `legacy_local boolean` permits implicit local resolution only for pre-upgrade rows. |
| `v2_storage_copies` | `copy_id uuid PK`, `package_id` FK, `root_id` FK to `v2_capacity_roots`, `backend_alias varchar(64)`, `verified_at`, `active boolean`. Unique `(copy_id,root_id,backend_alias)` for the object FK, unique partial index on `package_id WHERE active`, plus index on `package_id` for retained copies. Active selection changes only as a whole verified copy. |
| `v2_storage_objects` | `object_id uuid PK`, `root_id` FK to `v2_capacity_roots`, `charge_id`, nullable `copy_id`, `backend_alias varchar(64)`, `object_key varchar(1024)`, nullable `version_id varchar(1024)`, `member varchar(128)`, `media_schema varchar(128)`, `byte_length bigint`, `sha256 varchar(64)`, nullable `multipart_id varchar(1024)`, `state varchar(16)`, `updated_at`. Composite FKs `(charge_id,root_id,backend_alias)` to charges and `(copy_id,root_id,backend_alias)` to copies. Unique `(root_id,backend_alias,object_key)` and `(copy_id,member)`, index `(charge_id,state)`. |

Object states are `planned`, `writing`, `verified`, `retained`,
`retiring`, `retired`. A row with a copy FK is verified, has exact positive
length and SHA-256 and, on S3, a non-null provider version ID. Object length
has a 4 GiB ceiling and each member also obeys its existing tighter limit.
Hashes are lowercase hex. Aliases and member names use a bounded ASCII
allowlist. A member is a single basename from the corresponding validator,
with no traversal or separators. Keys have bounded ASCII segments and reject
absolute paths, dot segments and traversal. Local paths also require existing
root containment and link/junction rejection. Freeze root, backend alias, key,
member, schema, length, hash and charge binding at intent creation. Set
`multipart_id` once from the matching initiation receipt before writing parts.
Set `version_id` once from the exact verified completed generation. These
identifiers cannot be cleared or reassigned. Attach `copy_id` once, at
registration, from verified intent rows belonging to the authorized operation
and charge. Validate the entire member set against the registered owner and
verified package, including its manifest hash. Freeze copy ownership and
membership after attachment. Use a new copy for a new location or generation.
Enforce these one-way transitions with guarded updates under the relevant
locks. Readers verify the registered package and exact generation.

Add `backend_alias varchar(64) NOT NULL DEFAULT 'local'` to
`v2_data_charges` and a unique key on `(charge_id,root_id,backend_alias)`.
New charge groups bind one backend at reservation. Extend the singleton
capacity binding with nullable `object_alias varchar(64)`
and `object_namespace_sha256 varchar(64)`, both null or both set. Reserve
`local` as the filesystem alias. The fingerprint covers the canonical
operator endpoint, region, bucket and prefix, with no credentials. Credential
rotation does not rebind a namespace. Verify the alias and namespace on use
and fail closed on mismatch. Keep the existing local root binding. Advance
the migration-head guards in admission binding and capacity accounting to
require the existing capacity/inference tables and new storage tables at
`0012_v2_storage`. Missing or inconsistent schema/binding fails closed
before reads or admission. Restore
uses explicit operator verification before rebinding either namespace.

Seed lightweight implicit-local package rows for retained registrations and
pre-upgrade finalized canonical generations in the forward migration, using
database metadata alone. Quiesce writers before upgrade. Historical artifact
and job rows stay byte exact. Map completed browser sources by generation FK
and completed CLI sources by import FK, validating the legacy source generation
against the import row. An expired or unfinalized pre-upgrade upload follows
the existing local lifecycle and retains its charges. When an old pending
upload finalizes, register its verified source in the same transaction as
finalization. A finalized source required for a new job must resolve to its
exact pinned generation. Never infer a browser upload from the current import
pointer if a job pinned another generation.

For new publications, every catalog row has a package with one complete active
copy in the same transaction. Resolve the package and all active members from
one database snapshot. Zero active copies is legal only for an implicit local
package. The first explicit activation clears `legacy_local` permanently in
the same transaction. Later removal or loss of the active mapping is an
integrity error. A missing package, missing member, wrong hash, missing
generation or failed verification is also an integrity error. A failed active copy never causes a
lookup of another copy or a legacy path. Previously verified inactive copies
remain addressable only to operator commands. No worker can delete them.

## Publication and read protocol

Provide `put_new`, `stat`, `read_verified`, `materialize_verified`, and
operator-only `delete_unreferenced`. Pass opaque keys and pinned provider
versions internally. Never expose endpoints, object keys, tokens, secret
material or multipart IDs in product payloads, manifests or error details.
Local writes use exclusive staging and atomic no-overwrite publication into
the contained namespace. New keys are
`attempts/<job-or-import-uuid>/<token-or-generation-ordinal>/<upload-uuid>/<member>`.
The local legacy logical path remains available in the existing registration
as a layout field. S3 requires enabled versioning, exact-version HEAD/GET,
conditional create for both PutObject and CompleteMultipartUpload, and private
credentials with deletion denied to normal writers. Require bucket policy
that enforces conditional creation for writes to the managed prefix. Qualify
the chosen endpoint's behavior with actual requests. Use SHA-256 and length,
not the ETag, to authenticate readback. See the primary documentation for
[conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html)
and [multipart uploads](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html).

1. Under existing admission and attempt fences, reserve the complete write
   ceiling and record unique object intents before any external write. Each
   intent binds the exact owner/ticket and the member's expected length and
   hash. Validate local output first, then write and read back the exact object
   generation. Reuse the existing full package validators on those bytes.
2. Perform large file and network I/O outside the registration transaction.
   Acquire the existing import row first when applicable, then job/run row,
   then the version/run advisory lock and the existing quota lock where
   reconciliation requires it. Preserve existing lock ordering. Keep the
   10-second lock and 15-second statement/idle limits. Recheck the live
   owner/token, lease, cancellation, receipt and location mapping immediately
   before registration. Register the package/copy, catalog result, charge
   transition and successful job together. Research success and memo enqueue
   remain atomic.
3. If a different same-version publication won, read and validate the exact
   winner outside locks. Reenter the fence and compare its registration and
   active-copy identity before reuse. Preserve existing comparison of
   deterministic results and dataset logical content. The losing objects
   stay undiscoverable and charged. Stale/cancelled work cannot register,
   including after successful external writes. After commit, replay returns
   the registered success without writing another copy.

On restart, prefer a new unique attempt if an abandoned upload lacks a
verified receipt. Preserve the old charge and require full admission for the
new attempt. Registered version/content mismatches, access failures including
expired credentials, and unknown errors fail closed. Only transport timeouts
and classified transient network/HTTP 408, 429 and 5xx failures consume the
existing durable retry path. No automatic source/backend fallback. Bound
connect/read timeouts by 5s/30s, disable hidden SDK retries and redirects and
enforce enclosing operation deadlines and cancellation. Provider operations
with uncertain outcomes retain their reservation. Stop local workers using
existing drain rules and distinguish remote uncertainty from local drain.

## Staging, accounting and materialization

Browser PUT keeps the 15-minute token, exact Content-Length and one atomic
claim. Renew explicitly to a different generation and reserve its full
declared size. The API and canonical CLI use sequential 16 MiB multipart
buffers with at most 256 parts for a 4 GiB source. Reject excess bytes before
writing them, verify streamed length and SHA-256, complete only the expected
parts and verify the exact completed version before marking it uploaded.
Persist the upload ID before sending any part. No blind replay of initiation,
part or completion after an ambiguous result. Retain the intent and charge
until an operator can verify the exact remote state. Finalization pins the
already verified generation under the import lock. The worker re-verifies
length and SHA-256 before normalization.

Retain the 100 GiB committed-plus-reserved data ceiling, four active staged
uploads and eight running ingestion/numerical jobs. Use the same
`v2-space:<root>` lock and logical charge ledger. Local disk, scratch, spill
and existing native admission are still checked separately. One existing or
new charge covers each managed write group, with the sum of its intent
lengths checked against that charge's ceiling under the capacity lock.
Compute logical usage as the local baseline plus all `reserved` and
`retained` charges across both backends. The baseline continues to include
verified local inventory and unresolved historical non-scratch storage and
research output reservations. Preserve each pending reservation at its
existing amount, and count it once if explicitly linked to a new charge.
Any transfer between baseline and charge coverage occurs under the same
capacity lock and preserves the outstanding amount. Reconciliation
may absorb a local charge only after its exact drained, retained files are
verified and included in the new baseline. Commit baseline and absorption
together under the capacity lock after checking the inventory epoch. A
remote charge cannot be absorbed or released by a local filesystem scan.
Reconcile remote charges only from durable write intent and exact provider
evidence. Cache and scratch remain subject to physical reservations and are
excluded from the authoritative baseline only when their ownership is proven.

An explicit copy record for a previously implicit local package links to an
`absorbed` local charge recording the exact inventoried member bytes. Reuse
an exact existing absorbed charge when it matches the package or insert an
absorbed inventory link after confirming every member is already counted in
the baseline. Never treat this link as a new debit or an opportunity to clear
another charge. Reserve an additional full charge for every migration copy
or competing upload that creates new retained bytes. Existing local copies
continue to count. Reconcile completed multipart parts as one
completed object only when the provider proves replacement. Uncertain,
interrupted, expired, stale and losing writes retain their full unresolved
reservation. Verified recorded parts and completed objects retain actual
bytes after any unused reservation is released. If reconciliation cannot
prove absence, preserve the charge. Keep aggregate counters across local
and S3 objects, and include new object/charge records in the initialization
and reconciliation epoch. Materializations and working files use bounded
physical admission and never replace or disguise retained data charges.

The verified file cache is 10 GiB per worker, keyed by SHA-256 and length.
Check exact registered generation availability and size, and verify the
materialized bytes before use. On a cache miss read the pinned generation
and hash while streaming into bounded temporary storage. Install verified
entries atomically. Pin for the full native read lifetime and evict only
unpinned least-recently-used entries. A corrupt entry is unusable. Re-fetch
the same registered generation if available, never a different copy. Use
the existing 20 GiB job scratch allowance and separate spill/output limits
for larger working sets or when pinned cache pressure prevents caching.
Acquire physical capacity before materialization, and reject a working set
that cannot fit without exceeding existing limits. Cache paths are private,
never authoritative, and independent of the Redis response cache. Process
coverage/overlap verification in bounded windows while preserving cross-window
checks. Keep metadata and immutable member identities across windows and
release file pins after their last consumer. Verify cold all-62 behavior
without pinning the whole selection. Cached analytics responses still require
registered binding validation and cannot hide missing authoritative data.

## Operator copy, reversal and restore

Add a local operator command with dry-run, copy/verify, switch and reverse
operations. Run on quiescent owned resources. A receipt identifies the bounded
package selection, source mapping and hashes, destination namespace and exact
versions, sizes, and original and new charges. Reserve capacity before copying.
Stream exact bytes through the same verification path. A switch or reversal
uses one database transaction for the selected packages, compares current
active mappings to the reviewed receipt, then activates complete verified
copies. Re-verify reversal targets outside the transaction and recheck the
mapping under locks. Source and destination copies both remain retained.
Adopt the implicit local package as an explicit verified local copy before
the first switch, preserving its original paths. Reversal activates that
explicit copy and never restores implicit-local eligibility.

Backup captures PostgreSQL, exact referenced object versions, local files and
ledger/incomplete-upload state under quiescence. Keep an inventory of retained
failed/partial writes and their evidence. A restored unresolved charge cannot
be released solely because parts are absent on the destination. Restore into
separate owned resources, reverify bytes and bind restored object generations
and namespace explicitly using the same copy/switch rules. Provider version
IDs may differ on the restore destination. Artifact identity never changes.
Retention and operator recovery documentation must identify original and
restored resource IDs and include safe credential setup. Any cleanup must
prove ownership, no current or retained copy reference, no live or uncertain
writer, and verified absence after explicit retirement. Unproved retirement
stays charged. Automatic cleanup and original-service rollout are excluded.

## Required verification

Use one bounded acceptance runner over existing fixtures, lifecycle, fault
injection and closeout helpers. Freeze inputs, comparison outputs and ownership
before live operations. Reuse actual Phase 2–5 datasets, immutable outputs
and prior model-quality evidence with their source qualifications.

| Gate | Required evidence |
| --- | --- |
| P6-01 | Owned local and actual S3-compatible storage. Verify original and generalized datasets, legacy/v2 saved research and memo packages, and canonical staged input. Exercise fresh official and canonical CSV/Parquet ingestion, charts, research and memo publication. Copy parity compares exact bytes, manifests and IDs. Fresh-run parity compares logical outputs and records actual provenance. |
| P6-02 | Crash before/during upload, after verified objects, before commit and after commit. Exercise ambiguous multipart initiation/part/completion, same-version competing publication, stale fence/cancellation, missing or corrupt pinned generation and misleading ETags. Reject locator mutations, mismatched root/charge/copy and wrong owner/member attachment. Check registration, state, readback and retained charges. |
| P6-03 | Actual storage outage and expired credentials. Poisoned/full/pinned cache, scratch exhaustion, interrupted or expired uploads, renewal and concurrent reservation boundaries. Assert bounded failure/retry, no overwrite or fallback and exact conservative charge accounting. Reconcile repeatedly with absorbed local bytes, historical pending reservations, retained objects and uncertain multipart charges. Exercise exact 4 GiB browser upload and over-limit rejection once. |
| P6-04 | Rehearse fresh and populated forward upgrades on owned copies, preserving exactly-once coverage of pending historical reservations. Reject missing ledgers at the new head. Copy/verify/switch/reverse original and generalized artifacts with retained originals. Drop the active pointer on a disposable copy after switching and assert fail-closed readback. Restore coordinated DB and objects to isolated resources and verify every sampled artifact with normal readers. |

Run the relevant full locked offline, real PostgreSQL, quality, frontend/build
and packaged legacy/v2 reader checks on final source. Reuse the five retained
numerical scenarios and cold all-62 inputs with the final storage path. Run a
focused actual browser import-to-results flow in Chromium, Firefox and WebKit
and one bounded actual pinned-model copilot-to-research-to-memo smoke on S3.
Repeat full model cohorts only if model behavior or grounding changes.
Preserve historical failures and new receipts. Before and after owned
operations verify original-service and protected-artifact inventories. Retain
verified backups and perform only ownership-checked cleanup of owned resources
after independent outcome review. Missing mandatory prerequisites leave the
gate incomplete. Hosted CI is separate from actual acceptance and requires
publication authorization.

Implementation uses the roadmap's prescribed coder and independent reviewer
after separate runtime authority. Close all blocking findings before advancing.

## Independent pre-code review

On November 4, 2026, independent read-only reviewer `gpt-6-astra/medium`
passed the contract body with SHA-256
`b8758f6bfc8fb6b067aa35c95ce18224b6180687a257720ef0d10e80a1123f0f`
before this review record was appended.

The initial review required permanent removal of implicit local eligibility
after activation, immutable verified locators and package membership, and
explicit separation of local baseline accounting from remote charges. The
revised contract resolves all three, including exact once coverage of
historical pending reservations during upgrade and reconciliation. The
review establishes the documentation outcome. Runtime implementation and
acceptance are pending separate authorization.

## Implementation supplement: materialization ownership

Implementation was subsequently authorized, including the required SDK and
lockfile changes, with all S3 feature tests explicitly deferred. Independent
read-only reviewer `gpt-6-astra/medium` approved this narrow schema supplement
before implementation of materialization recovery.

Revision 0012 adds nullable `materialization_native_identity text` to
`v2_research_reservations`, with a CHECK limiting UTF-8 bytes to 16384. Existing
rows stay NULL. Capture the existing native identity envelope immutably for
new materialization reservations. Recovery is restricted to exact
`.materializations/<reservation_uuid>` paths, NULL run_id, preparation purpose,
and zero spill/output. Stop intake and quiesce under the shared capacity lock;
recheck the unchanged owner/path/identity before any release. Reuse existing
native identity and native-child death/group-drain proofs; parent PID death
alone does not prove native consumers have stopped. Unknown, foreign, malformed
or incomplete ownership proofs retain their reservations. Remove only the
contained owned tree and verify absence before zeroing reserved bytes. Ordinary
audits never automatically release these reservations. No new native identity
algorithm or broader process-management scope is introduced.
