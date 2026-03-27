"""Frontend service serving the operator panel and proxying API calls."""

from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings
from app.ui.panel import panel_response


STATIC_DIR = Path(__file__).resolve().parents[2] / "app" / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the frontend app."""
    resolved = settings or Settings.from_env()
    app = FastAPI(title="HeyBlog Frontend Service", version="0.1.0")
    app.state.backend_base_url = resolved.backend_base_url.rstrip("/")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def root() -> RedirectResponse:
        return RedirectResponse(url="/panel", status_code=307)

    @app.get("/panel")
    def panel() -> HTMLResponse:
        return panel_response()

    @app.api_route("/api/{path:path}", methods=["GET", "POST"])
    async def proxy_api(path: str, request: Request) -> Response:
        target = f"{app.state.backend_base_url}/api/{path}"
        async with httpx.AsyncClient(timeout=60.0) as client:
            forwarded = await client.request(
                request.method,
                target,
                params=request.query_params,
                content=await request.body(),
                headers={"content-type": request.headers.get("content-type", "application/json")},
            )
        return Response(
            content=forwarded.content,
            status_code=forwarded.status_code,
            media_type=forwarded.headers.get("content-type"),
        )

    return app


app = create_app()
