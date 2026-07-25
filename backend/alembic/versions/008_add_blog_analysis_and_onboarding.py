"""Add blog_analysis_json and onboarding_completed to user_settings.

Revision ID: 008_add_blog_analysis_and_onboarding
Revises: 007_add_user_interest_signals
Create Date: 2026-03-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_add_blog_analysis_and_onboarding"
down_revision: Union[str, None] = "007_add_user_interest_signals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # Widen alembic_version.version_num to accommodate longer revision IDs
    bind.execute(sa.text(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)"
    ))

    # Add blog_analysis_json column if not exists
    result = bind.execute(sa.text(
        "SELECT EXISTS(SELECT FROM information_schema.columns "
        "WHERE table_name='user_settings' AND column_name='blog_analysis_json')"
    ))
    if not result.scalar():
        op.add_column("user_settings", sa.Column("blog_analysis_json", sa.JSON(), nullable=True))

    # Add onboarding_completed column if not exists
    result = bind.execute(sa.text(
        "SELECT EXISTS(SELECT FROM information_schema.columns "
        "WHERE table_name='user_settings' AND column_name='onboarding_completed')"
    ))
    if not result.scalar():
        op.add_column(
            "user_settings",
            sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default="false"),
        )


def downgrade() -> None:
    op.drop_column("user_settings", "onboarding_completed")
    op.drop_column("user_settings", "blog_analysis_json")
