"""add generic external channel export tracking fields"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260315_0008"
down_revision = "20260315_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_candidates",
        sa.Column("external_channel", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "content_candidates",
        sa.Column("external_exported_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_content_candidates_external_channel"),
        "content_candidates",
        ["external_channel"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_content_candidates_external_channel"), table_name="content_candidates")
    op.drop_column("content_candidates", "external_exported_at")
    op.drop_column("content_candidates", "external_channel")
