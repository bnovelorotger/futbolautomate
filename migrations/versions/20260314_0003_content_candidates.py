"""add content candidates table"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260314_0003"
down_revision = "20260314_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("competition_slug", sa.String(length=120), sa.ForeignKey("competitions.code"), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("text_draft", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("source_summary_hash", sa.String(length=64), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "competition_slug",
            "content_type",
            "source_summary_hash",
            name="uq_content_candidates_slug_type_hash",
        ),
    )
    op.create_index("ix_content_candidates_competition_slug", "content_candidates", ["competition_slug"])
    op.create_index("ix_content_candidates_content_type", "content_candidates", ["content_type"])
    op.create_index("ix_content_candidates_priority", "content_candidates", ["priority"])
    op.create_index("ix_content_candidates_source_summary_hash", "content_candidates", ["source_summary_hash"])
    op.create_index("ix_content_candidates_status", "content_candidates", ["status"])


def downgrade() -> None:
    op.drop_index("ix_content_candidates_status", table_name="content_candidates")
    op.drop_index("ix_content_candidates_source_summary_hash", table_name="content_candidates")
    op.drop_index("ix_content_candidates_priority", table_name="content_candidates")
    op.drop_index("ix_content_candidates_content_type", table_name="content_candidates")
    op.drop_index("ix_content_candidates_competition_slug", table_name="content_candidates")
    op.drop_table("content_candidates")
