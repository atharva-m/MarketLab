# R4 deterministic research contract

Approved October 24, 2026, before implementation. The user authorized this contract,
ROADMAP.md/AGENTS.md updates, the prescribed coder/reviewer workflow, full acceptance
and honest outcome documentation. The initial request excluded commit/push; the
October 25 publication authorization below supersedes that restriction. R5–R9
remain backlog. Preserve the complete R1, R2 and R3 contracts and historical evidence.

## Input and bounds

`schema: "research-spec-v1"` is required in a strict JSON object with workflow, symbols,
dataset_versions, start, end, history_start, interval, metrics, parameters and
predicates. No unknown fields, duplicate JSON keys, boolean/number coercion,
nonfinite numbers, expressions, SQL, URLs or paths. Workflows are market_profile,
cross_asset and volatility_cluster. Profile/clusters select exactly one exact
BTCUSDT/ETHUSDT symbol; cross_asset selects both. Versions are explicit registered
64-lowercase-hex identities, exactly one per selected symbol/touched UTC day,
never latest. Symbols, versions and metrics are canonical sorted unique sets.

All timestamps are explicit UTC, five-minute aligned. History and evaluation
remain in January 2025; evaluation is [start,end), history [history_start,start).
Interval is exactly 5m. At most 62 versions and 17,856 expected input buckets
across selected symbols, 64 KiB submission JSON. Parameters are an empty strict
object in v1: numerical choices are versioned constants. Predicates are empty
for profile/cross_asset and, for clusters, the exact typed constants
`{"volatility_quantile":"0.9","volume_multiple":"2","min_bars":2}`.
Metric allowlists are profile for market_profile; profile/correlation/
close_change_difference for cross_asset; profile/clusters for volatility_cluster.
Selections contain at least one unique metric. Full
workflow results are deterministic, while the requested metrics select summary
fields. Validate shape before DB work and catalog coverage/integrity before
accepting a new run. Warm-up coverage validation occurs before durable acceptance.

Profile/cross_asset need 12 contiguous preceding bars. Clusters need 288 valid
previous volatility observations, requiring 300 preceding bars/25 hours with
complete data. Explicit longer January history may supply enough valid previous
observations around gaps. Never silently shorten evaluation or fetch more input.
Missing partitions/initial history are coverage errors. Missing buckets remain
missing; returns require adjacent closes and rolling windows contiguous inputs.
During evaluation gaps make affected statistics undefined until windows recover;
gaps break clusters. Previous 288 valid volatility values remain timestamp ordered
and may precede a gap. Report counts and actual history span. Warm-up never enters
evaluation totals, drawdown, ranks or events. No pre-January ingestion in R4.
The first evaluation return may use the final adjacent warm-up close; only returns
whose current-bar timestamp lies inside evaluation enter the reported statistics.

## Numerical definitions

Use R3 bars-v1 exactly. Derived arithmetic uses an explicit Decimal context with
80 significant digits, ROUND_HALF_EVEN, stable timestamp order and no binary float
fallback. Algorithms are research-numerics-v1. Serialize derived decimals as strings
rounded once to 18 fractional digits, negative zero normalized. Decisions use
internal unformatted values. Arithmetic errors fail; nulls carry an allowlisted
reason and observation_count, never NaN/infinity. Reasons include
insufficient_observations, missing_contiguous_history, zero_denominator and
zero_variance. Units: prices/quote volumes USDT, base volumes BTC/ETH, returns,
volatility, correlation and Sharpe dimensionless ratios, not percent-scaled.

Simple return r[t]=C[t]/C[t-1]-1; log return l[t]=ln(C[t]/C[t-1]). Volume multiple
is current base volume / mean of preceding 12 contiguous base volumes, excluding
current. Sample standard deviation divides squared deviations by n-1.

Market profile means descriptive OHLCV, not price-bin volume/TPO distribution.
Results include expected/observed/missing counts; first open/last close and their
timestamps; high/low; base/quote volume and trade counts; period quote/base VWAP;
first-to-last close change; drawdown min(C[t]/running_max_close[t]-1); valid simple
return mean/sample deviation; unannualized mean/deviation Sharpe proxy (zero
risk-free adjustment); top three eligible volume multiples, descending ratio then
earliest timestamp. Warm-up is excluded. Drawdown uses observed closes across gaps
and flags an incomplete grid; return statistics never cross gaps. One close gives
zero drawdown; fewer than two returns makes sample deviation/Sharpe undefined.
Outputs are descriptive asset statistics, never strategy performance.

Cross_asset adds per-asset profiles, common-bar/aligned-return/missing counts,
Pearson correlation of log returns at identical timestamps (each requiring an
adjacent bar in both assets), and BTC-minus-ETH first-to-last close-change using
common endpoints. Pearson uses centered sums: sum(dx*dy)/sqrt(sum(dx²)*sum(dy²)).
Fewer than two pairs or zero variance gives null. No nearest join, filling,
regression, beta, lead/lag search, cointegration or trading spread.

