# Use and operate MarketLab locally

## Data and research

Use catalog-registered explicit January 2025 BTCUSDT/ETHUSDT versions. Catalog
metadata does not imply a fresh full content rehash. Full inspection verifies
registered artifacts. A fresh ingestion key rechecks the official source; identical
source bytes reuse the immutable version, while changed bytes create another
version. Do not silently select the latest version or overwrite an older one.

Submit one of the three supported five-minute research workflows with explicit
history/evaluation bounds. Required warm-up is validated; the system does not
shorten the period or download earlier history. Numerical results use deterministic
versioned definitions, exact decimal strings and null reasons. They describe
assets rather than strategy performance. Chart coordinates are approximate; exact
tables/tooltips remain authoritative and missing bars stay missing.

Run the existing bounded ingestion/research/inference CLI workers as separate
operator invocations. Browser/API submission does not launch a worker. Queued
state does not prove that a worker is present or establish an ETA. Inspect durable
state, attempts and safe diagnostics; never reset terminal state to force a rerun.

## Replay and recovery

After a lost submission response, reuse the original operation key and exact body.
Do not invent a new key solely to discover whether work was accepted. Reusing a
key with a different canonical body conflicts. A deliberate new operation has a
new key and distinct durable identity. Browser storage is a convenience, not the
database authority.

Copilot interpretation must pass independent shape, semantic, catalog and history
validation before atomic research handoff. Clarification answers carry the current
revision and their own replay key. Refresh on stale conflict; do not overwrite a
newer revision. Five answer rounds remain the bound. Safe failed interpretation
is not successful clarification, and closing the browser does not cancel durable
work or prove upstream generation cancellation.

Claims, retries and crash recovery use the existing database-time protocol,
heartbeats, leases, fencing and attempt cap. Restart an owned bounded worker to
resume eligible work; let native retry/lease deadlines govern eligibility. The
known clock discrepancy persists; its queued-claim workaround does not change
lease or retry semantics. Incompatible queued source identities remain rejected;
old completed results remain readable.

## Optional dependencies and memo independence

Redis is optional for correctness. Observe HIT/MISS/BYPASS and bounded outage
behavior; do not interpret a cache outage as data corruption. Existing cache
limits and compute admission remain unchanged.

Ollama is optional for manual numerical work. The default is the exact pinned
qwen3.5:9b-q4_K_M digest. There is no automatic pull, fallback or model update.
The shared inference worker gives pending copilot requests priority over pending
memos without interrupting active work. Memos are immutable supplements; their
pending/ready/failed state is separate from numerical success. A failed memo does
not invalidate numerical results, and a ready memo is never regenerated in place.

## Monitoring and cleanup

Use the separate opt-in monitoring stack. API and CLI-worker registries are
distinct, and the durable collector supplies bounded read-only job aggregates.
Missing/stale telemetry means unavailable, not zero work. Resource snapshots are
not peak memory, and recorded process/container/GPU scopes must stay explicit.

Before experiments, inventory protected hashes and original service identities.
Use unique owned ports, resolved paths, labels, IDs and process birth/ancestry.
Retain the owned database dump and evidence before removing only exact owned
resources. Do not prune globally, restart originals, change the clock, run initd
experiments, or claim absent resources prove successful cleanup. Compare protected
hashes and current-interval original health/endpoints afterward.

Current operations belong in this guide and README. Historical approvals, failed
invocations and incidents remain in [Project history](project-history.md) and the
milestone verification reports. A later successful run does not erase an earlier
failure or restore continuity across the historical uptime gap.
