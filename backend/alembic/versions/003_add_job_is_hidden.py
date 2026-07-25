"""Add is_hidden to jobs for soft delete from My Videos.

Revision ID: 003_add_job_is_hidden
Revises: 002_add_active_hook_index
Create Date: 2026-03-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_add_job_is_hidden"
down_revision: Union[str, None] = "002_add_active_hook_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("is_hidden", sa.Boolean(), nullable=True, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("jobs", "is_hidden")
