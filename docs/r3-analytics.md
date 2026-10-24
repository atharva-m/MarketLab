# R3 analytical reads and cache contract

Approved October 24, 2026. This contract is recorded before R3 code. The user
approved documentation, implementation with the prescribed coder/reviewer,
full acceptance and honest outcome documentation. The initial implementation
request excluded commit/push. Later October 24, after local acceptance/review/
cleanup, the user authorized verified R3 commit/push, hosted CI verification,
actual R3-only CI fixes with prescribed coder/reviewer and outcome documentation/
publication. This supersedes the initial restriction without expanding feature
scope. Artifacts/data, credentials, environments and weights remain excluded from
Git. R1/R2 are complete and retained; R4-R9 remain unauthorized.

## Scope and numerical definition

Calculate bars on demand from catalog-registered Binance Spot BTCUSDT/ETHUSDT
January 2025 daily Parquet. No persistent bar datasets, migrations or new jobs.
One symbol per request, explicit versions (one per touched UTC day), no latest
selection. Intervals are exactly 1m/5m, UTC aligned, half-open [start,end).
Require aligned UTC start/end; return whole contained bars only. Open/close use
ascending (executed_at, numeric source_trade_id); high/low use price extrema.
Sum normalized quantity and source quote_quantity exactly; count accepted rows.
VWAP is quote volume/base volume, rounded once to 18 fractional digits with
round-half-even. Other decimals serialize with exactly 18 fractional digits.
SQL decimal(38,18) sums are checked: overflow is an analytical error, never a
float fallback. Valid historical inputs remain valid even when a sum overflows.
5m is directly aggregated from trades and independently reconciled against 1m.
Empty buckets are omitted, never filled. Missing partitions are coverage errors.
Completed coverage means registered daily coverage, not proven exchange completeness.
Bar definition and serialization version is bars-v1; cache schema is cache-v1.

## API and limits

Add GET /v1/bars with repeated version parameters, symbol, interval, start and end.
Return dataset_versions sorted by day, symbol, interval, start/end, definition,
expected_buckets, returned_buckets, empty_buckets and bars. Each bar has start/end,
open/high/low/close, base_volume, quote_volume, trade_count and vwap.
Version IDs are 64 lowercase hex. Timestamps require explicit UTC timezone and
seconds, using the existing strict parser before validating UTC alignment.
No implicit version choice, duplicate days/versions, extra versions or truncation.
At most 1440 expected buckets, hence one day 1m or five days 5m and at most five
partitions. Invalid requests return 422 before DB work; absent versions 404,
coverage mismatch 409, integrity/arithmetic failures 422, unavailable catalog or
overload 503, query timeout 504. All errors use safe fixed diagnostics.

DuckDB uses fixed templates and bound parameters for paths, timestamps and interval;
paths only come from catalog/manifests. Disable external access/extension loading
beyond trusted local Parquet reads; never accept SQL, paths, URLs or configuration.
At most two expensive reads per process, with one-second admission timeout. Each
DuckDB connection has one thread, 512 MiB memory setting, private 2 GiB bounded
spill and 60-second execution deadline. Interrupt actual query on deadline or
caller cancellation; finish cleanup before releasing capacity. Memory setting is
not an RSS guarantee. Failed reads do not return partial data or cache results.

## Verification and identity

Read committed catalog rows only. On first read inspect_version fully verifies
manifest/schema/hash/logical contents. Cache this verification per process, bounded
to 128 versions, keyed by complete catalog identity and manifest/artifact file
metadata (size, mtime_ns, ctime_ns, inode). Each request checks catalog and metadata
before a Redis hit. Changes/restart require re-verification; unsafe paths, symlinks,
unregistered orphans and missing/corrupt artifacts fail. Retain R1 cooperating-
writer assumption; no arbitrary metadata-preserving tamper guarantee.

## Cache and concurrency

Cache immutable completed bar responses and fixture-only completed summaries.
Keys include cache schema, definition/schema, sorted dataset identities or run
identity and canonical parameter SHA-256. Canonical JSON bytes, no float decimals.
Bars TTL 900 seconds with uniform +/-10% jitter (810..990); summary TTL 3600
seconds with jitter (3240..3960). Limit whole serialized envelope to 1 MiB.
Redis connect/operation timeout 100 ms; no retries. Three consecutive command
failures open a ten-second circuit; bypass then one controlled recovery probe.
Successful commands reset consecutive failures. Invalid cache envelopes are misses,
never returned. Errors/incomplete responses are never cached. Redis is optional.
HIT means validated cached body; MISS means computed and successfully cached;
BYPASS means disabled/unavailable/open/oversized/write failure. Coalesce identical
reads per process; waiter cancellation cannot cancel another request's work.
Cap in-flight distinct work and verification with the same two-query admission
boundary; hits may wait behind verification but never bypass integrity checks.
Metrics use bounded labels for outcomes/failures/circuit/coalescing/query time,
active work/overload/timeouts. Retain Redis 256 MiB allkeys-lru, no persistence;
verify container headroom in isolated acceptance. No new summary calculations/API.

