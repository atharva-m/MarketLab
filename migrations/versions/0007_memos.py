"""Additive durable supplemental memos."""

from alembic import op

revision = "0007_memos"
down_revision = "0006_copilot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE memo_jobs (
      run_id varchar(36) PRIMARY KEY REFERENCES research_runs,
      FOREIGN KEY(run_id) REFERENCES research_results,
      numerical_manifest_sha256 varchar(64) NOT NULL
        CHECK(numerical_manifest_sha256 ~ '^[0-9a-f]{64}$'),
      summary_sha256 varchar(64) NOT NULL CHECK(summary_sha256 ~ '^[0-9a-f]{64}$'),
      execution text, execution_sha256 varchar(64)
        CHECK(execution_sha256 ~ '^[0-9a-f]{64}$'),
      state varchar(16) NOT NULL CHECK(state IN ('queued','running','retry_wait','ready','failed')),
      attempt_count integer NOT NULL CHECK(attempt_count BETWEEN 0 AND 3),
      model_calls integer NOT NULL CHECK(model_calls BETWEEN 0 AND 2),
      fencing_token bigint NOT NULL CHECK(fencing_token>=0), owner varchar(36),
      lease_until timestamptz,
      eligible_at timestamptz NOT NULL, error varchar(160), draft text, provenance text,
      result_sha256 varchar(64) CHECK(result_sha256 ~ '^[0-9a-f]{64}$'),
      created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
      CHECK((execution IS NULL)=(execution_sha256 IS NULL)),
      CHECK((state='running')=(owner IS NOT NULL AND lease_until IS NOT NULL)),
      CHECK(state='running' OR (owner IS NULL AND lease_until IS NULL)),
      CHECK((state='ready')=(result_sha256 IS NOT NULL)))""")
    op.execute("""CREATE TABLE memo_attempts (
      run_id varchar(36) REFERENCES memo_jobs,
      attempt_number integer CHECK(attempt_number BETWEEN 1 AND 3),
      fencing_token bigint NOT NULL CHECK(fencing_token>0), owner varchar(36) NOT NULL,
      started_at timestamptz NOT NULL, ended_at timestamptz,
      outcome varchar(16) NOT NULL CHECK(outcome IN
        ('running','ready','transient','permanent','expired')),
      error varchar(160), PRIMARY KEY(run_id,attempt_number), UNIQUE(run_id,fencing_token),
      CHECK((outcome='running')=(ended_at IS NULL)))""")
    op.execute("""CREATE TABLE memo_results (
      run_id varchar(36) PRIMARY KEY REFERENCES memo_jobs,
      manifest_path text NOT NULL, manifest_sha256 varchar(64) NOT NULL
        CHECK(manifest_sha256 ~ '^[0-9a-f]{64}$'),
      memo_sha256 varchar(64) NOT NULL CHECK(memo_sha256 ~ '^[0-9a-f]{64}$'),
      summary_sha256 varchar(64) NOT NULL CHECK(summary_sha256 ~ '^[0-9a-f]{64}$'),
      registered_at timestamptz NOT NULL)""")


def downgrade() -> None:
    for name in ("memo_results", "memo_attempts", "memo_jobs"):
        op.drop_table(name)
