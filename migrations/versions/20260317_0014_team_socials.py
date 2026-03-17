"""add team_socials table

Revision ID: 20260317_0014
Revises: 20260317_0013
Create Date: 2026-03-17 16:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260317_0014"
down_revision = "20260317_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "team_socials" not in existing_tables:
        op.create_table(
            "team_socials",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("team_name", sa.String(length=255), nullable=False),
            sa.Column("competition_slug", sa.String(length=120), nullable=True),
            sa.Column("x_handle", sa.String(length=120), nullable=True),
            sa.Column("followers_approx", sa.Integer(), nullable=True),
            sa.Column("activity_level", sa.String(length=20), nullable=False, server_default="media"),
            sa.Column("is_shared_handle", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("team_name", "competition_slug", name="uq_team_socials_team_competition"),
        )

    existing_indexes = {index["name"] for index in inspector.get_indexes("team_socials")}
    if "ix_team_socials_team_name" not in existing_indexes:
        op.create_index("ix_team_socials_team_name", "team_socials", ["team_name"])
    if "ix_team_socials_competition_slug" not in existing_indexes:
        op.create_index("ix_team_socials_competition_slug", "team_socials", ["competition_slug"])
    if "ix_team_socials_team_name_competition" not in existing_indexes:
        op.create_index(
            "ix_team_socials_team_name_competition",
            "team_socials",
            ["team_name", "competition_slug"],
        )
    if "ix_team_socials_x_handle" not in existing_indexes:
        op.create_index("ix_team_socials_x_handle", "team_socials", ["x_handle"])
    if "ix_team_socials_activity_level" not in existing_indexes:
        op.create_index("ix_team_socials_activity_level", "team_socials", ["activity_level"])
    if "ix_team_socials_is_active" not in existing_indexes:
        op.create_index("ix_team_socials_is_active", "team_socials", ["is_active"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "team_socials" not in inspector.get_table_names():
        return
    existing_indexes = {index["name"] for index in inspector.get_indexes("team_socials")}
    for index_name in (
        "ix_team_socials_is_active",
        "ix_team_socials_activity_level",
        "ix_team_socials_x_handle",
        "ix_team_socials_team_name_competition",
        "ix_team_socials_competition_slug",
        "ix_team_socials_team_name",
    ):
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name="team_socials")
    op.drop_table("team_socials")
