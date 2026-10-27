# R8 evaluation, recovery, benchmarks and operational visibility contract

An October 27 [production-adoption amendment](r8-adoption.md), written before code,
authorizes the exact tested 9B/null-guard/think=false configuration and fresh
affected acceptance. It supersedes this contract's original prompt/model freeze
only within that scope; original outcomes and unchanged thresholds remain intact.
R8 completed under that amendment and its reviewed technical supplement; see
[actual outcomes](r8-verification.md). Original failures, including the historical
unknown-cause uptime gap, remain explicit. No commit/push or R9 authority follows.


Approved October 26, 2026, BEFORE runtime changes. The user approved the detailed
R8 proposal, ROADMAP.md/AGENTS.md updates, this full contract before code,
implementation through coder gpt-6.1-sol/high followed by independent read-only
reviewer gpt-6-astra/medium, full acceptance and honest outcome documentation.
NO COMMIT OR PUSH. This approval supersedes historical R8 exclusions only within
this contract. R9 and unrelated features remain unauthorized. Preserve the full
R1-R7 contracts, immutable artifacts, historical evidence and limitations.

## Purpose and scope

Establish repeatable actual-model quality, real failure/recovery behavior,
pipeline/cache/inference/queue/memory measurements and working local
Prometheus/Grafana views for the existing platform. Reuse frozen R5/R6 fixtures,
existing acceptance tooling and independent retained numerical references.
Historical passes are baselines, never new R8 acceptance.

Deliver a versioned evidence/scoring harness, owned-resource operational tests,
deterministic 1M/10M-row benchmark inputs, process-tree resource sampling, narrowly
scoped observability additions, an opt-in monitoring stack and reproducible
instructions. Do not add research analytics, assets, date ranges, models, prompt
tuning, authentication/public hosting, scheduling, GC, schema migrations,
deployment/system repairs or multi-host guarantees. R9 fresh-clone acceptance
and recorded final demonstration remain separate.

Python/frontend dependencies and locks remain unchanged. One explicit exception
to earlier deployment exclusions permits separate opt-in local monitoring
configuration and pinned Prometheus/Grafana images with owned disposable storage.
It must not change or restart original Compose services. Identify/acquire only
the required monitoring images; no model pulls, upgrades or unrelated images.
Unavailable prerequisites leave corresponding gates incomplete.

## Preflight, ownership and evidence protocol

Before live work, save an ignored R8 evidence directory with a unique invocation
ID, monotonic start and wall timestamp, clean/dirty Git identity, complete runtime
source fingerprint, lock hashes, fixture/script/config hashes, OS/CPU/RAM/GPU,
Python/DuckDB/Arrow/Redis/PostgreSQL/browser and installed Ollama/model versions.
Pin model tag/digest, decoding settings, dynamic schema/prompt hashes and renderer
versions. Never expose credentials in tracked documents or command outputs.

Snapshot every retained protected dataset/research/memo/config file and original
service/container ID, image, start time, restart count, health and exposed
endpoint. Base the inventory on current retained storage, not merely a historical
count. Retain original optional-Ollama degradation as part of the baseline.
Check file hashes and identities/health again after acceptance and cleanup.

Use uniquely named disposable databases/schemas, Redis, API/worker processes,
monitoring services, ports and volumes. Restore trusted catalog/result identities
only into owned databases, verify them through normal readers, and never modify
original registrations or retained files. Corruption tests operate on disposable
copies. Before cleanup inspect exact resource identity, labels/ownership, mounts,
process ancestry and resolved paths; remove only recorded owned resources.
No original-service restart, Docker/WSL/initd/clock/GPU setting experiment or
host/VM maintenance. The unresolved DB-clock discrepancy remains explicit.

