"""Regression tests for repository import and backend selection."""

from pathlib import Path

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
