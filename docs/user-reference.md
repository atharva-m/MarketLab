# Command and API reference

Run commands from the repository root with the locked environment. The examples use
PowerShell; replace uppercase identity placeholders with values returned by the application.

## Historical data

Supported input is official Binance Spot BTCUSDT/ETHUSDT daily trades from
`2025-01-01` through `2025-01-31`. Date ranges use an inclusive first date and an
exclusive before date. A full month across both assets contains 62 daily jobs.

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli submit --symbols BTCUSDT ETHUSDT --from-date 2025-01-01 --before-date 2025-02-01 --key january-2025
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli worker --max-jobs 62 --submission SUBMISSION_UUID --wait-seconds 60
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli jobs --submission SUBMISSION_UUID
```

For synchronous one-day ingestion and complete registered-artifact inspection:

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli ingest --symbol BTCUSDT --date 2025-01-01
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli inspect --version DATASET_VERSION_ID
```

Archives are checksum-verified before parsing. Normalized decimal values and UTC
microseconds are preserved. Identical verified source/transform identity reuses a
version; changed source bytes create a new immutable version. Only registered
versions are discoverable. Fresh submission keys recheck sources, while replaying
the same key and request returns the original jobs. Partial completion stays explicit.
Limits are 512 MiB compressed, 4 GiB expanded, and 20 million rows per archive.

## Manual research

Save an explicit specification as `request.json`. Replace the version placeholder
with the registered BTCUSDT version for January 1:

```json
{
  "schema": "research-spec-v1",
  "workflow": "market_profile",
  "symbols": ["BTCUSDT"],
  "dataset_versions": ["REPLACE_WITH_64_CHARACTER_DATASET_VERSION"],
  "start": "2025-01-01T01:00:00Z",
  "end": "2025-01-02T00:00:00Z",
  "history_start": "2025-01-01T00:00:00Z",
  "interval": "5m",
  "metrics": ["profile"],
  "parameters": {},
  "predicates": {}
}
```

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli submit --spec request.json --key my-research
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli worker --max-runs 1 --run RUN_UUID
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli inspect --run RUN_UUID
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli results --run RUN_UUID
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli summary --run RUN_UUID
```

Market profiles and cross-asset comparisons require 12 preceding five-minute bars.
Clusters require 288 preceding valid volatility observations, or 300 bars/25 hours
with complete data. Missing bars affect coverage and break clusters. The application
never downloads earlier history or silently shortens the requested period.

Use `cross_asset` for both assets with metrics `profile`, `correlation` and
`close_change_difference`. Use `volatility_cluster` with `profile` and `clusters`,
and the fixed predicates
`{"volatility_quantile":"0.9","volume_multiple":"2","min_bars":2}`.
The [research specification](r4-research.md) defines exact fields, units, null reasons,
warm-up and numerical calculations.

## Copilot requests and clarification

Save `copilot.json` with an explicit selection and request:

```json
{
  "schema": "copilot-request-v1",
  "text": "Run a descriptive OHLCV market profile for BTCUSDT using 5m bars and profile metrics. Evaluation starts 2025-01-01T01:00:00Z and ends exclusively 2025-01-02T00:00:00Z. History starts 2025-01-01T00:00:00Z.",
  "dataset_versions": ["REPLACE_WITH_64_CHARACTER_DATASET_VERSION"],
  "context": {}
}
```

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.copilot_cli create --request copilot.json --key my-copilot
.\.venv\Scripts\uv.exe run --locked python -m marketlab.copilot_cli worker --max-jobs 1 --request REQUEST_UUID
.\.venv\Scripts\uv.exe run --locked python -m marketlab.copilot_cli inspect --request REQUEST_UUID
```

A successful interpretation returns a research run ID; execute it with the research
worker. A request needing clarification has no numerical run yet. Save an answer in
`answer.json`, using the current revision:

