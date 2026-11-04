# V2 Phase 5: selected-catalog copilot and grounded memos

The reviewed `copilot-prompt-v7` revision changes only the final paragraph of
v6. The exact replacement is the following text with a final LF. The complete
prompt is 1,731 bytes with SHA256
`a0f0d25af2189d2d775f4a994433c78cb50576b95dadcdbbdc376a6cef5e09b9`.

> Choose outcome after checking the request, intent and evidence. For a supported request with all seven fields explicitly grounded and compatible, return candidate, reason none, unresolved []. An explicit compatible metric list is resolved, including a single metric. Clarify only actual missing, conflicting or ambiguous meaning. Mark unsupported only for an actual unsupported request. All-null only if none usable.

Current normative amendment 004 (November 2, 2026): v5 development failed its first
evidence-grounding probe and closed safely. Independent pre-code review approved
the exact [request-specific evidence grammar](phase-5-evidence-grammar.md) packet,
compact prompt-v6, explicit grammar/semantic/execution identities and only the
redundant `cross_asset comparison` lexical correction. This supersedes prior
new-work prompt/generation-grammar requirements and that one lexical rule only;
independent decide() and all other rules, output wire shape, full literal cohorts/
thresholds, pinned model/settings and limits remain unchanged. Preserve twelve
requests/eleven calls, the queued unexecuted handoff and twenty original memo jobs.
Implementation review, full freeze/input/launch, all eight actual development
passes and all mandatory acceptance remain separate gates. No operational release
or Phase 5 completion follows; earlier checkpoints remain historical.

Current normative amendment 003 (November 2, 2026): v4 unscored development
failed on its second probe's quote provenance after the first text probe passed.
Independent pre-code review approved [uniform evidence priority](phase-5-evidence-priority.md),
exact prompt-v5 bytes/version and minimal fresh binding. This supersedes earlier
new-work prompt-version requirements only. All eleven requests/ten calls, the
unexecuted queued handoff and twenty old memos remain immutable. Validators,
context/interpretation schemas, fixtures/cohorts, model/settings and limits stay
fixed. Implementation and all actual freeze/launch/acceptance gates remain pending
at this entry. Earlier statuses and source-qualified outcomes are historical.

Current normative amendment 002 (November 2, 2026): the separate v3 development
invocation failed safely on invalid evidence despite correct intent values.
Independent pre-code review approved the exact
[evidence prompt correction](phase-5-evidence-correction.md) and minimal new-directory
binding. This supersedes earlier copilot prompt-v2/v3 requirements only for new
v4-source work; old records/identities remain unchanged. Runtime validators,
interpretation/context schemas, model/settings, limits and all literal development/
acceptance inputs remain fixed. Implementation/freeze/launch review and actual
inference remain pending at this entry; all earlier checkpoints remain historical.

Current normative amendment (November 2, 2026): the original scored copilot
campaign failed and is preserved. Independent pre-code review approved the
[prompt correction](phase-5-prompt-correction.md), exact copilot-prompt-v3 bytes
and bounded separate development proposal. That amendment supersedes the original
copilot-prompt-v2 requirement below only for newly created corrected-source work;
all original records and identities remain unchanged. Memo prompt/grammar, all
independent validators, literal acceptance cohorts, pinned model/settings and
limits remain fixed. Implementation/development review and fresh acceptance are
pending at this entry. The original pre-code status below is historical.

Status: PRE-CODE CONTRACT; INDEPENDENT DESIGN REVIEW PASSED. November 2, 2026
(America/New_York). This document precedes runtime edits and model dispatch.
Requirements describe proposed behavior, not observed acceptance. Actual outcomes
belong in [verification](phase-5-verification.md).
Independent read-only review found no unresolved blocking finding at contract
SHA256 `366c89f0d12657da111fe78f6f0f553de7e648f1f41dd9de50cb9261aa97e062`.
This status note records that result; implementation and literal frozen
fixture/prompt review remain pending.

## 1. Authority and preserved boundaries

The user approved Phase 5 in [ROADMAP_v2](../../ROADMAP_v2.md), the
[Phase 1 contract](phase-1-contract.md), [compatibility](compatibility-matrix.md)
and [acceptance](acceptance-matrix.md): document first, implement through coder
`gpt-6.1-sol/high`, then independent read-only reviewer `gpt-6-astra/medium`.
Resolve blocking design findings before runtime changes or inference and blocking
implementation/acceptance findings before closeout. NO COMMIT OR PUSH.

Deliver generalized copilot and memos through the local API, CLI, browser and
bounded durable workers. Support only registered Binance spot instruments,
explicit immutable daily versions and the existing market_profile, cross_asset
and volatility_cluster workflows. Preserve formulas, Decimal80 values, all legacy
interfaces/artifact bytes/readers, synthetic `/trades`, historical failed outcomes,
source/lock compatibility, resource limits, conservative accounting and numerical
independence. Existing README GIF and protected artifacts remain byte-exact.

