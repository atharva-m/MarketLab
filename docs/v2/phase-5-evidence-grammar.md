# Phase 5 amendment 004: request-specific evidence grammar

Status: independent pre-code review PASSED on November 2, 2026, exact revision003
packet SHA256 33f46de8ab8f6d93f1df3e126def9ab7b02a1643bc44d737bf760602e0d38bc7.
The retained passed-review receipt SHA256 is
ef74b8d5c85c0a35504e64aac42e0f03b21d5ea5543b060d25f2b88f94a6d7a8.
This normative authority record precedes prescribed implementation and independent
read-only review. It supersedes the evidence generation prompt/grammar and only
the explicitly scoped lexical rule in the [original contract](phase-5-copilot-memos.md)
and [amendment 003](phase-5-evidence-priority.md). All other contract gates and
historical records remain intact; actual outcomes belong in
[verification](phase-5-verification.md). Exact proposal/proof files remain under
ignored artifacts/v2-phase5-20261102/grammar-feasibility-003/. Revisions001/002
remain byte-exact historical evidence. No inference or operational release follows.

## Evidence failure and scope

Prompt-v5's first actual development probe supplied seven correct intent values
but cited context:true for every field although its literal context was empty.
It failed closed. Preserve all twelve historical requests, eleven permanently
spent calls, the queued unexecuted v4 handoff
f2797192-3ed7-4946-82c4-6beeacadb860 and twenty original queued memo jobs, with their
separate immutable audit/helper/test/plan/result histories. No historical upgrade,
replay, reset, refund, deletion or handoff execution follows.

Replace only the new-request evidence generation grammar and generic copilot
prompt, plus the separately identified narrow lexical correction below. Keep
copilot-interpretation-v2 wire shape, intent/outcome/reason/null generation,
independent interpretation parser and decide() code unchanged. The lexical
correction changes semantically_covered's handling of one redundant phrase;
therefore this is not a claim that every validator byte/semantic is unchanged.
All other evidence, conflict, unsupported, selection, coverage, UTC, warm-up and
atomic handoff validation remains unchanged. No evidence/value repair, model
answer rewriting, deterministic candidate substitution or unrestricted fallback.

## Exact grammar algorithm

`prototype.py` is the executable prospective definition; `schemas.json` retains
every measured per-request schema. Start with the existing model_schema result,
remove only its now-unused generic `$defs.proof`, and replace each evidence
field's `$ref` with `{enum:[null,...exact proof objects...]}`. All other grammar
members remain byte-equivalent under canonical serialization. No sibling type or
object constraints are relied on for enum literals. The independent parser and
decide() still validate the native result, including evidence-to-intent equality.

For every actual turn, preserve its zero-based index and original text. Normalize
actual structured context through existing supplied(). A field's context object
is possible only when that named field is actually supplied. Selection and other
metadata never create context proof. Text candidate spans come only from existing
workflow_mentions, selected-alias boundary matches, interval matches, labelled
date matches using the exact existing role/boundary syntax, and metric_mentions.
Dates use the actual matched UTC timestamp as a quote and the existing UTC proof
rule; do not invent a timestamp, label or timezone.

For instruments and metrics, enumerate contiguous windows between actual mention
boundaries within 160 characters. Validate each exact substring at its known
source span: require0<=first<last<=len(text), text[first:last]==quote, and neither
adjacent source character may match [A-Za-z0-9_]. This directly proves the same
existing ASCII-boundary substring condition at that location without re-searching
the entire original text per candidate. Then apply existing extract/UTC value
rules to the bounded quote only. A multi-value proof must prove
the complete proposed list; singleton proofs cannot justify a larger list. Never
concatenate spans or synthesize a joined quote. Keep original case and characters.

Within each (turn, field, distinct proven value), retain one canonical witness:
actual matching named context first; otherwise shortest valid exact quote, then
earliest source position. Keep every distinct proven value and every turn; do not
prune alternatives based on expected fixtures, latest-turn preference or desired
outcomes. This canonical witness policy removes equivalent citation spellings,
not semantic alternatives. No field/value from expected specs enters the builder.
Null is always allowed; a field with no proof gets enum [null]. Intent remains
generic and uncoupled to these enumerations; incorrect choices still fail closed.

