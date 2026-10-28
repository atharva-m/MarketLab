# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

A solo quantitative researcher running MarketLab on their own machine to study January 2025
Binance Spot BTCUSDT and ETHUSDT trades. They pin exact dataset versions, run descriptive
analyses, read exact results and charts, and sometimes ask a local copilot or read a generated
memo. Reviewers (for example hiring managers) mostly meet the product through the README demo.

## Product Purpose

MarketLab turns official daily trade archives into immutable, verified dataset versions and runs
deterministic research over them: market profiles, BTC/ETH cross-asset comparisons and
volatility clusters on five-minute bars. Success means every figure on screen is exact,
reproducible from pinned inputs, and easy to inspect and trust.

## Positioning

Every number is computed deterministically from explicitly pinned dataset versions and carries
its provenance and hashes. The local language model can only propose a validated research
specification or write a separate memo; it never produces or alters numerical results.
Everything runs locally and is owned by the researcher.

## Operating Context

- Local workstation (Windows/PowerShell in practice); browser workspace at 127.0.0.1:5173 talking
  to a local API, PostgreSQL, optional Redis cache and optional Ollama with a pinned
  qwen3.5:9b-q4_K_M model.
- Queued work (ingestion, research, copilot, memos) is executed by bounded CLI workers that the
  researcher starts. The UI submits and inspects durable jobs; it never launches workers.
- Data scope is fixed: 62 daily partitions (BTCUSDT and ETHUSDT, 2025-01-01 to 2025-01-31, UTC).

## Capabilities and Constraints

- Exact presentation: decimal strings and large integers are shown exactly (lossless parsing);
  null is not zero and keeps its reason and observation count; units are ratio, USDT and base
  asset. Approximate numbers are allowed only for chart coordinates.
- Research uses explicit half-open UTC windows, a fixed 5-minute interval and separate history;
  versions are never selected implicitly ("latest").
- Charts read /v1/bars only, at most 1,440 buckets per window; missing buckets stay visibly empty.
- Submissions are replay-safe (saved operation key and body); reload never resubmits.
- Polling: active details every 2 s, backing off on failure, paused when hidden, stopped after 30 min.
- Memos are exactly three plain-text paragraphs, labelled AI-generated, with descriptive limitations.
- Queued states show the exact worker command as a copyable hint (confirmed); no ETA or invented
  progress.
- No authentication, public hosting, scheduling or trading features.

## Brand Commitments

- Name: MarketLab (confirmed).
- Binding visual brief from the owner: black background with white holographic/ASCII type and a
  minimalist, futuristic feel, drawing on x.ai, Coinbase, Linear and ascii-magic. Monospace for
  UI chrome and data with a sans face for prose; a slow animated holographic sheen confined to
  signature elements.
- The finished product contains no prototype, MVP or scaffolding language: no apologetic notes,
  internal milestone names or explanations a user would not want to read.

## Evidence on Hand

- Real data: 62 verified partitions, 230,311,900 trades (artifacts/r2 catalog), recorded research
  runs, summaries, charts, memos and a copilot clarification from the README demo capture.
- README demo GIF (docs/assets/marketlab-demo.gif) and recording pipeline in demo/.
- No customers, testimonials, benchmarks or pricing exist; none may be invented.

## Product Principles

1. Exact over approximate: show the authoritative value, never a rounded stand-in.
2. Explicit over implicit: pinned versions, stated windows, visible provenance.
3. Numbers stand without the model: generated text is supplemental and labelled.
4. Local and owned: nothing leaves the machine; every external dependency is optional.
5. Finished, not provisional: every word on screen is something a user wants to read.

## Accessibility & Inclusion

WCAG AA contrast for every text tier, full keyboard operation with visible focus, labelled
controls, and a prefers-reduced-motion path that keeps all content.
