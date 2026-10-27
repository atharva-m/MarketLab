# R9 reproducible handoff and final demonstration plan

Approved October 27, 2026. Scope: fresh-clone verification, complete user
and operator documentation, and a short professional demonstration of the existing
MarketLab product. The user selected Remotion for the video workflow. This document
is now authorized for implementation and actual acceptance under the full
[pre-code contract](r9-handoff.md), including scoped tool setup and authority
updates. Commit/push and public publication remain excluded. Planning-only
instructions below describe the pre-approval stage and are superseded by that
contract solely within the approved R9 scope.

## Scope and deliverables

- Fresh-checkout setup instructions covering prerequisites, locked installation,
  configuration, migrations, local services, bounded workers and owned cleanup.
- Separate clean-start and retained-evidence procedures, with explicit prerequisites.
- User guidance for ingestion, explicit versions, manual research, copilot
  clarification, exact charts/results, provenance and independent memo status.
- Operator guidance for replay keys, interrupted jobs, model/cache failures,
  monitoring and current limitations.
- A 2–3 minute local Remotion video, captions, transcript, editable composition,
  reproduction instructions and a shot-to-evidence index. Longer original captures
  remain available separately as evidence.
- An R9 verification report mapping mandatory gates to actual observations,
  independent review, preservation and cleanup results.

README.md should present current product capabilities, configuration and usage.
Historical approvals, failed invocations, incidents and publication records belong
in [Project history](project-history.md) and the linked milestone reports. The
earlier documentation relocation is separate from R9 implementation acceptance.

Keep application behavior unchanged by default. Exclude new analytics, symbols,
dates, prompt/model changes, schedulers, garbage collection, authentication,
public hosting, original-service rollout, schema changes and upgrades to existing
application dependencies. Docker/WSL/initd/clock/GPU changes remain excluded.
Any runtime defect discovered requires a narrowly scoped proposed amendment before
runtime repair. A video project may have its own pinned dependencies after approval;
it must not modify MarketLab's Python or frontend dependency graphs or lockfiles.

## Implementation sequence after approval

1. Write the full R9 acceptance contract before tooling or video code. Fix the
   source baseline, resource ownership, scenario matrix, evidence fields, scoring,
   failure policy and completion gates. Update contributor authority only when
   separately authorized; this proposal does not update AGENTS.md.
2. Reconcile current publication status from exact revision evidence. The retained
   R8 report verifies 3fc8584 and hosted run 40548949738; the later documentation
   commit's hosted outcome must be checked rather than inferred.
3. Snapshot protected files and original service IDs, images, start/restart counts,
   health and endpoints. Allocate explicitly owned resources and fresh evidence
   directories; record ports, resolved paths and process/container ownership.
4. Audit and improve the setup/runbooks. Implement only necessary bounded
   verification helpers. Use coder gpt-6.1-sol/high, followed by independent
   read-only reviewer gpt-6-astra/medium; fix actionable findings and rerun affected
   checks. Do not launch this delegation during planning.
5. Freeze the tested source and execute both fresh-checkout paths below. Record
   exact source/lock/model identities, inputs, timings and every failed invocation.
6. Execute retained regressions and actual workflow acceptance. Source changes
   after the freeze require relevant retesting and explicit evidence provenance.
7. Prepare sanitized footage after performance/resource measurements, compose and
   render the Remotion demo locally, then review the complete exported video.
8. Complete independent source/documentation/evidence/video review, retain dumps
   and logs, verify original preservation and perform exact ownership-checked
   cleanup. Report actual outcomes without turning missing prerequisites into passes.

## Fresh-checkout paths

### Clean source and empty state

Clone into a new directory. Do not copy the original virtual environment, frontend
dependencies, build outputs, .env, application caches or database. Record existing
machine prerequisites: a fresh clone on this machine is not a previously unused
computer. Install from existing locks without regenerating them, provision owned
PostgreSQL/Redis storage and artifact roots, and apply existing migrations.

Verify empty catalog behavior, API health, frontend and packaged startup, then
exercise committed synthetic fixtures. Perform one actual official January daily
ingestion, full readback, same-key replay and fresh-key same-source reuse. Document
the bounded all-62 ingestion procedure. The mandatory new download is one day;
full-month coverage comes from the next path. Do not claim a newly downloaded
month. Provider failure leaves the download gate incomplete.

