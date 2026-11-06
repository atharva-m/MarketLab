# Phase 6 storage operations

Use the [reviewed contract](phase-6-storage.md) for the storage and retention
rules and [verification](phase-6-verification.md) for observed results. Commands
in this runbook target a separately owned stack with its own PostgreSQL
database, data root and, when selected, private object namespace.

## Configure a namespace

The default `MARKETLAB_STORAGE_BACKEND=local` writes to
`MARKETLAB_STORAGE_PATH`. To make an optional S3-compatible namespace available,
set the following in the API and CLI worker environment.

| Setting | Value |
| --- | --- |
| `MARKETLAB_STORAGE_S3_ALIAS` | Stable operator name for this namespace, distinct from `local`. Default `s3`. |
| `MARKETLAB_STORAGE_S3_ENDPOINT` | Operator endpoint origin, without embedded credentials or URL parameters. Use TLS outside loopback. |
| `MARKETLAB_STORAGE_S3_REGION` | Provider signing region. Default `us-east-1`. |
| `MARKETLAB_STORAGE_S3_BUCKET` and `MARKETLAB_STORAGE_S3_PREFIX` | Dedicated private namespace and contained managed prefix. |
| `MARKETLAB_STORAGE_S3_ACCESS_KEY` and `MARKETLAB_STORAGE_S3_SECRET_KEY` | Scoped credentials supplied through protected environment or local secret injection. |
| `MARKETLAB_STORAGE_S3_SESSION_TOKEN` | Session token when required by the supplied credentials. |

Set `MARKETLAB_STORAGE_BACKEND` to the configured alias to write new packages
and staged generations there. Keep `local` selected to continue local writes
while reading registered remote copies. Credentials can rotate without changing
the namespace. Application reads fail closed if a registered alias, namespace,
version or digest does not match.

Enable versioning and private access. Require conditional creation for
PutObject and multipart completion, and allow the corresponding multipart
initiation and part operations. Permit exact-version HEAD/GET, credentialed
versioning checks and scoped writes to the managed prefix. Normal application
credentials cannot delete registered objects. Keep exact-version deletion and
multipart reconciliation permissions in a separate operator credential. Use a
provider that passes the actual Phase 6 capability checks. The AWS S3 policy
examples distinguish object creation from intermediate multipart operations.
[Conditional-write policy guidance](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html)

After backing up a quiescent owned stack, apply the forward schema migration
and bind the capacity root and optional namespace using the same settings
the service will use. Keep queued historical jobs bound to their original
execution identities.

```powershell
uv run --locked alembic upgrade 0012_v2_storage
uv run --locked python -m marketlab.dataset_cli v2 capacity-initialize
```

Initialization requires all application workers, upload streams and reader
materializations to drain. Close the process that owns the verified cache
before initialization. Do not point a second active stack at the same root or
bucket prefix.

If a process crashed while holding a materialization, use
`uv run --locked python -m marketlab.storage.operator reclaim-materialization
--reservation-id RESERVATION_ID` on the owned stack. The command requires the
persisted native process envelope and definite child drain before removing
the exact reservation directory. Live or uncertain ownership retains the
bytes and physical reservation.

## Move one retained package

Quiesce writers and keep both source and destination capacity available.
For each package, run `dry-run` with its catalog owner and ID and retain the
output. Owner names are `legacy_dataset`, `v2_dataset`, `legacy_research`,
`v2_research`, `legacy_memo`, `v2_memo`, `upload_generation`, and `cli_import`.
The commands below illustrate moving one v2 dataset to a configured `s3` alias.

```powershell
uv run --locked python -m marketlab.storage.operator dry-run v2_dataset DATASET_ID
uv run --locked python -m marketlab.storage.operator copy v2_dataset DATASET_ID --backend s3
uv run --locked python -m marketlab.storage.operator switch v2_dataset DATASET_ID --source-copy SOURCE_COPY_ID --target-copy TARGET_COPY_ID
```

Copy reserves and verifies the destination while the source remains active.
The receipt gives the two copy IDs and the destination members. Review the
receipt against the dry-run identity before switching. Switch re-verifies the
target bytes and atomically changes the selected complete copy. Run the normal
reader and compare its identity and output to the saved source read. To reverse
on the same bound namespace, use the same IDs with `reverse` in place of
`switch`. It verifies the retained source before changing the mapping.

Uncertain attempts remain charged. An unattached, verified generation with a
drained owner may be retired explicitly using `delete-unreferenced --object-id
OBJECT_ID` and the separate scoped operator credential. Retain the before/after
inventory. If deletion or the proof of absence is ambiguous, keep the charge
and leave the resource for reviewed reconciliation. An inactive package copy
is still referenced and is ineligible for this action.

## Back up and restore on isolated resources

1. Quiesce the source stack and drain all cache and scratch ownership. On the
   source, record the verified inventory from
   `uv run --locked python -m marketlab.storage.recovery backup-inventory`.
   Save the JSON as an operator receipt outside Git.
   The operator role needs permission to read `pg_control_system()`. The
   receipt binds the nonsecret PostgreSQL cluster identity and database OID.
