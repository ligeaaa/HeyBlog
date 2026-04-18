"""Best-effort Apache AGE shadow graph management for persistence."""

from __future__ import annotations
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

VALID_GRAPH_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SYNC_BATCH_SIZE = 250


def _cypher_string(value: str) -> str:
    """Escape one Python string for safe interpolation into Cypher."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _agtype_to_int(value: Any) -> int:
    """Parse one AGE agtype count result into an integer."""
    if isinstance(value, int):
        return value
    if value is None:
        return 0
    normalized = str(value).strip().strip('"')
    return int(normalized or 0)


def _validate_graph_name(graph_name: str) -> str:
    """Validate one AGE graph identifier before interpolating it into SQL text."""
    if not VALID_GRAPH_NAME_PATTERN.fullmatch(graph_name):
        raise ValueError(f"Unsupported AGE graph name: {graph_name}")
    return graph_name


def _chunked_rows(rows: list[dict[str, Any]], chunk_size: int = SYNC_BATCH_SIZE) -> list[list[dict[str, Any]]]:
    """Split one list of sync rows into stable chunks for batched Cypher rebuilds."""
    if not rows:
        return []
    return [rows[index : index + chunk_size] for index in range(0, len(rows), chunk_size)]


def _render_blog_batch_query(blogs: list[dict[str, Any]]) -> str:
    """Render one batched Cypher CREATE query for blog vertices."""
    records = ",\n".join(
        (
            "{"
            f"blog_id: {int(blog['id'])}, "
            f"crawl_status: '{_cypher_string(str(blog.get('crawl_status') or ''))}', "
            f"normalized_url: '{_cypher_string(str(blog.get('normalized_url') or ''))}', "
            f"domain: '{_cypher_string(str(blog.get('domain') or ''))}'"
            "}"
        )
        for blog in blogs
    )
    return f"""
        UNWIND [{records}] AS blog
        CREATE (:Blog {{
            blog_id: blog.blog_id,
            crawl_status: blog.crawl_status,
            normalized_url: blog.normalized_url,
            domain: blog.domain
        }})
    """


def _render_edge_batch_query(edges: list[dict[str, Any]]) -> str:
    """Render one batched Cypher CREATE query for graph edges."""
    records = ",\n".join(
        (
            "{"
            f"edge_id: {int(edge['id'])}, "
            f"source_id: {int(edge['from_blog_id'])}, "
            f"target_id: {int(edge['to_blog_id'])}"
            "}"
        )
        for edge in edges
    )
    return f"""
        UNWIND [{records}] AS edge
        MATCH (source:Blog {{blog_id: edge.source_id}}),
              (target:Blog {{blog_id: edge.target_id}})
        CREATE (source)-[:LINKS_TO {{edge_id: edge.edge_id}}]->(target)
    """


class AgeGraphManager:
    """Manage a rebuildable AGE shadow graph without affecting authoritative writes."""

    def __init__(self, engine: Engine | None, *, enabled: bool, graph_name: str) -> None:
        """Store database access and AGE configuration."""
        self.engine = engine
        self.enabled = enabled and engine is not None and engine.dialect.name == "postgresql"
        self.graph_name = _validate_graph_name(graph_name)
        self.sync_state = "not_configured" if not self.enabled else "idle"
        self.parity_status = "unknown"
        self.last_error: str | None = None

    def _execute_cypher(self, connection: Any, query: str, *, column_name: str = "result") -> Any:
        """Execute one validated Cypher query against the configured AGE graph."""
        return connection.execute(
            text(
                f"""
                SELECT *
                FROM cypher('{self.graph_name}', $$
                    {query}
                $$) AS ({column_name} agtype)
                """
            )
        )

    def status(self, *, graph_backend: str, snapshot_namespace: str) -> dict[str, Any]:
        """Return graph-read readiness metadata for operators and tests."""
        return {
            "graph_backend": graph_backend,
            "age_enabled": self.enabled,
            "age_sync_state": self.sync_state,
            "parity_status": self.parity_status,
            "latest_snapshot_namespace": snapshot_namespace,
            "age_graph_name": self.graph_name,
            "last_error": self.last_error,
        }

    def sync_shadow_graph(self, blogs: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
        """Rebuild the AGE shadow graph from authoritative relational rows."""
        if not self.enabled or self.engine is None:
            self.sync_state = "not_configured"
            self.parity_status = "unknown"
            return

        self.sync_state = "rebuilding"
        self.last_error = None
        try:
            with self.engine.begin() as connection:
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS age"))
                connection.execute(text("LOAD 'age'"))
                connection.execute(text('SET search_path = ag_catalog, "$user", public'))
                connection.execute(
                    text(
                        """
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1
                                FROM ag_catalog.ag_graph
                                WHERE name = :graph_name
                            ) THEN
                                PERFORM ag_catalog.create_graph(:graph_name);
                            END IF;
                        END
                        $$;
                        """
                    ),
                    {"graph_name": self.graph_name},
                )
                self._execute_cypher(connection, "MATCH (n) DETACH DELETE n")

                for blog_batch in _chunked_rows(blogs):
                    self._execute_cypher(connection, _render_blog_batch_query(blog_batch))

                for edge_batch in _chunked_rows(edges):
                    self._execute_cypher(connection, _render_edge_batch_query(edge_batch))

                vertex_count = _agtype_to_int(
                    self._execute_cypher(connection, "MATCH (n:Blog) RETURN count(n)", column_name="count").scalar_one()
                )
                edge_count = _agtype_to_int(
                    self._execute_cypher(
                        connection,
                        "MATCH ()-[r:LINKS_TO]->() RETURN count(r)",
                        column_name="count",
                    ).scalar_one()
                )
                expected_blogs = len(blogs)
                expected_edges = len(edges)
                self.parity_status = (
                    "passing" if vertex_count == expected_blogs and edge_count == expected_edges else "failing"
                )
                self.sync_state = "ready"
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            self.sync_state = "failed"
            self.parity_status = "failing"
