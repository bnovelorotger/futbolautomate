"""standings snapshots history"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260316_0012"
down_revision = "20260316_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "standings_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_name", sa.String(length=50), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("competition_id", sa.Integer(), sa.ForeignKey("competitions.id"), nullable=False),
        sa.Column("scraper_run_id", sa.Integer(), sa.ForeignKey("scraper_runs.id"), nullable=True),
        sa.Column("season", sa.String(length=50), nullable=True),
        sa.Column("group_name", sa.String(length=120), nullable=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("snapshot_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("team_raw", sa.String(length=255), nullable=False),
        sa.Column("played", sa.Integer(), nullable=True),
        sa.Column("wins", sa.Integer(), nullable=True),
        sa.Column("draws", sa.Integer(), nullable=True),
        sa.Column("losses", sa.Integer(), nullable=True),
        sa.Column("goals_for", sa.Integer(), nullable=True),
        sa.Column("goals_against", sa.Integer(), nullable=True),
        sa.Column("goal_difference", sa.Integer(), nullable=True),
        sa.Column("points", sa.Integer(), nullable=True),
        sa.Column("form_text", sa.String(length=50), nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_name",
            "competition_id",
            "season",
            "group_name",
            "team_raw",
            "snapshot_timestamp",
            name="uq_standings_snapshots_team_timestamp",
        ),
    )
    op.create_index("ix_standings_snapshots_competition_id", "standings_snapshots", ["competition_id"])
    op.create_index("ix_standings_snapshots_scraper_run_id", "standings_snapshots", ["scraper_run_id"])
    op.create_index("ix_standings_snapshots_snapshot_date", "standings_snapshots", ["snapshot_date"])
    op.create_index(
        "ix_standings_snapshots_snapshot_timestamp",
        "standings_snapshots",
        ["snapshot_timestamp"],
    )
    op.create_index("ix_standings_snapshots_source_name", "standings_snapshots", ["source_name"])
    op.create_index("ix_standings_snapshots_content_hash", "standings_snapshots", ["content_hash"])


def downgrade() -> None:
    op.drop_index("ix_standings_snapshots_content_hash", table_name="standings_snapshots")
    op.drop_index("ix_standings_snapshots_source_name", table_name="standings_snapshots")
    op.drop_index("ix_standings_snapshots_snapshot_timestamp", table_name="standings_snapshots")
    op.drop_index("ix_standings_snapshots_snapshot_date", table_name="standings_snapshots")
    op.drop_index("ix_standings_snapshots_scraper_run_id", table_name="standings_snapshots")
    op.drop_index("ix_standings_snapshots_competition_id", table_name="standings_snapshots")
    op.drop_table("standings_snapshots")
