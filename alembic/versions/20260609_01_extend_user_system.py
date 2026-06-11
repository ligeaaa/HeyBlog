"""Extend user auth lifecycle fields.

Revision ID: 20260609_01
Revises: 20260607_04
Create Date: 2026-06-09 16:40:00 UTC
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260609_01"
down_revision = "20260607_04"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    """Return table names currently visible to Alembic."""
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    """Return column names for one table currently visible to Alembic."""
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    """Add user lifecycle columns, token rows, and audit rows."""
    existing_tables = _table_names()
    if "users" in existing_tables:
        user_columns = _column_names("users")
        if "role" not in user_columns:
            op.add_column("users", sa.Column("role", sa.Text(), nullable=False, server_default="user"))
        if "is_active" not in user_columns:
            op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
        if "email_verified_at" not in user_columns:
            op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
        if "password_changed_at" not in user_columns:
            op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))
        if "last_login_at" not in user_columns:
            op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
        op.create_check_constraint(
            "ck_users_role",
            "users",
            "role IN ('admin', 'user')",
        )

    if "user_verification_tokens" not in existing_tables:
        op.create_table(
            "user_verification_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.Text(), nullable=False),
            sa.Column("purpose", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("token_hash", name="uq_user_verification_tokens_token_hash"),
        )
        op.create_index("ix_user_verification_tokens_user_id", "user_verification_tokens", ["user_id"])
        op.create_index("ix_user_verification_tokens_token_hash", "user_verification_tokens", ["token_hash"])
        op.create_index("ix_user_verification_tokens_purpose", "user_verification_tokens", ["purpose"])

    if "user_audit_events" not in existing_tables:
        op.create_table(
            "user_audit_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("event_type", sa.Text(), nullable=False),
            sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_user_audit_events_user_id", "user_audit_events", ["user_id"])
        op.create_index("ix_user_audit_events_event_type", "user_audit_events", ["event_type"])


def downgrade() -> None:
    """Remove user lifecycle columns, token rows, and audit rows."""
    existing_tables = _table_names()
    if "user_audit_events" in existing_tables:
        op.drop_index("ix_user_audit_events_event_type", table_name="user_audit_events")
        op.drop_index("ix_user_audit_events_user_id", table_name="user_audit_events")
        op.drop_table("user_audit_events")
    if "user_verification_tokens" in existing_tables:
        op.drop_index("ix_user_verification_tokens_purpose", table_name="user_verification_tokens")
        op.drop_index("ix_user_verification_tokens_token_hash", table_name="user_verification_tokens")
        op.drop_index("ix_user_verification_tokens_user_id", table_name="user_verification_tokens")
        op.drop_table("user_verification_tokens")
    if "users" in existing_tables:
        user_columns = _column_names("users")
        op.drop_constraint("ck_users_role", "users", type_="check")
        for column_name in (
            "last_login_at",
            "password_changed_at",
            "email_verified_at",
            "is_active",
            "role",
        ):
            if column_name in user_columns:
                op.drop_column("users", column_name)