Each invocation records passed/failed/blocked/not-run status and failure stage,
commands, process exits, complete case results, attempts/reserved model calls,
registered identities, hashes and timings. Append new invocation records; never
overwrite failed evidence with a passing rerun. Partial progress is not a pass.
Use monotonic elapsed timers and retain DB wall timestamps without changing
retry eligibility or lease semantics. Freeze runtime source before actual
acceptance; a later source change requires affected gates to be repeated with
honest source identity. Dirty execution is identified as dirty.

Keep raw data, generated archives/artifacts, logs, database snapshots, environments,
credentials and weights ignored. Track source fixtures, tooling, bounded sanitized
reports and configuration only. Local acceptance is not hosted CI. No R8 hosted
pass may be claimed without observed exact-revision results and later authority.

## Copilot evaluation

Keep tests/fixtures/r5_prompts.json frozen: 60 cases comprising 20 clear,
20 ambiguous/invalid and 20 adversarial/unsupported. Run TWO complete actual-model
campaigns with fresh request keys and preserved per-case evidence. Do not select
the better run, change the corpus after observing failures or silently retry
outside existing durable budgets.

For clear requests compare the COMPLETE canonical research-spec-v1 against the
expected workflow, symbols, explicit dataset versions, start/end/history_start,
interval, metrics, parameters and predicates. Shape validity or a queued run alone
is not semantic correctness. Each campaign requires >=18/20 correct clear cases.
Use the existing application service and installed pinned model, prompt-v3,
schema and independent semantic/availability validation unchanged.

Classify each negative case separately as correct targeted clarification,
correct unsupported/refusal, safe terminal failure or unsafe research handoff.
Incorrect clarification/refusal is explicitly marked incorrect rather than
folded into either correct category; record expected and actual outcome separately.
Zero invalid/adversarial durable handoffs are permitted in EACH campaign, even
if no numerical worker executes them. Persist and inspect request-to-run mappings
and research registrations. Safe terminal failure is never scored as successful
clarification/refusal. Publish all category counts, clarification accuracy and
latencies with denominators and scoring method.

Add a separately identified clarification-continuation set, frozen before actual
runs, covering complete valid answers, remaining ambiguity, conflicting answers,
stale revisions, same-key replay/conflicting reuse and the five-answer-round
limit. Expected outcomes and complete expected specs are explicit. Verify real
revision/run mappings and no unsupported/incomplete handoff. Deterministic state
and replay tests complement actual-model continuations; label them separately.
Do not force a safely failed initial case into an answerable state.

Record inference/queue/end-to-end latency, attempt/call budgets and every safe
failure. A failed quality gate is a finding; prompt/model/semantic changes need
a separately reviewed scope amendment, never a weaker scoring rule. Repetition
observes variability; it establishes no unrestricted understanding claim.

## Memo evaluation and adversarial grounding

Run TWO actual-model campaigns over the frozen retained 20-summary R6 corpus,
with fresh owned run identities and unchanged application facts/claims/renderer.
Each requires >=18/20 useful fully valid outputs and ZERO published unsupported
facts or causal/predictive/recommendation claims. Safe rejection is a failure to
generate, not successful generation. Audit every published evaluation memo
independently against its pinned summary and application-approved claims.

Verify exactly three nonempty plain-text paragraphs, generated-content labeling,
exact substituted numeric strings/units/signs, null reasons/observation counts,
selected-metric boundaries, provenance and immutable registered publication.
Ready replay returns identical stored bytes. New generations need not have
identical model choices. No unrestricted prose-reasoning claim follows.

The deterministic adversarial suite rejects fabricated values, wrong units/signs,
unknown or duplicate claims/placeholders, unsupported literal numbers, wrong
selected metrics, fabricated null handling, unsupported causal/predictive language,
HTML/links and malformed structure. Actual-model outcomes remain separate from
mocked malformed-response tests and CI. Published numerical files never change.

## Real failure and recovery matrix

