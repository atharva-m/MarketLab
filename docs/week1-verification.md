# Week 1 verification

## Scope

Python 3.13 scaffold, virtual environment and locked dependencies, health and metrics endpoints,
PostgreSQL baseline migration, Redis infrastructure, Docker Compose, CI and local Ollama smoke test.
No research, ingestion, cache-aside, frontend or copilot features are implemented.

## Agent configuration

Project-local `.codex/config.toml` declares coder and reviewer roles. Coder uses
`gpt-6.1-sol` with high reasoning; reviewer uses `gpt-6-astra` with medium reasoning.
Both role TOML files parsed successfully. Installed Codex CLI 0.163.0-alpha.11.2
reported configuration loaded when invoked with `--strict-config doctor --summary`.
The overall doctor command also reported unrelated sandbox/runtime state and network issues;
that command was not an overall environment-health pass. The requested models were explicitly
selected for the implementation and independent review agents in this session. Project role
configuration does not retroactively change an existing chat's model.

## Local quality checks

- Python library import smoke: all requested runtime and test libraries imported successfully.
- Ruff lint and format checks: passed.
- Strict mypy: passed (six source files at this checkpoint).
- Unit tests: 19 passed; two integration tests excluded from that unit-only invocation.
- Compose configuration validation: passed.
- Astra review: six actionable setup/error-handling findings resolved by Sol; final source review
  reported no remaining actionable findings.

Windows global pytest temporary-directory permissions prevented the first test attempt.
Use the check script, which creates a fresh workspace-local test directory. Failed or interrupted
sandbox attempts are not counted as passes. Git was initialized locally; no remote or push was made.

## Runtime verification

- Docker image build: passed; API, PostgreSQL and Redis running healthy; migration exited 0.
- Migration installed only the 0001_baseline Alembic bookkeeping table.
- Full check.ps1 -Integration: lint, formatting, typing, 19 unit tests and 2 real PostgreSQL tests passed.
- API smoke: /health/live, /health/ready, /health/dependencies and /metrics passed.
- Initial dependency check: PostgreSQL, storage, Redis and host Ollama all up.
- Redis outage: stopping the project Redis container produced HTTP 200 with degraded status;
  Redis was restored afterward.
- Host localhost resolution caused PostgreSQL connection hangs on this machine. Explicit
  127.0.0.1 defaults and bounded connection waits resolved this. Windows async PostgreSQL
  requires the documented SelectorEventLoop startup option.
- Ollama 0.40.9 ran qwen3.5:4b-q8_0 successfully; no runtime update was needed.
- Model digest: e15635ee93129fd2086640926e900c37589c5167561104abc3914bd6644c7e07.
- Model reports 4.2B parameters, Q8_0 quantization, 5,157,983,852 file bytes.
- JSON-schema output validated with Pydantic: status=ok, value=2.
- Cold completion: 49.8125 seconds, including 33.4988 seconds model loading.
- Ollama reported 5,112,709,774 loaded/VRAM bytes and an 8,192-token context.
- Host available RAM before/after: 7,364,239,360 / 6,303,547,392 bytes.
- Machine-readable local result: artifacts/ollama-smoke.json (ignored by Git).

These measurements are one compatibility check, not a throughput benchmark or copilot evaluation.
GitHub Actions configuration is included, but no hosted run occurred because no remote was created.


Final documented bootstrap.ps1 -Start completed successfully: locked sync, final image build, migrations, healthy containers and all four API smoke endpoints.
