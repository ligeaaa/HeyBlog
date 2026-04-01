"""Define runtime settings and environment-based loading."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_USER_AGENT = "HeyBlogBot/0.1 (+https://example.invalid/heyblog)"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_NODES_PER_RUN = 10
DEFAULT_MAX_PATH_PROBES_PER_BLOG = 50
DEFAULT_CANDIDATE_PAGE_FETCH_CONCURRENCY = 4


def _parse_csv_env(name: str) -> tuple[str, ...]:
    """Parse comma-separated environment values into a tuple."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


@dataclass(slots=True)
class Settings:
    """Configuration values for crawler, storage, and exports."""

    db_path: Path
    seed_path: Path
    export_dir: Path
    db_dsn: str | None = None
    persistence_base_url: str = "http://127.0.0.1:8030"
    crawler_base_url: str = "http://127.0.0.1:8010"
    search_base_url: str = "http://127.0.0.1:8020"
    backend_base_url: str = "http://127.0.0.1:8000"
    search_cache_dir: Path | None = None
    user_agent: str = DEFAULT_USER_AGENT
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    max_nodes_per_run: int = DEFAULT_MAX_NODES_PER_RUN
    max_path_probes_per_blog: int = DEFAULT_MAX_PATH_PROBES_PER_BLOG
    candidate_page_fetch_concurrency: int = DEFAULT_CANDIDATE_PAGE_FETCH_CONCURRENCY
    friend_link_domain_blocklist: tuple[str, ...] = ()
    friend_link_tld_blocklist: tuple[str, ...] = ()
    friend_link_exact_url_blocklist: tuple[str, ...] = ()
    friend_link_prefix_blocklist: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from environment variables with sensible defaults."""
        root = Path.cwd()
        db_path = Path(os.getenv("HEYBLOG_DB_PATH", root / "data" / "heyblog.sqlite"))
        seed_path = Path(os.getenv("HEYBLOG_SEED_PATH", root / "seed.csv"))
        export_dir = Path(os.getenv("HEYBLOG_EXPORT_DIR", root / "data" / "exports"))
        return cls(
            db_path=db_path,
            db_dsn=os.getenv("HEYBLOG_DB_DSN"),
            seed_path=seed_path,
            export_dir=export_dir,
            persistence_base_url=os.getenv("HEYBLOG_PERSISTENCE_BASE_URL", "http://persistence-api:8030"),
            crawler_base_url=os.getenv("HEYBLOG_CRAWLER_BASE_URL", "http://crawler:8010"),
            search_base_url=os.getenv("HEYBLOG_SEARCH_BASE_URL", "http://search:8020"),
            backend_base_url=os.getenv("HEYBLOG_BACKEND_BASE_URL", "http://backend:8000"),
            search_cache_dir=Path(os.getenv("HEYBLOG_SEARCH_CACHE_DIR", root / "data" / "search-cache")),
            user_agent=os.getenv("HEYBLOG_USER_AGENT", DEFAULT_USER_AGENT),
            request_timeout_seconds=float(
                os.getenv(
                    "HEYBLOG_REQUEST_TIMEOUT_SECONDS",
                    str(DEFAULT_REQUEST_TIMEOUT_SECONDS),
                )
            ),
            max_nodes_per_run=int(
                os.getenv("HEYBLOG_MAX_NODES_PER_RUN", str(DEFAULT_MAX_NODES_PER_RUN))
            ),
            max_path_probes_per_blog=int(
                os.getenv(
                    "HEYBLOG_MAX_PATH_PROBES_PER_BLOG",
                    str(DEFAULT_MAX_PATH_PROBES_PER_BLOG),
                )
            ),
            candidate_page_fetch_concurrency=max(
                1,
                int(
                    os.getenv(
                        "HEYBLOG_CANDIDATE_PAGE_FETCH_CONCURRENCY",
                        str(DEFAULT_CANDIDATE_PAGE_FETCH_CONCURRENCY),
                    )
                ),
            ),
            friend_link_domain_blocklist=_parse_csv_env("HEYBLOG_FRIEND_LINK_DOMAIN_BLOCKLIST"),
            friend_link_tld_blocklist=_parse_csv_env("HEYBLOG_FRIEND_LINK_TLD_BLOCKLIST"),
            friend_link_exact_url_blocklist=_parse_csv_env("HEYBLOG_FRIEND_LINK_EXACT_URL_BLOCKLIST"),
            friend_link_prefix_blocklist=_parse_csv_env("HEYBLOG_FRIEND_LINK_PREFIX_BLOCKLIST"),
        )
