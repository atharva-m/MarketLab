# Phased delivery: Binance spot MarketLab

Publication authority (November 6, 2026): the user authorized secret-safe
commit/push of reviewed Phase 6 and hosted CI verification for the exact published
SHA, with scoped failures handled through the prescribed coder/reviewer workflow.
Reuse qualified local passes and retain all historical failures and preservation
limitations. Publication and exact-SHA hosted results remain pending. Private
files, generated outputs, data, weights, logs and evidence are excluded through
an explicit publication allowlist. The preexisting tracked `.env.example` blob
is retained unchanged without reading/staging its working contents; its content
has not been secret-audited. No AWS settings change, original-service rollout,
new inference, limit change or Phase 7 authority follows.

Current Phase 6 status (November 6, 2026): the remaining S3 acceptance gates
passed, with qualified preservation and reversible closeout. Boundary 008 passed
exact 4 GiB upload/readback and accounting, with the writer completing in
1,506.066 seconds under the unchanged 1,800-second limit. Owner 008 passed exact native load/unload drain before
deliberate idle-group termination. Capability, 24 live PG/S3 cases, nine browser
flows, functional model checks and applicable local checks were reused.

The rerun corrections are confined to test/diagnostic/closeout helpers. Historical
failures remain retained; three empty-load probes generated no text and did not
repeat the one copilot and one memo functional calls. Five new dump/restore proofs
passed while preserving all previous databases/restores. Owned test containers
are stopped and retained with their volumes, data, remote objects and evidence.
Original services/endpoints/GIF matched point observations; 283 protected hashes
match and two dependency differences are authorized. Two dotenv files remain
unverified, so the full preservation check is not reported as passed. D:'s floor
alone remains waived. No AWS settings changes, commit, push or original-service
rollout occurred. See [verification](docs/v2/phase-6-verification.md).

Earlier investigation checkpoint:
The user subsequently authorized investigating and rerunning the two failed
gates. The affected-only investigation retains all prior outcomes and limits,
reuses qualified checks, and requires reviewed diagnostics/corrections before
concrete reruns. Rerun outcomes are pending; the checkpoint below remains the
last completed test campaign.

Earlier Phase 6 checkpoint (November 6, 2026): S3 testing and reversible closeout
are recorded, but acceptance remains incomplete. Capability and 24 live PG/S3
cases passed; all nine canonical/official browser flows qualified. Model
functionality qualified through one copilot call, one memo call and a separate
read-only completion with zero new calls. Reuse applicable passed local checks.

Two gates remain failed: the exact 4 GiB upload/readback timed out, and the
isolated model owner's normal native-drain check
required forced cleanup. Preserve both failures; no limit relaxation or repeated
inference is implied. Five database dumps/restores passed independent review.
Owned PG/Redis stopped cleanly; containers, volumes, restored databases, host data,
S3 objects and all evidence remain retained. Original services/endpoints/GIF
matched point observations; 283 protected files matched plus two authorized
dependency changes, while two dotenv files remain intentionally unverified.
D:'s floor alone was waived, not passed. The agent made no AWS settings changes;
no commit or push occurred. See [verification](docs/v2/phase-6-verification.md). Earlier checkpoints
below remain historical.

Earlier S3 checkpoint: single-part capability, 19 original live PG cases,
two corrected fence cases, two six-family parity/race cases and the genuine
expired-credential case have passed independent outcome review. Earlier failures
remain retained. Browser/model acceptance and final backup/closeout are pending.
Browser attempt 001 retained a failed partial upload; attempt 002 failed before
tests on an isolated helper import. The user waived only D:'s 50 GiB preflight
floor; C: and all other limits remain unchanged. No AWS settings changes, original
service changes, commit or push are authorized. Earlier checkpoints below are
historical; see the detailed verification receipts.

Under the user's subsequent all-tests authorization, the network-enabled
HeadBucket diagnostic passed. Live capability check 002 passed metadata checks
and created a 32-byte versioned probe, then stopped on HTTP 403 reading that
version's metadata. Independent outcome review confirmed the failure and retained
probe/evidence. Dependent S3 acceptance awaits effective version-specific read
access; no settings changes, original-service changes, commit or push occurred.

The diagnostic-only repair passed independent review and 27 focused offline
tests. The original failed source/evidence remain preserved. A separate reviewed
one-request HeadBucket diagnostic awaits user approval for network-enabled
execution. No AWS retry, settings change, commit or push occurred in this repair;
live S3 acceptance remains incomplete.

