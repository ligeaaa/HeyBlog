"""Regression tests for the SQLAlchemy-backed repository."""

from pathlib import Path

import pytest

import persistence_api.repository as repository_module
from persistence_api.db import session_scope
from persistence_api.models import BlogLabelAssignmentModel
from persistence_api.models import BlogLabelTagModel
from persistence_api.models import BlogModel
from persistence_api.models import EdgeModel
from persistence_api.models import IngestionRequestModel
from shared.contracts.enums import CrawlStatus


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

    assert result["ok"] is True
    assert result["blogs_deleted"] == 2
    assert result["edges_deleted"] == 1
    assert result["logs_deleted"] == 0
    assert result["ingestion_requests_deleted"] == 0
    assert result["blog_link_labels_deleted"] == 0
    assert result["blog_label_tags_deleted"] == 0
    assert result["blog_dedup_scan_items_deleted"] == 0
    assert result["blog_dedup_scan_runs_deleted"] == 0
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


def test_repository_dedupes_ingestion_request_by_identity_key_but_keeps_history(tmp_path: Path) -> None:
    """Alias URLs should reuse one active request, but completed history must not block a new request."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")

    first = repository.create_ingestion_request(
        homepage_url="https://langhai.cc/",
        email="owner@example.com",
    )
    second = repository.create_ingestion_request(
        homepage_url="http://blog.langhai.cc/index.html",
        email="owner@example.com",
    )

    assert first["request_id"] == second["request_id"]
    assert first["identity_key"] == "site:langhai.cc/"

    repository.mark_blog_result(
        blog_id=first["seed_blog_id"],
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=0,
    )

    third = repository.create_ingestion_request(
        homepage_url="http://www.langhai.cc/",
        email="owner@example.com",
    )

    assert third["request_id"] is None
    assert third["status"] == "DEDUPED_EXISTING"
    assert len(repository.list_blogs()) == 1


def test_repository_run_blog_dedup_scan_deletes_duplicate_edges_and_labels_and_records_items(
    tmp_path: Path,
) -> None:
    """Full-library dedup scan should keep one survivor and delete duplicate-owned edges and labels."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    canonical_id, inserted = repository.upsert_blog(
        url="https://langhai.cc/",
        normalized_url="https://langhai.cc/",
        domain="langhai.cc",
    )
    assert inserted is True
    external_id, inserted = repository.upsert_blog(
        url="https://friend.example/",
        normalized_url="https://friend.example/",
        domain="friend.example",
    )
    assert inserted is True

    with session_scope(repository.session_factory) as session:
        duplicate = BlogModel(
            url="http://blog.langhai.cc/index.html",
            normalized_url="http://blog.langhai.cc/index.html",
            identity_key="",
            identity_reason_codes="[]",
            identity_ruleset_version="",
            domain="blog.langhai.cc",
            email=None,
            title="Duplicate Langhai",
            icon_url=None,
            status_code=200,
            crawl_status=CrawlStatus.FINISHED,
            friend_links_count=1,
            created_at=repository_module.now_utc(),
            updated_at=repository_module.now_utc(),
        )
        session.add(duplicate)
        session.flush()
        duplicate_id = int(duplicate.id)
        tag = BlogLabelTagModel(
            name="blog",
            slug="blog",
            created_at=repository_module.now_utc(),
            updated_at=repository_module.now_utc(),
        )
        session.add(tag)
        session.flush()
        session.add(
            BlogLabelAssignmentModel(
                blog_id=duplicate_id,
                tag_id=int(tag.id),
                labeled_at=repository_module.now_utc(),
                created_at=repository_module.now_utc(),
                updated_at=repository_module.now_utc(),
            )
        )
        session.add(
            EdgeModel(
                from_blog_id=external_id,
                to_blog_id=duplicate_id,
                link_url_raw="http://blog.langhai.cc/index.html",
                link_text="duplicate",
                discovered_at=repository_module.now_utc(),
            )
        )

    repository.add_edge(
        from_blog_id=external_id,
        to_blog_id=canonical_id,
        link_url_raw="https://langhai.cc/",
        link_text="canonical",
    )
    repository.add_edge(
        from_blog_id=external_id,
        to_blog_id=duplicate_id,
        link_url_raw="http://blog.langhai.cc/index.html",
        link_text="duplicate",
    )
    queued = repository.create_ingestion_request(
        homepage_url="http://www.langhai.cc/",
        email="owner@example.com",
    )

    summary = repository.run_blog_dedup_scan(crawler_was_running=True)
    items = repository.list_blog_dedup_scan_run_items(summary["id"])
    blogs = repository.list_blogs()
    edges = repository.list_edges()
    labeling = repository.list_blog_labeling_candidates()

    assert summary["status"] == "SUCCEEDED"
    assert summary["crawler_was_running"] is True
    assert summary["removed_count"] == 1
    assert len(items) == 1
    assert items[0]["survivor_identity_key"] == "site:langhai.cc/"
    assert items[0]["survivor_selection_basis"].startswith("normalized_url_length=")
    assert sum(1 for blog in blogs if blog["identity_key"] == "site:langhai.cc/") == 1
    assert edges == [
        {
            "id": edges[0]["id"],
            "from_blog_id": external_id,
            "to_blog_id": canonical_id,
            "link_url_raw": "https://langhai.cc/",
            "link_text": "canonical",
            "discovered_at": edges[0]["discovered_at"],
        }
    ]
    assert [row["id"] for row in labeling["items"]] == [canonical_id]
    assert labeling["items"][0]["labels"] == []
    request = repository.get_ingestion_request(
        request_id=queued["request_id"],
        request_token=queued["request_token"],
    )
    assert request is not None
    assert request["identity_key"] == "site:langhai.cc/"


