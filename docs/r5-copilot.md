# R5 durable inbound copilot contract

Approved October 25, 2026 BEFORE code. User authorized this contract, ROADMAP.md/
AGENTS.md updates, prescribed coder/reviewer implementation, full acceptance and
honest outcomes. The initial request excluded commit/push; the later R5
publication authorization below supersedes that restriction only for verified
R5 publication. Historical exclusions are superseded only for
this R5 contract; R6-R9 remain unauthorized. Preserve full R1-R4 contracts.

## Input and semantic validation

Strict copilot-request-v1 requires schema, text, dataset_versions, context. Body
<=64 KiB; text nonempty <=8192 UTF-8 bytes; versions nonempty unique sorted
lowercase SHA-256 set <=62. Context optionally supplies workflow, symbols, start,
end, history_start, interval, metrics with R4 types. Reject unknown/duplicate JSON
keys, coercion, nonfinite values. Keys match ASCII letters/digits/._-, length
1..128. Same canonical key/request replays, conflicting reuse is 409.

Only R4 January BTCUSDT/ETHUSDT five-minute market_profile, cross_asset and
volatility_cluster, metric allowlists, fixed predicates/parameters are supported.
No arbitrary code/SQL/URLs/paths, strategy/predictions, new analytics/downloads,
UI/auth/memos, scheduling/GC, dependency/lock/deployment changes or multi-host claim.

Schema-constrained copilot-interpretation-v1 output is untrusted: outcome
candidate/needs_clarification/unsupported, intent, exact-quote/context evidence for
each supplied field, unresolved field names, allowlisted reason. Application
independently validates shape/evidence/meaning/availability. Model has no tools,
DB credentials, executable instructions or dataset-selection authority. Explicit
BTC/Bitcoin and ETH/Ethereum aliases are permitted. Never silently latest-select,
resolve relative dates, shorten evaluation, change thresholds or fill gaps.

Volume versus VWAP, vague dates/timezone/boundaries, ambiguous market profile
(OHLCV versus TPO), missing history and undefined thresholds require targeted
application-owned clarification. Explicit unsupported assets/intervals/thresholds
are unsupported. Conflicting text/context requires clarification. Application
assembles strict research-spec-v1, fixed predicates and exact needed day/symbol
subset of supplied versions. R4 integrity/coverage/actual warm-up checks precede
acceptance. Schema validity alone does not prove semantic correctness.
The model decoder requires all seven intent/evidence slots, nullable only for
missing values; application normalization removes matching absent pairs after
rejecting unknown keys. Only independently complete grounded intent can submit. Whole-turn extraction
and explicit context are the grounding authority; a model-selected excerpt cannot
supply a missing field or choose a conflicting branch. Preserve multiple-boundary
and negative-selection ambiguity across revisions. Workflow names do not silently
select summary metrics. Exact lexical boundaries exclude identifier fragments.
Prompt-v3 uses request-specific evidence enums containing only actual field source
spans or the context sentinel; this constrains quote generation, never supplies
missing intent. Independent full-turn semantic validation still applies. Prompt,
source and dynamic schema hashes are pinned; this is a constrained interpretation
pipeline, not a claim of unrestricted model understanding.

Answers are strict copilot-answer-v1 with expected_revision, text, context and own
idempotency key/body bounds. Immutable revisions 0..5: at most five answer rounds,
only from needs_clarification. Same answer replays before current-state checks;
stale revision/conflicting key is 409. Obsolete workers cannot finalize a newer
revision. Submitted/unsupported/failed are terminal; use fresh request to restart.

## Durable schema and execution

Migration 0006_copilot alters no existing table. Separate tables:
- copilot_requests: UUID PK, unique key, canonical initial body/hash, revision
  0..5, unique nullable research-run FK, DB created/updated timestamps.
- copilot_revisions: request/revision PK/FK, immutable body/hash, nullable answer
  key unique per request, nullable outcome submitted/needs_clarification/
  unsupported/failed, interpretation/provenance/questions/spec JSON text, DB time.
- copilot_jobs: UUID PK, unique request/revision composite FK, state queued/
  running/retry_wait/completed/failed, attempts 0..3, model_calls 0..2,
  nonnegative token, owner/lease iff running, eligible_at, safe error, DB times.
