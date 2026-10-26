# R7 local research workspace contract

Approved October 26, 2026 BEFORE code. The user authorized the detailed R7 plan,
ROADMAP.md/AGENTS.md updates, this full contract before implementation, prescribed
coder gpt-6.1-sol/high then independent read-only reviewer gpt-6-astra/medium,
full acceptance and honest outcome documentation. NO COMMIT/PUSH. This supersedes
historical UI/dependency exclusions only within this contract. R8/R9 remain
unauthorized. Preserve every R1-R6 contract, immutable artifact and historical
failure/limitation, including the unresolved Docker clock discrepancy.

## Product scope

Deliver a local React/TypeScript/Vite workspace for registered January 2025
Binance Spot BTCUSDT/ETHUSDT data: catalog/version selection, bounded ingestion
submission and daily job inspection, research/copilot discovery and detail,
structured research, clarification/revisions/provenance, exact numerical tables,
bounded price/volume charts and cluster events, independent memo status/content.
Use existing market_profile/cross_asset/volatility_cluster only. Browser actions
submit/inspect durable jobs; existing bounded operator-started CLI workers execute
them. No worker launch/control endpoint, daemon, scheduler or worker-presence claim.
No new analytics, sources/dates/download policy/model behavior, strategy, forecast,
authentication, public hosting, GC, dashboards or R8/R9 evaluation/demo work.

## Additive HTTP adapters

Existing HTTP/CLI/library shapes and status semantics remain unchanged. Add:

* GET /v1/datasets: catalog metadata list; filters symbol, start_date inclusive,
  before_date exclusive. Only registered published catalog rows. Items contain
  dataset_version_id, venue, symbol, trade_date, row_count, source_sha256,
  manifest_sha256, published_at and verification="registered_metadata". No paths.
* GET /v1/datasets/{version_id}: full existing inspect_version verification in a
  worker thread; returns {dataset_version_id,verification:"verified",manifest}.
  Acquire reused BarService request admission and one shared compute permit before
  full inspection; one-second capacity decision, real thread draining before
  permit release on cancellation. This route cannot add unbounded expensive work
  alongside the existing verifier/DuckDB budget. No nested pool or cache bypass.
  Missing 404; malformed 422; corrupt 422; unavailable catalog 503. A list entry
  never implies current full rehash. No filesystem discovery or orphan listing.
* POST /v1/ingestion/submissions: strict application/json <=64 KiB, exact keys
  schema="ingestion-submission-v1", symbols, start_date, before_date. Dates are
  ISO dates; symbols unique exact supported values; R2 January bounds/max 62 jobs.
  Idempotency-Key required with existing 1..128 ASCII letters/digits/._- rules.
  Call R2 submit in thread, official source mode only. Return {submission_id};
  201 for accepted/replayed requests (identity is the replay authority). Conflicting
  key 409; invalid 422; unavailable 503. Never execute ingestion in HTTP request.
* GET /v1/ingestion/submissions: paginated submission metadata, optional state
  filter matching at least one child and symbol filter matching selected symbol.
  Include submission_id, symbols array, start_date, before_date, created_at and
  counts total/succeeded/failed/queued/running/retry_wait. Only official submissions
  are browsable here; known legacy inline/fixture identity remains inspectable.
* GET /v1/ingestion/submissions/{submission_id}: existing bounded R2 inspection
  (submission/jobs/attempts/total/succeeded/failed/complete); UUID validation,
  missing 404/invalid 422/unavailable 503. Remove storage/credential internals if any;
  preserve safe operational fields and explicit partial completion.
* GET /v1/research/runs: paginated run metadata with run_id,state,attempt_count,
  created_at,updated_at,workflow,symbols,start,end; optional existing state filter.
* GET /v1/copilot/requests: paginated request metadata with request_id,revision,
  run_id,created_at,updated_at,current job state/outcome; optional state filter.

Collections return {items,next_cursor}; default limit 25, strict integer 1..100.
Reject unknown/repeated query keys, malformed filters/cursors before database
access. Dataset dates limited to Jan1..Feb1 boundaries; exact symbols only.
Other state filters use the relevant existing durable state allowlist. Sort
descending by published_at/created_at then unique identity with PostgreSQL C
collation for string ties. Keyset cursor is bounded URL-safe base64 JSON containing
schema, collection, canonical filters, UTC timestamp and unique identity; at most
2048 encoded characters; require
exact shape/type/bounds and matching filters. Limit may change between pages.
No user SQL/column/path interpolation. Queries use bound SQLAlchemy expressions,
limit+1 and bounded transaction statement/lock timeouts. Reads are current
committed, not snapshots; no total-count/performance guarantee or arbitrary scans.
No migration/index/dependency change to Python. Evidence may motivate a separate
reviewed amendment, not implicit schema expansion.

Safe fixed errors only; never SQL/credentials/source rows or absolute paths.
Full artifact reads are outside transactions and off the event loop. New dataset
detail uses existing complete verification, not a persistent trust cache. Existing
R3 two-permit verification/DuckDB budget and lifecycle remain unchanged.

