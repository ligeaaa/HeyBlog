"""Compatibility shim for backend service entrypoint."""

from backend.main import BackendState
from backend.main import RunBatchRequest
from backend.main import app
from backend.main import build_backend_state
from backend.main import create_app

__all__ = [
    "BackendState",
    "RunBatchRequest",
    "app",
    "build_backend_state",
    "create_app",
]
