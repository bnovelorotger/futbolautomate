"""add scorer coverage status to matches"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260523_0018"
down_revision = "20260517_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column(
            "scorer_status",
            sa.String(length=30),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "matches",
        sa.Column("scorer_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_matches_scorer_status", "matches", ["scorer_status"])
    op.execute("UPDATE matches SET scorer_status = 'covered' WHERE has_scorers IS TRUE")


def downgrade() -> None:
    op.drop_index("ix_matches_scorer_status", table_name="matches")
    op.drop_column("matches", "scorer_checked_at")
    op.drop_column("matches", "scorer_status")
