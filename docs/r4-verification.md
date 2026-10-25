# R4 actual verification

October 24, 2026. R4 implementation, full local numerical/compatibility acceptance,
independent source review and ownership-checked cleanup passed. Final locked checks
passed **655 offline and 152 real PostgreSQL cases**, zero skips. No commit or push
is authorized; hosted CI is unrun. R5-R9 remain unauthorized. R1-R3 historical
evidence is retained unchanged.

## Scope, environment and provenance

Delivered [the approved contract](r4-research.md): strict research-spec-v1;
five-minute Decimal80 market_profile/cross_asset/volatility_cluster; separate
0005_research schema; database-time leased/fenced execution and atomic immutable
publication; manual HTTP/CLI; verified summary cache. No dependencies, lockfile,
deployment configuration or retained ingestion/bar/trade modules changed. The only
retained runtime integration is additive research lifecycle/routes in app.py; the
existing migration-head assertion now includes the four additive research tables.
No pre-January download, model, memo, UI, strategy, scheduler, GC or replication.

Owned PostgreSQL port 55434, Redis port 56381 and API port 58004 were isolated from
original services. Ownership IDs/labels/configuration were captured before use;
evidence and artifacts remain ignored under artifacts/r4. Historical input root
is artifacts/r2/historical-storage. Intel Core i9-14900HX: 24 cores/32 logical
processors; reported physical memory 34,053,414,912 bytes; Windows 11 build 26300.
Peak memory was **not measured**. Settings/memory limits are not measured RSS.

Execution used uncommitted source based on Git revision
111d3b8695573e43ac56c813c2b45e0781e86843, explicitly dirty, with lock hash
730f02bec94d1f824a2cadf74f60cf5dcc246faa55004d5d060b92931224618f.
The actual ten month runs pin source hash
e5e8667b76468cbcf39cc82b940a416dd8654c5b67cc8333d64d3e2b3f3bacff.
A later replay-response-only correction produces final source hash
d868cec2d64ae53661ff2bcd716f8b09a8ee89c99c3c8e754835cec0f899bc7c.
All 31 per-file hashes and pre-fix copies prove only service.py/store.py changed:
the transaction now returns its actual new/replayed flag to HTTP/CLI. No numerical,
input-loading, publication or artifact format changed. Final-code readback of all
20 accepted result/summary payloads matched their references; final concurrent HTTP
and full-suite checks cover the correction. The month was not rescanned after this
metadata fix, and its original fingerprint/manifests were not rewritten. Evidence:
source-files-before-metadata-fix.json, pre-replay-service.py/pre-replay-store.py,
post-metadata-readback.json and month-acceptance.json. This is not a clean R4 commit.

## Actual retained-month reconciliation

An independent scaled-integer streaming scan freshly read all **62 partitions /
230,311,900 trades** (BTC 135,946,515; ETH 94,365,385), checking manifest/artifact/
logical hashes and generating **17,856 five-minute bars** in 642.593 seconds.
The separate Decimal reference exactly matched complete production result and
summary bodies, including coverage, nulls, units, warm-up spans and event fields.

Actual durable execution then submitted each of five full-period requests plus
one fresh-key independent repeat: **10/10 succeeded, one attempt each**. Replayed
keys returned their original identities. Each pair had identical numerical payload
hashes, all 20 payloads matched the independent reference, and each run's summary
returned MISS then HIT. All 62 source manifest/artifact hashes remained unchanged.

| Workflow | Evaluation UTC, exclusive end | Observed evaluation bars | Events |
| --- | --- | --- | --- |
| BTC profile | Jan 1 01:00 to Feb 1 00:00 | 8,916 | No missing buckets |
| ETH profile | Jan 1 01:00 to Feb 1 00:00 | 8,916 | No missing buckets |
| Cross-asset | Jan 1 01:00 to Feb 1 00:00 | 8,916 per asset | Aligned return reference matched |
| BTC clusters | Jan 2 01:00 to Feb 1 00:00 | 8,628 | 31 clusters, 128 qualifying, zero ineligible |
| ETH clusters | Jan 2 01:00 to Feb 1 00:00 | 8,628 | 33 clusters, 133 qualifying, zero ineligible |