- copilot_attempts: job/attempt 1..3 PK/FK, unique job/token, owner, DB start/end,
  outcome running/completed/transient/permanent/expired, safe error; running iff
  ended_at absent.

SKIP LOCKED claims; queued immediately eligible without later clock comparison.
DB clock_timestamp retry/lease gates, 60s lease, 10s separate heartbeat, increasing
fencing token, three total attempts including crashes, no fourth. Every worker
mutation matches current owner/token/unexpired lease, active revision and local
lost flag. Narrow transient network/capacity/deadline/DB failures retry after
10s then 30s; validation/integrity/unknown errors terminate. At most TWO model
calls per revision (one retry), reserved durably under ownership before dispatch;
crash may consume reservation, never refund. Persist validated interpretation
and provenance before expensive preparation, allowing recovery without another
call. Third durable attempt may finalize/recover without inference. No hidden
HTTP retries. Missing model/digest mismatch/malformed output fails safely.

## Atomic same-service research handoff

Split ResearchService submit into shared async preparation and connection-owned
registration, preserving manual signatures, outputs, validation and replay.
Model/catalog/artifact/warm-up reads stay outside locks. In bounded transaction
(10s lock/15s statement/idle): lock/fence copilot job, lock request, check active
revision/no run, acquire research-key advisory lock, register through SAME manual
registration operation, write mapping/revision submitted/job/attempt completion.
Recheck lease before writes. Research key is application-owned copilot.<request
UUID>. Unique mapping/key ensure one committed handoff per request. Rollback
leaves neither run nor mapping; crash after commit replays result. External model
execution is bounded at-least-once, not exactly-once. Submitted means queued
research run, not numerical success. R4 workers/publication/results/cache remain.

## Model, interfaces, provenance and limits

Existing Ollama configuration/default qwen3.5:4b-q8_0. No pulls/updates/fallback or
request-supplied URL/model. Inspect/pin installed digest/version, temperature 0,
think false, 8192 context, bounded prediction, 120s inference deadline. One active
call among cooperating workers using namespaced DB session advisory lock held
outside transactions. No memo priority yet. Cancellation closes local HTTP work;
actual server cancellation behavior must be measured, not assumed.

Response <=32 KiB before parsing. Total text/context plus system/schema input
<=6000 UTF-8 bytes, reserving 2048 output tokens and framing within the 8K window;
dataset IDs are excluded from model input (application alone selects them); never silently truncate. Worker max jobs 1..62; R4 preparation retains
30-minute timeout and shared BarService admission. Heartbeat covers all work;
cancellation drains R4 work and closes model client. Persist model tag/digest/
Ollama version, prompt/schema/settings, bounded response/hash, input hash, timing,
code/source/lock provenance and safe validation reasons. Metrics bounded labels
for outcomes/retries/rejection/queue/inference/handoff; logs/labels omit prompts,
responses and IDs. DB authoritative; no conversation cache. Startup and old
result retrieval need neither model nor checkout; execution provenance lazy.

Add POST /v1/copilot/requests, GET same /{request_id}, POST same /{request_id}/
clarifications. Require JSON/stream body cap. Creation promptly durable queued
201 (200 replay), request_id/revision/replayed. Inspect ordered revisions/attempts,
state, nullable outcome, questions, provenance, safe error and run_id. 422 invalid,
404 absent, 409 key/revision/state conflict, 503 unavailable, fixed safe errors.
CLI create --request FILE --key KEY; answer --request ID --answer FILE --key KEY;
inspect --request ID; worker --max-jobs 1..62 [--request ID]. JSON success, safe
stderr/nonzero error, argparse 2 syntax error. No arbitrary server/model options.

## Acceptance and preservation

Offline: strict parsing/bounds, evidence/semantics, exact spec assembly,
clarification conflicts/adversarial inputs, malformed/timeout/digest behavior,
API/CLI and admission/cancellation cleanup. Real PostgreSQL: fresh/populated
migration/constraints/preservation, concurrency/idempotency/answers/claims,
backward-clock queued regression, heartbeat/expiry/stale ownership/revision,
three-attempt/two-call budget, atomic rollback/visibility, actual process kills
before/during/after handoff without duplicate/unlinked runs. Real model outage/
cancellation and manual numerical availability are required.

