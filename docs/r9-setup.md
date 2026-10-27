# Reproduce a local MarketLab checkout

Use Python 3.13, Git, uv 0.13.5, Node/npm compatible with the committed frontend
lock, and a working local Docker engine. Record their actual versions. A fresh
checkout on an existing workstation does not prove first-time machine setup.
Ollama and the exact approved 9B weights are needed for copilot/memos, while
numerical research remains usable without inference. No automatic model pull or
account connection is part of application startup.

## Install source and locked environments

Clone the published repository and check out an explicit revision. For unpublished
R9 verification, `scripts/r9_handoff.py clone --prefix r9-clone-first` creates a
local Git clone plus an audited source overlay. Its manifest distinguishes the
published base from uncommitted R9 changes. It does not copy a virtual environment,
frontend installation, data, secrets or generated outputs. Keep the source overlay
manifest with the run evidence.

The checkout is placed at the short owned path `artifacts/c/<invocation hash>`
and recorded in the invocation receipt. Within it, prefer `artifacts/r9-20261027/s`
for retained storage. This preserves Windows path budget for the immutable
version/venue/symbol/date hierarchy without changing system long-path settings.
All invocation evidence remains under the checkout's R9 evidence root. Prior
longer failed checkouts and partial copy evidence remain separately retained.

From the fresh checkout, install using a separately available uv executable:

```powershell
uv sync --locked
Set-Location frontend
npm ci
Set-Location ..
```

