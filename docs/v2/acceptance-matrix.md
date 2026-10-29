# V2 acceptance matrix

This is the Phase 1 acceptance design as narrowed to Binance spot by the user
on October 28, 2026. The [prior exact design](history/pre-binance-20261028/README.md)
is historical; the amendment changes future scope only. All Phase 2–9 rows are **not run**
until their separate implementation approval. Current observed documentation and
baseline outcomes are in [verification](phase-1-verification.md). No historical
test count substitutes for running the then-current required suite.

## Evidence and scoring rules

Each invocation records ID, exact source/dirty overlay and lock/protocol identity,
command/configuration, UTC start/end plus monotonic elapsed time, environment,
owned resource IDs, expected outcomes, actual counters/hash comparisons, safe
failure detail, and raw evidence location/hash. Every failed/incomplete invocation
remains retained when rerun. No changing thresholds after observing a result.
Missing prerequisites leave the relevant gate incomplete. Report peak memory only
when measured with sampling interval and process coverage; otherwise unmeasured.
Client HTTP cancellation is distinct from upstream token cancellation.

Every phase has an independent read-only review; blocking findings must be fixed
and reviewed. Appropriate full locked/offline, real PostgreSQL, lint/format/type,
frontend/build/browser, live legacy, and package checks are required in each runtime
phase for the surfaces it touches. All applicable cases must pass; documented
historical-input skips stay explicit and do not count as passes. Hosted CI and
local actual-data/model/multi-host evidence are separate claims.

## Requirement-to-gate mapping