No other venue/market/provider, automatic data fetching from model output, new
workflow, free-form model tools/code/SQL, model upgrade, prompt tuning during
scored evaluation, dependency/lock change, currency conversion, Phase 6 storage,
Phase 7 multi-host execution, Phase 8 authentication/customer isolation, Phase 9,
scheduling/automatic GC, original-service change/rollout, purchase or unrelated
repair follows. Local routes carry existing stack-operator authority, not customer
identity or Internet deployment guarantees. Raw evidence, data, dumps, archives,
weights, credentials and generated media remain outside Git.

## 2. Inspected baseline and implementation ownership

Read-only inspection started at clean HEAD
`ecc438650f9fdcdf6e30b893cdf02e712a04c593`. Migration head is
`0010_v2_browser_imports`. Legacy `copilot/{spec,model,store,service}.py` implements
interpretation-v1/prompt-v4, January BTC/ETH evidence checks and durable revisions;
`memos/` implements facts/draft/renderer-v1. `inference.py` supplies the shared
session advisory lock. `research/v2/` has verified immutable numerical results
and no v2 memo enqueue. `datasets/v2/admission.py` supplies the root-bound quota
and native ownership ledger. These are inspected facts, not new tests or live
model/service observations.

Implement new contracts under `copilot/v2/` and `memos/v2/`; use narrow dispatch
in app lifecycle, existing CLIs, v2 routes, capability reporting and frontend.
Reuse the v2 manual numerical service, shared inference admission, canonical JSON,
local mutation policy and artifact safety helpers. Preserve old public parsers,
schemas, table state and prompt/renderer constants. Shared helper edits must
preserve legacy semantics and receive affected legacy checks. New forward-only
migration is `0011_v2_copilot_memos`, following `0010_v2_browser_imports`; no edited
historical migration or destructive downgrade. Protocol fixtures and acceptance
runner are scoped Phase 5 source; retained helper/evidence archives are not Git
content. One active acceptance runner and one bounded owned-lifecycle helper are
sufficient; do not resurrect redundant harnesses or global process forensics.

## 3. Strict local interfaces

All control JSON uses strict UTF-8, <=64 KiB, rejects duplicate/unknown keys,
nonfinite numbers, bool-as-int/coercions and oversized/deep structures. Use existing
canonical JSON (sorted keys, compact separators, ASCII escaping, terminal LF),
UUID grammar and `[A-Za-z0-9_.-]{1,128}` operation keys. Every mutation requires
Idempotency-Key and existing same-origin/Fetch Metadata checks before body work.
No arbitrary CORS or remote URL/credential/path/prompt/model fields.

| Surface | Exact contract |
| --- | --- |
| POST /v2/copilot/requests | `copilot-request-v2`: exactly schema, text, context, instrument_ids, dataset_versions. Text is nonempty <=8192 UTF-8 bytes as in v1, subject to the unchanged aggregate 6000-byte inference limit below. Context is a partial object of workflow, instrument_ids, start, end, history_start, interval, metrics; never versions. Top-level selected set contains 1..2 distinct explicit instrument IDs; versions contains 1..62 explicit registered IDs. Both arrays sort uniquely; duplicates reject. Context instruments, when present, must be a subset of that set. |
| GET /v2/copilot/requests/{id} | `copilot-status-v2`: immutable input/snapshot identities, current revision 0..5, bounded revision outcomes/questions, state/error, reserved call count and optional sole research run/spec/reference. No secret, internal path or arbitrary model prose. |
| POST /v2/copilot/requests/{id}/clarifications | `copilot-answer-v2`: exactly schema, expected_revision, text, context. Same text/context bounds; expected_revision integer 0..4. Selection/snapshot cannot change. New selection requires a fresh request/key. |
| POST /v2/research/runs/{id}/memo | Exactly `{"schema":"memo-request-v2"}`. Successful verified v2 numerical result only; idempotently create the single supplemental job or return existing state. No regeneration/reset, caller claims, renderer/prompt/model choices. |
| GET /v2/research/runs/{id}/memo | `memo-status-v2`: missing/pending state separately from numerical state, pinned numerical hashes, job budget/error and verified three-paragraph artifact when succeeded. Missing job is 404; queued/running/retry_wait/failed remains readable without inference. |

CLI adds explicit `v2` create/get/answer/worker operations for copilot and
enqueue/get/worker for memo, with JSON-file input and bounded `--max-jobs 1..62`,
optional exact request/run filter and existing bounded wait <=3600s. Legacy CLI
forms retain their parsers. Browser reuses Phase 4 explicit daily-version controls,
then offers optional copilot with editable structured context, durable questions,
revision status and linked numerical result. Memo is a supplemental panel/action;
numerical results/charts remain usable during any model failure. Render plain text
through existing safe React text nodes; never HTML/Markdown from model/metadata.

