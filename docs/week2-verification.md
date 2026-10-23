# Week 2 verification

Date: October 23, 2026. Environment: Windows, project `.venv`, Python 3.13.7, existing
`uv.lock` dependencies. No dependency or lockfile changes were needed.

## Scope

- Added a strict frozen execution schema with exact decimals and UTC timestamps.
- Added pure JSON/CSV batch parsing with shared validation and duplicate-ID rejection.
- Added seeded synthetic fixtures, checked-in synthetic JSON/CSV examples, malformed-input
  tests and Hypothesis decimal/timezone round trips.
- Updated `AGENTS.md` for week 2 and documented the assumed canonical contract separately.

## Local checks

The existing `scripts/check.ps1` runs locked Ruff lint/format checks, strict mypy source
checks and the non-integration pytest suite. An initial sandbox run failed because uv could
not persist its interpreter cache; rerunning with the execution tool's escalation succeeded.

During focused testing, the smallest permitted decimal serialized with an exponent that the
parser rejected. Plain-decimal JSON serialization now preserves valid round trips. Tests
also cover precision boundaries, offsets, duplicate fields/IDs, missing/extra fields,
malformed CSV/JSON, fixture repeatability and independence from global random/decimal state.

Final `scripts/check.ps1` results: Ruff lint passed, Ruff formatting passed, strict mypy
passed for 10 source files, and **159 unit tests passed**, including **140 trade tests**.
The two PostgreSQL integration tests were deselected. No unit tests were skipped.

Independent Astra review identified one actionable issue: Python's timestamp decoder silently
normalizes malformed timezone offsets such as `+00:99`. Offset syntax now explicitly bounds
hours to 00–23 and minutes to 00–59. Regression tests cover malformed positive/negative offsets
through schema validation and both parsers. The final full checks above include this fix.

## Week 1 infrastructure regression verification

Follow-up verification on October 23, 2026 used the existing project environment and running
Compose services. No application, infrastructure, dependency or test changes were required.
Trade parsing remains in memory; no ingestion or domain database tables were added.

- `scripts/check.ps1 -Integration` passed: Ruff lint, formatting, strict mypy for 10 source
  files, **159 unit tests and 2 real PostgreSQL integration tests**. Neither invocation
  skipped any tests. Each invocation deselects the other test category by design.
- The integration invocation obtained the published PostgreSQL address and current database
  credentials from Compose configuration without printing credentials. The tests exercised
  real database readiness and confirmed revision `0001_baseline` with only `alembic_version`
  in the public schema. A read-only SQL check confirmed the same schema after deployment.
- An initial sandbox check attempt failed before lint because uv could not write its
  interpreter cache. The full check passed when rerun with execution-tool escalation.
- `scripts/bootstrap.ps1 -Start` passed locked dependency sync, Compose validation, a fresh
  image build, baseline migration, healthy startup and the existing API smoke script.
  The host environment uses Python 3.13.7; the rebuilt API image uses Python 3.13.17.
- `/health/live`, `/health/ready`, `/health/dependencies` and `/metrics` returned HTTP 200.
  PostgreSQL, storage, Redis and host Ollama all reported up. Request ID propagation,
  a matching structured JSON request log, and request-count/duration metrics were verified.
- Stopping Redis caused readiness to return HTTP 200 with `degraded`, Redis down and both
  required dependencies up. All four API smoke endpoints still passed during the outage.
  Redis was restarted in a `finally` block; readiness returned to `ready` with Redis up.
  Final Compose status showed API, PostgreSQL and Redis healthy and migration exited 0.
- Live Redis configuration remained 256 MiB, `allkeys-lru`, no snapshots and no append-only
  persistence. Existing PostgreSQL and storage volumes were preserved.
- The existing live Ollama smoke passed using already installed `qwen3.5:4b-q8_0` on
  Ollama 0.40.9. Its Q8_0 model returned Pydantic-valid schema output `status=ok`, `value=2`
  in 6.0097 seconds, including 5.6357 seconds loading. No model pull or runtime update ran.
  Digest: `e15635ee93129fd2086640926e900c37589c5167561104abc3914bd6644c7e07`.
  The local result is `artifacts/ollama-smoke-week2.json`, ignored by Git. The completion
  is one compatibility check, not a performance benchmark.

## Limits

Hosted CI and the Linux quality-test matrix were not run; the Linux Docker image was built
and exercised locally. The historical week 1 verification record is unchanged. Synthetic
symbols/precision bounds are documented assumptions, not a provider format or venue
specification. This follow-up verifies the existing empty baseline and health infrastructure;
it does not add database-backed trade persistence.
