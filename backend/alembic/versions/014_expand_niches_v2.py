"""Expand niche system to 36 categories + add per-reel niche column.

Reset all existing profile niches to NULL so they get re-classified
with the new 36-niche prompt on next check_stale_profiles() cycle.

Revision ID: 014_expand_niches_v2
Revises: 013_add_multiauth_tables
Create Date: 2026-03-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014_expand_niches_v2"
down_revision: Union[str, None] = "013_add_multiauth_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add per-reel niche column to profile_reels
    op.add_column("profile_reels", sa.Column("niche", sa.String(), nullable=True))
    op.create_index(
        "idx_profile_reels_niche", "profile_reels", ["niche", "is_trending"]
    )

    # Reset all profile-level niches to NULL — profiles will be re-classified
    # with the new 36-niche prompt on next check_stale_profiles() cycle
    op.execute("UPDATE tracked_profiles SET niche = NULL WHERE niche IS NOT NULL")


def downgrade() -> None:
    op.drop_index("idx_profile_reels_niche", table_name="profile_reels")
    op.drop_column("profile_reels", "niche")
    # Cannot restore original profile niches; they will be re-inferred on next check
