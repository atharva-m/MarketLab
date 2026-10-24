# MarketLab recovery roadmap

Status: R1 COMPLETE — implementation, local verification, independent review, cleanup and hosted CI passed; R2–R9 remain unauthorized backlog.
Prepared: October 23, 2026.
Baseline: `55530ab01e0bc6f522c3c1d3938a51ad48a42e24` on `main`.

## Authority and approval boundary

The user explicitly approved this roadmap and authorized R1 implementation, AGENTS.md updates, the prescribed coder/reviewer workflow, preservation of existing behavior, checks and honest results/blocker documentation. This approval covers R1 only. R2–R9 are not authorized for implementation. The initial implementation task did not request a commit/push. The user subsequently explicitly authorized committing/pushing verified R1 changes, checking hosted CI, documenting actual results/blockers and pushing the reviewed verification update.

After explicit approval, record the approval and approved milestone here, then update AGENTS.md to that milestone before implementation. Approval of the roadmap establishes direction; execute only the milestone the user authorizes. If an approval is ambiguous, clarify the execution scope. Keep later milestones as backlog.

Use this root document as the durable roadmap reference for future sessions. Preserve the historical week 1–9 documents and commits; those labels describe completed repository increments, not completion of the original 14-week schedule. Use R1–R9 below for recovery milestones. Do not relabel unrelated work as progress on the original plan.

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

Missing capabilities include historical downloads/checksums/provenance, immutable dataset publication, durable workers, analytical bars, application caching, research workflows, DSL/submission, copilot, memos and frontend. Installed DuckDB/PyArrow dependencies, a Redis container and an Ollama smoke are foundations, not implementations of those capabilities.

## Sequenced recovery milestones

The order below restores the original dependency chain. Each milestone ends with a reviewable working slice, independent review, verification evidence and an explicit completion/blocked status.

| ID | Deliverable and exit gate | Original plan coverage | Rough effort |
| --- | --- | --- | --- |
| R1 | One-day historical ingestion, checksum/provenance, immutable Parquet and minimal catalog; detailed contract below | Missing weeks 2–4 | 25–40 hours |
| R2 | PostgreSQL durable jobs and fenced publication; expand verified ingestion to both symbols for January 2025 | Weeks 3–5 | 25–40 hours |
| R3 | Deterministic 1m/5m bars, DuckDB reads and Redis cache-aside with outage/eviction tests | Week 6 and cache portion of week 8 | 25–40 hours |
| R4 | Versioned typed ResearchSpec, manual submission service, reproducible runs, three workflows and deterministic metrics/summary | Week 7 and prerequisites from weeks 9–10 | 40–60 hours |
| R5 | Durable copilot interpretation, clarification and automatic validated submission through the same service | Week 9 | 25–40 hours |
| R6 | Separate memo jobs, grounded three-paragraph output and immutable supplemental manifests | Week 10 | 20–35 hours |
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

## Contracts retained for later milestones

### R2: durable execution and scale-up

Use PostgreSQL `FOR UPDATE SKIP LOCKED`, 10-second heartbeats, 60-second leases, fencing tokens and three total attempts for transient failures. Enforce current ownership in the publication transaction; test stale workers, crashes and repeated execution without duplicate published results. Route R1 ingestion through this machinery without changing its source/normalization contracts. Expand to BTCUSDT and ETHUSDT January 2025 with explicit bounded jobs. Obtain pre-period warm-up history when required by later workflows; never silently truncate requested research periods.

### R3: analytics and caching

Define completed UTC bars, exact aggregation/rounding rules and 1m/5m intervals; missing bars remain missing, with no forward filling. Query published dataset versions via fixed templates and bound parameters. Cache immutable bar responses and completed numerical summaries only. Keys include cache schema, dataset/run identity and canonical parameter hash. Preserve the original TTLs (15 minutes bars, one hour summaries, ±10% jitter), 1 MiB value cap, 100 ms Redis timeouts, no automatic retries and a ten-second bypass after three failures. Coalesce identical reads per process and cap expensive uncached queries at two. Provide `X-Cache: HIT|MISS|BYPASS` and metrics; retain 256 MiB allkeys-lru/no persistence with container headroom. Test actual cached results during outage and eviction, beyond health probes.

### R4: deterministic research before natural language

Implement a versioned strict ResearchSpec with dataset version, allowlisted workflow/symbols/metrics, explicit timestamps, interval and typed parameters/predicates. No expression strings, arbitrary SQL/code/paths. Validate shape, units/meaning, coverage and warm-up. Manual submissions use one idempotent application service and pin dataset versions, parameters, code revision and lock hash.

Support market-profile, cross-asset and volatility-cluster workflows. The supplied original plan does not fully define market-profile or cross-asset outputs: approve their numerical contracts at R4 entry before implementation rather than inventing hidden requirements. For clusters, preserve trailing 12-bar return volatility, comparison with the previous 288 valid volatility observations' 90th percentile (excluding current), volume above twice the preceding 12-bar mean, and at least two contiguous qualifying bars. Specify remaining volatility estimator/quantile details explicitly. Missing bars break clusters; insufficient warm-up is a coverage error.

