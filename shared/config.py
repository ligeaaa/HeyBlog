"""Define runtime settings and environment-based loading."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_USER_AGENT = "HeyBlogBot/0.1 (+https://example.invalid/heyblog)"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 10.0
DEFAULT_BLOG_CRAWL_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_NODES_PER_RUN = 10
DEFAULT_MAX_PATH_PROBES_PER_BLOG = 50
DEFAULT_CANDIDATE_PAGE_FETCH_CONCURRENCY = 4
DEFAULT_RUNTIME_WORKER_COUNT = 3
DEFAULT_PRIORITY_SEED_NORMAL_QUEUE_SLOTS = 2
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "heyblog.sqlite"
DEFAULT_SEED_PATH = PROJECT_ROOT / "seed.csv"
DEFAULT_EXPORT_DIR = PROJECT_ROOT / "data" / "exports"
DEFAULT_SEARCH_CACHE_DIR = PROJECT_ROOT / "data" / "search-cache"
DEFAULT_PERSISTENCE_BASE_URL = "http://127.0.0.1:8030"
DEFAULT_CRAWLER_BASE_URL = "http://127.0.0.1:8010"
DEFAULT_SEARCH_BASE_URL = "http://127.0.0.1:8020"
DEFAULT_BACKEND_BASE_URL = "http://127.0.0.1:8000"
_ENV_LOADED = False


def _strip_wrapping_quotes(value: str) -> str:
    """Remove matching single or double quotes around a value."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from the project .env file once without overriding the shell."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    env_path = path or (PROJECT_ROOT / ".env")
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue
            os.environ.setdefault(key, _strip_wrapping_quotes(value.strip()))

    _ENV_LOADED = True


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
    blog_crawl_timeout_seconds: float = DEFAULT_BLOG_CRAWL_TIMEOUT_SECONDS
    max_nodes_per_run: int = DEFAULT_MAX_NODES_PER_RUN
    max_path_probes_per_blog: int = DEFAULT_MAX_PATH_PROBES_PER_BLOG
    candidate_page_fetch_concurrency: int = DEFAULT_CANDIDATE_PAGE_FETCH_CONCURRENCY
    runtime_worker_count: int = DEFAULT_RUNTIME_WORKER_COUNT
    priority_seed_normal_queue_slots: int = DEFAULT_PRIORITY_SEED_NORMAL_QUEUE_SLOTS
    friend_link_domain_blocklist: tuple[str, ...] = ()
    friend_link_tld_blocklist: tuple[str, ...] = ()
    friend_link_exact_url_blocklist: tuple[str, ...] = ()
    friend_link_prefix_blocklist: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from environment variables with sensible defaults."""
        _load_dotenv()
        db_path = Path(os.getenv("HEYBLOG_DB_PATH", str(DEFAULT_DB_PATH)))
        seed_path = Path(os.getenv("HEYBLOG_SEED_PATH", str(DEFAULT_SEED_PATH)))
        export_dir = Path(os.getenv("HEYBLOG_EXPORT_DIR", str(DEFAULT_EXPORT_DIR)))
        return cls(
            db_path=db_path,
            db_dsn=os.getenv("HEYBLOG_DB_DSN"),
            seed_path=seed_path,
            export_dir=export_dir,
            persistence_base_url=os.getenv("HEYBLOG_PERSISTENCE_BASE_URL", DEFAULT_PERSISTENCE_BASE_URL),
            crawler_base_url=os.getenv("HEYBLOG_CRAWLER_BASE_URL", DEFAULT_CRAWLER_BASE_URL),
            search_base_url=os.getenv("HEYBLOG_SEARCH_BASE_URL", DEFAULT_SEARCH_BASE_URL),
            backend_base_url=os.getenv("HEYBLOG_BACKEND_BASE_URL", DEFAULT_BACKEND_BASE_URL),
            search_cache_dir=Path(os.getenv("HEYBLOG_SEARCH_CACHE_DIR", str(DEFAULT_SEARCH_CACHE_DIR))),
            user_agent=os.getenv("HEYBLOG_USER_AGENT", DEFAULT_USER_AGENT),
            request_timeout_seconds=float(
                os.getenv(
                    "HEYBLOG_REQUEST_TIMEOUT_SECONDS",
                    str(DEFAULT_REQUEST_TIMEOUT_SECONDS),
                )
            ),
            blog_crawl_timeout_seconds=max(
                0.001,
                float(
                    os.getenv(
                        "HEYBLOG_BLOG_CRAWL_TIMEOUT_SECONDS",
                        str(DEFAULT_BLOG_CRAWL_TIMEOUT_SECONDS),
                    )
                ),
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
            runtime_worker_count=max(
                1,
                int(
                    os.getenv(
                        "HEYBLOG_RUNTIME_WORKER_COUNT",
                        str(DEFAULT_RUNTIME_WORKER_COUNT),
                    )
                ),
            ),
            priority_seed_normal_queue_slots=max(
                1,
                int(
                    os.getenv(
                        "HEYBLOG_PRIORITY_SEED_NORMAL_QUEUE_SLOTS",
                        str(DEFAULT_PRIORITY_SEED_NORMAL_QUEUE_SLOTS),
                    )
                ),
            ),
            friend_link_domain_blocklist=_parse_csv_env("HEYBLOG_FRIEND_LINK_DOMAIN_BLOCKLIST"),
            friend_link_tld_blocklist=_parse_csv_env("HEYBLOG_FRIEND_LINK_TLD_BLOCKLIST"),
            friend_link_exact_url_blocklist=_parse_csv_env("HEYBLOG_FRIEND_LINK_EXACT_URL_BLOCKLIST"),
            friend_link_prefix_blocklist=_parse_csv_env("HEYBLOG_FRIEND_LINK_PREFIX_BLOCKLIST"),
        )
