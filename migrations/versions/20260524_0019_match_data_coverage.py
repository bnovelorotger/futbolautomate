"""add generic match data coverage table"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260524_0019"
down_revision = "20260523_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "match_data_coverage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("data_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("source_name", sa.String(length=50), nullable=True),
        sa.Column("expected_count", sa.Integer(), nullable=True),
        sa.Column("observed_count", sa.Integer(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], name="fk_match_data_coverage_match_id_matches"),
        sa.PrimaryKeyConstraint("id", name="pk_match_data_coverage"),
        sa.UniqueConstraint("match_id", "data_type", name="uq_match_data_coverage_match_type"),
    )
    op.create_index(
        "ix_match_data_coverage_match_id",
        "match_data_coverage",
        ["match_id"],
    )
    op.create_index(
        "ix_match_data_coverage_data_type",
        "match_data_coverage",
        ["data_type"],
    )
    op.create_index(
        "ix_match_data_coverage_status",
        "match_data_coverage",
        ["status"],
    )
    op.create_index(
        "ix_match_data_coverage_type_status",
        "match_data_coverage",
        ["data_type", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_match_data_coverage_type_status", table_name="match_data_coverage")
    op.drop_index("ix_match_data_coverage_status", table_name="match_data_coverage")
    op.drop_index("ix_match_data_coverage_data_type", table_name="match_data_coverage")
    op.drop_index("ix_match_data_coverage_match_id", table_name="match_data_coverage")
    op.drop_table("match_data_coverage")