## Preservation and acceptance

Do not alter R1/R2 schemas, manifests, artifacts, identities, ingestion limits,
source behavior, publication locks/fencing/atomicity, job retries/leases or CLI
signatures/output. DuckDB/Redis do not enter ingestion or publication transactions.
Preserve all existing synthetic HTTP/CLI, imports, pagination/filtering, errors,
health, observability and locked dependencies. Add only /v1/bars and R3 settings.
No warm-up downloads, research, models, UI, scheduling, GC or multi-host claims.

Exact fixtures cover arithmetic, timestamp ties/numeric IDs, shuffled input,
minute/day boundaries, missing buckets/coverage, overflow, decimal rounding,
5m/1m equivalence, canonical requests/identities and unsafe inputs. Real PostgreSQL
covers catalog visibility/rollback/integrity, plus all retained migration/jobs tests.
Cache tests cover TTL ranges, 1 MiB boundaries, corruption, coalescing, concurrency,
cancellation/failure capacity release, breaker/recovery. Actual isolated Redis must
show MISS/HIT, primed-response outage recomputation, restart and real LRU eviction.

Restore 62 saved R2 catalog registrations only into owned disposable PostgreSQL
after full verification against retained manifests/artifacts. Generate both
intervals for every partition, reconcile 230311900 counts, volumes and OHLC with
an independent streaming reference, compare cross-day and 1m/5m results, restart
and cache states. Record actual counts/hashes/durations/hardware/limits; peak memory
only if measured. Missing input or failing reconciliation blocks monthly acceptance.
Run locked lint/format/mypy, full offline/PostgreSQL and focused live legacy API/CLI
plus historical compatibility. Recheck formatting after final documentation.
Coder gpt-6.1-sol high; independent read-only reviewer gpt-6-astra medium; resolve
findings and rerun relevant checks. Inspect resource ownership before cleanup;
preserve original services/data. Record actual evidence in r3-verification.md,
README and roadmap. The initial implementation authorization excluded commit/push; the later publication authorization above now governs verified R3 publication and hosted CI.

VWAP ratios support up to 38 integer digits plus 18 fractional digits: a valid source quote/base ratio can exceed source price width. The decimal(38,18) checked bound applies to source fields and sums, not to the divided VWAP representation. Cold full verification may take longer than the 60-second DuckDB deadline; cancelled verification is drained before its expensive slot is released. Redis reads use atomic GETRANGE bounded to cap+1 bytes before JSON parsing.


Cancellation means cancellation of the asynchronous service task. An HTTP TCP disconnect does not guarantee immediate cancellation by FastAPI; any continuing work retains the documented admission, verification and native query bounds. No immediate TCP-disconnect cancellation claim is made.


The application constructs one BarService per process/event loop. Library callers must reuse a single service with matching engine/storage/cache configuration and close it at shutdown. Capacity and coalescing belong to that service; independently constructed library instances do not share admission or in-flight work. This lifecycle requirement defines the documented per-process app limits.


## Approved-scope closeout

R3 implementation, full local acceptance, independent review and owned-resource
cleanup completed October 24, 2026. [Actual verification](r3-verification.md)
records results, resolved findings and operational limits. At local implementation
closeout no commit/push had been performed or authorized and hosted R3 CI was
unrun. The later October 24 publication authorization above supersedes that initial
restriction; subsequent actual outcomes belong in verification. R4-R9 remain backlog.


The verified implementation was subsequently committed/pushed as
`54f15d3c4312248f1ec8beda6bca805d4e37bb38` and
[hosted CI run 40072552311](https://github.com/atharva-m/MarketLab/actions/runs/40072552311)
passed on Ubuntu/Windows quality and Linux integration. No CI fix or feature
scope change was needed. Hosted checks do not replace the separate completed
local full-month/bar-cache acceptance; see the verification record for exact
coverage and limits. R4-R9 remain unauthorized.
