# Week 8 verification

Date: October 23, 2026. Environment: Windows, project `.venv`, Python 3.13.7,
unchanged locked dependencies. Implementation used the requested coder
(GPT-6.1 Sol, high), followed by independent read-only review
(GPT-6 Astra, medium).

## Implemented scope

`AGENTS.md` records the approved week 8 scope. Run the local read-only CLI with
`python -m marketlab.trade_cli`. It accepts the existing listing filters with
hyphenated options, defaults to one page of 100 records and supports positive
`--max-pages N` traversal. It retains filters and changes only `after_id`.
`--port` supports the configurable local API port at IPv4 loopback; default 8000.

Each validated page prints its existing envelope as one stdout JSON line,
preserving decimal and UTC timestamp strings and the final resume cursor. The
client uses finite ten-second request-operation timeouts, stops at null cursor
or the cap, and rejects inconsistent/non-progressing pages. HTTP, connection,
timeout and malformed-response failures return safe stderr diagnostics and a
nonzero exit code. Documentation describes partial output on later failure,
resuming with filters and the existing current-committed-data pagination semantics.
README and `docs/week8-cli.md` document invocation, options, output and errors.
No API, OpenAPI, migration, index, dependency, lockfile, CI or deployment change.

## Actual checks

The complete `.\scripts\check.ps1 -Integration` passed with `uv run --locked`:

- Ruff lint and formatting passed (44 Python files already formatted).
- Strict mypy passed for 13 source files.
- **409 offline tests passed**, zero skips; 73 integration tests deselected.
- **73 real PostgreSQL integration tests passed**, zero skips; 409 offline tests deselected.
- `git diff --check` passed.

The 50 new offline cases cover retained filters and changing cursors, positive
timestamp-offset URL encoding, finite timeout settings, single-page defaults,
explicit page caps with preserved resume cursors, empty/partial/exactly full
terminal pages, untouched decimal/UTC strings, malformed CLI inputs and safe
argument diagnostics before client creation. Malformed responses cover missing
or extra fields, incorrect wire types, invalid decimals/IDs, non-UTC timestamps,
oversized pages, duplicate/reversed/before-boundary IDs, wrong symbol/time matches,
empty or short nonterminal pages and mismatched cursors. Failures after a valid
printed page cover connection, timeout, HTTP 503, redirect, invalid JSON, incorrect
media type and repeated IDs. They assert partial stdout, safe stderr and nonzero
exit status. A subprocess verifies the documented module invocation's `--help`.

Two new real PostgreSQL-backed API tests run the CLI's traversal using FastAPI
TestClient and the same CLI parser/validation/output path. They combine exact
symbol, both time bounds represented as equivalent offsets, a nonexistent ID
boundary and one-record pages, with ID order deliberately different from time
order. A second case commits an API import after the first printed page: the
new matching ID beyond the cursor appears, while a new ID before the cursor,
another symbol and rows outside inclusive/exclusive time boundaries are excluded.
Both verify final null cursor and exact UTC/decimal serialization. These are
commits between requests, not overlapping uncommitted transactions; existing
PostgreSQL regression tests retain overlapping-import coverage.

Integration used separate `postgres:17-alpine` container
`marketlab-w8-postgres-20261023`, full ID
`093f41b060e25c1ef62daf8226c1403ce4e9a68d9732ed8aad7d99ba491546c4`,
ownership label `marketlab.week8.owner=week8-20261023`, random loopback port 53733.
Fresh migration reached `0002_trades`. The existing fixture cloned the migrated
trade table into unique private schemas and removed them afterward. Post-suite
SQL confirmed revision `0002_trades`, zero `public.trades` rows and zero
`test_trades_*` schemas. Existing Compose containers were inventoried before
starting the disposable database and were not used for synthetic imports.

Initial sandbox access to Docker was denied and uv could not persist interpreter
cache files. Execution-tool escalation enabled all recorded checks. Initial
focused verification passed 50 offline and two integration cases. Formatting
corrected initial line-length issues; strict mypy required the argparse error
override to declare `Never`. The complete successful run above includes both fixes.
No functional test failure was observed.

The locked Starlette/FastAPI TestClient emits deprecation warnings about its
existing httpx support and passing timeout arguments. The tests passed; no
dependency change was introduced to suppress those warnings.

## Limits and review

Independent read-only review by GPT-6 Astra, medium found no actionable findings
in the CLI, tests or documentation. The reviewer independently reran all 50 new
CLI offline cases successfully with project Python 3.13.7 and ran
`git diff --check`. The review did not rerun PostgreSQL tests, the full regression
suite or live TCP checks.

After review, cleanup verified the disposable container's full ID and ownership
label and confirmed its single anonymous volume was attached only to that owned
container. Cleanup removed the container and its volume. Post-cleanup inventories
found no remaining owned container or anonymous volume. The original Compose API,
PostgreSQL and Redis IDs `b379ae85c220`, `8656644dd0ac` and `bec035733c30` matched
the initial inventory, and all three remained healthy. Final `git diff --check`
passed. No test rerun was needed for this review/cleanup documentation update.

## Additional live TCP verification

The user subsequently requested live TCP CLI checks. These completed on
October 23, 2026 with the prescribed coder workflow. No application or test changes
were needed. The 409 offline and 73 PostgreSQL integration totals above belong
to the earlier implementation run; those suites were not rerun for this
harness/documentation-only follow-up.