Validation is 422, missing ID 404, key/revision/state/selection conflict 409,
quota/admission 429 with bounded Retry-After and unavailable catalog/storage/model
503. Once queued, transient worker failures are durable safe job errors, not
retroactively successful HTTP calls. Public errors use bounded allowlisted codes
and messages; detailed native evidence belongs only in bounded retained provenance.

## 4. Frozen selected context and independent grounding

At creation verify every selected version through the existing catalog verifier,
its registered instrument/semantic mapping and immutable manifest. Reject missing,
foreign, duplicate-day alternative or unselected-instrument versions; no latest or
preferred version. Selected coverage may include a bounded superset until intent
is known; final handoff must use exactly one pinned selected version per touched
instrument/day and no extras, following the manual spec rules. Disabled registry
instruments remain eligible for retained readback as in Phase 3. Store a canonical
`copilot-selection-v2` snapshot containing the exact selected metadata, official
symbol/base/quote codes, application-owned alias mappings, per-day version IDs,
manifest/semantic hashes, observed coverage, registry hash and capability hash.
Snapshot <=64 KiB; reject excess without truncation. Full dataset IDs never enter
the model grammar or its output.

The model receives only this request's max-two instruments, represented by stable
slots `i0`/`i1`, exact official symbol/base/quote identity, compact coverage runs,
allowed workflow/metric names and the bounded user turns. Do not pass the entire
catalog, files, raw trades, URLs or arbitrary display descriptions. Full pinned
snapshot remains stored; a hash binds the compact `copilot-model-context-v2`
projection to it. Display labels are untrusted escaped data and cannot define
aliases or instructions. The application owns aliases derived from exact
registered source symbol and base/quote codes plus the preserved exact BTC/ETH
name mappings where applicable; no fuzzy matching or symbol splitting. A base
alias mapping to multiple selected quote/instrument choices requires clarification;
unselected instruments, non-Binance venue and derivatives never enter a handoff.

`copilot-interpretation-v2` has exactly schema, outcome, reason, intent, evidence,
unresolved. Outcome is candidate/needs_clarification/unsupported. Reasons remain
none/missing_fields/ambiguous/unsupported/conflict/coverage. Intent has exactly
workflow, instruments, start, end, history_start, interval, metrics; absent fields
are null, instrument values are selected slots only. Evidence has the same keys:
null, exact user substring <=160 characters with turn number 0..5, or structured
context reference with turn number. Unresolved is a unique allowlisted field list
(plus meaning/coverage); no free-form instructions. Grammar excludes dataset IDs,
paths, tools, thresholds, SQL, code and model changes. Pin prompt
`copilot-prompt-v2`, interpretation, context projection and handoff identities
with hashes; never reuse legacy prompt-v4 under changed bytes.

Independently parse *all* turns, including after punctuation, through deterministic
allowlisted field extraction and exact evidence checks. Resolve explicit official
symbols/aliases only against the snapshot, normalize explicit UTC timestamps and
existing workflow/metric aliases, and require every candidate field be proved by
text or structured context. Unsupported intent wins over otherwise valid context;
conflicting evidence clarifies, unknown semantics clarifies, no inferred defaults.
Later explicit answers may resolve previously identified missing/ambiguous fields;
they cannot silently override an unrelated conflicting explicit value. A claimed
candidate never outranks an independent unsafe/uncertain determination. Failure
to ground any candidate is safe clarification/refusal/failure with zero handoff.

Application maps slots to pinned IDs, derives only the selected versions needed
for the explicit range, and builds `research-spec-v2` with its fixed parameters/
predicates through the *same* parser, catalog preparation, resource admission,
warm-up/coverage checks and submit service as manual input. Equal quote assets,
62 total partitions, 17,856 expected five-minute buckets including warm-up and
actual >=12/profile/comparison or >=300/cluster history remain mandatory.
No model-selected version and no auto-download. Persist the exact canonical spec
and fingerprint. Hold no DB lock while verifying files/computing preparation.

## 5. Revisions, retries, checkpoints and atomic handoff

Revision zero is the initial request. Each accepted clarification answer increments
once, through five accepted answers/revision five and a real sixth model response.
Only a completed needs_clarification revision without run_id accepts an answer.
Validate expected_revision integer 0..4 before mutation: a sixth answer with
expected_revision=5 is 422; a valid-shaped stale revision is 409. Under request row
lock check prior answer-key replay first: same key/body returns its old revision,
different body conflicts, neither creates work/calls. New keys with stale revisions
conflict. Once submitted/unsupported/failed or revision-five clarified, no new
revision; keep outcomes readable. No forced DB edits to pass clarification gates.