Span enumeration never considers all arbitrary substrings. With the fixed <=160
character window and finite mention families, sorting costs O(m log m) for m
mention spans; enumeration costs O(m) times the fixed160-character/family constant.
Every candidate source check is bounded by160 characters plus its two adjacent
characters, and extract/UTC revalidation sees only that bounded quote. No candidate
validation re-searches the full turn text; the test-only independent proven helper
retains that full search only when no known span is passed. The actual grammar
builder always passes a known span. The prototype avoids suffix-list slicing.
These are candidate sorting/enumeration bounds; existing mention-helper and
independent full-turn validator internals are reused as-is, without a new claim
about their own overall complexity.
Full text remains <=8192 UTF-8 bytes per turn and at
most six turns. As an inexpensive equivalent lower-bound guard, reject when
canonical content alone already exceeds6000 before constructing a schema; this
cannot admit or reject a request differently from total content+schema+prompt.
Do not impose a new candidate cap or truncate alternatives to fit. Exact total
budget rejection still follows schema construction for all remaining requests.

## Separately scoped lexical correction

Pure checks found exactly two of twenty unchanged clear literals,
clear-comparison-1 and clear-comparison-3, contain `cross_asset comparison`.
The current full-turn semantically_covered rejects the redundant noun comparison
as unknown, so even a perfect seven-value interpretation yields meaning
clarification. All five positive development literals already pass that validator;
the two defects cap this clear subset at18/20, with no threshold change proposed.

The exact prospective correction, only at the beginning of semantically_covered
before generic name stripping, is:

    remaining = re.sub(
        r"(?<![A-Za-z0-9_])(cross_asset)\s+comparison(?![A-Za-z0-9_])",
        r"\1", text, flags=re.I,
    )

This recognizes a redundant noun only following the already explicit canonical
workflow token. It adds no workflow alias or general harmless word. Original text
is retained for workflow extraction, evidence, all other checks and receipts.
Do not globally strip comparison or unknown words. `lexical_prototype.py` checks
this in an isolated in-memory patch and restores it; no source file is modified.
Static candidate witnesses change18/20 to20/20. Eight negative checks cover
standalone comparison, comparable, foreign venue, negation, extra constraint,
conflicting workflow and word-prefix/suffix boundaries; all remain fail-closed.
This exact additional lexical scope requires independent pre-code approval.

## Prompt and serialization measurements

Use exact `proposed-prompt-v6.txt` UTF-8 bytes, including final newline:1552 bytes,
SHA256 f301f7d5fd3f5e1c1c436d0f5d4092570f093b0af0b9e8c4d9be01a5027d38c3.
It is generic, with no fixture-specific symbol/date/expected response or example.
It replaces the prompt as a whole so the grammar fits without increasing limits.

`serialized-budgets.json` reconstructs every retained original content and verifies
all115 accepted input hashes:75 copilot (including both six-prefix clarification
transcripts) and40 memo. Maximum4926/6000 bytes, unchanged intake no-call rejection
records, and the original cumulative oversized answer still rejects at7273 bytes.
Both full five-answer sequences are3653,3754,3841,3918,4041,4229 bytes. The same
eight development content hashes from the actual full freeze are3933–4227 bytes.
The original literal cohorts/expectations, counts, distribution and thresholds
remain unchanged. Original actual-bind and actual v5 full-freeze SHA256s are pinned
and verified by the prototype. Memo content/prompt/schema hashes remain exact.

`pure-checks.json` establishes493 valid enumerated non-null source proof objects,
28 complete positive witness outputs representable, all eight development static
outcomes and all clarification prefix outcomes. These hand-constructed witnesses
only test grammar representability and independent rules. They are not model
responses and provide no development or scored acceptance credit. Its original
validator results explicitly retain the two lexical defects; lexical-checks.json
separately records the prospective correction. The maximum8192-byte dense text
span timing is recorded in this revision's pure-checks.json; it already exceeds
the content-only6000-byte lower bound. Timing is an observation, not a resource/
latency acceptance result. Revision002 also compares complete generated schemas
against revision001: all75 accepted copilot contexts and eight development contexts
retain exact allowed proof sets/schema bytes; all40 memo contexts remain unchanged.
Added direct-span negative and ASCII-versus-Unicode boundary cases exercise the
correction. Exact correction packet002 remains retained with manifest SHA256
dca3b0b3731fdaaf77ec772bbd1d0e551e74e99bfb5e5a22572dc054e7f7c1de.
Revision003 adds pure dense-span timing cases for content within6000 and for a
request within the actual6000 aggregate budget; exact bytes/timings are retained
in pure-checks.json:5384 text bytes/5994 content bytes/9224 aggregate bytes took
8.3054s and rejects;2160 text bytes/2770 content bytes/exact6000 aggregate bytes
took3.2904s and admits under the byte budget. Raw8192 text bytes took13.0690s in
the deliberate direct-builder stress; the prospective content-only guard would
reject it before schema construction. These are local observations, not native/worker resource or
model acceptance, and no candidate cap/truncation is introduced.

