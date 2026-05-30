"""Regression tests for the SQLAlchemy-backed repository."""

from pathlib import Path
import sys

import pyarrow.parquet as pq
import pytest
from sqlalchemy import event
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import import_legacy_blog_labels
import import_legacy_label_counts
import persistence_api.repository as repository_module
from persistence_api.db import session_scope
from persistence_api.models import BlogLabelModel
from persistence_api.models import BlogLabelTagModel
from persistence_api.models import BlogModel
from persistence_api.models import IngestionRequestModel
from persistence_api.models import RawDiscoveredUrlModel
from shared.contracts.enums import CrawlStatus
from shared.config import Settings


def test_build_repository_roundtrip_works_with_path_backed_repository(tmp_path: Path) -> None:
    """The compatibility wrapper should still support path-backed test repositories."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    blog_id, inserted = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
    )

    assert inserted is True
    fetched = repository.get_blog(blog_id)
    assert fetched is not None
    assert fetched["domain"] == "blog.example.com"
    assert fetched["blog_id"] == blog_id


def test_build_repository_enables_schema_sync_for_dsn(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Postgres-backed repositories must run startup schema sync for compatibility migrations."""
    captured: dict[str, object] = {}

    def fake_repository(
        database_url: str,
        *,
        decision_settings: Settings | None = None,
        startup_schema_sync: bool = True,
    ) -> object:
        captured["database_url"] = database_url
        captured["decision_settings"] = decision_settings
        captured["startup_schema_sync"] = startup_schema_sync
        return object()

    settings = Settings(
        db_path=tmp_path / "db.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
    )
    monkeypatch.setattr(repository_module, "SQLAlchemyRepository", fake_repository)

    repository_module.build_repository(
        db_path=tmp_path / "fallback.sqlite",
        db_dsn="postgresql+psycopg://example",
        settings=settings,
    )

    assert captured == {
        "database_url": "postgresql+psycopg://example",
        "decision_settings": settings,
        "startup_schema_sync": True,
    }


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


def test_repository_register_login_and_session_profile(tmp_path: Path) -> None:
    """Users can register, log in, and resolve their bearer session profile."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")

    created = repository.register_user(email="User@Example.com", password="correct horse")
    assert created["user"]["email"] == "user@example.com"
    assert created["token"]
    resolved_user = repository.get_user_by_session_token(token=created["token"])
    assert resolved_user is not None
    assert resolved_user["id"] == created["user"]["id"]
    assert resolved_user["email"] == created["user"]["email"]

    logged_in = repository.login_user(email="user@example.com", password="correct horse")
    assert logged_in["user"]["id"] == created["user"]["id"]
    assert logged_in["token"] != created["token"]

    assert repository.revoke_user_session(token=created["token"]) is True
    assert repository.get_user_by_session_token(token=created["token"]) is None


def test_repository_rejects_duplicate_user_and_bad_credentials(tmp_path: Path) -> None:
    """Email uniqueness and password validation should produce stable errors."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    repository.register_user(email="dupe@example.com", password="long enough")

    with pytest.raises(repository_module.UserAuthError, match="email_already_registered"):
        repository.register_user(email="DUPE@example.com", password="long enough")
    with pytest.raises(repository_module.UserAuthError, match="invalid_credentials"):
        repository.login_user(email="dupe@example.com", password="wrong password")
    with pytest.raises(ValueError, match="password_too_short"):
        repository.register_user(email="short@example.com", password="short")


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
    assert fetched["seed_blog"]["blog_id"] == created["seed_blog_id"]


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


def test_repository_filter_stats_follow_configured_chain_order(tmp_path: Path) -> None:
    """Filter stats should report remaining counts in configured filter order."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    source_id, _ = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
    )

    repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://friend-a.example/",
        status="success",
    )
    repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://blog.example.com/",
        status="rule:same_domain",
    )
    repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://github.com/example",
        status="rule:platform_blocked",
    )

    stats = repository.get_filter_stats_by_chain_order()

    assert stats["by_filter_reason"]["raw"] == 3
    # ``rule:duplicate_url`` now leads the chain ordering; no duplicates here so
    # the remaining count is unchanged after that step.
    assert stats["by_filter_reason"]["rule:duplicate_url"] == 3
    assert stats["by_filter_reason"]["rule:same_domain"] == 2
    assert stats["by_filter_reason"]["rule:platform_blocked"] == 1
    # Terminal nodes close the funnel on the real accepted-URL and blog counts.
    assert stats["by_filter_reason"]["success"] == 1
    assert stats["by_filter_reason"]["blogs"] == repository.stats()["total_blogs"]
    assert "other" not in stats["by_filter_reason"]


def test_repository_filter_stats_account_for_duplicate_and_terminal_nodes(tmp_path: Path) -> None:
    """Filter stats should subtract duplicates and end on success/blog counts."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    source_id, _ = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
    )

    # Two records share a normalized URL, so the second is tagged as a duplicate
    # at ingestion time before the configurable rule chain runs.
    repository.create_raw_discovered_url_record(
        source_blog_id=source_id,
        normalized_url="https://friend-a.example/",
        status="success",
    )
    repository.create_raw_discovered_url_record(
        source_blog_id=source_id,
        normalized_url="https://friend-a.example/",
        status="success",
    )

    stats = repository.get_filter_stats_by_chain_order()["by_filter_reason"]

    assert stats["raw"] == 2
    # The duplicate is dropped at the first chain step, leaving one candidate.
    assert stats["rule:duplicate_url"] == 1
    assert stats["success"] == 1
    assert stats["blogs"] == repository.stats()["total_blogs"]
    assert "other" not in stats


def test_repository_stats_include_raw_discovered_url_count(tmp_path: Path) -> None:
    """Repository stats should expose raw URL volume for crawler capacity gating."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    source_id, _ = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://one.example/",
        status="success",
    )
    repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://two.example/",
        status="rule:same_domain",
    )

    assert repository.stats()["raw_discovered_urls"] == 2


def test_repository_marks_duplicate_raw_urls_before_filter_chain(tmp_path: Path) -> None:
    """Raw URL insertion should only check older rows for duplicate URLs."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    source_id, _ = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
    )

    first = repository.create_raw_discovered_url_record(
        source_blog_id=source_id,
        normalized_url="https://friend.example/",
        status="pending",
    )
    duplicate = repository.create_raw_discovered_url_record(
        source_blog_id=source_id,
        normalized_url="https://friend.example/",
        status="pending",
    )

    assert first["status"] == "pending"
    assert duplicate["status"] == "rule:duplicate_url"
    assert first["id"] < duplicate["id"]


