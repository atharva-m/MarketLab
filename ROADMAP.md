# MarketLab recovery roadmap

Status: R6 and its cold-verifier follow-up COMPLETE with full local acceptance/review/owned cleanup; published as c94ef4b, initial hosted run 40269166877 failed and reviewed test-only CI recovery is in progress; R7-R9 remain unauthorized backlog. R5 COMPLETE with full local acceptance/review/owned cleanup; verified R5 was published as 19a1363 and hosted CI run 40177491693 passed; R1 COMPLETE; R2 COMPLETE — implementation, full local verification, independent review, actual 62-partition January publication/recheck and owned cleanup passed. R3 COMPLETE with full local acceptance/review/cleanup and passing hosted CI for verified implementation commit 54f15d3. R4 COMPLETE with full local acceptance/source review/owned cleanup under docs/r4-research.md; its application clock fix passed fresh verification with the known Docker clock discrepancy. Verified R4 and the clock fix were published as 2c0dd0b; hosted CI run 40167912094 passed for that revision. R2 implementation and documentation fix were committed/pushed; replacement hosted CI passed on both quality platforms and Linux integration after the recorded formatting failure.
Prepared: October 23, 2026.
Baseline: `55530ab01e0bc6f522c3c1d3938a51ad48a42e24` on `main`.

## Authority and approval boundary

Current publication authority (October 26, 2026): the user authorized
committing/pushing verified R6 and its approved cold-verifier optimization,
checking hosted CI, fixing actual scope-related CI failures through prescribed
coder gpt-6.1-sol/high then independent read-only reviewer gpt-6-astra/medium,
and documenting/publishing observed outcomes. This supersedes earlier
no-commit/push restrictions only for this verified scope. Preserve all R1-R6
behavior, immutable artifacts, tested-source distinctions and historical failures
and limitations. Artifacts/data, archives, credentials, environments and weights
remain excluded from Git. Verified publication is c94ef4b; initial hosted run
40269166877 failed and reviewed test-only recovery is being prepared. Exact
outcomes are recorded in [R6 verification](docs/r6-verification.md) and the
[optimization follow-up](docs/verifier-optimization.md); local acceptance is not
a hosted CI pass. R7-R9 and unrelated feature/deployment/system authority do not
follow. Earlier authority/closeout records below remain historical.

Historical post-R6 implementation authority: the user authorized exact cold-verifier
optimization and bounded CPU parallelism under [the pre-code contract](docs/verifier-optimization.md),
with prescribed coder/reviewer, full cold all-62 numerical-workflow acceptance
within 1800s, retained R1-R6 checks/hashes and owned cleanup. The initial request
excluded commit/push; later publication authority above now governs.
Historical R6 completion and its cold/ordered evidence remain intact; R7-R9
remain unauthorized. This scoped authority supersedes verifier/concurrency freeze
only as specified, not numerical definitions or resource/deployment protections.

Frozen-source cold acceptance passed in 272.814s including cleanup: all 62
partitions/230,311,900 trades and every original manifest/physical/logical hash
matched; numerical result/summary payloads matched independent R4 references.
Two spawned verification workers shared a maximum-two compute budget with DuckDB,
then were reaped. Full checks passed 811 offline/189 PostgreSQL cases. OS cache
was uncontrolled. Packaged Linux spawn/read/close, all 257 protected-file hashes
and ownership-checked resource cleanup passed; original service identities,
uptime and optional Ollama degradation were preserved. The optimization contract
records final review and all helper failures. The historical R6 cold failure
remains explicit. No commit/push or hosted CI was performed for this follow-up.

Current R6 authority (October 25, 2026): the user approved the detailed R6 plan,
ROADMAP.md/AGENTS.md updates, full [R6 contract](docs/r6-memos.md) before code,
prescribed coder/reviewer implementation, full acceptance and honest outcome
documentation. NO COMMIT/PUSH. Preserve R1-R5 and all historical evidence. This
supersedes earlier R6 exclusions only within that contract; R7-R9 remain backlog.
Earlier current-authority statements below are retained historical records.

Current authority (October 25, 2026): the user authorized committing/pushing verified R5, checking hosted CI, fixing actual R5-only CI failures through the prescribed coder/reviewer workflow, and documenting/publishing actual outcomes. Preserve R1–R4 and all R5 local evidence. This supersedes the initial R5 no-commit restriction only for this publication scope; R6–R9 remain unauthorized. Verified R5 was published as 19a1363 and hosted CI run 40177491693 passed. See R5 approval, closeout and publication records below.

Historical R4 publication authority (October 25, 2026): the user authorized committing/pushing the verified R4 changes and application clock fix, then checking hosted CI. This supersedes the earlier publication restriction without expanding R4 scope. The October 24 approval covered the detailed R4 scope, ROADMAP.md/AGENTS.md updates, the [R4 contract](docs/r4-research.md) before code, prescribed coder/reviewer implementation, full acceptance and actual outcome documentation. Preserve R1-R3 and historical evidence. R5-R9 remain unauthorized. Record actual hosted results for the exact published revision in [R4 verification](docs/r4-verification.md).

On October 24, 2026 the user approved the detailed R3 scope, ROADMAP.md/AGENTS.md updates, the [R3 contract](docs/r3-analytics.md) before code, prescribed coder/reviewer implementation and full acceptance. Preserve R1/R2. The initial implementation request excluded commit/push; the later R3 publication authorization below supersedes that restriction. R4-R9 remain unauthorized. These R3 approvals are historical execution authority; the R4 approval below now governs current work. Earlier milestone closeouts remain historical evidence.

Later on October 24, 2026, after completed R3 local verification/review/cleanup, the user explicitly authorized committing/pushing the verified R3 changes, checking hosted CI, fixing actual R3-only CI failures through the prescribed coder/reviewer workflow and documenting/publishing actual outcomes. This supersedes the initial R3 no-commit instruction without expanding feature scope. Archives/artifacts/data, credentials, environments and weights remain excluded from Git; R4-R9 remain unauthorized. Hosted results must be observed for the exact published revision and recorded in [R3 verification](docs/r3-verification.md).

On October 23, 2026 the user approved the detailed R2 proposal, authorized ROADMAP.md/AGENTS.md updates, implementation with the prescribed coder/reviewer workflow, preservation of R1, acceptance tests and honest results/blocker documentation. The initial R2 implementation request explicitly excluded commit/push. This scope approval superseded earlier statements that R2 was unauthorized; R3–R9 remain backlog.

