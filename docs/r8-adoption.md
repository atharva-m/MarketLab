# R8 production adoption and completion amendment

Approved October 27, 2026, before adoption code changes. The user explicitly authorized adopting the tested Qwen3.5 9B Q4_K_M interpreter with the latest one-line null-guard prompt and think=false in production code, then finishing remaining R8 acceptance through the prescribed coder gpt-6.1-sol/high and independent read-only reviewer gpt-6-astra/medium workflow. No commit or push. R9 remains unauthorized. This narrowly supersedes prior R8 prompt/model exclusions; all R1-R7 contracts, immutable artifacts and historical failures remain intact.

## Exact adoption

Set the default shared model to qwen3.5:9b-q4_K_M and its expected digest to `56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90`. Use the exact latest supplied system prompt plus only the approved null-guard line, including its leading/trailing newline, SHA-256 `b5b297d29febdcc29e0dde8e845b52bb46568e6843be6a8004ffa39a6c2596c7`. Version copilot provenance as copilot-prompt-v4 and record the exact prompt hash. Adopt the tested copilot decoding settings: temperature=0, num_ctx=8192, num_predict=-1 and think=false. The unlimited prediction-token option does not remove the existing native 120-second inference deadline, 32 KiB response bound, 6000-byte prompt/schema/input budget, one active inference admission, 10-second heartbeat, 60-second DB-time lease, three attempts/two reserved calls per revision, fencing or semantic validation.

The existing copilot_model setting is shared by API/CLI copilot and memo workers. Accordingly the default/pin adoption also selects 9B for memos. Preserve memo-prompt-v1, approved claims/renderer/grounding rules, think=false and its existing 2048-token prediction budget; do not change memo semantics or its prompt. Revalidate actual memo quality on 9B rather than reusing4B results. Existing explicit configuration overrides remain explicit; no automatic fallback, model download, dependency/lock/migration/analytics change or original-service restart is introduced. The already requested 9B weights are installed. Do not edit .env, .env.example, Compose or system settings.

## Implementation and identity

Before edits archive exact prior production model/config and relevant acceptance sources in ignored artifacts/r8-adoption-20261027/source-before. Update production copilot/model.py and Settings defaults, plus focused transport/default/prompt-provenance tests. Keep schemas, independent interpretation()/decide(), numerical preparation and all HTTP/CLI state semantics unchanged. Source fingerprint changes honestly; old queued incompatible source identities remain rejected, while old completed numerical/memo artifacts remain readable and immutable. Do not relabel old results with the new prompt/model/source identity.

Align acceptance tooling with the new pinned model and fresh resource/evidence profile; never overwrite artifacts/r8 or the experiment campaigns. Preserve exact old tooling sources/hashes. Correct the legacy clarification helper/test expectation rather than production answer validation: a proper sixth service-method payload with expected_revision=5 currently returns422 before the store, while a valid-shaped stale4 returns409. Require actual revision5 needs_clarification after five accepted answers, six completed interpretations/jobs, no revision6/seventh job/call, exact replay and conflicting/stale rejection without mutation, and truthful native statuses. No HTTP-route assertion is inferred from service-method testing. Do not silently count a terminal failed fifth revision as boundary success.

## Fresh acceptance fixed before calls

Use new ignored base artifacts/r8-adoption-20261027 and separately inventoried owned resources on PostgreSQL 55444, Redis 56386 and Ollama 11443. Root owns original-service/protected-hash snapshots, exact disposable resource creation, reviewed operations, database dumps and ownership-checked cleanup. Old R8 failed/incomplete evidence and current/old service identity intervals remain distinct. No original restart or Docker/WSL/initd/clock/GPU change is authorized.

Run TWO fresh complete actual production 9B copilot campaigns over unchanged r5_prompts.json: each requires at least 18/20 full-spec correct clear cases and ZERO unsafe handoffs among 40 negative cases. Preserve every case, expected/actual classification, targeted-question score, safe failures, attempts/calls and source/prompt/model identities. No corpus tuning, best-run selection, post-hoc threshold changes or optional replacement campaign. Run TWO fresh 20-summary9B memo campaigns: each at least 18/20 useful valid outputs and ZERO unsupported published claims, with independent audit of all 40 memos against pinned summaries/allowlisted claims. Safe generation failure is not success.

Run one fresh real durable four-case clarification campaign on the adopted production path, without the experimental model adapter/fingerprint extension. Complete valid answer must atomically hand off one exact spec/run; ambiguous/conflicting answers must not produce unsupported handoff. Require actual five-answer continuity with the native 422/409/no-mutation behavior described above; do not force/reset failed work. Run affected model priority, native 120-second timeout, cancellation/outage, durable recovery/call-budget/source-identity preservation checks. Repeat the installed9B inference benchmark: three verified cold calls and ten warm calls per copilot/memo workload (26 calls), with native timings, complete resource enrollment and honest client/upstream cancellation limitations.

