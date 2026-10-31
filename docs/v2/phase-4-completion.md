# V2 Phase 4 completion amendment

Status: PHASE 4 LOCALLY COMPLETE, October 31, 2026. This amendment was documented
and independently reviewed before implementation. The user requested this bounded
completion scope, implementation through coder `gpt-6.1-sol/high` followed by
independent read-only reviewer `gpt-6-astra/medium`, and cleanup of unnecessary
files from the earlier attempt. Implementation, actual acceptance, backup/export,
preservation and owned cleanup passed independent outcome review with no
unresolved blocker; see [verification](phase-4-verification.md). Historical failed
attempts remain preserved. No commit or push is authorized.

This amendment governs remaining Phase 4 work where it conflicts with the
[original contract](phase-4-ui-imports.md) or later harness proposals. Preserve
those historical records and failed outcomes. It replaces expanding acceptance
and closeout machinery; it does not relax application accounting, publication,
admission, compatibility, or resource limits. Independent pre-code review must
resolve blocking decisions before implementation.

## Frozen delivery

Finish the local browser flow: metadata discovery, official Binance ingestion or
canonical CSV/Parquet upload, durable status/cancellation/renewal, catalog,
explicit daily-version selection, the existing profile/comparison/cluster
workflows, charts, numerical results, and provenance. Include empty-catalog
guidance, actionable errors, canonical guidance, and local operator registry
forms. Correct demonstrated defects in these requirements; add no new features.

Preserve legacy API/CLI/readers/results, formulas, source and lock identities,
cache isolation, immutable fenced publication, the shared exact capacity-root
lock, conservative retained-byte charges, and the local 100 GiB committed plus
reserved data ceiling, four staged uploads, and eight running v2 attempts.
Existing physical/per-run limits and the 8 GiB acceptance resource bound remain.
Failed bytes remain charged; replay, renewal, expiry, or cleanup of scaffolding
does not refund them. Existing production restart tickets and unknown-owner
recovery retain exact identity checks and fail-closed behavior.

## Bounded execution and lifecycle

Maintain one active acceptance runner and one active lifecycle helper. Reuse
working components. Each run owns its launches and records role, command,
process identity, logs, and relevant durable job/run identities at launch.
Register ownership and establish the existing Windows private Job containment
and retained process handles before releasing application work. A known owned
handle remains the authority for that process's lifetime; repeated global
identity rediscovery is unnecessary. Native children belong to the owned group.

Normal shutdown requests cooperative stop, waits within a fixed recorded
timeout, joins owned workers/executors, records exit outcomes, and verifies the
owned group empty. Application threads are joined by their parent; no separate
OS-thread census is required. Unexpected forced termination fails the normal
lifecycle gate. Planned crash tests may terminate exact owned targets and must
verify recovery and group drain. Failure cleanup may terminate only verified
owned resources and records that fact.

Test normal completion, startup failure, worker crash, cancellation, and shutdown
timeout. Add further tests only for demonstrated defects. No global process
census, historical parent-chain reconstruction, general-purpose supervisor,
incidental Windows-error reproduction requirement, or recursive fixture
qualification project is part of completion. Routine invocation corrections
retain the failed command and rerun the corrected command without a new design
proposal. Review substantive code changes and actionable findings through the
prescribed coder/reviewer workflow.

## Independent acceptance results

Report functional, lifecycle, and sampled-resource results separately. A failed
measurement does not erase demonstrated functionality; functionality does not
excuse an incomplete required resource result. Historical failed campaigns keep
their original status. A final combined pass requires all three gates.

The runner declares the measured process groups and relevant service contribution
before execution, including browser, API, workers, and measurement overhead.
For Windows-owned groups, use the native held Job's committed-memory high-water
counter, which covers its contained descendants without per-PID sampling. This
prospectively replaces the earlier aggregate-RSS census criterion; it is a Job
committed-memory measurement, not RSS or a true whole-host peak. Contain the
runner, API/UI/controller, browsers, workers, and Docker sampling subprocesses
in one workload Job. Add the outer bootstrap's own process peak committed memory
queried directly through its self handle, so its overhead is also accounted.
Record the Job counter after workload drain and before its handle closes. Sample
the named PostgreSQL/Redis containers at a five-second target cadence with a
twenty-second read timeout, retaining timestamps/gaps and each observed
maximum. Account for each shared service once. Require the conservative sum of
owned Job high-water counters and service sampled maxima to remain below 8 GiB;
label that mixed, non-simultaneous upper-envelope calculation explicitly.

