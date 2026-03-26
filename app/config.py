from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_USER_AGENT = "HeyBlogBot/0.1 (+https://example.invalid/heyblog)"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_NODES_PER_RUN = 10
DEFAULT_MAX_DEPTH = 2
DEFAULT_MAX_OUTGOING_LINKS_PER_BLOG = 50


@dataclass(slots=True)
class Settings:
    db_path: Path
    seed_path: Path
    export_dir: Path
    user_agent: str = DEFAULT_USER_AGENT
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    max_nodes_per_run: int = DEFAULT_MAX_NODES_PER_RUN
    max_depth: int = DEFAULT_MAX_DEPTH
    max_outgoing_links_per_blog: int = DEFAULT_MAX_OUTGOING_LINKS_PER_BLOG

    @classmethod
    def from_env(cls) -> "Settings":
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
        )
