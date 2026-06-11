"""Add pending user registration table.

Revision ID: 20260611_01
Revises: 20260609_01
Create Date: 2026-06-11 00:00:00 UTC
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260611_01"
down_revision = "20260609_01"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    """Return table names currently visible to Alembic."""
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    """Create pending registrations for verify-before-persist signup."""
    if "pending_user_registrations" in _table_names():
        return
    op.create_table(
        "pending_user_registrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("email", name="uq_pending_user_registrations_email"),
        sa.UniqueConstraint("token_hash", name="uq_pending_user_registrations_token_hash"),
    )
    op.create_index("ix_pending_user_registrations_email", "pending_user_registrations", ["email"])
    op.create_index("ix_pending_user_registrations_token_hash", "pending_user_registrations", ["token_hash"])


def downgrade() -> None:
    """Drop pending registrations."""
    if "pending_user_registrations" not in _table_names():
        return
    op.drop_index("ix_pending_user_registrations_token_hash", table_name="pending_user_registrations")
    op.drop_index("ix_pending_user_registrations_email", table_name="pending_user_registrations")
    op.drop_table("pending_user_registrations")