```json
{
  "schema": "copilot-answer-v1",
  "expected_revision": 0,
  "text": "Use this explicit history start.",
  "context": {"history_start": "2025-01-01T00:00:00Z"}
}
```

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.copilot_cli answer --request REQUEST_UUID --answer answer.json --key ANSWER_KEY
.\.venv\Scripts\uv.exe run --locked python -m marketlab.copilot_cli worker --max-jobs 1 --request REQUEST_UUID
```

There are at most five answer rounds. Dataset selection stays fixed across answers;
create a new request to replace or add versions. Stale revisions and conflicting
key reuse are rejected. Terminal failed/unsupported requests are not reset.

The model receives no database credentials or tools. Bodies are bounded to 64 KiB,
text to 8 KiB and selections to 62 versions; the combined prompt/schema/input budget
is 6,000 UTF-8 bytes. Copilot inference uses an 8,192-token context, a 120-second
deadline and a 32 KiB response bound. Requests outside recognized explicit language
may require structured clarification or fail safely.

## Memos

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.inference_cli worker --max-jobs 1
.\.venv\Scripts\uv.exe run --locked python -m marketlab.memo_cli inspect --run RUN_UUID
.\.venv\Scripts\uv.exe run --locked python -m marketlab.memo_cli read --run RUN_UUID --markdown
```

For an older completed run without a memo job, `memo_cli enqueue --run RUN_UUID`
idempotently ensures work exists. Terminal failed jobs cannot be reset, and ready
memos are never overwritten. Each memo is a separate immutable Markdown supplement
with its own manifest and summary lineage. It contains three plain-text paragraphs
covering scope, descriptive findings and limitations. Memo generation retains a
2,048-token output budget. Failed supplements leave numerical reads usable.

## HTTP endpoints

Open the running API's [interactive documentation](http://127.0.0.1:8000/docs)
for schemas and responses.

| Task | Route |
| --- | --- |
| Browse / fully inspect datasets | `GET /v1/datasets`, `GET /v1/datasets/{version_id}` |
| Submit / inspect ingestion | `POST /v1/ingestion/submissions`, `GET /v1/ingestion/submissions/{submission_id}` |
| Submit / inspect research | `POST /v1/research/runs`, `GET /v1/research/runs/{run_id}` |
| Numerical results / summary | `GET /v1/research/runs/{run_id}/results`, `GET /v1/research/runs/{run_id}/summary` |
| Copilot / clarification | `POST /v1/copilot/requests`, `GET /v1/copilot/requests/{request_id}`, `POST /v1/copilot/requests/{request_id}/clarifications` |
| Read / enqueue memo | `GET` / `POST /v1/research/runs/{run_id}/memo` |
| Bounded bars | `GET /v1/bars` |

Ingestion, research and copilot submissions, including clarification answers, use
JSON and an `Idempotency-Key` header. Memo enqueue uses an empty body, needs no
idempotency header, and is identified by the run ID. Responses distinguish queued
work from finished execution.

Bars require one exact version per touched day, one asset, aligned UTC boundaries
and `1m` or `5m` intervals. Requests allow at most 1,440 buckets and five daily
partitions. Repeat the `version` query parameter for cross-day windows. OHLCV values
are exact decimal strings; missing buckets stay absent. See the
[bar API specification](r3-analytics.md).

Redis cache outcomes are `HIT`, `MISS` or `BYPASS`. Bars expire after 15 minutes
and numerical summaries after one hour, with ±10% jitter and a 1 MiB entry cap.
Redis commands have 100 ms deadlines and no automatic retries; three failures trigger
ten seconds of bypass. At most two expensive analytical operations run per process.
Memory settings are resource controls, not measured application peak memory.

## Synthetic trade imports and browsing

The separate synthetic trade API accepts atomic JSON/CSV imports up to 1 MiB.
`POST /trades/import/json` requires `application/json`; `POST /trades/import/csv`
requires `text/csv`. Success returns `{"imported":N}`. Exact-ID reads use
`GET /trades/{trade_id}`.

