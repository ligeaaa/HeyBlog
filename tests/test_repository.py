"""Regression tests for the SQLAlchemy-backed repository."""

from pathlib import Path

import pytest

import persistence_api.repository as repository_module


def test_build_repository_roundtrip_works_with_path_backed_repository(tmp_path: Path) -> None:
    """The compatibility wrapper should still support path-backed test repositories."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    blog_id, inserted = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
    )

    assert inserted is True
    assert repository.get_blog(blog_id)["domain"] == "blog.example.com"


def test_repository_reset_clears_data_and_restarts_ids(tmp_path: Path) -> None:
    """Reset should wipe graph data and restart primary keys."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    first_blog_id, inserted = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
    )
    assert inserted is True
    second_blog_id, inserted = repository.upsert_blog(
        url="https://friend.example.com/",
        normalized_url="https://friend.example.com/",
        domain="friend.example.com",
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
        message="This should not be persisted",
    )

    result = repository.reset()

    assert result == {
        "ok": True,
        "blogs_deleted": 2,
        "edges_deleted": 1,
        "logs_deleted": 0,
        "ingestion_requests_deleted": 0,
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
    )
    assert inserted is True
    assert new_blog_id == 1


def test_repository_mark_blog_result_persists_site_metadata(tmp_path: Path) -> None:
    """Result updates should store homepage-derived title and icon fields."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    blog_id, inserted = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
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


def test_repository_defaults_blog_email_to_none(tmp_path: Path) -> None:
    """New blogs should keep a nullable email field until claimed by a user."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    blog_id, inserted = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
    )
    assert inserted is True

    blog = repository.get_blog(blog_id)
    assert blog is not None
    assert blog["email"] is None


def test_repository_creates_ingestion_request_and_persists_blog_email(tmp_path: Path) -> None:
    """Self-serve ingestion should capture the requester email onto the seed blog."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")

    created = repository.create_ingestion_request(
        homepage_url="https://blog.example.com/",
        email="owner@example.com",
    )

    assert created["status"] == "QUEUED"
    assert created["request_id"] == created["id"]
    assert created["email"] == "owner@example.com"
    assert created["blog"]["email"] == "owner@example.com"

    fetched = repository.get_ingestion_request(
        request_id=created["request_id"],
        request_token=created["request_token"],
    )
    assert fetched is not None
    assert fetched["normalized_url"] == "https://blog.example.com/"
    assert fetched["seed_blog_id"] == created["seed_blog_id"]


def test_repository_dedupes_ingestion_request_by_normalized_url(tmp_path: Path) -> None:
    """Repeated requests for the same blog should reuse one active ingestion request."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")

    first = repository.create_ingestion_request(
        homepage_url="https://blog.example.com/?utm_source=test",
        email="owner@example.com",
    )
    second = repository.create_ingestion_request(
        homepage_url="https://blog.example.com/",
        email="owner@example.com",
    )

    assert first["request_id"] == second["request_id"]
    assert len(repository.list_blogs()) == 1


def test_repository_dedupes_existing_finished_blog_before_creating_request(tmp_path: Path) -> None:
    """Already-finished blogs should short-circuit to a DEDUPED_EXISTING response."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    blog_id, inserted = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
    )
    assert inserted is True
    repository.mark_blog_result(
        blog_id=blog_id,
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=0,
    )

    response = repository.create_ingestion_request(
        homepage_url="https://blog.example.com/",
        email="owner@example.com",
    )

    assert response["status"] == "DEDUPED_EXISTING"
    assert response["blog_id"] == blog_id
    assert response["request_id"] is None


def test_repository_requeues_processing_blogs_on_restart(tmp_path: Path) -> None:
    """Repository init should recover interrupted PROCESSING blogs back to WAITING."""
    db_path = tmp_path / "db.sqlite"
    repository = repository_module.build_repository(db_path=db_path)
    blog_id, inserted = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
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


def test_repository_claims_waiting_blogs_in_id_order(tmp_path: Path) -> None:
    """Queue claiming should be a stable FIFO over WAITING rows."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    first_blog_id, _ = repository.upsert_blog(
        url="https://first.example/",
        normalized_url="https://first.example/",
        domain="first.example",
    )
    second_blog_id, _ = repository.upsert_blog(
        url="https://second.example/",
        normalized_url="https://second.example/",
        domain="second.example",
    )

    first_claim = repository.get_next_waiting_blog()
    second_claim = repository.get_next_waiting_blog()

    assert first_claim is not None
    assert second_claim is not None
    assert first_claim["id"] == first_blog_id
    assert second_claim["id"] == second_blog_id