All requests explicitly began history Jan 1 00:00. Registered/grid coverage does
not prove exchange trade completeness. Thresholds were not tuned to obtain events.

| Workflow | Results SHA-256 | Summary SHA-256 |
| --- | --- | --- |
| BTC profile | 3669b7e1e136f778e045bd274b274bb77b8de4f725e5bfa1555fc92f44c62619 | 72ed7f5d14a770ac58be86816f8a95e5733a79d321e9c6cbe80c377878592dd7 |
| ETH profile | d64b612c7b60847807bbb3bf5509c3021557f7703aa0b7fee1c7cbc407c9a7e9 | a1d4a74bd15a71d061b49b9ae66a57897c84f1beab120de72943c2db9698d87f |
| Cross-asset | 33724830e4f00c3a7365514407cd02fcc478d8f92f32336bf968f5cf849263a6 | 6a2bc6c1188f6024bb5340f63ded0698fde80c6caaa1652a5ea343e0a191cf81 |
| BTC clusters | ce1161929e93f3dbecbec1c912d30a7926accbbec29c0633a08e41c0b298615f | 6af0883f374d5580d425bc1b53f493cc359619f5601ef37fa4877271cafe8ad5 |
| ETH clusters | 60db0a2f782190c1c531f2354d2c4cb734cacaeadcfd906e3fa455e47c2bfa5d | ad79d22c7e37abf43ddcd7fc2f7caa1d6093c3a60b38a189fb2c2bdab09c5040 |

The full acceptance took 2,430.330 seconds. BTC's first request took 1,418.770s,
its fresh repeat 2.475s; ETH's first took 961.808s, repeat 2.465s. Cross-asset took
27.688s/4.839s; cluster requests approximately 2.43-2.49s each. These include
submission/verification/execution/summary phases, with verified input/cache reuse;
they are not controlled cache benchmarks. Cold verification remained within each
unchanged 1,800-second validation/attempt bound; native DuckDB limits stayed intact.

Before cleanup, catalog-final.json exported exactly the accepted ten submissions,
runs, attempts and registrations plus 62 dataset registrations, explicit storage
root and migration head. Fixture runs with other roots were excluded. Preserve
that snapshot alongside immutable artifacts for later inspection/restoration.

## Tests, real failures and independent review

Final scripts/check.ps1 -Integration passed locked Ruff lint/format (93 files),
strict mypy (31 sources), **655 offline / 152 PostgreSQL cases**, zero skips.
PostgreSQL tests took 48.22s. Hardware and full logs are retained; these are local
Windows checks against Linux PostgreSQL, not hosted R4 CI or cross-platform claims.

Coverage includes strict JSON/canonicalization/direct-library validation; exact
sample statistics and interpolated quantiles; strict equality rejection; negative/
zero-variance correlation; gaps and rolling recovery with previous valid history;
missing evaluation start; boundary clusters/singletons; no lookahead; source order
reproducibility; real fresh/populated migrations preserving all five legacy tables;
actual foreign keys/checks; concurrent claims/submissions; three expired attempts;
stale fencing; and lease expiry between fence and final writes rolling back
result/run/attempt changes. Registered output corruption fails before cache hits.

Four real worker processes were killed before staging, during partial staging,
after rename/before registration and after commit/before response. The first
three recovered in attempt 2; committed success was retained without another
claim. Partial staging was never discoverable. Cooperative calculation timeout
drained actual worker-thread execution and prevented publication. Tests also cover
16 MiB result-cap cleanup, execution fingerprint mismatch and coalesced summary
reads where canceling one waiter does not cancel another. The final same-key HTTP
race returns one 201/new and one 200/replayed response for one durable run.

Prescribed independent gpt-6-astra read-only review identified five actionable
issues, all resolved by the prescribed coder: eager Git provenance broke packaged
startup; unchecked final mutation rowcounts risked atomicity after expiry; manual
dataclasses bypassed service validation; PostgreSQL retry classification was too
broad; and the concurrent idempotency loser incorrectly reported new creation.
Additional numerical/migration boundary coverage was added. Reviewer independently
ran focused suites, audited actual hashes/lineage and accepted the scoped metadata
fix/readback distinction. Final independent documentation audit passed with no findings.

