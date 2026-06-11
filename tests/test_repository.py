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
from persistence_api.models import BlogInteractionModel
from persistence_api.models import BlogModel
from persistence_api.models import PendingUserRegistrationModel
from persistence_api.models import RawDiscoveredUrlModel
from persistence_api.models import RecommendationImpressionModel
from persistence_api.models import RecommendationRequestModel
from persistence_api.models import AdminHourlyStatsModel
from persistence_api.models import SeedModel
from shared.contracts.enums import CrawlStatus
from shared.config import Settings


class CapturingEmailDelivery:
    """Test email sender that records lifecycle messages.

    Attributes:
        verification_urls: Verification messages captured as `(email, url)`.
        reset_urls: Password reset messages captured as `(email, url)`.
    """

    def __init__(self) -> None:
        self.verification_urls: list[tuple[str, str]] = []
        self.reset_urls: list[tuple[str, str]] = []

    def send_verification_email(self, *, to_email: str, verification_url: str) -> None:
        """Capture one verification email.

        Args:
            to_email: Recipient email address.
            verification_url: One-time verification URL.

        Returns:
            None.
        """

        self.verification_urls.append((to_email, verification_url))

    def send_password_reset_email(self, *, to_email: str, reset_url: str) -> None:
        """Capture one password reset email.

        Args:
            to_email: Recipient email address.
            reset_url: One-time password reset URL.

        Returns:
            None.
        """

        self.reset_urls.append((to_email, reset_url))


def build_dev_token_repository(tmp_path: Path) -> repository_module.SQLAlchemyRepository:
    """Build a repository that exposes lifecycle tokens for local flow tests."""
    settings = Settings(
        db_path=tmp_path / "db.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        email_dev_expose_tokens=True,
    )
    return repository_module.build_repository(db_path=settings.db_path, settings=settings)


def register_and_verify_user(
    repository: repository_module.SQLAlchemyRepository,
    *,
    email: str,
    password: str,
) -> dict[str, object]:
    """Create a user through the verify-before-persist registration flow."""

    pending = repository.register_user(email=email, password=password)
    token = pending.get("verification_token")
    assert isinstance(token, str)
    return repository.confirm_email_verification(token=token)


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


def test_repository_reset_preserves_seed_rows_and_restarts_ids(tmp_path: Path) -> None:
    """Reset should wipe only graph queue tables while retaining other records."""
    repository = build_dev_token_repository(tmp_path)
    first_blog_id, inserted = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
        accepted_by="seed",
        seed_source_path="seed.csv",
        seed_source_row=2,
    )
    assert inserted is True
    second_blog_id, inserted = repository.upsert_blog(
        url="https://friend.example.com/",
        normalized_url="https://friend.example.com/",
        domain="friend.example.com",
    )
    assert inserted is True
    repository.mark_blog_result(
        blog_id=first_blog_id,
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=1,
        metadata_captured=True,
        title="Blog Example",
    )
    repository.add_edge(
        from_blog_id=first_blog_id,
        to_blog_id=second_blog_id,
        link_url_raw="https://friend.example.com/",
        link_text="Friend Blog",
    )
    repository.create_raw_discovered_url(
        source_blog_id=first_blog_id,
        normalized_url="https://raw.example.com/",
        status="success",
    )
    repository.add_log(
        blog_id=first_blog_id,
        stage="crawl",
        result="ok",
        message="This should not be persisted",
    )
    verified_user = register_and_verify_user(repository, email="reset-user@example.com", password="long enough")
    user = repository.login_user(email=str(verified_user["email"]), password="long enough")
    batch = repository.create_random_recommendation_batch(
        count=1,
        visitor_id="visitor-reset",
        session_id="session-reset",
        source="reset-test",
        page_url="http://localhost/reset-test",
    )
    recommendation_item = batch["items"][0]
    repository.record_blog_interaction(
        event_uuid="reset-event",
        event_type="detail_open",
        blog_id=recommendation_item["id"],
        visitor_id="visitor-reset",
        session_id="session-reset",
        entrance_kind="reset_test",
        entrance_url="http://localhost/reset-test",
        request_uuid=recommendation_item["request_uuid"],
        impression_id=recommendation_item["impression_id"],
        interaction_order=1,
    )

    result = repository.reset()

    assert result["ok"] is True
    assert result["blogs_deleted"] == 2
    assert result["edges_deleted"] == 1
    assert result["raw_discovered_urls_deleted"] == 1
    assert result["logs_deleted"] == 0
    assert set(result) == {
        "ok",
        "blogs_deleted",
        "edges_deleted",
        "raw_discovered_urls_deleted",
        "logs_deleted",
    }
    assert repository.list_blogs() == []
    assert repository.list_edges() == []
    assert repository.list_logs() == []
    assert repository.stats()["total_blogs"] == 0
    assert repository.stats()["total_edges"] == 0
    with session_scope(repository.session_factory) as session:
        seed = session.scalar(select(SeedModel))
        assert seed is not None
        assert seed.normalized_url == "https://blog.example.com/"
        assert seed.blog_id is None
        assert repository.get_user_by_session_token(token=user["token"]) is not None
        assert session.scalar(select(RecommendationRequestModel).limit(1)) is not None
        assert session.scalar(select(RecommendationImpressionModel).limit(1)) is not None
        assert session.scalar(select(BlogInteractionModel).limit(1)) is not None

    new_blog_id, inserted = repository.upsert_blog(
        url="https://reset.example.com/",
        normalized_url="https://reset.example.com/",
        domain="reset.example.com",
    )
    assert inserted is True
    assert new_blog_id == 1
    restored_blog_id, inserted = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
    )
    assert inserted is True
    restored_stats = repository.get_blog_recommendation_stats(restored_blog_id)
    assert restored_stats is not None
    assert restored_stats["impressions"] == 1
    assert restored_stats["detail_opens"] == 1