def test_repository_blog_catalog_paginates_and_filters(tmp_path: Path) -> None:
    """Catalog queries should paginate and filter on the server side."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    seeded: list[int] = []
    for index in range(4):
        blog_id, inserted = repository.upsert_blog(
            url=f"https://site-{index}.example/posts/{index}",
            normalized_url=f"https://site-{index}.example/posts/{index}",
            domain=f"site-{index}.example",
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
    assert first_page["items"][0]["connection_count"] >= 0
    assert "activity_at" in first_page["items"][0]
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


def test_repository_blog_catalog_normalizes_query_inputs(tmp_path: Path) -> None:
    """Catalog normalization should clamp paging and reject unsupported statuses."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    for index in range(3):
        blog_id, inserted = repository.upsert_blog(
            url=f"https://normalize-{index}.example",
            normalized_url=f"https://normalize-{index}.example",
            domain=f"normalize-{index}.example",
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
    assert oversized["filters"] == {
        "q": None,
        "site": None,
        "url": None,
        "status": None,
        "sort": "id_desc",
        "has_title": None,
        "has_icon": None,
        "min_connections": 0,
    }

    last_page = repository.list_blogs_catalog(page=99, page_size=2)
    assert last_page["page"] == 2
    assert len(last_page["items"]) == 1

    waiting = repository.list_blogs_catalog(status=" waiting ")
    assert waiting["filters"]["status"] == "WAITING"
    assert len(waiting["items"]) == 1

    with pytest.raises(ValueError, match="Unsupported crawl status"):
        repository.list_blogs_catalog(status="unknown")

    with pytest.raises(ValueError, match="Unsupported blog catalog sort"):
        repository.list_blogs_catalog(sort="magic")

    empty_optional_filters = repository.list_blogs_catalog(
        has_title="",
        has_icon="",
        min_connections="",
    )
    assert empty_optional_filters["filters"]["has_title"] is None
    assert empty_optional_filters["filters"]["has_icon"] is None
    assert empty_optional_filters["filters"]["min_connections"] == 0


def test_repository_blog_catalog_uses_display_identity_fallbacks_for_legacy_rows(tmp_path: Path) -> None:
    """Catalog should remain usable for older rows that were created before metadata capture existed."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    blog_id, inserted = repository.upsert_blog(
        url="https://legacy.example/posts/1",
        normalized_url="https://legacy.example/posts/1",
        domain="legacy.example",
    )
    assert inserted is True
    repository.mark_blog_result(
        blog_id=blog_id,
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=0,
        metadata_captured=False,
    )

    title_filtered = repository.list_blogs_catalog(has_title=True)
    icon_filtered = repository.list_blogs_catalog(has_icon=True)

    assert [row["id"] for row in title_filtered["items"]] == [blog_id]
    assert [row["id"] for row in icon_filtered["items"]] == [blog_id]
    assert title_filtered["items"][0]["title"] == "legacy.example"
    assert icon_filtered["items"][0]["icon_url"] == "https://legacy.example/favicon.ico"


def test_repository_blog_detail_aggregates_bidirectional_relationships(tmp_path: Path) -> None:
    """Detail queries should inline incoming/outgoing edges with neighbor summaries."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    alpha_id, inserted = repository.upsert_blog(
        url="https://alpha.example/",
        normalized_url="https://alpha.example/",
        domain="alpha.example",
    )
    assert inserted is True
    beta_id, inserted = repository.upsert_blog(
        url="https://beta.example/",
        normalized_url="https://beta.example/",
        domain="beta.example",
    )
    assert inserted is True
    gamma_id, inserted = repository.upsert_blog(
        url="https://gamma.example/",
        normalized_url="https://gamma.example/",
        domain="gamma.example",
    )
    assert inserted is True

    for blog_id, domain in (
        (alpha_id, "alpha.example"),
        (beta_id, "beta.example"),
        (gamma_id, "gamma.example"),
    ):
        repository.mark_blog_result(
            blog_id=blog_id,
            crawl_status="FINISHED",
            status_code=200,
            friend_links_count=1,
            metadata_captured=True,
            title=f"{domain} title",
            icon_url=f"https://{domain}/favicon.ico",
        )

    repository.add_edge(
        from_blog_id=alpha_id,
        to_blog_id=beta_id,
        link_url_raw="https://beta.example/",
        link_text="Beta",
    )
    repository.add_edge(
        from_blog_id=gamma_id,
        to_blog_id=alpha_id,
        link_url_raw="https://alpha.example/",
        link_text="Alpha",
    )
    delta_id, inserted = repository.upsert_blog(
        url="https://delta.example/",
        normalized_url="https://delta.example/",
        domain="delta.example",
    )
    assert inserted is True
    repository.mark_blog_result(
        blog_id=delta_id,
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=1,
        metadata_captured=True,
        title="delta.example title",
        icon_url="https://delta.example/favicon.ico",
    )
    repository.add_edge(
        from_blog_id=beta_id,
        to_blog_id=delta_id,
        link_url_raw="https://delta.example/",
        link_text="Delta",
    )

    detail = repository.get_blog_detail(alpha_id)

    assert detail is not None
    assert detail["domain"] == "alpha.example"
    assert detail["outgoing_edges"] == [
        {
            "id": 1,
            "from_blog_id": alpha_id,
            "to_blog_id": beta_id,
            "link_url_raw": "https://beta.example/",
            "link_text": "Beta",
            "discovered_at": detail["outgoing_edges"][0]["discovered_at"],
            "neighbor_blog": {
                "id": beta_id,
                "domain": "beta.example",
                "title": "beta.example title",
                "icon_url": "https://beta.example/favicon.ico",
            },
        }
    ]
    assert detail["incoming_edges"] == [
        {
            "id": 2,
            "from_blog_id": gamma_id,
            "to_blog_id": alpha_id,
            "link_url_raw": "https://alpha.example/",
            "link_text": "Alpha",
            "discovered_at": detail["incoming_edges"][0]["discovered_at"],
            "neighbor_blog": {
                "id": gamma_id,
                "domain": "gamma.example",
                "title": "gamma.example title",
                "icon_url": "https://gamma.example/favicon.ico",
            },
        }
    ]
    assert detail["recommended_blogs"] == [
        {
            "blog": {
                "id": delta_id,
                "url": "https://delta.example/",
                "normalized_url": "https://delta.example/",
                "domain": "delta.example",
                "email": None,
                "title": "delta.example title",
                "icon_url": "https://delta.example/favicon.ico",
                "status_code": 200,
                "crawl_status": "FINISHED",
                "friend_links_count": 1,
                "last_crawled_at": detail["recommended_blogs"][0]["blog"]["last_crawled_at"],
                "created_at": detail["recommended_blogs"][0]["blog"]["created_at"],
                "updated_at": detail["recommended_blogs"][0]["blog"]["updated_at"],
                "incoming_count": 1,
                "outgoing_count": 0,
                "connection_count": 1,
                "activity_at": detail["recommended_blogs"][0]["blog"]["activity_at"],
                "identity_complete": True,
            },
            "reason": "mutual_connection",
            "mutual_connection_count": 1,
            "via_blogs": [
                {
                    "id": beta_id,
                    "domain": "beta.example",
                    "title": "beta.example title",
                    "icon_url": "https://beta.example/favicon.ico",
                }
            ],
        }
    ]
