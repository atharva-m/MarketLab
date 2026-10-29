# V2 Phase 2: actual verification

Date: October 28, 2026 (America/New_York).
Status: PHASE 2 COMPLETE; final-source quality/backend/package, actual-data,
native crash, preservation, owned cleanup and independent read-only closeout
review passed. No unresolved blocking finding remains.
Verified Phase 2 was published as `eca54fe68af357ca16973aa98ed7dcca3a266973`.
Its exact-SHA hosted integration job failed six capacity-dependent tests;
four other jobs passed. The first capacity repair's hosted run then failed the
50 GiB prerequisite before tests. A further scoped CI capacity repair is pending.
Local acceptance remains separate from hosted outcomes.
Earlier checkpoint statuses below are retained as historical observations.

## Authority and source

The user approved the detailed Binance-only Phase 2 scope, contributor/roadmap
updates, contract BEFORE code, prescribed coder and independent read-only review,
implementation and full acceptance. No commit/push, original-service deployment
or unrelated system change. The [contract](phase-2-ingestion.md) defines scope.

Inspected HEAD is `b8ededa67c7bebec3380ecab08dabad791deacdc`; at pre-code inspection,
the existing overlay comprised AGENTS.md, ROADMAP_v2.md and docs/v2 documentation.
Coder gpt-6.1-sol/high inspected
migration head 0007_memos, legacy source/normalization/jobs/publication/CLI/settings,
dependency manifest, existing acceptance scripts and CI read-only. No needed new
dependency was identified; any dependency limitation needs a scoped amendment.

## Pre-operation evidence

Parent captured ignored `artifacts/v2-phase2-20261028/protected-before.json`:
287/287 protected files match the Phase 1 current baseline, not the older R9
expectation. Sanitized `services-before.json` observes all five original/README
containers running, restart counts zero, original three healthy, with IDs/images/
mounts/start/health/ownership/ports. Initial sandbox Docker inspection was denied;
approved elevated read-only inspection succeeded without restart/reconfiguration.
These are point observations, not continuous uptime; historical gap/clock limits
persist. Fresh endpoint/database/backup prerequisites remain pre-operation gates.

## Pre-code deliverables and checks

Drafted concrete contract: eight table definitions, FKs/CHECKs/indexes/cross-row
invariants, strict identities, local immutable source staging/accounting, durable
claims/retry/cancellation/publication, CLI/read services, frozen acceptance and
rollback/cleanup. Current authority/roadmap updates preserve historical entries.

An initial attempted documentation write exceeded Windows process command length
(CreateProcessW error206) before execution; the apply_patch write succeeded.
Static checks and independent pre-code review are pending. No runtime code,
application suite, migration, source download, inference, provisioning, service
operation, commit or push has run in this pre-code milestone. P2-01..P2-07 and
P2-P/P2-R remain NOT RUN.

Pre-code static inspection subsequently checked all four changed/current Phase 2
authority/roadmap/contract/verification documents: 51 relative links resolved,
zero trailing-whitespace findings, and git diff --check passed (existing LF/CRLF
conversion warning only). Independent pre-code review remains pending. These are
documentation checks, not application acceptance.

Independent pre-code reviewer gpt-6-astra/medium found three blocking issues:
local uploaded state could strand work after a crash; official identity metadata/
source hash target needed exact definition; arbitrary-file provenance/renumbering/
derived-quote fraud detection was overstated. Corrections made CLI verified-copy
and enqueue one staging-lease transaction, fixed official ZIP-byte identity and
metadata keys/values, and distinguished mechanical validation from full provider-
reference comparison/operator origin declarations. Rereview found no unresolved
blocking finding. The pre-code contract and hash receipt were frozen under ignored
artifacts/v2-phase2-20261028 before runtime edits. Full R1/R2 contracts were read;
an initial guessed R1 filename failed before the correct complete read.
Implementation is now authorized/in progress; runtime acceptance remains pending.


## Implementation and focused validation (in progress)

