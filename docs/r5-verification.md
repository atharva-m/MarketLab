# R5 verification

**R5 COMPLETE** under the approved [contract](r5-copilot.md), October 25, 2026.
Implementation, independent read-only review, full locked checks, actual model
and retained-month acceptance, preservation and owned-resource cleanup passed.
At local closeout no commit/push or hosted CI had occurred. The user later
explicitly authorized verified R5 publication, hosted CI, actual R5-only fixes
and actual outcome documentation/publication; results are not yet observed.
R6-R9 remain unauthorized. The known Docker system clock discrepancy persists;
this work preserves the application workaround.

Final checks passed **736 offline / 174 real PostgreSQL cases**. Frozen v3 met
the model gates (**18/20 clear correct; zero unsafe submissions among 40 negative
cases**), with the quality limitations below. Ten actual durable runs over all
62 retained partitions matched every canonical spec and result/summary hash
against the retained independent reference. Earlier failures, including the v2
unsafe queued submission, are retained below rather than relabeled as passes.

## Implementation and focused checks observed

Contract and ROADMAP/AGENTS authority were written before source changes.
Implementation adds 0006_copilot, strict interpretation/clarification, fenced
jobs/attempts, two durable model-call reservations/three attempts, additive API/
CLI, bounded Ollama and atomic registration through the shared manual research
service. Model interpretation is untrusted. Independent conservative application
rules can complete fields explicitly grounded in text/context; schema validity
alone is not semantic correctness.

Focused locked checks observed during development:
- 81 new offline copilot tests passed, including forced bad-model candidates for
  threshold/interval/asset/negative-execution/boundary changes, ambiguity tracking,
  explicit corrections, evidence, strict transport/schema/bounds/cancellation.
- 16 real PostgreSQL copilot tests passed before the last semantic-only changes:
  concurrent keys/answers/claims, pinning/recovery, fencing/call/attempt budget,
  rollback/visibility, manual-key collision, same numerical hashes, real process
  kills before/during/after handoff, fresh/populated migration/FKs/constraints,
  cancellation during session-lock acquisition and near-expiry rollback.
  Forced lease expiry in focused tests is distinct from real-time acceptance.
- Scoped Ruff lint/format and strict mypy (38 sources) passed.

Initial PostgreSQL test invocation encountered Windows temporary-directory access
errors (2 tests passed, 11 setup errors). A fresh owned workspace --basetemp path
resolved the test-environment problem; later 13 then 16 focused cases passed.
An initial full check passed 706 offline cases but the retained migration HEAD/
table-inventory assertion still expected 0005_research. It was updated to exact
0006_copilot plus the four additive tables, preserving all legacy schema checks.
The second full locked checks passed 709 offline and 174 real PostgreSQL
cases, Ruff lint/format and strict mypy (38 sources). Log:
artifacts/r5/full-checks-second.log. Earlier failure remains history.

Actual preliminary Ollama smoke first failed malformed/truncated JSON when
repeated full-request evidence exhausted the bounded output. Prompt/schema now
require shortest evidence quotes; a subsequent warm smoke passed in 3.808s with
the installed model. This is a compatibility smoke, not the 60-prompt gate.
Malformed/truncated completion is a safe terminal outcome; bounded raw response,
hash, done_reason and model/settings provenance are retained when available.

## Actual operational durability

Real-time owned-resource acceptance passed in 242.925 seconds, including 100
immediate queued claims, actual 10s/30s retry gates, two heartbeats, three genuine
60-second expiry cycles, stale reserve/checkpoint/fail/finish rejection, no fourth
attempt and the two-call reservation budget. Its isolated schema was removed.
Evidence: artifacts/r5/r5-final-durability-live.json. Model/spec source changed
while this store-focused run was active; the durable store behavior was unchanged.
This is separate from focused tests that force lease/eligibility timestamps.

## Model evaluation development failures

An actual provisional 60-case evaluation was interrupted after eleven clear
cases: one submitted correctly, eight needs_clarification, two failed. The model
frequently emitted only workflow and called explicitly present fields missing;
some evidence repeated or truncated request text. This failed the clear-request
gate and was not counted as a successful evaluation. Evidence:
artifacts/r5/r5-eval-20261025-final-model-evaluation.json (marked provisional).
Prompt-v2 then required every intent/evidence slot (null only when absent) and
includes one worked complete seven-field extraction. Independent application
policies are unchanged. Four actual representative v2 smokes (clear-02/04/06/10)
all produced candidate intent exactly matching the independent expected values;
evidence: artifacts/r5/prompt-v2-representative-smoke.json. The completed failed v2 evaluation is recorded below.

