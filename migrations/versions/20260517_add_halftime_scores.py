"""add halftime score columns to matches"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260517_0017"
down_revision = "20260516_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("halftime_home_score", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("halftime_away_score", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "halftime_away_score")
    op.drop_column("matches", "halftime_home_score")
