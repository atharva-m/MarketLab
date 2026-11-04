"""Add versioned interpretation/memo state without upgrading historical work."""

from alembic import op

revision = "0011_v2_copilot_memos"
down_revision = "0010_v2_browser_imports"
branch_labels = None
depends_on = None


def blob(name: str, size: int, *, nullable: bool = False) -> str:
    return f"{name} text {'NULL' if nullable else 'NOT NULL'} CHECK(octet_length({name})<={size})"


def sha(name: str, *, nullable: bool = False) -> str:
    return (
        f"{name} varchar(64) {'NULL' if nullable else 'NOT NULL'} "
        f"CHECK({name} ~ '^[0-9a-f]{{64}}$')"
    )


STATE = """
 state varchar(16) NOT NULL DEFAULT 'queued'
 CHECK(state IN ('queued','running','retry_wait','succeeded','failed')),
 attempt_count integer NOT NULL DEFAULT 0 CHECK(attempt_count BETWEEN 0 AND 3),
 model_calls integer NOT NULL DEFAULT 0 CHECK(model_calls BETWEEN 0 AND 2),
 fencing_token bigint NOT NULL DEFAULT 0 CHECK(fencing_token>=0),
 owner uuid, lease_until timestamptz,
 eligible_at timestamptz NOT NULL DEFAULT clock_timestamp(), error_code varchar(64),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK((state='running' AND owner IS NOT NULL AND lease_until IS NOT NULL)
 OR (state<>'running' AND owner IS NULL AND lease_until IS NULL))
"""

DDL = f"""
CREATE TABLE v2_copilot_requests (
 request_id uuid PRIMARY KEY, idempotency_key varchar(128) NOT NULL UNIQUE
 CHECK(idempotency_key ~ '^[A-Za-z0-9_.-]{{1,128}}$'),
 {sha("request_sha256")}, {blob("body_json", 65536)},
 {blob("snapshot_json", 65536)}, {sha("snapshot_sha256")},
 {blob("execution_json", 65536)}, {sha("execution_sha256")}, {sha("lock_sha256")},
 current_revision integer NOT NULL DEFAULT 0 CHECK(current_revision BETWEEN 0 AND 5),
 run_id uuid UNIQUE REFERENCES v2_research_runs,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE v2_copilot_revisions (
 request_id uuid NOT NULL REFERENCES v2_copilot_requests,
 revision integer NOT NULL CHECK(revision BETWEEN 0 AND 5),
 {blob("body_json", 65536)}, {sha("body_sha256")}, answer_key varchar(128),
 outcome varchar(24) CHECK(outcome IN
 ('submitted','needs_clarification','unsupported','failed')),
 {blob("interpretation_json", 32768, nullable=True)},
 {blob("provenance_json", 131072, nullable=True)},
 {blob("questions_json", 8192, nullable=True)},
 {blob("spec_json", 65536, nullable=True)}, {sha("spec_sha256", nullable=True)},
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(request_id,revision), UNIQUE(request_id,answer_key),
 CHECK((revision=0)=(answer_key IS NULL)),
 CHECK(answer_key IS NULL OR answer_key ~ '^[A-Za-z0-9_.-]{{1,128}}$'),
 CHECK((outcome='submitted')=(spec_json IS NOT NULL AND spec_sha256 IS NOT NULL)),
 CHECK((spec_json IS NULL)=(spec_sha256 IS NULL))
);
ALTER TABLE v2_copilot_requests ADD CONSTRAINT fk_v2_copilot_current
 FOREIGN KEY(request_id,current_revision) REFERENCES v2_copilot_revisions
 DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE v2_copilot_jobs (
 job_id uuid PRIMARY KEY, request_id uuid NOT NULL, revision integer NOT NULL,
 UNIQUE(request_id,revision), FOREIGN KEY(request_id,revision)
 REFERENCES v2_copilot_revisions, {STATE}
);
CREATE TABLE v2_memo_jobs (
 run_id uuid PRIMARY KEY REFERENCES v2_research_results,
 {sha("numerical_manifest_sha256")}, {sha("summary_sha256")},
 {sha("numerical_fingerprint_sha256")}, {blob("execution_json", 65536)},
 {sha("execution_sha256")}, {sha("lock_sha256")},
 {blob("draft_json", 32768, nullable=True)},
 {blob("provenance_json", 131072, nullable=True)}, {STATE}
);
"""