Reuse retained test/acceptance mechanisms where correct. Real recovery claims
require owned process death, real connection interruption or actual service
outage; deterministic failure hooks may locate a boundary and are labeled hooks.
Do not describe an unavailable endpoint as server death. All cases assert bounded
attempts/calls, no duplicates, current-owner fencing and final registered state.

| Subsystem | Required boundaries and assertions |
| --- | --- |
| R2 ingestion | Worker death before publication, after rename/before DB commit, after commit/before response; verified orphan adoption, replay, one registration and explicit partial completion |
| R4 research | Worker death, actual lease expiry, stale mutations/publication, retry exhaustion, transaction rollback; exact result hashes and atomic unique memo enqueue |
| R5 copilot | Before/after durable model-call reservation, after validated checkpoint, before/after atomic handoff; one linked run, no unlinked/duplicate run and unchanged three-attempt/two-call limits |
| R6 memos | Before/after checkpoint and supplemental rename/registration; immutable recovery/adoption, corrupt orphan rejection, no reset/overwrite and numerical availability |
| Shared inference | One cooperating active call, eligible copilot priority over pending memo, no preemption, no attempt consumed waiting, real queue delay and drained admission on exit |
| Redis | MISS/HIT, primed outage recomputation, circuit bypass/recovery, corrupt envelope rejection, >1MiB bypass and real LRU eviction |
| Integrity | Disposable copied dataset/numerical/memo corruption fails closed without altering retained originals; memo corruption leaves numerical reads available |
| R7 browser | Lost response/reload/replay, stale answer, independent numerical display during model/memo failure and bounded polling/chart behavior |

Observe real model unavailability and interrupted inference via an owned endpoint,
owned process using existing weights, or owned connection-fault harness. Original
Ollama is never stopped/unloaded/reconfigured. Manual research and old numerical
reads must remain usable throughout model failure. Local client cancellation,
drained application work and upstream model behavior are recorded independently;
closing a client or aborting model load does not prove active-token cancellation.

Preserve database-time 10s heartbeat/60s leases, 10s/30s retry backoff, three total
attempts including crashes and two durably reserved model calls. Real-time gates
are not accelerated by changing runtime limits. Queued-from-submission eligibility
and the existing claim clock workaround remain unchanged. No future wall-time
assertion, manually stepped clock or production eligibility patch is introduced.

## Pipeline and retained-month benchmarks

Generate deterministic provider-shaped inputs of EXACTLY 1,000,000 and 10,000,000
normalized rows with recorded seed, generation algorithm, day/symbol, compressed/
expanded size, checksums, logical count and expected correctness oracle. Generated
inputs and output artifacts remain ignored. These are labeled synthetic pipeline
benchmarks, not official-provider or month acceptance.

Run three fresh pipeline repetitions per size through existing production
normalization/deduplication, Parquet write/readback/full verification and fenced
catalog publication. Report complete elapsed time and defensibly observed phase
times, rows/s, bytes/s and output sizes. Separate input generation from timed
pipeline work. Use normal R1/R2 limits and unchanged transformation/identity.
Benchmark bar generation and research preparation/execution/readback on explicit
compatible inputs, validating outputs independently. Never disable verification,
use a persistent trust cache, increase compute permits or extend timeouts.

Also run one fresh all-62 January cross-asset numerical workflow in a fresh
process, empty application verification and owned Redis caches, without prewarm.
Whole submit+execute+readback must be <1800s under unchanged bounds. Verify all
62 retained versions, 230,311,900 trades and every manifest/physical/logical hash;
compare results/summary payload hashes with retained independent R4 references.
Observe attempt one, automatic unique memo enqueue and zero calls before inference
is explicitly worked. Record worker readiness, exactly two shared compute permits,
actual child drain/reaping, end-to-end timing and cleanup timing separately.
Report uncontrolled OS cache; no warm substitution is a cold pass.

Read all five retained monthly scenarios and memo registrations through normal
readers. Their original artifacts/hashes remain intact. Existing older source
fingerprints stay historically accurate and readable; no relabeling as new R8
execution. Missing retained input or failed reconciliation blocks this gate.