def test_retired_label_assignment_migration_reports_single_table_rows(tmp_path: Path) -> None:
    """Retired label-assignment migration should leave the single label table intact."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    source_id, _ = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    raw_id = repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://target.example/",
        status="success",
    )
    repository.replace_blog_link_labels(blog_id=raw_id, tag_ids=[1, 2])

    from scripts.migrate_blog_label_assignment_ids import migrate_blog_label_assignment_ids

    summary = migrate_blog_label_assignment_ids(repository=repository, apply=True)

    assert summary.blog_labels_rows == 1
    labeled = repository.list_blog_labeling_candidates(label="1", labeled=True)
    assert [row["id"] for row in labeled["items"]] == [raw_id]



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


def test_repository_run_blog_dedup_scan_removes_rejected_links_and_orphaned_targets(
    tmp_path: Path,
) -> None:
    """Admin rescan should drop persisted blog URLs rejected by the current decision chain."""
    settings = Settings(
        db_path=tmp_path / "db.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        friend_link_exact_url_blocklist=("https://rejected.example/",),
        decision_model_consensus_enabled=False,
    )
    repository = repository_module.build_repository(db_path=settings.db_path, settings=settings)
    source_id, inserted = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    assert inserted is True
    target_id, inserted = repository.upsert_blog(
        url="https://rejected.example/",
        normalized_url="https://rejected.example/",
        domain="rejected.example",
    )
    assert inserted is True

    with session_scope(repository.session_factory) as session:
        session.add(
            BlogLabelModel(
                normalized_url="https://rejected.example/",
                label_id={"1": 1},
                created_time=repository_module.now_utc(),
                updated_time=repository_module.now_utc(),
            )
        )

    repository.add_edge(
        from_blog_id=source_id,
        to_blog_id=target_id,
        link_url_raw="https://rejected.example/",
        link_text="Rejected",
    )

    run = repository.create_blog_dedup_scan_run(crawler_was_running=True)
    summary = repository.execute_blog_dedup_scan_run(run_id=int(run["id"]))
    items = repository.list_blog_dedup_scan_run_items(summary["id"])
    blogs = repository.list_blogs()

    assert summary["status"] == "SUCCEEDED"
    assert summary["crawler_was_running"] is True
    assert summary["total_count"] == 2
    assert summary["scanned_count"] == 2
    assert summary["removed_count"] == 1
    assert summary["kept_count"] == 1
    assert repository.list_edges() == []
    assert [blog["id"] for blog in blogs] == [source_id]
    assert len(items) == 1
    assert items[0]["survivor_blog_id"] is None
    assert items[0]["removed_blog_id"] == target_id
    assert items[0]["removed_url"] == "https://rejected.example/"
    assert items[0]["reason_code"] == "exact_url_blocked"


def test_repository_dedup_scan_keeps_valid_blog_urls(tmp_path: Path) -> None:
    """Rescan should preserve persisted blogs whose own URLs still pass the chain."""
    settings = Settings(
        db_path=tmp_path / "db.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        friend_link_exact_url_blocklist=("https://blocked.example/",),
        decision_model_consensus_enabled=False,
    )
    repository = repository_module.build_repository(db_path=settings.db_path, settings=settings)
    first_source_id, inserted = repository.upsert_blog(
        url="https://source-a.example/",
        normalized_url="https://source-a.example/",
        domain="source-a.example",
    )
    assert inserted is True
    second_source_id, inserted = repository.upsert_blog(
        url="https://source-b.example/",
        normalized_url="https://source-b.example/",
        domain="source-b.example",
    )
    assert inserted is True
    target_id, inserted = repository.upsert_blog(
        url="https://blocked.example/",
        normalized_url="https://blocked.example/",
        domain="blocked.example",
    )
    assert inserted is True
    survivor_id, inserted = repository.upsert_blog(
        url="https://friend.example/",
        normalized_url="https://friend.example/",
        domain="friend.example",
    )
    assert inserted is True

    repository.add_edge(
        from_blog_id=first_source_id,
        to_blog_id=survivor_id,
        link_url_raw="https://friend.example/",
        link_text="Canonical",
    )
    repository.add_edge(
        from_blog_id=second_source_id,
        to_blog_id=target_id,
        link_url_raw="https://blocked.example/",
        link_text="Blocked",
    )

    run = repository.create_blog_dedup_scan_run(crawler_was_running=False)
    summary = repository.execute_blog_dedup_scan_run(run_id=int(run["id"]))
    items = repository.list_blog_dedup_scan_run_items(summary["id"])
    blogs = repository.list_blogs()
    edges = repository.list_edges()

    assert summary["total_count"] == 4
    assert summary["scanned_count"] == 4
    assert summary["removed_count"] == 1
    assert summary["kept_count"] == 3
    assert len(items) == 1
    assert items[0]["removed_url"] == "https://blocked.example/"
    assert [edge["link_url_raw"] for edge in edges] == ["https://friend.example/"]
    assert {blog["id"] for blog in blogs} == {first_source_id, second_source_id, survivor_id}


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
    assert blog["blog_id"] == first["seed_blog_id"]
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


def test_repository_dedup_scan_uses_model_consensus_when_enabled(tmp_path: Path, monkeypatch) -> None:
    """Rescan should share the same model-consensus decision layer as live crawler filtering."""
    settings = Settings(
        db_path=tmp_path / "db.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        decision_model_root=tmp_path / "models",
        decision_model_consensus_enabled=True,
    )
    repository = repository_module.build_repository(db_path=settings.db_path, settings=settings)
    source_id, inserted = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    assert inserted is True
    target_id, inserted = repository.upsert_blog(
        url="https://maybe-blog.example/",
        normalized_url="https://maybe-blog.example/",
        domain="maybe-blog.example",
    )
    assert inserted is True

    run_dir = settings.decision_model_root / "structured" / "2604120847"
    run_dir.mkdir(parents=True)
    (run_dir / "model.joblib").write_bytes(b"stub")
    (run_dir / "config.json").write_text('{"model_config":{"threshold":0.5}}', encoding="utf-8")

    class StubPredictor:
        threshold = 0.5

        def predict_proba(self, samples: list[object]) -> list[float]:
            probabilities: list[float] = []
            for sample in samples:
                url = str(getattr(sample, "url", ""))
                probabilities.append(0.9 if "source.example" in url else 0.1)
            return probabilities

    monkeypatch.setattr("crawler.crawling.decisions.consensus.load_model", lambda path: StubPredictor())

    repository.add_edge(
        from_blog_id=source_id,
        to_blog_id=target_id,
        link_url_raw="https://maybe-blog.example/",
        link_text="Maybe Blog",
    )

    run = repository.create_blog_dedup_scan_run(crawler_was_running=False)
    summary = repository.execute_blog_dedup_scan_run(run_id=int(run["id"]))
    items = repository.list_blog_dedup_scan_run_items(summary["id"])

    assert summary["removed_count"] == 1
    assert summary["kept_count"] == 1
    assert repository.list_edges() == []
    assert [blog["id"] for blog in repository.list_blogs()] == [source_id]
    assert items[0]["reason_code"] == "model_consensus_all_non_blog"


def test_repository_url_refilter_run_reapplies_chain_and_updates_rows(tmp_path: Path) -> None:
    """URL refilter should backup the database, rewrite statuses, and sync blog/edge rows."""
    config_path = tmp_path / "filter_chain.toml"
    config_path.write_text(
        """
[[filters]]
kind = "same_domain"
enabled = true
""".strip(),
        encoding="utf-8",
    )
    settings = Settings(
        db_path=tmp_path / "db.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        filter_chain_config_path=config_path,
        friend_link_exact_url_blocklist=("https://blocked.example/",),
    )
    repository = repository_module.build_repository(db_path=settings.db_path, settings=settings)
    source_id, _ = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    blocked_id, _ = repository.upsert_blog(
        url="https://blocked.example/",
        normalized_url="https://blocked.example/",
        domain="blocked.example",
    )
    repository.add_edge(
        from_blog_id=source_id,
        to_blog_id=blocked_id,
        link_url_raw="https://blocked.example/",
        link_text=None,
    )
    repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://blocked.example/",
        status="success",
    )
    repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://agency.gov/",
        status="rule:platform_blocked",
    )
    activated_raw_id = repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://friend.example/",
        status="rule:domain_blocked",
    )

    config_path.write_text(
        """
[[filters]]
kind = "same_domain"
enabled = true

[[filters]]
kind = "exact_url_blocklist"
enabled = true

