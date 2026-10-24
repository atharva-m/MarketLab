# Week 9 verification

Date: October 23, 2026. Environment: Windows, project `.venv`, Python 3.13.7,
unchanged locked dependencies. Implementation used the prescribed coder
(GPT-6.1 Sol, high), followed by independent read-only review
(GPT-6 Astra, medium).

## Implemented scope

`AGENTS.md` records the approved week 9 scope. The existing local CLI accepts
`--trade-id ID` for one request to the existing exact-ID endpoint, prints one
validated five-field object and preserves decimal/UTC string wire values. Lookup
accepts `--port` and rejects explicitly supplied browsing options, even defaults.
Invalid IDs fail before HTTP access. Returned IDs must match exactly. Missing IDs,
HTTP, connection, timeout and malformed-response failures emit safe stderr,
return nonzero and print no stdout. Existing browsing behavior is preserved.

README and `docs/week9-cli.md` document invocation, conflicts, output, errors and
browsing's partial-output/current-committed-data limitations. Shared request and
wire-value checks retain finite timeouts, IPv4 loopback, disabled redirects and
disabled environment proxies. API/OpenAPI, schema, indexes, dependencies,
lockfile, CI and deployment files are unchanged.

## Actual checks

The complete `.\scripts\check.ps1 -Integration` passed using `uv run --locked`:

- Ruff lint and formatting passed (45 Python files already formatted).
- Strict mypy passed for 13 source files.
- **456 offline tests passed**, zero skips; 76 integration tests deselected.
- **76 real PostgreSQL integration tests passed**, zero skips; 456 offline tests deselected.
- `git diff --check` passed.

The 47 new offline cases cover every browsing-option conflict, explicit defaults
and equals syntax; invalid ID validation before client creation; successful IDs
with mixed case, punctuation and maximum length; exact UTC/decimal wire strings;
one GET without query parameters; finite timeout and client protections; missing
or extra fields, incorrect wire types/values, malformed timestamps, non-UTC
responses, wrong or case-mismatched IDs and unexpected page envelopes; HTTP 404,
503, redirects, connection/timeouts, invalid JSON and media types. Failure cases
assert no stdout, safe stderr and a single request without retry. The existing
50 offline browsing tests continue to pass. An initial focused run passed all
97 offline CLI tests with five integration cases deselected.

Three new real PostgreSQL-backed API cases run the CLI parser, dispatch,
validation and output path with FastAPI TestClient and the private-schema
fixture. They cover successful punctuation-containing ID lookup, a case-mismatched
missing ID and a different missing ID. Existing combined-filter browsing and
imports-between-pages coverage also passed. TestClient supplies in-process HTTP;
the separate live TCP checks below use actual CLI subprocesses and sockets.

Integration used a separate `postgres:17-alpine` container named
`marketlab-w9-postgres-20261023`, full ID
`649fc6cf020148d28c191e99348a1294c133f07a2c98b267d61963fa09b5d7a0`,
ownership label `marketlab.week9.owner=week9-20261023`, random IPv4 loopback port
50490 and a tmpfs PostgreSQL data directory. Fresh migration reached `0002_trades`.
Private integration schemas were removed by the existing fixture.

## Focused live TCP verification

Six actual CLI subprocess invocations passed their expected outcomes against
an isolated host Uvicorn API and that real PostgreSQL container:

- Three successful exact lookups returned complete expected JSON, including
  distinct case-sensitive IDs, punctuation, trailing decimal zeros, maximum
  price/precision, minimal quantity and microsecond UTC timestamp strings.
- A missing case variant exited 1 with HTTP 404, empty stdout and safe stderr.
- Explicit `--limit 100` with lookup exited 2 before HTTP access.
- Default browsing returned the expected page envelope in PostgreSQL `C` ID
  order, with a final null cursor and exact wire strings.

The host API bound to random IPv4 loopback port 55992, used only the disposable
week 9 database and ignored artifact storage, and was terminated afterward.
Host harness/API/CLI processes all used project Python 3.13.7 and locked
libraries. This was host live TCP verification; no production-container build,
Compose smoke or hosted CI run was performed for week 9.

The first live TCP harness run used an incorrect expected punctuation ordering
for the browsing regression. Actual application output was correctly ordered;
the expected value was corrected to ascending ASCII ID order, and the harness
rerun passed all six cases. No application fix was needed. Final SQL recorded
revision `0002_trades`, three deliberately synthetic public rows and zero
`test_trades_*` schemas.

Ignored evidence under `artifacts/week9/` includes the complete regression log,
initial container inventory, disposable database inspection, TCP harness,
per-process arguments/exit/stdout/stderr records, API logs and SQL postcheck.
No credentials, evidence artifacts, environments or market data are committed.

## Execution limits and blockers

The first `apply_patch` call stalled and was interrupted before changing files;
bounded local file edits completed the implementation. Initial sandboxed uv
execution could not persist its interpreter cache. Escalated execution enabled
the recorded locked-environment checks. Docker Desktop was installed but stopped;
it was started normally, and sandbox Docker pipe denial was resolved by execution
escalation. These initial blockers were resolved; integration was not skipped.

Existing locked Starlette/FastAPI TestClient deprecation warnings about httpx and
its timeout argument remain. They did not fail tests; dependencies were not
changed to suppress them. Ollama generation, Redis outage checks and hosted CI
were not rerun for week 9. Earlier week 8 results remain historical evidence,
not week 9 passes. No model compatibility, cross-page snapshot or large-dataset
query-performance claim is made.

## Independent review and cleanup

Independent read-only review by GPT-6 Astra, medium found no actionable
findings in the implementation, tests or documentation. The reviewer independently
ran all 97 offline CLI cases successfully with project Python 3.13.7 and ran
`git diff --check`. The review examined regression logs supporting the 456 offline
and 76 integration passes, and all six recorded live TCP subprocess outcomes.
The reviewer did not rerun the full suite, PostgreSQL tests or TCP harness.

After review, cleanup verified the disposable container's full ID and ownership
label, inspected its mounts and confirmed there were no persistent volumes.
Only that owned container was removed; its PostgreSQL data used tmpfs. No new
image, network or named/anonymous volume needed removal. The owner-label
container inventory was empty after cleanup. `artifacts/week9/cleanup.json`
records the verified identity, mounts and before/after inventories. Ignored
evidence was preserved.

Existing MarketLab API/PostgreSQL/Redis IDs `b379ae85c220`, `8656644dd0ac`
and `bec035733c30` matched the initial inventory and all three remained healthy
after cleanup. Their data was not accessed or used for synthetic imports.
Final `git diff --check` passed. No application/test changes were made after
review, and no full-suite rerun was needed for this review/cleanup documentation
update.
