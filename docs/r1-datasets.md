# R1 historical dataset contract

Approved scope: Binance Spot BTCUSDT daily trades for January 1, 2025 UTC. This
contract was written before the catalog migration and publication implementation.
The synthetic `/trades` subsystem and CLI are independent and unchanged.

## Input, bounds and normalization

`python -m marketlab.dataset_cli ingest --symbol BTCUSDT --date 2025-01-01`
uses the official `https://data.binance.vision/data/spot/daily/trades/` archive and
its `.CHECKSUM` file. Only BTCUSDT and that date are enabled in R1. The library's
provider-shaped fixture route uses local archive/checksum files; it is not an
arbitrary remote URL fetcher. Download limits: 512 MiB compressed, 4 GiB expanded,
20 million CSV records, 4096 bytes per CSV line, 4096 bytes per checksum; request
connect/read/write/pool inactivity timeout 30 seconds. Redirects, environment
proxies and retries are disabled. Limits may be lowered by library tests; the
CLI uses these fixed bounds. Verify SHA-256 before opening the ZIP. Require one
regular member whose exact basename is BTCUSDT-trades-2025-01-01.csv; never extract
archive paths. Reject symlinks, encryption, extra members and unsafe names.

Seven CSV columns (no header): source trade ID, price, quantity, quote quantity,
integer execution microseconds, buyer-maker boolean, best-match boolean. IDs are
canonical unsigned decimal integers within signed 64-bit range (Binance IDs fit
this representation); preserve their integer value without applying synthetic ID
rules. Values use positive plain decimal text with at most 20 integer and 18
fractional digits; Arrow decimal128(38,18) preserves exact values without rounding.
Empty archives are rejected. Booleans are exactly True/False. UTC timestamps must fall in the requested day.
Normalize using disk-backed SQLite for bounded-memory duplicate detection and
ascending numeric source-ID order. Same identity with equal normalized values
collapses; different values block publication. Historical identity is
(binance_spot, symbol, source_trade_id), independent of synthetic IDs.

Parquet columns: venue/string, symbol/string, source_trade_id/int64,
executed_at/timestamp(us, UTC), price/decimal128(38,18), quantity/same,
quote_quantity/same, is_buyer_maker/bool, is_best_match/bool. Use Zstandard
compression and fixed batches. The logical content hash covers normalized rows
in source-ID order. File hashes describe actual output bytes; cross-version
Parquet byte identity is not promised.

## Catalog and publication protocol

Add migration `0003_dataset_versions` after `0002_trades`. Create only
`dataset_versions` with dataset_version_id (64 lowercase hex primary key),
source_sha256, manifest_sha256, relative manifest_path, venue, symbol, trade_date,
row_count, status constrained to published, and published_at UTC. No synthetic
table change. The service exposes inserts/reads only; catalog update/delete
operations are not provided. Database superusers and external filesystem writers
remain outside the immutability boundary.

Version identity hashes canonical JSON of source SHA-256, venue/symbol/date,
schema version, transform version and dependency-lock hash. Same inputs resolve to the same ID;
changed source bytes or transform identity produce another ID. Provenance retains
retrieval time, URLs, expected/actual source hash, Git HEAD/dirty state and
uv.lock hash. Manifests distinguish requested day from observed timestamp bounds;
these bounds do not establish exchange completeness.

Stage under storage `.staging/`; parse, write and read back Parquet, compute file
and logical hashes, write complete manifest/quality report, flush files. Acquire
a PostgreSQL advisory transaction lock keyed by dataset version with a finite
lock timeout. If catalog row exists, verify registered manifest and all artifact
hashes/readback before returning it. Otherwise atomically rename complete staging
publication into `datasets/<version>/venue=binance_spot/symbol=BTCUSDT/date=2025-01-01/`
and insert the catalog row in the same locked database transaction. Artifacts are
complete before registration; readers discover rows only after commit. Concurrent
same-version publishers reuse the winner; they never overwrite final files.
Failure after rename can leave an unregistered immutable directory. Retry verifies
its complete manifest/artifacts and adopts it; corrupt directories fail without
replacement. Staging temporary files are removed on ordinary failure. Process
crashes may leave staging directories; inspect manually. No automatic GC.

This protocol assumes one catalog and one shared storage root, local filesystem
atomic rename and cooperating application writers. It provides safe synchronous
publication/idempotency, not worker fencing, storage replication or a cross-system
transaction or a power-loss durability guarantee. Manual removal of registered artifacts is detected as corruption.

## Inspection and offline route

`python -m marketlab.dataset_cli inspect --version VERSION` verifies catalog-backed
artifacts and returns the registered manifest. Library `ingest_archive(engine,
root, archive_path, checksum_path, symbol=..., trade_date=..., provenance=...)`
uses the same parser/publication pipeline for provider-shaped fixtures. It cannot
publish with a mismatched checksum. `ingest_day` downloads and invokes that path.
Missing catalog versions return no result; orphan directories are not discoverable.
CLI failures emit safe stderr and nonzero exit; no source records/credentials/SQL.

## Examples and operational limits

The command uses existing Settings (`MARKETLAB_DATABASE_URL`, optional separate
password, and `MARKETLAB_STORAGE_PATH`, including the existing .env behavior).
Apply `alembic upgrade head` to the intended database before ingestion. Ingestion
prints dataset_version_id and relative manifest_path; inspection prints the
verified manifest. Exit 0 is success, exit 2 invalid arguments, exit 1 an
operation/output failure. Output sink failures can occur after bytes were written.

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli ingest --symbol BTCUSDT --date 2025-01-01
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli inspect --version <64-lowercase-hex-version>
```

Provider-shaped synthetic fixtures are generated in `tests/test_datasets.py`:
create a ZIP with the exact official member basename, seven-column synthetic
rows and a matching `<sha256>  <archive-name>` checksum document, then call
`ingest_archive` with a disposable engine and root. This executes the same
checksum, normalization, publication and inspection code without network access.
The CLI intentionally has no arbitrary archive/URL option.

Inspect catalog records via `inspect_version(engine, root, version_id)`. It returns
None only for an absent version, and fails on missing/corrupt registered artifacts.
Same-source reruns verify the registered version before returning it; they do not
reparse trusted identical bytes into a replacement. Concurrent first submissions
serialize registration under the version lock.

Orphan inspection is manual: compare `datasets/**/manifest.json` version identities
against catalog rows and inspect `.staging/`/`.downloads/` only when no ingestion
process is active. Unregistered final directories may be adopted by a verified
same-input retry. Do not delete registered paths or assume an unregistered path is
safe to delete while another publisher runs. Ordinary failures clean owned staging
and download directories; process termination may leave temporary files. R1 does
not provide automatic cleanup, update/delete operations or distributed fencing.

For isolated verification use tmpfs PostgreSQL or a disposable database and a
private artifact root. Existing legacy tables/records are not historical storage.
Readback is intentionally complete and may be CPU-intensive for large inputs;
limits and batching do not imply a large-dataset performance guarantee. Measured
results and external blockers are in [R1 verification](r1-verification.md).


## R2 compatibility note

This document records the approved R1 contract. The later approved R2 extends the
allowlist to BTCUSDT/ETHUSDT daily archives throughout January 2025 and routes
synchronous ingestion through durable fenced jobs; see [R2 contract](r2-jobs.md).
R1 schema, transform/version identity, normalization, source limits and old immutable
manifests remain valid. Existing command success output and inspection semantics
are preserved. Job state is stored separately, never added to old manifests.