Initial failures remain recorded. The first full check stopped at eight overlong
new migration SQL lines, fixed by wrapping literals. Expanded process tests also
initially missed an after-rename marker while source was being edited; the child
diagnostic did not prove its cause. Focused and full frozen-source phase reruns
passed, without waiving that phase. A subsequent full suite passed 654 offline /
148 PostgreSQL but failed a retained R2 pre-publication checkpoint because its
child obtained no claim. A second passed 655 offline / 150 PostgreSQL but failed
a retained R1 publication case with the same immediate-claim symptom. The original
rows were cleaned before clock/lock capture; those initial runs are not passes.
All four retained process phases passed a focused rerun. The final complete run
passed 655/152; earlier logs are preserved separately rather than overwritten.

## Database-clock environment limitation at R4 closeout

Isolated diagnostics reproduced the missing-claim mechanism: freshly queued jobs
temporarily became ineligible because PostgreSQL wall time moved backwards.
Before affinity, 3,281 iterations/32.743s captured three failures; for example a
job eligible at 16:20:37.762745 UTC was later observed at DB time
16:20:37.157366. A second eligible at 16:20:37.448885 was observed at
16:20:36.345939. Immediate second claims also returned none, with queued state and
false eligibility. Captures retain rows, contract, locks/activity and DB-clock vs
monotonic samples. These establish the reproduced mechanism; the exact initial
failed rows were not captured.

Pinning only the verified owned PostgreSQL container to one CPU did not resolve
it: 4,529 iterations/43.955s captured three more failures. The experimental
affinity was restored. A quiescent diagnostic after cold reads ended still captured
three failures in 5,826 iterations/57.625s. **The clock issue is not fixed**; the
final passing suite does not establish clock stability. Evidence files are
claim-diagnostic-before-affinity.json, claim-diagnostic-after-affinity.json and
claim-diagnostic-quiescent.json/log. Under backwards DB time, immediate claims can
temporarily return no eligible work. Existing database-time/fencing semantics
remain intact; neither host/WSL clocks, test eligibility semantics nor retained
runtime were changed. No blind retry loop was added to obtain a green suite.

## Live compatibility, cache and cleanup

Actual summary cache acceptance passed MISS/HIT (TTL 3901s); four primed outage
BYPASS reads; Redis restart and application restart; real LRU eviction (311
evictions, target removed, then MISS/HIT); corrupt/oversized envelope rejection;
oversized write bypass; and disk corruption rejection before a primed cache hit.
Redis remained 256 MiB/allkeys-lru/no persistence with 512 MiB container headroom.
Ollama-unavailable manual submission/worker/results/summary passed. No model was
called. Bounded metrics were observed.

Retained live trade import/rollback/C ordering/exact-ID/paginated/missing CLI,
exact cached bars, historical fixture repeat/CLI inspection and original R1 full
readback (1,516,556 rows) passed. Existing Docker image build/startup passed
/health/live, /openapi.json and /trades with no Git checkout. New research
executions require checkout provenance; registered numerical reads do not.

Ownership-checked cleanup removed exactly the three owned R4 API/PostgreSQL/Redis
containers and the owned R4 image. Original API/PostgreSQL/Redis IDs and running/
healthy states exactly matched the initial baseline; the temporary affinity was
restored before cleanup. catalog-final.json was validated as ten accepted runs/
62 dataset registrations before removal. Evidence is artifacts/r4/cleanup.json.

Artifacts/evidence/snapshots remain ignored, no market data or credentials enter
Git, and nothing has been committed or pushed. Hosted CI remains unrun. Apart from
the explicitly observed DB-clock environment limitation, no unresolved R4 code or
numerical acceptance blocker remains.

A later user-authorized clock follow-up partially mitigated large distortion, but dense sampling still found smaller Docker initd backwards steps. An exploratory initd help command unexpectedly restarted original containers and violated uptime preservation; standard recovery restored the same IDs/images/volumes and healthy host endpoints. Recovery is separate from earlier R4 acceptance, and uptime/cache continuity are not claimed. See [actual follow-up and incident](r4-clock.md). Historical results/immutable fingerprints remain unchanged; no application eligibility/fencing change or commit/push occurred. The clock fix remains incomplete.
