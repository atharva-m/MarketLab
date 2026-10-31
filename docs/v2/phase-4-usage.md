# Binance spot browser workspace and canonical imports

Phase 4 implementation is under independent review and acceptance. Consult the
[verification report](phase-4-verification.md) for observed gates and limitations;
this guide does not establish completion or hosted validation. The existing
[Phase 2 CLI](phase-2-usage.md) and [Phase 3 numerical CLI](phase-3-usage.md) remain
available. Generalized numerical execution requires no model.

## Owned local setup

Use the locked Python/frontend dependencies and a disposable database, Redis and
storage root. Preserve original services and data. Back up and restore the owned
database before applying forward migration `0010_v2_browser_imports`; never run a
destructive downgrade or apply this milestone to original services.

After configuring the owned `MARKETLAB_DATABASE_URL` and `MARKETLAB_STORAGE_PATH`,
quiesce its writers and explicitly initialize the root ledger:

```powershell
.\.venv\Scripts\uv.exe run --locked python -m marketlab.dataset_cli v2 capacity-initialize
```

Initialization verifies registered artifacts, inventories retained files and
outstanding data reservations, binds the database to the exact normalized root,
and records a checksummed receipt. A root mismatch, missing/corrupt artifact,
unresolved live writer or ledger failure blocks new intake. Existing data is never
deleted or forgiven to fit a quota. A later unmanaged write or missing/changed
baseline file requires drained reconciliation. Historical completed readers keep
their existing integrity checks.

Run the existing API and frontend against that owned configuration. The ordinary
frontend proxy targets API port 8000. Acceptance tooling uses separately owned
ports 55175/55176 with `MARKETLAB_PHASE4_TEST=1`; this does not change original
service configuration. Local mode has shared stack-operator authority and origin
protection. It does not provide authenticated remote/customer access.

Linux native recovery is bound to the visible PID namespace, kernel boot and
namespace-init birth. `/etc/machine-id` is optional; no host identity file is
created or modified. Keep packaged API and worker processes in the same owned
container PID namespace (for example, run the worker with `docker exec`). A process
restart inside that namespace can prove exact prior PID/birth death. A recreated
container, new namespace or changed Linux boot is a foreign execution domain;
unresolved older tickets remain charged and cannot be automatically declared
dead. Drain and reconcile owned work before replacing that namespace. Earlier
Linux tickets recorded with the old plain machine-id identity also remain foreign
and require ownership evidence; they are never silently reinterpreted or reset.

## Catalog and explicit selection

Open the **Binance workspace** navigation item, then Catalog. Instrument labels
and base/quote units come from the registry. Empty catalogs provide ingestion and
file-import onboarding. Register a new Binance spot instrument using explicit,
operator-verified source symbol/base/quote metadata; no symbol splitting or
automatic provider lookup occurs.

Choose an instrument and bounded UTC date window. Inspect registered daily
alternatives and explicitly pin one version per touched day, including research
history. Incomplete alternative pages do not establish a gap or a unique default.
Coverage windows with more than 1,000 alternatives return a safe density error;
narrow the date range and use dataset pagination. No dataset is silently replaced
with a newer alternative.

Disabled instruments remain readable/researchable from retained versions and
reject new imports. Display-name edits do not rewrite historical pinned metadata.

## Official daily ingestion

Use Official ingestion to select one or two enabled registered instruments and
completed UTC days. Confirm the instrument/day count before submitting. Follow
the durable submission and child jobs; transport or worker exit alone does not
prove publication. Open the catalog only after the job reports a registered
version. Revision-checked cancellation prevents later success when it wins the
existing publication boundary. No background missing-day download occurs during
research selection.

## Canonical file imports

One import contains one Binance-origin daily CSV or Parquet file. Preserve the
original numeric trade IDs and supplied quote quantity. Unsupported venues,
derivatives, OHLCV-only data, implicit quote derivation and arbitrary column mapping
are rejected. Caller-supplied origin/provenance is an operator declaration, not
independent proof of Binance authenticity.

CSV header:

```text
source_trade_id,executed_at,price,quantity,quote_quantity,is_buyer_maker,is_best_match
```

Use exact decimal strings, the selected explicit timestamp encoding, and the
Phase 2 boolean/null schema. CSV supports `rfc3339_utc`, `unix_seconds`,
`unix_milliseconds` and `unix_microseconds`; Parquet requires
`arrow_timestamp_us_utc` and the exact canonical types. The supplied timestamp
must belong to the selected UTC day. Use the retained canonical conversion
procedure from Phase 2 to generate Parquet with locked PyArrow and retain the
input/conversion hashes outside Git; renaming a CSV does not create Parquet.

For a reproducible format example, save the following as
`artifacts/canonical_csv_to_parquet.py`. It converts an already verified canonical
CSV using `rfc3339_utc`; it does not establish Binance origin. It keeps supplied
quote quantities, uses exact decimals and bounded batches, and creates a new
output exclusively. Retain the script/source/output hashes with the original
Binance verification and conversion evidence.