def test_repository_register_login_and_session_profile(tmp_path: Path) -> None:
    """Users persist only after email verification, then can log in."""
    repository = build_dev_token_repository(tmp_path)

    pending = repository.register_user(email="User@Example.com", password="correct horse")
    assert pending["sent"] is True
    assert pending["verification_token"]
    with session_scope(repository.session_factory) as session:
        assert session.scalar(select(PendingUserRegistrationModel).where(PendingUserRegistrationModel.email == "user@example.com")) is not None
        assert session.scalar(select(repository_module.UserModel).where(repository_module.UserModel.email == "user@example.com")) is None
    with pytest.raises(repository_module.UserAuthError, match="invalid_credentials"):
        repository.login_user(email="user@example.com", password="correct horse")

    created = repository.confirm_email_verification(token=str(pending["verification_token"]))
    assert created["email"] == "user@example.com"
    assert created["role"] == "user"
    assert created["email_verified"] is True

    logged_in = repository.login_user(email="user@example.com", password="correct horse")
    assert logged_in["user"]["id"] == created["id"]
    assert logged_in["token"]

    assert repository.revoke_user_session(token=logged_in["token"]) is True
    assert repository.get_user_by_session_token(token=logged_in["token"]) is None


def test_repository_email_verification_and_password_reset_flow(tmp_path: Path) -> None:
    """Email verification and password reset tokens should be single-use."""
    repository = build_dev_token_repository(tmp_path)

    created = repository.register_user(email="verify@example.com", password="correct horse")
    verification_token = created["verification_token"]
    verified = repository.confirm_email_verification(token=verification_token)
    assert verified["email_verified"] is True

    with pytest.raises(repository_module.UserAuthError, match="invalid_token"):
        repository.confirm_email_verification(token=verification_token)

    login = repository.login_user(email="verify@example.com", password="correct horse")
    reset_request = repository.request_password_reset(email="verify@example.com")
    reset_token = reset_request["reset_token"]
    reset_user = repository.reset_user_password(token=reset_token, password="new correct horse")
    assert reset_user["email"] == "verify@example.com"
    assert repository.get_user_by_session_token(token=login["token"]) is None

    with pytest.raises(repository_module.UserAuthError, match="invalid_credentials"):
        repository.login_user(email="verify@example.com", password="correct horse")
    assert repository.login_user(email="verify@example.com", password="new correct horse")["token"]


def test_repository_sends_lifecycle_email_and_hides_tokens_when_configured(tmp_path: Path) -> None:
    """Production email mode should send links without exposing raw tokens."""
    email_delivery = CapturingEmailDelivery()
    settings = Settings(
        db_path=tmp_path / "db.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        public_base_url="https://heyblog.example.com",
        email_dev_expose_tokens=False,
    )
    repository = repository_module.build_repository(
        db_path=tmp_path / "db.sqlite",
        settings=settings,
        email_delivery=email_delivery,
    )

    verification_payload = repository.register_user(email="Mail@Example.com", password="correct horse")
    assert verification_payload == {
        "sent": True,
        "expires_at": verification_payload["expires_at"],
    }
    assert len(email_delivery.verification_urls) == 1
    sent_email, verification_url = email_delivery.verification_urls[0]
    assert sent_email == "mail@example.com"
    assert verification_url.startswith("https://heyblog.example.com/profile?verify_token=")
    verification_token = verification_url.rsplit("=", 1)[1]
    assert repository.confirm_email_verification(token=verification_token)["email_verified"] is True

    reset_payload = repository.request_password_reset(email="mail@example.com")
    assert reset_payload == {
        "sent": True,
        "expires_at": reset_payload["expires_at"],
    }
    assert len(email_delivery.reset_urls) == 1
    reset_email, reset_url = email_delivery.reset_urls[0]
    assert reset_email == "mail@example.com"
    assert reset_url.startswith("https://heyblog.example.com/profile?reset_token=")
    reset_token = reset_url.rsplit("=", 1)[1]
    assert repository.reset_user_password(token=reset_token, password="new correct horse")["email"] == "mail@example.com"