A third full verification run passed 714 offline cases but failed four copilot
integration cases while the actual model evaluator was concurrently holding the
shared global inference lock in the same owned PostgreSQL database. Other 170
PostgreSQL cases passed. This was an orchestration failure: isolated table schemas
do not isolate the intentionally global inference lock. No implementation/test
waiver was applied; the exclusive final verification below subsequently passed. Evidence:
artifacts/r5/full-checks-third.log. Two additional offline tests now cover bounded
malformed/truncated response provenance and safe nonfinite-value rejection.

## Actual v2 gate failure and v3 correction

The complete v2 actual evaluation FAILED after 60 cases in 495.438 seconds:
15/20 clear canonical specs, 30/40 expected negative clarification/refusal
outcomes and ONE unsafe accepted research submission from ambiguous-10. The
request omitted metrics, but the model quoted `profile` from inside the workflow
identifier `market_profile`; application excerpt fallback incorrectly synthesized
the missing metric. The created numerical run was only queued in the owned
disposable acceptance database (62e973dc-ccb0-420b-bdb8-7b88a353c1f7). No numerical
worker executed it. This is an actual failed safety gate, not a mocked failure or
successful acceptance. Preserve all case responses and source fingerprint in
artifacts/r5/r5-eval-v2-20261025-model-evaluation.json.

The v3 correction removes excerpt-based field synthesis entirely, tracks whole-
turn conflicting values explicitly, uses exact lexical/phrase boundaries, masks
workflow-name spans from implicit metric selection and preserves field-negation
ambiguity. Evidence must reference the exact field/value and cannot support a
corrected value using an older quote. Request-specific schema enums constrain
evidence to actual field source spans/context markers; they do not synthesize
intent. The model still interprets raw text/context and all independent checks
remain. Context-only values require the context marker. Dynamic schema hashing
and deterministic field ordering are recorded. Final source has 81 focused
offline cases passing, including the actual unsafe reproduction and related
fragment/conflicting-boundary/negative-selection regressions. Independent review
and the actual final-model/retained-month evidence below subsequently passed.

## Final frozen-source checks observed

Final locked offline checks passed **736 offline tests** (10.75s), Ruff lint and
format and strict mypy (38 sources). Evidence:
artifacts/r5/final-offline-checks.log. Final exclusive real PostgreSQL verification
passed **174 tests** in 60.38s
(736 offline deselected), artifacts/r5/final-integration-checks.log. The earlier
shared-lock orchestration failure remains history; no full-suite failure is
unresolved.

All ten historical R4 completed runs were read using current code and every
results/summary hash matched the retained independent references. The check
explicitly forbade current execution provenance while reading old results and
proved an incompatible queued old fingerprint was refused. Its owned schema was
removed. Evidence: artifacts/r5/r5-final2-retained-results.json. The initial
harness stopped after four reads because raw cross-asset metric order was compared
rather than the canonical spec; only the harness comparison was corrected. Failed
initial evidence remains in r5-final-retained-results.json/log. No runtime contract
or numerical payload was changed to satisfy this check.

Frozen v3 packaged image built successfully under separate owned tag
marketlab:r5-20261025. Its owned API on loopback 58005 used only owned PostgreSQL/
Redis and unavailable-model endpoint 11436; /health/live, /health/ready,
/openapi.json and /trades returned 200 without Git checkout or a model.
Evidence: artifacts/r5/image-build.log, image-startup.json and owned-api.json.
No original image/service was replaced; final ownership-checked cleanup passed
as recorded below.

## Final actual model evaluation

Frozen v3 passed the specified gates on the unchanged 60-case corpus in
**411.152 seconds**: **18/20 clear requests produced the correct canonical spec**
(90%), and **0/40 ambiguous/invalid/adversarial requests submitted a run**.
Of those 40 negative cases, **25 produced the expected clarification/refusal**
and **15 failed safely** during model/schema/evidence validation. Do not describe
all 40 as successful clarification/refusal. Clear-13 and clear-20 failed safely
because the model omitted an explicitly requested metric and the independent
validator rejected the mismatch. No safety or quality gate was relaxed.

