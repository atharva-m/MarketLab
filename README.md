# MarketLab

MarketLab is a local research workspace for Binance spot trade data. It turns official
daily trade archives into verified, immutable dataset versions and runs deterministic
research over the versions you pin: market profiles, cross-asset comparisons and
volatility clusters on five-minute bars.

Every figure on screen is exact and reproducible from its pinned inputs. A local language
model can interpret a research request or write a separate memo, but it never produces or
changes a numerical result. Everything runs on your own machine.

![MarketLab workspace: pin BTC/USDT dataset versions in the catalog and submit a research run; a worker on a remote host claims it and is killed, its lease expires and a worker on another machine finishes the run; inspect the attempt history, exact results and a price chart, read the generated memo, ask the local copilot, which requests one clarification before queueing the same run, then view the worker inventory across both hosts](docs/assets/marketlab-workspace-demo.gif)

Recorded from the real workspace with workers on two hosts, one local and one in the
cloud, on different operating systems and sharing object storage. Waits are sped up or
cut.

## What you can do

- Ingest official Binance daily trade archives, or import your own Binance trade files as
  CSV or Parquet, with checksums verified before anything is published.
- Browse the catalog and pin the exact dataset versions a piece of research may use.
- Run market profiles, cross-asset comparisons and volatility-cluster analysis.
- Read exact numerical results, price charts and full provenance for every run.
- Describe a run to the local copilot. It asks when something is missing and queues
  research only after the request validates.
- Read a three-paragraph memo generated from a run's verified summary.
- See which worker and host ran each attempt, including retries that moved to another host.

The statistics describe market data. They are not strategy returns, forecasts or advice.

## Requirements

The commands below use PowerShell on Windows.