def test_repository_admin_role_updates_user_identity(tmp_path: Path) -> None:
    """Users should be promotable between regular user and admin roles."""
    repository = build_dev_token_repository(tmp_path)

    created = register_and_verify_user(repository, email="admin@example.com", password="correct horse")
    user_id = int(created["id"])
    promoted = repository.update_user_role(user_id=user_id, role="admin")
    assert promoted["role"] == "admin"
    listed = repository.list_users()
    assert listed["items"][0]["role"] == "admin"

    demoted = repository.update_user_role(user_id=user_id, role="user")
    assert demoted["role"] == "user"
    with pytest.raises(ValueError, match="invalid_user_role"):
        repository.update_user_role(user_id=user_id, role="label_admin")


def test_repository_rejects_duplicate_user_and_bad_credentials(tmp_path: Path) -> None:
    """Email uniqueness and password validation should produce stable errors."""
    repository = build_dev_token_repository(tmp_path)
    register_and_verify_user(repository, email="dupe@example.com", password="long enough")

    with pytest.raises(repository_module.UserAuthError, match="email_already_registered"):
        repository.register_user(email="DUPE@example.com", password="long enough")

    repository.register_user(email="pending@example.com", password="long enough")
    with pytest.raises(repository_module.UserAuthError, match="email_registration_pending"):
        repository.register_user(email="PENDING@example.com", password="long enough")
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


def test_repository_keeps_accepted_blog_visible_after_crawl_failure(tmp_path: Path) -> None:
    """Crawl failures must not undo durable blog acceptance.

    Args:
        tmp_path: Temporary directory used for the SQLite test database.

    Returns:
        None. Assertions verify acceptance fields and catalog eligibility.
    """
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    blog_id, inserted = repository.upsert_blog(
        url="https://friend.example.com/",
        normalized_url="https://friend.example.com/",
        domain="friend.example.com",
        accepted_by="rss",
    )
    assert inserted is True

    repository.mark_blog_result(
        blog_id=blog_id,
        crawl_status="FAILED",
        status_code=413,
        friend_links_count=0,
        crawl_error_kind="page_too_large",
        crawl_error_message="homepage exceeded max page bytes",
    )

    blog = repository.get_blog(blog_id)
    assert blog is not None
    assert blog["acceptance_status"] == "ACCEPTED"
    assert blog["accepted_by"] == "rss"
    assert blog["crawl_status"] == "FAILED"
    assert blog["crawl_error_kind"] == "page_too_large"
    assert blog["successful_crawl_at"] is None

    catalog = repository.list_blogs_catalog()
    assert [item["id"] for item in catalog["items"]] == [blog_id]
    assert catalog["filters"]["acceptance_status"] == "ACCEPTED"


def test_repository_successful_crawl_clears_previous_error(tmp_path: Path) -> None:
    """A later successful crawl should clear stale failure details.

    Args:
        tmp_path: Temporary directory used for the SQLite test database.

    Returns:
        None. Assertions verify failure details do not survive a success.
    """
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    blog_id, _ = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
        accepted_by="model",
    )

    repository.mark_blog_result(
        blog_id=blog_id,
        crawl_status="FAILED",
        status_code=None,
        friend_links_count=0,
        crawl_error_kind="timeout",
        crawl_error_message="timed out",
    )
    repository.mark_blog_result(
        blog_id=blog_id,
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=3,
    )

    blog = repository.get_blog(blog_id)
    assert blog is not None
    assert blog["acceptance_status"] == "ACCEPTED"
    assert blog["accepted_by"] == "model"
    assert blog["crawl_error_kind"] is None
    assert blog["crawl_error_message"] is None
    assert blog["successful_crawl_at"] is not None


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
    assert stats["rule_drops"]["rule:same_domain"] == 1
    assert stats["rule_drops"]["rule:platform_blocked"] == 1
    assert stats["success_sources"] == {"rss": 0, "model": 0, "unknown": 1}
    assert stats["funnel"]["raw"] == 3
    assert stats["funnel"]["success"] == 1
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


