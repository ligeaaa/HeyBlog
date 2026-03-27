"""Compatibility shim for frontend service entrypoint."""

from frontend.server import FALLBACK_HTML
from frontend.server import FRONTEND_ASSETS_DIR
from frontend.server import FRONTEND_DIST_DIR
from frontend.server import app
from frontend.server import create_app

__all__ = [
    "FALLBACK_HTML",
    "FRONTEND_ASSETS_DIR",
    "FRONTEND_DIST_DIR",
    "app",
    "create_app",
]
