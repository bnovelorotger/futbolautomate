"""add x publication tracking fields to content candidates"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260315_0006"
down_revision = "20260314_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_candidates",
        sa.Column("external_publication_timestamp", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "content_candidates",
        sa.Column("external_publication_attempted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "content_candidates",
        sa.Column("external_publication_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("content_candidates", "external_publication_error")
    op.drop_column("content_candidates", "external_publication_attempted_at")
    op.drop_column("content_candidates", "external_publication_timestamp")
