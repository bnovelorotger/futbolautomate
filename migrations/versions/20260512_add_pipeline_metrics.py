"""add pipeline_metrics table

Revision ID: 20260512_0015
Revises: 20260317_0014
Create Date: 2026-05-12 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260512_0015"
down_revision = "20260317_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "pipeline_metrics" not in existing_tables:
        op.create_table(
            "pipeline_metrics",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("run_date", sa.Date(), nullable=False),
            sa.Column("pipeline_name", sa.String(length=120), nullable=False),
            sa.Column("candidates_generated", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("candidates_approved", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("candidates_autoapproved", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("candidates_rejected", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("candidates_published", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("quality_check_failures", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("run_duration_seconds", sa.Float(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("run_date", "pipeline_name", name="uq_pipeline_metrics_date_pipeline"),
        )

    existing_indexes = {index["name"] for index in inspector.get_indexes("pipeline_metrics")}
    if "ix_pipeline_metrics_run_date" not in existing_indexes:
        op.create_index("ix_pipeline_metrics_run_date", "pipeline_metrics", ["run_date"])
    if "ix_pipeline_metrics_pipeline_name" not in existing_indexes:
        op.create_index("ix_pipeline_metrics_pipeline_name", "pipeline_metrics", ["pipeline_name"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "pipeline_metrics" not in inspector.get_table_names():
        return
    existing_indexes = {index["name"] for index in inspector.get_indexes("pipeline_metrics")}
    for index_name in (
        "ix_pipeline_metrics_pipeline_name",
        "ix_pipeline_metrics_run_date",
    ):
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name="pipeline_metrics")
    op.drop_table("pipeline_metrics")
