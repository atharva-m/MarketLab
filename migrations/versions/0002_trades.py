"""Persist the five-field synthetic execution contract."""

import sqlalchemy as sa
from alembic import op

revision = "0002_trades"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trades",
        sa.Column("trade_id", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Numeric(20, 8), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False),
        sa.PrimaryKeyConstraint("trade_id", name="trades_pkey"),
    )


def downgrade() -> None:
    op.drop_table("trades")
