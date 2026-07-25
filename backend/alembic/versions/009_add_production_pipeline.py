"""Add production pipeline tables and fields.

Revision ID: 009_add_production_pipeline
Revises: 008_add_blog_analysis_and_onboarding
Create Date: 2026-03-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_add_production_pipeline"
down_revision: Union[str, None] = "008_add_blog_analysis_and_onboarding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT EXISTS(SELECT FROM information_schema.columns "
        f"WHERE table_name='{table}' AND column_name='{column}')"
    ))
    return result.scalar()


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(sa.text(
        f"SELECT EXISTS(SELECT FROM information_schema.tables WHERE table_name='{table}')"
    ))
    return result.scalar()


def upgrade() -> None:
    # --- Extend user_scripts with production pipeline fields ---
    if not _column_exists("user_scripts", "production_status"):
        op.add_column("user_scripts", sa.Column("production_status", sa.String(20), nullable=True))
        op.create_index("ix_user_scripts_production_status", "user_scripts", ["production_status"])

    if not _column_exists("user_scripts", "assignee_id"):
        op.add_column("user_scripts", sa.Column(
            "assignee_id", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ))

    if not _column_exists("user_scripts", "due_date"):
        op.add_column("user_scripts", sa.Column("due_date", sa.DateTime(), nullable=True))

    if not _column_exists("user_scripts", "scheduled_publish_at"):
        op.add_column("user_scripts", sa.Column("scheduled_publish_at", sa.DateTime(), nullable=True))

    if not _column_exists("user_scripts", "published_at"):
        op.add_column("user_scripts", sa.Column("published_at", sa.DateTime(), nullable=True))

    # --- Extend users with team_role ---
    if not _column_exists("users", "team_role"):
        op.add_column("users", sa.Column(
            "team_role", sa.String(20), nullable=False, server_default="owner",
        ))

    # --- Create production_assets ---
    if not _table_exists("production_assets"):
        op.create_table(
            "production_assets",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("script_id", sa.String(), sa.ForeignKey("user_scripts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("stage", sa.String(20), nullable=False),
            sa.Column("file_key", sa.String(), nullable=False),
            sa.Column("file_name", sa.String(), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=True),
            sa.Column("file_type", sa.String(50), nullable=True),
            sa.Column("uploaded_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_production_assets_script_id", "production_assets", ["script_id"])

    # --- Create production_comments ---
    if not _table_exists("production_comments"):
        op.create_table(
            "production_comments",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("script_id", sa.String(), sa.ForeignKey("user_scripts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("stage", sa.String(20), nullable=False),
            sa.Column("author_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_production_comments_script_id", "production_comments", ["script_id"])

    # --- Create production_history ---
    if not _table_exists("production_history"):
        op.create_table(
            "production_history",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("script_id", sa.String(), sa.ForeignKey("user_scripts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("from_status", sa.String(20), nullable=True),
            sa.Column("to_status", sa.String(20), nullable=False),
            sa.Column("triggered_by", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_production_history_script_id", "production_history", ["script_id"])


def downgrade() -> None:
    op.drop_index("ix_production_history_script_id", table_name="production_history")
    op.drop_table("production_history")

    op.drop_index("ix_production_comments_script_id", table_name="production_comments")
    op.drop_table("production_comments")

    op.drop_index("ix_production_assets_script_id", table_name="production_assets")
    op.drop_table("production_assets")

    op.drop_column("users", "team_role")

    op.drop_column("user_scripts", "published_at")
    op.drop_column("user_scripts", "scheduled_publish_at")
    op.drop_column("user_scripts", "due_date")
    op.drop_column("user_scripts", "assignee_id")
    op.drop_index("ix_user_scripts_production_status", table_name="user_scripts")
    op.drop_column("user_scripts", "production_status")
