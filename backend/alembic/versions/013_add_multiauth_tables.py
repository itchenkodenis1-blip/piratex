"""Add multi-auth tables and backfill Telegram identities.

Revision ID: 013_add_multiauth_tables
Revises: 012_add_job_thumbnail_url
Create Date: 2026-03-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013_add_multiauth_tables"
down_revision: Union[str, None] = "012_add_job_thumbnail_url"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :table AND column_name = :column"
    ), {"table": table, "column": column})
    return result.fetchone() is not None


def _table_exists(table: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_name = :table"
    ), {"table": table})
    return result.fetchone() is not None


def upgrade() -> None:
    # 1. Add columns to users table
    if not _column_exists("users", "email_verified"):
        op.add_column(
            "users",
            sa.Column("email_verified", sa.Boolean(), server_default="false", nullable=False),
        )
    if not _column_exists("users", "auth_provider"):
        op.add_column(
            "users",
            sa.Column("auth_provider", sa.String(20), nullable=True),
        )

    # 2. Create auth_identities table
    if not _table_exists("auth_identities"):
        op.create_table(
            "auth_identities",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("provider", sa.String(20), nullable=False),
            sa.Column("provider_user_id", sa.String(), nullable=False),
            sa.Column("email", sa.String(), nullable=True),
            sa.Column("display_name", sa.String(), nullable=True),
            sa.Column("avatar_url", sa.String(), nullable=True),
            sa.Column("access_token", sa.String(), nullable=True),
            sa.Column("refresh_token", sa.String(), nullable=True),
            sa.Column("token_expires_at", sa.TIMESTAMP(), nullable=True),
            sa.Column("raw_profile", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("NOW()")),
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("NOW()")),
            sa.UniqueConstraint("provider", "provider_user_id", name="uq_identity_provider_user"),
        )
        op.create_index("ix_identity_user_provider", "auth_identities", ["user_id", "provider"])

    # 3. Create magic_link_codes table
    if not _table_exists("magic_link_codes"):
        op.create_table(
            "magic_link_codes",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("email", sa.String(), nullable=False, index=True),
            sa.Column("code", sa.String(64), unique=True, nullable=False, index=True),
            sa.Column("ghost_user_id", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("confirmed", sa.Boolean(), server_default="false"),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("NOW()")),
            sa.Column("expires_at", sa.TIMESTAMP(), nullable=False),
        )

    # 4. Create phone_auth_codes table
    if not _table_exists("phone_auth_codes"):
        op.create_table(
            "phone_auth_codes",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("phone", sa.String(20), nullable=False, index=True),
            sa.Column("code", sa.String(6), nullable=False),
            sa.Column("ghost_user_id", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("confirmed", sa.Boolean(), server_default="false"),
            sa.Column("attempts", sa.Integer(), server_default="0"),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("NOW()")),
            sa.Column("expires_at", sa.TIMESTAMP(), nullable=False),
        )

    # 5. Create oauth_states table
    if not _table_exists("oauth_states"):
        op.create_table(
            "oauth_states",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("state", sa.String(64), unique=True, nullable=False, index=True),
            sa.Column("provider", sa.String(20), nullable=False),
            sa.Column("ghost_user_id", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("redirect_url", sa.String(), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("NOW()")),
            sa.Column("expires_at", sa.TIMESTAMP(), nullable=False),
        )

    # 6. Backfill auth_identities from existing Telegram users
    op.execute(sa.text("""
        INSERT INTO auth_identities (id, user_id, provider, provider_user_id, display_name, created_at, updated_at)
        SELECT
            gen_random_uuid()::text,
            id,
            'telegram',
            telegram_user_id,
            COALESCE(telegram_username, name),
            created_at,
            NOW()
        FROM users
        WHERE telegram_user_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM auth_identities ai
              WHERE ai.user_id = users.id AND ai.provider = 'telegram'
          )
    """))

    # 7. Backfill auth_provider on existing Telegram users
    op.execute(sa.text("""
        UPDATE users SET auth_provider = 'telegram'
        WHERE telegram_user_id IS NOT NULL AND auth_provider IS NULL
    """))


def downgrade() -> None:
    op.drop_table("oauth_states")
    op.drop_table("phone_auth_codes")
    op.drop_table("magic_link_codes")
    op.drop_index("ix_identity_user_provider", table_name="auth_identities")
    op.drop_table("auth_identities")
    op.drop_column("users", "auth_provider")
    op.drop_column("users", "email_verified")
