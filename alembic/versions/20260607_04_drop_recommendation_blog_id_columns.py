"""Drop blog_id columns from recommendation event tables.

Revision ID: 20260607_04
Revises: 20260607_03
Create Date: 2026-06-07 16:35:00 BST
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260607_04"
down_revision = "20260607_03"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    """Return currently present table names.

    Args:
        None.

    Returns:
        Set of table names visible through the active migration connection.
    """

    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    """Return column names for one table.

    Args:
        table_name: Table to inspect.

    Returns:
        Set of existing column names, or an empty set when the table is absent.
    """

    inspector = sa.inspect(op.get_bind())
    if table_name not in set(inspector.get_table_names()):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    """Return index names for one table.

    Args:
        table_name: Table to inspect.

    Returns:
        Set of existing index names, or an empty set when the table is absent.
    """

    inspector = sa.inspect(op.get_bind())
    if table_name not in set(inspector.get_table_names()):
        return set()
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _unique_constraint_names(table_name: str) -> set[str]:
    """Return named unique constraints for one table.

    Args:
        table_name: Table to inspect.

    Returns:
        Set of existing unique constraint names, or an empty set when absent.
    """

    inspector = sa.inspect(op.get_bind())
    if table_name not in set(inspector.get_table_names()):
        return set()
    return {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(table_name)
        if constraint["name"]
    }


def upgrade() -> None:
    """Remove blog foreign-key columns from recommendation event tables.

    Args:
        None.

    Returns:
        None. Existing rows keep their durable `normalized_url` attribution.
    """

    tables = _table_names()
    if "recommendation_impressions" in tables:
        columns = _column_names("recommendation_impressions")
        indexes = _index_names("recommendation_impressions")
        unique_constraints = _unique_constraint_names("recommendation_impressions")
        with op.batch_alter_table("recommendation_impressions") as batch_op:
            if "ix_recommendation_impressions_blog_created" in indexes:
                batch_op.drop_index("ix_recommendation_impressions_blog_created")
            if "ix_recommendation_impressions_blog_id" in indexes:
                batch_op.drop_index("ix_recommendation_impressions_blog_id")
            if "uq_recommendation_impression_request_blog" in unique_constraints:
                batch_op.drop_constraint("uq_recommendation_impression_request_blog", type_="unique")
            if "uq_recommendation_impression_request_url" not in unique_constraints:
                batch_op.create_unique_constraint(
                    "uq_recommendation_impression_request_url",
                    ["request_id", "normalized_url"],
                )
            if "ix_recommendation_impressions_url_created" not in indexes:
                batch_op.create_index(
                    "ix_recommendation_impressions_url_created",
                    ["normalized_url", "created_at"],
                )
            if "blog_id" in columns:
                batch_op.drop_column("blog_id")

    if "blog_interactions" in tables:
        columns = _column_names("blog_interactions")
        indexes = _index_names("blog_interactions")
        with op.batch_alter_table("blog_interactions") as batch_op:
            if "ix_blog_interactions_blog_event_created" in indexes:
                batch_op.drop_index("ix_blog_interactions_blog_event_created")
            if "ix_blog_interactions_blog_id" in indexes:
                batch_op.drop_index("ix_blog_interactions_blog_id")
            if "ix_blog_interactions_url_event_created" not in indexes:
                batch_op.create_index(
                    "ix_blog_interactions_url_event_created",
                    ["normalized_url", "event_type", "created_at"],
                )
            if "blog_id" in columns:
                batch_op.drop_column("blog_id")


def downgrade() -> None:
    """Recreate removed blog_id columns for rollback.

    Args:
        None.

    Returns:
        None. Recreated values are nullable because historical URL-keyed event
        rows cannot always be relinked after a graph reset.
    """

    tables = _table_names()
    if "recommendation_impressions" in tables:
        columns = _column_names("recommendation_impressions")
        indexes = _index_names("recommendation_impressions")
        unique_constraints = _unique_constraint_names("recommendation_impressions")
        with op.batch_alter_table("recommendation_impressions") as batch_op:
            if "blog_id" not in columns:
                batch_op.add_column(sa.Column("blog_id", sa.Integer(), nullable=True))
            if "ix_recommendation_impressions_url_created" in indexes:
                batch_op.drop_index("ix_recommendation_impressions_url_created")
            if "uq_recommendation_impression_request_url" in unique_constraints:
                batch_op.drop_constraint("uq_recommendation_impression_request_url", type_="unique")
            if "uq_recommendation_impression_request_blog" not in unique_constraints:
                batch_op.create_unique_constraint(
                    "uq_recommendation_impression_request_blog",
                    ["request_id", "blog_id"],
                )
            if "ix_recommendation_impressions_blog_id" not in indexes:
                batch_op.create_index("ix_recommendation_impressions_blog_id", ["blog_id"])
            if "ix_recommendation_impressions_blog_created" not in indexes:
                batch_op.create_index(
                    "ix_recommendation_impressions_blog_created",
                    ["blog_id", "created_at"],
                )

    if "blog_interactions" in tables:
        columns = _column_names("blog_interactions")
        indexes = _index_names("blog_interactions")
        with op.batch_alter_table("blog_interactions") as batch_op:
            if "blog_id" not in columns:
                batch_op.add_column(sa.Column("blog_id", sa.Integer(), nullable=True))
            if "ix_blog_interactions_url_event_created" in indexes:
                batch_op.drop_index("ix_blog_interactions_url_event_created")
            if "ix_blog_interactions_blog_id" not in indexes:
                batch_op.create_index("ix_blog_interactions_blog_id", ["blog_id"])
            if "ix_blog_interactions_blog_event_created" not in indexes:
                batch_op.create_index(
                    "ix_blog_interactions_blog_event_created",
                    ["blog_id", "event_type", "created_at"],
                )