This measures the constrained model-plus-application pipeline, including
whole-turn semantic validation and explicit context, not unrestricted model
understanding. The corpus includes 16 text-only and four partial-context clear
requests. Evidence: artifacts/r5/r5-eval-v3-20261025-model-evaluation.json with
model/source/prompt/schema provenance, per-case responses/timings/attempts and
unchanged corpus hash. Model tag qwen3.5:4b-q8_0, installed digest
e15635ee93129fd2086640926e900c37589c5167561104abc3914bd6644c7e07,
Ollama 0.40.9, temperature zero, 8192 context and 2048 output bound.

Actual v3 representative clear-05/17/18/19 smokes passed. Both independent January
date/history holdouts passed exact intent, establishing that date extraction was
not merely copying the earlier example dates; evidence:
artifacts/r5/model-date-holdouts-v3.json. All five unchanged full-month scenario
texts also produced exact candidate intent in actual model smokes, including both
cluster metric sets; artifacts/r5/month-model-smoke-v3.json. The separate full durable month
execution/reconciliation also passed, as recorded below.

## Final live interface and retained compatibility acceptance

All five interface/compatibility groups and bounded metrics/source checks passed
on frozen v3. Evidence: artifacts/r5/r5-interfaces-final-interfaces-live.json.
Actual HTTP copilot creation reached needs_clarification; CLI answer/replay,
worker and inspection resumed it to one research run, then an R4 worker published
results and summary cache HIT was observed. Retained synthetic trade HTTP/CLI
transactionality, filters and streamed import limits passed; exact 12-bar reads
showed MISS/HIT; synchronous historical fixture reuse and inspection CLI passed.
The owned ephemeral API was removed. Earlier provisional interface attempts
remain separate evidence and are not represented as final passes.

The separately built packaged API was also removed after root verified its owned
identity. Its image and the owned PostgreSQL/Redis/Ollama resources were removed
during final cleanup below.

## Final live model failure isolation and cancellation

All six frozen-source live failure checks passed with the source guard intact:
artifacts/r5/r5-live-final-live-failures.json. Configuring the copilot to the
unavailable loopback endpoint 11436 produced three durable failed attempts and
no research handoff, while manual R4 numerical submission/execution/retrieval
succeeded. This is an actual unavailable-endpoint test; no original Ollama server
was stopped for it.

A deliberately lowered 0.5-second model deadline returned TimeoutError in
0.508151 seconds. Explicit client task cancellation returned in 0.0019696 seconds.
The final owned-server log records cancellation while LOAD/context work was
being aborted. It does **not** establish cancellation of active token generation.
An earlier provisional run showed token-generation cancellation/release/idle
slots, but that run failed its source-change guard and is separate historical
evidence. Neither loaded-model inventory nor the final load-abortion log proves
immediate generation termination. Default production inference remains 120s.
Client/connection cleanup is independently covered by cancellation/admission
regressions; these observations are separate from durable lease/crash checks.

## Actual full-month acceptance and execution identity

Frozen v3 full-month acceptance PASSED in **2473.395265 seconds (41.22 minutes)**.
It used all **62 retained January partitions / 230,311,900 trades**, with no new
downloads. Five copilot requests and five independent manual submissions produced
**10/10 succeeded durable numerical runs, all on attempt 1**. Every canonical
spec, complete numerical results payload/hash and summary payload/hash matched
the retained independent R4 reference and the paired manual run. All 62 source
hashes were unchanged and the source guard passed. Evidence:
artifacts/r5/r5-month-final-month.json (all five copilot provenance records and
ten numerical run inspections), plus the final audit snapshot
artifacts/r5/catalog-final.json saved before database removal.

| Scenario | Copilot/manual runs | Attempts per run | Spec/results/summary |
| --- | --- | --- | --- |
| BTC market_profile | 1 / 1 | 1 | Exact reference match |
| ETH market_profile | 1 / 1 | 1 | Exact reference match |
| BTC/ETH cross_asset | 1 / 1 | 1 | Exact reference match |
| BTC volatility_cluster | 1 / 1 | 1 | Exact reference match |
| ETH volatility_cluster | 1 / 1 | 1 | Exact reference match |