November 6, 2026: continue local Phase 6 acceptance preparation. Every further
AWS action requires explicit user approval; AWS settings must not be changed.
No commit or push. The user-applied policy passed independently reviewed read-only
verification, with versioning enabled and region matched. Offline S3 SDK, proxy
and safe-output checks passed (16, 27 and 8 cases respectively). Actual S3 write
behavior and full live acceptance remain pending. Reuse passed local checks and
preserve original services. Earlier checkpoints below remain historical.

The minimal capability helper also passed independent review and 16 offline
fake-client cases. Its concrete ten-request AWS packet awaits user approval;
no live object behavior or full S3 acceptance is claimed.

Subsequently, the user approved that packet. Its one execution stopped at the
first HeadBucket attempt with an indeterminate sanitized error. Independent
review confirmed no object writes/deletes or settings changes were reached.
No retry occurred; S3 acceptance remains incomplete and further AWS action
requires explicit approval.

The user authorized deferred Phase 6 S3 testing on November 5, 2026, with no
commit or push. Applicable passed checks will be reused. Live AWS bindings and
credential access remain prerequisites; actual S3 acceptance is not yet
established. Preserve original services and prior evidence.

Phase 6 implementation, local acceptance and owned-resource closeout passed
independent review on November 5, 2026. All blocking non-S3 findings are resolved.
S3 features and tests are implemented, but S3 tests remain unexecuted and
uncollected at the user's direction; full Phase 6 acceptance is incomplete.
Original services and retained data/evidence were preserved. No commit or push
occurred. See [verification](docs/v2/phase-6-verification.md).

Phase 6 implementation is authorized under the reviewed
[storage contract](docs/v2/phase-6-storage.md), including its required S3 SDK and
lockfile changes. The user explicitly deferred execution of all S3-related
tests while authorizing their implementation. Applicable non-S3 checks proceed;
full Phase 6 acceptance remains incomplete until the deferred gates are run.
Use the prescribed coder/reviewer workflow and preserve original services.
No commit or push. See [actual verification](docs/v2/phase-6-verification.md).

The Phase 6 [storage contract](docs/v2/phase-6-storage.md) passed independent
pre-code review on November 4, 2026 after three blocking findings were resolved.
Runtime implementation, service operations, commit and push require separate
authorization. Earlier checkpoints remain historical.