def test_repository_filter_stats_split_success_sources(tmp_path: Path) -> None:
    """Filter stats should distinguish RSS and model success exits."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    source_id, _ = repository.upsert_blog(
        url="https://blog.example.com/",
        normalized_url="https://blog.example.com/",
        domain="blog.example.com",
    )
    rss_raw = repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://rss.example/",
        status="pending",
    )
    model_raw = repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://model.example/",
        status="pending",
    )
    rejected_raw = repository.create_raw_discovered_url(
        source_blog_id=source_id,
        normalized_url="https://reject.example/",
        status="pending",
    )

    repository.update_raw_discovered_url_status(record_id=rss_raw, status="success", accepted_by="rss")
    repository.update_raw_discovered_url_status(record_id=model_raw, status="success", accepted_by="model")
    repository.update_raw_discovered_url_status(
        record_id=rejected_raw,
        status="model:model_consensus_all_non_blog",
        accepted_by="model",
    )

    stats = repository.get_filter_stats_by_chain_order()

    assert stats["success_sources"] == {"rss": 1, "model": 1, "unknown": 0}
    assert stats["funnel"]["after_rules"] == 3
    assert stats["funnel"]["model_rejected"] == 1
    assert stats["funnel"]["success"] == 2


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


def test_repository_finds_blog_id_by_normalized_url(tmp_path: Path) -> None:
    """Duplicate discovery repair should resolve accepted target blogs by URL."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    blog_id, _ = repository.upsert_blog(
        url="https://friend.example/",
        normalized_url="https://friend.example/",
        domain="friend.example",
    )

    assert repository.find_blog_id_by_normalized_url(normalized_url="https://friend.example/") == blog_id
    assert repository.find_blog_id_by_normalized_url(normalized_url="https://missing.example/") is None


def test_repository_finds_blog_id_by_normalized_url_identity_fallback(tmp_path: Path) -> None:
    """Duplicate edge repair should survive blog identity canonicalization."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    blog_id, _ = repository.upsert_blog(
        url="https://zhuruilei.66law.cn/",
        normalized_url="https://zhuruilei.66law.cn/",
        domain="zhuruilei.66law.cn",
    )

    assert repository.find_blog_id_by_normalized_url(normalized_url="https://zhuruilei.66law.cn/") == blog_id


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

    assert len(blogs) == 2
    assert {blog["identity_key"] for blog in blogs} == {"site:66law.cn/"}
    assert all(blog["identity_ruleset_version"] == repository_module.IDENTITY_RULESET_VERSION for blog in blogs)


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


def test_repository_requeues_failed_blogs_for_retry(tmp_path: Path) -> None:
    """Explicit admin retry should move failed blogs back to the waiting queue."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    failed_id, _ = repository.upsert_blog(
        url="https://failed.example/",
        normalized_url="https://failed.example/",
        domain="failed.example",
    )
    finished_id, _ = repository.upsert_blog(
        url="https://finished.example/",
        normalized_url="https://finished.example/",
        domain="finished.example",
    )
    repository.mark_blog_result(
        blog_id=failed_id,
        crawl_status="FAILED",
        status_code=None,
        friend_links_count=0,
    )
    repository.mark_blog_result(
        blog_id=finished_id,
        crawl_status="FINISHED",
        status_code=200,
        friend_links_count=1,
    )

    result = repository.requeue_failed_blogs()

    assert result == {"requeued": 1}
    assert repository.get_blog(failed_id)["crawl_status"] == "WAITING"
    assert repository.get_blog(finished_id)["crawl_status"] == "FINISHED"
    stats = repository.stats()
    assert stats["pending_tasks"] == 1
    assert stats["failed_tasks"] == 0


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


def test_repository_creates_user_seed_as_accepted_waiting_blog(tmp_path: Path) -> None:
    """User seeds should be accepted as blogs while remaining crawlable."""
    repository = repository_module.build_repository(
        db_path=tmp_path / "db.sqlite",
        settings=Settings(
            db_path=tmp_path / "db.sqlite",
            seed_path=tmp_path / "seed.csv",
            export_dir=tmp_path / "exports",
            decision_model_consensus_enabled=False,
        ),
    )

    result = repository.create_user_seed(homepage_url="https://user-blog.example.com/")

    assert result["status"] == "QUEUED"
    blog = repository.get_blog(result["blog_id"])
    assert blog is not None
    assert blog["acceptance_status"] == "ACCEPTED"
    assert blog["accepted_by"] == "user"
    assert blog["crawl_status"] == "WAITING"
    seeds = repository.list_seeds()
    assert len(seeds) == 1
    assert seeds[0]["normalized_url"] == "https://user-blog.example.com/"
    assert seeds[0]["source_path"] == "user"
    assert seeds[0]["blog_id"] == result["blog_id"]
    claimed = repository.get_next_waiting_blog()
    assert claimed is not None
    assert claimed["id"] == result["blog_id"]


