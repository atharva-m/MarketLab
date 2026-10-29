# V2 compatibility and preservation matrix

This is the Phase 1 design, not a migration or a runtime acceptance result.
[Contract](phase-1-contract.md) is normative; observed source/evidence status is
in [verification](phase-1-verification.md). No old files, records, or historical
failures are rewritten by this milestone.

Current scope is Binance spot only under the October 28, 2026 documentation
amendment. The [prior exact documents](history/pre-binance-20261028/README.md)
remain historical; their review is not a review of this amendment.

## Persisted and public compatibility

| Surface | Existing contract | Generalized behavior | Preservation/transition gate |
| --- | --- | --- | --- |
| Synthetic trades | Existing independent five-field trade model/global ID, imports/listing/filter/pagination/CLI | Unchanged; not an analytical import path | Full legacy API/CLI and DB preservation |
| Dataset v1 | R1 schema/transform/lock identity, Binance numeric IDs, immutable January artifacts | Read through legacy reader and instrument mapping | All original bytes/hash/manifest/catalog identity exact |
| Dataset v2 | Not implemented | New tables, schema, manifest, semantic hash, generalized Binance transform and Binance-origin canonical import | Never overwrite/relabel v1 artifacts; exact per-version readback |
| Binance original ingest | Original signatures, symbols/month, synchronous shape | Legacy route retains old semantics; new v2 commands generalize | Existing consumers receive unchanged old payloads/IDs |
| Legacy ingestion jobs | Original source modes, request keys, CHECKs, attempts/fences | Legacy-compatible worker only; new workers do not claim indiscriminately | No old key rehash, owner reset, budget refund, or source substitution |
| V2 ingestion jobs | Not implemented | New contract/tables and instrument/day expansion ≤62 | Same key canonical replay; conflicting reuse 409; fenced publication |
| Fixtures/inline clients | Explicit caller-owned resume dependencies | Remain local legacy paths, not generic distributed tasks | Generic workers cannot steal fixture/client-bound work |
| Legacy bars | bars-v1, numeric ID tie order, exact decimals, 1m/5m bounds | Same API/body/errors; mapped v1 artifacts remain supported | Exact original bar JSON/hash and ordering |
| V2 bars | Not implemented | Binance instrument identity and numeric ID comparator; units pinned | Equal legacy-compatible inputs yield equal numerical values; envelopes may differ |
| Research v1 spec/result | research-spec-v1/research-numerics-v1, pinned source/lock execution | Completed reads use retained reader; execution requires exact compatible fingerprint | Never recalculate old identity with v2 fields |
| Research v2 | Not implemented | Instrument IDs, same workflows/formulas, new schema/numerics envelope | Legacy-equivalence projection compares all values/nulls/counts/bounds; no false byte-hash equivalence |
| Queued research | Exact captured execution identity | Compatible old worker may resume; incompatible new worker rejects/skips | Status/history retained, no conversion/reset; explicit fresh submission to rerun |
| Copilot v1 | prompt-v4 adoption, interpretation-v1, durable revisions/evidence | Completed requests readable; exact compatible source needed for queued execution | Old ambiguous/failure outcomes retained; no silent prompt/model upgrade |
| Copilot v2 | Not implemented | New prompt/schema/context snapshot and same manual handoff service | Provenance pinned, safe clarification/refusal, no model-selected versions |
| Memo v1 | facts/draft/renderer v1, independent result and claim safety | Completed artifact read without model/Git checkout; legacy fact rules | Three original paragraphs/hash unchanged; numerical reads independent |
| Memo v2 | Not implemented | Pinned instrument units and versioned fact/renderer identity | Old terminal memo never reset/replaced; new schema for new work |
| Cache | Contract/version/parameters determine validated entries | Namespace additionally binds v2 instrument/schema/numerical identity | No shared stale result across schema/instrument/version; Redis remains optional |
| Local storage | Safe relative roots; atomic rename; corruption detection | Remains default backend; registered legacy references supported | Copy/move procedure changes location mapping only after exact verification |
| Object storage | Not implemented | Registered immutable generation+SHA references, verified local cache | No ETag/hash assumption, unregistered objects undiscoverable, no overwrite |
| Auth/local origins | Loopback workspace protection; no customer account system | Local mode retained; customer mode requires OIDC/roles for old and new routes | Success payload compatibility does not imply unauthenticated remote exposure |
| UI | Catalog largely metadata-based; forms/validators fixed | Capability-driven controls and explicit pins | No examples/historical screenshots misrepresented as current capability |
| Binance scope | Legacy analytical data is Binance spot | Venue fixed to `binance`; reject other venues/derivatives and opaque trade IDs; canonical files carry Binance-origin evidence | No relabeling non-Binance data or weakening original contracts |
| Operational history | R1–R9 failures, uptime/clock/model/cache/cancellation limits | Retained verbatim as history | New passes append evidence, never erase failed invocation identities |

