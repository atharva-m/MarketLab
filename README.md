# MarketLab

MarketLab is a local workspace for reproducible research on January 2025 Binance Spot
BTCUSDT and ETHUSDT trades. Ingest verified data, run deterministic analyses, explore
results in your browser, and optionally use a local copilot and grounded research memos.

## Demo

![MarketLab workflow: pin January BTCUSDT dataset versions, submit a deterministic research run, execute it with a local worker, then inspect exact results, a candle chart and the generated memo](docs/assets/marketlab-demo.gif)

Recorded from the real local workspace; waits for local workers are sped up.

## What you can do

- Download official daily trade archives, verify checksums, and keep immutable dataset versions.
- Run descriptive market profiles, cross-asset comparisons, and volatility-cluster analysis.
- Inspect exact numerical results, bounded price/volume charts, and source provenance.
- Turn a natural-language request into validated research, with explicit clarification when needed.
- Generate a separate three-paragraph memo without making numerical results depend on a model.
- Inspect durable jobs and resume eligible work with bounded local workers.

Research uses explicit dataset versions, UTC dates, and history windows. The statistics
describe market data; they are not strategy returns or forecasts.

## Prerequisites

The instructions below use PowerShell on Windows.

- Python **3.13** with the `py` launcher.
- Git and Node.js **22.12 or newer**, with npm.
- Docker Desktop using Linux containers, with Docker Compose v2 and `--wait` support.
- Optional: Ollama and the pinned `qwen3.5:9b-q4_K_M` model for copilot and memo generation.

Manual research and numerical readback work without Ollama. PostgreSQL is required;
Redis is an optional cache. The quickstart starts PostgreSQL and Redis in Docker and
runs the API, browser workspace, and workers from the source checkout.

## Quickstart

### 1. Get the source and install dependencies

```powershell
git clone https://github.com/atharva-m/MarketLab.git
Set-Location MarketLab
.\scripts\bootstrap.ps1
```

The bootstrap creates `.venv`, installs uv 0.13.5, copies `.env.example` to `.env`
if needed, and installs the locked Python dependencies. It preserves an existing `.env`.

### 2. Start the database and cache

Review `.env`, then run from the repository root:

```powershell
docker compose up -d --wait postgres redis
.\.venv\Scripts\uv.exe run --locked alembic upgrade head
```

The default host connections are PostgreSQL on `127.0.0.1:5432` and Redis on
`127.0.0.1:6379`. Set `MARKETLAB_STORAGE_PATH` to the artifact directory you want
this installation to use; its default is the ignored `data/` directory.

### 3. Start the API

Keep this terminal open:

```powershell
.\.venv\Scripts\uv.exe run --locked uvicorn marketlab.app:create_app --factory --host 127.0.0.1 --port 8000 --loop asyncio:SelectorEventLoop --no-access-log
```

Keep the explicit selector event loop on Windows for psycopg compatibility.
Start this API from the Git checkout so new research can record its source identity.

### 4. Start the browser workspace

