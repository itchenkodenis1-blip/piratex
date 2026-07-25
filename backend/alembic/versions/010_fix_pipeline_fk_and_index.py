"""Fix pipeline FK ondelete and add assignee index.

Revision ID: 010_fix_pipeline_fk_and_index
Revises: 009_add_production_pipeline
Create Date: 2026-03-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010_fix_pipeline_fk_and_index"
down_revision: Union[str, None] = "009_add_production_pipeline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _find_fk_constraint(table: str, column: str) -> str | None:
    """Find the actual FK constraint name on a given column."""
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT tc.constraint_name "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "  ON tc.constraint_name = kcu.constraint_name "
        "     AND tc.table_schema = kcu.table_schema "
        f"WHERE tc.table_name = '{table}' "
        f"  AND kcu.column_name = '{column}' "
        "  AND tc.constraint_type = 'FOREIGN KEY'"
    ))
    row = result.first()
    return row[0] if row else None


def _index_exists(index_name: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(sa.text(
        f"SELECT EXISTS(SELECT 1 FROM pg_indexes WHERE indexname = '{index_name}')"
    ))
    return result.scalar()


def upgrade() -> None:
    # 1. Fix triggered_by FK: CASCADE -> SET NULL, nullable
    fk_name = _find_fk_constraint("production_history", "triggered_by")
    if fk_name:
        op.drop_constraint(fk_name, "production_history", type_="foreignkey")

    op.alter_column("production_history", "triggered_by", nullable=True)

    op.create_foreign_key(
        "fk_production_history_triggered_by_users",
        "production_history",
        "users",
        ["triggered_by"],
        ["id"],
        ondelete="SET NULL",
    )

    # 2. Add index on user_scripts.assignee_id (idempotent)
    if not _index_exists("ix_user_scripts_assignee_id"):
        op.create_index("ix_user_scripts_assignee_id", "user_scripts", ["assignee_id"])


def downgrade() -> None:
    if _index_exists("ix_user_scripts_assignee_id"):
        op.drop_index("ix_user_scripts_assignee_id", table_name="user_scripts")

    fk_name = _find_fk_constraint("production_history", "triggered_by")
    if fk_name:
        op.drop_constraint(fk_name, "production_history", type_="foreignkey")

    op.alter_column("production_history", "triggered_by", nullable=False)

    op.create_foreign_key(
        "fk_production_history_triggered_by_users",
        "production_history",
        "users",
        ["triggered_by"],
        ["id"],
        ondelete="CASCADE",
    )
