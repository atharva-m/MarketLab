# Phase 5 prompt amendment 002: exact evidence source

Current amendment 003 (November 2, 2026): the v4 development's second probe
failed safely after its first passed. Independent pre-code review approved
[uniform prompt-v5 evidence priority](phase-5-evidence-priority.md), superseding
only the new-work prompt version. Keep all v4 source, results, requests/calls and
the unexecuted queued handoff unchanged. No preparation is released.

Status: independent pre-code review PASSED on November 2, 2026, exact packet
SHA256 `b9415e499a8b5cec28bf79cb484a7aa025c92fadb53aa21d48034de706791524`.
The prescribed coder is authorized to implement only the exact reviewed prompt/
version and fresh v4 development binding after this normative authority record.
Independent runtime/binding, actual freeze/input and launch review must precede
model dispatch. No implementation or new inference result is claimed at this entry.

This amendment supersedes the copilot prompt-version requirement in
[amendment 001](phase-5-prompt-correction.md) and the
[original contract](phase-5-copilot-memos.md) for newly created corrected-source work
only. Preserve all earlier source-qualified records and outcomes unchanged.
Actual outcomes belong in [verification](phase-5-verification.md). The exact
literal prompt and static proof files named below are retained under ignored
`artifacts/v2-phase5-20261102/copilot-prompt-amendment-002/`.

## Observed failed development and diagnosis

The first v3 unscored development invocation stopped on its first probe,
`dev-text-profile`. The result under
`artifacts/v2-phase5-20261102/prompt-v3-development/probes-run-01/` is functional
failed with lifecycle and owned sampled resources passed: 73.9386s, final active
zero, handles closed, no forced cleanup and unchanged source. The post-supervisor
SELECT-only audit records one committed intake, one attempt and one checkpointed
spent call, zero handoffs, and preserves the previous eight requests and twenty
memo jobs. Independent failed-outcome review is separate from these observations;
no eight-probe readiness or acceptance credit follows from a one-probe failure.

`diagnosis.json` binds the exact retained payload, result and post-drain audit.
The native user message contains `turns[0].context: {}` and all seven explicit
values in text. All seven values in the raw model candidate match the expected
intent. The model nevertheless cites `{turn:0, context:true}` for workflow and
instruments, with text quotes for the other five fields. Workflow availability
and selected-instrument mapping are not user-supplied turn context.

Reconstructing canonical user content matches the stored native payload and
input hash; system prompt, grammar and raw response hashes also match durable
receipts. Applying the unchanged independent `decide` to that exact retained
answer raises `invalid_request: Ungrounded context evidence`. The application
therefore safely retained execution_failed without handoff. No payload loss or
validator defect is evidenced; the mistake is the model's evidence-source choice.
The pinned completion was complete, `done_reason=stop`, input 4,805 bytes. Static
diagnosis did not call any model/service or repair the output.

Retain request `470a5b50-49e3-40d2-8104-c9bffe09a4ff`, its job/call/response and key
`p5.dev.v3.0404b0884f3f434d94423838ef04048c.dev-text-profile` unchanged. Raw response
SHA256 is `85638c524cefa175b7998807a34e5adadafc32af34cc06406e157783fdf952c4`.
Together with the failed original scored campaign, protected interpretation
history is now **nine requests and eight permanently spent calls**: eight v2
requests/seven calls from the original audited cohort plus this failed v3
request/one call. Keep the twenty old-source queued automatic memo jobs unspent.
No replay, reset, revision, source relabel, budget refund or deletion is permitted.

## Exact proposed correction and fixed boundaries

Implement only the exact UTF-8 bytes of `proposed-prompt-v4.txt` after pre-code
approval and normative authority recording. Version the copilot execution and
native receipt `copilot-prompt-v4`; leave memo prompt-v2, schemas, transport,
model/settings, independent validator, handoff and limits unchanged.

The correction says that context evidence is legal **only when that exact field
is present in `turns[n].context` and equals the proposed intent value**. Selection
and workflow lists do not count as turn context. Text-derived fields, including
workflow and instruments, require an exact quote from `turns[n].text`; an empty
turn context cannot support context evidence for any field. This applies to any
turn/field/instrument/date, without a fixture-specific example or expected answer.
Quotes must still independently establish the claimed meaning. Do not infer
evidence, substitute corrected evidence, salvage a candidate, expand permitted
context, or soften failed-grounding behavior in application code.

Other generic wording is compressed solely to retain the existing byte budget:
the seven-field requirement, explicit context/text merge, conflict/ambiguity,
selection/coverage distinction, exact UTC boundaries, no defaults, supported
workflows/metrics, missing/unsupported outcomes and metadata-instruction exclusion
remain. The proposed prompt is **2,118 UTF-8 bytes**, fifteen fewer than v3,
SHA256 `5508aa188e0386812e8bd8abaceebb5bf710936344e8209f1422f9f8dbbcef57`.

