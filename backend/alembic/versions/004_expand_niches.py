"""Expand niche system from 10 to 15 categories.

Reset all existing profile niches to NULL so they get re-classified
with the new expanded prompt on the next check_stale_profiles cycle.

Revision ID: 004_expand_niches
Revises: 003_add_job_is_hidden
Create Date: 2026-03-10
"""
from typing import Sequence, Union

from alembic import op

revision: str = "004_expand_niches"
down_revision: Union[str, None] = "003_add_job_is_hidden"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Reset all niches to NULL — profiles will be re-classified
    # with the new 15-niche prompt on next check_stale_profiles() cycle
    op.execute("UPDATE tracked_profiles SET niche = NULL WHERE niche IS NOT NULL")


def downgrade() -> None:
    # Cannot restore original niches; they will be re-inferred on next check
    pass