Implemented the v2 runtime/forward migration/CLI and separate source-normalization
modules through coder gpt-6.1-sol/high, including a delegated coder for source,
normalization and artifact verification. The independent reviewer inspected
incremental changes and corrections. Early findings fixed the canonical-claim
heartbeat interleaving, SQL NULL token CHECK, forward-only downgrade, replay after
caller input removal, strict malformed metadata handling, observed coverage,
Windows SQLite connection lifetime, accurate decoded bytes, decimal leading-zero
handling and source/build provenance. A valid but source-divergent orphan is
rejected; an adopted winner supplies the registered quality fields.

Focused source/control/real-PG checks reached 103 passes, then added exact key/
control-byte/row/partition boundaries and both publication/cancellation orders.
The added boundary/control/real-PG subset passed 29 cases. These are actual local
invocations, separate from the full-suite and actual-provider gates still pending.
Initial failures included inaccessible default pytest temp directory (rerun under
owned ignored basetemp), Windows long-path SQLite open (scoped safe-path repair),
adjacent SQL literal whitespace, an untyped NULL filter and a SQLite cursor left
open on a resource-error path. Failed invocations remain failures; reruns do not
erase them. Initial Ruff/mypy failures during implementation were corrected.

A targeted isolated resource gate found an actual Parquet decoder allocation gap:
the 1,637-byte retained file passed metadata-only admission and Arrow attempted a
512 MiB allocation. The process-local 256 MiB Job limit safely rejected that
allocation; receipt remains under ignored evidence. This invocation FAILED the
required preallocation bound. Parent natively cancelled the first actual-data
invocation `p2-bd913822dc10409e9df316c24d9b5c6d`; it exited failed and is not a pass.

The scoped contract supplement and defensive bounded page-header preflight now
validate V1/V2/dictionaries and cumulative column/group sizes before Arrow data
decode. 105 focused parser/control/page tests passed, including valid encoding
combinations and rejection of that retained fixture before data decode. Independent
repair review and fresh-source full/actual/crash gates remain pending. No original
service, lock/dependency, model/prompt or global/system setting changed.


## Corrected-source review and acceptance checkpoint

Independent read-only reviewer gpt-6-astra/medium cleared the bounded-page repair
and follow-up flat row-count/cancellation corrections with no unresolved blocking
finding before the second runtime freeze. Admission of enabled instruments now
holds a registry share lock so disable and import admission serialize; that
correction was independently reviewed as well. All eleven v2 runtime modules
passed Ruff lint/format and strict mypy. The corrected parser/control/page subset
passed 110 cases, including ordinary V1/V2/dictionary/compression/null combinations,
flat column/footer count mismatch, finite header bounds, cancellation after some
headers, exact input boundaries, and the retained predecode resource regression.
These focused checks do not claim the final full or actual-provider gates passed.

`source-freeze-second.json` pins inspected HEAD
`b8ededa67c7bebec3380ecab08dabad791deacdc`, the dirty runtime overlay and execution
fingerprint `ff7621986d66a93f2d25a6c31e2d838cba0949ddb59b5d52841590787e77929d`.
The lock SHA-256 is
`730f02bec94d1f824a2cadf74f60cf5dcc246faa55004d5d060b92931224618f`.
The prior `e770a9d3a0d67fb3834899e1836e632b25ea960e35aa17d66e3ac56f3cf873c7`
source and failed/interrupted invocation remain retained separately. Current
actual-data and full-suite invocations are running/pending at this checkpoint.

Parent operational verification observed:

- Fresh and populated forward upgrades passed; all captured legacy rows and
  constraints matched before/after (`migration-final-rehearsal.json`).
- Separate v1-state rehearsal at 0007 seeded queued/running/retry_wait/succeeded/
  failed jobs and attempts, upgraded 0008, and preserved rows/constraints/budgets
  exactly. V2 could not claim v1 work; incompatible v2 stayed queued with zero
  attempts (`v1-states-migration.json`). Migration SHA is
  `dbb866aa1f6a62fa51e35fd532a62787d518ec75885e5021844fc26ef874f4ef`.
- Unified full readback of all retained 62 legacy dataset versions passed for
  230,311,900 rows in 385.75 seconds (`legacy-62-readback.json`). The first
  invocation used a stale historical root and failed; corrected actual retained
  root invocation passed, preserving that failure.
