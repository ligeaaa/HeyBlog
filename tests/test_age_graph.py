"""Tests for AGE shadow graph helpers."""

from persistence_api.age_graph import AgeGraphManager
from persistence_api.age_graph import _chunked_rows
from persistence_api.age_graph import _render_blog_batch_query
from persistence_api.age_graph import _render_edge_batch_query


class PostgresDialect:
    """Minimal SQLAlchemy-like dialect stub for AGE manager tests."""

    name = "postgresql"


class PostgresEngine:
    """Minimal SQLAlchemy-like engine stub for AGE manager tests."""

    dialect = PostgresDialect()


def test_age_graph_manager_rejects_unsafe_graph_names() -> None:
    """AGE graph names should be validated before SQL text interpolation."""
    try:
        AgeGraphManager(PostgresEngine(), enabled=True, graph_name="bad-name;drop table")
    except ValueError as exc:
        assert "Unsupported AGE graph name" in str(exc)
    else:
        raise AssertionError("expected invalid graph name to fail")


def test_age_graph_batch_helpers_render_compact_cypher_payloads() -> None:
    """Batched helpers should emit one UNWIND query per chunk."""
    blog_query = _render_blog_batch_query(
        [
            {
                "id": 1,
                "crawl_status": "FINISHED",
                "normalized_url": "https://alpha.example/",
                "domain": "alpha.example",
            }
        ]
    )
    edge_query = _render_edge_batch_query(
        [
            {
                "id": 7,
                "from_blog_id": 1,
                "to_blog_id": 2,
            }
        ]
    )

    assert "UNWIND" in blog_query
    assert "CREATE (:Blog" in blog_query
    assert "edge_id: 7" in edge_query
    assert "MATCH (source:Blog" in edge_query


def test_age_graph_chunking_splits_large_payloads() -> None:
    """Chunking should keep ordering stable while enforcing batch boundaries."""
    chunks = _chunked_rows([{"id": index} for index in range(5)], chunk_size=2)

    assert chunks == [
        [{"id": 0}, {"id": 1}],
        [{"id": 2}, {"id": 3}],
        [{"id": 4}],
    ]
