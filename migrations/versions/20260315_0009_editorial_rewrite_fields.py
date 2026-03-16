"""add editorial rewrite tracking fields to content candidates"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260315_0009"
down_revision = "20260315_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_candidates",
        sa.Column("rewritten_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "content_candidates",
        sa.Column("rewrite_status", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "content_candidates",
        sa.Column("rewrite_model", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "content_candidates",
        sa.Column("rewrite_timestamp", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "content_candidates",
        sa.Column("rewrite_error", sa.Text(), nullable=True),
    )
    op.create_index(
        op.f("ix_content_candidates_rewrite_status"),
        "content_candidates",
        ["rewrite_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_content_candidates_rewrite_status"), table_name="content_candidates")
    op.drop_column("content_candidates", "rewrite_error")
    op.drop_column("content_candidates", "rewrite_timestamp")
    op.drop_column("content_candidates", "rewrite_model")
    op.drop_column("content_candidates", "rewrite_status")
    op.drop_column("content_candidates", "rewritten_text")
