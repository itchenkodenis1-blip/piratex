"""Add user_interest_signals table for Interest Graph.

Revision ID: 007_add_user_interest_signals
Revises: 006_add_thumbnail_key
Create Date: 2026-03-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_add_user_interest_signals"
down_revision: Union[str, None] = "006_add_thumbnail_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT EXISTS(SELECT FROM information_schema.tables WHERE table_name='user_interest_signals')"
    ))
    if result.scalar():
        return

    op.create_table(
        "user_interest_signals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic", sa.String(100), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("source_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_uis_user_topic", "user_interest_signals", ["user_id", "topic"])
    op.create_index("idx_uis_user_source", "user_interest_signals", ["user_id", "source"])


def downgrade() -> None:
    op.drop_index("idx_uis_user_source", table_name="user_interest_signals")
    op.drop_index("idx_uis_user_topic", table_name="user_interest_signals")
    op.drop_table("user_interest_signals")