for kind, ident in (("copilot", "job_id"), ("memo", "run_id")):
    extra = (
        "attempt_uuid uuid NOT NULL UNIQUE, relative_path text NOT NULL UNIQUE, "
        "ticket_id uuid UNIQUE REFERENCES v2_admission_tickets, "
        "charge_id uuid UNIQUE REFERENCES v2_data_charges, "
        "CHECK((ticket_id IS NULL)=(charge_id IS NULL)),"
        if kind == "memo"
        else ""
    )
    DDL += f"""
CREATE TABLE v2_{kind}_attempts (
 {ident} uuid NOT NULL REFERENCES v2_{kind}_jobs,
 attempt_number integer NOT NULL CHECK(attempt_number BETWEEN 1 AND 3),
 owner uuid NOT NULL, fencing_token bigint NOT NULL CHECK(fencing_token>0),
 started_at timestamptz NOT NULL DEFAULT clock_timestamp(), ended_at timestamptz,
 outcome varchar(16) NOT NULL DEFAULT 'running' CHECK(outcome IN
 ('running','succeeded','retry_wait','expired','failed')), error_code varchar(64),
 {extra} PRIMARY KEY({ident},attempt_number), UNIQUE({ident},fencing_token),
 CHECK((outcome='running')=(ended_at IS NULL))
);
CREATE TABLE v2_{kind}_calls (
 {ident} uuid NOT NULL REFERENCES v2_{kind}_jobs,
 call_number integer NOT NULL CHECK(call_number BETWEEN 1 AND 2),
 attempt_number integer NOT NULL, fencing_token bigint NOT NULL CHECK(fencing_token>0),
 {sha("model_digest")}, {sha("input_sha256")}, {sha("schema_sha256")}, {sha("prompt_sha256")},
 reserved_at timestamptz NOT NULL DEFAULT clock_timestamp(), finished_at timestamptz,
 state varchar(16) NOT NULL DEFAULT 'reserved'
 CHECK(state IN ('reserved','checkpointed','failed')),
 {blob("response_text", 32768, nullable=True)}, {sha("response_sha256", nullable=True)},
 {blob("provenance_json", 131072, nullable=True)},
 PRIMARY KEY({ident},call_number), FOREIGN KEY({ident},attempt_number)
 REFERENCES v2_{kind}_attempts,
 CHECK(state<>'checkpointed' OR
 (response_text IS NOT NULL AND response_sha256 IS NOT NULL AND provenance_json IS NOT NULL))
);
CREATE INDEX ix_v2_{kind}_due ON v2_{kind}_jobs(state,eligible_at,created_at,{ident});
CREATE INDEX ix_v2_{kind}_lease ON v2_{kind}_jobs(state,lease_until);
CREATE INDEX ix_v2_{kind}_attempt ON v2_{kind}_attempts({ident},started_at);
"""

DDL += f"""
CREATE INDEX ix_v2_copilot_execution ON v2_copilot_requests(execution_sha256,created_at);
CREATE INDEX ix_v2_memo_execution ON v2_memo_jobs(execution_sha256,created_at);
CREATE TABLE v2_memo_results (
 run_id uuid PRIMARY KEY REFERENCES v2_memo_jobs REFERENCES v2_research_results,
 attempt_number integer NOT NULL, relative_path text NOT NULL UNIQUE,
 {sha("manifest_sha256")}, {sha("memo_sha256")}, {sha("facts_sha256")}, {sha("summary_sha256")},
 package_bytes bigint NOT NULL CHECK(package_bytes BETWEEN 1 AND 1048576),
 registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(run_id,attempt_number) REFERENCES v2_memo_attempts
);
CREATE TABLE v2_memo_operations (
 idempotency_key varchar(128) PRIMARY KEY CHECK(idempotency_key ~ '^[A-Za-z0-9_.-]{{1,128}}$'),
 run_id uuid NOT NULL REFERENCES v2_memo_jobs, {sha("request_sha256")},
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
DO $$
DECLARE c record; n integer := 0;
BEGIN
 CREATE TEMP TABLE expected_p5_roles (role varchar(16),
 CHECK(role IN ('upload','ingestion','research','legacy'))) ON COMMIT DROP;
 CREATE TEMP TABLE expected_p5_restored_roles (role varchar(16),
 CHECK(role::text=ANY(ARRAY[('upload'::varchar)::text,('ingestion'::varchar)::text,
 ('research'::varchar)::text,('legacy'::varchar)::text]))) ON COMMIT DROP;
 FOR c IN SELECT conname,pg_get_expr(conbin,conrelid) AS expression
 FROM pg_constraint WHERE conrelid='v2_admission_tickets'::regclass AND contype='c'
 LOOP
  IF c.expression IN (SELECT pg_get_expr(conbin,conrelid) FROM pg_constraint
    WHERE conrelid IN ('expected_p5_roles'::regclass,
    'expected_p5_restored_roles'::regclass) AND contype='c') THEN
   EXECUTE format('ALTER TABLE v2_admission_tickets DROP CONSTRAINT %I',c.conname);
   n := n+1;
  END IF;
 END LOOP;
 IF n<>1 THEN RAISE EXCEPTION 'Unexpected admission role constraint'; END IF;
END $$;
ALTER TABLE v2_admission_tickets ADD CONSTRAINT ck_v2_admission_p5_roles
 CHECK(role IN ('upload','ingestion','research','legacy','memo'));
UPDATE v2_capacity_roots SET ready=false,epoch=epoch+1,updated_at=clock_timestamp();
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    raise RuntimeError("V2 model state is forward-only; restore a verified owned backup")