Workers acquire the existing shared `marketlab:copilot:inference-v1` session
advisory admission before claiming work. Legacy and v2 copilot eligible work take
priority over legacy/v2 pending memos at selection. Both legacy and v2 memo
selectors must consult a combined legacy/v2 eligible-copilot check while holding
that exact admission lock; adding only a new v2 selector would leave a priority
bypass in the legacy memo path. Single cooperating dispatch,
no preemption or starvation guarantee; no attempt or call spent waiting. This
local shared-lock integration is not Phase 7 multi-host acceptance. Use DB clock,
60s lease, 10s independent heartbeat, monotone fence, three total attempts including
crashes, retry delays 10s/30s and existing bounded transaction deadlines (10s lock,
15s statement/idle). Claim only exact execution/source/lock/protocol compatibility.

Before external dispatch: build/check the full input, identify the exact model,
checkpoint pinned identity, then under current lease/fence atomically reserve one
of two calls *per revision* and append its reservation record. Never refund on
crash, timeout, malformed output or unknown dispatch completion. Native response
and its hashes/settings are checkpointed before interpretation/handoff; reuse a
valid compatible checkpoint after crash without another call. Two calls are an
upper bound, not a promise to retry permanent invalid output. Transient failures
may retry within both attempt and call budgets; exhausted work fails safely.
Admission/claim precedes no long preparation held under an inference transaction.

After inference checkpoint release model admission before numerical preparation.
The handoff transaction locks request then current revision/job, checks the exact
revision/fence/unexpired lease/no existing run, and uses a connection-taking v2
manual submit helper with deterministic reserved key `copilot-v2.<request_uuid>`.
Submit row/selection/run creation, request run_id, canonical accepted spec and
submitted outcome commit together; same key/spec replays exactly one run. Reserve
that key namespace from direct manual callers. Existing run_id must match the
stored spec hash or fail integrity. A stale worker cannot publish a handoff. Death
before commit creates no research; death after commit replays the sole run.
Model uncertainty/outage never blocks manual research or modifies a numerical run.

## 6. Memo enqueue, facts and rendering

For new Phase 5-source numerical successes, register the pending v2 memo row in
the *same numerical publication transaction*, using the numerical manifest and
summary hashes and the new memo execution contract, without identifying/calling
the model. This small row does not perform model or memo filesystem admission;
model/quota problems remain supplemental and cannot invalidate numerical success.
All preexisting successful v2 runs remain unchanged until explicit memo POST/CLI.
That operation first verifies the immutable numerical result with a compatible
reader outside locks, then locks the run/result, rechecks registered hashes and
inserts one pending job. Its memo execution identity is the current v2 memo build;
the original numerical execution/fingerprint remains pinned separately, never
rewritten to current source. No migration backfill or automatic old-run model work.

Same-run enqueue always returns the existing job, including terminal failed state;
different idempotency keys cannot create a second memo. Same key/changed body or
hash mismatch conflicts. Queued old-contract work stays inspectable and explicitly
incompatible with a new worker, never silently upgraded/reset. Legacy memo jobs
and routes remain legacy; existing v1 numerical runs do not become v2 memo runs.

Read only hash-verified `research-summary-v2` plus pinned spec/metadata. Build
`memo-facts-v2` from selected approved metrics, inclusive/exclusive UTC scope,
instrument IDs/official symbols/base/quote units, observation counts, exact decimal
strings, null reason allowlist and observed-only limitation. <=128 facts and
<=32 KiB canonical facts, finite validated decimals, integer counts and bounded
allowlisted strings. No event/trade arrays, unselected metrics, display-label
instructions or currency equivalence. Profile claims include all selected profile
statistics; comparison includes each selected correlation/difference metric and
counts/null reason; cluster includes approved aggregate event/return/volume facts
only. No recomputing/changing formulas. Unit assertions are pinned metadata, not
hardcoded USDT or model text; dimensionless correlation/returns remain so.

`memo-draft-v2` is exactly schema and three paragraphs in order scope/findings/
limitations. Each paragraph contains only its required claim ID and wording enum
standard/measured; the model chooses no numbers, symbols, units, arbitrary prose
or omitted claims. `memo-prompt-v2` receives only approved placeholder claim
structure, never numerical values or arbitrary metadata. Application validates
all required selected claims and renders `memo-renderer-v2` using exact facts and
approved templates. Output is exactly three nonempty paragraphs separated by
`\n\n`, <=16 KiB, no invented figure/unit/cause/forecast/recommendation/strategy
return. Valid JSON alone never passes the grounding gate. V1 renderer/files remain
available byte-exact for old reads. No deterministic fallback masquerades as a
successful model-produced memo.