- Frontend type/lint/build, 20 component and 66 browser cases across the three
  engines passed; demo lint/types and 11 tests passed. Initial sandbox EPERM and
  occupied existing 5173 browser-server attempts remain retained. Owned 55173
  browser override passed without modifying the existing server.
- All five original/README container captured fields and endpoints remained
  unchanged at the observed 19:51 UTC checkpoint; this is not continuous uptime.
  Original database backup and isolated restore were captured and verified.
- Independently acquired exact official BTCUSDT 2025-02-01 and SOLUSDT 2025-03-01
  archives matched their official checksums. Their separate acquisition proves
  input availability/reference bytes, not application ingestion acceptance.

Final application/full/actual/crash/package gates, post-operation preservation,
retained dumps and exact ownership cleanup remain pending. No hosted CI,
commit/push, original-service rollout or Phase 3 implementation is claimed.


Current documentation static inspection checked ten current authority/roadmap/
README/v2 documents, 81 relative links and four fenced JSON examples: all passed,
with zero trailing-whitespace findings. `git diff --check` passed with existing
LF/CRLF conversion warnings. Frozen Phase 1 historical files remain unchanged.
These are documentation checks while runtime acceptance continues.


## Corrected resource regression and migration test expectations

On the second frozen source, the contained resource rerun passed: the original
1,633-byte Parquet was accepted; the retained 1,637-byte inconsistent-page file
was rejected by bounded preflight with V2Error and no decoder cause. Arrow peak
allocated bytes were zero for the rejected file; native peak working/private
measurements were 69,423,104/45,506,560 bytes under the process-only 256 MiB cap.
`resource-after-receipt.json` retains this actual outcome. The earlier failed
512 MiB allocation attempt is preserved separately and is not rewritten as a pass.

The first full locked run passed quality and 1,131 offline cases (213 integration
cases deselected). Its real PostgreSQL invocation executed all 213 cases and
FAILED with 211 passes/two failures: old integration assertions still expected
0007 and the exact old 17-table set after upgrading to head. Scoped test-only
updates now expect 0008 and the exact old 17 plus eight new v2 tables, retaining
all old column/type/primary-key/FK/constraint assertions. Both affected tests
passed their focused rerun (two passes in 3.22 seconds); no runtime fingerprint
changed. The complete PostgreSQL rerun remains pending at this checkpoint.

Owned current-image API/CLI/legacy inspect/v2 adaptation and owned Redis-outage
package checks passed seven checks. Initial packaging context/PAX interpretation
and read-only readiness-root invocations remain failed and retained; the successful
harness used an owned writable readiness root plus read-only retained legacy data.
No original service or storage root was changed by these harness corrections.


## Exact UTC read-path correction and third source checkpoint

Read-only profiling of one owned first batch measured page admission at 0.1254s,
16,384-row Python conversion at 8.7396s and validation of 1,000 rows at 0.02477s.
The profile recorded 16,391 import lookups and 114,725 filesystem stat calls,
identifying repeated optional-import lookup during Arrow timestamp conversion as
the dominant observed cost. It does not establish a controlled overall speedup.
The receipt is `bounded-verifier-profile.json`.

The second BTCUSDT worker completed SUCCESSFULLY in approximately 953 seconds.
It did not time out, and no native job cancellation was accepted. The parent was
then independently reading back the completed artifact; after verifying exact
owned Python PIDs 24672/27004, the parent processes were stopped to open the
reviewed repair window. Invocation two exited nonzero and its parent readback is
INTERRUPTED, not a full-campaign pass. `actual-second-interruption.json` records
this distinction; the successful job/artifact remains readable and unchanged.
All five original/README service fields remained exact at the interruption
snapshot. Neither timing nor interruption is relabeled as a source timeout.