Do not regenerate the locks to make installation succeed. Record download/cache
provenance; a shared package download cache does not mean an installed environment
was copied. Install browser binaries for the locked Playwright version as a
separate prerequisite. On this Windows installation, inspect the documented
[Firefox physical-cache evidence](r7-verification.md#windows-firefox-physical-cache-configuration-fix-october-26-2026)
before choosing a process-only browser-cache override. Do not change system or
persistent environment settings to hide a startup failure.

## Configure owned services

Use an isolated migrated PostgreSQL database, optional owned Redis, local artifact
root and optional separately owned model endpoint. Do not reuse original services
for acceptance. Pass configuration only to the relevant process; keep connection
details out of source, commands recorded in public logs, browser assets and Git.

Apply the existing migrations, then start the API and UI using the commands in
[README](../README.md). Use the dedicated local API port 58007 when the original
8000 service remains in use. The Vite proxy supports that fixed test port through
`MARKETLAB_R7_TEST_API_PORT=58007`. A blank migrated database should have an empty
catalog; it does not automatically import ignored acceptance snapshots.

The R9 tools expect these private files under `artifacts/r9-20261027`:

- `connection-private.json`: exact owner `r9-20261027`, `database_url` on
  127.0.0.1:55445/database marketlab, `redis_url` on 127.0.0.1:56387/0,
  `ollama_url` on 127.0.0.1:11444 and absolute `storage_path` inside that evidence root.
- `owned-postgres.json` and `owned-redis.json`: recorded Docker inspect objects;
  actual IDs/images/names, `marketlab.r9.owner` labels and loopback bindings are
  checked before using the connections.
- `retained-inputs.json`: schema `r9-retained-inputs-v1`, with a `files` object
  mapping `catalog`, `references`, `research_snapshot`, and optionally
  `memo_snapshot`/`scenarios`/`old_execution`/`native_reference`, to objects
  containing `path` and exact `sha256`.
  Memo readback requires both optional inputs. These are external evidence,
  separately inventoried and never part of the source overlay.

Provisioning is owned by the root orchestrator. The explicit failure-isolation
phase cycles the inventoried Redis container, and packaged smoke creates/removes
its separately labeled image/container. Original/protected baseline snapshots are
an orchestration prerequisite, not something inferred from these connection files.

## Clean start and retained evidence

`path-a` requires an empty owned catalog and a new `path-a-storage` directory. It
submits official BTCUSDT January 1, 2025 ingestion through the normal CLI, executes
one bounded worker, reads the registered version, replays the original key and
performs a fresh-key source recheck. It requires one published same-source version.
It downloads the official day twice; it does not download the full month.

Before Path B, retain a dump of the owned Path A database. Preserve that completed
history in a separately named owned database (for example `marketlab_path_a`) and
create a new empty owned `marketlab` database. Record exact resource ownership and
database identities first. Do not reset Path A jobs or overwrite its registrations:
the same immutable dataset ID can have a different catalog publication timestamp
from the older retained catalog. Path B imports into its fresh database.

`copy-retained --source PATH` copies only dataset/research artifacts into an absent
owned storage root, hashing both sides and checking unchanged originals. The
complete file/path preflight runs before creating the destination or copying files;
on Windows, any destination at or above 260 characters refuses the copy.
The
`cold` phase registers verified retained manifests without prewarming content,
then reuses the existing all-62 verifier assertions under a fresh service/process.
`research` restores completed old R4 registrations, reads all retained scenarios
against independent references and executes one fresh scenario per workflow.
`retained-memos` restores selected completed R6 history and reads five scenario
memos/numerical outputs through normal service readers.

`failure-isolation` stops and restarts only the previously verified owned Redis
container, exercises actual cache BYPASS while stopped, then performs an unavailable
model memo attempt against loopback port 1 and verifies numerical results remain
unchanged. Coordinate this lifecycle with the root resource owner; do not run any
other acceptance operation concurrently. `observe` reads fixed API 58007,
collector 59119 and separate worker 59120 endpoints while those owned processes
are active. It observes existing exporters and does not launch them.

`source-compatibility` runs the existing four persisted-old-source tests with a
generated harness that changes evidence locations and receipt prefix, and imports
the original dataset fixture into the generated module's scope outside `tests/`. The
old identity file remains byte-identical and hash-pinned; no runtime identity,
model response or retry timestamp is forced. It requires `old_execution` input.
`packaged-linux` reuses the existing no-network local-image native verifier smoke,
including strict hash/bar/drain assertions and exact labeled container/image
cleanup. It requires the smallest retained day's `native_reference` input.
`scripts/r9_legacy.py --prefix r9-legacy-first` exercises the actual guarded API's
synthetic JSON/CSV import, transactional rollback, bounds, exact-case pagination,
time filters and CLI readback without using original services.

Full checks use short, invocation-specific temporary directories under
`artifacts/t` to keep Windows native test marker paths below classic path limits.
The parent directory is created first; pytest creates the fresh per-run directory.
An existing per-run directory is refused rather than deleting earlier evidence.
Command labels such as `test:e2e` retain their original metadata but use safe log
filenames such as `test-e2e.log`, avoiding NTFS alternate streams.

## Actual browser gates and capture

After recording the owned API/UI PID, birth, executable, source command and
listener manifests, run `node scripts/r9_browser.mjs INPUT.json`. INPUT.json
must live under the checkout's R9 evidence root and contain a fresh `prefix`.
The helper uses the locked frontend Playwright runtime, real local API routes,
1920×1080 capture, exclusive output receipts and loopback-only browser routing.
It refuses unexpected console/page errors and retains cleanup failures.

Use mode `empty` before ingestion to verify the actual empty catalog and visible
empty message. Mode `manual` takes a full explicit `spec` from a known independent
reference, fills the real form, checks the submitted body, records the new run,
reloads without resubmission and performs an explicit exact-key/body HTTP replay
that must return the same identity. Worker execution remains a separate operator
action. Mode `retained` checks five old scenarios and bounded cross-day charts.

Capture-only modes `catalog`, `copilot-inspect`, `run-inspect` and `provenance`
show actual catalog/run/revision history without reexecuting models. `catalog`
may include an explicit first-page `version` to exercise complete inspection.
Run captures require `run_id`; optional `focus` is `summary`, `memo` or `chart`.
Provenance expands the real pinned specification/attempt detail. `hold_seconds`
is an integer from 0 to 45 (default 2), allowing the planned short chapter clips.
Record these clips after timed acceptance; their duration is footage timing,
not workflow latency. Use real readback identity/hash fields in the shot index.

Run each phase with a fresh bounded `r9-` prefix. Files are created exclusively;
a failed invocation remains failed and its identity is never reused. The model
phase saves its exact frozen requests before actual calls, then exercises one
clear request, one unsupported/adversarial request, one durable clarification and
a fresh grounded memo. It is an integration gate, not a new quality estimate.

Run the full checks in the fresh environment and keep separate bare-clone skips
and external-snapshot compatibility results. See [the contract](r9-handoff.md) for
mandatory cold, browser, monitoring, failure and preservation gates. Tool existence
or a partial run is not acceptance.