[[filters]]
kind = "blocked_tld"
enabled = true
""".strip(),
        encoding="utf-8",
    )

    run = repository.create_url_refilter_run(crawler_was_running=False)
    summary = repository.execute_url_refilter_run(run_id=run["id"])
    events = repository.list_url_refilter_run_events(run["id"])

    assert summary["status"] == "SUCCEEDED"
    assert summary["total_count"] == 3
    assert summary["scanned_count"] == 3
    assert summary["unchanged_count"] == 0
    assert summary["activated_count"] == 1
    assert summary["deactivated_count"] == 1
    assert summary["retagged_count"] == 1
    assert summary["backup_path"] is not None
    assert Path(summary["backup_path"]).exists()
    assert [event["message"] for event in events[:3]] == [
        "备份中",
        f"备份完成，文件保存在 {summary['backup_path']}",
        "开始按过滤链重新扫描原始URL表",
    ]

    with session_scope(repository.session_factory) as session:
        raw_rows = session.query(RawDiscoveredUrlModel).order_by(RawDiscoveredUrlModel.id.asc()).all()
        assert [row.status for row in raw_rows] == [
            "rule:exact_url_blocked",
            "rule:blocked_tld",
            "success",
        ]

    blogs = repository.list_blogs()
    assert {row["normalized_url"] for row in blogs} == {
        "https://source.example/",
        "https://friend.example/",
    }
    assert next(row["id"] for row in blogs if row["normalized_url"] == "https://friend.example/") == activated_raw_id
    edges = repository.list_edges()
    assert edges == [
        {
            "id": edges[0]["id"],
            "from_blog_id": source_id,
            "to_blog_id": next(row["id"] for row in blogs if row["normalized_url"] == "https://friend.example/"),
            "link_url_raw": "https://friend.example/",
            "link_text": None,
            "discovered_at": edges[0]["discovered_at"],
        }
    ]


def test_repository_url_refilter_deactivation_deletes_blog_graph_idempotently(tmp_path: Path) -> None:
    """Deactivated URLs should remove their target blog graph and tolerate missing rows."""
    config_path = tmp_path / "filter_chain.toml"
    config_path.write_text(
        """
[[filters]]
kind = "same_domain"
enabled = true
""".strip(),
        encoding="utf-8",
    )
    settings = Settings(
        db_path=tmp_path / "db.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        filter_chain_config_path=config_path,
        friend_link_exact_url_blocklist=("https://target.example/",),
    )
    repository = repository_module.build_repository(db_path=settings.db_path, settings=settings)
    source_id, _ = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    target_id, _ = repository.upsert_blog(
        url="https://target.example/",
        normalized_url="https://target.example/",
        domain="target.example",
    )
    other_id, _ = repository.upsert_blog(
        url="https://other.example/",
        normalized_url="https://other.example/",
        domain="other.example",
    )
    repository.add_edge(
        from_blog_id=source_id,
        to_blog_id=target_id,
        link_url_raw="https://target.example/",
        link_text=None,
    )
    repository.add_edge(
        from_blog_id=target_id,
        to_blog_id=other_id,
        link_url_raw="https://other.example/",
        link_text=None,
    )
    raw_id = repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://target.example/",
        status="success",
    )

    config_path.write_text(
        """
[[filters]]
kind = "same_domain"
enabled = true

[[filters]]
kind = "exact_url_blocklist"
enabled = true
""".strip(),
        encoding="utf-8",
    )

    run = repository.create_url_refilter_run(crawler_was_running=False)
    summary = repository.execute_url_refilter_run(run_id=run["id"])

    assert summary["status"] == "SUCCEEDED"
    assert summary["deactivated_count"] == 1
    assert repository.get_blog(target_id) is None
    assert repository.list_edges() == []

    with session_scope(repository.session_factory) as session:
        raw = session.scalar(select(RawDiscoveredUrlModel).where(RawDiscoveredUrlModel.id == raw_id))
        assert raw is not None
        repository._handle_refilter_deactivated_success(session, raw=raw)  # type: ignore[attr-defined]

    assert repository.get_blog(target_id) is None
    assert repository.list_edges() == []


def test_repository_url_refilter_activation_skips_edge_when_source_blog_is_missing(tmp_path: Path) -> None:
    """Activated raw URLs should still create targets but not orphaned source edges."""
    config_path = tmp_path / "filter_chain.toml"
    config_path.write_text("", encoding="utf-8")
    settings = Settings(
        db_path=tmp_path / "db.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        filter_chain_config_path=config_path,
    )
    repository = repository_module.build_repository(db_path=settings.db_path, settings=settings)
    source_id, _ = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    raw_id = repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://target.example/",
        status="rule:domain_blocked",
    )
    with session_scope(repository.session_factory) as session:
        source = session.scalar(select(BlogModel).where(BlogModel.blog_id == source_id))
        assert source is not None
        session.delete(source)

    run = repository.create_url_refilter_run(crawler_was_running=False)
    summary = repository.execute_url_refilter_run(run_id=run["id"])

    assert summary["status"] == "SUCCEEDED"
    assert summary["activated_count"] == 1
    assert repository.get_blog(raw_id) is not None
    assert repository.list_edges() == []


def test_repository_url_refilter_run_marks_old_duplicate_raw_urls(tmp_path: Path) -> None:
    """URL refilter should apply duplicate URL filtering before other filters."""
    config_path = tmp_path / "filter_chain.toml"
    config_path.write_text(
        """
[[filters]]
kind = "same_domain"
enabled = true
""".strip(),
        encoding="utf-8",
    )
    settings = Settings(
        db_path=tmp_path / "db.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        filter_chain_config_path=config_path,
    )
    repository = repository_module.build_repository(db_path=settings.db_path, settings=settings)
    source_id, _ = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    first_raw_id = repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://friend.example/",
        status="success",
    )
    duplicate_raw_id = repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://friend.example/",
        status="success",
    )
    assert duplicate_raw_id != first_raw_id
    repository.update_raw_discovered_url_status(record_id=duplicate_raw_id, status="success")

    run = repository.create_url_refilter_run(crawler_was_running=False)
    summary = repository.execute_url_refilter_run(run_id=run["id"])

    assert summary["status"] == "SUCCEEDED"
    assert summary["unchanged_count"] == 1
    assert summary["deactivated_count"] == 1
    with session_scope(repository.session_factory) as session:
        raw_rows = session.query(RawDiscoveredUrlModel).order_by(RawDiscoveredUrlModel.id.asc()).all()
        assert [row.status for row in raw_rows] == ["success", "rule:duplicate_url"]


def test_repository_url_refilter_logs_lifecycle_without_small_final_progress(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Small refilter runs should log start and finish, while progress waits for each 10k batch."""
    config_path = tmp_path / "filter_chain.toml"
    config_path.write_text(
        """
[[filters]]
kind = "same_domain"
enabled = true
""".strip(),
        encoding="utf-8",
    )
    settings = Settings(
        db_path=tmp_path / "db.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        filter_chain_config_path=config_path,
    )
    repository = repository_module.build_repository(db_path=settings.db_path, settings=settings)
    source_id, _ = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://friend.example/",
        status="success",
    )

    logger = repository_module.logging.getLogger(repository_module.URL_REFILTER_LOGGER_NAME)
    monkeypatch.setattr(logger, "propagate", True)
    caplog.set_level(0, logger=repository_module.URL_REFILTER_LOGGER_NAME)
    run = repository.create_url_refilter_run(crawler_was_running=False)
    repository.execute_url_refilter_run(run_id=run["id"])

    refilter_records = [
        record for record in caplog.records if record.name == repository_module.URL_REFILTER_LOGGER_NAME
    ]
    assert [getattr(record, "event", None) for record in refilter_records] == [
        "maintenance.url_refilter.execute.started",
        "maintenance.url_refilter.execute.finished",
    ]
    assert getattr(refilter_records[-1], "reason") == "all_raw_urls_scanned"
    assert getattr(refilter_records[-1], "message") == (
        "url refilter execution finished: all raw URLs scanned successfully"
    )
    assert getattr(refilter_records[-1], "total_count") == 1


