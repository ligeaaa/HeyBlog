"""Regression tests for repository import and backend selection."""

from pathlib import Path
import sqlite3

import pytest

import persistence_api.repository as repository_module


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
        depth=0,
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
        depth=0,
        source_blog_id=None,
    )
    assert inserted is True
    second_blog_id, inserted = repository.upsert_blog(
        url="https://friend.example.com/",
        normalized_url="https://friend.example.com/",
        domain="friend.example.com",
        depth=1,
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
        depth=0,
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
        depth=0,
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


def test_build_repository_migrates_existing_sqlite_blog_table_with_metadata_columns(tmp_path: Path) -> None:
    """Repository init should add title/icon columns to an existing SQLite blogs table."""
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
          discovered_at TEXT NOT NULL
        );

        CREATE TABLE crawl_logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          blog_id INTEGER,
          stage TEXT NOT NULL,
          result TEXT NOT NULL,
          message TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        """
    )
    connection.commit()
    connection.close()

    repository_module.build_repository(db_path=db_path)

    migrated = sqlite3.connect(db_path)
    columns = {
        row[1]
        for row in migrated.execute("PRAGMA table_info(blogs)").fetchall()
    }
    migrated.close()

    assert "title" in columns
    assert "icon_url" in columns
