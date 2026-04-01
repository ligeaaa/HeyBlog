"""Regression tests for repository import and backend selection."""

from pathlib import Path
import sqlite3
from typing import Any

import pytest

import persistence_api.repository as repository_module
import persistence_api.schema as schema_module


def test_build_repository_uses_sqlite_when_psycopg_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SQLite repository creation should not require the PostgreSQL driver."""
    monkeypatch.setattr(repository_module, "psycopg", None)
    monkeypatch.setattr(repository_module, "dict_row", None)

    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    blog_id, inserted = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
        source_blog_id=None,
    )

    assert inserted is True
    assert repository.get_blog(blog_id)["domain"] == "blog.example.com"


def test_build_repository_raises_helpful_error_for_postgres_without_psycopg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Postgres path should fail with an actionable error when psycopg is absent."""
    monkeypatch.setattr(repository_module, "psycopg", None)
    monkeypatch.setattr(repository_module, "dict_row", None)

    with pytest.raises(ModuleNotFoundError, match="psycopg"):
        repository_module.build_repository(
            db_path=tmp_path / "db.sqlite",
            db_dsn="postgresql://heyblog:heyblog@persistence-db:5432/heyblog",
        )


def test_sqlite_repository_reset_clears_data_and_restarts_ids(tmp_path: Path) -> None:
    """Reset should wipe crawler data and restart SQLite autoincrement ids."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    first_blog_id, inserted = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
        source_blog_id=None,
    )
    assert inserted is True
    second_blog_id, inserted = repository.upsert_blog(
        url="https://friend.example.com/",
        normalized_url="https://friend.example.com/",
        domain="friend.example.com",
        source_blog_id=first_blog_id,
    )
    assert inserted is True
    repository.add_edge(
        from_blog_id=first_blog_id,
        to_blog_id=second_blog_id,
        link_url_raw="https://friend.example.com/",
        link_text="Friend Blog",
    )
    repository.add_log(
        blog_id=first_blog_id,
        stage="crawl",
        result="ok",
        message="Crawled blog.example.com",
    )

    result = repository.reset()

    assert result == {
        "ok": True,
        "blogs_deleted": 2,
        "edges_deleted": 1,
        "logs_deleted": 1,
    }
    assert repository.list_blogs() == []
    assert repository.list_edges() == []
    assert repository.list_logs() == []
    assert repository.stats()["total_blogs"] == 0
    assert repository.stats()["total_edges"] == 0

    new_blog_id, inserted = repository.upsert_blog(
        url="https://reset.example.com/",
        normalized_url="https://reset.example.com/",
        domain="reset.example.com",
        source_blog_id=None,
    )
    assert inserted is True
    assert new_blog_id == 1


def test_sqlite_repository_mark_blog_result_persists_site_metadata(tmp_path: Path) -> None:
    """Result updates should store homepage-derived title and icon fields."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    blog_id, inserted = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
        source_blog_id=None,
    )
    assert inserted is True

    repository.mark_blog_result(
        blog_id=blog_id,
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=2,
        metadata_captured=True,
        title="Blog Example",
        icon_url="https://blog.example.com/favicon.ico",
    )

    blog = repository.get_blog(blog_id)
    assert blog is not None
    assert blog["title"] == "Blog Example"
    assert blog["icon_url"] == "https://blog.example.com/favicon.ico"


def test_sqlite_repository_requeues_processing_blogs_on_restart(tmp_path: Path) -> None:
    """Repository init should recover interrupted PROCESSING blogs back to WAITING."""
    db_path = tmp_path / "db.sqlite"
    repository = repository_module.build_repository(db_path=db_path)
    blog_id, inserted = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
        source_blog_id=None,
    )
    assert inserted is True

    claimed = repository.get_next_waiting_blog()
    assert claimed is not None
    assert claimed["id"] == blog_id
    assert repository.stats()["processing_tasks"] == 1

    recovered = repository_module.build_repository(db_path=db_path)

    stats = recovered.stats()
    assert stats["processing_tasks"] == 0
    assert stats["pending_tasks"] == 1

    blog = recovered.get_blog(blog_id)
    assert blog is not None
    assert blog["crawl_status"] == "WAITING"

    reclaimed = recovered.get_next_waiting_blog()
    assert reclaimed is not None
    assert reclaimed["id"] == blog_id


