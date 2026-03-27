"""Compatibility shim for persistence API entrypoint."""

from persistence_api.main import AddEdgeRequest
from persistence_api.main import AddLogRequest
from persistence_api.main import BlogResultRequest
from persistence_api.main import PersistenceState
from persistence_api.main import UpsertBlogRequest
from persistence_api.main import app
from persistence_api.main import build_persistence_state
from persistence_api.main import create_app

__all__ = [
    "AddEdgeRequest",
    "AddLogRequest",
    "BlogResultRequest",
    "PersistenceState",
    "UpsertBlogRequest",
    "app",
    "build_persistence_state",
    "create_app",
]
