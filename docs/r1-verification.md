# R1 verification

Date: October 23, 2026 (local America/New_York; source retrieval timestamp is UTC).
Environment: Windows, project .venv Python 3.13.7, unchanged locked dependencies.
Implementation used GPT-6.1 Sol, high, with a second prescribed coder owning tests.
Independent read-only GPT-6 Astra, medium review completed with no actionable findings.

## Implemented scope

R1 adds a separate synchronous Binance Spot historical ingestion library/CLI,
strict bounded archive validation, exact normalization, immutable Parquet/manifests
and additive PostgreSQL catalog migration `0003_dataset_versions`. Only BTCUSDT
January 1, 2025 is enabled. Existing synthetic trades/API/OpenAPI/CLI modules,
dependencies, lockfile and deployment configuration are unchanged. The existing
integration migration assertion was updated for the additive head/catalog table.
The contract, schema, finite limits and publication protocol were documented in
`docs/r1-datasets.md` before implementation/migration.

Catalog visibility follows artifact completion and verification. Same-version
concurrent submissions serialize registration; orphan final directories can be
verified/adopted after transaction rollback. Registered corruption is detected
without replacement. This is application-level immutable synchronous publication,
not distributed worker fencing or power-loss/cross-system atomicity.

## Final full regression checks

The final `.\scripts\check.ps1 -Integration` passed with `uv run --locked`:

- Ruff lint and formatting passed (57 Python files formatted).
- Strict mypy passed for 18 source files.
- **516 offline tests passed**, zero skips; 89 integration cases deselected.
- **89 real PostgreSQL integration tests passed**, zero skips; 516 offline cases deselected.
- Final `git diff --check` passed after review/cleanup documentation updates.

The 60 new offline cases cover exact historical precision, UTC microseconds,
numeric source-ID order, deterministic normalization, exact duplicates/conflicts,
malformed values/columns/encoding, empty inputs, ZIP traversal/symlink/extra members,
truncation, compressed/expanded/line/row/checksum limits, official URL/request
bounds, HTTP/redirect/timeout/disconnect failures, CLI validation and safe errors,
private exception redaction, output sink failure and engine disposal.

The 13 new real PostgreSQL cases cover additive catalog schema/constraints,
publication/readback, idempotency, changed-source immutable versions, concurrent
same-source submission, failures before registration and before catalog commit,
rollback/orphan retry, registered and orphan corruption, absent-version discovery,
independent historical/synthetic identity and ordinary long Windows storage paths.
The existing 456 offline and 76 PostgreSQL regression cases are included in the
full totals. No skipped integration cases are counted as passed.

Integration used separate `postgres:17-alpine` container
`marketlab-r1-postgres-20261023`, full ID
`29b67a7742064992f85f9b2db4d9dad80748f771b947ef87800e77d0d0612511`,
label `marketlab.r1.owner=r1-20261023`, random IPv4 loopback port 62949,
and tmpfs PostgreSQL data. Fresh migration reached `0003_dataset_versions`.
Tests cloned the actual migrated catalog/trades into private schemas; fixture
cleanup removed all of those schemas. Existing local services/data were not used.

## Actual historical acceptance run

