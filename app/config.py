"""Compatibility shim for shared configuration."""

from shared.config import DEFAULT_MAX_DEPTH
from shared.config import DEFAULT_MAX_NODES_PER_RUN
from shared.config import DEFAULT_MAX_PATH_PROBES_PER_BLOG
from shared.config import DEFAULT_REQUEST_TIMEOUT_SECONDS
from shared.config import DEFAULT_USER_AGENT
from shared.config import Settings

__all__ = [
    "DEFAULT_MAX_DEPTH",
    "DEFAULT_MAX_NODES_PER_RUN",
    "DEFAULT_MAX_PATH_PROBES_PER_BLOG",
    "DEFAULT_REQUEST_TIMEOUT_SECONDS",
    "DEFAULT_USER_AGENT",
    "Settings",
]
