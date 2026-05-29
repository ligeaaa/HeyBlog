"""Add user auth and per-user label selection tables.

Revision ID: 20260526_02
Revises: 20260526_01
Create Date: 2026-05-26 22:04:50 BST
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260526_02"
down_revision = "20260526_01"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    """Return table names currently visible to Alembic."""
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    """Create registered-user, session, and per-user label selection tables."""
    existing_tables = _table_names()
    if "users" not in existing_tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email", sa.Text(), nullable=False),
            sa.Column("password_hash", sa.Text(), nullable=False),
            sa.Column("display_name", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("email", name="uq_users_email"),
        )
        op.create_index("ix_users_email", "users", ["email"])
    if "user_sessions" not in existing_tables:
        op.create_table(
            "user_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
        )
        op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
        op.create_index("ix_user_sessions_token_hash", "user_sessions", ["token_hash"])
    if "blog_user_label_selections" not in existing_tables:
        op.create_table(
            "blog_user_label_selections",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("normalized_url", sa.Text(), nullable=False),
            sa.Column("label_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("user_id", "normalized_url", name="uq_user_label_selection_user_url"),
        )
        op.create_index("ix_blog_user_label_selections_user_id", "blog_user_label_selections", ["user_id"])
        op.create_index(
            "ix_blog_user_label_selections_normalized_url",
            "blog_user_label_selections",
            ["normalized_url"],
        )


def downgrade() -> None:
    """Drop user auth and per-user label selection tables."""
    existing_tables = _table_names()
    if "blog_user_label_selections" in existing_tables:
        op.drop_index("ix_blog_user_label_selections_normalized_url", table_name="blog_user_label_selections")
        op.drop_index("ix_blog_user_label_selections_user_id", table_name="blog_user_label_selections")
        op.drop_table("blog_user_label_selections")
    if "user_sessions" in existing_tables:
        op.drop_index("ix_user_sessions_token_hash", table_name="user_sessions")
        op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
        op.drop_table("user_sessions")
    if "users" in existing_tables:
        op.drop_index("ix_users_email", table_name="users")
        op.drop_table("users")