def test_repository_dedup_scan_prefers_shortest_normalized_url_as_survivor(tmp_path: Path) -> None:
    """Within one identity group, the shortest normalized_url should survive."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    shortest_id, inserted = repository.upsert_blog(
        url="https://langhai.cc/",
        normalized_url="https://langhai.cc/",
        domain="langhai.cc",
    )
    assert inserted is True

    with session_scope(repository.session_factory) as session:
        duplicate = BlogModel(
            url="http://blog.langhai.cc/index.html",
            normalized_url="http://blog.langhai.cc/index.html",
            identity_key="",
            identity_reason_codes="[]",
            identity_ruleset_version="",
            domain="blog.langhai.cc",
            email=None,
            title=None,
            icon_url=None,
            status_code=None,
            crawl_status=CrawlStatus.FINISHED,
            friend_links_count=0,
            created_at=repository_module.now_utc(),
            updated_at=repository_module.now_utc(),
        )
        session.add(duplicate)
        session.flush()
        duplicate_id = int(duplicate.id)

    summary = repository.run_blog_dedup_scan(crawler_was_running=False)
    blogs = repository.list_blogs()
    items = repository.list_blog_dedup_scan_run_items(summary["id"])

    assert summary["removed_count"] == 1
    assert [blog["id"] for blog in blogs if blog["identity_key"] == "site:langhai.cc/"] == [shortest_id]
    assert items[0]["removed_blog_id"] == duplicate_id
    assert "normalized_url=https://langhai.cc/" in items[0]["survivor_selection_basis"]


def test_repository_upsert_blog_collapses_tenant_like_subdomains_to_root_url(tmp_path: Path) -> None:
    """Tenant-like homepage subdomains should persist as one canonical root blog URL."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")

    first_id, first_inserted = repository.upsert_blog(
        url="https://zhuruilei.66law.cn/",
        normalized_url="https://zhuruilei.66law.cn/",
        domain="zhuruilei.66law.cn",
    )
    second_id, second_inserted = repository.upsert_blog(
        url="https://lichenlvs.66law.cn/",
        normalized_url="https://lichenlvs.66law.cn/",
        domain="lichenlvs.66law.cn",
    )

    assert first_inserted is True
    assert second_inserted is False
    assert second_id == first_id

    blog = repository.get_blog(first_id)
    assert blog is not None
    assert blog["url"] == "https://66law.cn/"
    assert blog["normalized_url"] == "https://66law.cn/"
    assert blog["domain"] == "66law.cn"
    assert blog["identity_key"] == "site:66law.cn/"
    assert "tenant_subdomain_collapsed" in blog["identity_reason_codes"]