| ID / delivery phase | Required scenario | Pass condition |
| --- | --- | --- |
| P1-01 / 1 | Contract coverage and source inventory | Every scope item maps to contract/interface/limit and future acceptance row; source facts verified against recorded revision |
| P1-02 / 1 | Baseline evidence | Source/working tree and available protected inventory/service snapshots recorded; unavailable evidence explicitly blocks later operations |
| P1-03 / 1 | Documentation consistency | Local links resolve; JSON/CSV examples match declared contracts; compatibility/authority boundaries agree; no runtime implementation claims |
| P1-04 / 1 | Independent review | No unresolved implementation-blocking decision or blocking finding; actual review identity/outcome recorded |
| P2-01 / 2 | Actual generalized Binance ingestion | Full daily BTCUSDT 2025-02-01 and SOLUSDT 2025-03-01 archive/checksum acquired through official adapter, normalized/published/read back; all hashes/counts exact; unavailable source is blocked, not substituted |
| P2-02 / 2 | Actual Binance-origin canonical files | Use the checksum-verified SOLUSDT 2025-03-01 official Binance spot archive from P2-01; retain raw archive/checksum, source hashes and external conversion mapping/receipt; map the same day to canonical CSV and Parquet outside app; both import successfully and equal the archive reference in exact logical rows/count/hash. Source-byte dataset identities remain distinct. Reject non-Binance manifests and known non-Binance provenance; caller hash is not proof of origin |
| P2-03 / 2 | Canonical precision/time/type validation | Exercise all encodings and day boundaries, >18 fractional precision, floats, NaN, offset/naive/submicrosecond timestamps, overflow, missing/extra/duplicate columns, invalid bools, null flags, missing quote quantity and attempted implicit derivation; valid exact, invalid rejected before publication |
| P2-04 / 2 | IDs and metadata | Binance instruments with the same trade ID stay separate; numeric 2/10 ordering exact; opaque/renumbered IDs and non-Binance venue aliases rejected; labels do not mutate pinned metadata; semantic edits after publication rejected |
| P2-05 / 2 | Identity/dedup/source replay | Same-source fresh key reuses verified version; same key conflicting body 409; exact within-version duplicates collapse; within-version conflicts fail; corrected source values produce new immutable daily alternative without overwriting old bytes; conflicting IDs across a selected snapshot fail; empty input fails |
| P2-06 / 2 | Bounds and durable ingestion | Exact-limit and one-over file/row/record/partition/key/child counts; real concurrent claims, lease/reclaim/stale fencing, third-attempt exhaustion, publication rollback, corruption, crash recovery; no partial published artifact |
| P2-07 / 2 | Migration and legacy data | Fresh and populated disposable upgrade, old CHECKs/rows/artifacts unchanged, original ingest/inspect API/CLI shapes and v1 identities exact |
| P3-01 / 3 | Original five scenarios | Retained BTC profile, ETH profile, cross-asset, BTC cluster, ETH cluster over all 62 originals: every original result/summary hash exact through compatible v1 path; v2 projection every numerical value/count/null/bound equals independent retained reference |
| P3-02 / 3 | Generalized calculations | Independent Decimal oracle for new instruments/dates; 1m/5m bars, timestamp/ID ties, sparse days, warm-up, cross-day windows, same-quote comparisons and no missing-bar fill; exact values and eligibility |
| P3-03 / 3 | Invalid research | Different quotes (including USD vs USDT), alternative same-day versions, missing coverage, mismatched instrument/version, inadequate warm-up, invalid predicates/interval/alignment, >62 versions or >17,856 buckets fail explicitly |
| P3-04 / 3 | Cache and recovery | Cache miss/hit/eviction/corruption/outage and schema/instrument isolation; bounded cancellation and current-source claims/crashes; Redis outage does not change numerical truth |
| P3-05 / 3 | Cold preservation workload | Fresh owned cold all-62 run through the retained legacy research/memo path, including complete verification and owned worker drain, completes <1800s, 230,311,900 retained trades, all retained numerical/hash checks exact, one numerical attempt, legacy memo queued/zero calls until explicitly dispatched. New v2 memo enqueue is gated in Phase 5, not required before its tables exist |
| P4-01 / 4 | Complete browser import/research flow | Canonical upload → status → catalog → explicit versions → research → chart/readback for official Binance ingestion and Binance-origin canonical imports, correct units/Binance label/dates/counts and safe errors in Chromium/Firefox/WebKit |
| P4-02 / 4 | Discovery and defaults | Empty catalog onboarding, multiple Binance instruments/alternatives, disabled retained instrument, coverage gaps, limit failures, missing warm-up; no hardcoded January/BTC/ETH defaults outside labeled examples |
| P4-03 / 4 | Upload failure and replay | Truncated/oversized/wrong-hash stream, false Content-Length, expiry, concurrent/replayed PUT, repeated finalize, explicit renewal after upload_failed/expiry, cancellation in every pre-finalize state and race with finalize, interrupted browser, duplicate clicks, origin denial; post-claim PUT writes zero bytes, all retained generations charged, no direct S3 PUT capability, duplicate jobs, secret/path leakage, quota bypass, or partial publication; terminal imports cannot renew/reset |
| P5-01 / 5 | Actual-model copilot cohorts | Two independently invoked frozen 60-case cohorts, each ≥18/20 exact valid clear handoffs and zero unsafe handoffs among 40 negatives; all calls/reservations/outcomes/resources accounted |
| P5-02 / 5 | Actual-model memo cohorts | Two frozen 20-run cohorts; each 20/20 valid grounded memos, all selected required claims and three paragraphs, zero invented numbers/units/causes/recommendations |
| P5-03 / 5 | Actual durable clarification | Two fresh requests each reaches five accepted clarification answers and a sixth actual response; subsequent sixth answer rejected 422, stale valid expected_revision rejected 409, no extra work/calls |
| P5-04 / 5 | Model outage/identity/recovery | Digest mismatch, unavailable model, malformed/oversized completion, context exhaustion, inference timeout, process death around call reservation/checkpoint/handoff; safe failure, no refunded calls/duplicate research, manual numerical path usable |
| P5-05 / 5 | Generalized grounding | Same numerical spec through manual and copilot equals exact values/reference; hostile display metadata, ambiguous Binance asset/quote selections, non-Binance requests, unselected dataset IDs, unsupported markets, excessive context fail or clarify without unsafe handoff |
| P6-01 / 6 | Backend parity | Local and S3-compatible backends verify identical registered content/manifests/logical results for original and generalized data; migrated old artifacts retain original bytes/IDs |
| P6-02 / 6 | Object failure matrix | Crash before upload/during upload/after verified objects/before commit/after commit; wrong ETag assumption avoided, missing/corrupt generation fails, same-version race reuses winner, stale token cannot register |
| P6-03 / 6 | Storage outage/cache/quota | Actual unavailable storage and expired credentials, full/poisoned cache, pinned-cache pressure, scratch exhaustion, expired uploads and retained failed reservations; bounded failure/retry, no overwrite or silent fallback |
| P6-04 / 6 | Location migration/restore | Copy, verify, atomic mapping switch and reversal; original copies retained until explicit retirement; coordinated DB+object restore to isolated resources reads every sampled artifact exactly |
| P7-01 / 7 | Distinct-host workers | At least two real hosts cooperate; 20 independent deterministic numerical jobs across both hosts plus ingestion and inference jobs; no duplicate committed result, exact output, host/execution ownership demonstrated |
| P7-02 / 7 | Distributed recovery | Repeat each crash boundary three times; competing claim/lease loss/network partition/stale success and cancellation race. ≤3 attempts, monotonically increasing tokens, zero stale registrations, terminal state agrees with registered result |
| P7-03 / 7 | Shared model admission | Multi-host copilot/memo contention: one cooperating dispatch at a time, copilot priority at selection, no attempts/calls spent waiting; upstream continuation measured separately |
| P7-04 / 7 | Monitoring and compatibility | Actual normal CLI workers visible; old/incompatible worker cannot claim v2; missing capability/lock/source fails safely; bounded metrics omit customer data and cardinality hazards |
| P8-01 / 8 | Two separate customer stacks | Distinct DB instances, buckets/credentials, Redis, worker pools, model endpoints, OIDC audiences and membership verified; no shared mutable catalog/state |
| P8-02 / 8 | Access matrix | Viewer/operator/service actions exercised; missing/expired/wrong issuer/audience/key/role tokens denied; foreign IDs/buckets/uploads/jobs inaccessible; local mode cannot be exposed as customer mode |
| P8-03 / 8 | Browser/session threats | PKCE/state/nonce/CSRF/origin, cookie flags/expiry, role revocation, OIDC outage/key rotation, token-controlled URL injection, metadata script/link injection; zero unauthorized mutation/data disclosure |
| P8-04 / 8 | Quota/audit/credential controls | Concurrent reservation races, low quota, credential rotation, import capability expiry/scope, failed authorization audit, secret-redaction inspection; exact counters and no privileged leakage |
| P8-05 / 8 | Provision/backup/deprovision rehearsal | Two owned stacks provisioned reproducibly; verified isolated restore; deprovision dry-run identifies only owned resources, original services untouched; destructive actions separately authorized |
| P9-01 / 9 | Integrated acceptance | All then-current mandatory suites and P2–P8 gates pass at final exact source; older-source evidence identified separately; no failing mandatory gate waived |
| P9-02 / 9 | Performance and operations | Controlled 1-worker vs 2-host/2-worker 20-job fixed campaign, three repetitions each; report throughput/p50/p95/time/memory/storage/admission without asserting speedup unless measured; every individual run meets existing 1800s attempt bound |
| P9-03 / 9 | Preservation and cleanup | All protected hashes exact, original identities/images/mounts/start/restart/health/endpoints unchanged for observed interval, dumps retained/verified, exact ownership cleanup and port/resource ledger reconciled |
| P9-04 / 9 | Handoff | Fresh setup, upgrade/rollback restrictions, import templates, user/operator/security/recovery docs executed against owned environments; independent review no blocker |

