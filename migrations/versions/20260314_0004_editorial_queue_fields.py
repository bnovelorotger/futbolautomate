"""add editorial queue fields to content candidates"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260314_0004"
down_revision = "20260314_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_candidates", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("content_candidates", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("content_candidates", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("content_candidates", sa.Column("rejection_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("content_candidates", "rejection_reason")
    op.drop_column("content_candidates", "published_at")
    op.drop_column("content_candidates", "approved_at")
    op.drop_column("content_candidates", "reviewed_at")
