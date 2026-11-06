"""Track verified artifact locations and retained storage intents."""

from alembic import op

revision = "0012_v2_storage"
down_revision = "0011_v2_copilot_memos"
branch_labels = None
depends_on = None

DDL = """
ALTER TABLE v2_capacity_roots
 ADD COLUMN object_alias varchar(64),
 ADD COLUMN object_namespace_sha256 varchar(64),
 ADD CONSTRAINT ck_v2_object_namespace CHECK (
  (object_alias IS NULL AND object_namespace_sha256 IS NULL) OR
  (object_alias IS NOT NULL AND object_alias <> 'local'
   AND object_alias ~ '^[A-Za-z0-9_-]+$'
   AND object_namespace_sha256 IS NOT NULL
   AND object_namespace_sha256 ~ '^[0-9a-f]{64}$'));
ALTER TABLE v2_data_charges
 ADD COLUMN backend_alias varchar(64) NOT NULL DEFAULT 'local'
  CHECK (backend_alias ~ '^[A-Za-z0-9_-]+$'),
 ADD CONSTRAINT uq_v2_storage_charge_binding UNIQUE(charge_id,root_id,backend_alias);
ALTER TABLE v2_storage_reservations ADD COLUMN data_charge_id uuid REFERENCES v2_data_charges;
ALTER TABLE v2_research_reservations
 ADD COLUMN data_charge_id uuid REFERENCES v2_data_charges,
 ADD COLUMN materialization_native_identity text,
 ADD CONSTRAINT ck_v2_materialization_identity CHECK (
  (materialization_native_identity IS NULL AND
   relative_root<>'.materializations/'||reservation_id::text) OR
  (materialization_native_identity IS NOT NULL AND
   octet_length(materialization_native_identity) BETWEEN 1 AND 16384 AND
   relative_root='.materializations/'||reservation_id::text AND run_id IS NULL AND
   purpose='preparation' AND spill_bytes=0 AND output_bytes=0));
CREATE FUNCTION v2_materialization_identity_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.materialization_native_identity IS DISTINCT FROM NEW.materialization_native_identity THEN
  RAISE EXCEPTION 'Immutable materialization identity';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_v2_materialization_identity BEFORE UPDATE ON v2_research_reservations
 FOR EACH ROW EXECUTE FUNCTION v2_materialization_identity_immutable();

CREATE TABLE v2_storage_packages (
 package_id uuid PRIMARY KEY,
 legacy_dataset_id varchar(64) UNIQUE REFERENCES dataset_versions,
 v2_dataset_id varchar(64) UNIQUE REFERENCES v2_dataset_versions,
 legacy_research_id varchar(36) UNIQUE REFERENCES research_results,
 v2_research_id uuid UNIQUE REFERENCES v2_research_results,
 legacy_memo_id varchar(36) UNIQUE REFERENCES memo_results,
 v2_memo_id uuid UNIQUE REFERENCES v2_memo_results,
 upload_generation_id uuid UNIQUE REFERENCES v2_upload_generations,
 cli_import_id uuid UNIQUE REFERENCES v2_canonical_imports,
 legacy_local boolean NOT NULL,
 CHECK (num_nonnulls(legacy_dataset_id,v2_dataset_id,legacy_research_id,v2_research_id,
  legacy_memo_id,v2_memo_id,upload_generation_id,cli_import_id)=1)
);
CREATE TABLE v2_storage_copies (
 copy_id uuid PRIMARY KEY,
 package_id uuid NOT NULL REFERENCES v2_storage_packages,
 root_id uuid NOT NULL REFERENCES v2_capacity_roots,
 backend_alias varchar(64) NOT NULL CHECK (backend_alias ~ '^[A-Za-z0-9_-]+$'),
 verified_at timestamptz NOT NULL,
 active boolean NOT NULL,
 UNIQUE(copy_id,root_id,backend_alias)
);
CREATE UNIQUE INDEX ix_v2_storage_active ON v2_storage_copies(package_id) WHERE active;
CREATE INDEX ix_v2_storage_package ON v2_storage_copies(package_id);
CREATE TABLE v2_storage_objects (
 object_id uuid PRIMARY KEY,
 root_id uuid NOT NULL REFERENCES v2_capacity_roots,
 charge_id uuid NOT NULL,
 copy_id uuid,
 backend_alias varchar(64) NOT NULL,
 object_key varchar(1024) NOT NULL CHECK (
   object_key ~ '^[A-Za-z0-9_.=-]+(/[A-Za-z0-9_.=-]+)*$'
   AND object_key !~ '(^|/)[.]{1,2}(/|$)'),
 version_id varchar(1024),
 member varchar(128) NOT NULL CHECK (member ~ '^[A-Za-z0-9_.-]+$' AND member NOT IN ('.','..')),
 media_schema varchar(128) NOT NULL CHECK (media_schema ~ '^[A-Za-z0-9_.+/-]+$'),
 byte_length bigint NOT NULL CHECK (byte_length BETWEEN 1 AND 4294967296),
 sha256 varchar(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
 multipart_id varchar(1024),
 state varchar(16) NOT NULL CHECK (state IN
   ('planned','writing','verified','retained','retiring','retired')),
 updated_at timestamptz NOT NULL,
 UNIQUE(root_id,backend_alias,object_key),
 UNIQUE(copy_id,member),
 FOREIGN KEY(charge_id,root_id,backend_alias)
   REFERENCES v2_data_charges(charge_id,root_id,backend_alias),
 FOREIGN KEY(copy_id,root_id,backend_alias)
   REFERENCES v2_storage_copies(copy_id,root_id,backend_alias),
 CHECK (copy_id IS NULL OR state='verified'),
 CHECK (backend_alias <> 'local' OR (version_id IS NULL AND multipart_id IS NULL)),
 CHECK (backend_alias = 'local' OR state <> 'verified'
  OR (version_id IS NOT NULL AND version_id NOT IN ('','null'))),
 CHECK (multipart_id IS NULL OR multipart_id <> '')
);
CREATE INDEX ix_v2_storage_charge ON v2_storage_objects(charge_id,state);

UPDATE v2_storage_reservations r SET data_charge_id=g.charge_id
 FROM v2_upload_generations g
 JOIN v2_admission_tickets t ON t.ticket_id=g.ticket_id AND t.role='upload'
 JOIN v2_data_charges c ON c.charge_id=g.charge_id AND c.ticket_id=t.ticket_id
  AND c.root_id=t.root_id AND c.backend_alias='local'
 WHERE r.reservation_id=g.reservation_id AND r.kind='source'
  AND r.import_id=g.import_id AND r.relative_path=g.relative_path
  AND r.ceiling_bytes=g.declared_bytes AND c.ceiling_bytes=g.declared_bytes;
WITH exact_cli AS (
 SELECT r.reservation_id,(array_agg(c.charge_id))[1] AS charge_id
 FROM v2_storage_reservations r
 JOIN v2_canonical_imports i ON i.import_id=r.import_id AND i.transport='cli'
 JOIN v2_admission_tickets t ON t.resource_id=i.import_id AND t.role='upload'
 JOIN v2_data_charges c ON c.ticket_id=t.ticket_id AND c.root_id=t.root_id
 WHERE r.data_charge_id IS NULL AND r.kind='source' AND c.backend_alias='local'
  AND r.relative_path=i.source_relative_path AND r.ceiling_bytes=i.declared_bytes
  AND c.ceiling_bytes=i.declared_bytes
 GROUP BY r.reservation_id HAVING count(*)=1
)
UPDATE v2_storage_reservations r SET data_charge_id=e.charge_id
 FROM exact_cli e WHERE e.reservation_id=r.reservation_id;

CREATE FUNCTION v2_storage_object_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (OLD.object_id,OLD.root_id,OLD.charge_id,OLD.backend_alias,OLD.object_key,
     OLD.member,OLD.media_schema,OLD.byte_length,OLD.sha256)
    IS DISTINCT FROM
    (NEW.object_id,NEW.root_id,NEW.charge_id,NEW.backend_alias,NEW.object_key,
     NEW.member,NEW.media_schema,NEW.byte_length,NEW.sha256)
    OR (OLD.multipart_id IS NOT NULL AND OLD.multipart_id IS DISTINCT FROM NEW.multipart_id)
    OR (OLD.version_id IS NOT NULL AND OLD.version_id IS DISTINCT FROM NEW.version_id)
    OR (OLD.copy_id IS NOT NULL AND OLD.copy_id IS DISTINCT FROM NEW.copy_id)
    OR (OLD.copy_id IS NOT NULL AND NEW.state <> 'verified')
    OR (OLD.state='retired' AND NEW.state <> 'retired') THEN
  RAISE EXCEPTION 'Immutable storage object';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_v2_storage_object_immutable BEFORE UPDATE ON v2_storage_objects
 FOR EACH ROW EXECUTE FUNCTION v2_storage_object_immutable();

INSERT INTO v2_storage_packages(package_id,legacy_dataset_id,legacy_local)
 SELECT gen_random_uuid(),dataset_version_id,true FROM dataset_versions;
INSERT INTO v2_storage_packages(package_id,v2_dataset_id,legacy_local)
 SELECT gen_random_uuid(),dataset_version_id,true FROM v2_dataset_versions;
INSERT INTO v2_storage_packages(package_id,legacy_research_id,legacy_local)
 SELECT gen_random_uuid(),run_id,true FROM research_results;
INSERT INTO v2_storage_packages(package_id,v2_research_id,legacy_local)
 SELECT gen_random_uuid(),run_id,true FROM v2_research_results;
INSERT INTO v2_storage_packages(package_id,legacy_memo_id,legacy_local)
 SELECT gen_random_uuid(),run_id,true FROM memo_results;
INSERT INTO v2_storage_packages(package_id,v2_memo_id,legacy_local)
 SELECT gen_random_uuid(),run_id,true FROM v2_memo_results;
INSERT INTO v2_storage_packages(package_id,upload_generation_id,legacy_local)
 SELECT gen_random_uuid(),g.generation_id,true
 FROM v2_canonical_imports i JOIN v2_upload_generations g
 ON g.import_id=i.import_id AND g.generation_id=i.generation_id
 WHERE g.state='uploaded';
INSERT INTO v2_storage_packages(package_id,cli_import_id,legacy_local)
 SELECT gen_random_uuid(),i.import_id,true FROM v2_canonical_imports i
 WHERE i.submission_id IS NOT NULL AND NOT EXISTS
 (SELECT 1 FROM v2_upload_generations g WHERE g.import_id=i.import_id);
UPDATE v2_capacity_roots SET ready=false,epoch=epoch+1,updated_at=clock_timestamp();
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    raise RuntimeError("V2 storage is forward-only; restore a verified owned backup")
