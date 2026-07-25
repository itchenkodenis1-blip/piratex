"""Add user_reel_likes table for universal like system.

Revision ID: 005_add_user_reel_likes
Revises: 004_expand_niches
Create Date: 2026-03-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_add_user_reel_likes"
down_revision: Union[str, None] = "004_expand_niches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_reel_likes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("url", sa.String(), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "url", name="uq_user_reel_like"),
    )


def downgrade() -> None:
    op.drop_table("user_reel_likes")
