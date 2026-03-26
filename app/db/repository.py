"""Provide repository operations for blogs, edges, and crawl logs."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from typing import Iterator

from app.db.schema import init_db


def now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


class Repository:
    """Encapsulate all persistence operations against SQLite."""

    def __init__(self, db_path: Path) -> None:
        """Initialize the repository and ensure schema availability."""
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            init_db(connection)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a managed SQLite connection with row factory enabled."""
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def add_log(
        self, stage: str, result: str, message: str, blog_id: int | None = None
    ) -> None:
        """Insert one crawler log entry."""
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO crawl_logs (blog_id, stage, result, message, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (blog_id, stage, result, message, now_iso()),
            )
            connection.commit()

    def upsert_blog(
        self,
        *,
        url: str,
        normalized_url: str,
        domain: str,
        depth: int,
        source_blog_id: int | None,
    ) -> tuple[int, bool]:
        """Insert a blog if absent and return its id with insertion status."""
        timestamp = now_iso()
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM blogs WHERE normalized_url = ?",
                (normalized_url,),
            ).fetchone()
            if existing:
                return int(existing["id"]), False

            cursor = connection.execute(
                """
                INSERT INTO blogs (
                  url, normalized_url, domain, crawl_status, depth,
                  source_blog_id, created_at, updated_at
                )
                VALUES (?, ?, ?, 'WAITING', ?, ?, ?, ?)
                """,
                (url, normalized_url, domain, depth, source_blog_id, timestamp, timestamp),
            )
            connection.commit()
            return int(cursor.lastrowid), True

    def pending_blog_count(self) -> int:
        """Count blogs waiting to be crawled."""
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM blogs WHERE crawl_status = 'WAITING'"
            ).fetchone()
            return int(row["count"])

    def get_next_waiting_blog(self, max_depth: int) -> sqlite3.Row | None:
        """Fetch and reserve the next waiting blog up to the provided depth."""
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM blogs
                WHERE crawl_status = 'WAITING' AND depth <= ?
                ORDER BY depth ASC, id ASC
                LIMIT 1
                """,
                (max_depth,),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE blogs
                SET crawl_status = 'PROCESSING', updated_at = ?
                WHERE id = ?
                """,
                (now_iso(), row["id"]),
            )
            connection.commit()
            return row

    def mark_blog_result(
        self,
        *,
        blog_id: int,
        crawl_status: str,
        status_code: int | None,
        friend_links_count: int,
    ) -> None:
        """Store crawl result metadata for one blog."""
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE blogs
                SET crawl_status = ?, status_code = ?, friend_links_count = ?,
                    last_crawled_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    crawl_status,
                    status_code,
                    friend_links_count,
                    now_iso(),
                    now_iso(),
                    blog_id,
                ),
            )
            connection.commit()

    def add_edge(
        self,
        *,
        from_blog_id: int,
        to_blog_id: int,
        link_url_raw: str,
        link_text: str | None,
    ) -> None:
        """Insert an edge between two blogs if it does not yet exist."""
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO edges (
                  from_blog_id, to_blog_id, link_url_raw, link_text, discovered_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (from_blog_id, to_blog_id, link_url_raw, link_text, now_iso()),
            )
            connection.commit()

    def list_blogs(self) -> list[dict[str, Any]]:
        """Return all blog rows ordered by id."""
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, url, normalized_url, domain, status_code, crawl_status,
                       friend_links_count, depth, source_blog_id, last_crawled_at,
                       created_at, updated_at
                FROM blogs
                ORDER BY id ASC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def get_blog(self, blog_id: int) -> dict[str, Any] | None:
        """Return one blog by id or None when absent."""
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM blogs WHERE id = ?",
                (blog_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_edges(self) -> list[dict[str, Any]]:
        """Return all stored graph edges ordered by id."""
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, from_blog_id, to_blog_id, link_url_raw, link_text, discovered_at
                FROM edges
                ORDER BY id ASC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def list_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return latest crawl log rows up to the given limit."""
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, blog_id, stage, result, message, created_at
                FROM crawl_logs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def stats(self) -> dict[str, Any]:
        """Return aggregate crawler statistics across blogs and edges."""
        with self.connect() as connection:
            status_rows = connection.execute(
                """
                SELECT crawl_status, COUNT(*) AS count
                FROM blogs
                GROUP BY crawl_status
                """
            ).fetchall()
            status_counts: dict[str, int] = {
                str(row["crawl_status"]): int(row["count"]) for row in status_rows
            }
            summary = connection.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM blogs) AS total_blogs,
                  (SELECT COUNT(*) FROM edges) AS total_edges,
                  (SELECT MAX(depth) FROM blogs) AS max_depth,
                  (SELECT AVG(friend_links_count) FROM blogs) AS average_friend_links
                """
            ).fetchone()
            return {
                "total_blogs": int(summary["total_blogs"] or 0),
                "total_edges": int(summary["total_edges"] or 0),
                "max_depth": int(summary["max_depth"] or 0),
                "average_friend_links": float(summary["average_friend_links"] or 0.0),
                "status_counts": status_counts,
                "pending_tasks": int(status_counts.get("WAITING", 0)),
                "processing_tasks": int(status_counts.get("PROCESSING", 0)),
                "failed_tasks": int(status_counts.get("FAILED", 0)),
                "finished_tasks": int(status_counts.get("FINISHED", 0)),
            }
