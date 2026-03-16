"""add editorial quality check tracking fields to content candidates"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260316_0010"
down_revision = "20260315_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_candidates",
        sa.Column("quality_check_passed", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "content_candidates",
        sa.Column("quality_check_errors", sa.JSON(), nullable=True),
    )
    op.add_column(
        "content_candidates",
        sa.Column("quality_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_content_candidates_quality_check_passed"),
        "content_candidates",
        ["quality_check_passed"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_content_candidates_quality_check_passed"), table_name="content_candidates")
    op.drop_column("content_candidates", "quality_checked_at")
    op.drop_column("content_candidates", "quality_check_errors")
    op.drop_column("content_candidates", "quality_check_passed")
