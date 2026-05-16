"""add publication attempt counter to content candidates"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260516_0015"
down_revision = "20260512_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_candidates",
        sa.Column("publication_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("content_candidates", "publication_attempts", server_default=None)


def downgrade() -> None:
    op.drop_column("content_candidates", "publication_attempts")