def test_sqlite_repository_claims_waiting_blogs_in_id_order(tmp_path: Path) -> None:
    """Queue claiming should be a stable FIFO over WAITING rows."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    first_blog_id, _ = repository.upsert_blog(
        url="https://first.example/",
        normalized_url="https://first.example/",
        domain="first.example",
        source_blog_id=None,
    )
    second_blog_id, _ = repository.upsert_blog(
        url="https://second.example/",
        normalized_url="https://second.example/",
        domain="second.example",
        source_blog_id=first_blog_id,
    )

    first_claim = repository.get_next_waiting_blog()
    second_claim = repository.get_next_waiting_blog()

    assert first_claim is not None
    assert second_claim is not None
    assert first_claim["id"] == first_blog_id
    assert second_claim["id"] == second_blog_id


def test_build_repository_rebuilds_existing_sqlite_blog_table_without_depth(tmp_path: Path) -> None:
    """Repository init should rebuild legacy SQLite blog tables to drop depth."""
    db_path = tmp_path / "legacy.sqlite"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE blogs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          url TEXT NOT NULL,
          normalized_url TEXT NOT NULL UNIQUE,
          domain TEXT NOT NULL,
          status_code INTEGER,
          crawl_status TEXT NOT NULL DEFAULT 'WAITING',
          friend_links_count INTEGER NOT NULL DEFAULT 0,
          depth INTEGER NOT NULL DEFAULT 0,
          source_blog_id INTEGER,
          last_crawled_at TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE edges (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          from_blog_id INTEGER NOT NULL,
          to_blog_id INTEGER NOT NULL,
          link_url_raw TEXT NOT NULL,
          link_text TEXT,
          discovered_at TEXT NOT NULL,
          FOREIGN KEY(from_blog_id) REFERENCES blogs(id) ON DELETE CASCADE,
          FOREIGN KEY(to_blog_id) REFERENCES blogs(id) ON DELETE CASCADE
        );

        CREATE TABLE crawl_logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          blog_id INTEGER,
          stage TEXT NOT NULL,
          result TEXT NOT NULL,
          message TEXT NOT NULL,
          created_at TEXT NOT NULL,
          FOREIGN KEY(blog_id) REFERENCES blogs(id) ON DELETE SET NULL
        );
        """
    )
    connection.execute(
        """
        INSERT INTO blogs (
          id, url, normalized_url, domain, status_code, crawl_status,
          friend_links_count, depth, source_blog_id, last_crawled_at,
          created_at, updated_at
        )
        VALUES (
          1, 'https://blog.example.com/', 'https://blog.example.com/', 'blog.example.com',
          200, 'FINISHED', 2, 0, NULL, NULL,
          '2026-03-31T00:00:00Z', '2026-03-31T00:00:00Z'
        )
        """
    )
    connection.execute(
        """
        INSERT INTO edges (
          id, from_blog_id, to_blog_id, link_url_raw, link_text, discovered_at
        )
        VALUES (
          1, 1, 1, 'https://blog.example.com/', 'Self link', '2026-03-31T00:00:00Z'
        )
        """
    )
    connection.execute(
        """
        INSERT INTO crawl_logs (
          id, blog_id, stage, result, message, created_at
        )
        VALUES (
          1, 1, 'crawl', 'ok', 'legacy row', '2026-03-31T00:00:00Z'
        )
        """
    )
    connection.commit()
    connection.close()

    repository = repository_module.build_repository(db_path=db_path)

    migrated = sqlite3.connect(db_path)
    columns = {
        row[1]
        for row in migrated.execute("PRAGMA table_info(blogs)").fetchall()
    }
    migrated.close()

    assert "title" in columns
    assert "icon_url" in columns
    assert "depth" not in columns
    blog = repository.get_blog(1)
    assert blog is not None
    assert blog["source_blog_id"] is None
    assert "depth" not in blog
    assert len(repository.list_edges()) == 1
    logs = repository.list_logs()
    assert len(logs) == 1
    assert logs[0]["blog_id"] == 1
    assert logs[0]["message"] == "legacy row"


