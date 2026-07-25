"""Add content moderation fields: is_blocked on tracked_profiles, is_hidden on profile_reels.

Revision ID: 015_add_content_moderation_fields
Revises: 014_expand_niches_v2
Create Date: 2026-03-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015_add_content_moderation_fields"
down_revision: Union[str, None] = "014_expand_niches_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # TrackedProfile: moderation fields
    op.add_column("tracked_profiles", sa.Column("is_blocked", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("tracked_profiles", sa.Column("blocked_at", sa.DateTime(), nullable=True))
    op.add_column("tracked_profiles", sa.Column("blocked_reason", sa.String(), nullable=True))
    op.create_index("idx_tracked_profiles_blocked", "tracked_profiles", ["is_blocked"])

    # ProfileReel: moderation fields
    op.add_column("profile_reels", sa.Column("is_hidden", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("profile_reels", sa.Column("hidden_at", sa.DateTime(), nullable=True))
    op.add_column("profile_reels", sa.Column("hidden_reason", sa.String(), nullable=True))
    op.create_index("idx_profile_reels_hidden", "profile_reels", ["is_hidden"])


def downgrade() -> None:
    op.drop_index("idx_profile_reels_hidden", table_name="profile_reels")
    op.drop_column("profile_reels", "hidden_reason")
    op.drop_column("profile_reels", "hidden_at")
    op.drop_column("profile_reels", "is_hidden")

    op.drop_index("idx_tracked_profiles_blocked", table_name="tracked_profiles")
    op.drop_column("tracked_profiles", "blocked_reason")
    op.drop_column("tracked_profiles", "blocked_at")
    op.drop_column("tracked_profiles", "is_blocked")