On October 24, 2026, after verified R2 closeout, the user explicitly authorized committing/pushing the verified R2 changes, checking hosted CI, fixing actual CI failures within R2, and documenting/publishing actual results and blockers. This publication authorization supersedes the initial no-commit instruction without expanding R2 feature scope. Archives/artifacts/data, credentials, environments and weights remain excluded from Git. Hosted CI results must be recorded from actual run evidence; see the R2 publication record below.

The user explicitly approved this roadmap and authorized R1 implementation, AGENTS.md updates, the prescribed coder/reviewer workflow, preservation of existing behavior, checks and honest results/blocker documentation. That initial approval covered R1 only; R2–R9 were not authorized then. That later R2 approval authorized its completed work; the R3 approval above is now the current execution authority. The initial implementation task did not request a commit/push. The user subsequently explicitly authorized committing/pushing verified R1 changes, checking hosted CI, documenting actual results/blockers and pushing the reviewed verification update.

After explicit approval, record the approval and approved milestone here, then update AGENTS.md to that milestone before implementation. Approval of the roadmap establishes direction; execute only the milestone the user authorizes. If an approval is ambiguous, clarify the execution scope. Keep later milestones as backlog.

Use this root document as the durable roadmap reference for future sessions. Preserve the historical week 1–9 documents and commits; those labels describe completed repository increments, not completion of the original 14-week schedule. Use R1–R9 below for recovery milestones. Do not relabel unrelated work as progress on the original plan.

## R4 scope authority (October 24, 2026)

The user approved the detailed deterministic R4 proposal, ROADMAP.md/AGENTS.md
updates, the [R4 contract](docs/r4-research.md) before code, prescribed coder/reviewer
implementation, full acceptance and honest actual outcome documentation. The initial
request excluded commit/push; October 25 publication authority supersedes that
restriction. R5-R9 remain unauthorized. This later approval supersedes
historical R4 exclusions only for the approved contract; preserve R1-R3.

Deliver strict typed ResearchSpec, five-minute profile/cross-asset/clusters with
explicit January warm-up, Decimal80 definitions, separate durable research schema
and fenced execution/publication, immutable numerical results/summary, manual API/
CLI and actual summary caching. No pre-January ingestion or model/UI work. Full
retained suites, real PostgreSQL/crash/Redis checks, independent all-62-partition
reconciliation and repeatability are completion gates. Actual evidence belongs in
[verification](docs/r4-verification.md). Implementation, local acceptance, independent
source review and owned cleanup passed. Final locked checks: 655 offline/152 real
PostgreSQL cases. All 62 January partitions/230,311,900 trades reconciled independently;
ten durable workflow runs/repeats matched all numerical hashes, BTC/ETH clusters
31/33, source artifacts unchanged. The measured DB-clock regression remains an
environment limitation, not a resolved issue; see exact failures and provenance.

## Product objective retained from the original plan

Build a local, reproducible market-research platform with historical BTCUSDT/ETHUSDT data, deterministic synthetic demos, immutable Parquet datasets and research artifacts, PostgreSQL durable jobs/catalog/lineage, DuckDB analytical reads, Redis response caching, React UI and local Ollama inference. No paid service is required.

The final demonstration must show a clear natural-language request automatically submitting validated research, an ambiguous request asking for clarification, deterministic results, a grounded three-paragraph memo, Redis hits, and numerical results remaining accessible when Ollama is stopped. Manual structured submission remains available.

## What is already complete and must be preserved

| Repository history | Reusable completed work | Mapping to original plan |
| --- | --- | --- |
| Week 1 | Python 3.13, locked environment, FastAPI, Compose, migrations, CI, health, logs/metrics, actual Ollama compatibility smoke | Substantially original week 1 |
| Weeks 2–3 | Strict five-field synthetic trade contract, parsers, fixtures, UTC/decimal correctness, transactional PostgreSQL imports | Part of original weeks 2–3, plus supporting persistence |
| Weeks 4–7 | Bounded HTTP imports, exact-ID retrieval, pagination, symbol/time filters | Supporting API functionality; does not complete original weeks 4–7 |
| Weeks 8–9 | Local browsing and lookup CLI, failure handling, extensive regression and live TCP checks | Part of original week 8; not original week 9 copilot |

Baseline evidence: 456 offline and 76 PostgreSQL tests passed locally, six week 9 live TCP outcomes passed, and hosted Windows/Linux quality plus integration jobs passed. See [week 9 verification](docs/week9-verification.md). These are historical results, not automatic passes for future changes.

Keep existing `/trades` contracts, synthetic fixtures, global synthetic trade-ID behavior, import transactionality and streamed 1 MiB limit, filtering/pagination semantics, exact serialization, local CLI behavior, redacted errors, health/observability and locked environment. Do not replace the tested subsystem with historical ingestion.

R1 completed historical downloads/checksums/provenance, immutable dataset publication and the minimal catalog. R2 completed durable ingestion jobs and fenced publication, with actual month-scale publication/readback and same-source recheck. R3 subsequently completed bars and resilient caching; R4 completed typed manual research, durable numerical runs and summaries. Remaining backlog is copilot, memos, frontend and later evaluation/demo work. An Ollama smoke is a foundation, not an implementation of those later model capabilities.

## Sequenced recovery milestones

The order below restores the original dependency chain. Each milestone ends with a reviewable working slice, independent review, verification evidence and an explicit completion/blocked status.

| ID | Deliverable and exit gate | Original plan coverage | Rough effort |
| --- | --- | --- | --- |
| R1 | One-day historical ingestion, checksum/provenance, immutable Parquet and minimal catalog; detailed contract below | Missing weeks 2–4 | 25–40 hours |
| R2 | PostgreSQL durable jobs and fenced publication; expand verified ingestion to both symbols for January 2025 | Weeks 3–5 | 25–40 hours |
| R3 | Deterministic 1m/5m bars, DuckDB reads and Redis cache-aside with outage/eviction tests | Week 6 and cache portion of week 8 | 25–40 hours |
| R4 | Versioned typed ResearchSpec, manual submission service, reproducible runs, three workflows and deterministic metrics/summary | Week 7 and prerequisites from weeks 9–10 | 40–60 hours |
| R5 | Durable copilot interpretation, clarification and automatic validated submission through the same service | Week 9 | 25–40 hours |
| R6 | Separate memo jobs, grounded three-paragraph output, shared copilot-priority inference and immutable supplemental manifests | Week 10 | 35–55 hours |
| R7 | React ingestion/catalog/jobs, structured research form, copilot, charts and memo viewer with browser tests | Weeks 11–12 | 35–55 hours |
| R8 | Full model evaluations, recovery/failure injection, pipeline/cache/model benchmarks and operational dashboards | Week 13 and remaining platform evidence | 25–40 hours |
| R9 | Fresh-clone verification, complete documentation and recorded end-to-end demo | Week 14 | 10–20 hours |