def test_repository_ensure_edge_in_session_dedupes_pending_edges(tmp_path: Path) -> None:
    """Refilter edge creation should ignore already-pending same-direction edges."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    source_id, _ = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    target_id, _ = repository.upsert_blog(
        url="https://target.example/",
        normalized_url="https://target.example/",
        domain="target.example",
    )

    with session_scope(repository.session_factory) as session:
        repository._ensure_edge_in_session(  # type: ignore[attr-defined]
            session,
            from_blog_id=source_id,
            to_blog_id=target_id,
            link_url_raw="https://target.example/",
            link_text=None,
        )
        repository._ensure_edge_in_session(  # type: ignore[attr-defined]
            session,
            from_blog_id=source_id,
            to_blog_id=target_id,
            link_url_raw="https://target.example/",
            link_text=None,
        )

    assert len(repository.list_edges()) == 1


def test_raw_discovered_urls_survive_source_blog_deletion(tmp_path: Path) -> None:
    """Raw discovered URLs are root discovery facts and must not cascade with blogs."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    source_id, _ = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    raw_id = repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://friend.example/",
        status="success",
    )

    with session_scope(repository.session_factory) as session:
        source = session.scalar(select(BlogModel).where(BlogModel.blog_id == source_id))
        assert source is not None
        session.delete(source)

    with session_scope(repository.session_factory) as session:
        raw = session.scalar(select(RawDiscoveredUrlModel).where(RawDiscoveredUrlModel.id == raw_id))
        assert raw is not None
        assert raw.source_blog_id == source_id


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
        session.flush()
        first.blog_id = int(first.id)
        second.blog_id = int(second.id)

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


def test_repository_claims_priority_blogs_by_request_priority(tmp_path: Path) -> None:
    """Priority queue claiming should follow ingestion priority before request age."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    first = repository.create_ingestion_request(
        homepage_url="https://first-priority.example/",
        email="owner@example.com",
    )
    second = repository.create_ingestion_request(
        homepage_url="https://second-priority.example/",
        email="owner@example.com",
    )

    with session_scope(repository.session_factory) as session:
        first_request = session.scalar(
            repository_module.select(repository_module.IngestionRequestModel).where(
                repository_module.IngestionRequestModel.id == first["request_id"]
            )
        )
        second_request = session.scalar(
            repository_module.select(repository_module.IngestionRequestModel).where(
                repository_module.IngestionRequestModel.id == second["request_id"]
            )
        )
        assert first_request is not None
        assert second_request is not None
        first_request.priority = 100
        second_request.priority = 200
        first_request.updated_at = repository_module.now_utc()
        second_request.updated_at = repository_module.now_utc()

    claimed = repository.get_next_priority_blog()

    assert claimed is not None
    assert claimed["id"] == second["seed_blog_id"]


def test_repository_waiting_queue_can_exclude_priority_seed_blogs(tmp_path: Path) -> None:
    """Normal queue claiming should skip active ingestion seeds when requested."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    priority_request = repository.create_ingestion_request(
        homepage_url="https://priority-seed.example/",
        email="owner@example.com",
    )
    normal_blog_id, inserted = repository.upsert_blog(
        url="https://normal.example/",
        normalized_url="https://normal.example/",
        domain="normal.example",
    )
    assert inserted is True

    claimed = repository.get_next_waiting_blog(include_priority=False)

    assert claimed is not None
    assert claimed["id"] == normal_blog_id
    assert repository.get_blog(priority_request["seed_blog_id"])["crawl_status"] == "WAITING"


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
    queue = repository.list_blogs_catalog(statuses="waiting, processing", sort="id_asc")
    assert queue["filters"]["statuses"] == ["WAITING", "PROCESSING"]
    assert queue["sort"] == "id_asc"


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
        "statuses": None,
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

    multi_status = repository.list_blogs_catalog(statuses=" waiting , processing ")
    assert multi_status["filters"]["statuses"] == ["WAITING", "PROCESSING"]

    with pytest.raises(ValueError, match="Unsupported crawl status"):
        repository.list_blogs_catalog(status="unknown")

    with pytest.raises(ValueError, match="Unsupported crawl status"):
        repository.list_blogs_catalog(statuses="waiting,bad")

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


def test_repository_blog_catalog_supports_random_sort_for_finished_sampling(tmp_path: Path) -> None:
    """Catalog should allow random ordering so the frontend can sample finished blogs."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    for index in range(3):
        blog_id, inserted = repository.upsert_blog(
            url=f"https://random-{index}.example",
            normalized_url=f"https://random-{index}.example",
            domain=f"random-{index}.example",
        )
        assert inserted is True
        repository.mark_blog_result(
            blog_id=blog_id,
            crawl_status="FINISHED",
            status_code=200,
            friend_links_count=index,
            metadata_captured=True,
            title=f"Random {index}",
            icon_url=f"https://random-{index}.example/favicon.ico",
        )

    random_page = repository.list_blogs_catalog(status="finished", sort="random", page_size=2)
    assert random_page["sort"] == "random"
    assert random_page["filters"]["status"] == "FINISHED"
    assert len(random_page["items"]) == 2


def test_repository_random_catalog_filters_admin_non_blog_and_saves_user_labels(tmp_path: Path) -> None:
    """Random catalog should exclude admin non-blog URLs and store public votes separately."""
    repository = repository_module.build_repository(db_path=tmp_path / "heyblog.sqlite")
    blog_tag = repository.create_blog_label_tag(name="blog")
    company_tag = repository.create_blog_label_tag(name="company")
    other_tag = repository.create_blog_label_tag(name="other")

    kept_id, kept_inserted = repository.upsert_blog(
        url="https://kept.example/",
        normalized_url="https://kept.example/",
        domain="kept.example",
    )
    excluded_id, excluded_inserted = repository.upsert_blog(
        url="https://excluded.example/",
        normalized_url="https://excluded.example/",
        domain="excluded.example",
    )
    assert kept_inserted is True
    assert excluded_inserted is True
    repository.mark_blog_result(
        blog_id=kept_id,
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=1,
        metadata_captured=True,
        title="Kept",
        icon_url=None,
    )
    repository.mark_blog_result(
        blog_id=excluded_id,
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=1,
        metadata_captured=True,
        title="Excluded",
        icon_url=None,
    )
    raw_kept = repository.create_raw_discovered_url(
        source_blog_id=kept_id,
        normalized_url="https://kept.example/",
        status="success",
    )
    raw_excluded = repository.create_raw_discovered_url(
        source_blog_id=excluded_id,
        normalized_url="https://excluded.example/",
        status="success",
    )
    repository.replace_blog_link_labels(
        blog_id=raw_excluded,
        label_id={str(company_tag["id"]): 1},
    )

    user_label = repository.increment_blog_user_label(blog_id=kept_id, label="blog")
    duplicate_blog = repository.increment_blog_user_label(blog_id=kept_id, label="blog", previous_label="blog")
    user_non_blog = repository.increment_blog_user_label(blog_id=kept_id, label="other", previous_label="blog")
    account = repository.register_user(email="labeler@example.com", password="long enough")
    user_id = int(account["user"]["id"])
    account_blog = repository.increment_blog_user_label(blog_id=kept_id, label="blog", user_id=user_id)
    account_other = repository.increment_blog_user_label(blog_id=kept_id, label="other", user_id=user_id)

    random_page = repository.list_blogs_catalog(status="finished", sort="random", page_size=10)
    assert [item["url"] for item in random_page["items"]] == ["https://kept.example/"]
    assert user_label["label_id"] == {str(blog_tag["id"]): 1}
    assert duplicate_blog["label_id"] == {str(blog_tag["id"]): 1}
    assert user_non_blog["label_id"] == {str(other_tag["id"]): 1}
    assert account_blog["label_id"] == {str(other_tag["id"]): 1, str(blog_tag["id"]): 1}
    assert account_other["label_id"] == {str(other_tag["id"]): 2}
    assert repository.list_user_label_selections(user_id=user_id)[0]["label"] == "other"
    assert repository.count_user_label_selections(user_id=user_id) == 1

    admin_labeled = repository.list_blog_labeling_candidates(labeled=True, page_size=10)
    assert [item["id"] for item in admin_labeled["items"]] == [raw_excluded]
    assert raw_kept not in [item["id"] for item in admin_labeled["items"]]


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


def test_repository_blog_catalog_has_title_filters_on_stored_title_only(tmp_path: Path) -> None:
    """Title filtering should keep rows whose rendered display title is non-empty."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    titled_blog_id, inserted = repository.upsert_blog(
        url="https://titled.example/",
        normalized_url="https://titled.example/",
        domain="titled.example",
    )
    assert inserted is True
    untitled_blog_id, inserted = repository.upsert_blog(
        url="https://untitled.example/",
        normalized_url="https://untitled.example/",
        domain="untitled.example",
    )
    assert inserted is True

    repository.mark_blog_result(
        blog_id=titled_blog_id,
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=0,
        metadata_captured=True,
        title="Titled Blog",
        icon_url="https://titled.example/favicon.ico",
    )
    repository.mark_blog_result(
        blog_id=untitled_blog_id,
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=0,
        metadata_captured=True,
        title="",
        icon_url="https://untitled.example/favicon.ico",
    )

    payload = repository.list_blogs_catalog(has_title=True)

    assert [row["id"] for row in payload["items"]] == [untitled_blog_id, titled_blog_id]
    assert payload["items"][0]["title"] == "untitled.example"


