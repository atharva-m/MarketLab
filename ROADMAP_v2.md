# Phased delivery: Binance spot MarketLab

Status: Phase 1 documentation and read-only verification completed on October 28,
2026, with independent review and no unresolved blocking finding. Phase 2 is
authorized under the [pre-code contract](docs/v2/phase-2-ingestion.md).
Implementation, final-source quality/backend/package checks and the actual
official/CSV/Parquet campaign and six native process-crash boundaries passed.
Final preservation, ownership-checked cleanup and independent closeout review
passed with no unresolved blocking finding. Phase 2 is complete.
The user subsequently authorized publication of verified Phase 2 and exact-SHA
hosted CI. The first published run failed its integration disk-capacity gate;
a scoped CI-only capacity repair and exact-SHA rerun are pending. Local acceptance
remains complete. Phases 3-9 remain proposed and require separate
authorization. No infrastructure purchase or original-service deployment is
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

**Completion gate:** browser acceptance demonstrates import → catalog → selection
→ research → charts for new instruments and dates, with correct text and no hidden
January/BTC/ETH assumptions.

## Phase 5 — Generalized copilot and memos

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