Profile/cross-asset evaluation is January 1 01:00 UTC through February 1
exclusive, with explicit January 1 history. Cluster evaluation begins January 2
01:00 UTC with the same history. The retained reference covers 17,856 five-minute
bars; this R5 comparison reuses the independently established R4 reference rather
than claiming a newly implemented independent numerical algorithm.

The final model evaluation and month acceptance used the same **dirty-source**
execution identity (not a clean implementation commit):
- Git HEAD: daae7623638046edda5ee08bbb3ab8c5485c650b, git_dirty=true.
- Python source SHA-256:
  60f215ec3ddc271f049f2d76a781e21873bebd7b9ca006adf3c33019fb8c076a.
- uv.lock SHA-256:
  730f02bec94d1f824a2cadf74f60cf5dcc246faa55004d5d060b92931224618f.
- Retained workflow-reference SHA-256:
  18569e053343621a2bf02b660a8bdc083b0c45b3ee071b5d26ce54e59419972a.

Hardware recorded by the harness is Windows-11-10.0.26300-SP0. Timing is actual
wall time for the acceptance harness, not an engineering-effort or pipeline
throughput benchmark. **Peak memory was not measured**. Model allocations and
loaded-model inventory are not substituted for measured peaks.

## Independent review, preservation and cleanup

Implementation used the prescribed coder gpt-6.1-sol/high and independent
read-only reviewer gpt-6-astra/medium. Actionable findings were resolved with
regressions, including atomic handoff/key collision, pre-dispatch model pinning,
physical inference-lock cleanup during cancellation, near-expiry fenced mutation
rollback, full-turn ambiguity/negation, strict lexical/evidence boundaries and the
actual missing-metric unsafe-submission reproduction. Final independent source
and acceptance-evidence review found no blocking issue.

Final preservation hashing passed for **124 original dataset files** (62
manifests plus 62 Parquet files) and **53 protected files**, including all 40 old
R4 research artifact files. Evidence: artifacts/r5/preservation-final.json. No
R1-R4 artifact was rewritten. New source intentionally changes execution
fingerprints; old completed results remain readable and incompatible queued code
remains rejected. Dependencies/lock/deployment and original services stayed intact.

Ownership-checked cleanup passed (artifacts/r5/cleanup.json): exactly the owned
PostgreSQL/Redis containers, owned image and owned Ollama process were removed;
the packaged API had been removed earlier after identity verification. No
original container or image was replaced. Original API/PostgreSQL/Redis IDs,
images, start times, restart counts and healthy states matched the initial
baseline. Post-cleanup verification passed
(artifacts/r5/post-cleanup-preservation.json): original API live/ready both 200,
Redis PONG, and owned ports 55438/56380/11435/58005 closed. The final audit database
snapshot was saved before owned PostgreSQL removal. Evidence/artifacts remain
ignored, not included in source control.

R5 is complete with the explicit model-quality and environment limitations above.
No unresolved R5 acceptance blocker remains. The backward-clock system issue is
not fixed and peak memory is unmeasured. At local closeout hosted CI was unrun
and commit/push was excluded. The later publication approval below supersedes
that restriction only for verified R5. R6-R9 remain unauthorized backlog;
historical failures and the R4 clock incident remain preserved.

## Publication authorization (October 25, 2026)

After completed local closeout the user explicitly authorized committing/pushing
verified R5, checking hosted CI, fixing actual R5-only CI failures through the
prescribed coder gpt-6.1-sol/high and independent read-only reviewer
gpt-6-astra/medium workflow, and documenting/publishing actual outcomes. This
supersedes the earlier R5 no-commit/push instruction for this publication scope
only. R6-R9 remain unauthorized. Archives/artifacts/data, credentials,
environments and weights must not be included in Git.

No publication or hosted CI result has been observed at this authorization
update. The published SHA and actual hosted run outcomes must be recorded after
they are observed; local 736/174 checks and month/model acceptance are not hosted
CI results. Preserve all local source hashes, dirty-source provenance, initial
failures and unsafe queued v2 result, model-quality limitations, clock history and
client-cancellation versus model-load-abortion distinction. Publication approval
does not reclassify earlier failed runs or expand feature scope.