def test_repository_ingestion_request_reuses_tenant_like_root_identity(tmp_path: Path) -> None:
    """Tenant-like subdomains should share one queued seed blog/request identity."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")

    first = repository.create_ingestion_request(
        homepage_url="https://zhuruilei.66law.cn/",
        email="first@example.com",
    )
    second = repository.create_ingestion_request(
        homepage_url="https://lichenlvs.66law.cn/",
        email="second@example.com",
    )

    assert first["status"] == "QUEUED"
    assert second["status"] == "QUEUED"
    assert second["request_id"] == first["request_id"]
    assert second["seed_blog_id"] == first["seed_blog_id"]
    assert second["identity_key"] == "site:66law.cn/"

    blog = repository.get_blog(int(first["seed_blog_id"]))
    assert blog is not None
    assert blog["url"] == "https://66law.cn/"
    assert blog["normalized_url"] == "https://66law.cn/"
    assert blog["domain"] == "66law.cn"


def test_repository_reused_tenant_like_ingestion_request_is_canonicalized_to_root_url(tmp_path: Path) -> None:
    """Reused active requests should rewrite legacy tenant normalized_url to the registrable root URL."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")

    with session_scope(repository.session_factory) as session:
        seed = BlogModel(
            url="https://66law.cn/",
            normalized_url="https://66law.cn/",
            identity_key="site:66law.cn/",
            identity_reason_codes='["scheme_ignored"]',
            identity_ruleset_version=repository_module.IDENTITY_RULESET_VERSION,
            domain="66law.cn",
            email=None,
            title=None,
            icon_url=None,
            status_code=None,
            crawl_status=CrawlStatus.WAITING,
            friend_links_count=0,
            created_at=repository_module.now_utc(),
            updated_at=repository_module.now_utc(),
        )
        session.add(seed)
        session.flush()
        request = IngestionRequestModel(
            requested_url="https://zhuruilei.66law.cn/",
            normalized_url="https://zhuruilei.66law.cn/",
            identity_key="site:66law.cn/",
            identity_reason_codes='["scheme_ignored"]',
            identity_ruleset_version=repository_module.IDENTITY_RULESET_VERSION,
            requester_email="existing@example.com",
            status="QUEUED",
            priority=100,
            seed_blog_id=int(seed.id),
            matched_blog_id=None,
            request_token="legacy-token",
            expires_at=None,
            error_message=None,
            created_at=repository_module.now_utc(),
            updated_at=repository_module.now_utc(),
        )
        session.add(request)
        session.flush()
        request_id = int(request.id)

    reused = repository.create_ingestion_request(
        homepage_url="https://lichenlvs.66law.cn/",
        email="next@example.com",
    )

    assert reused["request_id"] == request_id
    assert reused["normalized_url"] == "https://66law.cn/"
    assert reused["identity_key"] == "site:66law.cn/"


