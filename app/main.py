from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import build_router
from app.state import AppState
from app.state import build_app_state
from app.ui.panel import panel_response


STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(state: AppState | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not hasattr(app.state, "heyblog_state"):
            app.state.heyblog_state = build_app_state()
        yield

    app = FastAPI(title="HeyBlog", version="0.1.0", lifespan=lifespan)

    if state is not None:
        app.state.heyblog_state = state

    def get_state() -> AppState:
        return app.state.heyblog_state

    app.include_router(build_router(get_state))
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def root() -> dict:
        return {
            "name": "HeyBlog",
            "docs": "/docs",
            "status": "/api/status",
            "panel": "/panel",
        }

    @app.get("/panel")
    def panel():
        return panel_response()

    return app


app = create_app()