Open another terminal in the same repository root:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Open [the workspace](http://127.0.0.1:5173). The API documentation is at
[127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

An empty catalog on first launch is expected. Use ingestion below to add data.
If a port is already occupied, see the [alternate-port setup](docs/user-reference.md#alternate-ports).

## First research run

### Add a day of data

In the workspace, open **Ingestion** and select BTCUSDT with first date `2025-01-01`
and before date `2025-01-02`. Submit, then copy the submission ID.

In a terminal at the repository root, replace `SUBMISSION_UUID` and run:

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli worker --max-jobs 1 --submission SUBMISSION_UUID
```

Refresh the submission page and confirm completion. Open **Dataset catalog** and select
the resulting version. Selecting a version pins that exact dataset; catalog metadata
is distinct from a complete artifact verification.

### Submit manual research

Open **Manual research** and use:

| Field | Value |
| --- | --- |
| Workflow | Market profile |
| Asset | BTCUSDT |
| Evaluation start | `2025-01-01T01:00:00Z` |
| Evaluation end, exclusive | `2025-01-02T00:00:00Z` |
| History start | `2025-01-01T00:00:00Z` |
| Metrics | profile |
| Dataset version | The registered version selected above |

Submit and copy the run ID. Validation checks data coverage and warm-up before
returning a queued run, so a large request may take time.

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli worker --max-runs 1 --run RUN_UUID
```

Refresh the run to inspect numerical results, charts, and provenance. Exact strings
in tables and tooltips are authoritative; chart coordinates are approximate. Missing
bars remain missing, and undefined statistics show a null reason.

For a full-month or cross-asset request, first ingest and explicitly select every
required day and asset. See the [command and API reference](docs/user-reference.md).

## Copilot and memos

### Set up local inference

Install and start Ollama separately. Model installation is an explicit download:

```powershell
ollama pull qwen3.5:9b-q4_K_M
```

The application expects digest
`56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90`.
A downloaded tag must match that pin; mismatches fail safely. The application does
not pull, update, or fall back to another model automatically.

### Ask the copilot

Open **Copilot**, provide explicit dataset versions, and try:

> Compute a descriptive OHLCV market profile for BTCUSDT using five-minute bars and
> profile metrics. Evaluation starts 2025-01-01T01:00:00Z and ends, exclusively,
> 2025-01-02T00:00:00Z. History starts 2025-01-01T00:00:00Z.

Submit and copy the request ID. Run interpretation from the repository root:

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.copilot_cli worker --max-jobs 1 --request REQUEST_UUID
```

Refresh the request. Answer any clarification using the displayed revision, then run
the worker again. A submitted interpretation links to a queued numerical run; execute
that run with the research worker shown above. Model output must pass independent
validation before it can create research.

### Generate and read a memo

Successful numerical execution queues memo work separately. Run the shared inference
worker, which gives pending copilot requests priority over pending memos:

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.inference_cli worker --max-jobs 1
.\.venv\Scripts\uv.exe run --locked python -m marketlab.memo_cli inspect --run RUN_UUID
.\.venv\Scripts\uv.exe run --locked python -m marketlab.memo_cli read --run RUN_UUID --markdown
```

Each invocation processes at most the requested number of eligible jobs; invoke it
again as needed. Memos use verified summaries and remain separate from numerical
results. A pending or failed memo does not prevent reading successful research.

## Workers and saved operations

The browser submits and inspects jobs; it does not start workers. Run workers from
the same checkout and with the same database and storage settings as the API.

| Work | Command |
| --- | --- |
| Ingest selected submission | `python -m marketlab.dataset_cli worker --max-jobs 62 --submission SUBMISSION_UUID` |
| Execute selected research run | `python -m marketlab.research_cli worker --max-runs 1 --run RUN_UUID` |
| Interpret selected copilot request | `python -m marketlab.copilot_cli worker --max-jobs 1 --request REQUEST_UUID` |
| Process pending copilot/memo jobs | `python -m marketlab.inference_cli worker --max-jobs 1` |

Use the project Python through `.\.venv\Scripts\uv.exe run --locked` as in the examples.
These are finite operator commands, not a scheduler.

If a response is lost, reuse the saved operation key and exact request body.
Reloading a page does not resubmit it. Reusing a key with a changed request conflicts;
creating a new key creates a deliberate new operation. Closing the browser does not
cancel accepted durable work. See the [operating guide](docs/r9-operations.md).

## Configuration

Settings are read from `.env` in the repository root and from process environment
variables. Keep local configuration, data, and model weights out of Git.

| Setting | Purpose |
| --- | --- |
| `MARKETLAB_DATABASE_URL` | Host PostgreSQL URL, using `postgresql+psycopg://` |
| `MARKETLAB_DATABASE_PASSWORD` | Optional literal password override, avoiding URL escaping |
| `MARKETLAB_STORAGE_PATH` | Shared dataset/research artifact root |
| `MARKETLAB_REDIS_URL` | Optional Redis cache endpoint |
| `MARKETLAB_OLLAMA_URL` | Host Ollama endpoint, normally `http://127.0.0.1:11434` |
| `MARKETLAB_COPILOT_MODEL` | Shared copilot/memo model, default `qwen3.5:9b-q4_K_M` |
| `MARKETLAB_COPILOT_MODEL_DIGEST` | Expected digest for the selected model |
| `POSTGRES_PORT`, `REDIS_PORT`, `POSTGRES_PASSWORD` | Compose database/cache configuration |
| `API_PORT` | Published port when running the Compose API |
| `MARKETLAB_METRICS_PORT` | Optional per-worker exporter port; `0` disables it |

See [.env.example](.env.example) and the
[configuration reference](docs/user-reference.md#configuration-details) for passwords,
container URLs, and alternate ports.

## Health and troubleshooting

| Symptom | What to check |
| --- | --- |
| Empty catalog | Ingest data into the configured database/storage pair; a clone contains no market dataset. |
| Job stays queued | Start the appropriate bounded worker and inspect its attempt/state history. |
| Coverage or warm-up error | Select all required versions and enough preceding history; requests never silently shorten their period. |
| Copilot or memo fails | Check Ollama availability and the exact model digest. Manual research remains available. |
| Cache shows BYPASS | Redis is unavailable or the value is not cacheable; verified reads can still succeed. |
| Windows API reports an async-loop error | Keep `--loop asyncio:SelectorEventLoop` in the host API command. |
| Port already in use | Follow the alternate-port instructions rather than stopping an unrelated service. |
| Lost response or stale clarification | Reuse the saved request/key, or refresh the current revision before answering. |

Use [liveness](http://127.0.0.1:8000/health/live),
[readiness](http://127.0.0.1:8000/health/ready), and
[dependency status](http://127.0.0.1:8000/health/dependencies) to inspect the API.
Unavailable Redis or Ollama reports degraded readiness; unavailable PostgreSQL or
storage prevents readiness. API metrics are at
[127.0.0.1:8000/metrics](http://127.0.0.1:8000/metrics).
The optional [monitoring guide](monitoring/README.md) covers worker exporters and
local operational views.

Stop host processes with Ctrl+C. `docker compose down` stops this Compose stack and
preserves its persistent volumes; adding `--volumes` deletes stored contents.

## More documentation

- [Command and API reference](docs/user-reference.md)
- [Operating guide](docs/r9-operations.md)
- [Research fields and numerical definitions](docs/r4-research.md)
- [Dataset integrity and storage](docs/r1-datasets.md)
- [Build the demo locally](demo/README.md)
