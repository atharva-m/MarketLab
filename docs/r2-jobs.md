# R2 durable ingestion contract

Approved October 23, 2026. This contract precedes the R2 migration and code. R1
historical contract and evidence remain valid. The initial implementation request
excluded commit/push. On October 24, 2026 the user subsequently authorized verified
R2 commit/push, hosted CI verification, actual R2-only CI fixes and outcome
documentation. This does not expand feature scope; market data/artifacts and
credentials remain excluded from Git.

## Requests and persistent records

Allow only Binance Spot BTCUSDT/ETHUSDT UTC dates in January 2025. A request has
one or both exact symbols, inclusive start date, exclusive end date, and a caller
idempotency key (1–128 ASCII letters/digits/dot/underscore/hyphen). Canonical sorted
symbols/date interval/execution contract are SHA-256 hashed. The same key/hash
returns the same submission/jobs; different hash fails. At most 62 children.
Fresh keys deliberately recheck sources; jobs do not define dataset identity.

Add migration 0004_ingestion_jobs after 0003_dataset_versions; never alter trades
or existing dataset catalog. ingestion_submissions: UUID-text primary key, unique
idempotency_key, request_sha256, symbols JSON text, start_date, before_date,
execution_contract, created_at. ingestion_jobs: UUID-text primary key, submission
FK, venue, symbol, trade_date, source_mode (official/inline/fixture), input_sha256
(nullable except fixture), state, attempt_count, fencing_token, owner nullable,
lease_until nullable, eligible_at, result_version FK nullable, safe error nullable,
created_at/updated_at. Unique (submission_id,symbol,trade_date). CHECKs constrain
state, attempt 0..3, nonnegative token, supported venue/symbol/date; running iff
owner/lease present; succeeded iff result_version present. ingestion_attempts:
(job_id,attempt_number) primary key, unique(job_id,fencing_token), owner, start/end,
outcome running/succeeded/transient/permanent/expired, safe error. FK to job.

## Claims, state and retry

States queued/running/retry_wait/succeeded/failed. Database clock_timestamp() is
the time authority. Claims lock one eligible queued/retry_wait or expired running
job using FOR UPDATE SKIP LOCKED. An expired running attempt becomes expired;
if already attempt 3, fail without a fourth execution. Otherwise increment both
attempt_count and fencing_token, assign fresh worker identity and 60-second lease,
and record running attempt. Heartbeat every 10 seconds on a separate connection;
renew only current unexpired running owner/token. Late heartbeat cannot revive.

Worker processes execute one job at a time; multiple local processes can cooperate.
When Python receives SIGINT/SIGTERM, CLI handlers set a stop flag: finish current
work and stop further claims. Native force termination (including Windows process
termination APIs) uses lease-expiry recovery instead of graceful draining.
This does not impose a wall-clock deadline on valid progressing ingestion; source
inactivity and per-day size/row bounds remain finite. Hard termination uses leases. Killed workers recover after
lease expiry. A failed heartbeat marks the in-process claim lost and prevents further success.
Generic claims accept only source_mode official and matching execution_contract.
Inline network calls use mode inline, so another worker cannot steal a caller
provided client or lowered limits. Local fixtures use mode fixture with verified
input SHA-256 persisted. Generic network workers never claim inline/fixture jobs;
there is no provider fallback after a fixture crash. Explicit library resume is
required for these modes, retaining caller supplied source/client/limits.
Transient source network/408/429/5xx or known recoverable PostgreSQL failures retry
with 10 then 30 seconds (valid delta-seconds or HTTP-date Retry-After may delay further, capped at
3600 seconds; malformed/past guidance adds no delay); three total
attempts including crashes. Permanent validation/integrity/limit/local storage
errors and unknown failures stop. Diagnostics never expose records/SQL/credentials.
No hidden HTTP retries. An inspection lists at most 62 daily jobs and their attempt
history; result versions and completion counts explicitly identify partial success.

## Fenced publication and filesystem boundary

Keep R1 schema/transform/lock identity, manifest format and immutable namespace.
Fully verify staged artifacts or existing catalog/orphan artifacts outside the
publication transaction. Record the verified manifest hash; cooperating writers
never mutate artifacts. Begin a bounded transaction, lock the job row, validate
current unexpired owner/token, acquire version advisory transaction lock, recheck
lease and catalog/orphan metadata against the preverified hash. If another writer
created an unverified artifact since preflight, abort/retry preflight outside the
transaction. Never perform full Parquet readback while holding transaction locks.
For new versions, atomic rename completed staging to final; register immutable
catalog row and update job/attempt success in the SAME transaction. Existing
verified versions complete the job in that transaction. Lock order job then version;
lock_timeout 10 seconds, statement_timeout 15 seconds, idle transaction timeout
15 seconds. Recheck lease immediately before final writes. Ownership serialized
under the job row is the publication linearization boundary: reclaim cannot occur
until transaction ends; transaction rollback invalidates both catalog/job writes.