## Prospective identity and exact dispatch integration

Version new copilot prompt as copilot-prompt-v6, grammar as
copilot-evidence-grammar-v1, semantic coverage as copilot-semantic-coverage-v3, and
copilot execution schema as copilot-execution-v3. Add explicit grammar/semantic
version fields to the copilot execution identity. Leave memo prompt/renderer/wire
schema/settings unchanged; fresh source qualification still applies to memo work.
Do not relabel historical execution identities or approve old queued jobs.

Construct one canonical content and request-specific grammar from the exact frozen
snapshot/turns. prepare preflights these exact canonical bytes. Before reservation
and native dispatch, rebuild deterministically from the same immutable request,
verify the preflight input/schema/prompt SHA256s and current execution identity,
then send the same grammar object as native POST format. No static-schema hash,
placeholder schema or serialization differing from the counted/checkpointed bytes.
Native receipt must checkpoint that exact schema SHA256 and explicit versions.
Retained full bind/protocol artifacts must carry each request's schema/hash and
all clarification prefixes, rather than claiming a universal dynamic schema hash.

Keep pinned qwen3.5:9b-q4_K_M digest
56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90,
temperature0, think false, context8192, num_predict-1 copilot/2048memo, native120s,
response32KiB, aggregate6000 bytes, two nonrefundable calls/revision and five
answers, every durable/resource/admission limit and all dependency/lock versions.

## Mandatory gates after prospective approval

Prescribed coder gpt-6.1-sol/high implements only independently approved scope;
independent read-only gpt-6-astra/medium reviews final source. Parent owns async,
PostgreSQL, lifecycle/resource/ownership, access escalation and operational checks.
Meaningful offline/real PostgreSQL protocol tests must cover proof generation,
boundary/list/case/UTC/context failures, same schema through prepare/POST/checkpoint,
byte-budget/cumulative rejection, identities and narrow lexical negative cases.

The official Ollama structured-output documentation and upstream llama.cpp enum
converter/tests suggest enum-object support, but upstream is mutable and does not
prove installed Ollama0.40.9 support for this exact grammar. No extra diagnostic
model call is allowed. Only a separate independently reviewed fresh eight-probe
freeze/launch budget may establish pinned-engine behavior. Reuse the exact eight
literals, order, no answers/retries, one targeted invocation each, stop on first
failure, max eight calls, full normal freeze and final native drain/audit. Retain
all positive handoffs queued and do not execute numerical or memo work. Preserve
the union of twelve old requests/eleven calls and all original memo rows against
their separate immutable historical receipts, including v5's actual audit SHA256
fd71392e88c7e93bfd273b85d1401ba00498df353a7a109e0fb2b3dddc0beabf.

All eight actual probes must pass before separately reviewed new preparation and
full current source/input bindings. Then both full unchanged60-case copilot and
both20-case memo cohorts plus every other P5-01..05 gate remain mandatory. No old
passes can be supplemented or relabeled as acceptance. Owned backup/restore,
protection, final preservation and ownership-checked cleanup remain required.
No data/cache optimization, model upgrade, original-service change, commit/push,
Phase5 completion or later-phase authority follows.

Primary support references (not installed-engine proof):
https://docs.ollama.com/capabilities/structured-outputs
https://github.com/ggml-org/llama.cpp/blob/master/common/json-schema-to-grammar.cpp
https://github.com/ggml-org/llama.cpp/blob/master/tests/test-json-schema-to-grammar.cpp