def test_repository_user_seed_runs_rule_filters_only(tmp_path: Path) -> None:
    """User seed submission should reject deterministic rule failures."""
    repository = repository_module.build_repository(
        db_path=tmp_path / "db.sqlite",
        settings=Settings(
            db_path=tmp_path / "db.sqlite",
            seed_path=tmp_path / "seed.csv",
            export_dir=tmp_path / "exports",
            decision_model_consensus_enabled=False,
        ),
    )

    with pytest.raises(ValueError, match="rule:non_root_path"):
        repository.create_user_seed(homepage_url="https://user-blog.example.com/posts/1")


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
        "acceptance_status": "ACCEPTED",
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
    settings = Settings(
        db_path=tmp_path / "heyblog.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        email_dev_expose_tokens=True,
    )
    repository = repository_module.build_repository(db_path=settings.db_path, settings=settings)
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
    account = register_and_verify_user(repository, email="labeler@example.com", password="long enough")
    user_id = int(account["id"])
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


def test_repository_random_catalog_only_demotes_user_non_blog_feedback(tmp_path: Path) -> None:
    """Random catalog weighting should ignore blog votes and demote non-blog votes."""
    repository = repository_module.build_repository(db_path=tmp_path / "heyblog.sqlite")
    repository.create_blog_label_tag(name="blog")
    repository.create_blog_label_tag(name="other")

    if repository.engine.dialect.name == "sqlite":
        def fixed_random(dbapi_connection: object, _connection_record: object) -> None:
            dbapi_connection.create_function("random", 0, lambda: 1)

        event.listen(repository.engine, "connect", fixed_random)
        repository.engine.dispose()

    boosted_id, boosted_inserted = repository.upsert_blog(
        url="https://boosted.example/",
        normalized_url="https://boosted.example/",
        domain="boosted.example",
    )
    baseline_id, baseline_inserted = repository.upsert_blog(
        url="https://baseline.example/",
        normalized_url="https://baseline.example/",
        domain="baseline.example",
    )
    demoted_id, demoted_inserted = repository.upsert_blog(
        url="https://demoted.example/",
        normalized_url="https://demoted.example/",
        domain="demoted.example",
    )
    assert boosted_inserted is True
    assert baseline_inserted is True
    assert demoted_inserted is True
    for blog_id, title in (
        (boosted_id, "Boosted"),
        (baseline_id, "Baseline"),
        (demoted_id, "Demoted"),
    ):
        repository.mark_blog_result(
            blog_id=blog_id,
            crawl_status="FINISHED",
            status_code=200,
            friend_links_count=1,
            metadata_captured=True,
            title=title,
            icon_url=None,
        )

    repository.increment_blog_user_label(blog_id=boosted_id, label="blog")
    repository.increment_blog_user_label(blog_id=demoted_id, label="other")

    random_page = repository.list_blogs_catalog(status="finished", sort="random", page_size=10)

    assert [item["url"] for item in random_page["items"]] == [
        "https://baseline.example/",
        "https://boosted.example/",
        "https://demoted.example/",
    ]


