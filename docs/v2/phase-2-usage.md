# Binance spot v2 ingestion CLI

Phase 2 supplies explicit CLI ingestion and catalog commands for registered
Binance spot instruments and dates. The browser, bars/research, copilot and memo
interfaces retain their existing scope until their later phases are delivered.
Actual acceptance status is in [verification](phase-2-verification.md).

## Setup and instrument registration

Use the existing locked Python 3.13 environment. Configure
`MARKETLAB_DATABASE_URL` and `MARKETLAB_STORAGE_PATH` for the intended isolated
database and storage root, retain a verified backup, and rehearse `alembic upgrade
head` there. Migration 0008 adds v2 tables and verified BTCUSDT/ETHUSDT registry
mappings without changing old tables/manifests. This phase performs no rollout to
the original running services. The migration is forward-only; restore a verified
backup into a separate environment when needed.

Register another official Binance spot instrument with operator-verified asset
metadata. For SOLUSDT the request file contains:

```json
{"venue_id":"binance","market":"spot","source_symbol":"SOLUSDT","base_asset":"SOL","quote_asset":"USDT","display_name":"SOL/USDT","trade_id_order":"numeric","adapter":"binance_daily"}
```

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli v2 instrument-add --request sol.json --key register-sol
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli v2 instruments
```

The generated identity is `binance:spot:SOLUSDT`. Venue, market, symbol, assets,
numeric ordering and source adapter are immutable. Display name/enabled changes
use `instrument-update --instrument ID --request FILE --key KEY`, with
`expected_revision` and `display_name` and/or `enabled`. Disabling blocks new
imports while retaining reads. Other venues, derivatives and fabricated aliases
are unsupported. Do not infer assets by splitting symbol text.

## Official daily archives and workers

A submission request file for one day contains:

```json
{"schema":"daily-ingestion-v2","adapter":"binance_daily","instrument_ids":["binance:spot:SOLUSDT"],"from_date":"2025-03-01","before_date":"2025-03-02"}
```

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli v2 submit --request day.json --key sol-march-first
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli v2 worker --max-jobs 1 --submission <submission-id>
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli v2 jobs --submission <submission-id>
```

Ranges are UTC and end-exclusive, with one or two instruments and at most 62
instrument/day jobs. Official imports require completed past UTC days. Archive
availability is a provider prerequisite, not guaranteed by registry membership.
The adapter fetches only official Binance daily trades and checksums; it does not
change provider/day or follow a caller URL. Missing input fails explicitly.

Workers claim compatible execution identities only. The invocation is bounded
to 1..62 jobs and optional `--wait-seconds 0..3600`. A failed attempt count is not
a successful dataset count; inspect jobs for partial success/retry/terminal state.
Process crashes consume attempts and recover after database-time lease expiry,
within three total attempts. Incompatible queued work remains inspectable; it
does not silently execute under a new build.

## Binance-origin canonical files

Each file represents one registered Binance instrument and declared UTC day.
Supply strict uncompressed UTF-8 CSV or exact-schema Parquet, plus the canonical
metadata object from the [contract](phase-1-contract.md#4-canonical-files-provenance-and-normalization-phase-2).
CSV has exactly these unique columns, in any order:

```text
source_trade_id,executed_at,price,quantity,quote_quantity,is_buyer_maker,is_best_match
```

Trade IDs retain canonical numeric Binance IDs. Timestamps use the declared UTC
encoding; decimals are positive plain exact text with at most 20 integer and 18
fractional digits. Quote quantity must be supplied by Binance, never calculated.
Flags use `true`, `false`, or empty for unavailable. Parquet requires string IDs,
timestamp(us, UTC), decimal128(38,18) values and nullable boolean flags. Exact
metadata fields, timestamp encodings and validation rules are in the contract.

Keep original source references, source hashes, official checksum evidence where
available, and external conversion evidence. A caller hash verifies copied bytes,
not venue authenticity; arbitrary well-formed files cannot prove origin or detect
secretly fabricated IDs/quote amounts. The platform does not import another
venue merely because its data fits canonical columns.

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli v2 import --manifest manifest.json --file trades.csv --key import-sol-day
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli v2 imports --import <import-id>
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli v2 worker --max-jobs 1 --submission <submission-id>
```

The CLI copies source bytes into immutable owned staging, verifies length/hash,
then atomically enqueues one durable job. The worker uses that copy. Same-key
replay returns the original import/job identity even if the caller file was moved;
conflicting metadata reuse fails. Failed staging needs a fresh import/key, and
terminal jobs cannot be reset. A fresh-key identical source reuses its verified
dataset identity. Corrected source bytes create an immutable alternative; they
never overwrite earlier versions. Equivalent CSV/Parquet files retain distinct
source identities and can share the same logical row hash.

## Catalog, coverage and cancellation

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli v2 datasets --instrument binance:spot:SOLUSDT
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli v2 inspect --version <version-hash>
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli v2 coverage --instrument binance:spot:SOLUSDT --from-date 2025-03-01 --before-date 2025-03-02
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli v2 cancel --job <job-id> --expected-revision <revision> --key cancel-job
```

The v2 catalog adapts verified legacy versions and new v2 versions without
rewriting historical artifacts. Lists default to 25/max100 entries and expose
bounded filter-bound cursors. Coverage spans at most 62 days, identifies gaps and
alternative versions, and reports observed bounds without claiming full provider
coverage. Days with more than 100 alternatives include a continuation cursor and
mark aggregate observed bounds incomplete. Selection never chooses a preferred
alternative automatically. Detail inspection performs full integrity readback.

Cancellation serializes with publication: an accepted cancellation prevents a
later success; a committed success causes cancellation conflict. Supply the
current revision from status, and reuse the operation key only to replay that
same operation. SIGINT/SIGTERM stops new worker claims and drains current work;
native forced process termination recovers by lease expiry.

## Limits and retained storage

Official input: 512 MiB ZIP/4 GiB expanded, checksum <=4096 bytes. Canonical input:
4 GiB raw and 4 GiB logical row bytes. Daily input: 20M records, CSV record <=4096
bytes, control/manifest/quality JSON <=64 KiB each, normalized Parquet <=4 GiB.
Parquet footer metadata is capped at 16 MiB and each decoded row group/page at
64 MiB; write bounded row groups (the acceptance converter uses 16,384 rows).
Duplicates count before deduplication. Catalog growth does not raise job limits.

Source/output/scratch reservations check physical capacity before processing;
failed/expired data retains its charge until explicit verified cleanup. Scratch
is bounded per job. There is no automatic GC or cleanup of original services.
Keep raw data/evidence/credentials outside Git and use the ownership ledger when
planning operator cleanup. CLI exit 0 means the command succeeded, 2 means invalid
arguments/input, and 1 means an operational/conflict failure; inspect durable job
state for actual ingestion completion.