The reviewed correction retains exact Arrow timestamp(us, UTC) admission and
converts physical int64 microseconds through integer epoch arithmetic before
Python row materialization. Decimal/ID/flag values, row order, logical encoding,
source hashes and dataset identity are unchanged. Native control datetimes now
serialize in UTC even with a non-UTC database session; date-only values stay dates.
No optional dependency was installed. Ordinary Arrow row equivalence, signed
microseconds, exact day boundaries/next-day rejection, null/wrong-timezone/unit/
int64-range cases passed. Fifteen real-PG cases passed, including non-UTC registry,
job/import/status/coverage/manifest output, actual separate CLI import/replay after
caller-file removal and separate-worker readback, plus rejection of prior-source
queued work with zero attempts. The offline v2 parser/control/page/UTC subset
passed 125 cases. Ruff lint/format and strict mypy passed all eleven v2 modules.
Independent read-only review approved this correction before the next freeze.

`source-freeze-third.json` pins execution fingerprint
`a15d48bee4a5e19ac44a35bef2fbf54656f573341bfeaf87f95fc5bcee00ebba`.
Actual invocation `p2-fa9d625881bc477aaf8814bb7d66b6b8` and full invocation
`full-94483899` are running at this checkpoint. Existing ff762 completed artifacts
retain their original build provenance; new work independently verifies source
and logical equality before reusing an immutable version. This is not queued-work
upgrading or rewriting old manifests. Final-source actual-data/full/crash/package,
post-operation preservation, backup/cleanup and final review remain pending.


## Final-source full checks and gate map (acceptance continuing)

On `a15d48bee4a5e19ac44a35bef2fbf54656f573341bfeaf87f95fc5bcee00ebba`,
`full-94483899` passed locked lint/format/mypy, 1,146 offline cases in 64.96s and
215 real PostgreSQL cases in 198.83s, with no skips. Captured execution identity
matched before/after. These are the final-source local suite outcomes; earlier
failed PostgreSQL and source/resource invocations remain retained separately.
Final-source owned-image package/API/CLI/legacy/v2 adaptation/Redis-outage checks
passed all seven checks. This is isolated package acceptance, not original rollout.

Actual invocation `p2-fa9d625881bc477aaf8814bb7d66b6b8` PASSED in 788.443936s on
the final execution fingerprint. Both official days passed ingestion, full
readback and independent raw-ZIP reference comparison. BTCUSDT 2025-02-01 has
2,588,786 trades with logical SHA-256
`ef7471ac356a3ffb44c8de6a78fde6426a2dd5b21a4e9f73a680091312a68f3e`;
SOLUSDT 2025-03-01 has 1,658,774 with logical SHA-256
`b7da2fe5f01a503b01db6bede434c69bcd21839488cda4dbbcc4dd4baa3ec7a6`.
The pre-existing BTC version's manifest hash remained exact through independent
source verification and reuse.

The independent retained-SOL conversion produced a 191,229,130-byte CSV and a
16,422,824-byte Parquet. Separate subprocess CLI imports and workers fully read
back 1,658,774 rows each, matching the official SOL logical hash above. Official,
CSV and Parquet source identities are distinct. Same-key replay and fresh-key
same-source reuse passed. The exact receipt is
`actual/p2-fa9d625881bc477aaf8814bb7d66b6b8/p2-fa9d625881bc477aaf8814bb7d66b6b8-receipt.json`;
the conversion/harness SHA-256 is
`3723a9e42fc044e935edb006838735639e3edcf63c65a67116cef5d9f700ba2e`.
Campaign-wide memory remains unmeasured. The separate final-source contained
resource receipt passed predecode rejection with zero Arrow allocation; that
targeted measurement is not a whole-campaign memory claim.

| Gate | Observed status at this checkpoint |
| --- | --- |
| P2-01 official new dates/instrument | Both exact official days passed current-source ingestion, checksums, full readback and independent raw-reference comparison |
| P2-02 equivalent canonical formats | Actual CLI CSV/Parquet imports, full readbacks and independent raw-SOL conversion/oracle passed with equal counts/logical hashes and distinct source identities |
| P2-03 precision/time/types | Focused strict-input/resource cases and final full offline/real-PG suites passed |
| P2-04 IDs/registry | Registry, numeric order, unsupported venue/market, same-ID instrument isolation, disabled-read semantics and UTC controls passed focused/full suites |
| P2-05 identities/replay/conflicts | Controlled duplicate/conflict/correction/cross-day selection/readback tests and actual same-key/fresh-key source reuse passed |
| P2-06 resource/durable boundaries | Final suites include bounds and competing real-PG claims/heartbeat/cancellation/publication; contained decoder-bound correction and all six native process-crash boundaries passed |
| P2-07 migration/legacy | Fresh/populated/v1-state migration, 62-version legacy readback and final legacy/package/full suites passed |
| P2-P preservation/cleanup | All seven dump/restores, ownership-checked cleanup and post-cleanup 287/287 protected hashes/five original service snapshots/endpoints passed |
| P2-R independent review | Independent gpt-6-astra/medium pre-code, scoped repairs and final source/evidence/closeout review passed with no unresolved blocking finding |