2. Dump PostgreSQL and copy the inventoried local files to an independent
   backup. Export every listed remote member by its exact object key and
   version to the protected backup. Check lengths and SHA-256 values. The
   PostgreSQL dump retains write intents, reservations and failed-state
   evidence. Retain original partial uploads and their object namespace for
   operator reconciliation. A restored stack conservatively carries charges
   for unresolved original attempts. Capture the inventory again after the
   copies and compare it to the first while the source remains quiescent.
3. Restore the dump into a new owned PostgreSQL database and the local files
   into a different owned root. If the backup includes S3, provision a
   separate versioned namespace with a fresh alias never used in that
   database. Upload each exact exported member to a fresh key under that
   namespace. Record the provider's returned version ID and relative key in
   a JSON object indexed by the backup inventory's `object_id`. Each value is
   `{"key":"relative/managed/key","version":"provider-version"}`. For a
   local-only restore use an empty JSON object.
4. Point the environment at the isolated database, local root and new
   namespace. Run the restore binding command with the original receipt and
   destination version map. It verifies the restored ledger, exact local
   bytes and every destination generation before registering complete new
   copies and switching the corresponding active mappings in one transaction.
   It rebuilds the local inventory and requires ordinary readers to pass.
   It rejects the original source database even when supplied a different
   filesystem root.

```powershell
uv run --locked python -m marketlab.storage.recovery rebind-restore --owned-restore --backup BACKUP_INVENTORY_JSON --destinations DESTINATION_VERSIONS_JSON
```

Keep the source DB, files and object namespace intact. The restored database
retains old locator records under their detached alias. These historical
locators cannot be used as reversal targets through the new namespace.
Verify restored dataset, research, and memo outputs through their ordinary
HTTP or CLI readers and record the new binding and copy receipts. A restore
with an incomplete version map, bad hash or missing namespace remains
incomplete.

For a local-only stack, use the separate local entry points. They reject
remote configuration, namespace records and remote backup members before
backend selection.

```powershell
uv run --locked python -m marketlab.storage.recovery local-backup-inventory
uv run --locked python -m marketlab.storage.recovery local-rebind-restore --owned-restore --backup LOCAL_BACKUP_INVENTORY_JSON
```

Copy and verify the local files and restore the database dump to separate owned
resources before binding. The local restore accepts no destination version
map. It still requires a different PostgreSQL database identity, a different
contained root and exact backup hashes, then rebuilds the ordinary local
inventory and reader checks.

## Test selection

S3-dependent cases live under `tests/s3` and carry the `s3` marker, including
SDK stub cases. Keep them outside the non-S3 regression command.

```powershell
uv run --locked pytest --ignore=tests/s3 -m "not integration and not s3"
uv run --locked pytest --ignore=tests/s3 -m "integration and not s3"
```

Run S3 cases only under separate authorization. The live fixture additionally
requires `MARKETLAB_PHASE6_OWNED_S3=confirmed-disposable-prefix` and isolated
database settings. The fixture retains its exact owned object versions until
reviewed cleanup.

The deferred cases are split across SDK protocol tests, live storage/parity,
fault injection, restore binding and actual browser/model bindings. Restore
cases, including guard-only cases, remain in `tests/s3`. No case in that
directory has been executed or collected in this implementation session.

The actual browser binding requires `MARKETLAB_PHASE6_BROWSER_PLAN` pointing
to reviewed JSON with these fields.

| Field | Frozen input |
| --- | --- |
| `schema` | `phase6-browser-inputs-v1` |
| `ui_url` | The owned loopback UI serving the configured owned API. |
| `canonical.csv` and `canonical.parquet` | Actual Binance-origin source objects containing `format`, absolute `file_path`, `bytes`, `sha256` and the canonical `metadata` object. |
| `model_smoke` | Literal `copilot_request`, `expected_spec`, independently verified `expected_results`, `expected_memo_variants` and the pinned `model_digest`. |

Supply an isolated model endpoint through `MARKETLAB_OLLAMA_URL` and retain its
identity/launch evidence. The smoke binding rejects the original default model
port. Before dispatch, the reviewed external launch receipt must bind this
UI URL to the actual owned API, and bind that API to the exact owned database,
storage root and namespace, and isolated model endpoint. A nondefault port and
separately configured CLI settings alone do not establish that linkage. The
harness uses the existing private Windows Job and native memory
sampling helper. It runs the existing Phase 4 exact 4 GiB boundary procedure,
six real CSV/Parquet imports across Chromium, Firefox and WebKit, and one
bounded copilot-to-research-to-memo smoke with reference comparison. It retains
failed invocations, lifecycle receipts and any uncertain storage charge.

The restore test additionally accepts `MARKETLAB_PHASE6_RESTORE_DATABASE_URL`
for a separate owned target database and
`MARKETLAB_PHASE6_RESTORE_S3_ENDPOINT` with the matching
`REGION`, `BUCKET`, `PREFIX`, `ACCESS_KEY`, `SECRET_KEY` and optional
`SESSION_TOKEN` variables under that same prefix. PostgreSQL dump/restore
executables must be available. Actual expired-credential and outage cases
declare their separate credential/proxy prerequisites in the deferred tests.
Missing prerequisites leave those gates pending.
