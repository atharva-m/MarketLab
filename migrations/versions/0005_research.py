"""Separate deterministic research records; retain all R1-R3 schemas."""

from alembic import op

revision = "0005_research"
down_revision = "0004_ingestion_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE research_submissions (
      submission_id varchar(36) PRIMARY KEY, idempotency_key varchar(128) NOT NULL UNIQUE,
      request_sha256 varchar(64) NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
      spec text NOT NULL, fingerprint text NOT NULL,
      fingerprint_sha256 varchar(64) NOT NULL CHECK(fingerprint_sha256 ~ '^[0-9a-f]{64}$'),
      created_at timestamptz NOT NULL,
      CHECK(idempotency_key ~ '^[A-Za-z0-9_.-]{1,128}$'))""")
    op.execute("""CREATE TABLE research_runs (
      run_id varchar(36) PRIMARY KEY,
      submission_id varchar(36) NOT NULL UNIQUE REFERENCES research_submissions,
      state varchar(16) NOT NULL
        CHECK(state IN ('queued','running','retry_wait','succeeded','failed')),
      attempt_count integer NOT NULL CHECK(attempt_count BETWEEN 0 AND 3),
      fencing_token bigint NOT NULL CHECK(fencing_token >= 0),
      owner varchar(36), lease_until timestamptz,
      eligible_at timestamptz NOT NULL, result_id varchar(36), error varchar(160),
      created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
      CHECK((state='running' AND owner IS NOT NULL AND lease_until IS NOT NULL) OR
            (state<>'running' AND owner IS NULL AND lease_until IS NULL)),
      CHECK((state='succeeded')=(result_id IS NOT NULL)),
      CHECK(result_id IS NULL OR result_id=run_id))""")
    op.execute("""CREATE TABLE research_attempts (
      run_id varchar(36) REFERENCES research_runs,
      attempt_number integer CHECK(attempt_number BETWEEN 1 AND 3),
      fencing_token bigint NOT NULL CHECK(fencing_token>0), owner varchar(36) NOT NULL,
      started_at timestamptz NOT NULL, ended_at timestamptz,
      outcome varchar(16) NOT NULL
        CHECK(outcome IN ('running','succeeded','transient','permanent','expired')),
      error varchar(160), PRIMARY KEY(run_id,attempt_number), UNIQUE(run_id,fencing_token),
      CHECK((outcome='running')=(ended_at IS NULL)))""")
    op.execute("""CREATE TABLE research_results (
      run_id varchar(36) PRIMARY KEY REFERENCES research_runs,
      manifest_sha256 varchar(64) NOT NULL CHECK(manifest_sha256 ~ '^[0-9a-f]{64}$'),
      manifest_path text NOT NULL,
      results_sha256 varchar(64) NOT NULL CHECK(results_sha256 ~ '^[0-9a-f]{64}$'),
      summary_sha256 varchar(64) NOT NULL CHECK(summary_sha256 ~ '^[0-9a-f]{64}$'),
      registered_at timestamptz NOT NULL)""")
    op.execute("CREATE INDEX ix_research_claim ON research_runs(state,eligible_at,lease_until)")


def downgrade() -> None:
    for table in ("research_results", "research_attempts", "research_runs", "research_submissions"):
        op.drop_table(table)
