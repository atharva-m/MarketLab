"""Register complete immutable historical dataset versions separately from trades."""

import sqlalchemy as sa
from alembic import op

revision = "0003_dataset_versions"
down_revision = "0002_trades"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dataset_versions",
        sa.Column("dataset_version_id", sa.String(64), primary_key=True),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("manifest_path", sa.Text, nullable=False, unique=True),
        sa.Column("venue", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("trade_date", sa.Date, nullable=False),
        sa.Column("row_count", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("dataset_version_id ~ '^[0-9a-f]{64}$'", name="dataset_version_hex"),
        sa.CheckConstraint("source_sha256 ~ '^[0-9a-f]{64}$'", name="dataset_source_hex"),
        sa.CheckConstraint("manifest_sha256 ~ '^[0-9a-f]{64}$'", name="dataset_manifest_hex"),
        sa.CheckConstraint("row_count >= 0", name="dataset_nonnegative_rows"),
        sa.CheckConstraint("status = 'published'", name="dataset_published_only"),
    )


def downgrade() -> None:
    op.drop_table("dataset_versions")