These are planning estimates, not commitments or measured velocity: 230–370 remaining engineering hours, approximately 16–31 working weeks at 12–15 hours/week, excluding external delays. Re-estimate after R1 and R2 using actual time and blockers. Do not claim completion percentages from milestone numbering or test counts.

## Completed approved milestone: R1 — publish one reproducible historical day

### Goal and bounded scope

Publish one immutable dataset version for Binance Spot BTCUSDT trades covering `[2025-01-01T00:00:00Z, 2025-01-02T00:00:00Z)`. Use the official daily trade archive and its published SHA-256 checksum. The user approved this provider/date selection as part of R1.

Use a separate synchronous local ingestion command and library service. No background worker, new HTTP route, research workflow or UI is required for R1. Reuse existing httpx, PyArrow, SQLAlchemy/Alembic and validation utilities where their contracts fit; no dependency/lockfile changes are planned.

The official [Binance public-data documentation](https://github.com/binance/binance-public-data/blob/master/README.md) documents archive checksums and notes that Spot timestamps from January 1, 2025 use microseconds. Source metadata was captured during the actual checksum-verified download, publication and readback; see [R1 verification](docs/r1-verification.md) for measurements and limits.

### Concrete deliverables

1. **Bounded source adapter.** An allowlisted Binance Spot daily-trades adapter with explicit symbol/date arguments, streamed download, finite timeouts, explicit compressed/uncompressed size and row limits, and checksum verification before parsing. Pin and document finite defaults before implementation review; exceeding them must fail clearly without publishing. No arbitrary URL fetcher, paid API, credential requirement or automatic provider fallback. Retain archive URL, checksum URL, expected/actual SHA-256 and retrieval time. Never log credentials or raw records.
2. **Historical normalization contract.** Preserve source IDs, exact decimal values and UTC microsecond timestamps with a documented Arrow schema and stable record order. Use a separate historical identity `(venue, symbol, source_trade_id)`; leave the existing synthetic `trades` table and its global ID primary key untouched. Exact duplicate records may collapse with reported counts; conflicting records for the same historical identity block publication. Validate all required source columns and reject malformed or out-of-day records; never silently round or discard invalid data. Do not assume synthetic precision bounds are venue rules: document historical bounds and fail on overflow.
3. **Immutable storage.** Write compressed Parquet under a version-specific local/shared-volume namespace partitioned by venue, symbol and UTC date. A published version is never overwritten. Source archive and generated data stay outside Git. Define logical reproducibility separately from byte identity: repeated normalization of the same verified input and pinned transform produces the same logical content; record actual file hashes without promising identical Parquet bytes across library versions.
4. **Manifest and quality report.** Record schema/transform versions, dataset/version identity, source hashes/provenance, artifact hashes and sizes, raw/accepted/duplicate/conflict counts, requested interval, observed timestamp bounds, symbol/venue, validation outcomes, Git revision (and dirty state) and dependency-lock hash. Distinguish requested coverage from observed records: minimum/maximum timestamps do not prove gap-free exchange coverage. A failed input cannot produce a published manifest.
5. **Minimal PostgreSQL catalog.** Add a separate, additive dataset-version catalog with immutable manifest identity and published status. Do not repurpose the synthetic trade table. Specify the migration, constraints and publication protocol before coding it. Stage files, finish and verify immutable artifacts, then transactionally register the completed version. Readers discover only registered versions. A crash may leave an unregistered directory, but never a catalog entry pointing to unfinished artifacts. R1 requires safe retry/idempotency and documented orphan inspection; automatic garbage collection is deferred.
6. **Repeatable local invocation.** Provide a synchronous ingestion command returning a compact dataset/version and manifest-location result, plus a catalog inspection command or documented library call. Same source hash plus transform/config identity resolves to the existing version instead of duplicate publication. Changed upstream source bytes form a different source identity and never overwrite earlier versions. Failures have nonzero status and safe diagnostics.
7. **Offline synthetic route.** Provider-shaped synthetic archives and checksum fixtures exercise the same verification, normalization and publication path without network access. Existing canonical synthetic fixtures remain unchanged.

### Acceptance and evidence

- Offline tests cover checksum mismatch, HTTP/timeout/truncation errors, malformed archives/rows, archive path traversal and decompression limits, timestamp units, date boundaries, decimal precision, cross-symbol identity, duplicate/conflict behavior, deterministic normalization and corrupt artifacts.
- Real PostgreSQL tests verify additive migration, immutable catalog identity, repeated/concurrent submissions, rollback and catalog visibility. Failure injection before artifact completion and before catalog commit must leave no discoverable incomplete dataset; retry must be safe. This does not claim distributed worker lease/fencing guarantees, which belong to R2.
- A real one-day run verifies the provider checksum, publishes Parquet, reads it back, reconciles counts/hashes and demonstrates an idempotent rerun. Record actual bytes, rows, duration and measured memory only when available. Do not call a fixture-only run successful historical ingestion.
- Run Python 3.13 in the locked `.venv`, lint/format/mypy, all existing offline and PostgreSQL regressions, and a focused legacy CLI/API compatibility check. Use isolated disposable test resources and preserve user data.
- Add R1 contract/examples/verification documentation and README links. Record every skipped check and external blocker. Provider unavailability permits offline progress, but the historical-run acceptance gate remains incomplete.
- Use the prescribed coder (GPT-6.1 Sol, high), then independent read-only reviewer (GPT-6 Astra, medium); coder resolves actionable findings and runs appropriate checks. Preserve explicit later user model overrides.

### Explicit exclusions and review choices

R1 excludes ETHUSDT and full-month downloads, workers/leases, caches, analytical bars, research metrics, copilot/memos, UI, deployment expansion and changes to existing HTTP/CLI contracts. Later milestones add those capabilities in order.

R1 approval authorizes new historical-data modules, a separate synchronous ingestion entry point, immutable local storage and an additive catalog migration. These deliberate changes from completed week 9 restrictions are reflected in AGENTS.md. The approved choices are Binance Spot BTCUSDT for January 1, 2025, separate historical identity/storage, and bounded synchronous-first publication.

## Approved R2 contract and contracts retained for later milestones

### Approved R2: durable execution and scale-up

The approved detailed contract is [R2 durable jobs](docs/r2-jobs.md). Deliver 62 independently bounded daily jobs covering BTCUSDT and ETHUSDT for [2025-01-01T00:00:00Z, 2025-02-01T00:00:00Z). Add durable submission idempotency, job/attempt history, bounded local worker and inspection commands, synchronous R1 compatibility through the same fenced pipeline, transactional job-success/catalog registration, three-attempt crash recovery, and real full-month/readback/recheck evidence. Preserve existing version identity/manifests, normalization/source limits, API/trade CLI, dependencies/lock and deployment. Test migration preservation, concurrent claims, stale ownership, retries, process crashes and partial visibility with real PostgreSQL. Use isolated owned resources. R2 is complete only after actual 62-partition evidence and independent review; blockers remain explicit. No automatic GC, new HTTP routes, warm-up downloads, analytics/cache/research/model/UI or multi-host guarantees.

Use PostgreSQL `FOR UPDATE SKIP LOCKED`, 10-second heartbeats, 60-second leases, fencing tokens and three total attempts for transient failures. Enforce current ownership in the publication transaction; test stale workers, crashes and repeated execution without duplicate published results. Route R1 ingestion through this machinery without changing its source/normalization contracts. Expand to BTCUSDT and ETHUSDT January 2025 with explicit bounded jobs. Obtain pre-period warm-up history when required by later workflows; never silently truncate requested research periods.

### Approved R3: analytics and caching

Detailed approved contract: [R3 analytical reads](docs/r3-analytics.md). Implementation, full local acceptance, independent review and owned-resource cleanup are complete; see [R3 verification](docs/r3-verification.md). At local closeout changes remained uncommitted/unpushed; later R3 publication authorization is recorded above. R4-R9 require later authorization.

Define completed UTC bars, exact aggregation/rounding rules and 1m/5m intervals; missing bars remain missing, with no forward filling. Query published dataset versions via fixed templates and bound parameters. Cache immutable bar responses and completed numerical summaries only. Keys include cache schema, dataset/run identity and canonical parameter hash. Preserve the original TTLs (15 minutes bars, one hour summaries, ±10% jitter), 1 MiB value cap, 100 ms Redis timeouts, no automatic retries and a ten-second bypass after three failures. Coalesce identical reads per process and cap expensive uncached queries at two. Provide `X-Cache: HIT|MISS|BYPASS` and metrics; retain 256 MiB allkeys-lru/no persistence with container headroom. Test actual cached results during outage and eviction, beyond health probes.

### Approved R4: deterministic research before natural language

Detailed approved contract: [R4 deterministic research](docs/r4-research.md).
Implementation, full local acceptance, independent source review and owned cleanup
passed; [actual verification](docs/r4-verification.md) retains initial failures,
recurring DB-clock limitation and pre/post metadata-fix execution provenance.
Publication now follows the October 25 authorization above; R5-R9 remain backlog.

Implement a versioned strict ResearchSpec with dataset version, allowlisted workflow/symbols/metrics, explicit timestamps, interval and typed parameters/predicates. No expression strings, arbitrary SQL/code/paths. Validate shape, units/meaning, coverage and warm-up. Manual submissions use one idempotent application service and pin dataset versions, parameters, code revision and lock hash.

Support market-profile, cross-asset and volatility-cluster workflows. The supplied original plan does not fully define market-profile or cross-asset outputs: approve their numerical contracts at R4 entry before implementation rather than inventing hidden requirements. For clusters, preserve trailing 12-bar return volatility, comparison with the previous 288 valid volatility observations' 90th percentile (excluding current), volume above twice the preceding 12-bar mean, and at least two contiguous qualifying bars. Specify remaining volatility estimator/quantile details explicitly. Missing bars break clusters; insufficient warm-up is a coverage error.

Produce deterministic summary.json here so it is available before memo generation: drawdown as minimum close/running-maximum-close minus one; unannualized five-minute simple-return mean/sample-standard-deviation Sharpe proxy; top three current-volume/previous-12-bar-mean spikes; aligned five-minute log-return Pearson correlation; coverage/counts/units/definition versions. Use null plus reason when undefined. Distinguish descriptive asset statistics from strategy performance. Test exact fixtures and boundaries.

### R5: inbound copilot

Implement the planned `/v1/copilot/requests` creation, retrieval and clarification flow as durable jobs, returning submitted/needs_clarification/unsupported/failed. Use schema-constrained Ollama output plus independent shape, semantic and availability validation. Only a complete validated spec reaches the same manual submission service; persist request-to-run mapping atomically to prevent duplicate runs. The model has no tools or database credentials. Volume versus VWAP, vague dates and undefined thresholds must trigger clarification, never silent reinterpretation. Start the evaluation corpus here; full acceptance is in R8.

### Approved R6: outbound memo and inference lifecycle

The detailed approved contract is [R6 durable grounded memos](docs/r6-memos.md),
written before runtime changes. Approval covers implementation, full acceptance,
independent prescribed review and honest outcomes, excluding commit/push. The
updated 35-55 hour estimate includes shared admission, crash-safe supplements and
qualitative grounding; it is not measured velocity. R7-R9 remain unauthorized.

Enqueue memo work separately in the numerical-publication transaction with unique run identity; numerical success is independent. Use host Ollama with `qwen3.5:4b-q8_0`, configurable local/container connectivity and an initial 8K context window; record the installed model digest and measured runtime behavior. One inference worker prioritizes copilot over pending memos without preemption; use 120-second inference timeout and at most one retry, initial temperature zero and recorded settings. Generate exactly three structured paragraphs grounded only in deterministic summaries. Resolve allowlisted numeric placeholders in application code, reject unknown placeholders/unsupported numeric literals, handle nulls, disable raw HTML and label generated content. Formatting does not prove qualitative truth.

Publish `research_memo_{run_id}.md` in the immutable run namespace using a separate supplemental manifest; retain summary/memo hashes, model tag/digest, Ollama version, prompt/schema versions, decoding settings and timestamp. Never mutate the numerical manifest or overwrite a published memo. Expose separate pending/running/ready/failed memo status and safe retry.

### R7–R9: UI, evaluation and evidence

Build React/TypeScript/Vite views for ingestion/catalog/jobs, manual research, copilot clarification/provenance, charts and memo status/content. Fetch numerical results separately from mutable memo status. Cover browser workflows with Playwright.

Maintain 60 copilot prompts: 20 clear, 20 ambiguous/invalid and 20 adversarial/unsupported. Require zero invalid/adversarial executions and at least 90% semantic correctness on clear prompts; record clarification accuracy and latency. Keep actual-model evaluation distinct from mocked CI. Evaluate memo grounding, three paragraphs, nulls, provenance, retries, immutable publication and unsupported causal/predictive claims.

Inject Ollama failures during interpretation/memos and verify manual submissions/results remain usable without duplicates. Benchmark 1M/10M-row pipelines, Redis cold/warm/unavailable behavior, model cold/warm latency, token throughput, measured peak memory and queue delay. Report hardware, inputs and limits; do not substitute before/after memory snapshots for peaks. Complete Prometheus/Grafana operational views without treating current metrics exposure as a deployed dashboard.

Finish with a fresh-clone local run, actual evidence, reproducible instructions and recorded final demo. Resume claims must reflect measured dataset size, cache improvement and semantic evaluation outcomes.

## Session handoff and change control

At the start of future work, read this file, AGENTS.md and the latest approved milestone contract/verification. Report any inconsistency before changing scope. Preserve historical verification rather than rewriting prior results. At each milestone close, record its commit, implemented scope, checks, independent review, blockers and next approval gate here or in linked milestone records. Completion requires delivered capabilities and evidence, not only green tests.

Historical R1 closeout: R1 implementation passed 516 offline and 89 real PostgreSQL tests, plus actual official one-day historical publication/readback/idempotent reuse (1,516,556 records) and five CLI subprocess compatibility outcomes. Independent GPT-6 Astra review found no actionable findings and independently passed all 60 new offline and 13 new PostgreSQL cases. Owned disposable resources were verified and removed; original services remain healthy. R1 is complete. See [R1 contract](docs/r1-datasets.md) and [actual verification](docs/r1-verification.md) for evidence, resolved execution blockers and limits. At R1 closeout, R2–R9 remained backlog requiring later authorization. The verified implementation was committed/pushed as `75bb466c2bfa0a1e6ad0096335a54128fe7557ff`; [hosted CI run 40058652835](https://github.com/atharva-m/MarketLab/actions/runs/40058652835) passed Ubuntu/Windows quality and Linux integration (including image build, PostgreSQL, API smoke and Redis outage checks). Hosted pytest counts were not retrieved; the counts above are local. The CI documentation follow-up independently passed read-only review with no actionable findings and is published with this roadmap record. R2 was unauthorized at that closeout; its later approval is recorded above.


R2 handoff (October 24, 2026): COMPLETE. Additive durable submissions/jobs/attempts, leased local execution and fenced atomic catalog/job success preserve R1 identity and synchronous behavior. Full locked checks passed 557 offline and 124 real PostgreSQL cases; five live CLI outcomes and retained original R1 artifact verification passed. Actual 62 January BTCUSDT/ETHUSDT partitions published/read back 230,311,900 rows; fresh-key download/recheck reused all 62 exact versions, no failures, all attempts 1. Independent GPT-6 Astra review resolved all actionable findings and independently passed 76 new job tests plus original R1 focused tests; final catalog/source/artifact/job evidence review passed. Owned disposable container was verified and removed, original services unchanged/healthy, artifacts retained. No unresolved blocker. Peak memory was not measured; hosted CI was unrun at local closeout and its later actual results are recorded below. See [R2 contract](docs/r2-jobs.md) and [actual verification](docs/r2-verification.md). R1 historical evidence remains intact. At implementation closeout R2 remained uncommitted/unpushed under the initial request. The user subsequently authorized publication and hosted CI verification; those actual outcomes are recorded below. R3–R9 require later authorization.


### R2 publication and first hosted CI result (October 24, 2026)

Verified R2 was committed/pushed normally to origin/main as
`8bfff40e8b431e2382640fb25e66b2d648520588`, with exactly the 16 scoped source,
test/migration and documentation files; no market artifacts/data, dependencies or
deployment configuration were included. [Initial hosted CI run 40067420625](https://github.com/atharva-m/MarketLab/actions/runs/40067420625)
failed: Ubuntu quality failed Ruff formatting; Windows quality concluded cancelled
with the same formatting step failure recorded, and neither quality job reached
mypy/offline pytest. Linux integration passed all 124 PostgreSQL cases (25.92s),
API image build/startup, API smoke, healthy Redis and actual Redis outage checks,
and cleanup. The 557 hosted deselections are not offline passes.

The failure was an unformatted Python fenced example in docs/r2-jobs.md added
after the successful local full check. Subsequent documentation closeout checked
UTF-8/whitespace but omitted rerunning Ruff for that new code example. The example
has now been formatted with the locked formatter; repository-wide locked Ruff
lint and formatting pass (64 files). Runtime, dependencies and workflows are
unchanged. This first hosted run remains a failure; the subsequent passing replacement run is recorded below.


### R2 hosted CI recovery verified (October 24, 2026)

The reviewed formatting-only example fix and failure record were committed/pushed
as `d22523aaafc2182fc411c1615ad615e0be24c771`.
[Replacement CI run 40067854743](https://github.com/atharva-m/MarketLab/actions/runs/40067854743)
passed for that exact SHA: Ubuntu quality passed 557 offline tests (8.93s), Windows
quality passed 557 offline tests (12.48s), and Linux integration passed 124 real
PostgreSQL tests (25.44s). Ruff lint/format (64 files) and strict mypy (19 sources)
passed on both quality platforms. Integration also passed locked setup, Compose
validation, API image build/startup, API smoke, healthy Redis/outage checks and
cleanup. Only the failure-conditional Logs step was skipped, not a test step.
Exact run/job metadata and logs are retained under ignored artifacts/r2-ci/.

No unresolved R2 publication/CI blocker remains. The earlier failed/cancelled run
is retained as history. Historical 62-partition download/readback/recheck evidence
remains local, peak memory remains unmeasured, and no model/analytics claim follows
from CI. This closeout changes documentation only; no runtime, test, dependency,
lockfile, deployment or workflow changes were needed for CI recovery. R3-R9 remain
unauthorized and market artifacts/data remain excluded from Git.


### R3 local closeout (October 24, 2026)

COMPLETE under the approved [R3 contract](docs/r3-analytics.md). On-demand exact UTC
1m/5m bars, bounded DuckDB reads, additive GET /v1/bars, resilient Redis cache,
coalescing and bounded metrics are implemented. Summary-cache policy is fixture-
tested; research summaries remain R4. Existing R1/R2 source/identity/manifests,
publication/jobs/leases/fencing and legacy HTTP/CLI contracts remain preserved.
Dependencies/lockfile and deployment are unchanged; no migration was added.

Full locked checks passed 606 offline and 132 real PostgreSQL cases, zero skips,
Ruff lint/format (75 files) and strict mypy (24 sources). Independent GPT-6 Astra
review resolved all five actionable findings, independently passed 49 new offline/
eight new PostgreSQL and 149 retained R1/R2 cases, and independently audited final
canonical response/catalog/integrity evidence. Actual live acceptance passed
primed-response Redis outage/restart, application restart, real LRU eviction,
bounded oversized-value reads and focused legacy/durable historical compatibility.

All 62 retained January partitions reconciled 230,311,900 input records separately
at each interval: 89,280 one-minute and 17,856 five-minute bars, zero empty buckets.
All 124 daily canonical response hashes matched an independent streaming reference;
all 124 warm reads were HIT. Both symbols' five-day and midnight-crossing reads
matched reference slices. All 62 source manifest/artifact hashes remained unchanged.
Cold full verification can exceed the 60-second native DuckDB deadline; the largest
day's first 1m read plus warm repeat took 118.33 seconds including verification.
Recorded phase timings are not a complete-run benchmark; peak memory is unmeasured.

Ownership-checked cleanup removed all three owned disposable containers and left
original API/PostgreSQL/Redis IDs unchanged and healthy. Artifacts and snapshots
remain ignored. No unresolved R3 acceptance blocker remains. See [actual R3
verification](docs/r3-verification.md) for exact counts, review scope, resolved
execution issues, timings and limits. At this local closeout hosted R3 CI was
unrun and changes remained uncommitted/unpushed under the initial request. Later
October 24 publication/CI authorization is recorded above and below. R4-R9 remain
unauthorized; no market data/artifacts, credentials, environments or weights belong
in Git.


### R3 publication authorization (October 24, 2026)

After the verified local closeout above, the user authorized normal commit/push of
the scoped R3 changes, hosted CI verification, actual R3-only CI fixes and honest
outcome documentation/publication. Preserve the prescribed coder/reviewer workflow
for fixes. This changes publication authority only; R4-R9 remain unauthorized and
market archives/artifacts/data, credentials, environments and weights stay outside
Git. At that authorization update publication and hosted results were not yet
observed. Actual later results are recorded below and in
[R3 verification](docs/r3-verification.md).


### R3 publication and hosted CI verified (October 24, 2026)

Verified R3 was committed/pushed normally to origin/main as
`54f15d3c4312248f1ec8beda6bca805d4e37bb38` with exactly 15 scoped source/test/acceptance-script/
documentation files; no market data/artifacts, credentials, environments or weights.
[hosted CI run 40072552311](https://github.com/atharva-m/MarketLab/actions/runs/40072552311)
passed for this exact SHA: Ubuntu quality passed 606 offline tests (6.80 seconds),
Windows quality passed 606 offline tests (14.44 seconds), and Linux integration
passed 132 real PostgreSQL tests (26.78 seconds). Ruff lint/format (75 files) and
strict mypy (24 sources) passed on both quality platforms. Integration passed
Compose validation, API image build/startup, API smoke, healthy Redis/optional-
outage smoke and cleanup. No tests were skipped; only failure-conditional Logs.

No R3 CI failure/fix or unresolved publication blocker occurred. Hosted tests do
not repeat the local 230-million-row retained-month reconciliation or actual
R3 cached-bar outage/eviction harness; those remain distinct completed evidence.
Peak memory is unmeasured. This outcome follow-up is documentation only; no
runtime, dependency/lock, deployment or workflow change was needed. Exact hosted
metadata/logs remain ignored under artifacts/r3-ci/. R4-R9 remain unauthorized.

### R4 local closeout (October 24, 2026)

COMPLETE under the approved [R4 contract](docs/r4-research.md): strict typed
five-minute research, three deterministic workflows, separate durable research
schema/execution, immutable numerical publication, manual API/CLI and real summary
cache. Final locked checks passed 655 offline/152 real PostgreSQL cases, zero
skips. Independent source review resolved all five actionable findings; final
metadata-only replay-response correction was verified separately from the actual
month execution source snapshot.

An independent fresh scan reconciled all 62 retained partitions/230,311,900 trades
and 17,856 five-minute bars. Ten durable runs (five requests plus independent fresh
key repeats) succeeded in one attempt each and matched all 20 reference numerical
payload hashes. BTC/ETH cluster counts were 31/33. Real migration/fencing/process
crash/cache outage/eviction, Ollama-unavailable numerics, retained live contracts
and original R1 readback passed. All source artifacts remained unchanged; a final
snapshot preserves accepted run/catalog records before owned-resource cleanup.
Original service IDs/health were preserved and the three owned containers/image
removed. See [actual verification](docs/r4-verification.md) for exact evidence.

Recurring backwards PostgreSQL wall time was captured causing temporary immediate
claim ineligibility; affinity and quiescent diagnostics did not resolve it. Initial
failed suites remain recorded alongside the final passing suite; no retained
runtime/test eligibility or host clock was changed. This environment limitation
is still present. Peak memory is unmeasured; hosted R4 CI is unrun. All R4 changes
remain uncommitted/unpushed under the user's explicit instruction. R5-R9 require
separate authorization; no market artifacts/data, credentials, environments or
weights belong in Git.

### Authorized post-R4 clock follow-up: partial mitigation, unresolved (October 24, 2026)

The user authorized investigating/fixing the clock environment with prescribed
review, preservation and actual verification, no commit/push. [The report](docs/r4-clock.md)
retains before/failed partial evidence, Ubuntu timesyncd disable and PHC convergence,
actual job/lease and retained-suite passes, and unresolved smaller Docker initd
clock steps. No safe supported live control for that writer was identified; the
clock fix is incomplete.

An exploratory initd help command unexpectedly attempted VM initialization and
restarted original containers, violating uptime preservation. Stale host forwards
required standard API/PostgreSQL/Redis recovery restarts. Same original IDs/images/
volumes and healthy host endpoints were verified; uptime/cache continuity are not
claimed. Owned resources were cleaned. No manual rate reset or R1-R4 eligibility/
fencing change was applied. Historical R4 results and this incident remain intact;
R5-R9 remain unauthorized. Any later Docker/vendor maintenance needs a separate
reviewed operational plan.

### Authorized clock claim fix: application-layer workaround, issue persists (October 25, 2026)

**The backward-clock issue persists.** It was worked around at the application layer
(job claim logic) rather than fixed at the system level. Docker Desktop, WSL, the host
clock and time-sync configuration were not changed. The user approved fixing the job
code instead of the environment, with no commit/push.
The steps come from Docker Desktop /initd, which steps the shared WSL2 clock about
1-2ms backwards every ~30s (upstream docker/desktop-feedback#761, no setting to
disable it). Queued R2/R4 work is claimable from submission without a later
wall-clock comparison. ingest_day rechecks database time at most three times per
attempt before reporting a due retry as ineligible.

Retry backoff/lease expiry still use clock_timestamp(). Leases, heartbeats, the
three-attempt budget, fencing, publication, schema and dependencies are unchanged.
655 offline/158 real PostgreSQL cases, deterministic backward-step regressions and
real clock/lease acceptance passed on an owned disposable database. Original services
were untouched. Details: [clock fix](docs/r4-clock.md#root-cause-and-application-fix-october-25-2026).
R5-R9 remain unauthorized.

### R4 and clock-fix publication authorized (October 25, 2026)

The user explicitly authorized committing/pushing verified R4 and the application
clock fix, then checking hosted CI. Earlier no-commit/push instructions remain
historical; this approval does not authorize R5-R9 or market artifacts/data,
credentials, environments or weights in Git.

Fresh locked checks passed 655 offline/158 real PostgreSQL cases. Live acceptance
passed in 249.827s with 1,000 immediate claims per kind, concurrency/replay checks,
real 10s/30s retry gates, heartbeats, three real 60s lease-expiry cycles, stale-owner
rejection and no fourth attempt. Independent read-only review found no blocking
issue. The application works as intended with the known Docker clock discrepancy:
409,100,000 server clock samples over 90.021s still captured three backward steps,
largest 2.788ms. The owned test database was removed; original service IDs, start
times and health were unchanged. Evidence remains ignored under
artifacts/r4-clock/verify-20261025-2250dfb0-*. Hosted CI was pending at authorization;
the actual outcome follows and is recorded in [R4 verification](docs/r4-verification.md).

### R4 publication and hosted CI verified (October 25, 2026)

Verified R4 and its application clock fix were committed/pushed normally to
origin/main as 2c0dd0bbf8ebfcac9dd6a5cbd5255d288f383d0c. The push included the
existing R4 backup commit f600ccb7e1fc1487f88328c2826d72f956631e52. No market
artifacts/data, credentials, environments or weights were included.
[Hosted CI run 40167912094](https://github.com/atharva-m/MarketLab/actions/runs/40167912094)
passed all three jobs for that exact implementation revision.

Ubuntu quality passed 655 offline tests in 8.07s; Windows quality passed 655 in
14.35s. Linux integration passed 158 real PostgreSQL tests in 30.05s. Ruff
lint/format, strict mypy, Compose validation, image build/startup, API smoke,
optional Redis-outage checks and cleanup passed. No CI fix was needed and no
R4 publication/CI blocker remains.

Hosted smoke does not repeat the local all-62-partition numerical reconciliation,
real cache-eviction harness or dense Docker clock acceptance. Those records and
the known system-clock discrepancy remain intact. Exact hosted metadata/logs
remain ignored under artifacts/r4-ci/. R5-R9 remain unauthorized.

## R5 approval (October 25, 2026)

R5 APPROVED for implementation under [R5 contract](docs/r5-copilot.md), written
before code. User approved the detailed proposal, ROADMAP.md/AGENTS.md updates,
prescribed coder/reviewer workflow, full acceptance and honest actual outcome
documentation. NO COMMIT/PUSH. This supersedes historical R5 exclusions only
within the contract; R6-R9 remain unauthorized. Preserve completed R1-R4 and the
unresolved system clock discrepancy. Completion requires durable clarification,
atomic validated handoff, actual recovery/model evaluation and retained-month
numerical equivalence, independent review and owned cleanup. Estimated effort
40-60 hours, not measured velocity. Earlier status/authority statements above are
historical; this is the current execution authority.

## R5 local closeout (October 25, 2026)

COMPLETE under the approved [R5 contract](docs/r5-copilot.md), with source frozen,
independent read-only review and full actual acceptance; see
[R5 verification](docs/r5-verification.md). Durable strict interpretation/
clarification and fenced jobs, bounded local Ollama, atomic registration through
the same manual research service, additive API/CLI and provenance are implemented.
R1-R4 and week 1-9 contracts remain preserved. At local closeout no commit/push
or hosted CI had occurred; later publication authority below now governs.

Final locked checks passed 736 offline/174 real PostgreSQL cases, Ruff lint/format
and strict mypy (38 sources). Actual v3 evaluation passed the specified gates:
18/20 correct clear specs and zero unsafe submissions among 40 negative requests;
25 negatives produced expected clarification/refusal and 15 failed safely.
Earlier v1/v2 failures, including one unsafe queued v2 run never numerically
executed, and harness/source-drift/orchestration failures remain recorded. Do not
claim all 40 negatives were correctly clarified or refused.

All five retained-month scenarios completed through both copilot and manual
submission: 10/10 durable runs, all attempt 1, every canonical spec/results/summary
hash matched retained independent references across 62 January partitions/
230,311,900 trades. Actual elapsed 2473.395s (41.22min), dirty-source fingerprint
recorded. Real migration/crash/fencing/retry/lease, API/CLI/cache, unavailable-
model/manual-independence, cancellation/client cleanup, packaged startup and old
R4 readback/incompatible-code checks passed. Final cancellation logs demonstrate
model-load abortion, not active-token generation cancellation.

All 124 original dataset files and 53 protected files, including 40 old research
files, retained their hashes. Owned resources were removed after identity checks;
original service IDs/images/start times/restart counts/health and endpoints were
preserved. Peak memory remains unmeasured; the known Docker clock discrepancy
persists. No unresolved R5 acceptance blocker remains. R6-R9 remain unauthorized;
no market artifacts/data, credentials, environments or weights belong in Git.

## R5 publication authorized (October 25, 2026)

After completed local acceptance/review/cleanup, the user explicitly authorized
normal commit/push of verified R5, hosted CI verification, actual R5-only CI fixes
through the prescribed coder/reviewer workflow, and documentation/publication of
actual outcomes. This supersedes the earlier R5 publication restriction without
expanding feature scope. R6-R9 remain unauthorized. Archives/artifacts/data,
credentials, environments and weights remain excluded from Git.

Preserve the local dirty-source month/model evidence, quality limitations,
unsafe queued v2 failure, clock discrepancy, cancellation/load-abortion distinction
and all historical failures. Publication and hosted CI results were unobserved
at that authority update; record the exact revision and actual later outcomes in
[R5 verification](docs/r5-verification.md). Hosted checks do not replace the local
retained-month/model/operational acceptance.

## R5 publication and hosted CI verified (October 25, 2026)

Verified R5 was committed/pushed normally to origin/main as
19a136350e53418e46e99f739597e231628a8f55, containing exactly 23 scoped source,
test, migration, acceptance-tooling and documentation files. No market artifacts/
data, credentials, environments or weights were included.
[Hosted CI run 40177491693](https://github.com/atharva-m/MarketLab/actions/runs/40177491693)
passed all three jobs for that exact implementation revision. Ubuntu quality
passed 736 offline tests (7.03s), Windows quality passed 736 offline tests (18.77s),
and Linux integration passed 174 real PostgreSQL tests (35.42s). Ruff lint/format,
strict mypy, locked setup, Compose validation, image build/startup, API smoke,
initially healthy Redis, actual optional-Redis-outage smoke and cleanup passed.
No CI fix was needed; no R5 publication/CI blocker remains.

Hosted coverage does not repeat the separate local actual-model evaluation,
62-partition/month numerical reconciliation or real operational acceptance. Their
original dirty-source fingerprint, all failed v1/v2/harness/orchestration evidence,
model-quality limitations, unmeasured peak memory and known clock discrepancy
remain unchanged. Exact logs/metadata remain ignored under artifacts/r5-ci/.
See [R5 verification](docs/r5-verification.md). R6-R9 remain unauthorized.


## R6 local closeout (October 25, 2026)

COMPLETE under the approved [R6 contract](docs/r6-memos.md), with independent
read-only review, full local acceptance and ownership-checked cleanup; see
[actual verification](docs/r6-verification.md). Separate atomically enqueued memo
jobs, grounded three-paragraph supplements, immutable manifests, bounded API/CLI
and shared nonpreemptive copilot-priority inference are implemented. R1-R5 remain
preserved. At that local closeout no commit/push or hosted R6 CI had occurred;
later publication outcomes follow below. R7-R9 remain unauthorized.

Final locked checks passed 758 offline/189 real PostgreSQL cases, Ruff lint/format
and strict mypy. Actual constrained memo evaluation passed 20/20 with independent
factual/prose audit. R5 rerun passed 18/20 clear correct and zero unsafe among 40
negatives; 25 expected clarification/refusal and 15 safe failures remain distinct.
Eight published memos (five retained scenarios plus two fresh profiles and a fresh
cross-asset run) each used one attempt/one reserved call. All three fresh numerical
runs matched every retained independent result/summary hash, each numerical
attempt 1. Each profile read 31 partitions and cross-asset read all 62 January
partitions, covering the union of 230,311,900 trades.

Successful ordered BTC profile, ETH profile, then cross-asset acceptance took
2438.450s. Preserve the initial cold combined cross-asset preparation TimeoutError
at the existing 1800s bound before durable acceptance (1828.554s including earlier
memo work). The passing sequence uses existing workflows and normal caches; it
adds no cache-warmer, changes no timeout and is not a cold combined-month pass.
Ollama model inference used CUDA/all 33 layers; historical integrity/DuckDB/Decimal
preparation used CPU. Peak memory is unmeasured. Cooperating client admission and
local cancellation were measured; upstream active-token cancellation is not
established by closing a client.

Real durability/crash/fencing/budgets/priority, model/Redis failures, populated
migration/constraints, live API/CLI and packaged readback passed. All 229 original
protected file hashes and original service identities/start times/restart counts/
health were preserved. Owned resources were removed; eight native immutable memo
supplements and replayable database/source snapshots remain ignored evidence.
Execution used dirty source c9a6c63d1af3299060f211682614d2eba66c680345a3af31a02ab9e5d337aabc;
all initial test/harness/cold failures and the known system-clock discrepancy
remain explicit. No dependency/lock/deployment change or original-service restart
occurred. R6 completion itself does not authorize publication or R7-R9.

## R6/verifier publication and first hosted outcome (October 26, 2026)

Verified R6 plus its cold-verifier follow-up were committed/pushed as
`c94ef4bce9dd292730c8884761c787f799bac2d1`, containing 38 audited scoped files
without artifacts/data, archives, credentials, environments or weights.
[Hosted run 40269166877](https://github.com/atharva-m/MarketLab/actions/runs/40269166877)
failed: Ubuntu quality 810 offline passes/one worker-crash-test failure; Linux
integration 188 passes/one retry-test failure. Windows quality was canceled after
802 reported passes, which remain partial evidence rather than a complete pass.

Reviewed test-only corrections isolate the ingestion sleep mock from stdlib
subprocess polling and observe forced worker exit through its owned process
sentinel before asserting final reaping. Strict retry/broken-pool/SQL-fencing/
reaping/recreation assertions remain. Local validation passed 811 Windows offline,
40 PostgreSQL ingestion, 11 final Windows pool, 13 final Linux lifecycle and one
abnormal Linux launcher case. Original hosted signal state remains unknown; the
failed run and every diagnostic/helper failure remain recorded.

Runtime source hash remains f12cf32c7a33b8b81691cebd40195a6d174cc113be4aa35190dd209ccb3e1035;
the original R6/model/month and later 272.814s cold evidence are unchanged. Owned
fix resources were removed with original services preserved. Recovery commit and
replacement hosted results are pending; see [R6 verification](docs/r6-verification.md)
and the [optimization follow-up](docs/verifier-optimization.md). R7-R9 remain backlog.
