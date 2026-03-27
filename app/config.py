"""Define runtime settings and environment-based loading."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_USER_AGENT = "HeyBlogBot/0.1 (+https://example.invalid/heyblog)"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_NODES_PER_RUN = 10
DEFAULT_MAX_DEPTH = 2
DEFAULT_MAX_OUTGOING_LINKS_PER_BLOG = 50
DEFAULT_MAX_CANDIDATE_PAGES_PER_BLOG = 5
DEFAULT_MAX_PATH_PROBES_PER_BLOG = 4
DEFAULT_FRIEND_LINK_PAGE_SCORE_THRESHOLD = 2.5
DEFAULT_FRIEND_LINK_SECTION_SCORE_THRESHOLD = 2.5
DEFAULT_FRIEND_LINK_AMBIGUITY_THRESHOLD = 3.0
DEFAULT_CLASSIFIER_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_LINKS_FOR_MCP_REVIEW = 10


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
    user_agent: str = DEFAULT_USER_AGENT
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    max_nodes_per_run: int = DEFAULT_MAX_NODES_PER_RUN
    max_depth: int = DEFAULT_MAX_DEPTH
    max_outgoing_links_per_blog: int = DEFAULT_MAX_OUTGOING_LINKS_PER_BLOG
    max_candidate_pages_per_blog: int = DEFAULT_MAX_CANDIDATE_PAGES_PER_BLOG
    max_path_probes_per_blog: int = DEFAULT_MAX_PATH_PROBES_PER_BLOG
    friend_link_page_score_threshold: float = DEFAULT_FRIEND_LINK_PAGE_SCORE_THRESHOLD
    friend_link_section_score_threshold: float = DEFAULT_FRIEND_LINK_SECTION_SCORE_THRESHOLD
    friend_link_ambiguity_threshold: float = DEFAULT_FRIEND_LINK_AMBIGUITY_THRESHOLD
    classifier_timeout_seconds: float = DEFAULT_CLASSIFIER_TIMEOUT_SECONDS
    max_links_for_mcp_review: int = DEFAULT_MAX_LINKS_FOR_MCP_REVIEW
    enable_mcp_classifier: bool = False
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
            seed_path=seed_path,
            export_dir=export_dir,
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
            max_depth=int(os.getenv("HEYBLOG_MAX_DEPTH", str(DEFAULT_MAX_DEPTH))),
            max_outgoing_links_per_blog=int(
                os.getenv(
                    "HEYBLOG_MAX_OUTGOING_LINKS_PER_BLOG",
                    str(DEFAULT_MAX_OUTGOING_LINKS_PER_BLOG),
                )
            ),
            max_candidate_pages_per_blog=int(
                os.getenv(
                    "HEYBLOG_MAX_CANDIDATE_PAGES_PER_BLOG",
                    str(DEFAULT_MAX_CANDIDATE_PAGES_PER_BLOG),
                )
            ),
            max_path_probes_per_blog=int(
                os.getenv(
                    "HEYBLOG_MAX_PATH_PROBES_PER_BLOG",
                    str(DEFAULT_MAX_PATH_PROBES_PER_BLOG),
                )
            ),
            friend_link_page_score_threshold=float(
                os.getenv(
                    "HEYBLOG_FRIEND_LINK_PAGE_SCORE_THRESHOLD",
                    str(DEFAULT_FRIEND_LINK_PAGE_SCORE_THRESHOLD),
                )
            ),
            friend_link_section_score_threshold=float(
                os.getenv(
                    "HEYBLOG_FRIEND_LINK_SECTION_SCORE_THRESHOLD",
                    str(DEFAULT_FRIEND_LINK_SECTION_SCORE_THRESHOLD),
                )
            ),
            friend_link_ambiguity_threshold=float(
                os.getenv(
                    "HEYBLOG_FRIEND_LINK_AMBIGUITY_THRESHOLD",
                    str(DEFAULT_FRIEND_LINK_AMBIGUITY_THRESHOLD),
                )
            ),
            classifier_timeout_seconds=float(
                os.getenv(
                    "HEYBLOG_CLASSIFIER_TIMEOUT_SECONDS",
                    str(DEFAULT_CLASSIFIER_TIMEOUT_SECONDS),
                )
            ),
            max_links_for_mcp_review=int(
                os.getenv(
                    "HEYBLOG_MAX_LINKS_FOR_MCP_REVIEW",
                    str(DEFAULT_MAX_LINKS_FOR_MCP_REVIEW),
                )
            ),
            enable_mcp_classifier=(
                os.getenv("HEYBLOG_ENABLE_MCP_CLASSIFIER", "0").strip().lower()
                in {"1", "true", "yes", "on"}
            ),
            friend_link_domain_blocklist=_parse_csv_env("HEYBLOG_FRIEND_LINK_DOMAIN_BLOCKLIST"),
            friend_link_tld_blocklist=_parse_csv_env("HEYBLOG_FRIEND_LINK_TLD_BLOCKLIST"),
            friend_link_exact_url_blocklist=_parse_csv_env("HEYBLOG_FRIEND_LINK_EXACT_URL_BLOCKLIST"),
            friend_link_prefix_blocklist=_parse_csv_env("HEYBLOG_FRIEND_LINK_PREFIX_BLOCKLIST"),
        )
