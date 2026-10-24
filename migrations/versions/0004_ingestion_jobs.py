"""Add bounded durable ingestion submissions, attempts and fenced ownership."""

import sqlalchemy as sa
from alembic import op

revision = "0004_ingestion_jobs"
down_revision = "0003_dataset_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_submissions",
        sa.Column("submission_id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("symbols", sa.Text, nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("before_date", sa.Date, nullable=False),
        sa.Column("execution_contract", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="submission_request_hash"),
        sa.CheckConstraint(
            "start_date >= DATE '2025-01-01' AND start_date < before_date "
            "AND before_date <= DATE '2025-02-01'",
            name="submission_date_bounds",
        ),
    )
    op.create_table(
        "ingestion_jobs",
        sa.Column("job_id", sa.String(36), primary_key=True),
        sa.Column(
            "submission_id",
            sa.String(36),
            sa.ForeignKey("ingestion_submissions.submission_id"),
            nullable=False,
        ),
        sa.Column("venue", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("trade_date", sa.Date, nullable=False),
        sa.Column("source_mode", sa.String(16), nullable=False),
        sa.Column("input_sha256", sa.String(64)),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("attempt_count", sa.Integer, nullable=False),
        sa.Column("fencing_token", sa.BigInteger, nullable=False),
        sa.Column("owner", sa.String(36)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("eligible_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "result_version", sa.String(64), sa.ForeignKey("dataset_versions.dataset_version_id")
        ),
        sa.Column("error", sa.String(160)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("submission_id", "symbol", "trade_date", name="job_submission_day"),
        sa.CheckConstraint(
            "venue = 'binance_spot' AND symbol IN ('BTCUSDT','ETHUSDT') "
            "AND trade_date >= DATE '2025-01-01' AND trade_date < DATE '2025-02-01'",
            name="job_source_scope",
        ),
        sa.CheckConstraint(
            "source_mode IN ('official','inline','fixture') AND ((source_mode = 'fixture' "
            "AND input_sha256 IS NOT NULL AND input_sha256 ~ '^[0-9a-f]{64}$') "
            "OR (source_mode IN ('official','inline') AND input_sha256 IS NULL))",
            name="job_source_mode",
        ),
        sa.CheckConstraint(
            "state IN ('queued','running','retry_wait','succeeded','failed')", name="job_state"
        ),
        sa.CheckConstraint(
            "attempt_count BETWEEN 0 AND 3 AND fencing_token >= 0", name="job_attempt_bounds"
        ),
        sa.CheckConstraint(
            "(state = 'running' AND owner IS NOT NULL AND lease_until IS NOT NULL) "
            "OR (state <> 'running' AND owner IS NULL AND lease_until IS NULL)",
            name="job_ownership",
        ),
        sa.CheckConstraint(
            "(state = 'succeeded') = (result_version IS NOT NULL)", name="job_success_result"
        ),
    )
    op.create_index(
        "ix_ingestion_jobs_claim", "ingestion_jobs", ["state", "eligible_at", "lease_until"]
    )
    op.create_table(
        "ingestion_attempts",
        sa.Column(
            "job_id", sa.String(36), sa.ForeignKey("ingestion_jobs.job_id"), primary_key=True
        ),
        sa.Column("attempt_number", sa.Integer, primary_key=True),
        sa.Column("fencing_token", sa.BigInteger, nullable=False),
        sa.Column("owner", sa.String(36), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("error", sa.String(160)),
        sa.UniqueConstraint("job_id", "fencing_token", name="attempt_token"),
        sa.CheckConstraint(
            "attempt_number BETWEEN 1 AND 3 AND fencing_token > 0", name="attempt_bounds"
        ),
        sa.CheckConstraint(
            "outcome IN ('running','succeeded','transient','permanent','expired')",
            name="attempt_outcome",
        ),
        sa.CheckConstraint("(outcome = 'running') = (ended_at IS NULL)", name="attempt_finished"),
    )


def downgrade() -> None:
    op.drop_table("ingestion_attempts")
    op.drop_table("ingestion_jobs")
    op.drop_table("ingestion_submissions")
