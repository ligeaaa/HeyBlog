from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import build_router
from app.state import build_app_state


state = build_app_state()
app = FastAPI(title="HeyBlog", version="0.1.0")
app.include_router(build_router(state))


@app.get("/")
def root() -> dict:
    return {
        "name": "HeyBlog",
        "docs": "/docs",
        "status": "/api/status",
    }
