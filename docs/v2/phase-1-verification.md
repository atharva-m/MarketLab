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

## Binance-only documentation amendment (October 28, 2026)

The user subsequently instructed: "Then let's confine this platform only to
Binance. Change the documentation to specify that". This authorizes narrowing
future documentation, not Phase 2 implementation. The preceding Phase 1 report
is retained as originally written; its review, document hashes and preservation/
service receipts apply to the earlier revision and observed interval only.

Exact prior contract, compatibility matrix, acceptance matrix and this report
were copied before amendment under
[historical documents](history/pre-binance-20261028/README.md). Their SHA-256 values:

| Historical file | SHA-256 |
| --- | --- |
| `phase-1-contract.md` | `6c842f522d8eaf9afa7fc7de8c777cb5c261665deaaf2f85e325ba2d6408493f` |
| `compatibility-matrix.md` | `c28a11338594386d94001fe6d03fd6e698fb2a8e1908815b695cafebff036310` |
| `acceptance-matrix.md` | `e76c39d86d4d909bdbe05fda24ae9e82320562aa96676da58a6d30be6570c8dd` |
| `phase-1-verification.md` | `aeb398c1d1d0b621ad4ce12b829cef496b9d1874f35232b91dbe936a5271cef6` |

Current roadmap/contracts/matrices and contributor instructions now fix venue to
Binance and market to spot, retain generalized instruments/dates, restrict
canonical imports to Binance-origin trades, numeric source IDs and supplied quote
quantity, and reject other venues/derivatives/aliases. P2-02 now compares canonical
CSV/Parquet imports of the checksum-verified SOLUSDT 2025-03-01 day against the
archive reference with source/conversion evidence. Later UI/model gates use
Binance instruments and unsupported-venue rejection instead of multivenue support.
The canonical format remains supported future scope; it does not authenticate
venue origin. No generalized runtime capability is claimed.

Amendment static checks and independent review outcomes are pending until
recorded below. No application tests, data acquisition, migrations, model calls,
service operations, commit or push are part of this amendment.

The coder gpt-6.1-sol/high completed the documentation changes. Static inspection
checked seven current/index documents and 69 relative links, including frozen
snapshot links resolved in their original `docs/v2/` context: zero missing files.
Both fenced JSON examples parsed; current document whitespace inspection passed;
the original report remains an exact byte prefix of this appended report.
`git diff --check` passed (Git reported its existing LF/CRLF conversion warning).
Two initial local editing/check invocations failed on Windows' default cp1252
text decoding before those operations completed; explicit UTF-8 reruns passed.
No failed invocation was counted as a pass. Independent review is pending.

Independent read-only reviewer gpt-6-astra/medium completed review of this
Binance-only amendment and found no unresolved blocking finding. The reviewer
independently confirmed that all four historical snapshot hashes match the prior
Phase 1 closeout receipt, the preceding report remains an exact byte prefix,
relative links across the seven current/index documents resolve, both fenced JSON
examples parse, and `git diff --check` passes. The earlier "pending" statements
above describe the draft and coder-closeout stages; this recorded review resolves
them. Documentation amendment status is COMPLETE. This grants no Phase 2 runtime
implementation or publication authority and adds no runtime acceptance claim.
