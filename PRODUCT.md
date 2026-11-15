# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

A quantitative researcher running MarketLab on their own machines to study Binance spot
trades. They ingest or import data, pin exact dataset versions, run descriptive analyses, read
exact results and charts, and sometimes ask a local copilot or read a generated memo. When
workers run on more than one host, the same person is also the operator who starts them and
checks which worker ran what. Reviewers mostly meet the product through the README demo.

## Product Purpose

MarketLab turns official Binance daily trade archives, and Binance-origin CSV or Parquet
files, into immutable, verified dataset versions and runs deterministic research over them:
market profiles, cross-asset comparisons and volatility clusters on five-minute bars. Success
means every figure on screen is exact, reproducible from pinned inputs, and easy to inspect and
trust, whichever worker or host produced it.

## Positioning

Every number is computed deterministically from explicitly pinned dataset versions and carries
its provenance and hashes. The local language model can only propose a validated research
specification or write a separate memo; it never produces or alters numerical results.
Execution is durable and attributable: each job records its attempts, and a job abandoned by
one worker is finished by another without changing the result. Everything runs on hardware and
storage the researcher owns.

## Operating Context

- Browser workspace at 127.0.0.1:5173 talking to a local API and PostgreSQL, with an optional
  Redis cache and optional Ollama serving a pinned qwen3.5:9b-q4_K_M model.
- The default is one machine with local storage. Optionally, artifacts live in the
  researcher's own versioned S3 bucket and workers run on several hosts and operating systems
  against one shared database.
- Queued work (ingestion, research, copilot, memos) is executed by bounded CLI workers that the
  researcher starts. The UI submits and inspects durable jobs; it never launches workers.
- Two surfaces share the shell. **Workspace** (`/v2`) covers any registered Binance spot
  instrument and date, with tabs Catalog, Research, Copilot, Ingestion, Import, Instruments and
  Workers. The sidebar pages Datasets, Ingestion, Jobs, Research and Copilot are a focused view
  of January 2025 BTC/USDT and ETH/USDT with a day-by-day activity matrix.

## Capabilities and Constraints

- Scope is Binance spot only. No other venues, derivatives or alternate data providers.
- Exact presentation: decimal strings and large integers are shown exactly (lossless parsing);
  null is not zero and keeps its reason and observation count; units are ratio, quote asset and
  base asset. Approximate numbers are allowed only for chart coordinates.
- Research uses explicit half-open UTC windows, a fixed 5-minute interval and separate history;
  versions are never selected implicitly ("latest"). A request pins at most 62 daily versions
  and at most two instruments.
- Charts cover at most 1,440 bars across 5 days per window; missing buckets stay visibly empty.
- Imports are hashed in the browser before upload and accept files up to 4 GiB.
- Submissions are replay-safe (saved operation key and body); reload never resubmits.
- Polling: active details every 2 s, backing off on failure, paused when hidden, stopped after
  30 min.
- Memos are exactly three plain-text paragraphs, labelled AI-generated, with descriptive
  limitations.
- Queued states show the exact worker command as a copyable hint; no ETA or invented progress.
- Execution visibility: every run, ingestion job, copilot revision and memo lists its attempts
  with host, worker, start, duration and outcome. The Workers tab lists registered workers with
  host, state, heartbeat, capabilities and the jobs they hold. Host names are operator labels.
  A heartbeat is an observation and never implies that a worker holds a job. On a single
  machine the registry is empty and attempts show no host.
- State is plain coloured text everywhere: green for done or healthy, yellow for waiting or in
  progress, red for failed, grey for neutral. No status pills, dots or icons.
- No authentication, public hosting, scheduling, remote worker control or trading features.

## Brand Commitments

- Name: MarketLab (confirmed).
- Binding visual brief from the owner: black background with white holographic/ASCII type and a
  minimalist, futuristic feel, drawing on x.ai, Coinbase, Linear and ascii-magic. Monospace for
  UI chrome and data with a sans face for prose; a slow animated holographic sheen confined to
  signature elements.
- Pages share one layout: a title row with actions, a summary strip of facts, then single-line
  tables. New pages follow it.
- The finished product contains no prototype, MVP or scaffolding language: no apologetic notes,
  internal milestone names or explanations a user would not want to read.

## Evidence on Hand

- Real data: 62 verified January 2025 BTC/USDT and ETH/USDT partitions holding 230,311,900
  trades, plus verified daily versions for other dates and instruments from official archives
  and CSV/Parquet imports.
- A recorded run across two hosts on different operating systems: a worker claimed a run and
  was killed, its lease expired, and a worker on the other host finished it. Both hosts read
  back the same result.
- README demo GIF of that run (docs/assets/marketlab-workspace-demo.gif), the earlier
  single-machine GIF (docs/assets/marketlab-demo.gif) and the recording pipeline in demo/.
- No customers, testimonials, benchmarks or pricing exist; none may be invented.

## Product Principles

1. Exact over approximate: show the authoritative value, never a rounded stand-in.
2. Explicit over implicit: pinned versions, stated windows, visible provenance.
3. Numbers stand without the model: generated text is supplemental and labelled.
4. Owned end to end: data stays on the researcher's machines and storage; every external
   dependency is optional.
5. Attributable execution: who ran what, when and with what outcome is always on record.
6. Finished, not provisional: every word on screen is something a user wants to read.

## Accessibility & Inclusion

WCAG AA contrast for every text tier, full keyboard operation with visible focus, labelled
controls, and a prefers-reduced-motion path that keeps all content. State is never conveyed by
colour alone: the coloured text always names the state.