def test_repository_dedup_scan_canonicalizes_tenant_like_survivor_to_root_url(tmp_path: Path) -> None:
    """Historical tenant-like subdomains should merge into one root survivor after dedup scan."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")

    with session_scope(repository.session_factory) as session:
        first = BlogModel(
            url="https://zhuruilei.66law.cn/",
            normalized_url="https://zhuruilei.66law.cn/",
            identity_key="",
            identity_reason_codes="[]",
            identity_ruleset_version="",
            domain="zhuruilei.66law.cn",
            email=None,
            title=None,
            icon_url=None,
            status_code=None,
            crawl_status=CrawlStatus.WAITING,
            friend_links_count=0,
            created_at=repository_module.now_utc(),
            updated_at=repository_module.now_utc(),
        )
        second = BlogModel(
            url="https://lichenlvs.66law.cn/",
            normalized_url="https://lichenlvs.66law.cn/",
            identity_key="",
            identity_reason_codes="[]",
            identity_ruleset_version="",
            domain="lichenlvs.66law.cn",
            email=None,
            title=None,
            icon_url=None,
            status_code=None,
            crawl_status=CrawlStatus.WAITING,
            friend_links_count=0,
            created_at=repository_module.now_utc(),
            updated_at=repository_module.now_utc(),
        )
        session.add(first)
        session.add(second)
        session.flush()
        first_id = int(first.id)

    summary = repository.run_blog_dedup_scan(crawler_was_running=False)
    assert summary["removed_count"] == 1

    blogs = repository.list_blogs()
    assert [blog["id"] for blog in blogs] == [first_id]
    assert blogs[0]["url"] == "https://66law.cn/"
    assert blogs[0]["normalized_url"] == "https://66law.cn/"
    assert blogs[0]["domain"] == "66law.cn"
    assert blogs[0]["identity_key"] == "site:66law.cn/"


def test_repository_startup_migrates_legacy_tenant_like_rows_and_merges_to_root_url(tmp_path: Path) -> None:
    """Repository startup should refresh stale ruleset rows without auto-running admin dedup."""
    db_path = tmp_path / "db.sqlite"
    repository = repository_module.build_repository(db_path=db_path)

    with session_scope(repository.session_factory) as session:
        first = BlogModel(
            url="https://zhuruilei.66law.cn/",
            normalized_url="https://zhuruilei.66law.cn/",
            identity_key="site:zhuruilei.66law.cn/",
            identity_reason_codes='["scheme_ignored"]',
            identity_ruleset_version="2026-04-05-v1",
            domain="zhuruilei.66law.cn",
            email=None,
            title=None,
            icon_url=None,
            status_code=None,
            crawl_status=CrawlStatus.WAITING,
            friend_links_count=0,
            created_at=repository_module.now_utc(),
            updated_at=repository_module.now_utc(),
        )
        second = BlogModel(
            url="https://lichenlvs.66law.cn/",
            normalized_url="https://lichenlvs.66law.cn/",
            identity_key="site:lichenlvs.66law.cn/",
            identity_reason_codes='["scheme_ignored"]',
            identity_ruleset_version="2026-04-05-v1",
            domain="lichenlvs.66law.cn",
            email=None,
            title=None,
            icon_url=None,
            status_code=None,
            crawl_status=CrawlStatus.WAITING,
            friend_links_count=0,
            created_at=repository_module.now_utc(),
            updated_at=repository_module.now_utc(),
        )
        session.add(first)
        session.add(second)

    migrated = repository_module.build_repository(db_path=db_path)
    blogs = migrated.list_blogs()
    latest_run = migrated.get_latest_blog_dedup_scan_run()

    assert len(blogs) == 2
    assert {blog["identity_key"] for blog in blogs} == {"site:66law.cn/"}
    assert all(blog["identity_ruleset_version"] == repository_module.IDENTITY_RULESET_VERSION for blog in blogs)
    assert latest_run is None


def test_repository_startup_marks_orphaned_dedup_scan_run_failed(tmp_path: Path) -> None:
    """Startup should not leave stale RUNNING dedup scan summaries hanging forever."""
    db_path = tmp_path / "db.sqlite"
    repository = repository_module.build_repository(db_path=db_path)
    run = repository.create_blog_dedup_scan_run(crawler_was_running=False)

    restarted = repository_module.build_repository(db_path=db_path)
    latest_run = restarted.get_latest_blog_dedup_scan_run()

    assert latest_run is not None
    assert latest_run["id"] == run["id"]
    assert latest_run["status"] == "FAILED"
    assert latest_run["error_message"] == "orphaned_dedup_scan_run_cleaned_on_startup"


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


def test_repository_blog_labeling_candidates_only_return_finished_blogs_with_joined_label_state(
    tmp_path: Path,
) -> None:
    """Labeling candidates should only expose finished blogs and merge multiple labels."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    finished_blog_id, inserted = repository.upsert_blog(
        url="https://alpha.example/",
        normalized_url="https://alpha.example/",
        domain="alpha.example",
    )
    assert inserted is True
    waiting_blog_id, inserted = repository.upsert_blog(
        url="https://beta.example/",
        normalized_url="https://beta.example/",
        domain="beta.example",
    )
    assert inserted is True
    repository.mark_blog_result(
        blog_id=finished_blog_id,
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=2,
        metadata_captured=True,
        title="Alpha",
        icon_url="https://alpha.example/favicon.ico",
    )
    repository.mark_blog_result(
        blog_id=waiting_blog_id,
        crawl_status="WAITING",
        status_code=200,
        friend_links_count=0,
    )

    first_page = repository.list_blog_labeling_candidates(page=1, page_size=20, labeled=False)
    assert [row["id"] for row in first_page["items"]] == [finished_blog_id]
    assert first_page["items"][0]["labels"] == []
    assert first_page["items"][0]["is_labeled"] is False

    blog_tag = repository.create_blog_label_tag(name="blog")
    official_tag = repository.create_blog_label_tag(name="official")
    created = repository.replace_blog_link_labels(
        blog_id=finished_blog_id,
        tag_ids=[official_tag["id"], blog_tag["id"]],
    )
    assert created["blog_id"] == finished_blog_id
    assert created["label_slugs"] == ["blog", "official"]

    second_page = repository.list_blog_labeling_candidates(label="official", labeled=True, sort="recently_labeled")
    assert [row["id"] for row in second_page["items"]] == [finished_blog_id]
    assert [label["slug"] for label in second_page["items"][0]["labels"]] == ["blog", "official"]
    assert second_page["items"][0]["is_labeled"] is True
    assert second_page["items"][0]["last_labeled_at"] is not None
    assert [tag["slug"] for tag in second_page["available_tags"]] == ["blog", "official"]


