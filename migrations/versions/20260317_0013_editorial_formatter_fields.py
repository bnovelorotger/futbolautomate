"""editorial formatter fields and team mentions"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260317_0013"
down_revision = "20260316_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_candidates", sa.Column("formatted_text", sa.Text(), nullable=True))

    op.create_table(
        "team_mentions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_name", sa.String(length=255), nullable=False),
        sa.Column("twitter_handle", sa.String(length=120), nullable=False),
        sa.Column("competition_slug", sa.String(length=120), sa.ForeignKey("competitions.code"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("competition_slug", "team_name", name="uq_team_mentions_competition_team"),
    )
    op.create_index("ix_team_mentions_team_name", "team_mentions", ["team_name"])
    op.create_index("ix_team_mentions_competition_slug", "team_mentions", ["competition_slug"])


def downgrade() -> None:
    op.drop_index("ix_team_mentions_competition_slug", table_name="team_mentions")
    op.drop_index("ix_team_mentions_team_name", table_name="team_mentions")
    op.drop_table("team_mentions")
    op.drop_column("content_candidates", "formatted_text")