`GET /trades` returns `{"items":[...],"next_after_id":...}` in case-sensitive ID
order, with an exclusive `after_id` boundary. Page size defaults to 100 and is
bounded to 1–500. Exact `symbol` and inclusive `executed_from` / exclusive
`executed_before` filters apply before pagination. Pages read current committed
data without a shared snapshot.

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.trade_cli --symbol SYN.A --limit 25
.\.venv\Scripts\uv.exe run --locked python -m marketlab.trade_cli --port 8000 --symbol SYN.A --executed-from '2025-01-01T00:00:00Z' --executed-before '2025-02-01T00:00:00Z' --max-pages 4
.\.venv\Scripts\uv.exe run --locked python -m marketlab.trade_cli --trade-id SYN-001
```

The trade client defaults to loopback port 8000 and does not read `.env`.
It prints one JSON page per line and retains filters across bounded traversal.
Resume using the final `next_after_id` as `--after-id`. A later failure can leave
partial output, so inspect the exit status. Exact lookup accepts `--port` but
rejects browsing options. Missing IDs and request failures produce nonzero exit
status, safe stderr and no lookup stdout.

## Alternate ports

For the host API, pass `--port 58007` instead of 8000. In the frontend terminal,
set the fixed proxy override before starting Vite:

```powershell
$env:MARKETLAB_R7_TEST_API_PORT = '58007'
npm run dev
```

The current proxy accepts only 8000 or this explicit 58007 override. Vite binds
to `127.0.0.1:5173` with a strict port; free that port within your own installation
or choose a separate local session rather than stopping an unrelated process.
The override's environment name is retained for compatibility.

For database/cache port conflicts, set `POSTGRES_PORT` / `REDIS_PORT` in `.env`
and update `MARKETLAB_DATABASE_URL` / `MARKETLAB_REDIS_URL` to match.
Changing `API_PORT` affects the Compose API's host publication, not a host Uvicorn
process or Vite's fixed proxy target.

## Configuration details

`MARKETLAB_DATABASE_PASSWORD` overrides the password in the database URL as a
literal value. Otherwise URL-encode special password characters in the URL.
`POSTGRES_PASSWORD` initializes a newly created PostgreSQL volume; editing it does
not change credentials already stored in an existing database.

Host tools use `127.0.0.1` endpoints. Containers use service names for PostgreSQL
and Redis and `http://host.docker.internal:11434` for host Ollama, controlled by
`OLLAMA_HOST_URL`. Keep API and workers on the same database, storage root and source
checkout; a container volume is not automatically the host `data/` directory.
Packaged startup/readback is available without Git, while new research executions
need checkout source provenance.

Model overrides must specify both `MARKETLAB_COPILOT_MODEL` and its matching
`MARKETLAB_COPILOT_MODEL_DIGEST`. The compatibility smoke command has an older
default, so pass the intended model explicitly if using it:

```powershell
.\.venv\Scripts\uv.exe run --locked python scripts/ollama_smoke.py --model qwen3.5:9b-q4_K_M --output artifacts/ollama-smoke.json
```

For separate worker telemetry, set an unused `MARKETLAB_METRICS_PORT` in that
worker's terminal; default `0` disables it. Run the read-only durable collector
with `python -m marketlab.monitoring --port 59109`. API and worker registries are
separate; a finite worker's exporter disappears when it exits.

Library callers should reuse one `BarService` per process/event loop, close
research services before the bar service, and await shutdown. Scripts that spawn
verifier children must guard their entry point with `if __name__ == "__main__":`.

## Development commands

```powershell
.\scripts\check.ps1
Set-Location frontend
npm run typecheck
npm run lint
npm test
npm run build
```

Database tests require an explicitly configured disposable migrated database.
See the [operations guide](r9-operations.md) for job recovery and monitoring.
