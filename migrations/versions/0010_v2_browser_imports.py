"""Add browser generations and root-bound local admission without rewriting history."""

from alembic import op

revision = "0010_v2_browser_imports"
down_revision = "0009_v2_research"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL assigned names to these original unnamed checks. Match their
    # exact normalized definitions, not a name pattern or all import checks.
    op.execute("""
DO $$
DECLARE c record; n integer := 0;
BEGIN
 CREATE TEMP TABLE v2_expected_import_checks (
  state varchar(16), staging_owner uuid, staging_lease_until timestamptz,
  CHECK (state IN ('staging','queued','running','retry_wait','succeeded','failed','cancelled')),
  CHECK ((state='staging') = (staging_owner IS NOT NULL AND staging_lease_until IS NOT NULL)),
  CHECK (state='staging' OR (staging_owner IS NULL AND staging_lease_until IS NULL))
 ) ON COMMIT DROP;
 -- pg_dump/restored CHECKs cast each original varchar literal to text;
 -- fresh DDL casts the full varchar array. Both exact known expressions are
 -- generated prospectively here; no wildcard/semantic weakening is accepted.
 CREATE TEMP TABLE v2_expected_restored_import_check (
  state varchar(16), CHECK (state::text = ANY (ARRAY[
   ('staging'::character varying)::text, ('queued'::character varying)::text,
   ('running'::character varying)::text, ('retry_wait'::character varying)::text,
   ('succeeded'::character varying)::text, ('failed'::character varying)::text,
   ('cancelled'::character varying)::text]))
 ) ON COMMIT DROP;
 FOR c IN SELECT conname, pg_get_expr(conbin,conrelid) AS expression
  FROM pg_constraint WHERE conrelid='v2_canonical_imports'::regclass AND contype='c'
 LOOP
  IF c.expression IN (SELECT pg_get_expr(conbin,conrelid) FROM pg_constraint
    WHERE conrelid IN ('v2_expected_import_checks'::regclass,
     'v2_expected_restored_import_check'::regclass) AND contype='c') THEN
   EXECUTE format('ALTER TABLE v2_canonical_imports DROP CONSTRAINT %I',c.conname);
   n := n+1;
  END IF;
 END LOOP;
 IF n <> 3 THEN RAISE EXCEPTION 'Unexpected import constraint count'; END IF;
END $$;
ALTER TABLE v2_canonical_imports ADD COLUMN transport varchar(8) NOT NULL DEFAULT 'cli'
 CHECK (transport IN ('cli','browser'));
ALTER TABLE v2_canonical_imports ADD CONSTRAINT ck_v2_import_transport_states CHECK (
 (transport='cli' AND state IN
 ('staging','queued','running','retry_wait','succeeded','failed','cancelled'))
 OR (transport='browser' AND state IN ('awaiting_upload','uploading','upload_failed','uploaded',
 'queued','running','retry_wait','succeeded','failed','cancelled')));
ALTER TABLE v2_canonical_imports ADD CONSTRAINT ck_v2_import_active_owner CHECK (
 (state IN ('staging','uploading') AND staging_owner IS NOT NULL
 AND staging_lease_until IS NOT NULL)
 OR (state NOT IN ('staging','uploading') AND staging_owner IS NULL
 AND staging_lease_until IS NULL));
CREATE TABLE v2_capacity_roots (
 root_id uuid PRIMARY KEY, singleton boolean NOT NULL UNIQUE CHECK (singleton),
 root_path text NOT NULL UNIQUE, schema_version varchar(32) NOT NULL
 CHECK (schema_version='local-capacity-v1'),
 ready boolean NOT NULL DEFAULT false, epoch bigint NOT NULL DEFAULT 0 CHECK (epoch>=0),
 baseline_bytes bigint NOT NULL DEFAULT 0 CHECK (baseline_bytes>=0),
 receipt_sha256 varchar(64) CHECK (receipt_sha256 ~ '^[0-9a-f]{64}$'),
 receipt_json text, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 CHECK (NOT ready OR (receipt_sha256 IS NOT NULL AND receipt_json IS NOT NULL))
);
CREATE TABLE v2_admission_tickets (
 ticket_id uuid PRIMARY KEY, root_id uuid NOT NULL REFERENCES v2_capacity_roots(root_id),
 role varchar(16) NOT NULL CHECK (role IN ('upload','ingestion','research','legacy')),
 resource_id uuid, generation_id uuid, attempt_number integer, fencing_token bigint,
 owner uuid NOT NULL, native_identity text NOT NULL CHECK (octet_length(native_identity)<=16384),
 physical_bytes bigint NOT NULL DEFAULT 0 CHECK (physical_bytes>=0),
 state varchar(16) NOT NULL CHECK (state IN ('pending','active','draining','released')),
 created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL
);
CREATE TABLE v2_capacity_files (
 root_id uuid NOT NULL REFERENCES v2_capacity_roots(root_id), inventory_epoch bigint NOT NULL,
 relative_path text NOT NULL,
 file_bytes bigint NOT NULL CHECK (file_bytes>=0), mtime_ns bigint NOT NULL,
 content_sha256 varchar(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
 PRIMARY KEY(root_id,inventory_epoch,relative_path)
);
CREATE INDEX ix_v2_admission_active ON v2_admission_tickets(root_id,role,state);
CREATE TABLE v2_data_charges (
 charge_id uuid PRIMARY KEY, root_id uuid NOT NULL REFERENCES v2_capacity_roots(root_id),
 ticket_id uuid REFERENCES v2_admission_tickets(ticket_id), resource_id uuid,
 ceiling_bytes bigint NOT NULL CHECK (ceiling_bytes>=0),
 charged_bytes bigint NOT NULL CHECK (charged_bytes>=0 AND charged_bytes<=ceiling_bytes),
 state varchar(16) NOT NULL CHECK (state IN ('reserved','retained','absorbed','released')),
 relative_path text, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 CHECK (state<>'released' OR charged_bytes=0)
);
CREATE INDEX ix_v2_data_charges_active ON v2_data_charges(root_id,state);
CREATE TABLE v2_upload_generations (
 generation_id uuid PRIMARY KEY, import_id uuid NOT NULL REFERENCES v2_canonical_imports(import_id),
 ordinal integer NOT NULL CHECK (ordinal>=1), relative_path text NOT NULL UNIQUE,
 token_sha256 varchar(64) NOT NULL CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
 expires_at timestamptz NOT NULL, owner uuid, lease_until timestamptz,
 declared_bytes bigint NOT NULL CHECK (declared_bytes BETWEEN 1 AND 4294967296),
 received_bytes bigint NOT NULL DEFAULT 0
 CHECK (received_bytes>=0 AND received_bytes<=declared_bytes),
 source_sha256 varchar(64) NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
 state varchar(16) NOT NULL
 CHECK (state IN ('issued','claimed','uploaded','failed','retired','cancelled')),
 reservation_id uuid NOT NULL UNIQUE REFERENCES v2_storage_reservations(reservation_id),
 ticket_id uuid NOT NULL REFERENCES v2_admission_tickets(ticket_id),
 charge_id uuid NOT NULL REFERENCES v2_data_charges(charge_id),
 created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 UNIQUE(import_id,ordinal), CHECK (
 (state='claimed' AND owner IS NOT NULL AND lease_until IS NOT NULL)
 OR (state<>'claimed' AND owner IS NULL AND lease_until IS NULL))
);
CREATE INDEX ix_v2_upload_import ON v2_upload_generations(import_id,ordinal);
CREATE INDEX ix_v2_upload_recovery ON v2_upload_generations(state,lease_until,expires_at);
""")


def downgrade() -> None:
    raise RuntimeError("Browser imports are forward-only; restore a verified owned backup")