def test_repository_blog_labeling_upsert_rejects_invalid_targets_and_reset_clears_labels(
    tmp_path: Path,
) -> None:
    """Only finished blogs should be labelable, and reset should clear label/tag rows."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    finished_blog_id, inserted = repository.upsert_blog(
        url="https://finished.example/",
        normalized_url="https://finished.example/",
        domain="finished.example",
    )
    assert inserted is True
    queued_blog_id, inserted = repository.upsert_blog(
        url="https://queued.example/",
        normalized_url="https://queued.example/",
        domain="queued.example",
    )
    assert inserted is True
    repository.mark_blog_result(
        blog_id=finished_blog_id,
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=1,
    )

    with pytest.raises(repository_module.BlogLabelingConflictError, match="requires_finished"):
        repository.replace_blog_link_labels(blog_id=queued_blog_id, tag_ids=[1])

    with pytest.raises(repository_module.BlogLabelingNotFoundError, match="blog_not_found"):
        repository.replace_blog_link_labels(blog_id=999, tag_ids=[1])

    with pytest.raises(ValueError, match="Unsupported blog label name"):
        repository.create_blog_label_tag(name="   ")

    blog_tag = repository.create_blog_label_tag(name="blog")
    unknown_tag = repository.create_blog_label_tag(name="unknown")
    with pytest.raises(ValueError, match="blog_label_tag_not_found"):
        repository.replace_blog_link_labels(blog_id=finished_blog_id, tag_ids=[blog_tag["id"], 999])

    first = repository.replace_blog_link_labels(blog_id=finished_blog_id, tag_ids=[blog_tag["id"]])
    second = repository.replace_blog_link_labels(
        blog_id=finished_blog_id,
        tag_ids=[blog_tag["id"], unknown_tag["id"]],
    )
    assert first["blog_id"] == second["blog_id"] == finished_blog_id

    labeled = repository.list_blog_labeling_candidates(label="unknown", labeled=True)
    assert [row["id"] for row in labeled["items"]] == [finished_blog_id]
    assert [label["slug"] for label in labeled["items"][0]["labels"]] == ["blog", "unknown"]

    reset = repository.reset()
    assert reset["blog_link_labels_deleted"] == 2
    assert reset["blog_label_tags_deleted"] == 2
    assert repository.list_blog_labeling_candidates()["items"] == []


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
    assert detail["recommended_blogs"][0]["blog"] == {
        "id": delta_id,
        "url": "https://delta.example/",
        "normalized_url": "https://delta.example/",
        "identity_key": "site:delta.example/",
        "identity_reason_codes": ["scheme_ignored"],
        "identity_ruleset_version": "2026-04-07-v5",
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
    }
    assert detail["recommended_blogs"][0]["reason"] == "mutual_connection"
    assert detail["recommended_blogs"][0]["mutual_connection_count"] == 1
    assert detail["recommended_blogs"][0]["via_blogs"] == [
        {
            "id": beta_id,
            "domain": "beta.example",
            "title": "beta.example title",
            "icon_url": "https://beta.example/favicon.ico",
        }
    ]