Missing required Job counters, failed containment, unmeasured owner overhead, or
unavailable required service observations leave the resource gate incomplete.
Start service sampling and establish group ownership before workload release,
and continue through owned workload shutdown. Freeze a 7,200-second overall run
deadline and sixty-second cooperative shutdown waits. Preflight input preparation
and postflight verification perform no application workload and have no latency
or whole-host resource claim. A confirmed process exit on an
owned handle is an ordinary lifecycle event and needs no fresh executable or
ancestry discovery. Optional process RSS diagnostics supply no missing Job or
service evidence. Freeze the exact group/service coverage, cadence, and pass
rules before execution; later changes apply prospectively.

## Finite remaining work

| Work | Completion evidence |
| --- | --- |
| Actual browser campaign | One final campaign across Chromium, Firefox, and WebKit with actual official ingestion, canonical CSV/Parquet imports, explicit selection, all existing research workflows, charts/provenance, and the simplified functional/lifecycle/resource gates. Reuse the approved retained actual inputs and independent expected results. |
| Maximum upload boundary | One actual browser-to-server upload of exactly 4 GiB with exact size/hash and bounded-memory observations, plus over-limit rejection. This is a transport/staging boundary; it requires no additional numerical research campaign. Ordinary actual canonical imports still normalize and publish in all three engines. |
| Regression closure | Retain valid current-source backend/frontend/package/numerical/crash/cache/resource-race evidence. Rerun checks whose executable source or assumptions changed. Harness-only corrections rerun the affected helper checks and acceptance; they do not automatically invalidate unrelated application gates. |
| Operational closeout | Reconcile current owned processes/resources, unfinished durable work, reservations, and retained bytes; verify final checksummed dumps and isolated restores for the actual owned database inventory; verify protected files/original services; then clean up verified owned disposable resources. |

Current source validity and each reused result's scope must be explicit in
[verification](phase-4-verification.md). Fixtures and historical Phase 3 passes
cannot replace missing actual Phase 4 gates. A current owned inventory establishes
cleanup safety without reconstructing every historical tool-process chain;
unresolved current capable owners block affected cleanup. Queued legacy memos
remain under their historical recorded states with no new model dispatch;
historical call counts are preserved rather than required to be zero. Update
usage, roadmap, and verification
to the observed outcome; do not infer completion from this amendment.

## Earlier-file cleanup

The user authorizes removal of unnecessary earlier scaffolding, superseded drafts,
temporary files, and bytecode. First identify exact files, contained absolute
paths, ownership, and active references, and retain an inventory of the action.
Never perform a broad prune or remove a live dependency. Preserve datasets,
retained source/output bytes, dumps, credentials/configuration, original-service
resources, protected files, the byte-exact README GIF, and executed success/failure
receipts, logs, and measurements.

Where historical helper source or draft bytes are needed to interpret retained
evidence, preserve them with original relative paths in a checksummed archive and
verify its contents before removing redundant loose copies. Keep an archive index
and location map so historical provenance remains recoverable. Historical archive
content is not an execution dependency of the new runner. No artifacts, archives,
data, environments, credentials, weights, or generated media enter Git.

## Completion boundary

Further work must fix a demonstrated product defect, satisfy a named remaining
gate, or enable safe closeout. Phase 5/model/prompt/memo work, new workflows or
providers, dependency/lock changes, distributed execution, authentication,
scheduling/GC, deployment, original-service changes, commit, and push remain
outside scope. Phase 4 completes only with the named gates, independent read-only
review without unresolved blockers, final verified preservation/backups/restores,
and ownership-checked cleanup.

The exact-4-GiB campaign exposed a concrete local transport configuration defect:
the Vite HTTP server retained Node's five-minute incoming-request deadline while
the browser and proxy allowed 31 minutes. The existing demonstrated-defect
authority covers aligning those deadlines, independent review, the affected
frontend checks, and a fresh exact-size boundary run. Classify the one-file Vite
forward change explicitly against the source-04 baseline; preserve the 151 exact
files and the original successful actual/numerical evidence under its recorded
source. Do not repeat unrelated backend/numerical campaigns solely for this
local HTTP-server configuration correction. Retain failed upload bytes/charges
and the interrupted campaign's evidence; a disconnect does not establish an
unobserved HTTP status or a proven OS/network cause.
