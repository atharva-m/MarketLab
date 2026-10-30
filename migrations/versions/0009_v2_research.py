"""Add isolated generalized numerical research; preserve all old tables."""

from alembic import op

revision = "0009_v2_research"
down_revision = "0008_v2_ingestion"
branch_labels = None
depends_on = None

DDL = r"""
CREATE TABLE v2_research_submissions (
 submission_id uuid PRIMARY KEY,
 idempotency_key varchar(128) NOT NULL UNIQUE CHECK(idempotency_key ~ '^[A-Za-z0-9_.-]{1,128}$'),
 request_sha256 varchar(64) NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
 spec_json text NOT NULL CHECK(octet_length(spec_json)<=65536
 AND jsonb_typeof(spec_json::jsonb)='object'),
 contract varchar(48) NOT NULL CHECK(contract='research-spec-v2'),
 fingerprint_json text NOT NULL CHECK(octet_length(fingerprint_json)<=131072
 AND jsonb_typeof(fingerprint_json::jsonb)='object'),
 fingerprint_sha256 varchar(64) NOT NULL CHECK(fingerprint_sha256 ~ '^[0-9a-f]{64}$'),
 execution_sha256 varchar(64) NOT NULL CHECK(execution_sha256 ~ '^[0-9a-f]{64}$'),
 lock_sha256 varchar(64) NOT NULL CHECK(lock_sha256 ~ '^[0-9a-f]{64}$'),
 created_at timestamptz NOT NULL
);
CREATE TABLE v2_research_selections (
 submission_id uuid NOT NULL REFERENCES v2_research_submissions,
 instrument_id varchar(109) NOT NULL, semantic_sha256 varchar(64) NOT NULL,
 trade_date date NOT NULL CHECK(trade_date BETWEEN DATE '1970-01-01' AND DATE '9999-12-30'),
 dataset_version_id varchar(64) NOT NULL CHECK(dataset_version_id ~ '^[0-9a-f]{64}$'),
 legacy_version_id varchar(64) REFERENCES dataset_versions(dataset_version_id),
 v2_version_id varchar(64) REFERENCES v2_dataset_versions(dataset_version_id),
 manifest_sha256 varchar(64) NOT NULL CHECK(manifest_sha256 ~ '^[0-9a-f]{64}$'),
 metadata_json text NOT NULL CHECK(octet_length(metadata_json)<=4096
 AND jsonb_typeof(metadata_json::jsonb)='object'),
 PRIMARY KEY(submission_id,instrument_id,trade_date), UNIQUE(submission_id,dataset_version_id),
 FOREIGN KEY(instrument_id,semantic_sha256)
 REFERENCES v2_instruments(instrument_id,semantic_sha256),
 CHECK((legacy_version_id IS NOT NULL AND v2_version_id IS NULL
 AND legacy_version_id=dataset_version_id)
 OR (v2_version_id IS NOT NULL AND legacy_version_id IS NULL AND v2_version_id=dataset_version_id))
);
CREATE TABLE v2_research_runs (
 run_id uuid PRIMARY KEY, submission_id uuid NOT NULL UNIQUE REFERENCES v2_research_submissions,
 state varchar(16) NOT NULL CHECK(state IN
 ('queued','running','retry_wait','succeeded','failed','cancelled')),
 revision bigint NOT NULL CHECK(revision>=0),
 attempt_count integer NOT NULL CHECK(attempt_count BETWEEN 0 AND 3),
 fencing_token bigint NOT NULL CHECK(fencing_token>=0), owner uuid, lease_until timestamptz,
 eligible_at timestamptz NOT NULL, cancel_requested boolean NOT NULL, result_id uuid UNIQUE,
 error_code varchar(64), created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 CHECK((state='running')=(owner IS NOT NULL AND lease_until IS NOT NULL)),
 CHECK(state='running' OR (owner IS NULL AND lease_until IS NULL)),
 CHECK((state='succeeded')=(result_id IS NOT NULL)), CHECK(result_id IS NULL OR result_id=run_id),
 CHECK(state<>'cancelled' OR cancel_requested),
 CHECK(error_code IS NULL OR error_code IN ('invalid_request','coverage_gap','revision_conflict',
 'integrity_failure','capacity_exceeded','incompatible_execution','cancelled',
 'deadline_exceeded','unavailable','execution_failed'))
);
CREATE TABLE v2_research_attempts (
 run_id uuid NOT NULL REFERENCES v2_research_runs,
 attempt_number integer NOT NULL CHECK(attempt_number BETWEEN 1 AND 3),
 fencing_token bigint NOT NULL CHECK(fencing_token>0), owner uuid NOT NULL,
 started_at timestamptz NOT NULL, ended_at timestamptz,
 outcome varchar(16) NOT NULL CHECK(outcome IN
 ('running','succeeded','transient','permanent','expired','cancelled')),
 error_code varchar(64), PRIMARY KEY(run_id,attempt_number), UNIQUE(run_id,fencing_token),
 CHECK((outcome='running')=(ended_at IS NULL))
);
CREATE TABLE v2_research_results (
 run_id uuid PRIMARY KEY REFERENCES v2_research_runs, manifest_relative_path text NOT NULL UNIQUE,
 manifest_sha256 varchar(64) NOT NULL CHECK(manifest_sha256 ~ '^[0-9a-f]{64}$'),
 results_sha256 varchar(64) NOT NULL CHECK(results_sha256 ~ '^[0-9a-f]{64}$'),
 summary_sha256 varchar(64) NOT NULL CHECK(summary_sha256 ~ '^[0-9a-f]{64}$'),
 result_bytes bigint NOT NULL CHECK(result_bytes BETWEEN 1 AND 16777216),
 summary_bytes bigint NOT NULL CHECK(summary_bytes BETWEEN 1 AND 16777216),
 registered_at timestamptz NOT NULL,
 CHECK(manifest_relative_path='research-v2/'||run_id::text||'/manifest.json')
);
ALTER TABLE v2_research_runs ADD CONSTRAINT fk_v2_research_result FOREIGN KEY(result_id)
 REFERENCES v2_research_results(run_id) DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE v2_research_operations (
 operation varchar(16) NOT NULL CHECK(operation='cancel'),
 protocol varchar(48) NOT NULL CHECK(protocol='research-spec-v2'),
 idempotency_key varchar(128) NOT NULL CHECK(idempotency_key ~ '^[A-Za-z0-9_.-]{1,128}$'),
 request_sha256 varchar(64) NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
 run_id uuid NOT NULL REFERENCES v2_research_runs,
 response_json text NOT NULL CHECK(octet_length(response_json)<=65536),
 created_at timestamptz NOT NULL, PRIMARY KEY(operation,protocol,idempotency_key)
);
CREATE TABLE v2_research_reservations (
 reservation_id uuid PRIMARY KEY, run_id uuid REFERENCES v2_research_runs, owner uuid NOT NULL,
 purpose varchar(16) NOT NULL CHECK(purpose IN ('preparation','attempt')),
 state varchar(16) NOT NULL CHECK(state IN ('active','retained','released')),
 scratch_bytes bigint NOT NULL CHECK(scratch_bytes>=0),
 spill_bytes bigint NOT NULL CHECK(spill_bytes>=0),
 output_bytes bigint NOT NULL CHECK(output_bytes>=0), relative_root text NOT NULL UNIQUE,
 created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL, released_at timestamptz,
 CHECK((state='released')=(released_at IS NOT NULL)),
 CHECK(state<>'released' OR scratch_bytes+spill_bytes+output_bytes=0)
);
CREATE INDEX ix_v2_research_due ON v2_research_runs(state,eligible_at,created_at,run_id);
CREATE INDEX ix_v2_research_lease ON v2_research_runs(state,lease_until,run_id);
CREATE INDEX ix_v2_research_execution ON v2_research_submissions(execution_sha256,created_at);
CREATE INDEX ix_v2_research_dataset ON v2_research_selections(dataset_version_id);
CREATE INDEX ix_v2_research_attempt ON v2_research_attempts(run_id,started_at);
CREATE INDEX ix_v2_research_reservation ON v2_research_reservations(state,reservation_id);
"""


def upgrade() -> None:
    for statement in DDL.split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    raise RuntimeError("V2 research is forward-only; restore a verified backup separately")