`serialized-budgets.json` performs actual pure canonical serialization with this
prompt and the unchanged grammar over retained verified contexts: all **115**
accepted preflights remain valid, maximum **5,924/6,000 bytes**. All eight unchanged
development requests serialize to **4,790–5,011 bytes**. Input and schema hashes
match the retained receipts. Existing five intake no-call rejections stay separate
from model accuracy; the cumulative over-budget answer still rejects. This proves
static byte applicability, not fresh dataset integrity, native accuracy or a new
source-qualified bind. Operational freeze/create and later full bind still use
normal complete checks; no cached-proof or snapshot-validation optimization.

Keep exact `qwen3.5:9b-q4_K_M` digest
`56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90`,
temperature 0, think false, context 8192, current output settings, 120-second native
deadline, 6,000-byte aggregate input, 32-KiB response, two nonrefundable calls per
revision, five answers and existing leases/attempts/resources/admission limits.
No dependency, numerical, model, threshold, workflow or other behavior change.

## Prospective development binding, with historical source preserved

Keep the v3 development helper, tests, plans, approvals, frozen contexts and failed
result byte-exact in their original directory. Its actual run pins helper SHA256
`d7fdf51ca51059e31d77c644ea05922a34410e4501c6f314e283fbddb31aea7d`
and test SHA256 `8e0ed5251817c905f491bc823c61e17763c7f1beb585d3fe08fef85755fe0dd5`;
current retained files match those hashes. They are historical code and are not
new-source launch authority.

After pre-code approval, use a minimal separately versioned binding in a fresh
`prompt-v4-development/` directory, reusing the existing reviewed helper's normal
services, full freeze, single-invocation guard, supervisor/sampler, failfast run
and post-drain audit. No new supervisor, generic framework, cache or model tool.
The only necessary binding deltas are prompt/version/schema labels and hashes,
fresh v4 operation keys/one-invocation slot, and cumulative protected history.
Preserve the exact eight literal request bodies/specs from amendment001's
`development-probes.json` (SHA256
`59c79f6635d09ecd8ce3e6d9e61173b36d0880324fdf8460b9ab9154bb5c8634`).
Do not retune a probe, change order/expectation, add an easier example or alter
the full scored fixture. Distinguish that literal-input packet from the newly
approved prompt packet when hash-pinning both.

The fresh plan must bind separate immutable baseline receipts for original v2
eight-request history and the actual failed v3 one-request history. The existing
SELECT audit can select their union of nine IDs, but preservation must compare
all request/revision/job/attempt/call/handoff rows against the source-qualified
eight-plus-one receipts, without editing/merging the historical files. Continue
comparing complete twenty-memo row images and their zero calls/attempts, plus
baseline equality throughout the invocation. Keep protected older work outside
the fresh run's eight-intake/eight-call budget. Retain a final parent SELECT audit
after positive native drain, even when create or worker responses are lost.

Independently review concrete code/tests, actual full-freeze inputs, current
source/protocol/config/ownership pins and launch before calls. Run exactly the
same eight probes sequentially with fresh keys, one create and one targeted
`work(1,id)` per probe, maximum eight intake/worker/call attempts, no answers,
retries, model/numerical/memo fallback or automatic reruns. Stop on first failed
expectation and retain all durable rows/calls. Positive handoffs remain queued
with no numerical execution. All eight must pass before expensive preparation is
released. Development is unscored and provides no P5-01..05 acceptance credit.

## Remaining source qualification and acceptance

All-source execution hashes change for copilot and memo again. Preserve the old
v2 queued intake/memo jobs and terminal v2/v3 failures under their original pins;
new workers must not upgrade/reset them. The existing forty genuine numerical
results and twelve actual data bindings remain retained. Refresh the prospective
reuse-preparation inputs/source qualification to v4, explicitly protecting the
additional failed v3 request/call against its actual post-drain audit. Reuse the
twenty verified job-free preexisting results through normal readers, leaving
explicit enqueue until scored memo evaluation; compute twenty genuinely fresh
current-source numerical successes for automatic memo enqueue. No such new
numerical operation has run yet; no expensive preparation needs to be repeated
solely because this proposal was authored.

Keep every literal cohort, expected spec/fact, P5-01..05 threshold and mandatory
gate unchanged. After eight reviewed development passes, reviewed preparation
and new full source-qualified bind, both fresh 60-case copilot cohorts and both
20-case memo cohorts remain required. Refresh browser and remaining gate plans
against actual final source/run IDs; old approvals are invalid for changed
source. Preserve all failed scored/development evidence and their independent
outcome classifications. Final owned backups/restores, protection and exact
cleanup remain mandatory. Phase 5 is incomplete; no commit/push, original-service
mutation, dependency/model/limit change, optimization or further phase follows.