Lower-limit boundary fixtures remain labeled and are not physical 4 GiB/20M stress
passes. Canonical provenance stays operator-declared unless independently matched
to retained Binance references; ID/quote mutation comparison tests do not promise
universal fraud detection. No Phase 3 analytics/UI/model support is claimed.


## Native crash recovery and retained backups

Final-source native crash invocation `p2-a168828b33af4c11af513f9f8daba8af` PASSED
all six boundaries in 70.872366s, with a minimum 61-second native wait and no
database lease-clock edits. The receipt's `native_expiry_wait_seconds` value of
65.536580s includes that wait plus staging expiry/recovery/verification, rather
than measuring lease expiry alone. Two terminated staging copies expired terminally
without jobs. Claimed, normalized and renamed-before-registration work recovered
on attempt two; committed-before-response work retained its success on attempt
one. No pre-registration artifact was discoverable. Stale fencing mutations were
rejected and verified renamed orphan bytes remained exact through adoption.
The receipt is
`crashes/p2-a168828b33af4c11af513f9f8daba8af/p2-a168828b33af4c11af513f9f8daba8af-receipt.json`.
Crash fixtures are explicitly synthetic protocol fixtures, not provider-origin
acceptance. Campaign-wide memory was not measured.

The final active database dump contains 25 tables and is 92,803 bytes. All seven
owned source databases were dumped and restored into isolated verification
databases: rows, columns, indexes and constraint attributes matched exactly.
CHECK definitions matched after PostgreSQL server reparsing; the earlier literal
definition comparison failed on server canonical rewriting and remains retained.
Before cleanup, all 287 protected file hashes and all five original/README
containers' captured fields/endpoints matched. The owned storage inventory retains
54 files totaling 452,282,105 bytes. Conservative reservation charges totaling
77,309,804,544 bytes remain recorded in the retained database dump; no automatic
garbage collection or silent charge reset occurred. Guarded owned runtime cleanup,
post-cleanup preservation and final independent evidence review remain pending.


## Owned cleanup and final preservation

Ownership-checked cleanup PASSED: five owned containers, two exact captured
volumes, the private network and the remaining labeled image were removed.
Earlier build images were explicitly confirmed absent; the owner-filtered image
inventory is empty. No original container, image, listener or data root was
removed or restarted. `preservation-after-cleanup.json` confirms all 287/287
protected hashes and all five original/README containers' captured fields and
endpoints remain exact at the final observation. Local datasets, failed bytes,
raw evidence, dumps and conservative reservation records remain retained.
Preservation is bounded to the captured observations and does not repair the
historical service-uptime gap or clock discrepancy.

All mandatory local acceptance gates are now passed on the final source, with
historical failed/interrupted invocations preserved as recorded above. Final
independent read-only evidence/closeout review remains pending. No hosted CI,
commit/push, original-service rollout, model invocation, new dependency or Phase 3
implementation occurred under this phase.


## Independent closeout review and final status

Independent read-only reviewer `gpt-6-astra/medium` found no unresolved blocking
finding on the final `a15d48bee4a5e19ac44a35bef2fbf54656f573341bfeaf87f95fc5bcee00ebba`
source and scoped repairs. Review covered actual-data/oracle and regression
evidence, package/resource/native crash gates, backups including PostgreSQL CHECK
reparsing, owned cleanup, preservation and the stated limits. Phase 2 is complete.
Earlier pending statuses describe their checkpoints and are now resolved by this
closeout, without changing the recorded failures or earlier-source outcomes.

