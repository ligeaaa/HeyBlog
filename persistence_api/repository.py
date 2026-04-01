"""Repository implementations for SQLite and PostgreSQL persistence."""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from typing import Iterator
from typing import Protocol

try:
    import psycopg
    from psycopg.rows import dict_row
except ModuleNotFoundError:  # pragma: no cover - exercised via regression tests.
    psycopg = None
    dict_row = None

from persistence_api.schema import init_postgres_db
from persistence_api.schema import init_sqlite_db


PSYCOPG_IMPORT_ERROR = (
    "psycopg is required for PostgreSQL support. "
    "Install heyblog with the 'psycopg[binary]' dependency."
)


def _postgres_driver() -> tuple[Any, Any]:
    """Return the PostgreSQL driver and row factory when available."""
    if psycopg is None or dict_row is None:
        raise ModuleNotFoundError(PSYCOPG_IMPORT_ERROR)
    return psycopg, dict_row


def now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


class RepositoryProtocol(Protocol):
    """Protocol shared by SQLite, PostgreSQL, and HTTP-backed repositories."""

    def add_log(
        self, stage: str, result: str, message: str, blog_id: int | None = None
    ) -> None: ...

    def upsert_blog(
        self,
        *,
        url: str,
        normalized_url: str,
        domain: str,
        source_blog_id: int | None,
    ) -> tuple[int, bool]: ...

    def get_next_waiting_blog(self) -> dict[str, Any] | None: ...

    def mark_blog_result(
        self,
        *,
        blog_id: int,
        crawl_status: str,
        status_code: int | None,
        friend_links_count: int,
        metadata_captured: bool = False,
        title: str | None = None,
        icon_url: str | None = None,
    ) -> None: ...

    def add_edge(
        self,
        *,
        from_blog_id: int,
        to_blog_id: int,
        link_url_raw: str,
        link_text: str | None,
    ) -> None: ...

    def list_blogs(self) -> list[dict[str, Any]]: ...

    def get_blog(self, blog_id: int) -> dict[str, Any] | None: ...

    def list_edges(self) -> list[dict[str, Any]]: ...

    def list_logs(self, limit: int = 100) -> list[dict[str, Any]]: ...

    def stats(self) -> dict[str, Any]: ...

    def reset(self) -> dict[str, Any]: ...