Produce deterministic summary.json here so it is available before memo generation: drawdown as minimum close/running-maximum-close minus one; unannualized five-minute simple-return mean/sample-standard-deviation Sharpe proxy; top three current-volume/previous-12-bar-mean spikes; aligned five-minute log-return Pearson correlation; coverage/counts/units/definition versions. Use null plus reason when undefined. Distinguish descriptive asset statistics from strategy performance. Test exact fixtures and boundaries.

### R5: inbound copilot

Implement the planned `/v1/copilot/requests` creation, retrieval and clarification flow as durable jobs, returning submitted/needs_clarification/unsupported/failed. Use schema-constrained Ollama output plus independent shape, semantic and availability validation. Only a complete validated spec reaches the same manual submission service; persist request-to-run mapping atomically to prevent duplicate runs. The model has no tools or database credentials. Volume versus VWAP, vague dates and undefined thresholds must trigger clarification, never silent reinterpretation. Start the evaluation corpus here; full acceptance is in R8.

### R6: outbound memo and inference lifecycle

Enqueue memo work separately in the numerical-publication transaction with unique run identity; numerical success is independent. Use host Ollama with `qwen3.5:4b-q8_0`, configurable local/container connectivity and an initial 8K context window; record the installed model digest and measured runtime behavior. One inference worker prioritizes copilot over pending memos without preemption; use 120-second inference timeout and at most one retry, initial temperature zero and recorded settings. Generate exactly three structured paragraphs grounded only in deterministic summaries. Resolve allowlisted numeric placeholders in application code, reject unknown placeholders/unsupported numeric literals, handle nulls, disable raw HTML and label generated content. Formatting does not prove qualitative truth.

Publish `research_memo_{run_id}.md` in the immutable run namespace using a separate supplemental manifest; retain summary/memo hashes, model tag/digest, Ollama version, prompt/schema versions, decoding settings and timestamp. Never mutate the numerical manifest or overwrite a published memo. Expose separate pending/running/ready/failed memo status and safe retry.

### R7–R9: UI, evaluation and evidence

Build React/TypeScript/Vite views for ingestion/catalog/jobs, manual research, copilot clarification/provenance, charts and memo status/content. Fetch numerical results separately from mutable memo status. Cover browser workflows with Playwright.

Maintain 60 copilot prompts: 20 clear, 20 ambiguous/invalid and 20 adversarial/unsupported. Require zero invalid/adversarial executions and at least 90% semantic correctness on clear prompts; record clarification accuracy and latency. Keep actual-model evaluation distinct from mocked CI. Evaluate memo grounding, three paragraphs, nulls, provenance, retries, immutable publication and unsupported causal/predictive claims.

Inject Ollama failures during interpretation/memos and verify manual submissions/results remain usable without duplicates. Benchmark 1M/10M-row pipelines, Redis cold/warm/unavailable behavior, model cold/warm latency, token throughput, measured peak memory and queue delay. Report hardware, inputs and limits; do not substitute before/after memory snapshots for peaks. Complete Prometheus/Grafana operational views without treating current metrics exposure as a deployed dashboard.

Finish with a fresh-clone local run, actual evidence, reproducible instructions and recorded final demo. Resume claims must reflect measured dataset size, cache improvement and semantic evaluation outcomes.

## Session handoff and change control

At the start of future work, read this file, AGENTS.md and the latest approved milestone contract/verification. Report any inconsistency before changing scope. Preserve historical verification rather than rewriting prior results. At each milestone close, record its commit, implemented scope, checks, independent review, blockers and next approval gate here or in linked milestone records. Completion requires delivered capabilities and evidence, not only green tests.

Current handoff: R1 implementation passed 516 offline and 89 real PostgreSQL tests, plus actual official one-day historical publication/readback/idempotent reuse (1,516,556 records) and five CLI subprocess compatibility outcomes. Independent GPT-6 Astra review found no actionable findings and independently passed all 60 new offline and 13 new PostgreSQL cases. Owned disposable resources were verified and removed; original services remain healthy. R1 is complete. See [R1 contract](docs/r1-datasets.md) and [actual verification](docs/r1-verification.md) for evidence, resolved execution blockers and limits. R2–R9 remain backlog requiring later authorization. The verified implementation was committed/pushed as `75bb466c2bfa0a1e6ad0096335a54128fe7557ff`; [hosted CI run 40058652835](https://github.com/atharva-m/MarketLab/actions/runs/40058652835) passed Ubuntu/Windows quality and Linux integration (including image build, PostgreSQL, API smoke and Redis outage checks). Hosted pytest counts were not retrieved; the counts above are local. The CI documentation follow-up independently passed read-only review with no actionable findings and is published with this roadmap record. R2 remains unauthorized.
