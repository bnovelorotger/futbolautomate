"""add publication dispatch fields to content candidates"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260314_0005"
down_revision = "20260314_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_candidates", sa.Column("external_publication_ref", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("content_candidates", "external_publication_ref")