- Python **3.13** with the `py` launcher
- Git, and Node.js **22.12 or newer** with npm
- Docker Desktop using Linux containers, with Docker Compose v2
- Optional: [Ollama](https://ollama.com) with the `qwen3.5:9b-q4_K_M` model, for the
  copilot and memos

Research, results and charts work without Ollama. PostgreSQL is required and Redis is an
optional cache; the setup below runs both in Docker and runs the API, the browser
workspace and the workers from the source checkout.

## Setup

### 1. Get the source and install dependencies

```powershell
git clone https://github.com/atharva-m/MarketLab.git
Set-Location MarketLab
.\scripts\bootstrap.ps1
```

The bootstrap creates `.venv`, installs the locked Python dependencies and copies
`.env.example` to `.env` if you do not have one.

### 2. Start the database and prepare storage

Review `.env`, then run from the repository root:

```powershell
docker compose up -d --wait postgres redis
.\.venv\Scripts\uv.exe run --locked alembic upgrade head
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli v2 capacity-initialize
```

Datasets and results are stored under `MARKETLAB_STORAGE_PATH`, which defaults to the
ignored `data/` directory.

### 3. Start the API

Keep this terminal open:

```powershell
.\.venv\Scripts\uv.exe run --locked uvicorn marketlab.app:create_app --factory --host 127.0.0.1 --port 8000 --loop asyncio:SelectorEventLoop --no-access-log
```

### 4. Start the workspace

In a second terminal at the repository root:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Open [127.0.0.1:5173](http://127.0.0.1:5173). The catalog is empty on first launch.
If a port is already in use, see [alternate ports](docs/user-reference.md#alternate-ports).

### 5. Optional: set up the local model

Install and start Ollama, then download the model:

```powershell
ollama pull qwen3.5:9b-q4_K_M
```

MarketLab checks the model against a pinned digest and never downloads, updates or
substitutes a model on its own.

## Using the workspace

Open **Workspace** in the sidebar. Its tabs are Catalog, Research, Copilot, Ingestion,
Import, Instruments and Workers.

The workspace submits and tracks work; it does not run it. Each queued item shows the
worker command to run in a terminal at the repository root. The commands below use the
project environment, for example
`.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli v2 worker ...`.

### 1. Add data

BTC/USDT and ETH/USDT are registered out of the box. Add other Binance spot pairs under
**Instruments**.

Open **Ingestion**, pick one or two instruments and a date range of days that have
already ended (UTC), confirm and choose **Start ingestion**. Then run the worker shown on
the page:

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli v2 worker --max-jobs 1 --submission SUBMISSION_UUID
```

Raise `--max-jobs` to process more daily jobs in one invocation. To bring in your own
Binance trade file instead, use **Import**; its **File format** panel lists the required
columns.

### 2. Pin versions

Open **Catalog**, filter by instrument or date, and tick the daily versions to use.
Include enough earlier data for warm-up: 12 five-minute bars for profiles and
comparisons, 300 for volatility clusters. Choose **Run research**.

### 3. Run research

On **New research**, choose the workflow and instruments and enter the window in UTC on
five-minute boundaries, for example:

| Field | Value |
| --- | --- |
| History start | `2025-01-29T00:00:00Z` |
| Evaluation start | `2025-01-29T01:00:00Z` |
| Evaluation end | `2025-02-01T00:00:00Z` |

The evaluation end is exclusive. Confirm and choose **Run research**, then run the
worker shown on the run page:

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.research_cli v2 worker --max-runs 1 --run RUN_UUID
```

### 4. Read results

The run page shows the summary figures, the full results, a price chart for any window
inside the run (up to 1,440 bars across 5 days) and the pinned versions and provenance
behind them. Values in tables are exact; only chart coordinates are approximate. Missing
bars stay missing, and an undefined statistic shows `null` with its reason.

### 5. Read the memo

A finished run queues a memo. Run the memo worker and it appears on the run page:

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.memo_cli v2 worker --max-jobs 1 --run RUN_UUID
```

A pending or failed memo never blocks reading the numerical results.

### 6. Ask the copilot

Pin versions, open **Copilot** and describe one run. Being explicit works best:

> descriptive OHLCV market profile for BTCUSDT; history_start 2025-01-29T00:00:00Z;
> start 2025-01-29T01:00:00Z; exclusive end 2025-02-01T00:00:00Z; 5m; metrics profile.

Choose **Ask copilot**, then run its worker:

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.copilot_cli v2 worker --max-jobs 1 --request REQUEST_UUID
```

If something is missing, the request page asks a question. Answer it and run the worker
again. Once the request validates, **Open run** takes you to a queued run, which you
execute with the research worker as in step 3. Copilot work is served before memos, so
finish an open copilot request before expecting a memo.

### 7. See who ran it

Every run, ingestion job, copilot revision and memo has an **Execution** table listing its
attempts in order: host, worker, start time, duration and outcome. If a lease expires and
another worker takes over, the table says so. The **Workers** tab lists the registered
workers with their host, state, last heartbeat and the jobs they currently hold.

Hosts and workers are recorded when workers run on several hosts. On a single-machine
setup the Workers tab is empty and attempts show no host.

### Other pages

**Datasets**, **Ingestion**, **Jobs**, **Research** and **Copilot** in the sidebar are a
focused view of January 2025 BTC/USDT and ETH/USDT, with a day-by-day activity matrix for
pinning. They use their own worker commands, shown on each queued item and listed in the
[command reference](docs/user-reference.md).

## Configuration

Settings are read from `.env` in the repository root and from process environment
variables, which take precedence. Keep configuration, credentials, data and model
weights out of Git.

| Setting | Purpose |
| --- | --- |
| `MARKETLAB_DATABASE_URL` | PostgreSQL URL, using `postgresql+psycopg://` |
| `MARKETLAB_DATABASE_PASSWORD` | Optional password override, avoiding URL escaping |
| `MARKETLAB_STORAGE_PATH` | Root directory for datasets and results |
| `MARKETLAB_STORAGE_BACKEND` | Where artifacts are written: `local` (default) or `s3` |
| `MARKETLAB_REDIS_URL` | Optional Redis cache |
| `MARKETLAB_OLLAMA_URL` | Ollama endpoint, normally `http://127.0.0.1:11434` |
| `MARKETLAB_COPILOT_MODEL` | Copilot and memo model, default `qwen3.5:9b-q4_K_M` |
| `MARKETLAB_COPILOT_MODEL_DIGEST` | Expected digest for that model |
| `MARKETLAB_WORKER_ROOT_ID` | Root UUID of this host when workers run on several hosts |
| `MARKETLAB_METRICS_PORT` | Optional per-worker metrics port; `0` disables it |
| `POSTGRES_PORT`, `REDIS_PORT`, `POSTGRES_PASSWORD`, `API_PORT` | Docker Compose settings |

Run the API and every worker from the same checkout with the same database and storage
settings. See [.env.example](.env.example) and the
[configuration reference](docs/user-reference.md#configuration-details).

### Store artifacts in your own S3 bucket

Local storage is the default and needs no cloud account. To use S3, set these in `.env`
before running `capacity-initialize`:

```dotenv
MARKETLAB_STORAGE_BACKEND=s3
S3_BUCKET_NAME=
AWS_REGION=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
# AWS_SESSION_TOKEN=
# MARKETLAB_STORAGE_S3_PREFIX=marketlab
```

Use an existing private bucket with versioning enabled and a dedicated prefix. Set
`MARKETLAB_STORAGE_S3_ENDPOINT` for an S3-compatible service. Workers still use local
scratch space. See [storage setup and permissions](docs/v2/phase-6-operations.md), and
[running workers on a second host](docs/v2/phase-7-operations.md#explicit-configuration-and-identities).

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Empty catalog | Ingest or import data first; a fresh clone contains no market data. |
| Job stays queued | Run the worker command shown on the page. |
| Coverage or warm-up error | Pin every required day and enough earlier history. A request is never shortened silently. |
| Copilot or memo fails | Check that Ollama is running and the model digest matches. Research itself does not need the model. |
| Memo stays queued | Finish any open copilot request first; copilot work is served before memos. |
| API reports an async-loop error on Windows | Keep `--loop asyncio:SelectorEventLoop` in the API command. |
| Port already in use | Follow [alternate ports](docs/user-reference.md#alternate-ports). |
| A response was lost | Retry from the same page. The saved request is resent with the same key, so it cannot be applied twice. |

The API reports [liveness](http://127.0.0.1:8000/health/live),
[readiness](http://127.0.0.1:8000/health/ready) and
[dependency status](http://127.0.0.1:8000/health/dependencies). Its interactive
documentation is at [127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) and its metrics at
[127.0.0.1:8000/metrics](http://127.0.0.1:8000/metrics). The
[monitoring guide](monitoring/README.md) covers worker metrics and dashboards.

Stop the API and workspace with Ctrl+C. `docker compose down` stops the database and
cache and keeps their data; adding `--volumes` deletes it.

## More documentation

- [Command and API reference](docs/user-reference.md)
- [Operating guide](docs/r9-operations.md)
- [Research fields and numerical definitions](docs/r4-research.md)
- [Dataset integrity and storage](docs/r1-datasets.md)
- [Recording the demo](demo/README.md)
