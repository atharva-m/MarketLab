# Binance spot v2 numerical research

Phase 3 implements explicit pinned-selection bars and numerical research. Final
local runtime gates, eight database backup/restores, exact owned cleanup and
final preservation passed. Independent closeout review passed with no unresolved
blocking finding; Phase 3 is locally complete. Actual outcomes remain in
[verification](phase-3-verification.md). The browser,
discovery/uploads, copilot and generalized memo interfaces retain their earlier
scope until their respective phases. Numerical research requires no model.

## Setup and selection

Use locked Python 3.13 and an isolated database/storage root with verified backup.
Rehearse migration `0009_v2_research` on fresh/populated copies and verify restore
before `alembic upgrade head` in that owned environment. The migration is forward
only; do not apply it to the original services under this milestone.

Use the [Phase 2 CLI](phase-2-usage.md) to list instruments, dataset alternatives
and coverage. Pin one registered version per instrument/day, including history.
Missing daily partitions, alternative same-day selections, identity conflicts and
insufficient actual warm-up fail explicitly. Disabling an instrument prevents new
imports while retained numerical reads remain supported. No latest-version
selection or automatic missing-data download occurs.

## Create and execute research

The complete request for a verified SOL day has this shape; replace the placeholder
with its actual registered version. All fields are required.

```json
{"schema":"research-spec-v2","workflow":"market_profile","instrument_ids":["binance:spot:SOLUSDT"],"dataset_versions":["<registered 64-hex version>"],"history_start":"2025-03-01T00:00:00Z","start":"2025-03-01T01:00:00Z","end":"2025-03-02T00:00:00Z","interval":"5m","metrics":["profile"],"parameters":{},"predicates":{}}
```

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli v2 submit --spec research.json --key sol-profile
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli v2 worker --max-runs 1 --run <run-id>
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli v2 inspect --run <run-id>
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli v2 results --run <run-id>
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli v2 summary --run <run-id>
```

Creation returns id/state/replayed. Same key and canonical request replays the
original run and captured provenance; conflicting reuse fails. A fresh key creates
new work. Workers claim only the exact supported source/lock/protocol identity;
incompatible queued work remains inspectable without spending attempts. Terminal
runs are immutable. Exit 0 from a worker reports the bounded invocation completed;
inspect the run to establish actual numerical success.

For `cross_asset`, select exactly two instruments with the same exact quote asset,
all their touched daily versions and approved metrics profile/correlation/
close_change_difference. Comparison order is the sorted qualified instrument
order recorded in results. USD and USDT are different quotes. No conversion or
filling of missing buckets occurs.

For `volatility_cluster`, select one instrument, metrics profile and/or clusters,
and exact predicates `{"volatility_quantile":"0.9","volume_multiple":"2","min_bars":2}`.
Provide at least 300 preceding five-minute bars and enough actual valid history;
one daily partition alone cannot supply that warm-up. Profile/comparison require
12 actual contiguous preceding bars. Evaluation is `[start,end)` and history is
`[history_start,start)`; warm-up is excluded from reported totals.

## Bars and cancellation

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli v2 bars --instrument binance:spot:SOLUSDT --version <version> --interval 5m --start 2025-03-01T00:00:00Z --end 2025-03-02T00:00:00Z
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli v2 cancel --run <run-id> --expected-revision <current-revision> --key cancel-sol
```

Use the revision returned by inspect. Cancellation and publication serialize:
accepted cancellation prevents subsequent success; committed success conflicts.
Exact operation replay returns its original outcome. SIGINT/SIGTERM stop further
worker claims and allow current work to drain. Forced process death recovers by
native lease expiry within the three-attempt budget.

The equivalent local HTTP surface is GET `/v2/bars` (instrument_id, repeated
version, interval, start/end), POST `/v2/research/runs` with JSON and Idempotency-Key,
GET run/status/results/summary, and POST run/cancel with expected_revision and an
operation key. Existing local origin protection applies to mutations. Errors use
fixed codes and request IDs; there are no public discovery/upload/model endpoints
in this phase.

## Limits and readback

Research has at most 62 versions and 17,856 expected five-minute buckets across
instruments including history. Charts have at most 1,440 buckets/five partitions
and support 1m/5m. Selection scratch is 20 GiB, query spill 2 GiB, and output/control
reservation 34 MiB; actual physical admission shares conservative charges with
ingestion. Each result/summary is at most 16 MiB and an attempt at most 1,800s.
Failed/crashed leftovers retain charges until explicit ownership-checked cleanup;
there is no automatic GC.

Outputs pin dataset/manifest identities, instrument metadata/units and exact
execution provenance. All registered artifacts are verified before readback or
cache hits. Redis is optional; outage does not alter numerical truth. V2 results
do not enqueue memos. Historical legacy numerical/memo readers remain available
under their own contracts. Caller-supplied import provenance remains an origin
declaration, not independent proof of Binance authenticity.

V2 packaged execution requires readable bundled Python source files and uv.lock
to compute its exact compatibility identity. Git metadata is captured when
available; absent Git/checkout records explicit unavailable provenance and null
revision/dirty fields. It does not fabricate a clean build. Missing source/lock
fails safely; historical completed reads remain independent of current source
and Git availability. Legacy execution retains its own provenance contract.
