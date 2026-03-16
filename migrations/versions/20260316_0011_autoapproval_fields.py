"""add editorial autoapproval tracking fields to content candidates"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260316_0011"
down_revision = "20260316_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_candidates",
        sa.Column("autoapproved", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "content_candidates",
        sa.Column("autoapproved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "content_candidates",
        sa.Column("autoapproval_reason", sa.String(length=255), nullable=True),
    )
    op.create_index(
        op.f("ix_content_candidates_autoapproved"),
        "content_candidates",
        ["autoapproved"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_content_candidates_autoapproved"), table_name="content_candidates")
    op.drop_column("content_candidates", "autoapproval_reason")
    op.drop_column("content_candidates", "autoapproved_at")
    op.drop_column("content_candidates", "autoapproved")