def test_repository_persists_random_recommendation_batch_and_interaction_stats(tmp_path: Path) -> None:
    """Random recommendation batches should persist request, impression, event, and stat rows."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    for index in range(3):
        blog_id, inserted = repository.upsert_blog(
            url=f"https://recommend-{index}.example/",
            normalized_url=f"https://recommend-{index}.example/",
            domain=f"recommend-{index}.example",
            accepted_by="rss",
        )
        assert inserted is True
        repository.mark_blog_result(
            blog_id=blog_id,
            crawl_status="FINISHED",
            status_code=200,
            friend_links_count=index,
            metadata_captured=True,
            title=f"Recommend {index}",
            icon_url=None,
        )

    batch = repository.create_random_recommendation_batch(
        count=2,
        visitor_id="visitor-1",
        session_id="session-1",
        source="test",
        page_url="http://localhost/random",
    )

    assert batch["requested_count"] == 2
    assert batch["served_count"] == 2
    assert [item["position"] for item in batch["items"]] == [1, 2]
    first = batch["items"][0]
    event = repository.record_blog_interaction(
        event_uuid="event-1",
        event_type="detail_open",
        blog_id=first["id"],
        visitor_id="visitor-1",
        session_id="session-1",
        entrance_kind="test_detail",
        entrance_url="http://localhost/random",
        request_uuid=first["request_uuid"],
        impression_id=first["impression_id"],
        interaction_order=1,
        client_event_at="2026-06-07T12:00:00Z",
        attributes={"button": "detail"},
    )
    duplicate = repository.record_blog_interaction(
        event_uuid="event-1",
        event_type="detail_open",
        blog_id=first["id"],
        visitor_id="visitor-1",
        session_id="session-1",
        entrance_kind="test_detail",
        entrance_url="http://localhost/random",
    )
    repository.record_blog_interaction(
        event_uuid="event-2",
        event_type="external_open",
        blog_id=first["id"],
        visitor_id="visitor-1",
        session_id="session-1",
        entrance_kind="test_external",
        entrance_url="http://localhost/random",
        request_uuid=first["request_uuid"],
        impression_id=first["impression_id"],
        interaction_order=2,
    )
    stats = repository.get_blog_recommendation_stats(first["id"])
    strategy_stats = repository.get_recommendation_strategy_stats()
    hourly_stats = repository.get_admin_hourly_stats()

    assert event["duplicate"] is False
    assert event["entrance_kind"] == "test_detail"
    assert event["entrance_url"] == "http://localhost/random"
    assert duplicate["duplicate"] is True
    assert stats is not None
    assert stats["impressions"] == 1
    assert stats["detail_opens"] == 1
    assert stats["external_opens"] == 1
    assert stats["unique_visitors"] == 1
    assert stats["ctr"] == 2.0
    assert strategy_stats["total_requests"] == 1
    assert strategy_stats["total_impressions"] == 2
    assert strategy_stats["total_interactions"] == 2
    assert strategy_stats["by_strategy"][0]["clicks"] == 2
    assert hourly_stats["current_hour"]["user_count"] == 0
    assert hourly_stats["current_hour"]["random_request_count"] == 1
    assert hourly_stats["current_hour"]["random_impression_count"] == 2
    assert hourly_stats["current_hour"]["detail_open_count"] == 1
    assert hourly_stats["current_hour"]["external_open_count"] == 1
    assert hourly_stats["current_hour"]["detail_ctr"] == 0.5
    assert hourly_stats["current_hour"]["external_ctr"] == 0.5
    assert hourly_stats["current_hour"]["total_click_ctr"] == 1.0
    with session_scope(repository.session_factory) as session:
        assert session.scalar(select(RecommendationRequestModel).limit(1)) is not None
        stored_impression = session.scalar(select(RecommendationImpressionModel).limit(1))
        stored_interaction = session.scalar(select(BlogInteractionModel).limit(1))
        stored_hourly_stats = session.scalar(select(AdminHourlyStatsModel).limit(1))
        assert stored_impression is not None
        assert stored_impression.normalized_url == first["normalized_url"]
        assert "blog_id" not in RecommendationImpressionModel.__table__.columns
        assert stored_interaction is not None
        assert stored_interaction.normalized_url == first["normalized_url"]
        assert "blog_id" not in BlogInteractionModel.__table__.columns
        assert stored_hourly_stats is not None
        assert stored_hourly_stats.random_impression_count == 2


def test_repository_blog_catalog_uses_display_identity_fallbacks_for_legacy_rows(tmp_path: Path) -> None:
    """Catalog should keep title fallback but not synthesize unverified icons."""
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
    assert icon_filtered["items"] == []
    assert title_filtered["items"][0]["title"] == "legacy.example"
    assert title_filtered["items"][0]["icon_url"] is None


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
    assert reset["raw_discovered_urls_deleted"] == 1
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
    assert reset["blogs_deleted"] == 2
    assert reset["raw_discovered_urls_deleted"] == 1
    assert repository.list_blog_labeling_candidates()["items"] == []
    with session_scope(repository.session_factory) as session:
        label = session.scalar(
            select(BlogLabelModel).where(BlogLabelModel.normalized_url == "https://finished.example/")
        )
        assert label is not None
        assert label.label_id == {"1": 1, "4": 1}
        assert session.scalar(select(BlogLabelTagModel).where(BlogLabelTagModel.slug == "blog")) is not None
        assert session.scalar(select(BlogLabelTagModel).where(BlogLabelTagModel.slug == "unknown")) is not None
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
        "feed_url": None,
        "title": "delta.example title",
        "icon_url": "https://delta.example/favicon.ico",
        "status_code": 200,
        "acceptance_status": "ACCEPTED",
        "accepted_by": None,
        "accepted_at": detail["recommended_blogs"][0]["blog"]["accepted_at"],
        "crawl_error_kind": None,
        "crawl_error_message": None,
        "last_crawl_attempt_at": detail["recommended_blogs"][0]["blog"]["last_crawl_attempt_at"],
        "successful_crawl_at": detail["recommended_blogs"][0]["blog"]["successful_crawl_at"],
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
    assert detail["relation_graphs"]["incoming"]["focus_blog_id"] == alpha_id
    assert [node["blog_id"] for node in detail["relation_graphs"]["incoming"]["nodes"]] == [alpha_id, gamma_id]
    assert detail["relation_graphs"]["incoming"]["edges"][0]["from_blog_id"] == gamma_id
    assert detail["relation_graphs"]["outgoing"]["focus_blog_id"] == alpha_id
    assert {node["blog_id"] for node in detail["relation_graphs"]["outgoing"]["nodes"]} == {
        alpha_id,
        beta_id,
        delta_id,
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


def test_repository_blog_detail_relation_graph_keeps_all_edges_within_two_layers(
    tmp_path: Path,
) -> None:
    """Relation graphs should keep every edge reachable within the configured two-layer depth."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    focus_id, inserted = repository.upsert_blog(
        url="https://focus.example/",
        normalized_url="https://focus.example/",
        domain="focus.example",
    )
    assert inserted is True

    outgoing_first_ids: list[int] = []
    incoming_first_ids: list[int] = []
    for index in range(12):
        outgoing_id, inserted = repository.upsert_blog(
            url=f"https://out-first-{index}.example/",
            normalized_url=f"https://out-first-{index}.example/",
            domain=f"out-first-{index}.example",
        )
        assert inserted is True
        outgoing_first_ids.append(outgoing_id)
        repository.add_edge(
            from_blog_id=focus_id,
            to_blog_id=outgoing_id,
            link_url_raw=f"https://out-first-{index}.example/",
            link_text=f"Out first {index}",
        )

        incoming_id, inserted = repository.upsert_blog(
            url=f"https://in-first-{index}.example/",
            normalized_url=f"https://in-first-{index}.example/",
            domain=f"in-first-{index}.example",
        )
        assert inserted is True
        incoming_first_ids.append(incoming_id)
        repository.add_edge(
            from_blog_id=incoming_id,
            to_blog_id=focus_id,
            link_url_raw="https://focus.example/",
            link_text=f"In first {index}",
        )

    outgoing_second_ids: list[int] = []
    incoming_second_ids: list[int] = []
    for index in range(11):
        outgoing_id, inserted = repository.upsert_blog(
            url=f"https://out-second-{index}.example/",
            normalized_url=f"https://out-second-{index}.example/",
            domain=f"out-second-{index}.example",
        )
        assert inserted is True
        outgoing_second_ids.append(outgoing_id)
        repository.add_edge(
            from_blog_id=outgoing_first_ids[0],
            to_blog_id=outgoing_id,
            link_url_raw=f"https://out-second-{index}.example/",
            link_text=f"Out second {index}",
        )

        incoming_id, inserted = repository.upsert_blog(
            url=f"https://in-second-{index}.example/",
            normalized_url=f"https://in-second-{index}.example/",
            domain=f"in-second-{index}.example",
        )
        assert inserted is True
        incoming_second_ids.append(incoming_id)
        repository.add_edge(
            from_blog_id=incoming_id,
            to_blog_id=incoming_first_ids[0],
            link_url_raw="https://in-first-0.example/",
            link_text=f"In second {index}",
        )

    detail = repository.get_blog_detail(focus_id)

    assert detail is not None
    outgoing_node_ids = {node["blog_id"] for node in detail["relation_graphs"]["outgoing"]["nodes"]}
    assert set(outgoing_first_ids).issubset(outgoing_node_ids)
    assert set(outgoing_second_ids).issubset(outgoing_node_ids)

    incoming_node_ids = {node["blog_id"] for node in detail["relation_graphs"]["incoming"]["nodes"]}
    assert set(incoming_first_ids).issubset(incoming_node_ids)
    assert set(incoming_second_ids).issubset(incoming_node_ids)