def test_repository_priority_ingestion_list_hides_private_fields_and_orders_active_first(tmp_path: Path) -> None:
    """Public priority list should expose queue state without leaking request secrets."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")

    queued = repository.create_ingestion_request(
        homepage_url="https://queued.example/",
        email="owner@example.com",
    )
    processing = repository.create_ingestion_request(
        homepage_url="https://processing.example/",
        email="runner@example.com",
    )
    repository.mark_ingestion_request_crawling(blog_id=processing["seed_blog_id"])
    repository.mark_blog_result(
        blog_id=processing["seed_blog_id"],
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=0,
        metadata_captured=True,
        title="Processing Blog",
        icon_url="https://processing.example/favicon.ico",
    )

    items = repository.list_priority_ingestion_requests()

    assert [item["status"] for item in items] == ["QUEUED", "COMPLETED"]
    assert items[0]["request_id"] == queued["request_id"]
    assert items[0]["requested_url"] == "https://queued.example/"
    assert items[0]["blog"]["crawl_status"] == "WAITING"
    assert "email" not in items[0]
    assert "request_token" not in items[0]
    assert "priority" not in items[0]
    assert "email" not in items[0]["blog"]


def test_repository_blog_lookup_prefers_identity_match_and_returns_reason(tmp_path: Path) -> None:
    """Lookup should follow the frozen identity-first match ladder."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    blog_id, inserted = repository.upsert_blog(
        url="https://langhai.cc/",
        normalized_url="https://langhai.cc/",
        domain="langhai.cc",
    )
    assert inserted is True
    repository.mark_blog_result(
        blog_id=blog_id,
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=0,
    )

    payload = repository.lookup_blog_candidates(url="http://blog.langhai.cc/index.html")

    assert payload["normalized_query_url"] == "https://langhai.cc/"
    assert payload["match_reason"] == "identity_key"
    assert [item["id"] for item in payload["items"]] == [blog_id]


def test_repository_blog_lookup_returns_empty_payload_when_no_match(tmp_path: Path) -> None:
    """Lookup should return a stable empty payload instead of broad fuzzy matches."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")

    payload = repository.lookup_blog_candidates(url="https://missing.example/")

    assert payload["query_url"] == "https://missing.example/"
    assert payload["normalized_query_url"] == "https://missing.example/"
    assert payload["items"] == []
    assert payload["total_matches"] == 0
    assert payload["match_reason"] is None


def test_repository_blog_labeling_candidates_include_success_and_model_filtered_raw_urls(
    tmp_path: Path,
) -> None:
    """Labeling candidates should expose raw success and model-filtered URLs."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    source_blog_id, inserted = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    assert inserted is True
    repository.mark_blog_result(
        blog_id=source_blog_id,
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=3,
        metadata_captured=True,
        title="Source",
        icon_url="https://source.example/favicon.ico",
    )
    accepted_raw_id = repository.create_raw_discovered_url(
        source_blog_id=source_blog_id,
        normalized_url="https://accepted.example/",
        status="success",
    )
    model_raw_id = repository.create_raw_discovered_url(
        source_blog_id=source_blog_id,
        normalized_url="https://model-rejected.example/",
        status="model:model_consensus_all_non_blog",
    )
    repository.create_raw_discovered_url(
        source_blog_id=source_blog_id,
        normalized_url="https://rule-rejected.example/",
        status="rule:blocked_tld",
    )

    first_page = repository.list_blog_labeling_candidates(page=1, page_size=20, labeled=False)
    assert [row["url"] for row in first_page["items"]] == [
        "https://model-rejected.example/",
        "https://accepted.example/",
    ]
    created_ids = {row["url"]: row["id"] for row in first_page["items"]}
    assert created_ids["https://accepted.example/"] == accepted_raw_id
    assert created_ids["https://model-rejected.example/"] == model_raw_id
    assert created_ids["https://accepted.example/"] < created_ids["https://model-rejected.example/"]
    assert all(row["labels"] == [] for row in first_page["items"])

    blog_tag = repository.create_blog_label_tag(name="blog")
    official_tag = repository.create_blog_label_tag(name="official")
    model_blog_id = int(first_page["items"][0]["id"])
    created = repository.replace_blog_link_labels(
        blog_id=model_blog_id,
        tag_ids=[official_tag["id"], blog_tag["id"]],
    )
    assert created["blog_id"] == model_blog_id
    assert created["label_id"] == {"1": 1, "5": 1}
    assert created["label_slugs"] == ["blog", "official"]

    second_page = repository.list_blog_labeling_candidates(label="official", labeled=True, sort="recently_labeled")
    assert [row["id"] for row in second_page["items"]] == [model_blog_id]
    assert [label["slug"] for label in second_page["items"][0]["labels"]] == ["blog", "official"]
    assert second_page["items"][0]["label_id"] == {"1": 1, "5": 1}
    assert second_page["items"][0]["is_labeled"] is True
    assert second_page["items"][0]["last_labeled_at"] is not None
    assert [tag["slug"] for tag in second_page["available_tags"]] == [
        "blog",
        "company",
        "other",
        "unknown",
        "official",
        "government",
    ]


