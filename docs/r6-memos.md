# R6 durable grounded memo contract

Approved October 25, 2026, BEFORE implementation. The user approved the detailed
R6 plan, ROADMAP.md/AGENTS.md updates, this full contract before code, prescribed
coder gpt-6.1-sol/high then independent read-only reviewer gpt-6-astra/medium,
full acceptance and honest outcome documentation. NO COMMIT OR PUSH. Historical
memo exclusions are superseded only within this contract. Preserve R1-R5 contracts,
immutable artifacts, historical failures and evidence. R7-R9 remain unauthorized.

## Scope and independent numerical availability

Generate supplemental descriptive memos for the existing January 2025 five-minute
BTCUSDT/ETHUSDT market_profile, cross_asset and volatility_cluster workflows.
Successful new numerical publication atomically enqueues one separate memo job;
numerical results become available without waiting for inference. Both manual and
copilot research use this path. Copilot submitted still means research queued.
Ollama/memo failures never change numerical success or block numerical reads.

No new analytics, downloads, model pulls, arbitrary sources/code/SQL/paths,
forecasts, trading recommendations, strategy/backtesting, UI/authentication,
scheduling, GC, dependencies/lock/deployment changes or multi-host guarantees.
No original-service restarts, Docker/WSL/initd/clock experiments. The known clock
discrepancy persists; retain the application claim workaround.

## Grounding, output and bounds

Read only catalog-registered research summary and numerical manifest after the
existing full artifact verification. Do not send copilot conversation, raw trades,
external news, user instructions or model-selected sources. Build memo-facts-v1
from the summary's selected metric sections, period/history metadata, units and
definitions. No unselected full-result metrics. Canonical facts retain exact
decimal strings, integer counts, UTC timestamps, null reasons and observation
counts. Numerical units remain R4 ratios, USDT and base asset; no arithmetic or
percent conversion by the model. Never silently truncate an oversized fact input.

The model returns strict memo-draft-v1: schema and exactly three ordered structured
paragraphs (scope, findings, limitations). Each paragraph selects application-owned
claim identifiers and bounded approved wording variants with allowlisted numeric
placeholders. The application constructs the available claims from validated
facts/predicates. Unknown/duplicate fields, claims/placeholders, unsupported literal
numbers, HTML/links/images, arbitrary text and invalid combinations fail closed.
Model choices cannot invent facts or reinterpret signs, nulls, units or causality.
All selected facts required by each claim are substituted in application code.

Paragraph one identifies generated content, assets, evaluation [start,end),
five-minute interval and available coverage; history is explicitly separate.
Paragraph two gives descriptive selected-metric findings appropriate to workflow,
including unavailable values with their exact allowlisted reason. Sparse selections
are supported without inventing omitted profile metrics. Paragraph three states
applicable coverage/null/interpretation limitations and that descriptive statistics
are not strategy returns, causal evidence or predictions. Association predicates
may support positive/negative/zero association only when the pinned correlation
supports that sign; no causal explanation or strength label is inferred.

Rendering yields exactly three nonempty plain-text Markdown paragraphs separated
by one blank line, <=16 KiB UTF-8, with a generated-content label in paragraph one.
No headings/lists/raw HTML. Formatting/placeholder checks alone do not establish
qualitative truth; bounded validated claims are the production grounding boundary.
This intentionally constrained language is not unrestricted model understanding.

Renderer-v1 profile findings include VWAP, close change, drawdown and the
unannualized Sharpe proxy, with each statistic's observation count or null reason.
Other profile details remain available in the numerical summary. Cross-asset
findings include common/aligned counts and only selected correlation/difference
fields. Cluster findings include cluster/qualifying/ineligible counts; no event
representative is selected and the potentially long event array stays out of
inference. Scope includes profile coverage only when profile was selected; sparse
selections explicitly say coverage was not inferred. The model selects standard
or measured wording for all three required application-owned claim bundles;
it does not write unrestricted prose, choose which required findings to omit,
generate numeric placeholders or decide factual predicates.

Input facts <=32 KiB and no more than 128 facts/claims. Model input (system, compact
claim selection data and JSON schema) <=6000 UTF-8 bytes, output <=32 KiB before
parsing. Keep long cluster lists out of inference; their summary count remains a
verified fact and any chosen representative event must follow a documented stable
application selection. The full original summary hash is always pinned. A limit
failure produces safe failed memo state, never a shortened numerical result.