class Repository:
    """Encapsulate all persistence operations against SQLite."""

    def __init__(self, db_path: Path) -> None:
        """Initialize the repository and ensure schema availability."""
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            init_sqlite_db(connection)
            self._requeue_processing_blogs(connection)
            connection.commit()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a managed SQLite connection with row factory enabled."""
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def _requeue_processing_blogs(self, connection: sqlite3.Connection) -> None:
        """Recover rows left in PROCESSING after an unclean crawler shutdown."""
        connection.execute(
            """
            UPDATE blogs
            SET crawl_status = 'WAITING', updated_at = ?
            WHERE crawl_status = 'PROCESSING'
            """,
            (now_iso(),),
        )

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
                  url, normalized_url, domain, crawl_status,
                  source_blog_id, created_at, updated_at
                )
                VALUES (?, ?, ?, 'WAITING', ?, ?, ?)
                """,
                (url, normalized_url, domain, source_blog_id, timestamp, timestamp),
            )
            connection.commit()
            return int(cursor.lastrowid), True

    def get_next_waiting_blog(self) -> dict[str, Any] | None:
        """Fetch and reserve the next waiting blog in stable insertion order."""
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM blogs
                WHERE crawl_status = 'WAITING'
                ORDER BY id ASC
                LIMIT 1
                """,
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
            return dict(row)

    def mark_blog_result(
        self,
        *,
        blog_id: int,
        crawl_status: str,
        status_code: int | None,
        friend_links_count: int,
        metadata_captured: bool = False,
        title: str | None = None,
        icon_url: str | None = None,
    ) -> None:
        """Store crawl result metadata for one blog."""
        with self.connect() as connection:
            if metadata_captured:
                connection.execute(
                    """
                    UPDATE blogs
                    SET crawl_status = ?, status_code = ?, friend_links_count = ?,
                        title = ?, icon_url = ?, last_crawled_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        crawl_status,
                        status_code,
                        friend_links_count,
                        title,
                        icon_url,
                        now_iso(),
                        now_iso(),
                        blog_id,
                    ),
                )
            else:
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
                SELECT id, url, normalized_url, domain, title, icon_url, status_code, crawl_status,
                       friend_links_count, source_blog_id, last_crawled_at,
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
                """
                SELECT id, url, normalized_url, domain, title, icon_url, status_code, crawl_status,
                       friend_links_count, source_blog_id, last_crawled_at, created_at, updated_at
                FROM blogs
                WHERE id = ?
                """,
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
                  (SELECT AVG(friend_links_count) FROM blogs) AS average_friend_links
                """
            ).fetchone()
            return {
                "total_blogs": int(summary["total_blogs"] or 0),
                "total_edges": int(summary["total_edges"] or 0),
                "average_friend_links": float(summary["average_friend_links"] or 0.0),
                "status_counts": status_counts,
                "pending_tasks": int(status_counts.get("WAITING", 0)),
                "processing_tasks": int(status_counts.get("PROCESSING", 0)),
                "failed_tasks": int(status_counts.get("FAILED", 0)),
                "finished_tasks": int(status_counts.get("FINISHED", 0)),
            }

    def reset(self) -> dict[str, Any]:
        """Clear all crawler data and reset autoincrement counters."""
        with self.connect() as connection:
            summary = connection.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM blogs) AS blogs,
                  (SELECT COUNT(*) FROM edges) AS edges,
                  (SELECT COUNT(*) FROM crawl_logs) AS logs
                """
            ).fetchone()
            connection.execute("DELETE FROM edges")
            connection.execute("DELETE FROM crawl_logs")
            connection.execute("DELETE FROM blogs")
            connection.execute(
                "DELETE FROM sqlite_sequence WHERE name IN ('blogs', 'edges', 'crawl_logs')"
            )
            connection.commit()
        return {
            "ok": True,
            "blogs_deleted": int(summary["blogs"] or 0),
            "edges_deleted": int(summary["edges"] or 0),
            "logs_deleted": int(summary["logs"] or 0),
        }