Persist verified facts, draft, bounded provenance, memo text and manifest under
unique attempt-specific contained `memos-v2/<run_uuid>/<attempt_uuid>/` directories;
publish by DB reference, never overwrite a registered winner. Manifest records
schema, run ID, original numerical manifest/summary/fingerprint, memo execution,
facts/prompt/draft/renderer/settings/model identities, exact artifact bytes/hashes.
Bound each complete package to 1 MiB, including <=32 KiB response per call and
bounded provenance. Full I/O/readback outside transactions; final memo registration
locks run then memo job and root quota, verifies owner/token/lease and numerical
hashes, then atomically inserts result, terminal success and accounted bytes.
Crash-written unregistered directories remain retained/charged; compatible valid
checkpoint reuse does not create/refund another dispatch or overwrite the winner.
Reads verify registration and every artifact hash/length/schema without current
model, Git checkout, new computation or source-execution compatibility requirement.

## 7. Fixed inference and root accounting

The only model is `qwen3.5:9b-q4_K_M`, digest
`56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90`.
Temperature 0, think=false, num_ctx=8192; copilot num_predict=-1, memo 2048.
Native deadline 120s, response <=32 KiB, no redirects/environment proxy/hidden
transport retries/model pulls. Verify model tag/digest before and after dispatch;
missing/mismatched/changed identity fails safely with truthful call reservation.
EOF, malformed/oversized JSON, context exhaustion/done_reason length and timeout
never yield a handoff or rendered success. HTTP closure does not prove upstream
token cancellation or noncontinuation; record separately observed behavior.

Compute *before reservation/dispatch* the exact UTF-8 bytes of system prompt +
canonical grammar + complete compact model context/all accumulated turns. Sum
<=6000; no silent truncation, summarization, dropped turn or context expansion.
Full snapshot/64-hex versions remain application-only. Initial/answer preflight
must include the actual frozen prompt/grammar and all turns, rejecting over-budget
new intake with 422 and zero new work/calls; worker repeats it against persisted
hashes. A previously accepted incompatible/over-budget stored job fails closed.
Memo similarly counts complete claim projection, prompt and grammar; <=32 KiB
facts does not imply they fit inference. Literal prompts/grammars must demonstrate
the intended five-answer transcript fits 6000 before acceptance; raising the limit
is excluded. Model may see only context that the stored projection hash represents.

Copilot control rows/call traces stay bounded in PostgreSQL (six revisions, two
calls each, per-call response <=32 KiB); no copilot data-root files or scratch
reservation. Bound each persisted revision provenance/checkpoint <=128 KiB and
execution/snapshot <=64 KiB; retain previous calls in their separate rows. Database
backup growth is measured separately from the existing data-root byte ceiling.

Memo filesystem writers use the exact existing `v2-space:<canonical_root>` lock
and root binding. Extend the admission-ticket role allowlist with `memo` through
the new migration only; preserve the existing combined ingestion/research/legacy
ticket pool of eight and upload pool of four. Exclude memo tickets from that
eight-slot predicate without excluding legacy tickets or giving legacy work a
separate pool. Memo has no new numerical/ingestion slot: shared one-model admission
bounds dispatch, and at most one claimed memo per worker. Acquire a native
birth/domain/child-checked owned ticket before writing with 1 MiB logical and
physical reservation per attempt; aggregate with every existing baseline,
generation, ingestion, research and active charge under the same 100 GiB ceiling.
No independent quota pool or root lock spelling. Free-disk checking includes all
outstanding reservations and memo packages; no lowered physical prerequisites.

On partial/crash/failure retain actual bytes and conservative outstanding charge
until verified reconciliation; reserve fresh bytes for a new attempt without
refunding old ones. If process death/foreign domain cannot be proved, keep charge
and fail closed. On success reconcile exact package size; release only unused
reserved bytes after writer drain and verified inventory. Extend reconciliation
epoch inputs and registered-artifact verification to v2 memo jobs/results and
their charges so a quiesced re-inventory absorbs bytes once, not twice. Legacy
memo file writes in a bound Phase 5 stack must use the existing legacy ticket
path/conservative shared charge rather than bypass the quota; preserve legacy
rendered bytes. Missing required migrated ledgers fail closed at new head too.
No automatic artifact deletion or cleanup based solely on age/lease expiry.

## 8. Concrete additive database supplement

All IDs below are UUID, hashes lowercase 64-hex with CHECK, canonical JSON stored
as text with octet-length CHECKs; required fields NOT NULL unless marked nullable.
Use timestamptz `clock_timestamp()` for created_at/updated_at/eligibility/leases.
No cascade deletion; terminal records and checkpoints are service-immutable.
Service validates canonical JSON and digest equality on write/read; SQL enforces
bounds, FKs, uniqueness, state/count/owner invariants rather than trusting JSON.