def test_repository_blog_labeling_candidate_query_avoids_raw_url_group_by(
    tmp_path: Path,
) -> None:
    """Candidate listing should avoid the previous full raw URL aggregate shape."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    source_blog_id, inserted = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    assert inserted is True
    first_raw_id = repository.create_raw_discovered_url(
        source_blog_id=source_blog_id,
        normalized_url="https://duplicate.example/",
        status="success",
    )
    repository.create_raw_discovered_url(
        source_blog_id=source_blog_id,
        normalized_url="https://duplicate.example/",
        status="success",
    )

    statements: list[str] = []
    def capture_statement(_connection: object, _cursor: object, statement: str, *_args: object) -> None:
        statements.append(statement)

    event.listen(repository.engine, "before_cursor_execute", capture_statement)
    try:
        page = repository.list_blog_labeling_candidates(page=1, page_size=10, labeled=False)
    finally:
        event.remove(repository.engine, "before_cursor_execute", capture_statement)

    assert [row["id"] for row in page["items"]] == [first_raw_id]
    raw_candidate_sql = [
        statement
        for statement in statements
        if "raw_discovered_urls" in statement and "SELECT" in statement.upper()
    ]
    assert raw_candidate_sql
    assert all("GROUP BY raw_discovered_urls.normalized_url" not in statement for statement in raw_candidate_sql)
    assert any("NOT (EXISTS" in statement.upper() for statement in raw_candidate_sql)


def test_repository_blog_labeling_uses_raw_id_with_existing_blog_display_data(tmp_path: Path) -> None:
    """Labeling should use raw IDs while reusing existing blog display fields."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    source_blog_id, inserted = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    assert inserted is True
    existing_blog_id, inserted = repository.upsert_blog(
        url="https://existing.example/",
        normalized_url="https://existing.example/",
        domain="existing.example",
    )
    assert inserted is True
    raw_id = repository.create_raw_discovered_url(
        source_blog_id=source_blog_id,
        normalized_url="https://existing.example/",
        status="success",
    )

    page = repository.list_blog_labeling_candidates(page=1, page_size=20, labeled=False)

    assert raw_id != existing_blog_id
    assert [row["id"] for row in page["items"]] == [raw_id]
    assert page["items"][0]["domain"] == "existing.example"


def test_repository_blog_labeling_persists_and_backfills_titles(tmp_path: Path) -> None:
    """Labeling should store non-empty titles and backfill old empty label titles."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    source_blog_id, _ = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    titled_blog_id, _ = repository.upsert_blog(
        url="https://titled.example/",
        normalized_url="https://titled.example/",
        domain="titled.example",
    )
    repository.mark_blog_result(
        blog_id=titled_blog_id,
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=1,
        metadata_captured=True,
        title="Persisted Title",
    )
    raw_id = repository.create_raw_discovered_url(
        source_blog_id=source_blog_id,
        normalized_url="https://titled.example/",
        status="success",
    )
    blog_tag = repository.create_blog_label_tag(name="blog")

    repository.replace_blog_link_labels(blog_id=raw_id, tag_ids=[blog_tag["id"]])
    labeled = repository.list_blog_labeling_candidates(labeled=True)

    assert labeled["items"][0]["title"] == "Persisted Title"
    with session_scope(repository.session_factory) as session:
        label = session.get(BlogLabelModel, "https://titled.example/")
        assert label is not None
        assert label.title == "Persisted Title"
        label.title = ""

    relabeled = repository.list_blog_labeling_candidates(labeled=True)

    assert relabeled["items"][0]["title"] == "Persisted Title"
    with session_scope(repository.session_factory) as session:
        label = session.get(BlogLabelModel, "https://titled.example/")
        assert label is not None
        assert label.title == "Persisted Title"


def test_repository_blog_labeling_uses_request_title_for_raw_only_candidate(tmp_path: Path) -> None:
    """Raw-only labeling should persist a temporary title supplied by the UI."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    source_blog_id, _ = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    raw_id = repository.create_raw_discovered_url(
        source_blog_id=source_blog_id,
        normalized_url="https://raw-only.example/",
        status="model:model_consensus_all_non_blog",
    )
    blog_tag = repository.create_blog_label_tag(name="blog")

    repository.replace_blog_link_labels(
        blog_id=raw_id,
        tag_ids=[blog_tag["id"]],
        title="Temporary Raw Title",
    )

    with session_scope(repository.session_factory) as session:
        label = session.get(BlogLabelModel, "https://raw-only.example/")
        assert label is not None
        assert label.title == "Temporary Raw Title"
        assert label.label_id == {str(blog_tag["id"]): 1}


def test_repository_blog_labels_are_keyed_by_url_across_reset_and_recrawl(tmp_path: Path) -> None:
    """Labels should survive raw ID changes by persisting against normalized URL subjects."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    source_blog_id, _ = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    first_raw_id = repository.create_raw_discovered_url(
        source_blog_id=source_blog_id,
        normalized_url="https://stable.example/",
        status="success",
    )
    tag = repository.create_blog_label_tag(name="blog")

    first = repository.replace_blog_link_labels(blog_id=first_raw_id, tag_ids=[tag["id"]])
    reset = repository.reset()

    new_source_id, _ = repository.upsert_blog(
        url="https://new-source.example/",
        normalized_url="https://new-source.example/",
        domain="new-source.example",
    )
    repository.create_raw_discovered_url(
        source_blog_id=new_source_id,
        normalized_url="https://noise.example/",
        status="success",
    )
    second_raw_id = repository.create_raw_discovered_url(
        source_blog_id=new_source_id,
        normalized_url="https://stable.example/",
        status="success",
    )
    labeled = repository.list_blog_labeling_candidates(label="blog", labeled=True)

    assert first["blog_id"] == first_raw_id
    assert reset["blog_link_labels_preserved"] == 1
    assert second_raw_id != first_raw_id
    assert [row["id"] for row in labeled["items"]] == [second_raw_id]
    assert labeled["items"][0]["label_id"] == {"1": 1}
    assert labeled["items"][0]["label_slugs"] == ["blog"]


def test_repository_blog_labeling_upsert_rejects_non_labelable_raw_targets_and_reset_preserves_labels(
    tmp_path: Path,
) -> None:
    """Only raw-success/model-filtered blogs should be labelable."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    source_blog_id, inserted = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    assert inserted is True
    queued_blog_id, inserted = repository.upsert_blog(
        url="https://queued.example/",
        normalized_url="https://queued.example/",
        domain="queued.example",
    )
    assert inserted is True
    repository.mark_blog_result(
        blog_id=source_blog_id,
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=1,
    )
    repository.create_raw_discovered_url(
        source_blog_id=source_blog_id,
        normalized_url="https://finished.example/",
        status="success",
    )
    finished_blog = repository.get_labelable_blog_by_url(url="https://finished.example/")
    assert finished_blog is not None
    finished_blog_id = int(finished_blog["id"])

    with pytest.raises(repository_module.BlogLabelingConflictError, match="requires_labelable_raw_url"):
        repository.replace_blog_link_labels(blog_id=queued_blog_id, tag_ids=[1])

    with pytest.raises(repository_module.BlogLabelingNotFoundError, match="blog_not_found"):
        repository.replace_blog_link_labels(blog_id=999, tag_ids=[1])

    with pytest.raises(ValueError, match="Unsupported blog label name"):
        repository.create_blog_label_tag(name="   ")

    blog_tag = repository.create_blog_label_tag(name="blog")
    unknown_tag = repository.create_blog_label_tag(name="unknown")
    first = repository.replace_blog_link_labels(blog_id=finished_blog_id, tag_ids=[blog_tag["id"]])
    second = repository.replace_blog_link_labels(
        blog_id=finished_blog_id,
        tag_ids=[blog_tag["id"], unknown_tag["id"]],
    )
    assert first["blog_id"] == second["blog_id"] == finished_blog_id

    labeled = repository.list_blog_labeling_candidates(label="unknown", labeled=True)
    assert [row["id"] for row in labeled["items"]] == [finished_blog_id]
    assert [label["slug"] for label in labeled["items"][0]["labels"]] == ["blog", "unknown"]
    assert labeled["items"][0]["label_id"] == {"1": 1, "4": 1}

    reset = repository.reset()
    assert reset["blog_link_labels_deleted"] == 0
    assert reset["blog_label_tags_deleted"] == 0
    assert reset["blog_link_labels_preserved"] == 1
    assert reset["blog_labels_preserved"] == 1
    assert reset["blog_label_tags_preserved"] >= 6
    assert repository.list_blog_labeling_candidates()["items"] == []
    with session_scope(repository.session_factory) as session:
        label = session.scalar(
            select(BlogLabelModel).where(BlogLabelModel.normalized_url == "https://finished.example/")
        )
        assert label is not None
        assert label.label_id == {"1": 1, "4": 1}
        assert set(label.__table__.columns.keys()) == {
            "normalized_url",
            "title",
            "label_id",
            "created_time",
            "updated_time",
        }
        assert session.scalar(select(BlogLabelTagModel).where(BlogLabelTagModel.id == 1)).name == "blog"