Run a fresh cold all-62 workflow under the new runtime source: all 62 retained versions/230,311,900 trades and every manifest/physical/logical hash exact, retained independent result/summary hashes exact, attempt one, unique memo enqueue with zero calls before inference, exactly two compute permits and actual verifier readiness/drain. Whole submit/execute/readback remains below 1800s; preserve separate cleanup timing and uncontrolled OS-cache qualification. Repeat current-source retained five-scenario reads/live compatibility, packaged Linux and relevant migration/failure preservation.

Run full locked/offline and real PostgreSQL quality/tests, frontend locked installation/type/lint/components/build/browser checks, and actual isolated monitoring/normal CLI-worker visibility at the final reviewed source. Historical counts are baselines, not automatic new passes. Prior six deterministic 1M/10M pipelines and unchanged analytics/cache benchmarks remain versioned evidence for unchanged components; do not rerun them solely to manufacture a new source label. Repeat any specific gate if adoption or an actual finding affects its behavior. Clearly separate retained unaffected evidence from rerun evidence. No prior result substitutes for an affected mandatory gate.

## Completion and limitations

The experiments showed that the model can still return candidate with null required values; independent application validation is mandatory and is preserved. Do not claim the prompt alone enforces the invariant, unrestricted model understanding, native parallel qwen35 inference, or upstream generation cancellation based only on client cancellation. The historical 4B clarification failures, all interrupted experiments, legacy 409 expectation mismatch, prior browser/cache/cold/source distinctions and unresolved clock discrepancy remain readable.

R8 stays INCOMPLETE until every applicable mandatory gate is actually observed, independently reviewed, final protected hashes/resources/services are compared and exact owned cleanup is verified. Current-interval service preservation cannot restore uptime continuity across the earlier outage of unknown cause. Missing prerequisites or failed quality gates remain blockers; do not weaken scoring or silently change prompts/settings in response. Document actual outcomes/blockers/review/cleanup in the report, README, roadmap and contributor instructions. No commit/push, deployment of original services or R9 authority follows.

## Prospective single technical resource-validation repeat

Recorded before repeat calls on October 27, 2026, under the user's authority to
finish remaining R8 acceptance. The two original frozen adoption quality
campaigns remain fixed evidence. Each completed all 60 cases with 19/20 clear
correct and zero unsafe negative handoffs; the second campaign nevertheless
FAILED its mandatory CPU/process/container memory-coverage gate (512 complete
samples of 513). That failed invocation and every raw sample remain intact. Its
quality outcomes are valid observations, not a complete accepted resource pass.
Concurrent frontend/browser host load during part of that campaign is recorded;
the missing sample's cause is not established and is not described as fixed.

Authorize exactly ONE separately reviewed operational coverage repeat, prefix
`r8-9b-copilot-resource-repeat`, after independent review of this prospective plan.
Use identical production runtime source 66069d6a6238e214e9a6cda7b664dcce2445175bb5a729c5f38450699c8fbe53,
installed model/digest, exact prompt-v4 bytes/settings, unchanged 60-case corpus,
expected full specs, scoring, native timeouts and existing sampler implementation
and completeness threshold. Use fresh request keys. Do not backfill or replace
old samples, lower coverage requirements, extend timeouts, retune prompts/models,
change application behavior or choose the better quality score.

Run serially with no concurrent frontend/build/browser/test campaign or resource
control operation during measurement. Normal campaign instrumentation, read-only
sampler/monitoring observations and owned model/DB activity remain part of the
measured scope. This reduces avoidable concurrent host activity; it does not
establish or repair the unknown cause of the original missing sample.

Retain all third-run quality outcomes even if they differ. A new quality/safety
failure or incomplete mandatory coverage blocks acceptance; it is not discarded
because an earlier score was better. The repeat must meet the unchanged quality
and complete resource gates on its own. No further technical repeat is authorized
by this plan; another failure requires a new reviewed disposition before calls.
This necessary operational validation does not waive the original no-optional-
replacement/no-model-tuning rule, reclassify the failed second invocation as
passed, or create an unrestricted right to rerun until success. Original quality
scores and failed resource evidence remain explicitly separate from this repeat.


## Observed closeout (October 27, 2026)

R8 completed under this amendment and the prospectively reviewed technical
resource supplement. [Actual verification](r8-verification.md) records fixed
quality scores, the failed second resource invocation and unchanged technical
pass, both memo cohorts, production fifth-answer continuity, current full checks,
benchmarks, protected-file/service comparisons, dump and exact owned cleanup.
The prospective contracts above remain historical requirements, not rewritten
scoring. The earlier unknown-cause service-uptime gap and all model/clock/cache/
cancellation limitations remain explicit. No commit/push, original-service
rollout, hosted R8 pass or R9 authority follows.