## Contract dispatch rules

1. Persist protocol version with each submission, execution fingerprint, and
   artifact. API version selects a parser; do not infer a version from field names.
2. Keep legacy canonicalization, hash computation, and validators available for
   old contracts. Registry adaptation happens after verification and does not
   alter the legacy spec or artifact bytes.
3. New v2 durable tables prevent old workers from claiming generalized tasks.
   New workers advertise exact supported execution identities and claim only those
   identities; broad support for a schema name alone is insufficient.
4. Compatible old builds may resume eligible old work within persisted budgets.
   An incompatible task remains inspectable with a safe incompatibility reason;
   execution rejection does not mutate it into new work or imply completion.
5. Terminal failed/cancelled/succeeded work is immutable. New research/import
   requests use new keys and explicit selections; memo regeneration of the same
   terminal job is excluded.
6. Read paths need registered artifact integrity and a compatible reader, not
   current model availability or the source checkout used at execution. New
   execution must capture honest source/lock/model/protocol provenance.

## Database and artifact transition

Phase 2 forward migration adds registry and versioned ingestion/catalog tables;
Phase 3 adds versioned research tables; Phase 5 adds versioned interpretation/memo
records; Phases 6–8 add storage/worker/access metadata. Exact Alembic revision IDs
follow the then-current head and are assigned in each approved phase contract,
never by editing or reusing existing migration IDs. Each future pre-code schema
supplement must specify concrete columns, FKs, CHECKs, indexes, and transaction
invariants against this design before its implementation.

The registry seeds only verified legacy instrument mapping. Migration does not
parse/rebuild old Parquet, rewrite manifests, backfill model outputs, reset queued
jobs, or expand old CHECKs. Legacy catalogs are exposed through a union reader;
cross-contract selections require exact semantic compatibility and one explicit
daily version per instrument. Missing mapping fails closed.

Before any write, rehearse a fresh and populated forward upgrade with a backup
and source fingerprint, then compare legacy rows/constraints and all protected
hashes. After generalized writes, old binaries are limited to their old surface;
there is no destructive downgrade path. Preserve v2 storage and tables even when
v2 intake is disabled. Restore only a verified coordinated DB+object backup to a
separate owned environment. Original running services are not rollout targets.

## Model and schema identity decisions

Initial model remains `qwen3.5:9b-q4_K_M`, pinned digest
`56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90`.
Copilot keeps temperature 0/context 8192/num_predict=-1/think=false and native
120s, 32 KiB, input/admission/call budgets. Memo keeps 2048 prediction budget and
bounded claim rendering. Generalized prompt/schema/fact/renderer identifiers are
new v2 identities, not reassignments of old version labels. Any required tuning
or model change needs a scoped amendment and a newly frozen evaluation cohort.

## Evidence required before later operations

Refresh exact source overlay, protected-file inventory, original service
IDs/images/mounts/start/restart/health/endpoints, database dump identity, and owned
resource ledger before each phase's actual acceptance. Inspect ownership before
cleanup. Missing containers/listeners are not proof of cleanup or service
preservation. Historical hosted/local acceptance remains separate from new v2
results. Raw data, artifacts, archives, credentials, environments, weights, and
new generated media remain outside Git.