## Additive durable schema

Migration 0007_memos follows 0006_copilot and alters no existing table definition.
Separate tables:

- memo_jobs: run_id UUID-text PK/FK to research_runs and FK to registered
  research_results, numerical_manifest_sha256, summary_sha256, canonical execution
  identity/hash nullable until first execution, state queued/running/retry_wait/
  ready/failed, attempt_count 0..3, model_calls 0..2, nonnegative fencing_token,
  owner/lease iff running, eligible_at, safe error, validated draft/checkpoint and
  provenance JSON nullable, result_sha256 nullable (present iff ready),
  created_at/updated_at database timestamps.
- memo_attempts: (run_id,attempt_number 1..3) PK/FK, unique(run_id,fencing_token),
  owner, DB started/ended timestamps, outcome running/ready/transient/permanent/
  expired, safe error; running iff ended timestamp absent.
- memo_results: run_id PK/FK, supplemental manifest relative path/hash, memo hash,
  summary hash, registered_at DB timestamp. Insert/read only. Ready iff registered
  result identity is present, enforced by transaction protocol and constraints
  where a direct same-row check is possible.

Same run enqueue is idempotent regardless of repeated API/CLI calls. No caller
prompt/model/settings or generation revision is accepted. Ready/failed terminal
jobs cannot be reset, overwritten, refunded or silently regenerated. Safe retry
means another worker invocation resumes eligible queued/retry/expired work within
existing budgets. A new same-run generation protocol is outside R6.

## Numerical publication and explicit historical enqueue

Extend the R4 bounded publication transaction: after fencing the numerical run and
acquiring its run advisory lock, register numerical result, unique pending memo
job pinned to exact numerical-manifest/summary hashes, and numerical success in
one commit. No Ollama access/identification, prompt construction, full artifact
reads or additional expensive work under locks. Failed DB work rolls back all
records; ordinary recovery/adoption retains the existing R4 protocol. Once
committed, memo execution is completely independent.

Explicit per-run enqueue supports already completed R4/R5 runs. Fully verify old
registered artifacts outside locks, then bounded transaction locks research run
and run advisory key, verifies registered identity matches preflight and inserts
missing memo job. Concurrent calls return the same job; absent run 404, numerical
not ready 409, corruption safe error. No migration/startup automatic backfill.
No rewriting old numerical files or resetting existing jobs.

## Claims, fencing, retry and checkpoints

FOR UPDATE SKIP LOCKED claims; queued is immediately eligible without later DB
wall-time comparison. Retry eligibility/lease expiry use clock_timestamp().
Sixty-second lease, separate-connection heartbeat every ten seconds, increasing
fencing token, three attempts including crashes; expired third attempt fails
without a fourth. All worker mutations require current owner/token/unexpired lease
and local not-lost flag. Never resurrect ownership.

At most TWO model calls (one inference retry) reserved durably under ownership
before dispatch; crash consumes reservation, never refund. Persist pinned installed
digest/execution identity before dispatch and validated draft/provenance checkpoint
before filesystem publication. A third execution may publish/recover checkpoint
without inference. Narrow transient network/capacity/deadline/DB errors retry after
10 then 30 seconds if budgets permit; malformed output, unsupported claims,
integrity, digest/source mismatch, storage/unknown errors terminate safely. No
hidden transport retries. Capacity contention does not claim a new attempt or
reserve a call. Heartbeat covers all claimed work; lease loss prevents publication.

Bound an active memo attempt to 180 seconds excluding pre-claim admission, with
120-second inference deadline and bounded identity/DB/filesystem operations.
Cancellation closes/drains local tasks/clients and releases admission; shutdown
stops further claims. Hard termination recovers using lease expiry. Measure actual
server cancellation separately; client close/model-load abortion is not evidence
of active-token cancellation.

## Shared inference lifecycle and priority