Cluster volatility is sample deviation of the latest 12 simple returns, requiring
13 contiguous closes. Threshold is linear-interpolated 90th percentile of previous
288 valid volatility observations excluding current: sort, h=(n-1)*0.9=258.3,
interpolate floor/ceiling zero-based indices. Qualification requires volatility
STRICTLY above threshold AND volume STRICTLY above twice preceding-12 mean.
Equality fails. Maximal runs of at least two adjacent qualifying evaluation bars
are clusters. Undefined/gap/nonqualifying bars break them. Warm-up cannot complete
a singleton. Record start/exclusive end/count, volumes, maximum volatility and
volume multiple (earliest tie), first threshold and boundary-touch flags (outside
continuation unexamined). Future bars cannot change earlier qualification.

## Durable schema and state protocol

Add migration 0005_research, altering no existing tables. Separate tables:

* research_submissions: submission_id UUID text PK, idempotency_key unique
  1..128 ASCII letters/digits/._-, request_sha256, canonical spec JSON text,
  fingerprint JSON text and fingerprint_sha256, created_at DB UTC.
* research_runs: run_id UUID text PK, unique submission FK, state
  queued/running/retry_wait/succeeded/failed, attempt_count constrained 0..3,
  fencing_token nonnegative bigint, owner/lease present iff running,
  eligible_at, safe error, created_at/updated_at DB UTC. Succeeded iff a result
  identity is present; result registration refers to this run.
* research_attempts: (run_id,attempt_number) PK, unique(run_id,fencing_token),
  owner, started/ended_at, outcome running/succeeded/transient/permanent/expired,
  safe error. Running iff ended_at absent; attempt numbers 1..3, tokens positive.
* research_results: run_id PK/FK, manifest_sha256, relative manifest_path,
  results_sha256 and summary_sha256, registered_at DB UTC. Insert/read only.

Same key/canonical request returns original run even if execution revision later
changes; conflicting reuse is 409. Fresh key creates independent run. Serialize
same-key inserts with namespaced bounded advisory lock. Fingerprint pins spec,
dataset identities and manifest hashes, numerical/workflow versions, code revision,
source fingerprint/dirty state and lock hash. Worker refuses incompatible code.
Production acceptance uses clean source or records dirty source fingerprint
honestly; do not claim dirty execution is a clean production revision.

Use clock_timestamp(), SKIP LOCKED, 60-second leases, 10-second heartbeat on a
separate connection and monotonically increasing token. Queued runs are due from
submission without a later wall-clock comparison; retry eligibility and lease
expiry use clock_timestamp() ([clock fix](r4-clock.md)). Three attempts including
crashes; expired third attempt terminally fails without fourth execution. All
mutations require current owner/token/unexpired running lease; no resurrection.
Narrow PostgreSQL/network/capacity/timeout transient failures retry after 10 then
30 seconds; validation, integrity, arithmetic/storage/unknown errors are terminal.
No source downloads or hidden retry multiplication. Shutdown stops further claims.

Stage spec.json/results.json/summary.json/manifest.json under owned .staging.
Limit each numerical results payload to 16 MiB. Hash, fully verify and flush before
publication; manifest holds lineage, versions/units/counts/coverage, provenance,
hashes/sizes. Under bounded DB transaction lock run then namespaced run advisory
lock, recheck ownership/lease and preverified immutable identity, atomic rename
to research/<run_id>, insert result and mark attempt/run success atomically.
Use 10s lock and 15s statement/idle-transaction timeouts. No full artifact reads
under transaction locks. Crash after rename/before commit leaves undiscoverable
orphan; retry fully verifies/adopts without overwrite. Corruption fails. No GC.
Registered results only; output readers verify complete artifact hashes before
serving/cache hits. Same numerical inputs/fingerprint yield equal numerical
payload hashes; operational run IDs/times/manifests may differ. Local shared
storage/cooperating writers only; no replication or power-loss guarantees.

## Interfaces, resources and cache

Add POST /v1/research/runs, GET /v1/research/runs/{run_id}, GET same /results and
/summary. POST body is the strict spec, Idempotency-Key header required. Replay
returns original identity. Invalid 422; absent 404; key/coverage/not-ready 409;
unavailable/overload 503. Safe fixed errors only. Separate research CLI supports
submit --spec FILE --key KEY, worker --max-runs 1..62 [--run ID], inspect --run ID,
results --run ID and summary --run ID; no arbitrary server URL or SQL option.

Compose existing BarService reads in chunks <=1440 buckets and <=5 touched days,
sharing the application BarService (two expensive reads/process). Do not enlarge
R3 bounds. One active run per worker; 30-minute attempt deadline with actual
cancellation/draining and heartbeat cleanup; no publication after deadline.
Bound numerical calculation to input cap and execute without blocking HTTP loop.
Coalesce identical summary reads. Reuse R3 ResponseCache: summary TTL 3240..3960s,
1 MiB envelope, 100ms command/connect, no retries, three-failure 10s breaker,
bounded metrics and validated HIT/MISS/BYPASS. Cache cannot cause run failure;
Redis/Ollama unavailability never prevents manual numerical execution/retrieval.
No model call, memo work or memo manifest in R4.