def test_repository_blog_labeling_accepts_label_count_dict(tmp_path: Path) -> None:
    """Label replacement should persist direct label-id count dictionaries."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    source_blog_id, inserted = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    assert inserted is True
    raw_id = repository.create_raw_discovered_url(
        source_blog_id=source_blog_id,
        normalized_url="https://votes.example/",
        status="success",
    )

    created = repository.replace_blog_link_labels(
        blog_id=raw_id,
        label_id={"1": 10, "2": 1, "bad": 5, "4": 0},
    )
    page = repository.list_blog_labeling_candidates(label="company", labeled=True)

    assert created["label_id"] == {"1": 10, "2": 1}
    assert [label["count"] for label in created["labels"]] == [10, 1]
    assert [row["id"] for row in page["items"]] == [raw_id]
    assert page["items"][0]["label_id"] == {"1": 10, "2": 1}

    with pytest.raises(ValueError, match="Unsupported blog label id"):
        repository.replace_blog_link_labels(blog_id=raw_id, label_id={"999": 1})


def test_repository_blog_label_counts_use_all_persisted_url_labels(tmp_path: Path) -> None:
    """Label counts should aggregate every persisted URL label row."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    blog_tag = repository.create_blog_label_tag(name="blog")
    company_tag = repository.create_blog_label_tag(name="company")
    other_tag = repository.create_blog_label_tag(name="other")
    unknown_tag = repository.create_blog_label_tag(name="unknown")
    timestamp = repository_module.now_utc()
    with session_scope(repository.session_factory) as session:
        session.add_all(
            [
                BlogLabelModel(
                    normalized_url="https://blog.example/",
                    title="Blog",
                    label_id={str(blog_tag["id"]): 10},
                    created_time=timestamp,
                    updated_time=timestamp,
                ),
                BlogLabelModel(
                    normalized_url="https://company.example/",
                    title="Company",
                    label_id={str(company_tag["id"]): 1, str(other_tag["id"]): 1},
                    created_time=timestamp,
                    updated_time=timestamp,
                ),
                BlogLabelModel(
                    normalized_url="https://empty.example/",
                    title="Empty",
                    label_id={},
                    created_time=timestamp,
                    updated_time=timestamp,
                ),
            ]
        )

    counts = repository.get_blog_label_counts()

    assert counts["total_labeled"] == 2
    assert counts["by_label"]["blog"] == 1
    assert counts["by_label"]["company"] == 1
    assert counts["by_label"]["other"] == 1
    assert counts["by_label"]["unknown"] == 0


def test_repository_raw_label_target_does_not_create_lightweight_blog(tmp_path: Path) -> None:
    """Raw-only labeling should use raw IDs without creating lightweight blogs."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    legacy_id, inserted = repository.upsert_blog(
        url="https://legacy.example/",
        normalized_url="https://legacy.example/",
        domain="legacy.example",
    )
    assert inserted is True
    assert legacy_id == 1
    source_id, inserted = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    assert inserted is True
    repository.mark_blog_result(
        blog_id=source_id,
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=1,
    )
    raw_id = repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://new-raw.example/",
        status="success",
    )

    assert raw_id == legacy_id
    coverage = repository.ensure_labelable_raw_url_blogs()
    raw_target = repository.get_labelable_blog_by_url(url="https://new-raw.example/")

    assert coverage == {"inspected": 1, "created": 0}
    assert raw_target is not None
    assert raw_target["id"] == raw_id
    assert {row["normalized_url"] for row in repository.list_blogs()} == {
        "https://legacy.example/",
        "https://source.example/",
    }


def test_repository_builds_blog_label_training_rows_from_all_persisted_labels(
    tmp_path: Path,
) -> None:
    """Training rows should use every persisted label, independent of raw URL status."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    source_id, inserted = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    assert inserted is True
    repository.mark_blog_result(
        blog_id=source_id,
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=2,
        metadata_captured=True,
        title="Source",
    )
    repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://alpha.example/",
        status="success",
    )
    repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://model-alpha.example/",
        status="model:model_consensus_all_non_blog",
    )
    repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://blocked-alpha.example/",
        status="rule:blocked_tld",
    )
    alpha = repository.get_labelable_blog_by_url(url="https://alpha.example/")
    model_alpha = repository.get_labelable_blog_by_url(url="https://model-alpha.example/")
    assert alpha is not None
    assert model_alpha is not None
    alpha_id = int(alpha["id"])
    model_alpha_id = int(model_alpha["id"])
    _, inserted = repository.upsert_blog(
        url="https://blocked-alpha.example/",
        normalized_url="https://blocked-alpha.example/",
        domain="blocked-alpha.example",
    )
    assert inserted is True
    alpha_blog_id, inserted = repository.upsert_blog(
        url="https://alpha.example/",
        normalized_url="https://alpha.example/",
        domain="alpha.example",
    )
    assert inserted is True
    waiting_id, inserted = repository.upsert_blog(
        url="https://beta.example/",
        normalized_url="https://beta.example/",
        domain="beta.example",
    )
    assert inserted is True
    repository.mark_blog_result(
        blog_id=alpha_blog_id,
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=1,
        metadata_captured=True,
        title="Alpha",
    )
    repository.mark_blog_result(
        blog_id=waiting_id,
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=0,
    )

    blog_tag = repository.create_blog_label_tag(name="blog")
    official_tag = repository.create_blog_label_tag(name="official")
    repository.replace_blog_link_labels(blog_id=alpha_id, tag_ids=[official_tag["id"], blog_tag["id"]])
    repository.replace_blog_link_labels(blog_id=model_alpha_id, tag_ids=[blog_tag["id"]])
    with session_scope(repository.session_factory) as session:
        session.add(
            BlogLabelModel(
                normalized_url="https://legacy-only.example/",
                title="Legacy Only",
                label_id={str(blog_tag["id"]): 1},
                created_time=repository_module.now_utc(),
                updated_time=repository_module.now_utc(),
            )
        )
    with pytest.raises(repository_module.BlogLabelingConflictError):
        repository.replace_blog_link_labels(blog_id=waiting_id, tag_ids=[blog_tag["id"]])

    remaining = repository.list_blog_labeling_candidates(labeled=False)
    labeled = repository.list_blog_labeling_candidates(labeled=True, sort="recently_labeled")

    assert [row["url"] for row in remaining["items"]] == []
    assert {row["url"] for row in labeled["items"]} == {"https://alpha.example/", "https://model-alpha.example/"}
    with session_scope(repository.session_factory) as session:
        alpha_label = session.get(BlogLabelModel, "https://alpha.example/")
        alpha_title = alpha_label.title if alpha_label is not None else None
        rows = repository._blog_label_training_records(session)
    assert alpha_label is not None
    assert alpha_title == "Alpha"
    assert rows == [
        {
            "url": "https://alpha.example/",
            "title": "Alpha",
            "label": "blog",
        },
        {
            "url": "https://alpha.example/",
            "title": "Alpha",
            "label": "official",
        },
        {
            "url": "https://legacy-only.example/",
            "title": "Legacy Only",
            "label": "blog",
        },
        {
            "url": "https://model-alpha.example/",
            "title": "",
            "label": "blog",
        },
    ]