Reuse the existing R5 database session inference advisory-lock namespace across
cooperating old-compatible copilot commands and new shared worker. One active
cooperating application model call total. This serializes client dispatch, not
an unconditional guarantee about upstream server work after client timeout,
cancellation or process death; measure and report that behavior separately.
Selection and dispatch use one serialized admission point:
eligible copilot inference has priority over pending memo inference. Recheck
copilot eligibility at memo selection while holding admission. A request arriving
after memo dispatch waits; no preemption. Continuous copilot traffic may delay
memos; no starvation-freedom promise. Recovery work without inference need not
hold model capacity. Do not consume attempts merely waiting for this capacity.

Keep existing copilot worker command functional through shared admission; research
and ingestion remain separate. Add bounded shared inference worker max-jobs 1..62,
no daemon, scheduler or unbounded polling. Model session-lock connections are held
outside transactions and invalidated/closed on every exit, including acquisition
cancellation. Multiple local workers still cannot overlap cooperating application requests.

Use existing configured host Ollama/local-container connectivity and installed
qwen3.5:4b-q8_0 default. No downloads/updates/fallback/request URL or model. Pin and
recheck digest around dispatch, record Ollama version. Temperature 0, think false,
num_ctx 8192, num_predict <=2048, 120s inference timeout. No redirects/environment
proxies/HTTP retries. Missing model fails safely. Provenance includes prompt/schema/
facts/renderer hashes and versions, settings, input/response hash and bounded raw
response, validation reasons, timing, model tag/digest/Ollama version, code/source/
dirty/lock fingerprint. Startup/old result or memo read needs neither model nor Git
checkout. New execution requires compatible lazy provenance; do not weaken R4
incompatible-queued-run protection. Preserve R5 prompt-v3/semantics/handoff.

## Immutable supplemental publication

Stage under owned .staging, then publish a separate directory
research/<run_id>/memo/ containing research_memo_<run_id>.md and manifest.json.
Numerical research/<run_id>/manifest.json/spec.json/results.json/summary.json are
never changed. Supplemental manifest memo-manifest-v1 pins run identity,
numerical manifest/summary hashes, memo hash/size, facts/prompt/schema/renderer
versions/hashes, model tag/digest/Ollama version/settings, input/response hashes,
validation outcome, DB generation timestamp and source/lock provenance.

Flush/hash/fully verify staged files outside locks. In bounded transaction
(10s lock, 15s statement/idle) lock/fence memo job then run-scoped memo advisory
lock, recheck lease and preverified identities, atomically rename supplemental
directory without overwrite, register memo result and complete job/attempt.
No full reads under transaction locks. Crash after rename before commit leaves
undiscoverable orphan; current owner fully verifies/adopts it. Concurrent winner
must be verified outside transaction before reuse. Corrupt orphan/registered
supplement fails without replacement. Registered supplements only; read verifies
manifest/artifact hash and pinned numerical identity before serving.

Temperature zero does not promise identical newly generated prose. Ready replay
returns identical stored bytes. Only local shared storage/cooperating writers,
atomic rename; no cross-system power-loss/replication/external-writer guarantees.
No automatic GC. Numerical APIs remain available when supplement is corrupt.

## API, CLI and observability

POST /v1/research/runs/{run_id}/memo ensures one job for successful historical or
new run; body must be empty (no caller generation options). 201 new/200 replay,
{run_id,replayed}. GET same returns schema memo-status-v1, run_id, public status
pending/running/ready/failed, detailed state, attempts/call count, eligibility,
safe error/provenance and, only when ready and verified, content plus hashes.
Missing job/run 404; nonready numerical run 409; malformed UUID/body 422;
unavailable/overload 503. Safe fixed diagnostics, no prompts/SQL/paths/secrets.
Existing numerical/copilot response shapes stay unchanged.

CLI python -m marketlab.memo_cli enqueue --run UUID; inspect --run UUID;
read --run UUID. JSON success except read may return the exact Markdown through
an explicitly documented option; safe stderr/nonzero operation failures, argparse
2 syntax errors. python -m marketlab.inference_cli worker --max-jobs 1..62.
No arbitrary URL/model/SQL option, no terminal reset/revision flag. DB authoritative;
no memo cache and no mutable status in numerical-summary cache. Metrics have
bounded labels for queue/inference/retries/rejection/publication/outcome; no
prompt/response/IDs in metrics or logs. Dashboards remain R8.

## Acceptance, evidence and preservation