## Browser runtime and trust boundary

Separate frontend/ with committed package.json/package-lock.json, exact resolved
dependencies, strict TypeScript, lint/build/component/browser commands. Frontend
dependencies and scoped CI browser jobs are authorized; Python uv.lock, deployment
Compose/Dockerfiles, inference and numerical/runtime limits remain unchanged.
Vite binds 127.0.0.1:5173 strictPort and proxies only fixed /v1 and /health prefixes
to127.0.0.1:8000 by default (test harness may choose fixed owned local ports).
No arbitrary proxy target/request URL or browser DB/model access. No wildcard CORS.
The static production build may optionally be mounted at /ui/ only when present;
SPA fallback stays in /ui/, never shadows API/docs/health/metrics or filesystem paths.
Packaged API startup remains usable without frontend assets, Git or model.

For new ingestion POST, reject nonloopback Host and Origin when supplied; Origin
must be loopback HTTP(S) and must match request host authority or the explicit
local Vite origin. Missing Origin remains usable for existing nonbrowser clients.
Vite rejects nonlocal browser Origins for proxied mutations to existing research,
copilot and memo endpoints as well. Do not alter legacy route contracts.
Serve no secrets/config; no raw HTML, eval, arbitrary links or Markdown HTML.
Render memo paragraphs, model/user text and safe diagnostics as text. Relative
application links use validated identity values. Browser cannot reset terminal
jobs, overwrite data, select model/URL, launch workers or issue arbitrary commands.

## State, replay and polling

Catalog supports explicit full version identities, including multiple versions for
one day; never latest-select or silently resolve conflicts. Selected versions
must cover history and evaluation. Structured form exposes all required R4 fields,
UTC five-minute-aligned half-open evaluation and history bounds, metric allowlists,
empty parameters and fixed cluster predicates. Browser validation assists;
server shape/catalog/integrity/warm-up validation remains authoritative.

Research submit shows validating until durable run_id arrives. Client request
deadline must accommodate existing preparation 1800s without extending backend
timeouts. Persist the operation key and exact canonical body before sending in
localStorage with at most 20 entries and 64 KiB request body per entry; reuse after lost response/reload, disable
double dispatch and never auto-retry mutation. Editing unresolved body requires
explicit discard/new operation, with warning that original may be accepted.
Fresh deliberate operation creates a new key; response identity persisted in URL.
No claim that lost connection cancels durable work. Local browser storage is
convenience, not the durable authority; shared local user profile has no auth.

Copilot distinguishes job state/outcome; submitted means research queued. Answer
sends expected_revision and dedicated replay key; stale 409 refreshes current
state without overwrite. Maximum five rounds and terminal states remain R5.
No browser reinterpretation of relative dates/metrics/evidence. Display pinned
versions, revisions, questions, safe error, attempt/call budgets and provenance.

Poll visible active detail every 2s, at most one request per resource; failures
back off up to 10s, hidden tabs pause; stop terminal or after 30min monitoring window.
Explicit resume/visibility return can start a new window. Abort on navigation;
ignore stale responses. Numerical summary/results fetched independently of memo
status and remain displayed during memo/model errors. No mutable memo status in
numerical cache. Historical enqueue is explicit empty-body existing POST; no
terminal regeneration/reset controls. Explain operator worker invocation in
queued pages without inventing availability/ETA/progress percentages.

## Exact presentation and charts

Retain decimal strings and exact integer lexemes in client data. Do not let JSON
parse irreversibly round integers above JS safe range; use an audited lossless
parser or bounded lexical preservation. Exact table/tooltips/copied values use
authoritative strings. Approximate Number conversion is permitted solely for
chart coordinates; never research arithmetic or submission identity. Display
null reason/observation_count and existing ratio/USDT/base units; null is not 0.

Price/volume chart uses GET /v1/bars only: explicit symbol, versions, UTC aligned
start/end and 1m/5m; <=1440 buckets (one day 1m/five days 5m). Explicit window navigation;
no hidden all-month fanout. Missing buckets are visibly missing, no interpolation.
Chart request uses exact touched-day version subset. Overlay existing selected
run cluster intervals only inside displayed window. No frontend recomputation of
profiles/correlation/clusters. Show descriptive-OHLCV meaning, unannualized proxy,
evaluation/history separation, coverage/empty buckets and source/numerical hashes.
Memos remain exactly three plain-text paragraphs with generated label and
descriptive limitations; do not imply unrestricted prose reasoning.

## Acceptance and evidence