| New table | Columns, constraints and indexes |
| --- | --- |
| v2_copilot_requests | request_id PK; idempotency_key varchar(128) UNIQUE; request_sha256; body_json <=64 KiB; snapshot_json <=64 KiB, snapshot_sha256; execution_json <=64 KiB, execution_sha256, lock_sha256; current_revision int CHECK 0..5; run_id nullable UNIQUE FK v2_research_runs; created_at, updated_at. Index execution_sha256,created_at. |
| v2_copilot_revisions | (request_id,revision) PK/FK requests; revision CHECK 0..5; body_json <=64 KiB, body_sha256; answer_key nullable varchar(128), UNIQUE(request_id,answer_key), CHECK revision=0 iff answer_key NULL; outcome nullable enum submitted/needs_clarification/unsupported/failed; interpretation_json <=32 KiB nullable, provenance_json <=128 KiB nullable, questions_json <=8 KiB nullable, spec_json <=64 KiB nullable, spec_sha256 nullable; created_at. CHECK submitted iff spec/hash present after outcome set; only submitted links the request run_id in the service transaction. |
| v2_copilot_jobs | job_id PK; (request_id,revision) UNIQUE composite FK revisions; state queued/running/retry_wait/succeeded/failed; attempt_count 0..3; model_calls 0..2; fencing_token bigint >=0; owner nullable; lease_until nullable; eligible_at; error_code nullable varchar(64); created_at,updated_at. CHECK state=running iff owner+lease both nonnull; other states both NULL. Index state,eligible_at,created_at,job_id and state,lease_until; execution compatibility joins request. |
| v2_copilot_attempts | (job_id,attempt_number) PK/FK jobs; attempt_number 1..3; owner, fencing_token >0, started_at, ended_at nullable; outcome running/succeeded/retry_wait/expired/failed; error_code nullable. Index job_id,started_at. |
| v2_copilot_calls | (job_id,call_number) PK/FK jobs; call_number 1..2; attempt_number and composite FK attempts; fencing_token >0; model_digest, input_sha256, schema_sha256, prompt_sha256; reserved_at; finished_at nullable; state reserved/checkpointed/failed; response_text nullable <=32 KiB, response_sha256 nullable; provenance_json nullable <=128 KiB. CHECK checkpointed requires response/hash/provenance; failed does not erase reservation/response. |
| v2_memo_jobs | run_id PK/FK v2_research_results; numerical_manifest_sha256, summary_sha256, numerical_fingerprint_sha256; execution_json <=64 KiB, execution_sha256, lock_sha256; state,attempt_count,model_calls,fencing_token,owner,lease_until,eligible_at,error_code,created_at,updated_at as copilot jobs; draft_json nullable <=32 KiB, provenance_json nullable <=128 KiB. Same state/count/owner CHECKs and due/lease/execution indexes. Execution identifies all new memo contracts separately from original numerical execution. |
| v2_memo_attempts | (run_id,attempt_number) PK/FK jobs; same attempt constraints as copilot; attempt_uuid UNIQUE; relative_path UNIQUE; ticket_id nullable UNIQUE FK v2_admission_tickets; charge_id nullable UNIQUE FK v2_data_charges. Nullable until admission succeeds; both present together before writes. |
| v2_memo_calls | (run_id,call_number) PK/FK jobs; call_number 1..2 across the *whole run*; attempt_number composite FK attempts; same reservation/response/hash/provenance constraints as copilot_calls. |
| v2_memo_results | run_id PK/FK jobs and FK numerical results; attempt_number composite FK memo_attempts; relative_path UNIQUE; manifest_sha256, memo_sha256, facts_sha256, summary_sha256; package_bytes CHECK 1..1048576; registered_at. No current-source/model dependency for verified reads. |
| v2_memo_operations | idempotency_key varchar(128) PK; run_id FK memo_jobs; request_sha256; created_at. Same-key different run/body conflicts; different keys reference the sole same-run job without reset. |

Revision rows plus increasing current_revision are serialized under the request
lock; only append accepted answers. Job calls counter and call row increment in
one fenced transaction. Attempt_count increment and attempt insertion atomic;
expired attempts retain ended_at/outcome, no replay/reset. Final outcome/sole run
or memo result/state commit atomically. CHECKs do not claim to enforce arbitrary
JSON semantics; those are strict service validation and meaningful integration
tests. Required read paths verify stored hashes, not best-effort parsing.

