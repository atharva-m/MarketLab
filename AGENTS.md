# MarketLab contributor instructions

Current scope is week 2 only: trade schemas, deterministic synthetic fixtures, and parser/validation tests. Preserve the week 1 scaffold, environment, infrastructure, health endpoints, CI and Ollama compatibility smoke test. Keep trade parsing in memory with synthetic test inputs. Do not implement ingestion, domain database tables, jobs, analytical queries, caching behavior, frontend, copilot or memos yet.

Use the coder (gpt-6.1-sol, high) for implementation, then reviewer (gpt-6-astra, medium) for independent read-only review. The coder resolves actionable findings and runs relevant checks. The user explicitly authorizes this delegation workflow. Preserve explicit later user model overrides.

Use Python 3.13 and the project .venv with locked dependencies. Never commit credentials, environments, market data, artifacts or model weights. Document external blockers honestly; do not report skipped integration or model tests as passed. Local agent configuration does not change an already-running chat's model.