class PostgresRepository:
    """Encapsulate all persistence operations against PostgreSQL."""

    def __init__(self, db_dsn: str) -> None:
        """Initialize the repository and ensure schema availability."""
        self.db_dsn = db_dsn
        with self.connect(wait_for_ready=True) as connection:
            init_postgres_db(connection)
            self._requeue_processing_blogs(connection)

    @contextmanager
    def connect(self, *, wait_for_ready: bool = False) -> Iterator[psycopg.Connection[Any]]:
        """Yield a managed PostgreSQL connection with dict rows enabled."""
        driver, row_factory = _postgres_driver()
        if wait_for_ready:
            connection = self._connect_with_retry()
        else:
            connection = driver.connect(self.db_dsn, row_factory=row_factory)
        with connection:
            yield connection

    def _connect_with_retry(self) -> psycopg.Connection[Any]:
        """Retry startup connections while the database container becomes ready."""
        driver, row_factory = _postgres_driver()
        last_error: Exception | None = None
        for _attempt in range(20):
            try:
                return driver.connect(self.db_dsn, row_factory=row_factory)
            except driver.OperationalError as exc:
                last_error = exc
                time.sleep(1)
        assert last_error is not None
        raise last_error

    def _requeue_processing_blogs(self, connection: psycopg.Connection[Any]) -> None:
        """Recover rows left in PROCESSING after an unclean crawler shutdown."""
        connection.execute(
            """
            UPDATE blogs
            SET crawl_status = 'WAITING', updated_at = %s
            WHERE crawl_status = 'PROCESSING'
            """,
            (now_iso(),),
        )

    def add_log(
        self, stage: str, result: str, message: str, blog_id: int | None = None
    ) -> None:
        """Insert one crawler log entry."""
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO crawl_logs (blog_id, stage, result, message, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (blog_id, stage, result, message, now_iso()),
            )

    def upsert_blog(
        self,
        *,
        url: str,
        normalized_url: str,
        domain: str,
        source_blog_id: int | None,
    ) -> tuple[int, bool]:
        """Insert a blog if absent and return its id with insertion status."""
        timestamp = now_iso()
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM blogs WHERE normalized_url = %s",
                (normalized_url,),
            ).fetchone()
            if existing:
                return int(existing["id"]), False

            created = connection.execute(
                """
                INSERT INTO blogs (
                  url, normalized_url, domain, crawl_status,
                  source_blog_id, created_at, updated_at
                )
                VALUES (%s, %s, %s, 'WAITING', %s, %s, %s)
                RETURNING id
                """,
                (url, normalized_url, domain, source_blog_id, timestamp, timestamp),
            ).fetchone()
            return int(created["id"]), True

    def get_next_waiting_blog(self) -> dict[str, Any] | None:
        """Fetch and reserve the next waiting blog using row-level locks."""
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM blogs
                WHERE crawl_status = 'WAITING'
                ORDER BY id ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """,
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE blogs
                SET crawl_status = 'PROCESSING', updated_at = %s
                WHERE id = %s
                """,
                (now_iso(), row["id"]),
            )
            return dict(row)

    def mark_blog_result(
        self,
        *,
        blog_id: int,
        crawl_status: str,
        status_code: int | None,
        friend_links_count: int,
        metadata_captured: bool = False,
        title: str | None = None,
        icon_url: str | None = None,
    ) -> None:
        """Store crawl result metadata for one blog."""
        with self.connect() as connection:
            if metadata_captured:
                connection.execute(
                    """
                    UPDATE blogs
                    SET crawl_status = %s, status_code = %s, friend_links_count = %s,
                        title = %s, icon_url = %s, last_crawled_at = %s, updated_at = %s
                    WHERE id = %s
                    """,
                    (
                        crawl_status,
                        status_code,
                        friend_links_count,
                        title,
                        icon_url,
                        now_iso(),
                        now_iso(),
                        blog_id,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE blogs
                    SET crawl_status = %s, status_code = %s, friend_links_count = %s,
                        last_crawled_at = %s, updated_at = %s
                    WHERE id = %s
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
                INSERT INTO edges (
                  from_blog_id, to_blog_id, link_url_raw, link_text, discovered_at
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (from_blog_id, to_blog_id) DO NOTHING
                """,
                (from_blog_id, to_blog_id, link_url_raw, link_text, now_iso()),
            )

    def list_blogs(self) -> list[dict[str, Any]]:
        """Return all blog rows ordered by id."""
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, url, normalized_url, domain, title, icon_url, status_code, crawl_status,
                       friend_links_count, source_blog_id, last_crawled_at,
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
                """
                SELECT id, url, normalized_url, domain, title, icon_url, status_code, crawl_status,
                       friend_links_count, source_blog_id, last_crawled_at, created_at, updated_at
                FROM blogs
                WHERE id = %s
                """,
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
                LIMIT %s
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
                  (SELECT AVG(friend_links_count) FROM blogs) AS average_friend_links
                """
            ).fetchone()
            return {
                "total_blogs": int(summary["total_blogs"] or 0),
                "total_edges": int(summary["total_edges"] or 0),
                "average_friend_links": float(summary["average_friend_links"] or 0.0),
                "status_counts": status_counts,
                "pending_tasks": int(status_counts.get("WAITING", 0)),
                "processing_tasks": int(status_counts.get("PROCESSING", 0)),
                "failed_tasks": int(status_counts.get("FAILED", 0)),
                "finished_tasks": int(status_counts.get("FINISHED", 0)),
            }

    def reset(self) -> dict[str, Any]:
        """Clear all crawler data and restart PostgreSQL identity counters."""
        with self.connect() as connection:
            summary = connection.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM blogs) AS blogs,
                  (SELECT COUNT(*) FROM edges) AS edges,
                  (SELECT COUNT(*) FROM crawl_logs) AS logs
                """
            ).fetchone()
            connection.execute(
                "TRUNCATE TABLE crawl_logs, edges, blogs RESTART IDENTITY CASCADE"
            )
        return {
            "ok": True,
            "blogs_deleted": int(summary["blogs"] or 0),
            "edges_deleted": int(summary["edges"] or 0),
            "logs_deleted": int(summary["logs"] or 0),
        }


def build_repository(*, db_path: Path, db_dsn: str | None = None) -> RepositoryProtocol:
    """Build the configured repository implementation."""
    if db_dsn:
        return PostgresRepository(db_dsn)
    return Repository(db_path)