Only existing-table DDL is the exact admission-ticket role CHECK extension to
include memo; identify the existing named/normalized definition and fail migration
on unexpected schema. Existing admission currently counts every non-upload role
against eight; replace that predicate with the explicit ingestion/research/legacy
set to exclude only the new memo role. Combined eight-slot and four-upload
semantics otherwise stay exact. Fresh/populated migration rehearsal must demonstrate no rewritten
legacy rows/constraints/artifacts. Additive tables are empty on migration; no
queued job claim, snapshot construction, model output or memo backfill occurs.
Old binary rollback is limited to its old surface; retain new tables/data, restore
a coordinated verified backup to an isolated environment rather than downgrade.
The migration sets the existing capacity root ready=false; an explicit quiesced
inventory/registered-artifact verification must establish a fresh receipt including
retained memo generations, charge ownership and the expanded audit epoch before
writers resume. It does not silently trust a pre-Phase-5 receipt or release charges.

## 9. Frozen mandatory actual-model and data acceptance

[P5-01..05](acceptance-matrix.md) remain unchanged, including every planned
<=1s owned-worker sample. Before the first scored inference write literal prompts,
structured contexts/selected version IDs, expected exact specs/outcomes, all five
clarification answers, memo run selections/required claims, immutable input
provenance, scoring code and hashes into reviewed fixtures. Freeze v2 system
prompts, grammars, fact/renderer bytes and protocol/source identities too. Conduct
independent fixture/design review before scoring. No tuning between cohorts,
threshold change, post-hoc supplement or fixture/mock replacement for actual gates.
Scored failures remain failures with raw receipts; any required amendment is
prospective, independently reviewed and retains the failed invocation.

| Gate | Required observed acceptance |
| --- | --- |
| P5-01 | Two independently invoked frozen 60-case cohorts each with 20 clear (four for each retained five scenario shapes: first-instrument profile, second-instrument profile, comparison, first-instrument cluster, second-instrument cluster), 20 ambiguous/invalid, 20 adversarial/unsupported. Each >=18/20 exact canonical valid clear specs and exactly one durable run per clear success; zero unsafe handoffs among all 40 negatives. Classify clarification/refusal/safe failure and no-call HTTP rejection separately; account every reservation/dispatch/outcome. At least three Binance instruments, two non-January dates, official and canonical numeric-ID source data. |
| P5-02 | Two frozen 20-run memo cohorts, four per same scenario shape, old/new coverage, selected metrics, valid null reasons and two quote/base units; each 20/20 actual valid grounded memos, all required selected claims and exactly three paragraphs, zero invented numbers/units/causes/recommendations. Review every sentence against exact facts, not merely JSON. Fresh numerical automatic enqueue and explicit preexisting-run enqueue both exercised. |
| P5-03 | Two fresh durable requests, each five accepted prewritten answers and a sixth actual model response. Fixtures keep earlier rounds unresolved; sixth answer expected_revision=5 rejected 422, stale valid revision rejected 409; verify DB work/call counters unchanged by rejects/replays. No forced database edits. |
| P5-04 | Exact model digest mismatch/unavailable/identity swap, malformed and oversized native completion, context exhaustion, timeout, process death around reservation/response checkpoint/handoff and memo publication. Preserve spent calls, compatible checkpoint reuse, exactly one numerical handoff, fenced stale rejection, safe failure and usable manual numerical path. Observe upstream continuation separately; no claim from HTTP close alone. |
| P5-05 | Manual and copilot identical spec produce exact numerical values/reference projection. Hostile display metadata, ambiguous selected base/quote, non-Binance/invented/unselected IDs, alternate daily versions, quote mismatch, insufficient warm-up, unsupported markets/workflows, arbitrary sources/code and excessive cumulative context reject/clarify with zero unsafe handoff. |

Reuse verified retained BTCUSDT 2025-02-01, SOLUSDT 2025-03-01, official/canonical
SOL equivalence and overlapping BTC/SOL 2025-02-28..03-02, plus legacy BTC/ETH
January inputs/references for preservation. Verify their current bytes/catalog
identities before reuse; old pass counts are not new acceptance. Third-instrument
and second-unit fixtures must have genuine registered actual data. The bounded
proposed second-quote input is official Binance spot ETHBTC 2025-03-01, using an
operator-verified exact ETH/BTC registry mapping and checksum-verified archive;
confirm existing retained availability first. This supplies BTC quote and ETH
base units without conversion/new venue. Do not invent an alternate provider,
fabricate data or weaken the two-unit gate if that prerequisite is unavailable.
Pin concrete versions/ranges after verified ingestion and before corpus review;
missing prerequisite leaves Phase 5 incomplete. No scored dispatch until the
pinned installed model/digest/capacity and input corpus are independently ready.

## 10. Regression, operational acceptance and source qualification

Before any owned operational writes capture the exact source/files-map/dirty
overlay, dependency locks, protocol hashes, protected-file inventory and all five
original/README service/image/mount/start/restart/health/endpoint observations.
Refresh an explicit owned container/volume/network/image/process ledger; original
services are never migration/restart/probe/cleanup targets. Inspect and adapt
historical Phase 3/4 helpers: their hardcoded ownership, resource IDs and databases
are not Phase 5 authority. Do not blindly execute an old cleanup command.

