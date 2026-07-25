"""Add thumbnail_key to profile_reels for persistent thumbnail storage.

Revision ID: 006_add_thumbnail_key
Revises: 005_add_user_reel_likes
Create Date: 2026-03-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_add_thumbnail_key"
down_revision: Union[str, None] = "005_add_user_reel_likes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("profile_reels", sa.Column("thumbnail_key", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("profile_reels", "thumbnail_key")
