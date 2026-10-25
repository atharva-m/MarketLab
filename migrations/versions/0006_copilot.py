"""Additive durable inbound copilot records."""

from alembic import op

revision = "0006_copilot"
down_revision = "0005_research"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE copilot_requests (
      request_id varchar(36) PRIMARY KEY, idempotency_key varchar(128) NOT NULL UNIQUE
        CHECK(idempotency_key ~ '^[A-Za-z0-9_.-]{1,128}$'),
      request_sha256 varchar(64) NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
      body text NOT NULL, current_revision integer NOT NULL CHECK(current_revision BETWEEN 0 AND 5),
      run_id varchar(36) UNIQUE REFERENCES research_runs,
      created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL)""")
    op.execute("""CREATE TABLE copilot_revisions (
      request_id varchar(36) REFERENCES copilot_requests,
      revision integer CHECK(revision BETWEEN 0 AND 5),
      body text NOT NULL, body_sha256 varchar(64) NOT NULL CHECK(body_sha256 ~ '^[0-9a-f]{64}$'),
      answer_key varchar(128) CHECK(answer_key ~ '^[A-Za-z0-9_.-]{1,128}$'),
      outcome varchar(24) CHECK(outcome IN
        ('submitted','needs_clarification','unsupported','failed')),
      interpretation text, provenance text, questions text, spec text,
      created_at timestamptz NOT NULL,
      PRIMARY KEY(request_id,revision), UNIQUE(request_id,answer_key),
      CHECK((revision=0)=(answer_key IS NULL)))""")
    op.execute("""CREATE TABLE copilot_jobs (
      job_id varchar(36) PRIMARY KEY, request_id varchar(36) NOT NULL, revision integer NOT NULL,
      FOREIGN KEY(request_id,revision) REFERENCES copilot_revisions,
      UNIQUE(request_id,revision), state varchar(16) NOT NULL
        CHECK(state IN ('queued','running','retry_wait','completed','failed')),
      attempt_count integer NOT NULL CHECK(attempt_count BETWEEN 0 AND 3),
      model_calls integer NOT NULL CHECK(model_calls BETWEEN 0 AND 2),
      fencing_token bigint NOT NULL CHECK(fencing_token>=0), owner varchar(36),
      lease_until timestamptz,
      eligible_at timestamptz NOT NULL, error varchar(160), created_at timestamptz NOT NULL,
      updated_at timestamptz NOT NULL,
      CHECK((state='running')=(owner IS NOT NULL AND lease_until IS NOT NULL)),
      CHECK(state='running' OR (owner IS NULL AND lease_until IS NULL)))""")
    op.execute("""CREATE TABLE copilot_attempts (
      job_id varchar(36) REFERENCES copilot_jobs,
      attempt_number integer CHECK(attempt_number BETWEEN 1 AND 3),
      fencing_token bigint NOT NULL CHECK(fencing_token>0), owner varchar(36) NOT NULL,
      started_at timestamptz NOT NULL, ended_at timestamptz,
      outcome varchar(16) NOT NULL CHECK(outcome IN
        ('running','completed','transient','permanent','expired')),
      error varchar(160), PRIMARY KEY(job_id,attempt_number), UNIQUE(job_id,fencing_token),
      CHECK((outcome='running')=(ended_at IS NULL)))""")


def downgrade() -> None:
    for name in ("copilot_attempts", "copilot_jobs", "copilot_revisions", "copilot_requests"):
        op.drop_table(name)
