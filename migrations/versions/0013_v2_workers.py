"""Register explicit worker ownership without changing historical accounting."""

from alembic import op

revision = "0013_v2_workers"
down_revision = "0012_v2_storage"
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE v2_worker_hosts (
 host_id uuid PRIMARY KEY, operator_label varchar(128) NOT NULL
 CHECK(octet_length(operator_label) BETWEEN 1 AND 128),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE TABLE v2_worker_roots (
 root_id uuid PRIMARY KEY, host_id uuid NOT NULL REFERENCES v2_worker_hosts,
 local_path text NOT NULL CHECK(octet_length(local_path) BETWEEN 1 AND 4096),
 boot_identity varchar(128) NOT NULL, machine_identity varchar(64),
 CHECK(machine_identity IS NULL OR machine_identity ~ '^[0-9a-f]{64}$'),
 recovery_token uuid, recovery_epoch bigint NOT NULL DEFAULT 0 CHECK(recovery_epoch>=0),
 ready boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(), UNIQUE(host_id,local_path));
CREATE TABLE v2_worker_instances (
 instance_id uuid PRIMARY KEY, root_id uuid NOT NULL REFERENCES v2_worker_roots,
 source_sha256 varchar(64) NOT NULL CHECK(source_sha256 ~ '^[0-9a-f]{64}$'),
 lock_sha256 varchar(64) NOT NULL CHECK(lock_sha256 ~ '^[0-9a-f]{64}$'),
 boot_identity varchar(128) NOT NULL,
 native_identity text CHECK(octet_length(native_identity)<=16384),
 state varchar(16) NOT NULL CHECK(state IN ('starting','ready','draining','stopped')),
 registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 heartbeat_at timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE INDEX ix_v2_worker_fresh ON v2_worker_instances(state,heartbeat_at);
CREATE TABLE v2_worker_files (
 root_id uuid NOT NULL REFERENCES v2_worker_roots,
 relative_path text NOT NULL CHECK(octet_length(relative_path) BETWEEN 1 AND 4096),
 file_bytes bigint NOT NULL CHECK(file_bytes>=0), mtime_ns bigint NOT NULL,
 content_sha256 varchar(64) NOT NULL CHECK(content_sha256 ~ '^[0-9a-f]{64}$'),
 PRIMARY KEY(root_id,relative_path));
CREATE TABLE v2_worker_capabilities (
 instance_id uuid NOT NULL REFERENCES v2_worker_instances,
 kind varchar(16) NOT NULL CHECK(kind IN ('ingestion','research','copilot','memo')),
 contract varchar(64) NOT NULL,
 execution_sha256 varchar(64) NOT NULL CHECK(execution_sha256 ~ '^[0-9a-f]{64}$'),
 PRIMARY KEY(instance_id,kind,contract));
CREATE TABLE v2_worker_mode (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 mode varchar(16) NOT NULL CHECK(mode IN ('local','distributed')),
 shared_root_id uuid REFERENCES v2_capacity_roots,
 CHECK(mode='local' OR shared_root_id IS NOT NULL));
INSERT INTO v2_worker_mode(singleton,mode) VALUES(true,'local');
"""
for kind in ("ingestion", "research", "copilot", "memo"):
    DDL += f"""
ALTER TABLE v2_{kind}_attempts ADD COLUMN worker_instance_id uuid
 REFERENCES v2_worker_instances;
CREATE INDEX ix_v2_{kind}_worker ON v2_{kind}_attempts(worker_instance_id);
CREATE FUNCTION v2_{kind}_worker_attempt() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 NEW.worker_instance_id := nullif(current_setting('marketlab.worker_instance_id',true),'')::uuid;
 IF (SELECT mode='distributed' FROM v2_worker_mode WHERE singleton)
 AND NEW.worker_instance_id IS NULL THEN RAISE EXCEPTION 'Registered worker required'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_v2_{kind}_worker_attempt BEFORE INSERT ON v2_{kind}_attempts
 FOR EACH ROW EXECUTE FUNCTION v2_{kind}_worker_attempt();
"""
for table in ("admission_tickets", "storage_reservations", "research_reservations"):
    DDL += f"""
ALTER TABLE v2_{table} ADD COLUMN worker_root_id uuid REFERENCES v2_worker_roots;
CREATE INDEX ix_v2_{table}_worker ON v2_{table}(worker_root_id,state);
CREATE FUNCTION v2_{table}_worker_root() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 NEW.worker_root_id := nullif(current_setting('marketlab.worker_root_id',true),'')::uuid;
 IF (SELECT mode='distributed' FROM v2_worker_mode WHERE singleton)
 AND NEW.worker_root_id IS NULL THEN RAISE EXCEPTION 'Worker root required'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_v2_{table}_worker_root BEFORE INSERT ON v2_{table}
 FOR EACH ROW EXECUTE FUNCTION v2_{table}_worker_root();
"""
for kind in ("copilot", "memo"):
    # Match the exact old expression, including the pg_dump restored spelling.
    for suffix, column, old, new in (
        (
            "jobs",
            "state",
            "'queued','running','retry_wait','succeeded','failed'",
            "'queued','running','retry_wait','succeeded','failed','cancelled'",
        ),
        (
            "attempts",
            "outcome",
            "'running','succeeded','retry_wait','expired','failed'",
            "'running','succeeded','retry_wait','expired','failed','cancelled'",
        ),
    ):
        restored_values = ",".join("(" + value + "::varchar)::text" for value in old.split(","))
        DDL += f"""
DO $$ DECLARE c record; n integer := 0; BEGIN
 CREATE TEMP TABLE expected_worker_check ({column} varchar(16),
 CHECK({column} IN ({old}))) ON COMMIT DROP;
 CREATE TEMP TABLE expected_worker_restored_check ({column} varchar(16),
 CHECK({column}::text=ANY(ARRAY[{restored_values}]))) ON COMMIT DROP;
 FOR c IN SELECT conname FROM pg_constraint
 WHERE conrelid='v2_{kind}_{suffix}'::regclass AND contype='c'
 AND pg_get_expr(conbin,conrelid) IN (SELECT pg_get_expr(conbin,conrelid)
 FROM pg_constraint WHERE conrelid IN ('expected_worker_check'::regclass,
 'expected_worker_restored_check'::regclass) AND contype='c')
 LOOP EXECUTE format('ALTER TABLE v2_{kind}_{suffix} DROP CONSTRAINT %I',c.conname);
 n := n+1; END LOOP;
 IF n<>1 THEN RAISE EXCEPTION 'Unexpected worker state constraint'; END IF;
 DROP TABLE expected_worker_check;
 DROP TABLE expected_worker_restored_check;
END $$;
ALTER TABLE v2_{kind}_{suffix} ADD CONSTRAINT ck_v2_{kind}_{suffix}_worker
 CHECK({column} IN ({new}));
"""
    DDL += f"""
ALTER TABLE v2_{kind}_jobs ADD COLUMN cancel_requested boolean NOT NULL DEFAULT false,
 ADD COLUMN state_revision bigint NOT NULL DEFAULT 0 CHECK(state_revision>=0);
CREATE FUNCTION v2_{kind}_state_revision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.state IS DISTINCT FROM NEW.state OR
 (NOT OLD.cancel_requested AND NEW.cancel_requested) THEN
 NEW.state_revision := OLD.state_revision+1;
 ELSIF NEW.state_revision IS DISTINCT FROM OLD.state_revision THEN
 RAISE EXCEPTION 'Invalid state revision mutation';
 END IF; RETURN NEW;
END $$;
CREATE TRIGGER trg_v2_{kind}_state_revision BEFORE UPDATE ON v2_{kind}_jobs
 FOR EACH ROW EXECUTE FUNCTION v2_{kind}_state_revision();
"""
DDL += """
DO $$ DECLARE c record; n integer := 0; BEGIN
 CREATE TEMP TABLE expected_worker_revision (outcome varchar(24),
 CHECK(outcome IN ('submitted','needs_clarification','unsupported','failed'))) ON COMMIT DROP;
 CREATE TEMP TABLE expected_worker_revision_restored (outcome varchar(24),
 CHECK(outcome::text=ANY(ARRAY[('submitted'::varchar)::text,
 ('needs_clarification'::varchar)::text,('unsupported'::varchar)::text,
 ('failed'::varchar)::text]))) ON COMMIT DROP;
 FOR c IN SELECT conname FROM pg_constraint
 WHERE conrelid='v2_copilot_revisions'::regclass AND contype='c'
 AND pg_get_expr(conbin,conrelid) IN (SELECT pg_get_expr(conbin,conrelid)
 FROM pg_constraint WHERE conrelid IN ('expected_worker_revision'::regclass,
 'expected_worker_revision_restored'::regclass) AND contype='c')
 LOOP EXECUTE format('ALTER TABLE v2_copilot_revisions DROP CONSTRAINT %I',c.conname);
 n := n+1; END LOOP;
 IF n<>1 THEN RAISE EXCEPTION 'Unexpected revision outcome constraint'; END IF;
END $$;
ALTER TABLE v2_copilot_revisions ADD CONSTRAINT v2_copilot_revisions_outcome_check
 CHECK(outcome IN ('submitted','needs_clarification','unsupported','failed','cancelled'));
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    raise RuntimeError("Worker state is forward-only; restore a verified owned backup")