- Separate Compose project `marketlab-w8-tcp-20261023` used its own network,
  PostgreSQL/API named volumes, Redis anonymous volume and image
  `marketlab:week8-tcp-check`. Only its API was published, on random IPv4 loopback
  port 61607; its PostgreSQL and Redis ports were not published. Generated Compose
  configuration and an empty interpolation environment file stayed under ignored
  `artifacts/week8-tcp/`, preserving repository configuration and the original stack.
- Compose configuration passed, and the unchanged production Dockerfile built
  successfully with `uv sync --locked --no-dev`. A subsequent cached build repeated
  successfully and saved `build.log`. Runtime evidence confirmed Linux Python
  3.13.17, UID 10001 and the CLI's ten-second timeout. Host harness and actual CLI
  subprocesses used project `.venv` Python 3.13.7 and existing locked dependencies.
  Fresh Alembic migration reached `0002_trades`; all three services became healthy.
- **31 actual CLI subprocess invocations passed their expected outcomes**:
  21 directly targeted the isolated API, one used a controlled TCP forwarding proxy
  to the real API/PostgreSQL stack, one targeted an unused loopback port and eight
  targeted controlled TCP fault servers. Every invocation recorded arguments,
  exit status, stdout, stderr and duration in `results.json`; `summary.json`
  reconciles the counts. Expected failures are successful verification cases,
  not successful CLI traversals.
- The 21 direct-stack cases covered the default single page of 100 records,
  a two-page cap with the default size, maximum page size 500, combined exact
  symbol/time traversals at sizes 1/2/3/500, cap-and-resume, five excluded-record,
  nonexistent or terminal ID boundaries, empty symbol/time results, each one-sided
  time bound, real PostgreSQL outage, invalid CLI arguments during that outage,
  and recovery. Synthetic IDs include mixed case and punctuation, with ID order
  deliberately different from execution-time order. Every successful invocation
  compared complete envelopes, exact UTC timestamps and decimal strings against
  expected pages, including exactly full terminal pages with null cursors.
- An isolated loopback forwarding proxy fetched real API pages and committed a
  second real HTTP import after the first read completed, before returning that
  page to the CLI. The next CLI request saw the new matching ID beyond its cursor,
  while newly committed IDs before the cursor, for another symbol and outside the
  time interval were excluded. This was a real PostgreSQL traversal through a
  controlled TCP proxy, not a fabricated API response. Five recorded raw request
  paths prove unchanged limit/symbol/time filters, cursor progression and positive
  offset encoding as `%2B05%3A30`. This checks committed imports between page reads,
  not an overlapping uncommitted transaction or a cross-page snapshot.
- Stopping only isolated PostgreSQL produced HTTP 503 readiness and CLI exit 1
  with no stdout and `trade-cli: local API returned HTTP 503`. Invalid `--max-pages 0`
  still failed locally with exit 2 and no stdout. Restart restored HTTP 200
  readiness and exact combined-filter traversal of the committed data. An unused
  loopback port produced exit 1, empty stdout and a safe connection diagnostic.
- The eight controlled fault-server cases each returned one valid first page,
  then deliberately returned HTTP 503, malformed JSON, repeated IDs, a wrong symbol,
  a numeric decimal field, a redirect, a disconnected socket or a stalled response.
  These are protocol fault injection over real TCP; they do not describe faulty
  behavior observed from the application. Each actual CLI process exited 1,
  preserved exactly the first envelope, omitted the failing page and emitted safe
  stderr without injected secrets/SQL or tracebacks. Each server received exactly
  two requests with the expected next boundary. The stalled case failed after
  approximately 10.8 seconds, exercising the unchanged ten-second read timeout.
- Final SQL recorded revision `0002_trades`, 119 deliberately synthetic rows and
  zero `test_trades_*` schemas. Final logs contained no tracebacks, unhandled
  future/task warnings or unexpected error lines; PostgreSQL initialization's
  locale and local-authentication warnings were expected. Original Compose API,
  PostgreSQL and Redis IDs `b379ae85c220`, `8656644dd0ac` and `bec035733c30` matched
  the initial inventory and all remained healthy. Their data was not accessed.

Ignored evidence includes `prepare.py`, `verify.py`, `postcheck.py`, generated
Compose configuration, `build.log`, `runtime.txt`, `results.json`, `summary.json`,
raw proxy/fault request paths, stack logs/inventories and `postcheck.json`.

Independent read-only review by GPT-6 Astra, medium found no actionable findings.
The reviewer independently parsed and reconstructed all 31 expected outcomes,
checked exact output envelopes, cursors, filter retention/encoding, safe failures,
original service identities and the SQL/build/runtime evidence. The review did
not rerun CLI processes or the existing test suites.

After review, cleanup verified full container IDs and Compose project labels,
resource names, named-volume labels, exclusive anonymous-volume attachments,
network ownership/endpoints and the separate image tag. Cleanup removed only the
four isolated containers (including completed migration), project network, both
named volumes, Redis anonymous volume and `marketlab:week8-tcp-check` image tag.
`cleanup.json` records empty remaining resource inventories, image-tag removal
and original API/PostgreSQL/Redis IDs still matching and healthy. Ignored evidence
was preserved. Final `git diff --check` passed; no application/test changes or
additional full-suite run were needed for this evidence/documentation update.

## Remaining limits

Hosted Windows/Linux CI, Redis outage checks and installed Ollama generation
were not rerun in this follow-up. Optional Ollama intentionally used an unreachable
loopback address in the isolated stack and reported degraded readiness, so these
checks make no host-model compatibility claim. Earlier week 7 records remain
historical evidence for checks not repeated here. The unchanged Ollama smoke's
offline tests are included in the earlier 409 tests. There is no cross-page
snapshot or large-dataset query-performance guarantee.
