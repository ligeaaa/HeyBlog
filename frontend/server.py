"""Frontend service serving the operator panel and proxying API calls."""

from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi import HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from shared.config import Settings


FRONTEND_DIST_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"
FRONTEND_ASSETS_DIR = FRONTEND_DIST_DIR / "assets"
FALLBACK_HTML = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>HeyBlog Frontend Build Missing</title>
  </head>
  <body>
    <main style="max-width: 720px; margin: 48px auto; font-family: sans-serif;">
      <h1>Frontend build is not ready</h1>
      <p>Run <code>npm install</code> and <code>npm run build</code> inside <code>frontend/</code>.</p>
    </main>
  </body>
</html>
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the frontend app."""
    resolved = settings or Settings.from_env()
    app = FastAPI(title="HeyBlog Frontend Service", version="0.1.0")
    app.state.backend_base_url = resolved.backend_base_url.rstrip("/")
    if FRONTEND_ASSETS_DIR.exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_ASSETS_DIR), name="assets")

    @app.get("/")
    def root() -> RedirectResponse:
        return RedirectResponse(url="/stats", status_code=307)

    @app.get("/internal/health")
    def health() -> dict[str, str]:
        try:
            httpx.get(f"{app.state.backend_base_url}/api/status", timeout=10.0).raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail="backend_unavailable") from exc
        return {"status": "ok"}

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

    @app.get("/{path:path}", include_in_schema=False)
    def app_entry(path: str) -> HTMLResponse:
        if FRONTEND_DIST_DIR.exists():
            return HTMLResponse((FRONTEND_DIST_DIR / "index.html").read_text(encoding="utf-8"))
        return HTMLResponse(FALLBACK_HTML)

    return app


app = create_app()