Run locked Python 3.13 full Ruff lint/format/mypy/offline/real PostgreSQL suites,
fresh/populated existing migration preservation and focused live legacy HTTP/CLI,
ingestion, bars/cache, manual/copilot/memo readback. Historical819/189 is baseline,
not a new pass. Frontend npm ci/typecheck/lint/test/build; Playwright Chromium,
Firefox, WebKit plus Windows Chromium smoke. Cover keyboard/focus/labels,
responsive layout, zero unexpected console/page errors, exact values/nulls/gaps,
HTML injection, form states, API failures404/409/422/503, reload/navigation,
lost response/double-submit/key conflict and stale clarification; mocked CI is
explicitly separate from live/model acceptance. New APIs require offline shape/
bounds/error tests and actual PostgreSQL pagination/filter/idempotency/corruption/
registration-only/partial-completion cases, including pre-DB rejection.

Use owned disposable PostgreSQL/Redis/API processes and existing images/models,
no pulls or original-service restart. Snapshot original IDs/images/start/restart/
health/endpoints and all protected dataset/research/memo/config files before
acceptance. Restore trusted 62-version catalog/successful old research/memo
registrations only into owned DB, verify through normal readers. Browse all 62
partitions and all five retained monthly scenarios with memo state/content.
Fresh manual browser research must match independent retained result/summary
hashes. Fresh full 62 cross-asset process with empty application verifier/owned
Redis and no prewarm must submit+execute+readback<1800s under unchanged bounds,
actually verify 230,311,900 rows/all physical/logical/manifest hashes and retain
automatic memo enqueue. Record browser and backend elapsed separately, actual
process/readiness/drain evidence and uncontrolled OS cache. No timed warm substitute.

Exercise actual installed-model browser clear, clarification and unsupported
cases, observe validated run handoff/revision mapping and no unsafe execution.
No full new model-quality campaign unless prompts/validation/inference/grounding
change (out of intended scope; amend/retest first). Display five old scenario
memos and exercise fresh memo lifecycle without rewriting originals. Demonstrate
manual execution/readback with owned unavailable-model configuration, Redis
outage and memo failure/corruption independently of numerical availability.
Record actual model digest/settings/hardware/source/lock identities, timings,
hashes/attempts, failures and limits. Peak memory only if properly measured;
browser abort/client close is not proof of upstream active-token cancellation.

Coder implements/fixes; independent reviewer reads source/tests/evidence without
editing. Resolve actionable findings and rerun affected checks. Freeze runtime
source before actual acceptance; later source changes require relevant retesting
and honest provenance. Final protected hashes/service identity/health must match.
Ownership-check exact resources before cleanup; retain ignored reproducible
acceptance snapshots/logs. Never Git artifacts/data/archives/secrets/env/weights.
Document actual outcomes/blockers in docs/r7-verification.md, README, roadmap and
AGENTS.md. Unavailable model/data/browser leaves corresponding gate incomplete;
do not substitute mocked or old evidence or claim hosted CI without observing it.

## Preservation and authority

Preserve R1 checksums/normalization/identity/manifests/catalog publication/CLI;
R2 schemas/limits/idempotency/retries/leases/fencing/atomicity/partial completion;
R3 exact bars/bounds/cache/two shared compute permits/coalescing/draining and
corrected two-worker public-API bootstrap; R4 strict spec/Decimal80/history/hash/
manual APIs/provenance/source compatibility; R5 prompt-v3/revisions/semantic
validation/budgets/atomic handoff; R6 immutable grounded memos/unique enqueue/
priority without preemption/numerical independence. Preserve all week 1-9 trade,
import 1MiB/content-type/filter/pagination/serialization/CLI/health/metrics behavior.
New source fingerprints legitimately differ; old completed outputs stay readable
and incompatible queued work stays rejected. No clock/system/GPU/WSL/initd work.
Historical cold failures, later 266.692329s/272.814s passes, model quality/cancellation/
cache/memory limits and failed hosted runs remain explicit. Planning 55-80h is an
estimate. No commit/push or R8/R9 authority follows from this implementation approval.

## Local acceptance record (October 26, 2026)

Implementation, full local acceptance, independent source/test/evidence review
and exact owned cleanup passed. [Actual verification](r7-verification.md) records
853 offline/193 PostgreSQL cases, 18 frontend components and 33 browser cases,
the 526.987887s actual all-62 browser/API/separate-worker workflow, exact retained
numerical hashes, actual five-scenario/charts/model/memo/official-day/outage/
corruption/legacy/package checks and every failed/incomplete invocation. Windows
Firefox's default logical MSIX cache path remains affected; the later
[physical-cache invocation](r7-verification.md#windows-firefox-physical-cache-configuration-fix-october-26-2026)
passed 11/11 Windows cases with pristine binaries. The initial same-test Linux
Firefox pass remains separate. An actual
ambiguous request failed safely and is not counted as successful clarification.
No prompt/runtime limit/hash/lease/publication rule was weakened. No commit/push
or hosted R7 run occurred. Original clock/model/cancellation/memory limitations
and all historical R1-R6 evidence remain intact; R8/R9 remain unauthorized.
All 271 protected original hashes and service IDs/images/start/restart/health/
endpoints were preserved; exact owned resources and ports were cleaned.