Phase 5 is published with its scoped concurrent-inspection repair at
`9e0f654cb8afb73d08d96372e045f7ea8393df50` (November 4, 2026).
[Exact-SHA CI run 41849310726](https://github.com/atharva-m/MarketLab/actions/runs/41849310726)
passed all five jobs. Passed local checks and historical evidence remain retained;
only the observed integration race received a focused red/green regression and
coder/reviewer repair. This outcome-only documentation update receives its own
exact-SHA CI check. No original-service rollout or Phase 6 work follows. Earlier
publication checkpoints below are historical; see [verification](docs/v2/phase-5-verification.md).

Phase 5 publication checkpoint (November 4, 2026): commit `5c896c8` was pushed.
Its exact-SHA CI passed four jobs and failed one concurrent-answer integration
case. The scoped inspection-snapshot correction passed independent review and a
focused PostgreSQL red/green regression; repair publication and CI are pending.
See [verification](docs/v2/phase-5-verification.md). The local closeout below
predates this explicitly authorized publication; its retained evidence is unchanged.

Phase 5 is locally complete (November 4, 2026). Independent implementation,
actual acceptance, backup and cleanup reviews passed. Both copilot/memo cohorts,
clarification/grounding/faults, three browser engines, legacy/numerical/cache and
packaged application/readers passed. Applicable prior checks were reused.
All eighteen database dumps/restores, package exports and host roots were verified
before exact owned cleanup; protected files and original services were preserved.
See [Phase 5 verification](docs/v2/phase-5-verification.md) for source-qualified
outcomes, retained failures and operational qualifications. No commit, push,
original-service deployment or Phase 6 work occurred. Earlier checkpoints below
are historical and do not supersede this completion status.

V7 development, existing-root preparation and current-source binding passed.
Both v7 copilot cohorts passed independent outcome review. Each achieved 18 of
20 clear cases and zero handoffs across 40 negative cases. The isolated Ollama
diagnostic passed three calls. The authorized memo cohort A recovery recorded
20 valid entries using its 19 retained passes and one replacement. Independent
outcome review passed. The user then authorized cohort B recovery. Its
cold continuation recorded 20 valid entries using seven retained passes
and 13 new calls. Independent outcome review passed. Other Phase 5
gates and closeout remain incomplete.

The corrected v6 bind passed. The first scored v6 copilot A invocation failed:
three clear cases failed, leaving a maximum of 17 correct against the required
18. It stopped cooperatively. Scored acceptance remains incomplete and no
later scored cohort has run.

The first v6 bind was stopped cooperatively. Its elapsed time included about
2 hours 49 minutes of host sleep. The reviewed evaluator correction reuses verified
selections within a single bind while checking current package hashes and
catalog identity. Acceptance and closeout remain open.

Phase 5 finish checkpoint (November 3, 2026): all eight v6 development probes
and current preparation passed. Reuse the twelve registered dataset bindings,
twenty retained numerical results and twenty fresh numerical results, plus the
applicable 1,494 offline and 300 PostgreSQL passes. Current-source binding and
P5-01 through P5-05, remaining integration and compatibility checks, and final
backup, restore, preservation and owned cleanup remain open. Use existing
acceptance tools under the coder/reviewer workflow. Track actual outcomes in
[Phase 5 verification](docs/v2/phase-5-verification.md). No commit or push.

Current Phase 5 checkpoint, amendment 004 (November 2, 2026): v5 full freeze
passed, but unscored development safely failed its first evidence-grounding probe;
independent clean closeout preserved twelve requests/eleven spent calls, one queued
unexecuted handoff and twenty original queued memos. Exact revision003 of the
[request-specific evidence grammar amendment](docs/v2/phase-5-evidence-grammar.md)
passed independent pre-code review. Scope is the exact compact prompt, canonical
per-request evidence grammar, explicit version/hash integration and one separately
reviewed redundant `cross_asset comparison` lexical correction. All other
independent rules, literal fixtures/cohorts/thresholds, model/settings and limits
remain unchanged. Normative authority precedes prescribed implementation and
independent review; full freeze/input/launch, eight actual development passes and
every mandatory full acceptance gate remain separate. No inference, preparation,
Phase 5 completion, commit/push or original-service change follows. Earlier
statuses remain historical.

Current Phase 5 checkpoint, amendment 003 (November 2, 2026): v4 unscored
development passed its first text probe and safely failed its second context
probe, preserving eleven cumulative requests/ten spent calls and one queued
unexecuted handoff. The exact [uniform evidence-priority amendment](docs/v2/phase-5-evidence-priority.md)
passed independent pre-code review. Scope is prompt-v5/version and minimal fresh
binding, preserving all literals, full cohorts/thresholds, validators, model/settings
and limits. Implementation/freeze/input/launch/outcome review and every mandatory
acceptance gate remain separate. Preparation is held; no new inference or Phase 5
completion is claimed. Earlier statuses remain historical.

Current Phase 5 checkpoint, amendment 002 (November 2, 2026): separate unscored
v3 development failed the first probe's evidence grounding. The exact versioned
[evidence prompt amendment](docs/v2/phase-5-evidence-correction.md) passed
independent pre-code review. Scope is prompt-v4/version and minimal new-directory
development binding, with unchanged validators, eight development literals,
full acceptance fixtures/thresholds, pinned model/settings and limits. Preserve
nine requests/eight spent calls and twenty old-source queued memos. Implementation,
normal full freeze/input, launch and actual acceptance remain separate required
gates. No new inference or Phase 5 completion is claimed; earlier statuses remain
historical.

Current Phase 5 checkpoint (November 2, 2026): implementation and original frozen
input review passed, but the first actual copilot cohort failed and was safely
closed; Phase 5 remains incomplete. Independent pre-code review approved the
[versioned prompt correction](docs/v2/phase-5-prompt-correction.md) before its
implementation. Bounded unscored development requires independent implementation/
launch review; unchanged full acceptance cohorts and all remaining gates still
apply. Preserve failed model calls, queued intake/memos and prior source-qualified
data/numerical evidence. No threshold/model/limit change, data/cache optimization,
commit or push is authorized. Earlier pending statuses below remain historical.

Status: Phase 1 documentation and read-only verification completed on October 28,
2026, with independent review and no unresolved blocking finding. Phase 2 is
authorized under the [pre-code contract](docs/v2/phase-2-ingestion.md).
Implementation, final-source quality/backend/package checks and the actual
official/CSV/Parquet campaign and six native process-crash boundaries passed.
Final preservation, ownership-checked cleanup and independent closeout review
passed with no unresolved blocking finding. Phase 2 is complete.
The user subsequently authorized publication of verified Phase 2 and exact-SHA
hosted CI. Published SHA `be3f7aeb3539c1db7386401b6553fe918337d6a7` passed
[all five hosted jobs](https://github.com/atharva-m/MarketLab/actions/runs/40811497336)
after reviewed CI-only capacity repairs; all four earlier failed runs remain in
verification. Local actual-data acceptance remains distinct from hosted checks.
The documentation-only outcome publication is pending; its exact-SHA CI will be
reported in the session. Phase 3 was separately approved on October 29, 2026
for implementation and local acceptance under its pre-code contract below.
Final-source runtime gates, eight database backup/restores, owned cleanup and
final preservation passed; independent closeout review passed with no unresolved
blocking finding. Phase 3 is locally complete.
Phase 3 was subsequently published as `387dc8202b8716926b079fa9c4c56231b53bc6e0`;
[all five exact-SHA hosted jobs](https://github.com/atharva-m/MarketLab/actions/runs/40998640447)
passed after two independently reviewed Windows harness-only repairs. Both failed
published runs remain preserved in Phase 3 verification. Local actual-data gates
and hosted validation remain separate. The user approved Phase 4 on October 30,
2026 under its [pre-code contract](docs/v2/phase-4-ui-imports.md), with independent
design review before code, prescribed coder/reviewer, full local acceptance and
original-service preservation. The October 31
[completion amendment](docs/v2/phase-4-completion.md) bounded the remaining
acceptance and cleanup work. Actual three-engine flows, exact 4 GiB upload,
source-qualified regression gates, verified seventeen-database backup/restores,
two package exports, ownership-checked cleanup and final preservation passed.
Independent implementation/acceptance/backup/cleanup reviews found no unresolved
blocking finding. Phase 4 is locally complete; see
[verification](docs/v2/phase-4-verification.md). Historical failures remain retained.
Phase 4 and its scoped native-identity repair were published as
`0ab09fe966ead3234936b24fe43029152caa8ce8`;
[all five exact-SHA hosted jobs](https://github.com/atharva-m/MarketLab/actions/runs/41221399573)
passed. The failed first published run remains in verification, distinct from
local acceptance. Documentation-only outcome publication/CI is pending at this
entry. Phase 5 was separately approved on November 2, 2026 under its
[pre-code contract](docs/v2/phase-5-copilot-memos.md), with independent contract
review before runtime changes/model dispatch, prescribed coder/reviewer and full
local acceptance. Independent pre-code design review passed; implementation and
literal frozen prompt/corpus review remain pending. No Phase 5
acceptance is claimed. Phases 6-9 remain proposals requiring separate approval.
NO COMMIT OR PUSH is authorized for Phase 5.
No infrastructure purchase or original-service deployment is
authorized. Historical ROADMAP.md and milestone contracts remain intact.

Scope amendment, October 28, 2026: the user confined the platform to Binance
spot. Instruments and dates may generalize within Binance; other venues and
derivatives are excluded throughout Phases 2-9. Canonical CSV/Parquet imports
remain limited to Binance-origin trades. This documentation amendment does not
authorize implementation. The prior Phase 1 review applies to the archived
document revision; see the [amendment record](docs/v2/phase-1-verification.md#binance-only-documentation-amendment-october-28-2026).

Phase 1 deliverables: [contract](docs/v2/phase-1-contract.md),
[compatibility matrix](docs/v2/compatibility-matrix.md),
[acceptance matrix](docs/v2/acceptance-matrix.md), and
[actual verification](docs/v2/phase-1-verification.md).

Each phase produces a reviewable deliverable and has an explicit completion gate.
Implementation uses coder `gpt-6.1-sol/high`, followed by independent read-only
reviewer `gpt-6-astra/medium`. Resolve blocking findings before advancing.

## Phase 1 — Contracts and compatibility design

Define the generalized platform before changing runtime behavior.

- Specify instrument identity, canonical CSV/Parquet inputs, required metadata,
  provenance, timestamp/decimal rules, and immutable dataset identity.
- Define versioned import/research interfaces, capability discovery, resource
  limits, and migration strategy.
- Define distributed publication, worker compatibility, customer isolation,
  authentication, and authorization contracts.
- Inventory existing behavior and establish protected artifact hashes and
  original-service snapshots.
- Update roadmap and contributor instructions while retaining historical
  authority and evidence, only after explicit approval of Phase 1.

**Completion gate:** reviewed contracts and acceptance matrix covering all
subsequent phases. No application behavior changes.

## Phase 2 — Generalized instruments and ingestion

Status: implemented; actual official/CSV/Parquet and full suite/package checks
and six native crash boundaries passed, with final preservation and owned cleanup.
Independent closeout review passed with no unresolved blocking finding. Phase 2
is complete. See
[contract](docs/v2/phase-2-ingestion.md) and
[actual verification](docs/v2/phase-2-verification.md). Deliver CLI/shared services
only in this phase; public v2 discovery/uploads remain Phase 4.

Allow supported Binance spot data beyond BTC/ETH and January 2025.

- Add a Binance spot instrument registry with base/quote assets and display
  metadata; retain the qualified `binance:spot:<source_symbol>` identity.
- Introduce forward migrations with generalized v2 tables and a unified read
  catalog; retain legacy table constraints, records, and artifact identities.
- Generalize Binance daily archive ingestion.
- Add Binance-origin canonical CSV/Parquet imports through the CLI and durable
  ingestion jobs; reject non-Binance sources and preserve supplied quote quantity.
- Preserve checksum verification, exact normalization, immutable daily partitions,
  idempotency, retries, and fenced publication.
- Enforce existing ingestion resource limits independently of calendar dates.

**Completion gate:** actual ingestion for another month, another Binance
instrument, and equivalent Binance-origin canonical CSV/Parquet files with
retained source provenance. Non-Binance inputs are rejected. Original datasets
remain unchanged and readable; malformed inputs and identity collisions are
rejected.

## Phase 3 — Generalized analytics and research

Status: implemented under the independently reviewed
[pre-code contract](docs/v2/phase-3-research.md). Final-source quality/backend,
retained legacy, independent actual numerical, cold, crash/cache and rebuilt
package gates passed. All eight database backup/restores, exact owned cleanup
and final preservation passed, with no unresolved technical blocker before cleanup.
Final independent `gpt-6-astra/medium` documentation/post-cleanup review passed with
no unresolved blocking finding. Phase 3 is locally complete. Actual outcomes belong in
[verification](docs/v2/phase-3-verification.md). Deliver shared services, CLI and
only numerical v2 HTTP adapters; metadata discovery/UI/uploads remain Phase 4,
and v2 memo enqueue remains Phase 5. No commit or push is authorized.

Make registered data usable throughout the numerical platform.

- Replace fixed symbol/date validation with instrument identity and registered
  coverage.
- Add generalized research contracts while retaining legacy request handling.
- Preserve current bars and market-profile, two-instrument comparison, and
  volatility-cluster calculations.
- Require matching quote assets for cross-instrument comparisons.
- Enforce explicit partition, history, warm-up, and bucket limits.
- Preserve pinned dataset versions, result provenance, cache isolation, and
  historical result readers.

**Completion gate:** new datasets support actual numerical runs; missing coverage
and incompatible selections fail clearly. Original BTC/ETH numerical results and
protected hashes remain exact.

## Phase 4 — Metadata-driven UI and Binance file imports

Status: locally complete October 31, 2026, with independent implementation,
acceptance, backup/export and cleanup reviews passed and no unresolved blocker.
The October 31 [completion amendment](docs/v2/phase-4-completion.md) bounded the work
and supersedes conflicting acceptance/harness/closeout requirements in the
[original pre-code contract](docs/v2/phase-4-ui-imports.md). The user authorized
coder `gpt-6.1-sol/high`, independent read-only reviewer `gpt-6-astra/medium`, and
cleanup of unnecessary earlier scaffolding with evidence/data preservation.
Actual three-engine workflows, the exact 4 GiB transport boundary and retained
accounting, source-qualified regression gates, seventeen database dump/restores,
two package exports, original/protected preservation and exact owned cleanup
passed; observed outcomes are in [verification](docs/v2/phase-4-verification.md).
Redundant loose helper source/drafts were consolidated into a verified archive
and unnecessary bytecode removed; evidence/data/dumps remain retained.
Published SHA `0ab09fe966ead3234936b24fe43029152caa8ce8` passed all five jobs in
[exact-SHA hosted run 41221399573](https://github.com/atharva-m/MarketLab/actions/runs/41221399573).
The initial failed publication and repair history remain in verification;
documentation-only outcome publication/CI is pending at this checkpoint.
Original-service deployment is unauthorized. Earlier scope/status statements
remain historical.

Make the generalized capabilities usable without editing application code.

- Add instrument, coverage, and capability discovery interfaces.
- Derive catalog labels, instrument choices, date defaults, chart boundaries, and
  validation text from metadata.
- Add bounded browser uploads and import status using the same durable pipeline
  as the CLI.
- Provide Binance-origin canonical templates, explicit metadata entry, and
  actionable import errors, including rejection of unsupported venues/markets.
- Show onboarding for empty catalogs and explicit workload limits for large
  selections.
- Keep historical reports and demo media accurately labeled.
- Reuse existing official ingestion and numerical services through narrow local
  HTTP adapters; preserve legacy routes/readers and keep v2 model/memos Phase 5.
- Apply reviewed local 100 GiB committed+reserved data, four staged-upload and
  eight running-v2-job ceilings through the shared exact capacity-root lock,
  preserving physical/per-run limits and retained failed-generation charges.
- Rehearse only necessary forward v2 migrations on owned copies with verified
  backup/restore; original services are never operational targets.

**Completion gate:** browser acceptance demonstrates import → catalog → selection
→ research → charts for new instruments and dates, with correct text and no hidden
January/BTC/ETH assumptions in Chromium, Firefox and WebKit. Require actual official
and canonical workflows, upload/cancellation/crash/admission races, unchanged
legacy/generalized numerical gates including cold all-62, final-source suites and
package checks, independent review, backups, preservation and owned cleanup.
Use one active runner/lifecycle helper and separate functional, lifecycle, and
sampled-resource gates. Finish the actual three-engine campaign and exact 4 GiB
browser transport boundary; retain valid source-linked completed gates and rerun
only affected checks. Current owned inventory, final dumps/restores/preservation,
and safe cleanup close the phase; global process/ancestry/thread forensics do not.

## Phase 5 — Generalized copilot and memos

Status: LOCALLY COMPLETE (November 4, 2026). Independent implementation,
actual acceptance and final backup/cleanup reviews passed. All mandatory P5-01
through P5-05 gates, both full cohorts, browser and compatibility checks are
recorded in [verification](docs/v2/phase-5-verification.md). Model/settings,
validators and limits remain unchanged; all failures and data remain retained.
No commit, push, original-service deployment or Phase 6 work is authorized.

Original approval (November 2, 2026): the user authorized the [contract](docs/v2/phase-5-copilot-memos.md), contributor/roadmap
updates, implementation through coder `gpt-6.1-sol/high` followed by independent
read-only reviewer `gpt-6-astra/medium`, and full local acceptance/preservation.
Resolve blocking contract findings before code or model dispatch. Deliver local
API/CLI/browser adapters and bounded durable workers; no Phase 6+ or deployment.
Use the fixed 9B digest/settings, existing limits and manual numerical service,
preserve legacy outputs and exactly three application-rendered grounded memo
paragraphs. Freeze literal fixtures before scored inference; both actual copilot
60-case cohorts, both memo 20-run cohorts and all P5-01..05 gates remain mandatory.
Source-qualified outcomes and unavailable prerequisites belong in
[verification](docs/v2/phase-5-verification.md). NO COMMIT OR PUSH.

Extend natural-language workflows to the supported catalog.

- Version copilot prompts and output schemas around selected instruments, actual
  coverage, and supported capabilities.
- Resolve Binance spot instrument identities; ask for clarification when asset
  names or quote selections are ambiguous.
- Reject non-Binance venues, unsupported markets, missing coverage, and excessive
  workloads explicitly.
- Generalize memo fact validation and rendering while preserving grounded claims.
- Keep the pinned model initially and treat imported metadata as untrusted input.
- Preserve old completed outputs and reject incompatible queued work explicitly.

**Completion gate:** actual-model evaluations pass for new symbols/dates,
ambiguous requests, unsupported requests, clarification, and grounded memos.
Numerical execution remains independent of model success.

**Milestone reached:** a locally usable Binance spot research platform supporting
registered instruments and dates.

## Phase 6 — Shared artifact storage

Independent pre-code review passed. The [contract](docs/v2/phase-6-storage.md)
binds this phase to the Phase 1 storage protocol and the four mandatory Phase 6
gates. Implementation and local acceptance checks have passed independent review,
including the required SDK/lockfile changes. Owned-resource closeout also passed
independent review. S3 code and tests are implemented, but all S3 test execution and
collection remain explicitly deferred by the user; the completion gate is not
yet satisfied. See [verification](docs/v2/phase-6-verification.md).

Remove the local-filesystem dependency that prevents reliable multi-host execution.

- Introduce local and S3-compatible storage backends.
- Store datasets, research results, memos, manifests, and staged uploads through
  the storage interface.
- Use immutable, attempt-specific objects with verification before fenced database
  registration.
- Retain local temporary files and bounded verified caches.
- Preserve existing artifact identities; provide an explicit, verified
  copy-and-register procedure for moving retained artifacts.
- Add storage configuration, credentials handling, backup, and restore
  documentation.

**Completion gate:** equivalent local/object-store readback, integrity checks,
interrupted-upload recovery, duplicate publication handling, storage-outage
behavior, and retained-artifact migration rehearsal.

## Phase 7 — Distributed worker execution

Execute independent jobs across multiple hosts.

- Add worker identities, capabilities, and execution-contract compatibility checks.
- Run ingestion, research, copilot, and memo workers against shared PostgreSQL and
  artifact storage.
- Preserve database-time leases, fencing, retry budgets, and idempotency.
- Coordinate model admission across workers.
- Support cross-host cancellation, recovery, and result readback.
- Expose worker health, queue age, failures, resource usage, and storage/model
  availability.

**Completion gate:** actual execution on at least two distinct hosts, including
competing claims, worker loss, lease expiry, stale publication, retries,
cancellation, and outages.

Each research run still executes on one worker; distributed execution increases
concurrent capacity.

## Phase 8 — Customer isolation and authenticated access

Package the distributed platform for separate customers.

- Provision separate application services, PostgreSQL instances, storage
  buckets/credentials, Redis services, worker pools, and model endpoints per
  customer.
- Integrate an external OIDC provider with operator-managed membership.
- Implement viewer/operator roles and authorization for APIs, jobs, imports, and
  artifacts.
- Add scoped service credentials, bounded upload/storage quotas, and audit records.
- Provide private-container deployment templates, TLS ingress requirements,
  network boundaries, secret injection, and provisioning procedures.
- Keep public signup, billing, Kubernetes, and automated cloud provisioning outside
  this release.

**Completion gate:** two customer environments operate independently;
cross-customer API, object, upload, job, and credential access attempts fail.
Authentication and role enforcement pass end-to-end checks.

## Phase 9 — Integrated acceptance and operational handoff

Verify the complete platform and document its operating limits.

- Run full compatibility, database, browser, actual-data, actual-model, distributed
  recovery, and isolation acceptance.
- Rehearse clean installation, upgrades, backup/restore, and customer provisioning.
- Measure throughput, latency, storage, and worker resource use against the
  approved limits.
- Publish setup, import, research, operator, recovery, and troubleshooting
  documentation.
- Record actual outcomes, failed invocations, limitations, independent review
  findings, and ownership-checked cleanup.

**Completion gate:** every mandatory acceptance gate passes, original services and
protected artifacts remain preserved, and no blocking review finding remains.
Missing infrastructure or prerequisites leave the corresponding phase incomplete.

## Delivery boundaries

- Complete phases in order; each phase preserves the completed behavior of earlier
  phases.
- Scope covers Binance spot trades, official Binance archives, Binance-origin
  canonical files, existing research workflows, and bounded individual runs.
  Other exchanges, synthetic venue aliases, derivatives, and alternative-provider
  fallback are excluded; the independent legacy synthetic `/trades` subsystem
  remains preserved under its historical contract.
- Initial limits retain 62 daily partitions per submission/research selection,
  17,856 five-minute research buckets including warm-up across instruments, and
  existing chart and ingestion bounds. Catalog growth does not imply unbounded
  individual jobs.
- Equities, derivatives, arbitrary tables, OHLCV-only inputs, streaming feeds,
  currency conversion, column-mapping UI, and splitting a single research run
  across hosts remain deferred.
- Implementation requires full validation. Commits, pushes, infrastructure
  purchases, and deployment require separate authorization; this roadmap performs
  none of them.