def test_repository_blog_detail_includes_discovery_path(tmp_path: Path) -> None:
    """Detail payloads should explain manual origins and crawled discovery chains."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    seed_id, inserted = repository.upsert_blog(
        url="https://seed.example/",
        normalized_url="https://seed.example/",
        domain="seed.example",
        accepted_by="seed",
        seed_source_path="seed.csv",
        seed_source_row=2,
    )
    assert inserted is True
    middle_id, inserted = repository.upsert_blog(
        url="https://middle.example/",
        normalized_url="https://middle.example/",
        domain="middle.example",
        accepted_by="rss",
    )
    assert inserted is True
    target_id, inserted = repository.upsert_blog(
        url="https://target.example/",
        normalized_url="https://target.example/",
        domain="target.example",
        accepted_by="model",
    )
    assert inserted is True
    first_raw = repository.create_raw_discovered_url(
        source_blog_id=seed_id,
        normalized_url="https://middle.example/",
        status="pending",
    )
    repository.update_raw_discovered_url_status(record_id=first_raw, status="success", accepted_by="rss")
    second_raw = repository.create_raw_discovered_url(
        source_blog_id=middle_id,
        normalized_url="https://target.example/",
        status="pending",
    )
    repository.update_raw_discovered_url_status(record_id=second_raw, status="success", accepted_by="model")

    seed_detail = repository.get_blog_detail(seed_id)
    target_detail = repository.get_blog_detail(target_id)

    assert seed_detail is not None
    assert seed_detail["discovery_path"]["mode"] == "manual"
    assert seed_detail["discovery_path"]["steps"][0]["accepted_by"] == "seed"
    assert target_detail is not None
    assert target_detail["discovery_path"]["mode"] == "crawled"
    assert [step["domain"] for step in target_detail["discovery_path"]["steps"]] == [
        "seed.example",
        "middle.example",
        "target.example",
    ]
    assert target_detail["discovery_path"]["steps"][0]["accepted_label"] == "种子导入"
    assert target_detail["discovery_path"]["steps"][1]["raw_source_blog_id"] == seed_id
    assert target_detail["discovery_path"]["steps"][2]["raw_source_blog_id"] == middle_id


def test_repository_blog_detail_discovery_path_keeps_full_history(tmp_path: Path) -> None:
    """Discovery paths should return every historical source step, even for long chains."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    blog_ids: list[int] = []
    domains = [f"chain-{index}.example" for index in range(15)]
    for index, domain in enumerate(domains):
        blog_id, inserted = repository.upsert_blog(
            url=f"https://{domain}/",
            normalized_url=f"https://{domain}/",
            domain=domain,
            accepted_by="seed" if index == 0 else "rss",
        )
        assert inserted is True
        blog_ids.append(blog_id)

    for source_id, target_domain in zip(blog_ids[:-1], domains[1:], strict=True):
        raw_id = repository.create_raw_discovered_url(
            source_blog_id=source_id,
            normalized_url=f"https://{target_domain}/",
            status="pending",
        )
        repository.update_raw_discovered_url_status(record_id=raw_id, status="success", accepted_by="rss")

    detail = repository.get_blog_detail(blog_ids[-1])

    assert detail is not None
    assert detail["discovery_path"]["truncated"] is False
    assert [step["domain"] for step in detail["discovery_path"]["steps"]] == domains