```python
import csv
import hashlib
import re
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

source, target = map(Path, sys.argv[1:])
names = [
    "source_trade_id",
    "executed_at",
    "price",
    "quantity",
    "quote_quantity",
    "is_buyer_maker",
    "is_best_match",
]
schema = pa.schema(
    [
        pa.field("source_trade_id", pa.string(), nullable=False),
        pa.field("executed_at", pa.timestamp("us", tz="UTC"), nullable=False),
        *[pa.field(name, pa.decimal128(38, 18), nullable=False) for name in names[2:5]],
        *[pa.field(name, pa.bool_(), nullable=True) for name in names[5:]],
    ]
)


def file_hash(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


if not 0 < source.stat().st_size <= 4 * 1024**3:
    raise ValueError("Source exceeds canonical daily bound")
before = file_hash(source)
target.parent.mkdir(parents=True, exist_ok=True)
csv.field_size_limit(4096)
batch, count = [], 0
with source.open(encoding="utf-8", newline="") as incoming, target.open("xb") as outgoing:
    reader = csv.DictReader(incoming)
    if len(reader.fieldnames or []) != 7 or set(reader.fieldnames or []) != set(names):
        raise ValueError("Canonical header required")
    with pq.ParquetWriter(outgoing, schema, compression="zstd") as writer:
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Exact canonical column count required")
            if not re.fullmatch(r"0|[1-9][0-9]*", row["source_trade_id"]):
                raise ValueError("Original numeric ID required")
            if not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", row["executed_at"]
            ):
                raise ValueError("Exact UTC microsecond timestamp required")
            row["executed_at"] = datetime.fromisoformat(row["executed_at"].replace("Z", "+00:00"))
            for name in names[2:5]:
                if not re.fullmatch(r"[0-9]{1,20}(?:\.[0-9]{1,18})?", row[name]):
                    raise ValueError("Canonical exact decimal required")
                row[name] = Decimal(row[name])
                if row[name] <= 0:
                    raise ValueError("Positive supplied values required")
            for name in names[5:]:
                if row[name] not in ("", "true", "false"):
                    raise ValueError("Canonical nullable flag required")
                row[name] = {"": None, "true": True, "false": False}[row[name]]
            count += 1
            if count > 20_000_000:
                raise ValueError("Daily row bound exceeded")
            batch.append(row)
            if len(batch) == 16_384:
                writer.write_table(pa.Table.from_pylist(batch, schema=schema))
                batch.clear()
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=schema))
if count == 0 or file_hash(source) != before or target.stat().st_size > 4 * 1024**3:
    raise ValueError("Empty, changed or excessive canonical conversion")
print("source_sha256", before)
print("parquet_sha256", file_hash(target))
print("rows", count)
```

```powershell
.\.venv\Scripts\uv.exe run --locked python artifacts/canonical_csv_to_parquet.py artifacts/verified-day.csv artifacts/import-example/day.parquet
```

Enter `arrow_timestamp_us_utc` and the printed output hash for the Parquet
manifest. The import worker still enforces its full canonical validation and
declared UTC day. Generated files and evidence remain excluded from Git.

In File import, select the file and enter its instrument, UTC day, format,
timestamp encoding and source provenance. The browser hashes bounded slices in a
worker. Confirm the manifest before upload. The browser sends the original File
as a raw request body, managing Content-Length itself; never use multipart form
data or manually set that forbidden browser header.

Progress stages are distinct: hashing, transport, verified upload, durable queued/
running normalization and published dataset. A verified upload has the expected
length/hash but has not yet passed normalization. Finalize the current generation
once, then follow import/job status. Duplicate operation replay does not create a
second job.

Upload capabilities expire after 15 minutes and authorize one generation claim.
Failed or expired unfinalized uploads require explicit renewal and file reselection;
there is no partial/chunk resume. Renewal cannot replace finalized data or reset
terminal normalization failure. Refresh retains the import identity/status, not
the local file handle or capability token. Retained failed-generation bytes stay
charged until verified owned cleanup. Cancellation and lease expiry do not prove
an active native writer has drained; unresolved tickets conservatively retain
capacity.

## Research and charts

Choose market profile, two-instrument comparison or volatility clusters. Confirm
the pinned daily versions and `[history_start,start)` warm-up separately from
`[start,end)` evaluation. Profile/comparison require at least 12 actual eligible
preceding five-minute bars; clusters require 300. Registered daily coverage alone
does not establish eligible warm-up. Comparisons require exactly equal quote
assets; USD and USDT are different and no conversion is performed.

Results preserve exact numerical formulas, counts, null reasons and provenance.
Missing buckets remain missing. Choose an explicit bounded chart window when the
research range exceeds chart limits; charts use the same pinned versions.
Generalized copilot/memos remain unavailable until Phase 5. Existing legacy
copilot, memo and completed report routes retain their historical scope.

## Limits and recovery

| Work | Limit |
| --- | --- |
| Canonical daily source/logical rows | 4 GiB each; 20 million records |
| CSV record | 4,096 bytes |
| Ingestion submission | 1–2 instruments; at most 62 instrument/day children |
| Research | At most 62 versions and 17,856 five-minute buckets across instruments including warm-up |
| Chart | 1m/5m; at most 1,440 buckets and five daily partitions |
| Local stack data admission | 100 GiB committed plus reserved data |
| Concurrency | Four staged upload slots; eight running ingestion/numerical slots |
| Durable attempt | Existing 60s lease/10s heartbeat; three attempts; 1,800s numerical deadline |

Storage quota, physical free-space reservations and per-run limits are separate
checks. Failed/orphan bytes and uncertain process ownership can block admission.
Never resolve pressure by resetting counters, lowering production limits, deleting
unverified data or pruning unrelated resources. Drain exact owned workers,
preserve evidence/backups, verify ownership/references, and reconcile only after
verified cleanup. No automatic garbage collection is provided.

Errors show a fixed safe code and request ID. Keep these with the import/job/run
identity when diagnosing a failure; do not paste tokens, raw records, credentials
or private filesystem paths into public reports. No commit, push, original-service
deployment or Phase 5 authorization follows from this guide.