Freeze the R6 actual-model corpus before tuning: 20 valid summaries spanning all
workflows/sparse selections/gaps/nulls/signs/boundaries. >=18/20 useful fully valid
memos within budgets; zero published incorrect facts or unsupported causal/
predictive/recommendation claims across evaluated corpus. Independently audit
the rendered claims/facts; safe rejection is not successful generation. Separate
adversarial suite exercises numbers/units/placeholders/HTML/malformed output and
misleading qualitative claims. Do not count mocked CI as actual-model acceptance.

Real PostgreSQL fresh/populated additive migration and preservation, constraints,
atomic numerical enqueue/rollback/visibility/concurrency, historical enqueue,
queued backward-clock regression, heartbeat/retry/expiry/stale mutation fencing,
three-attempt/two-call budget, checkpoint recovery, actual process kills before/
during/after supplemental publication, orphan adoption/corruption and ready replay.
Real shared worker priority/nonpreemption/multiple-worker client-call no-overlap,
separately observed server cancellation/timeout behavior, model outage,
timeouts/cancellation/capacity release and manual numerical independence required.

Generate actual memos for all five retained monthly scenarios (BTC/ETH profiles,
cross_asset, BTC/ETH clusters) from fully verified retained registered references
covering 62 January partitions/230,311,900 trades. Fresh numerical publication must
exercise automatic enqueue and match retained independent reference numerical
hashes; no re-download. Rerun R5 actual 60-prompt gate because shared admission
changes: >=18/20 clear correct canonical specs, zero unsafe among 40 negatives,
record clarification/refusal versus safe failures separately. Unavailable model/
retained data leaves the relevant acceptance gate incomplete.

Run locked Python 3.13 lint/format/mypy, full offline and real PostgreSQL suites,
focused live legacy HTTP/CLI/import/filter/pagination, historical ingestion, bars/
Redis, research/manual and copilot preservation. Historical 736/174 counts are a
baseline, not an R6 pass. Snapshot protected dataset/numerical files and original
service IDs/images/start times/restart counts/health before acceptance and compare
after. Owned disposable resources only; verify identity/ownership before cleanup.
Never commit artifacts/data/credentials/environments/weights.

Preserve R1 checksums/identity/normalization/manifests/publication/synchronous CLI;
R2 ingestion schema/jobs/limits/retry/leases/fencing; R3 exact bars/admission/cache/
cancellation; R4 strict spec/Decimal80/warm-up/hashes/manual APIs/numerical manifests
(only atomic memo enqueue added); R5 prompt-v3 semantic/clarification/handoff and
budgets (shared inference priority added); all week 1-9 behavior/health/metrics.
Source changes legitimately change execution fingerprint; old completed results
remain readable and incompatible queued work remains rejected.

Record actual attempts, hashes/source snapshot, model/settings/hardware/timing,
all failures, independent review/fixes, cleanup and remaining blockers in
docs/r6-verification.md, README and roadmap. Measure peak memory correctly or
report unmeasured. Local acceptance is not hosted CI. No commit/push in this
authorization. R6 completion grants no R7-R9 authority. Planning estimate 35-55
engineering hours is not measured velocity or a completion claim.


## Local closeout

R6 implementation, independent review, full local acceptance and ownership-checked
cleanup passed; see [actual verification](r6-verification.md). Final checks passed
758 offline/189 PostgreSQL cases. Actual constrained memo gate passed 20/20; R5
rerun retained 18/20 clear correct, zero unsafe among 40 negatives, 25 expected
clarification/refusal and 15 safe failures. Eight registered memos each used one
attempt/one reserved call; three fresh numerical runs matched all independent
reference result/summary hashes. Each profile used 31 partitions; cross-asset
used all 62 January partitions, a union of 230,311,900 trades.
All 229 protected original files and original service identities/start/restart/
health were preserved; owned resources were removed and immutable evidence kept.

The successful ordered profile-then-cross-asset workflow took 2438.450s. The first
cold combined preparation hit the unchanged 1800s bound before durable acceptance;
preserve that failure and distinguish the passing normal-cache sequence. CUDA
was used for model inference; data preparation remained CPU. Peak memory and
upstream active-token cancellation remain unproven. The dirty source fingerprint,
all failures and unresolved system-clock discrepancy remain explicit. No
commit/push or hosted R6 CI occurred; R7-R9 remain unauthorized.
