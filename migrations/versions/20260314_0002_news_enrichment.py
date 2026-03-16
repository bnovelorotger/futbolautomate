"""add news editorial enrichment table"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260314_0002"
down_revision = "20260314_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_enrichments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("news_id", sa.Integer(), sa.ForeignKey("news.id"), nullable=False),
        sa.Column("sport_detected", sa.String(length=80), nullable=True),
        sa.Column("is_football", sa.Boolean(), nullable=False),
        sa.Column("is_balearic_related", sa.Boolean(), nullable=False),
        sa.Column("clubs_detected", sa.JSON(), nullable=True),
        sa.Column("competition_detected", sa.String(length=255), nullable=True),
        sa.Column("editorial_relevance_score", sa.Integer(), nullable=False),
        sa.Column("signals", sa.JSON(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("news_id", name="uq_news_enrichments_news_id"),
    )
    op.create_index("ix_news_enrichments_news_id", "news_enrichments", ["news_id"])
    op.create_index("ix_news_enrichments_sport_detected", "news_enrichments", ["sport_detected"])
    op.create_index("ix_news_enrichments_is_football", "news_enrichments", ["is_football"])
    op.create_index(
        "ix_news_enrichments_is_balearic_related",
        "news_enrichments",
        ["is_balearic_related"],
    )
    op.create_index(
        "ix_news_enrichments_competition_detected",
        "news_enrichments",
        ["competition_detected"],
    )
    op.create_index(
        "ix_news_enrichments_editorial_relevance_score",
        "news_enrichments",
        ["editorial_relevance_score"],
    )


def downgrade() -> None:
    op.drop_index("ix_news_enrichments_editorial_relevance_score", table_name="news_enrichments")
    op.drop_index("ix_news_enrichments_competition_detected", table_name="news_enrichments")
    op.drop_index("ix_news_enrichments_is_balearic_related", table_name="news_enrichments")
    op.drop_index("ix_news_enrichments_is_football", table_name="news_enrichments")
    op.drop_index("ix_news_enrichments_sport_detected", table_name="news_enrichments")
    op.drop_index("ix_news_enrichments_news_id", table_name="news_enrichments")
    op.drop_table("news_enrichments")