60 prompts: 20 clear, 20 ambiguous/invalid, 20 adversarial/unsupported. Actual
model gate >=18/20 clear correct canonical specs, zero invalid/adversarial
executions. Record clarification quality/all failures, separate mocked CI; full
R8 eval/benchmark remains backlog. Two profiles, cross-asset and both clusters
via copilot over all 62 retained January versions: compare exact specs/every
numerical results/summary hash to manual and retained independent reference,
no downloads. Verify source artifacts unchanged.

Run locked Python 3.13 lint/format/mypy/full offline/real DB and live legacy API/
CLI, ingestion, bars/cache and research checks. Historical baseline 655/158 is
not a new pass. Record actual hashes/attempts/timings/hardware/model failures,
measured memory only (otherwise unmeasured), limitations/blockers in
r5-verification.md, README, roadmap. Owned disposable resources only; verify
ownership before cleanup; preserve original IDs/start times/health/data. No
Docker/WSL/initd/time experiments/restarts. Clock discrepancy persists; preserve
application workaround. No market artifacts/data/credentials/environments/weights
in Git. The initial no-commit/push restriction is superseded only by the later
R5 publication authorization below.

Preserve R1 identity/normalization/checksum/manifests/publication/CLI; R2 schema/
jobs/retry/fencing; R3 exact bars/admission/cache/cancellation; R4 strict specs,
Decimal80/warm-up/manual APIs/results/execution/provenance; all week 1-9 trade/
import/filter/pagination/CLI/health/metrics. R4 hashes all Python source: R5
changes fingerprint, old completed results stay readable, incompatible queued
runs remain rejected. Never weaken provenance.

Coder gpt-6.1-sol high; independent read-only reviewer gpt-6-astra medium; coder
resolves actionable findings/reruns relevant checks before actual closeout.

## Approved-scope closeout

R5 implementation, full local acceptance, independent read-only review and
ownership-checked cleanup completed October 25, 2026. See
[actual verification](r5-verification.md) for all results and historical failures.
Final checks passed 736 offline/174 real PostgreSQL cases. Frozen v3 passed
18/20 clear correct and zero unsafe negative submissions, with 25/40 expected
negative clarification/refusal and 15 safe failures. Ten full-month runs matched
all retained independent reference hashes; original artifacts/services were
preserved and owned resources removed. Dirty-source provenance, unmeasured peak
memory, known clock discrepancy and final load-abortion versus token-cancellation
limits remain explicit. At local closeout no hosted CI or publication had
occurred. Later explicit publication authority is recorded below; R6-R9 remain
unauthorized.

## Publication authorization (October 25, 2026)

The user subsequently authorized committing/pushing verified R5, checking hosted
CI, fixing actual R5-only CI failures through the prescribed coder/reviewer
workflow, and documenting/publishing actual outcomes. This supersedes the initial
no-commit/push restriction only for this scope. Preserve R1-R4 contracts and all
local verification provenance, model-quality limits, failed evaluations, known
clock discrepancy and cancellation evidence. No feature scope expansion or R6-R9
authorization follows. Archives/artifacts/data, credentials, environments and
weights remain excluded from Git.

Publication and hosted CI outcomes were unobserved at that authorization
update; the actual later outcome follows. Record actual results for the exact published revision in verification;
local acceptance is separate from hosted smoke coverage.

## Publication and hosted CI verified (October 25, 2026)

Verified implementation 19a136350e53418e46e99f739597e231628a8f55 was committed/
pushed normally to origin/main. [Hosted CI run 40177491693](https://github.com/atharva-m/MarketLab/actions/runs/40177491693)
passed for that exact revision: 736 offline cases on each of Ubuntu and Windows,
174 real PostgreSQL cases on Linux and quality/build/API/optional-Redis-outage/
cleanup checks. No CI fix was needed. No market artifacts/data, credentials,
environments or weights were included. No R6-R9 authority follows.

Hosted smoke does not replace or rerun local actual-model/month acceptance.
Its original dirty-source identity, quality limitations, known clock discrepancy
and all failed historical evidence remain intact in [verification](r5-verification.md).
