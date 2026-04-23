"""Add URL refilter run tracking tables.

Revision ID: 20260423_01
Revises: 20260416_01
Create Date: 2026-04-23 11:16:31 BST
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260423_01"
down_revision = "20260416_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create refilter tracking tables that older Postgres data volumes lack."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("url_refilter_runs"):
        op.create_table(
            "url_refilter_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("filter_chain_version", sa.Text(), nullable=False),
            sa.Column("crawler_was_running", sa.Boolean(), nullable=False),
            sa.Column("backup_path", sa.Text(), nullable=True),
            sa.Column("total_count", sa.Integer(), nullable=False),
            sa.Column("scanned_count", sa.Integer(), nullable=False),
            sa.Column("unchanged_count", sa.Integer(), nullable=False),
            sa.Column("activated_count", sa.Integer(), nullable=False),
            sa.Column("deactivated_count", sa.Integer(), nullable=False),
            sa.Column("retagged_count", sa.Integer(), nullable=False),
            sa.Column("last_raw_url_id", sa.Integer(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    inspector = sa.inspect(bind)
    if not inspector.has_table("url_refilter_run_events"):
        op.create_table(
            "url_refilter_run_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_id", sa.Integer(), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["run_id"], ["url_refilter_runs.id"], ondelete="CASCADE"),
        )
        op.create_index(
            "ix_url_refilter_run_events_run_id",
            "url_refilter_run_events",
            ["run_id"],
        )


def downgrade() -> None:
    """Remove refilter tracking tables."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("url_refilter_run_events"):
        op.drop_index("ix_url_refilter_run_events_run_id", table_name="url_refilter_run_events")
        op.drop_table("url_refilter_run_events")

    inspector = sa.inspect(bind)
    if inspector.has_table("url_refilter_runs"):
        op.drop_table("url_refilter_runs")
