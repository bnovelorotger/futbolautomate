"""add x oauth pkce support tables"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260315_0007"
down_revision = "20260315_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_auth_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("state", sa.String(length=255), nullable=False),
        sa.Column("code_verifier", sa.String(length=255), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channel_auth_sessions")),
        sa.UniqueConstraint("provider", "state", name="uq_channel_auth_sessions_provider_state"),
    )
    op.create_index(op.f("ix_channel_auth_sessions_provider"), "channel_auth_sessions", ["provider"], unique=False)
    op.create_index(op.f("ix_channel_auth_sessions_state"), "channel_auth_sessions", ["state"], unique=False)
    op.create_index(op.f("ix_channel_auth_sessions_expires_at"), "channel_auth_sessions", ["expires_at"], unique=False)

    op.create_table(
        "channel_user_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_type", sa.String(length=50), nullable=True),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("subject_id", sa.String(length=255), nullable=True),
        sa.Column("subject_username", sa.String(length=255), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channel_user_tokens")),
        sa.UniqueConstraint("provider", name="uq_channel_user_tokens_provider"),
    )
    op.create_index(op.f("ix_channel_user_tokens_provider"), "channel_user_tokens", ["provider"], unique=False)
    op.create_index(op.f("ix_channel_user_tokens_expires_at"), "channel_user_tokens", ["expires_at"], unique=False)
    op.create_index(op.f("ix_channel_user_tokens_subject_id"), "channel_user_tokens", ["subject_id"], unique=False)
    op.create_index(
        op.f("ix_channel_user_tokens_subject_username"),
        "channel_user_tokens",
        ["subject_username"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_channel_user_tokens_subject_username"), table_name="channel_user_tokens")
    op.drop_index(op.f("ix_channel_user_tokens_subject_id"), table_name="channel_user_tokens")
    op.drop_index(op.f("ix_channel_user_tokens_expires_at"), table_name="channel_user_tokens")
    op.drop_index(op.f("ix_channel_user_tokens_provider"), table_name="channel_user_tokens")
    op.drop_table("channel_user_tokens")

    op.drop_index(op.f("ix_channel_auth_sessions_expires_at"), table_name="channel_auth_sessions")
    op.drop_index(op.f("ix_channel_auth_sessions_state"), table_name="channel_auth_sessions")
    op.drop_index(op.f("ix_channel_auth_sessions_provider"), table_name="channel_auth_sessions")
    op.drop_table("channel_auth_sessions")
