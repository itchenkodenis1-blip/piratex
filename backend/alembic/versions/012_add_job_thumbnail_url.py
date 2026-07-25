"""Add thumbnail_url to jobs for platform thumbnail fallback.

Revision ID: 012_add_job_thumbnail_url
Revises: 011_add_payment_provider_to_payments
Create Date: 2026-03-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012_add_job_thumbnail_url"
down_revision: Union[str, None] = "011_add_payment_provider_to_payments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("thumbnail_url", sa.String(), nullable=True),
    )
    # Backfill from profile_reels where URLs match
    op.execute(sa.text("""
        UPDATE jobs
        SET thumbnail_url = pr.thumbnail_url
        FROM profile_reels pr
        WHERE jobs.thumbnail_url IS NULL
          AND pr.thumbnail_url IS NOT NULL
          AND (jobs.url = pr.url OR RTRIM(jobs.url, '/') = RTRIM(pr.url, '/'))
    """))


def downgrade() -> None:
    op.drop_column("jobs", "thumbnail_url")