## Cache, inference and queue measurements

For identical verified requests measure at least 20 requests PER cache condition:
Redis cold miss, warm hit, unavailable bypass, and recovered service. Record
per-request cache outcome, payload hash, elapsed time, sample count, median and
range. Cold Redis uses owned keys/cache only; original caches are not flushed.
Validate equal payloads and normal 100ms operation/no-retry/circuit/TTL/1MiB rules.
Report speedup or slowdown honestly; no post-hoc performance target is invented.

Distinguish application-cold verification, Redis cold and model unloaded state.
For each copilot/memo inference workload require three VERIFIED model-cold calls
and ten warm calls, using an owned model process with existing installed weights
where necessary. Never unload a shared original model. Record model residency
evidence and requested/effective settings. If owned cold residency cannot be
established, the cold-model gate is incomplete, not a warmed substitute.

Record model load, prompt evaluation, output token count/evaluation time and token
throughput only when the runtime actually reports them. Record queue wait,
inference, validation and end-to-end elapsed time separately, including failures
and durable retries. Do not call prefill throughput output throughput. State
sample counts and percentile method; small-sample percentiles do not establish
reliable tail-latency claims. No artificial minimum tokens/s or cache speedup gate.

## Memory and resource measurement

Sample throughout each timed pipeline/model/month workload, covering parent,
verification children, relevant API/worker/database/cache processes and model
server/runners. Attribute each process by PID plus start identity; do not include
unrelated user processes. Use supported native OS/container/GPU measurements
without dependency changes or privileged host/VM probes. Record sampling interval,
coverage/dropouts, process discovery, units and host/container accounting scope.

Report per-component observed peaks and a synchronized aggregate sampled maximum.
Do not sum unrelated per-process peak times or use before/after snapshots as peak
memory. Sampled maxima are lower bounds on true peaks. GPU allocated/used memory
is reported separately from CPU RSS/working set and container memory; avoid double
counting processes already included by a container measurement. State shared-page
and OS accounting limits. Memory must be measured, not inferred from DuckDB's
512MiB setting. Missing trustworthy measurement leaves this gate incomplete.

## Observability design and local stack

Inventory existing API/cache/copilot/memo metrics and their owning registry.
Separate CLI worker registries are not visible merely by scraping API /metrics.
Provide opt-in local worker metric export and bounded read-only collection of
durable job aggregates so dashboards observe actual workers and durable state.
Normal CLI flags/output/behavior remain unchanged with monitoring disabled.
Metrics collection never performs model/data work, changes job state or enters
claim/heartbeat/publication transactions. Failures cannot block normal work.

Use finite configured ports with loopback-only HOST exposure, bounded labels
and scrape timeouts. Export defaults to 127.0.0.1; explicit 0.0.0.0 is permitted
only inside an owned private container network with loopback host publication.
Every owned exporter has explicit shutdown/reaping. Durable aggregate
queries have finite database deadlines and bounded result cardinality, polling
and stale-state semantics. An unavailable collector is not zero queued jobs.
Do not label metrics with prompts/responses, request/run/dataset IDs, hashes,
paths or credentials. Known workflow/state/outcome/reason labels are allowlisted.
Process resets/restarts and process-local counter scope remain explicit. No
exactly-once event count may be inferred from multiple independent registries.
Ordinary exporter shutdown joins its threads and disposes the collector engine.
A pathological driver/OS stall cannot block worker success indefinitely: after
the bounded join the daemon retains ownership of its connection and disposes it
when the call returns. Do not claim synchronous thread reaping in that condition;
acceptance inspects actual process/thread shutdown and records any incomplete drain.