def test_sqlite_repository_blog_catalog_paginates_and_filters(tmp_path: Path) -> None:
    """Catalog queries should paginate and filter on the server side."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    seeded: list[int] = []
    for index in range(4):
        blog_id, inserted = repository.upsert_blog(
            url=f"https://site-{index}.example/posts/{index}",
            normalized_url=f"https://site-{index}.example/posts/{index}",
            domain=f"site-{index}.example",
            source_blog_id=None,
        )
        assert inserted is True
        repository.mark_blog_result(
            blog_id=blog_id,
            crawl_status="FINISHED" if index % 2 == 0 else "FAILED",
            status_code=200 if index % 2 == 0 else 500,
            friend_links_count=index,
            metadata_captured=True,
            title=f"Example Site {index}",
            icon_url=f"https://site-{index}.example/favicon.ico",
        )
        seeded.append(blog_id)

    first_page = repository.list_blogs_catalog(page=1, page_size=2)
    assert [row["id"] for row in first_page["items"]] == [seeded[3], seeded[2]]
    assert first_page["page"] == 1
    assert first_page["page_size"] == 2
    assert first_page["total_items"] == 4
    assert first_page["total_pages"] == 2
    assert first_page["has_next"] is True
    assert first_page["has_prev"] is False

    second_page = repository.list_blogs_catalog(page=2, page_size=2)
    assert [row["id"] for row in second_page["items"]] == [seeded[1], seeded[0]]
    assert second_page["has_next"] is False
    assert second_page["has_prev"] is True

    site_filtered = repository.list_blogs_catalog(site="Site 2")
    assert [row["id"] for row in site_filtered["items"]] == [seeded[2]]
    domain_filtered = repository.list_blogs_catalog(site="site-1.example")
    assert [row["id"] for row in domain_filtered["items"]] == [seeded[1]]
    url_filtered = repository.list_blogs_catalog(url="/posts/3")
    assert [row["id"] for row in url_filtered["items"]] == [seeded[3]]
    normalized_url_filtered = repository.list_blogs_catalog(url="SITE-0.EXAMPLE")
    assert [row["id"] for row in normalized_url_filtered["items"]] == [seeded[0]]
    combined = repository.list_blogs_catalog(q="site", status="finished")
    assert [row["id"] for row in combined["items"]] == [seeded[2], seeded[0]]


def test_sqlite_repository_blog_catalog_normalizes_query_inputs(tmp_path: Path) -> None:
    """Catalog normalization should clamp paging and reject unsupported statuses."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    for index in range(3):
        blog_id, inserted = repository.upsert_blog(
            url=f"https://normalize-{index}.example",
            normalized_url=f"https://normalize-{index}.example",
            domain=f"normalize-{index}.example",
            source_blog_id=None,
        )
        assert inserted is True
        repository.mark_blog_result(
            blog_id=blog_id,
            crawl_status="WAITING" if index == 0 else "FINISHED",
            status_code=200,
            friend_links_count=0,
        )

    oversized = repository.list_blogs_catalog(page=0, page_size=999, site="   ", q="   ")
    assert oversized["page"] == 1
    assert oversized["page_size"] == 200
    assert oversized["filters"] == {"q": None, "site": None, "url": None, "status": None}

    last_page = repository.list_blogs_catalog(page=99, page_size=2)
    assert last_page["page"] == 2
    assert len(last_page["items"]) == 1

    waiting = repository.list_blogs_catalog(status=" waiting ")
    assert waiting["filters"]["status"] == "WAITING"
    assert len(waiting["items"]) == 1

    with pytest.raises(ValueError, match="Unsupported crawl status"):
        repository.list_blogs_catalog(status="unknown")


class _RecordingCursor:
    def __init__(self, statements: list[str]) -> None:
        self._statements = statements

    def __enter__(self) -> "_RecordingCursor":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    def execute(self, statement: str) -> None:
        self._statements.append(" ".join(statement.split()))


class _RecordingConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def cursor(self) -> _RecordingCursor:
        return _RecordingCursor(self.statements)


def test_init_postgres_db_does_not_drop_depth_column_on_startup() -> None:
    """Postgres init should avoid destructive DROP COLUMN DDL during normal boot."""
    connection = _RecordingConnection()

    schema_module.init_postgres_db(connection)

    assert any("ADD COLUMN IF NOT EXISTS title" in statement for statement in connection.statements)
    assert any("ADD COLUMN IF NOT EXISTS icon_url" in statement for statement in connection.statements)
    assert all("DROP COLUMN IF EXISTS depth" not in statement for statement in connection.statements)
