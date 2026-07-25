"""Baseline — stamp existing schema.

Revision ID: 001_baseline
Revises:
Create Date: 2026-03-09

This migration represents the existing database schema.
All tables already exist; this just establishes Alembic tracking.
Run `alembic stamp 001_baseline` on existing databases.
"""
from typing import Sequence, Union

revision: str = "001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing schema — no changes needed.
    # All tables were created by Base.metadata.create_all() + inline migrations.
    pass


def downgrade() -> None:
    pass