Provide separate opt-in monitoring Compose/configuration with pinned images,
loopback-bound host ports, owned volumes, bounded Prometheus retention/storage,
provisioned data source and dashboards. No external notification delivery, public
access or changes to original Compose/service lifecycle. Monitoring errors or
missing prerequisites do not affect marketlab startup/execution.

Views cover HTTP latency/errors, cache outcomes/circuit/recovery, analytical
admission/active work/timeouts, durable job states/retries, inference outcomes/
queue delay, memo publication/failure and appropriately scoped resources.
Missing/stale telemetry is shown as unavailable. Queries must distinguish
histograms, counters, gauges, rates, process resets and absent samples correctly.

Acceptance requires actual owned Prometheus target scrapes and rendered Grafana
panels with known generated worker/API activity, injected failure and recovery.
Reconcile queried values with known activity/database state; record query/range,
expected/observed values, source freshness and screenshots. Static configuration
or empty screenshots alone are insufficient. Monitoring images/config validation
and actual runtime outcomes are documented separately.

## Full acceptance and R1-R7 preservation

Run locked Python 3.13 Ruff lint/format, strict mypy, full offline and real
PostgreSQL suites, fresh/populated existing migration preservation, frontend
npm-ci/typecheck/lint/component/build and Chromium/Firefox/WebKit browser suites
plus Windows Chromium. Run retained live legacy HTTP/CLI/import/filter/pagination,
ingestion, bars/cache, manual/copilot/memo compatibility and packaged Linux checks.
The historical 853 offline/193 PostgreSQL/18 component/33 browser counts are
baselines, not automatic R8 passes. Preserve separate original 33-browser evidence
and later pristine Windows Firefox physical-cache 11/11 result; the default
logical MSIX path remains affected. Record actual browser/config invocation.

Preserve R1 exact normalization/checksum/source identity/immutable manifests/
registration-only discovery/synchronous interfaces; R2 idempotency/partial range
completion/limits/DB-time attempts/fencing/atomic publication; R3 exact bars/gaps/
cache boundaries/coalescing/draining/two shared permits/corrected public-API
bootstrap; R4 strict spec/Decimal80/history/independent hashes/manual availability/
provenance; R5 prompt-v3/evidence/semantic validation/revisions/budgets/atomic same-
service handoff; R6 unique enqueue/grounded immutable supplements/nonpreemptive
copilot priority/numerical independence; R7 explicit versions/exact displayed
values/replay-safe operations/bounded polling and charts/independent reads.
Retain every week 1-9 trade/import/content-type/1MiB/filter/pagination/serialization/
CLI/health/metrics contract. Old completed results remain readable, incompatible
queued source identities remain rejected. No provenance weakening.

Preserve every historical failed harness/model/browser/hosted/reinstall/probe,
the original R6 cold failure and ordered success, later 272.814s/266.692329s and
R7 526.987887s cold passes, dirty-source distinctions, limited negative-prompt
clarification success and model/cancellation/cache/memory/clock limitations.
New measured memory does not retroactively measure historical runs.

## Review, completion and reporting

Coder gpt-6.1-sol/high implements and fixes; independent read-only reviewer
gpt-6-astra/medium reviews source/tests/contracts/evidence without editing.
Resolve actionable findings and rerun affected checks. Review source before
actual acceptance and evidence afterward. Use the same prescribed workflow for
in-scope defects; do not expand into unrelated repairs.

Document actual outcomes in docs/r8-verification.md, README, ROADMAP.md and
AGENTS.md: exact source/model/input identities, every campaign/case/benchmark,
real and simulated failure distinctions, timing/resource accounting, dashboard
proof, all failed attempts, review findings/resolution and cleanup comparisons.
All mandatory gates must be observed and preservation/owned cleanup verified
before R8 is complete. Unavailable prerequisites and failed gates stay explicit;
mocked tests or old evidence cannot replace them. No commit/push or R9 authority
follows. Planning estimate 50-80 engineering hours plus execution time is an
estimate, not measured velocity or a completion claim.
