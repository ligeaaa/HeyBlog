"""Add public random-page user label table.

Revision ID: 20260526_01
Revises: 20260525_03
Create Date: 2026-05-26 00:17:32 BST
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260526_01"
down_revision = "20260525_03"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    """Return table names currently visible to Alembic."""
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    """Create `blog_labels_userlabel` with the same structure as `blog_labels`."""
    bind = op.get_bind()
    if "blog_labels_userlabel" in _table_names():
        columns = {column["name"] for column in sa.inspect(bind).get_columns("blog_labels_userlabel")}
        if "title" not in columns:
            op.add_column("blog_labels_userlabel", sa.Column("title", sa.Text(), nullable=False, server_default=""))
        return
    op.create_table(
        "blog_labels_userlabel",
        sa.Column("normalized_url", sa.Text(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "label_id",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
            server_default=sa.text("'{}'::jsonb") if bind.dialect.name == "postgresql" else sa.text("'{}'"),
        ),
        sa.Column("created_time", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_time", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_blog_labels_userlabel_normalized_url",
        "blog_labels_userlabel",
        ["normalized_url"],
    )


def downgrade() -> None:
    """Drop the public random-page user label table."""
    if "blog_labels_userlabel" in _table_names():
        op.drop_index("ix_blog_labels_userlabel_normalized_url", table_name="blog_labels_userlabel")
        op.drop_table("blog_labels_userlabel")