def test_repository_syncs_and_rebuilds_blog_label_training_parquet(tmp_path: Path) -> None:
    """Parquet export should persist labeled rows and report missing saved data."""
    settings = Settings(
        db_path=tmp_path / "db.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
    )
    repository = repository_module.build_repository(db_path=settings.db_path, settings=settings)
    first_id, _ = repository.upsert_blog(
        url="https://alpha.example/",
        normalized_url="https://alpha.example/",
        domain="alpha.example",
    )
    second_id, _ = repository.upsert_blog(
        url="https://beta.example/",
        normalized_url="https://beta.example/",
        domain="beta.example",
    )
    for blog_id, title in ((first_id, "Alpha"), (second_id, "Beta")):
        repository.mark_blog_result(
            blog_id=blog_id,
            crawl_status="FINISHED",
            status_code=200,
            friend_links_count=1,
            metadata_captured=True,
            title=title,
        )
        repository.create_raw_discovered_url(
            source_blog_id=first_id,
            normalized_url="https://alpha.example/" if blog_id == first_id else "https://beta.example/",
            status="success",
        )

    blog_tag = repository.create_blog_label_tag(name="blog")
    official_tag = repository.create_blog_label_tag(name="official")
    repository.replace_blog_link_labels(blog_id=first_id, tag_ids=[blog_tag["id"]])

    first_sync = repository.sync_blog_label_training_parquet()

    parquet_path = tmp_path / "exports" / "blog-label-training.parquet"
    assert first_sync["rewritten"] is True
    assert first_sync["saved_count"] == 1
    assert parquet_path.exists()
    assert pq.read_table(parquet_path).to_pylist() == [
        {"url": "https://alpha.example/", "title": "Alpha", "label": "blog"}
    ]

    repository.replace_blog_link_labels(blog_id=second_id, tag_ids=[official_tag["id"]])
    status = repository.get_blog_label_training_parquet_status()
    assert status["saved_count"] == 1
    assert status["total_labeled"] == 2
    assert status["missing_count"] == 1

    rebuild = repository.rebuild_blog_label_training_parquet()
    assert rebuild["rewritten"] is True
    assert rebuild["saved_count"] == 2
    assert pq.read_table(parquet_path).to_pylist() == [
        {"url": "https://alpha.example/", "title": "Alpha", "label": "blog"},
        {"url": "https://beta.example/", "title": "Beta", "label": "official"},
    ]

    parquet_payload, export_status = repository.export_blog_label_training_parquet()
    assert parquet_payload == parquet_path.read_bytes()
    assert export_status["saved_count"] == 2


def test_legacy_label_import_uses_labelable_raw_url_scope(tmp_path: Path) -> None:
    """Legacy import should align labels against the same raw URL scope as the UI."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    source_id, _ = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    repository.mark_blog_result(
        blog_id=source_id,
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=2,
        metadata_captured=True,
        title="Source",
    )
    repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://model-old.example/",
        status="model:model_consensus_all_non_blog",
    )
    repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://rule-old.example/",
        status="rule:blocked_tld",
    )
    csv_path = tmp_path / "legacy.csv"
    csv_path.write_text(
        "url,title,label\n"
        "https://model-old.example/,Model Old,blog\n"
        "https://rule-old.example/,Rule Old,company\n",
        encoding="utf-8",
    )

    dry_run = import_legacy_blog_labels.import_legacy_labels(
        repository=repository,
        source_csv=csv_path,
        apply=False,
        replace_existing=False,
    )
    applied = import_legacy_blog_labels.import_legacy_labels(
        repository=repository,
        source_csv=csv_path,
        apply=True,
        replace_existing=False,
    )

    assert dry_run.importable_rows == 1
    assert dry_run.skipped_missing_blog == 1
    assert applied.imported_rows == 1
    labeled = repository.list_blog_labeling_candidates(label="blog", labeled=True)
    assert [row["url"] for row in labeled["items"]] == ["https://model-old.example/"]


def test_legacy_label_count_import_clears_and_restores_url_keyed_labels(tmp_path: Path) -> None:
    """URL-keyed legacy import should clear labels and restore CSV counts."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    blog_tag = repository.create_blog_label_tag(name="blog")
    other_tag = repository.create_blog_label_tag(name="other")
    source_id, _ = repository.upsert_blog(
        url="https://source.example/",
        normalized_url="https://source.example/",
        domain="source.example",
    )
    raw_id = repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://old.example/",
        status="success",
    )
    repository.replace_blog_link_labels(blog_id=raw_id, tag_ids=[blog_tag["id"]])
    csv_path = tmp_path / "legacy-counts.csv"
    csv_path.write_text(
        "url,title,label\n"
        "https://old.example/,Old,blog\n"
        "https://old.example/,Old,blog\n"
        "https://tool.example/,Tool,others\n"
        "bad-url,Bad,blog\n"
        "https://skip.example/,Skip,weird\n",
        encoding="utf-8",
    )

    dry_run = import_legacy_label_counts.import_legacy_label_counts(
        repository=repository,
        source_csv=csv_path,
        apply=False,
        clear_existing=False,
    )
    applied = import_legacy_label_counts.import_legacy_label_counts(
        repository=repository,
        source_csv=csv_path,
        apply=True,
        clear_existing=True,
    )

    assert dry_run.imported_urls == 2
    assert dry_run.imported_label_counts == 3
    assert applied.cleared_existing == 1
    assert applied.imported_urls == 2
    with session_scope(repository.session_factory) as session:
        rows = {
            row.normalized_url: (row.title, row.label_id)
            for row in session.scalars(select(BlogLabelModel)).all()
        }
    assert rows["https://old.example/"] == ("Old", {str(blog_tag["id"]): 2})
    assert rows["https://tool.example/"] == ("Tool", {str(other_tag["id"]): 1})


def test_legacy_label_count_import_can_backfill_titles_only(tmp_path: Path) -> None:
    """Title-only legacy import should update existing rows without changing labels."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    blog_tag = repository.create_blog_label_tag(name="blog")
    with session_scope(repository.session_factory) as session:
        session.add(
            BlogLabelModel(
                normalized_url="https://old.example/",
                title="",
                label_id={str(blog_tag["id"]): 7},
                created_time=repository_module.now_utc(),
                updated_time=repository_module.now_utc(),
            )
        )
    csv_path = tmp_path / "legacy-counts.csv"
    csv_path.write_text(
        "url,title,label\n"
        "https://old.example/,Recovered Title,blog\n"
        "https://missing.example/,Missing Title,blog\n",
        encoding="utf-8",
    )

    dry_run = import_legacy_label_counts.import_legacy_label_counts(
        repository=repository,
        source_csv=csv_path,
        apply=False,
        clear_existing=False,
        titles_only=True,
    )
    applied = import_legacy_label_counts.import_legacy_label_counts(
        repository=repository,
        source_csv=csv_path,
        apply=True,
        clear_existing=False,
        titles_only=True,
    )

    assert dry_run.title_updates_available == 1
    assert dry_run.updated_titles == 0
    assert applied.updated_titles == 1
    with session_scope(repository.session_factory) as session:
        rows = {
            row.normalized_url: (row.title, row.label_id)
            for row in session.scalars(select(BlogLabelModel)).all()
        }
    assert rows == {"https://old.example/": ("Recovered Title", {str(blog_tag["id"]): 7})}


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
                "blog_id": beta_id,
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
                "blog_id": gamma_id,
                "domain": "gamma.example",
                "title": "gamma.example title",
                "icon_url": "https://gamma.example/favicon.ico",
            },
        }
    ]
    assert detail["recommended_blogs"][0]["blog"] == {
        "id": delta_id,
        "blog_id": delta_id,
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
            "blog_id": beta_id,
            "domain": "beta.example",
            "title": "beta.example title",
            "icon_url": "https://beta.example/favicon.ico",
        }
    ]
