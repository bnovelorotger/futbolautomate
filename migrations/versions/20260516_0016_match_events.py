"""add match events table"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260516_0016"
down_revision = "20260516_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "match_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("team_side", sa.String(length=10), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("period", sa.String(length=60), nullable=True),
        sa.Column("minute_raw", sa.String(length=20), nullable=True),
        sa.Column("minute", sa.Integer(), nullable=True),
        sa.Column("minute_extra", sa.Integer(), nullable=True),
        sa.Column("player_raw", sa.String(length=255), nullable=True),
        sa.Column("player_source_url", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_event_key", sa.String(length=255), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("match_id", "source_event_key", name="uq_match_events_match_source_key"),
    )
    op.create_index("ix_match_events_match_sort_order", "match_events", ["match_id", "sort_order"])
    op.create_index("ix_match_events_team_event_type", "match_events", ["team_id", "event_type"])
    op.alter_column("match_events", "sort_order", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_match_events_team_event_type", table_name="match_events")
    op.drop_index("ix_match_events_match_sort_order", table_name="match_events")
    op.drop_table("match_events")
