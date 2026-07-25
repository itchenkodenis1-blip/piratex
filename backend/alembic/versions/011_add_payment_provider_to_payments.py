"""Add payment_provider column to payments table.

Revision ID: 011_add_payment_provider_to_payments
Revises: 010_fix_pipeline_fk_and_index
Create Date: 2026-03-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011_add_payment_provider_to_payments"
down_revision: Union[str, None] = "010_fix_pipeline_fk_and_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            "SELECT EXISTS(SELECT FROM information_schema.columns "
            f"WHERE table_name='{table}' AND column_name='{column}')"
        )
    )
    return result.scalar()


def upgrade() -> None:
    if not _column_exists("payments", "payment_provider"):
        op.add_column(
            "payments",
            sa.Column(
                "payment_provider",
                sa.String(50),
                nullable=False,
                server_default="yookassa",
            ),
        )


def downgrade() -> None:
    if _column_exists("payments", "payment_provider"):
        op.drop_column("payments", "payment_provider")