def test_repository_blog_detail_discovery_path_uses_incoming_edge_for_alias_raw_url(tmp_path: Path) -> None:
    """Discovery paths should follow incoming edges when raw URLs differ from canonical blog URLs."""
    repository = repository_module.build_repository(db_path=tmp_path / "db.sqlite")
    seed_id, inserted = repository.upsert_blog(
        url="https://seed.example/",
        normalized_url="https://seed.example/",
        domain="seed.example",
        accepted_by="seed",
    )
    assert inserted is True
    target_id, inserted = repository.upsert_blog(
        url="https://target.example/",
        normalized_url="https://target.example/",
        domain="target.example",
        accepted_by="rss",
    )
    assert inserted is True
    raw_id = repository.create_raw_discovered_url(
        source_blog_id=seed_id,
        normalized_url="https://blog.target.example/",
        status="pending",
    )
    repository.update_raw_discovered_url_status(record_id=raw_id, status="success", accepted_by="rss")
    repository.add_edge(
        from_blog_id=seed_id,
        to_blog_id=target_id,
        link_url_raw="https://blog.target.example/",
        link_text="Target",
    )

    detail = repository.get_blog_detail(target_id)

    assert detail is not None
    assert [step["domain"] for step in detail["discovery_path"]["steps"]] == [
        "seed.example",
        "target.example",
    ]
    assert detail["discovery_path"]["steps"][1]["raw_source_blog_id"] == seed_id