Provenance capture is lazy: existing packaged image startup/health and published
result retrieval require no Git checkout. New research executions require the
source checkout and lock file to pin revision/source fingerprint; unavailable
provenance fails safely. Deployment files remain unchanged.

## Payload shapes and local example

POST returns {run_id,replayed}, 201 new or 200 replay. Inspection returns durable
run state, attempt_count, fencing_token, ownership/lease/eligibility timestamps,
safe error, pinned spec/fingerprint and ordered attempts. Results carry schema
research-results-v1, definition research-numerics-v1, workflow/start/end/history_start,
interval/units, history by symbol and profiles by symbol; cross_asset and cluster
workflows add their named sections. Summary schema research-summary-v1 retains
definitions/units/history/period and only the selected metric sections. A scalar
statistic is {value: decimal-string-or-null, reason: reason-or-null,
observation_count: integer}. Coverage is {expected,observed,missing,incomplete_grid}.
History reports observed_bars, first_observed_start, last_observed_start,
valid_volatility_observations and threshold_history_start (earliest of up to the
last 288 pre-start valid volatility observations). Empty observed spans use null.
Cluster ineligible counts include missing evaluation buckets.

Create a strict JSON file with all required fields and explicit versions, then:

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli submit --spec request.json --key research-example
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli worker --max-runs 1 --run RUN_UUID
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli inspect --run RUN_UUID
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli summary --run RUN_UUID
```

CLI returns JSON on success, safe stderr/nonzero on operation/output failure, and
argparse exit 2 for argument syntax errors. Keys are separate from ingestion keys.

## Acceptance and preservation

Tests cover strict parsing/canonicalization/coverage/warm-up; hand-derived numerical
fixtures, ties/quantile equality/nulls; cluster boundaries/gaps/no lookahead;
chunk/input-order/restart reproducibility; real PostgreSQL migrations/preservation,
concurrent claims/submissions, lease fencing, three-crash budget and atomic
rollback/visibility; real process termination around publication and orphan
adoption; corruption, deadlines/cancellation/resource release and size limits.
Real Redis summary MISS/HIT/outage/restart/eviction/corruption/oversize and Ollama-
stopped manual paths are required. Full retained suites and focused live legacy,
ingestion and bar checks must pass in locked Python 3.13.

Actual retained-data acceptance uses all 62 registered January inputs in owned
disposable PostgreSQL. Profile each asset and cross_asset for Jan 1 01:00..Feb 1;
clusters each asset for Jan 2 01:00..Feb 1 with explicit Jan 1 history. Independently
stream/reconcile bars and every numerical result; independent repeat runs match
payload hashes. Record real counts (zero clusters valid), hashes/timings/attempts,
actual measured memory only, limitations and failures. Missing input/reconciliation
blocks acceptance. Verify all source manifests/artifacts unchanged. Preserve original
services/data; inspect ownership before cleanup. Never commit artifacts/data,
credentials, environments or weights.

Preserve R1 source/normalization/identity/publication/CLI; R2 ingestion schema,
idempotency/lease/retry/fencing/output; R3 bars/schema/bounds/cache/cancellation;
all weeks 1–9 trade/import/filter/pagination/CLI/health/metrics contracts. No
dependency/lock/deployment changes, pre-period download, strategy, copilot/memo,
UI/auth, scheduling, GC or multi-host claim. Update README/roadmap and actual
r4-verification.md; rerun formatting after final docs. Implementation uses coder
gpt-6.1-sol high, independent read-only reviewer gpt-6-astra medium, then coder
fixes and relevant rechecks. Publication follows the later authorization below.

## Local closeout

Implementation, full local acceptance, independent source review and ownership-
checked cleanup passed October 24, 2026; see [actual verification](r4-verification.md).
Final locked checks passed 655 offline/152 PostgreSQL cases. All 62 January
partitions reconciled with an independent stream; ten durable workflow runs and
fresh-key repeats matched all numerical payload hashes. Existing sources/services
were preserved. Initial failed checks, recurring DB-clock regression (not fixed),
pre/post replay-response metadata-fix source fingerprints, unmeasured peak memory
and unrun hosted CI remain explicit for that local closeout. Publication was then
excluded; no R5-R9 authorization follows.

## Publication authorization (October 25, 2026)

The user subsequently authorized committing/pushing verified R4 and the application
clock fix, then checking hosted CI. This changes publication authority only; the
numerical contract, preservation requirements and excluded scope remain intact.
Fresh verification passed 655 offline/158 real PostgreSQL tests and live
claim/retry/heartbeat/lease/fencing acceptance. The application works as intended
with the known Docker clock discrepancy; no system clock fix is claimed.

Verified implementation commit `2c0dd0b` was published to origin/main and passed
[hosted CI run 40167912094](https://github.com/atharva-m/MarketLab/actions/runs/40167912094):
655 offline tests on Ubuntu and Windows, 158 real PostgreSQL tests on Linux and
quality/build/API/optional-Redis-outage/cleanup checks. No CI fix was needed. The
exact revision and hosted/local evidence distinction are recorded in
[actual verification](r4-verification.md).