Crash after rename/before commit leaves an undiscoverable orphan; a current owner
verifies and adopts it. Crash after commit/before response leaves succeeded job;
repeat execution/submission returns durable result. Stale owner cannot register,
mark success/failure/retry, or refresh lease after reclaim. Ordinary failures clean
only owned temporary paths; no automatic orphan GC. One catalog/shared storage,
cooperating writers, atomic rename; no distributed filesystem/DB transaction,
replication, arbitrary external-writer or power-loss guarantees.

## Compatibility and commands

Existing ingest/inspect commands and ingest_day/ingest_archive library signatures
remain callable and successful output shape is preserved. Synchronous ingestion
submits a private single-day durable request and executes it inline through the
same worker/fenced publisher, requiring no separate worker. ingest_day waits for
its persisted retry eligibility and executes at most three attempts. Both
ingest_day and ingest_archive accept optional resume_job_id: inline network resume
requires matching mode/symbol/date, fixture resume additionally requires identical
verified archive SHA-256; succeeded resume verifies catalog artifacts. An unexpired
active owner cannot be reclaimed. Resume after process death waits for expiry or
returns not eligible; terminal failed jobs are never reset. Provider fixtures use
the same pipeline with caller local files; no remote arbitrary URL option.

Additional dataset CLI commands: submit --symbols BTCUSDT ETHUSDT --from-date
2025-01-01 --before-date 2025-02-01 --key KEY; worker --max-jobs N [--submission ID]
[--wait-seconds N]; jobs --submission ID. Worker max-jobs 1..62 and idle waiting
0..3600 seconds are bounded, not a daemon/scheduler. A new invocation resumes
remaining eligible jobs. Failed terminal jobs are inspected, not silently reset.

Retain source 512 MiB compressed / 4 GiB expanded / 20M rows / 4096-byte line and
checksum limits; timeout 30 seconds, no redirect/environment proxy. Month days
exceeding these fail. Requested coverage and observed record bounds remain distinct.
No old manifest rewrites. No changes to legacy API/CLI, dependencies/deployment.

## Acceptance and evidence

Tests: request expansion/validation/idempotency; fresh/populated upgrade and DB
constraints; real concurrent SKIP LOCKED claims; heartbeat/expiry/reclaim/stale
mutation fencing; all three attempts including crash budget; retry classification;
job/catalog atomic rollback; concurrent same-source/changed-source publication;
corruption; controlled real process termination before publication, during staging,
after rename/before commit and after commit; fixture pipeline parity; R1 and legacy
regressions. Actual historical run must publish/readback all 62 daily partitions,
restart/resume, replay key, fresh-key recheck with no new same-source versions.
Record per-day checksums, bytes/rows/logical hashes/times/attempts and full completion
mapping. Provider/day failure blocks monthly completion. Measure memory peaks only
with suitable instrumentation or report unavailable. Independent prescribed review
and safe owned-resource cleanup are required. Publication now follows the later
October 24 authorization; actual hosted CI outcomes must be observed and recorded.


## Finding interrupted inline work

The existing synchronous success JSON remains unchanged. After interruption, use
the documented read-only job tables to locate recent inline identities, then pass
the exact job ID to the matching library resume call with the same source/client
and limits. Do not reset attempts or edit ownership manually.

```python
import sqlalchemy as sa
from marketlab.datasets.jobs import jobs, inspect_submission

with engine.connect() as connection:
    recent = (
        connection.execute(
            sa.select(
                jobs.c.job_id,
                jobs.c.submission_id,
                jobs.c.source_mode,
                jobs.c.symbol,
                jobs.c.trade_date,
                jobs.c.state,
            )
            .where(jobs.c.source_mode.in_(["inline", "fixture"]))
            .order_by(jobs.c.created_at.desc())
            .limit(20)
        )
        .mappings()
        .all()
    )
# inspect_submission(engine, recent[0]["submission_id"]) includes attempts/errors.
# ingest_day(..., resume_job_id=recent[0]["job_id"]) resumes mode inline.
# ingest_archive(..., resume_job_id=...) requires the same verified fixture SHA.
```

Resume is explicit after a hard crash and cannot steal a still-valid lease.
Generic worker commands handle only durable official range jobs. Their console
attempt count includes failed attempts; inspect the submission for actual success
and pending retry state. Ordinary filesystem errors and unrecognized failures
are terminal; workers must not silently change limits or substitute sources.
