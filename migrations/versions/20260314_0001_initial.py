"""initial schema"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260314_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "competitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("category_level", sa.Integer(), nullable=True),
        sa.Column("gender", sa.String(length=20), nullable=False),
        sa.Column("region", sa.String(length=120), nullable=True),
        sa.Column("country", sa.String(length=120), nullable=False),
        sa.Column("federation", sa.String(length=120), nullable=True),
        sa.Column("source_name", sa.String(length=50), nullable=True),
        sa.Column("source_competition_id", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("normalized_name"),
    )
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("island", sa.String(length=120), nullable=True),
        sa.Column("municipality", sa.String(length=120), nullable=True),
        sa.Column("gender", sa.String(length=20), nullable=False),
        sa.Column("source_name", sa.String(length=50), nullable=True),
        sa.Column("source_team_id", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("normalized_name"),
    )
    op.create_table(
        "news",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_name", sa.String(length=50), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("subtitle", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("news_type", sa.String(length=40), nullable=False),
        sa.Column("clubs_detected", sa.JSON(), nullable=True),
        sa.Column("competition_detected", sa.String(length=255), nullable=True),
        sa.Column("raw_category", sa.String(length=255), nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_name", "source_url"),
    )
    op.create_table(
        "scraper_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scraper_name", sa.String(length=120), nullable=False),
        sa.Column("source_name", sa.String(length=50), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("competition_code", sa.String(length=120), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("records_found", sa.Integer(), nullable=False),
        sa.Column("records_inserted", sa.Integer(), nullable=False),
        sa.Column("records_updated", sa.Integer(), nullable=False),
        sa.Column("errors_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_id", sa.String(length=120), nullable=True),
        sa.Column("source_name", sa.String(length=50), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("competition_id", sa.Integer(), sa.ForeignKey("competitions.id"), nullable=False),
        sa.Column("season", sa.String(length=50), nullable=True),
        sa.Column("group_name", sa.String(length=120), nullable=True),
        sa.Column("round_name", sa.String(length=120), nullable=True),
        sa.Column("raw_match_date", sa.String(length=120), nullable=True),
        sa.Column("raw_match_time", sa.String(length=120), nullable=True),
        sa.Column("match_date", sa.Date(), nullable=True),
        sa.Column("match_time", sa.Time(), nullable=True),
        sa.Column("kickoff_datetime", sa.DateTime(timezone=True), nullable=True),
        sa.Column("home_team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("away_team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("home_team_raw", sa.String(length=255), nullable=False),
        sa.Column("away_team_raw", sa.String(length=255), nullable=False),
        sa.Column("home_score", sa.Integer(), nullable=True),
        sa.Column("away_score", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("venue", sa.String(length=255), nullable=True),
        sa.Column("has_lineups", sa.Boolean(), nullable=False),
        sa.Column("has_scorers", sa.Boolean(), nullable=False),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_name", "external_id", name="uq_matches_source_external_id"),
        sa.UniqueConstraint("source_name", "source_url", name="uq_matches_source_url"),
    )
    op.create_table(
        "standings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_name", sa.String(length=50), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("competition_id", sa.Integer(), sa.ForeignKey("competitions.id"), nullable=False),
        sa.Column("season", sa.String(length=50), nullable=True),
        sa.Column("group_name", sa.String(length=120), nullable=True),
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
        sa.UniqueConstraint("source_name", "competition_id", "season", "group_name", "team_raw"),
    )


def downgrade() -> None:
    op.drop_table("standings")
    op.drop_table("matches")
    op.drop_table("scraper_runs")
    op.drop_table("news")
    op.drop_table("teams")
    op.drop_table("competitions")