Use fresh disposable PostgreSQL/Redis/application resources. Before applying the
forward migration, create checksummed DB dumps plus matching filesystem backups,
restore each to a separate owned DB/root, run fresh/populated upgrade rehearsal,
compare legacy/new row counts/constraints and protected bytes, verify representative
catalog/numerical/memo readback and record restore identity. Any restore/upgrade
failure remains retained and blocks that operation until addressed/reviewed.

Run final-source locked lint/format/mypy, full offline and real PostgreSQL suites,
frontend unit/build and Chromium/Firefox/WebKit flows, existing demo checks and
rebuilt package/no-Git HTTP/CLI checks. Add meaningful strict parser/evidence,
revision/key replay, budget/checkpoint, exact-contract compatibility, migration,
handoff races, memo grounding/read corruption, admission/priority/nonoverlap,
quota/native identity, crash/recovery and terminal immutability tests. Existing
test eligibility, limits and dependency locks stay unchanged. Verify old completed
copilot/memos without current model/source and rejection of incompatible queued
legacy/v2 work without mutation/upgrade. Shared admission requires affected legacy
actual copilot/memo regression evidence; its old fixtures and gate remain separate
from the two new mandatory cohorts.

Retain the five numerical scenarios/independent generalized Decimal oracles and
fresh unchanged legacy cold all-62 workload (230,311,900 trades, <1800s including
owned drain, one numerical attempt, legacy memo queued/zero calls unless explicitly
dispatched). Numerical/hash outputs remain exact and failure history preserved.
Earlier source-qualified unaffected gates may be reused only with an explicit
file/dependency/protocol applicability proof; altered shared numerical, source or
capacity paths require affected reruns, not generic historical pass attribution.

Record invocation ID, exact runtime/test/package overlay and lock/protocol/model
hashes, command/environment, UTC start/end and monotonic elapsed, expected/actual
counts, numerical/reference hashes, DB reservations/dispatches/checkpoints, native
responses, raw failure receipts and owned resource IDs. Use <=1s sampling of every
launched worker/owned descendants through invocation/drain, with explicit planned
sample schedule and completeness; missing required samples fail the resource gate.
Measure owned service/model process coverage when available and report excluded
processes/unknown GPU or upstream inference use truthfully. Separate functional,
lifecycle, sampled-resource and upstream-cancellation conclusions; do not claim
continuous uptime or global process/thread/resource proofs.

Owned processes use launch-time identity, held handles/private Windows Job or
equivalent bounded ownership, cooperative stop/join/drain and retained diagnostics.
No global process census, historical ancestry reconstruction or unrelated OS-thread
forensics. External model service is observed and never restarted/killed without
separate authority; lack of upstream cancellation proof is an explicit limitation.
Keep existing memory, scratch, spill, per-attempt and disk ceilings; a failed gate
cannot be repaired by increasing limits or skipping data/tests.

Before final cleanup, drain owned work, reconcile current ledgers/native ownership
and retain all failures/data/partial packages, dump every Phase 5 source DB and
export each owned authoritative volume/root. Verify checksums, restore all source
DBs/exports separately and verify numerical/memo/catalog references, revisions,
call budgets and accounting. Compare protected hashes and original services/images
to baseline before and after exact ownership-checked cleanup of only named owned
containers/volumes/network/images. Keep host data/dumps/exports/evidence. Record
cleanup inventory/actions and endpoint observation limits; point-in-time matches
are not continuous uptime. Closeout requires independent technical, acceptance,
backup/preservation/cleanup outcome review with no unresolved blocking finding.

## 11. Review checkpoint and known unverified prerequisites

This contract chooses separate versioned tables, frozen compact selected context,
strict five-answer revisions, fenced sole manual-service handoff, automatic pending
memo registration for new numerical success, explicit old-v2-run enqueue, immutable
three-claim rendering and shared root quota integration. Independent design review
passed as recorded above; this does not establish implementation acceptance.
Literal corpus/prompt/schema sizes, actual model availability,
ETHBTC/second-quote data, current retained-file integrity, owned environment/free
capacity and migration rehearsals are **not verified by writing this document**.
The parent's initial read-only preservation preflight could not connect to the
Docker Desktop Linux engine (named pipe absent); no complete protected/service
baseline receipt exists from that attempt. Original services were not started or
changed. This blocks operational prerequisites, not documentation review; record
the failure and obtain fresh actual observations before any operational claim.
No runtime edits, model calls, data downloads, tests, service changes, backups or
cleanup are claimed at this pre-code checkpoint.