## Frozen actual-model campaign definition

Before Phase 5 implementation acceptance, write the literal prompts, structured
contexts, expected specs/outcomes, source versions, clarification transcripts,
memo selections, and scoring script into reviewed fixtures and record their hashes.
The distribution below is fixed now; concrete fixture bytes must be reviewed
before the first scored inference and cannot change between the two cohorts.
Use the pinned current 9B model/settings and new v2 prompt identity.

Each copilot cohort has 20 clear prompts: four per existing five scenario shapes,
covering at least three Binance spot instruments, two non-January dates, and
both official-archive and Binance-origin canonical datasets with numeric IDs. Clear
correctness requires exact canonical spec and exactly one durable handoff, not
merely plausible language. Twenty ambiguous/invalid prompts cover missing fields,
ambiguous Binance asset/quote selections, conflicting dates, missing/alternative versions, quote mismatch,
and insufficient history. Twenty adversarial/unsupported prompts cover metadata
instruction injection, non-Binance venues, arbitrary sources/SQL/code, unsupported
markets/workflows,
invented instruments, oversized inputs, and model/dataset selection attempts.
All 40 negatives require zero research handoff; classify expected refusal or
clarification versus safe failure separately. HTTP rejection before inference is
recorded as no call, never described as an actual model response.

Each memo cohort has four runs per scenario shape across both old/new coverage,
selected metrics, valid null reasons, and two quote/base units. Review every
rendered statement against exact pinned facts; passing JSON alone is insufficient.
Record native responses, call reservations, hashes and timing, validation failures,
resource monitoring coverage, and model identity before/after. Capture all worker
PIDs with ≤1s sampling through each invocation; require every planned sample or
an explicit failed resource gate. Do not retune or add a post-hoc supplement to
convert a failed mandatory invocation into a pass. Any scoped amendment is
prospective, keeps the original failed invocation, and gets independent review.

Clarification fixtures must define all five missing-field answers in advance,
keep every round unresolved until its intended point, and exercise native durable
continuation without forced state/database edits. Fixed mocks/protocol tests are
additional evidence, not substitutes for actual responses.

## Prerequisites and authority boundaries

Future gates require retained original artifacts/reference hashes, checksum-verified
Binance input and external canonical-conversion evidence, reachable official
Binance archives, owned PostgreSQL/Redis/object
storage, installed pinned weights/model capacity, two distinct hosts, two isolated
customer environments, and configured external OIDC. Record actual infrastructure
identity and software versions when supplied. Missing prerequisites block that
gate; they do not authorize purchases, accounts, cloud uploads, original-service
restarts, global Docker/WSL/clock/GPU changes, or unrelated repairs.

Phase 1 runs documentation checks and read-only inventory only. It does not run
the application suites or any acceptance row for future runtime phases. No
distribution/security/performance claim follows from documentation review.
