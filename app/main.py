"""Build and configure the FastAPI application for HeyBlog."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import build_router
from app.state import AppState
from app.state import build_app_state
from app.ui.panel import panel_response


STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(state: AppState | None = None) -> FastAPI:
    """Create the FastAPI application with API and panel routes."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Initialize shared state once at startup."""
        if not hasattr(app.state, "heyblog_state"):
            app.state.heyblog_state = build_app_state()
        yield

    app = FastAPI(title="HeyBlog", version="0.1.0", lifespan=lifespan)

    if state is not None:
        app.state.heyblog_state = state

    def get_state() -> AppState:
        """Return the request-scoped shared state object."""
        return app.state.heyblog_state

    app.include_router(build_router(get_state))
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def root() -> dict[str, str]:
        """Expose basic service metadata for quick health checks."""
        return {
            "name": "HeyBlog",
            "docs": "/docs",
            "status": "/api/status",
            "panel": "/panel",
        }

    @app.get("/panel")
    def panel() -> HTMLResponse:
        """Serve the embedded operator panel page."""
        return panel_response()

    return app


app = create_app()