Final current-document static inspection passed for ten documents, 81 relative
links and four fenced JSON examples, with no trailing whitespace. Frozen Phase 1
snapshots remain unchanged and retain their original relative-link context.
`git diff --check` passed with existing LF/CRLF conversion warnings only.


## Publication authorization (October 28, 2026)

After the reviewed local closeout, the user authorized committing/pushing verified
Phase 2, checking the exact published SHA's hosted CI and fixing actual Phase 2
CI failures through coder `gpt-6.1-sol/high` followed by independent read-only
reviewer `gpt-6-astra/medium`. Earlier no-commit/push statements describe their
historical acceptance authority and are superseded only within this publication
approval. At this checkpoint no commit, push or hosted result is claimed.

The publication audit must exclude raw artifacts, datasets, archives, credentials,
environments, weights and generated media, preserving the unchanged existing
README GIF. Protected artifacts, original services, historical failures and local
measurement limits remain preserved. No original rollout, Phase 3 or unrelated
repair authority follows. Actual commit identity and hosted outcomes will be
recorded separately when observed.


## First published CI failure and pre-repair scope

[Hosted run 40799181424](https://github.com/atharva-m/MarketLab/actions/runs/40799181424)
for published SHA `eca54fe68af357ca16973aa98ed7dcca3a266973` FAILED its integration
job: 205 passed, six failed and four historical-input cases skipped. The other
four jobs succeeded. The first failure was the native `capacity_exceeded` guard
when reserving 20 GiB scratch after the 4 GiB output reservation. The remaining
five failures followed unsuccessful ingestion; their assertions did not reach
the intended publication/readback/race checks. The retained job log is
`artifacts/v2-phase2-publication-20261028/check-two-job-123202896931.log`.

Read-only diagnosis found each v2 test already uses a separate disposable schema
and temporary storage root. Production reservation accounting is unchanged: the
runner lacks the required free space after the image build, rather than sharing
stale reservations between tests. Before editing the workflow, the scoped repair
is fixed as follows: only the integration job's GitHub-hosted Linux runner may
remove its exact unused preinstalled Android, .NET, Haskell, CodeQL, Java, Swift
and PowerShell toolchain paths.
Explicit runner/environment guards prevent this preparation on local or
self-hosted machines. After the Docker build and service startup, measure both
the actual Python temporary filesystem and checkout filesystem and require at
least 50 GiB free on each before running the unchanged integration suite. The
divergent-orphan test retains the first failed attempt's 24 GiB reservation while
admitting another 24 GiB attempt, plus source bytes and headroom. Both conservative
charges remain intact. Review rejected the initial 26 GiB prerequisite before
publication because it covered only one attempt; its local syntax/guard check
remains retained as an earlier insufficient-design checkpoint.
Insufficient capacity must fail as an explicit prerequisite, not skip tests.

No application/runtime, production limit, dependency/lock, CLI subprocess,
database isolation or test assertion changes are part of this repair. The exact
directory preparation is for the disposable hosted runner only and is not
executed against local/original services. Independent review and a new exact-SHA
hosted run are required; the failed published run remains failed.

The final preparation allowlist is exactly `/usr/local/lib/android`,
`/usr/share/dotnet`, `/usr/local/.ghcup`, `/opt/ghc`,
`/opt/hostedtoolcache/CodeQL`, `/usr/lib/jvm`, `/usr/share/swift` and
`/opt/microsoft/powershell`. GitHub's published
[runner image installers](https://github.com/actions/runner-images/tree/main/images/ubuntu/scripts/build)
identify the bundled toolchain locations; absent paths are harmless, and the
measured post-build capacity remains the definitive prerequisite. No toolcache
root, Docker state or dynamic path is removed.

Local repair checks passed YAML parsing, Bash syntax for both new steps, exact
allowlist inspection and a structural comparison proving every earlier workflow
step/job unchanged. Guard-only execution rejected missing/self-hosted/non-Linux
environments before any cleanup and accepted only the GitHub-hosted Linux shape.
Prerequisite-only checks accepted exactly 50 GiB and rejected one byte below it
on either filesystem; these are labeled synthetic prerequisite checks, not
application capacity acceptance. Actual local temporary/checkout free space also
passed the prerequisite. The first sandbox Bash check failed on MSYS object
permissions; the approved elevated read-only rerun passed. No cleanup command was
executed locally. Evidence is `ci-capacity-local-check-final.json`, retaining the
earlier insufficient 26 GiB check separately.

Only the workflow and four authority/roadmap/contract/verification documents
changed. Application execution fingerprint remains
`a15d48bee4a5e19ac44a35bef2fbf54656f573341bfeaf87f95fc5bcee00ebba` and lock
SHA remains `730f02bec94d1f824a2cadf74f60cf5dcc246faa55004d5d060b92931224618f`.
Independent review and actual hosted capacity/results remain pending.


## First capacity repair: hosted prerequisite still failed

[Hosted run 40800454123](https://github.com/atharva-m/MarketLab/actions/runs/40800454123)
for `dfb31c1e44157bc362c1c78789cfc5fefd2f69d4` FAILED the explicit 50 GiB
prerequisite before integration tests. All four other jobs passed. Its Ubuntu
26.04 image `20261025.179` reported 72 GiB total: 15 GiB available initially,
42 GiB after removing the eight reviewed unused bundles, and exactly
41,474,846,720 bytes free after Docker setup on both measured filesystems versus
53,687,091,200 bytes required. This is a failed capacity prerequisite, not a
successful integration invocation or another six-test failure. The retained log
is `fix-two-job-123207035813.log` under the publication evidence root; completed
run/job receipts are `fix-complete-run.json` and `fix-complete-jobs.json`.

Before the next workflow edit, the further scoped repair extends the exact
unused-bundle allowlist by seven roots: `/opt/hostedtoolcache/Python`,
`/opt/hostedtoolcache/PyPy`, `/opt/hostedtoolcache/go`,
`/opt/hostedtoolcache/Ruby`, `/usr/lib/llvm-20`, `/usr/lib/llvm-21` and
`/usr/lib/llvm-22`. GitHub's published
[Ubuntu 26.04 toolset](https://github.com/actions/runner-images/blob/main/images/ubuntu/toolsets/toolset-2604.json)
identifies those cached languages and Clang versions. Its
[toolcache installer](https://github.com/actions/runner-images/blob/main/images/ubuntu/scripts/build/Install-Toolset.ps1)
places named languages beneath `/opt/hostedtoolcache`. This is evidence of
bundled tools, not a claim about their unmeasured per-directory sizes in the
failed runner. The next hosted invocation will log byte-size inventories of
all fifteen exact candidates before removal and remeasure free space afterward.

The failed run independently downloaded uv-managed CPython 3.13.17 before the
locked sync; its uv installation is under `/opt/hostedtoolcache/uv`. Both that
path and the entire toolcache root remain untouched, along with Node, system
Python, Docker and container runtimes. The application image uses its own Python
interpreter. Host cached Python/PyPy/Go/Ruby and the three unused Clang toolchains
are not required by this Python/PostgreSQL/Docker integration job. No glob,
dynamic target, package-manager cleanup or local command execution is introduced.
The 50 GiB prerequisite, production thresholds, conservative reservation records
and all actual test/CLI assertions remain unchanged. Independent review and
measured hosted results are required again; both earlier failed runs remain failed.

The further repair passed YAML parsing, both Bash syntax checks, all four
hosted-environment guard cases and exact equality between the fifteen inventory
and removal paths. Structural comparison confirmed the 50 GiB prerequisite,
all integration tests and every other workflow step/job unchanged. No inventory
or cleanup command ran locally. Receipt `ci-capacity-second-local-check.json`
pins workflow SHA-256
`d81655238e0429dd25fa2463a69d77487cde52a89c39db57b87afa9d5f190068`.
Independent read-only `gpt-6-astra/medium` review approved that executable repair
with no unresolved blocking finding. Its publication and actual hosted capacity/
integration outcome remain pending; bundled-tool sizes remain unmeasured until
the next hosted inventory.
