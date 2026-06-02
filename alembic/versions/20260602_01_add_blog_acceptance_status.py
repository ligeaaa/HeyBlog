"""Split blog acceptance from crawl execution status.

Revision ID: 20260602_01
Revises: 20260601_01
Create Date: 2026-06-02 21:30:29 BST
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260602_01"
down_revision = "20260601_01"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    """Return currently present column names for one table.

    Args:
        table_name: Database table name to inspect.

    Returns:
        Set of column names currently present in the database.
    """
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    """Add acceptance and crawl-error fields, then backfill accepted graph rows.

    Args:
        None.

    Returns:
        None. The migration mutates the active database schema in place.
    """
    blog_columns = _columns("blogs")
    if "acceptance_status" not in blog_columns:
        op.add_column(
            "blogs",
            sa.Column("acceptance_status", sa.Text(), nullable=False, server_default="UNKNOWN"),
        )
    for column_name in (
        "accepted_by",
        "crawl_error_kind",
        "crawl_error_message",
    ):
        if column_name not in blog_columns:
            op.add_column("blogs", sa.Column(column_name, sa.Text(), nullable=True))
    for column_name in (
        "accepted_at",
        "last_crawl_attempt_at",
        "successful_crawl_at",
    ):
        if column_name not in blog_columns:
            op.add_column("blogs", sa.Column(column_name, sa.DateTime(timezone=True), nullable=True))

    op.execute(
        """
        UPDATE blogs b
        SET acceptance_status = 'ACCEPTED',
            accepted_by = COALESCE(b.accepted_by, r.accepted_by, 'unknown'),
            accepted_at = COALESCE(b.accepted_at, r.updated_at, b.created_at)
        FROM raw_discovered_urls r
        WHERE b.normalized_url = r.normalized_url
          AND r.status = 'success'
          AND b.acceptance_status = 'UNKNOWN'
        """
    )
    op.execute(
        """
        UPDATE blogs
        SET acceptance_status = 'ACCEPTED',
            accepted_by = COALESCE(accepted_by, 'seed'),
            accepted_at = COALESCE(accepted_at, created_at)
        WHERE acceptance_status = 'UNKNOWN'
          AND blog_id NOT IN (SELECT to_blog_id FROM edges)
        """
    )
    op.execute(
        """
        UPDATE blogs
        SET acceptance_status = 'ACCEPTED',
            accepted_by = COALESCE(accepted_by, 'graph'),
            accepted_at = COALESCE(accepted_at, created_at)
        WHERE acceptance_status = 'UNKNOWN'
          AND blog_id IN (SELECT from_blog_id FROM edges UNION SELECT to_blog_id FROM edges)
        """
    )


def downgrade() -> None:
    """Remove acceptance and crawl-error fields.

    Args:
        None.

    Returns:
        None. The migration mutates the active database schema in place.
    """
    for column_name in (
        "successful_crawl_at",
        "last_crawl_attempt_at",
        "crawl_error_message",
        "crawl_error_kind",
        "accepted_at",
        "accepted_by",
        "acceptance_status",
    ):
        if column_name in _columns("blogs"):
            op.drop_column("blogs", column_name)
