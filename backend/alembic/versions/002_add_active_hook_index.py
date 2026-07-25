"""Add active_hook_index to user_scripts.

Revision ID: 002_add_active_hook_index
Revises: 001_baseline
Create Date: 2026-03-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_add_active_hook_index"
down_revision: Union[str, None] = "001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_scripts",
        sa.Column("active_hook_index", sa.Integer(), nullable=True, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("user_scripts", "active_hook_index")