### Clean source with explicit retained evidence

Use a separate owned database and artifact destination. Inventory/hash retained
datasets, manifests, database snapshots, historical source snapshots and independent
references before importing. Document validation and restoration; do not assume
ignored files exist in a clone or silently connect to original services.

Verify all 62 registered partitions and old research/memo readback through normal
readers. Distinguish restored completed history from newly submitted work. Do not
rewrite source identities, reset terminal jobs or execute incompatible queued work.
Run new manual and copilot workflows from the fresh checkout.

## Acceptance criteria

| Gate | Required outcome |
| --- | --- |
| Setup | Documented commands work with declared prerequisites; no hidden original-checkout/environment/build dependency. |
| Locked regressions | Full Ruff lint/format, mypy, offline and real PostgreSQL suites; frontend type/lint/components/build and browser suites pass. Record actual counts and skips. |
| Historical source tests | Four snapshot-dependent PostgreSQL cases are explicitly skipped in the bare clone and pass separately with verified retained evidence. 196 plus four skips is not 200 passes. |
| Ingestion | Official checksum-before-parse, exact readback/count/hash reconciliation, safe replay and same-source version reuse. |
| Full month | All 62 January partitions reconcile 230,311,900 trades with exact retained manifest, physical and logical hashes. |
| Cold numerical run | Fresh application/verifier state and empty owned Redis; all-62 submit/execute/readback plus the agreed cleanup boundary under 1800 seconds, exact independent numerical hashes and real worker drain. Record cleanup timing and uncontrolled OS cache separately. |
| Research | All five retained scenarios remain readable; fresh executions cover all three workflows and match independent reference numerical payloads. |
| Copilot | Actual pinned 9B clear request, durable clarification continuation and unsupported/adversarial case; only validated specs reach research, without duplicate handoff. |
| Memo | Fresh actual three-paragraph grounded memo with factual/provenance audit; numerical results remain independently usable during pending/failure states. |
| Failure isolation | Owned Redis outage and unavailable-model cases preserve manual research and numerical reads. Replay/reload does not duplicate work. |
| UI and monitoring | Real browser flows preserve exact values, nulls, explicit versions and bounded charts; observe API and separate CLI-worker telemetry. |
| Video | 120–180 second local Remotion export, readable real UI, verified captions, no invented results, no account/service connection or media upload, complete shot/evidence mapping. |
| Preservation | Protected hashes and current-interval original-service identities/health/endpoints match; exact owned cleanup is verified. |
| Review | No unresolved blocking finding or unaccounted owned resource; each mandatory gate has an actual result and source identity. |

The 990 offline, 200 local PostgreSQL, 18 component and 33 browser counts are
historical baselines, not automatically R9 outcomes. Retain separate Linux and
Windows browser evidence and the known Windows Firefox cache-path limitation.
Retain focused legacy HTTP/CLI, migration preservation and packaged Linux checks.

R9 integration scenarios do not establish a new model-quality estimate. Do not
repeat all R8 quality/benchmark campaigns merely for documentation or video work.
If an approved change affects inference, validation, grounding or performance,
amend scope and rerun the relevant frozen acceptance gates. Never select the best
model attempt or weaken a threshold after seeing results.

## Selected Remotion workflow