Downloaded the official daily archive and checksum:
[BTCUSDT January 1, 2025 source archive](https://data.binance.vision/data/spot/daily/trades/BTCUSDT/BTCUSDT-trades-2025-01-01.zip),
[provider SHA-256 checksum](https://data.binance.vision/data/spot/daily/trades/BTCUSDT/BTCUSDT-trades-2025-01-01.zip.CHECKSUM).
Published checksum and computed archive SHA-256 matched:
`088c0401c491b235bf33ef5884633b2f080c9ba6afb8231f11fd71cea6e2d93c`.
Retrieval was `2026-10-24T03:06:38.619612Z` (October 23 locally).

| Measurement | Actual result |
| --- | --- |
| Downloaded ZIP bytes | 14,017,578 |
| Expanded CSV bytes | 115,531,356 |
| Raw/accepted records | 1,516,556 / 1,516,556 |
| Exact duplicates/conflicts | 0 / 0 |
| Parquet bytes | 19,781,735 |
| Observed first execution | 2025-01-01T00:00:00.010866Z |
| Observed last execution | 2025-01-01T23:59:59.658370Z |
| Initial normalization/publication seconds | 48.9147 |
| Verified same-input reuse seconds | 19.4371 |
| Catalog versions after both | 1 |
| Peak memory measurement | Not captured; no peak-memory claim |

The times are one local run, exclude the separate source download, and are not a
performance benchmark or guarantee. Each returned manifest was subsequently
inspected with full Parquet readback/schema/hash/count/logical reconciliation.
Observed execution bounds do not establish gap-free exchange coverage.

Dataset version:
`0754cbedca540cf372ee8d0f11b5ba9cf15f5b91536d33ec2187d02a2aec4d53`.
Parquet SHA-256:
`38dbcd020602f9097e96362b480f2fdf6194f3922aa4c921c38267f84bc7382d`.
Logical content SHA-256:
`02d17124c777d7565ca506053d1da3e9eb4630e4c8a122e2a26e233b9092c49b`.
The immutable manifest records baseline Git revision `55530ab...`, dirty state
true and the actual uv.lock hash; this implementation has not been committed.

## Actual command/API compatibility checks

Five actual project-Python CLI subprocess outcomes passed:

- New ingestion command downloaded/verified the official source again and reused
  the existing registered dataset identity.
- New inspect command returned the exact verified manifest.
- Legacy exact-ID trade lookup returned the expected case-sensitive JSON object.
- Legacy one-record combined symbol/time traversal returned A, Z, a in PostgreSQL
  C order, preserving decimal/UTC strings and final null cursor.
- Legacy missing-ID lookup exited 1, printed no stdout and emitted safe HTTP 404.

Legacy checks used a separate host Uvicorn process on IPv4 loopback port 55422,
pointing only to the disposable R1 database and ignored artifact storage. Real
HTTP health, transactional synthetic import and listing assertions also passed.
The host API was stopped afterward. SQL postcheck showed revision
`0003_dataset_versions`, one published historical version, three deliberate
synthetic legacy-smoke rows and zero private test schemas. Historical data never
entered the legacy `trades` table.

Ignored evidence under `artifacts/r1/` includes source archive/checksum,
source-provenance.json, real-manifest.json, real-results.json, tcp-results.json,
full-checks.log, harnesses, API logs, original/after container inventories,
postgres-inspect.json and postcheck.json. Archives/generated artifacts remain
ignored; no credentials, market data or environments are committed.

## Initial failures, resolved blockers and limits

Initial sandbox uv cache permissions and Docker pipe/TCP restrictions required
escalation for locked commands and isolated real-service checks. A delegated
escalated formatting invocation stalled and was interrupted; direct existing
.venv Ruff executables completed formatting. No dependencies changed.

An initial real verification attempt was interrupted while redundant full Python
Parquet conversion/readbacks were CPU-heavy. Verification now vector-casts time
and decimal columns, performs one complete pre-publication readback, and reuses
registered versions only after verifying them. The successful historical results
above belong to the completed rerun, not the interrupted prototype. Process
termination can leave staging files as documented; those are not catalog-visible.

Real execution exposed Windows fsync rejecting a read-only descriptor; writable
flush handles fixed it before any successful publication. Initial PostgreSQL tests
then exposed Arrow's internal decimal-to-string scientific notation for tiny
values and open Parquet handles retained on exception. Internal canonical decimal
formatting and explicit file closure fixed both; strict source decimal text rules
remain unchanged. A subsequent long-pytest-path run exposed Windows MAX_PATH
rename/inspection issues. Extended storage paths and test-local native artifact
inspection fixed those; the final full suite includes a normal long-path case.
Earlier failing runs are not claimed as passes.

Existing Starlette/FastAPI TestClient deprecation warnings remain non-failing.
The local implementation run did not include hosted CI, a production-container
build, Redis outage checks or Ollama generation. Subsequent hosted CI evidence
is recorded below; previous model results remain historical. There is no worker
lease/fencing, cache, analytical workflow or model integration claim. Source
availability did not block the real acceptance run. Memory peaks and hardware
benchmarks were not measured.

## Independent review and cleanup

Independent read-only review by GPT-6 Astra, medium found no actionable findings
in implementation, migration, tests or documentation. The reviewer independently
ran all 60 new offline tests and all 13 new real PostgreSQL integration tests
successfully. Review also verified the saved complete-suite logs, historical
manifest/results and five CLI subprocess records. The reviewer did not rerun
the full legacy regression suite, actual historical download or live TCP harness.
No application or test changes were needed after review.

Cleanup verified the disposable container's full ID and ownership label, inspected
mounts and confirmed its PostgreSQL data was tmpfs with zero persistent bind or
volume mounts. Only the owned container was removed. The owner-label container
inventory is empty afterward; no owned volume, network or image required removal
(the shared bridge and existing PostgreSQL image were reused). The ignored source
archive, published Parquet/manifests and evidence remain under artifacts/r1/.
`cleanup.json` records verified identity/mounts and original-service before/after
inventories. An initial cleanup guard treated Docker's empty tmpfs option string
as absence and aborted before deletion; checking key presence corrected that
guard without changing application code or removing any unintended resource.

Original MarketLab API/PostgreSQL/Redis IDs `b379ae85c220`, `8656644dd0ac` and
`bec035733c30` still match the initial inventory and all three remain healthy.
Their data was not accessed or used for historical/synthetic tests. No artifacts
or market data are tracked/staged. Final `git diff --check` passed. Changes after
review are documentation/status only, so no unnecessary full-suite rerun was made.
At implementation closeout R1 was complete and no commit/push had been requested or performed. The user subsequently authorized publication and hosted CI verification; actual outcomes will be recorded below. R2 remains unauthorized.


## Hosted CI after authorized commit and push

The user subsequently authorized committing/pushing the verified R1 work and
publishing this CI record. AGENTS.md and ROADMAP.md were updated to reflect that
authorization without changing the R1 feature scope. The 15 reviewed R1 source,
test, migration and documentation files were committed as
`75bb466c2bfa0a1e6ad0096335a54128fe7557ff`
(`Add verified R1 immutable historical dataset ingestion`) and pushed to
`origin/main` without force. No archive, data, artifact or credential was staged.
A staged whitespace check caught one trailing blank line in the new contract;
it was removed before commit. Application/test behavior was unchanged.

The [GitHub Actions CI run](https://github.com/atharva-m/MarketLab/actions/runs/40058652835)
completed successfully for that exact implementation commit. Authenticated run,
job and step metadata verified all three jobs:

- Ubuntu and Windows quality jobs passed Python 3.13 setup, locked dependency
  sync, Ruff lint/format, strict mypy and offline pytest.
- Linux integration passed locked setup, Compose configuration, production API
  image build, service startup, real PostgreSQL pytest, deployed API smoke,
  Redis initially-healthy and optional-outage checks, and cleanup.
- Only the failure-conditional Logs step was skipped, as expected for success;
  no test-suite step was skipped.

No CI fix was needed and no unresolved publication/CI blocker was observed.
Hosted pytest totals and full job logs were not retrieved; the earlier 516/89
counts remain local results, not claimed hosted counts. Hosted CI does not run
the real provider download or actual-model generation; the historical acceptance
run above remains local evidence and no additional model-compatibility claim is
made. Raw run/job/step metadata is retained under ignored artifacts/r1-ci/.
This follow-up changes documentation only; local application suites were not
rerun. Independent read-only review found no actionable findings and confirmed the
exact SHA/run, three successful jobs, listed steps, expected skip and evidence
limits. The reviewer did not rerun application/model checks. This reviewed record
is included in the requested follow-up documentation commit/push.
