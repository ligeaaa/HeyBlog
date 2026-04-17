"""Best-effort Apache AGE shadow graph management for persistence."""

from __future__ import annotations
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine


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


class AgeGraphManager:
    """Manage a rebuildable AGE shadow graph without affecting authoritative writes."""

    def __init__(self, engine: Engine | None, *, enabled: bool, graph_name: str) -> None:
        """Store database access and AGE configuration."""
        self.engine = engine
        self.enabled = enabled and engine is not None and engine.dialect.name == "postgresql"
        self.graph_name = graph_name
        self.sync_state = "not_configured" if not self.enabled else "idle"
        self.parity_status = "unknown"
        self.last_error: str | None = None

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
                connection.execute(
                    text(
                        f"""
                        SELECT *
                        FROM cypher('{self.graph_name}', $$
                            MATCH (n) DETACH DELETE n
                        $$) AS (result agtype)
                        """
                    )
                )

                for blog in blogs:
                    blog_id = int(blog["id"])
                    crawl_status = _cypher_string(str(blog.get("crawl_status") or ""))
                    normalized_url = _cypher_string(str(blog.get("normalized_url") or ""))
                    domain = _cypher_string(str(blog.get("domain") or ""))
                    connection.execute(
                        text(
                            f"""
                            SELECT *
                            FROM cypher('{self.graph_name}', $$
                                CREATE (:Blog {{
                                    blog_id: {blog_id},
                                    crawl_status: '{crawl_status}',
                                    normalized_url: '{normalized_url}',
                                    domain: '{domain}'
                                }})
                            $$) AS (result agtype)
                            """
                        )
                    )

                for edge in edges:
                    edge_id = int(edge["id"])
                    source_id = int(edge["from_blog_id"])
                    target_id = int(edge["to_blog_id"])
                    connection.execute(
                        text(
                            f"""
                            SELECT *
                            FROM cypher('{self.graph_name}', $$
                                MATCH (source:Blog {{blog_id: {source_id}}}),
                                      (target:Blog {{blog_id: {target_id}}})
                                CREATE (source)-[:LINKS_TO {{edge_id: {edge_id}}}]->(target)
                            $$) AS (result agtype)
                            """
                        )
                    )

                vertex_count = _agtype_to_int(
                    connection.execute(
                        text(
                            f"""
                            SELECT *
                            FROM cypher('{self.graph_name}', $$
                                MATCH (n:Blog) RETURN count(n)
                            $$) AS (count agtype)
                            """
                        )
                    ).scalar_one()
                )
                edge_count = _agtype_to_int(
                    connection.execute(
                        text(
                            f"""
                            SELECT *
                            FROM cypher('{self.graph_name}', $$
                                MATCH ()-[r:LINKS_TO]->() RETURN count(r)
                            $$) AS (count agtype)
                            """
                        )
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