October 27 approved rendering preference: the user subsequently requested the
dedicated GPU for rendering/export. Process-local Chromium GPU selection and
required NVIDIA hardware encoding are permitted, with actual adapter/encoder
verification and full output QA. The earlier GPU exclusion continues to prohibit
driver/global setting changes; application/model behavior remains unchanged.
See the [contract clarification](r9-handoff.md#selected-remotion-workflow).

Use Remotion locally for composition, preview and rendering. Account-free operation
is a requirement for the selected setup; no Remotion Cloud/Lambda, hosted Studio,
connected video plugin, cloud transcription or media upload is included. Check the
selected version's applicable license and local rendering prerequisites before
installation. If that setup requires sign-in, paid activation or remote media
processing, report the conflict rather than creating an account or switching services.
Local rendering support alone is not a blanket claim about every optional feature.

1. Read the official Remotion skills after implementation is authorized. Use
   best-practices, create/markup, Studio, captions and render guidance as applicable.
   Pin the reviewed skill revision and dependencies; do not install them now.
2. Create a separate video project with its own package manifest/lock and README.
   Use local files for footage, fonts, title assets, narration and captions. No
   remote asset URLs, analytics, account integration or production API calls in
   the composition. Keep raw media, outputs and dependencies outside Git.
3. Capture actual application footage with local OBS recording, or existing local
   browser capture if adequate. Choose and verify the capture route during setup;
   Remotion composition does not itself prove capture capability. Capture a short
   sample before full takes. Record after benchmark/resource gates, not concurrently.
4. Freeze a 120–180 second script and shot list using the detailed
   [demo storyboard](r9-demo-research.md). Use real UI footage, readable crops,
   restrained motion, intentional pauses and consistent typography. Preserve the
   source takes and failed invocation identities. Label time compression and any
   transition from clean state to restored data.
5. Build explicit frame-timed Remotion scenes at 1920×1080, 16:9, 30 fps. Add local
   recorded narration if available; otherwise use designed on-screen captions
   with sufficient reading time. No cloud TTS, voice cloning or generated product
   footage. Caption content is reviewed against actual displayed results.
6. Preview locally and render using the installed pinned CLI/Studio. Review source
   for external requests and verify a representative preview/render without
   external network access after prerequisites are installed, without system-wide
   firewall or network changes. Record the method and limits of this verification.
7. Watch the entire export and inspect chapter boundaries, captions, exact numerical
   labels, audio sync/levels, readable text and absence of unintended sensitive
   content. Rerender corrections. Save the MP4, caption file, transcript, asset
   manifest, render settings/tool versions, checksums and shot-to-run evidence index.

Reproduction requires pinned assets, composition inputs and toolchain. Do not
promise bit-identical MP4 bytes across encoders/platforms. Keep footage outside
cloud-synchronized folders. Local media processing does not make this assistant
offline; only sanitized frames/content should be supplied to the assistant.

Official references: [agent skills](https://www.remotion.dev/docs/ai/skills),
[rendering](https://www.remotion.dev/docs/render),
[license](https://www.remotion.dev/license), and
[OBS capture guide](https://obsproject.com/kb/quick-start-guide).

## Preservation of R1 through R8

| Contract | Invariants |
| --- | --- |
| R1 | Checksums, exact normalization, immutable identities/manifests, registered-only discovery and synchronous compatibility. |
| R2 | Idempotency, partial completion, three attempts, database-time leases/heartbeats, fencing, atomic publication and claim-clock workaround. |
| R3 | Exact bars, missing-bar semantics, cache limits/bypass, two shared compute permits and actual drain/worker lifecycle. |
| R4 | Strict specs, Decimal80 definitions, explicit history/warm-up, deterministic hashes and manual-service behavior. |
| R5 | Durable revisions, five-answer boundary, semantic validation, call/attempt budgets, atomic handoff and incompatible-source rejection. |
| R6 | Immutable supplemental memos, unique enqueue, numerical independence, nonpreemptive priority, memo prompt-v1 and 2048-token budget. |
| R7 | Local workspace, replay-safe operations, bounded polling/charts, exact display, explicit versions and no browser worker launch. |
| R8 | Exact adopted 9B digest/prompt-v4 bytes/settings, native bounds, frozen scoring/evidence and monitoring/resource limits. |

Preserve the original week 1–9 API/CLI/import/filter/pagination contracts. Preserve
the second R8 resource failure, failed 4B gates, historical uptime gap, clock
discrepancy, Firefox cache issue and model/cancellation/memory limits. New source
identities must be honest; old artifacts and source-linked outcomes remain intact.

## Estimate and completion boundary

Provisional estimate: 30–45 engineering hours plus setup/download, acceptance,
capture and rendering time. This updates the earlier 25–40 hour proposal to include
the isolated Remotion project, asset preparation, local-operation verification and
video QA; it is not measured velocity or a delivery commitment.

Missing prerequisites or a failed mandatory gate leave R9 incomplete. Documentation
and a polished video cannot substitute for actual acceptance. Publishing the video,
committing/pushing source and deploying original services remain separate decisions.
