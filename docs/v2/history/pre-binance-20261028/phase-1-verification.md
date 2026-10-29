# V2 Phase 1 — actual documentation verification

Date: October 28, 2026 (America/New_York).
Status: COMPLETE for Phase 1 documentation and read-only verification only.
Independent review found no unresolved blocking finding. Phases 2-9 are not
implemented or accepted by this result.

## Authority and source identity

The user approved implementing the proposed Phase 1 documentation and read-only
verification scope after saving ROADMAP_v2.md. This authorizes the contract,
compatibility/acceptance matrices, source and preservation inventory, independent
review, and scoped AGENTS.md/v2-roadmap updates. It does not authorize runtime
implementation or phases 2-9, tests, migrations, downloads, model invocations,
infrastructure provisioning, service changes, commits or pushes.

Inspected HEAD: `b8ededa67c7bebec3380ecab08dabad791deacdc`. At entry the only
working-tree difference was untracked ROADMAP_v2.md, saved in the preceding turn.
The documentation overlay is not a new Git revision or a tested runtime release.
Historical ROADMAP.md, contracts and verification reports remain unchanged.

## Deliverables and investigation

- [Normative design contract](phase-1-contract.md).
- [Compatibility matrix](compatibility-matrix.md).
- [Future acceptance matrix](acceptance-matrix.md).
- This report, [v2 roadmap](../../ROADMAP_v2.md), and scoped contributor authority.

Source investigation confirmed fixed symbols/dates in ingestion validation,
database migration 0004, workspace queries, analytics, research, copilot/memo
validation and UI controls. Dataset, research and memo publication currently
depend on local paths and filesystem renames. Future interfaces described in
the contract do not exist merely because this documentation specifies them.

## Preservation evidence

Raw, local-only evidence is retained under ignored
`artifacts/v2-phase1-20261028/`; it is not a committed artifact or credential dump.

`protected-before.json` rehashed the 287 paths listed in
`artifacts/r9-20261027/preservation-before.json` (approximately 2.91 GB total).
All 287 paths were present. 285 hashes match that historical baseline. Two
differences are `frontend/package.json` and `frontend/package-lock.json`, changed
by the already committed UI redesign `4f212ac` (Geist font dependencies). Both
are clean against inspected HEAD. Therefore this phase does NOT claim 287/287
equality against R9. The fresh 287-file inventory is the current-interval baseline.
`tracked-before.json` additionally hashes 222 Git-tracked files outside docs,
AGENTS.md and ROADMAP files, including runtime, migrations, scripts and locks.
`inventory-receipt.json` pins the historical and current inventory hashes and
records the reproduction commands. Reproduce the protected comparison by reading
each `files[].path` from the pinned historical baseline, computing SHA-256 and
length with `Get-FileHash`/`Get-Item`, and comparing by exact relative path. For
current-interval preservation compare against `protected-before.json`, not the
older R9 expectation. Do not print file contents or credential values.

`services-before.json` contains sanitized inspection of five existing containers:
the original API/PostgreSQL/Redis and two README PostgreSQL/Redis containers.
It includes IDs, images, starts, restart counts, health, mounts, port mappings
and Compose ownership labels; environment variables and credentials are omitted.
All five were running with restart count zero; the three originals reported
healthy, while the README containers had no Docker health status configured.

`historical-service-comparison.json` shows the three originals match the R9
post-GPU snapshot in IDs, image IDs, start times, restart counts, mounts and
health. Additional README containers were observed, not created or cleaned by
this phase. No service was stopped, restarted, reconfigured or removed.

These are point-in-time observations, not continuous uptime monitoring. They
do not resolve the historical uptime gap or clock discrepancy. No API endpoint
request was issued: the readiness endpoint writes a temporary storage probe,
so Docker's observed health status is recorded without claiming fresh endpoint
or database acceptance. Future operational acceptance remains separately gated.

An intermediate rehash in `preservation-after-draft.json` matched all 287 fresh
protected hashes and all 222 tracked non-documentation hashes. The subsequent
`services-after.json` matched every captured field for all five containers,
including port mappings and ownership labels. `closeout-receipt.json` pins the
final document hashes and preservation/service/document-check receipt hashes.
The completed `preservation-final.json` repeated that comparison: 287/287 current
protected files and 222/222 tracked non-documentation files matched. No comparison
failure was hidden by replacing the baseline. `document-check.json` records zero
broken relative file links across the v2 documents/roadmap and two syntactically
valid fenced JSON examples; placeholders are explicitly marked, not valid source
hashes to submit. Static whitespace inspection passed for the untracked design
documents; `git diff --check` passed for tracked edits. These are documentation
checks, not application tests or implementation acceptance.

## Failed inspection attempts and limits

- Some exploratory `rg` invocations using wildcard directory operands failed
  under Windows path handling; narrower actual directories/files supplied the
  inventory. These were inspection errors, not application failures.
- An initial search assumed a `tools` directory; the project uses `scripts`.
- Initial Docker listing was denied by the sandbox. An approved read-only
  elevated listing/inspection succeeded. No daemon restart or workaround changed
  service state.

No test suite, build, model evaluation, migration rehearsal, dataset download,
browser flow, object-store operation or multi-host acceptance ran. The future
acceptance matrix is a specification, not evidence of passing those gates.

## Review and closeout

The prescribed coder gpt-6.1-sol/high authored the three design documents in
`/root/phase1_coder`. Independent read-only reviewer gpt-6-astra/medium in
`/root/phase1_reviewer` inspected source facts, contracts, matrices and preservation
receipts, then rereviewed the corrections. Its substantive final conclusion was
no unresolved blocking finding. Missing future infrastructure is a prerequisite
for later acceptance, not evidence that any future capability is operational.

Initial independent review identified four blocking design issues: overly broad
trade-ID conflict rejection across corrected immutable versions; a Phase 3 memo
gate ahead of Phase 5 memo tables; missing explicit import renewal/lifecycle
payloads; and replayable direct upload URLs bypassing generation/quota limits.
All four were corrected and independently rereviewed:

1. Corrected source values can create immutable daily alternatives. Conflicts
   are checked within a version and the explicitly selected multi-day snapshot,
   without rewriting historical artifacts or globally banning corrections.
2. Phase 3 cold/memo preservation explicitly uses the legacy execution path;
   generalized memo enqueue/execution remains a Phase 5 gate.
3. Import create/finalize/renew/cancel bodies, revisions, terminal versus retriable
   states, state diagram, and consistent import/job/version lock order are defined.
4. Client uploads use a controlled proxy with exclusive, fenced generation claims,
   exact length/hash checking, all-generation quota accounting and explicit output
   reservation caps. Reusable client presigned PUTs are excluded.

The roadmap's initial constraint-removal wording was aligned with generalized v2
tables retaining old CHECK constraints. Reviewer follow-up on upload lifecycle
and normalized-output quota bounds was also resolved. Historical source checks,
current snapshot facts, future design decisions and unrun runtime gates remain
separate throughout the documents.

Final changed document set is AGENTS.md, ROADMAP_v2.md and the four docs/v2 files.
Raw evidence stays ignored. No runtime source, tests, migrations, dependency locks,
models, original services or historical reports were changed. No commit/push or
later-phase implementation occurred. Phase 1 completion creates no authority to
start Phase 2; the user must authorize it separately.
