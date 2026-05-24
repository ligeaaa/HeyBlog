"""HTTP client wrapper for the search service."""

from __future__ import annotations

from typing import Any

import httpx

from shared.http_clients.context import context_header_kwargs


class SearchHttpClient:
    """Query the search service over HTTP."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 10.0) -> None:
        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_seconds)

    def search(self, query: str, *, kind: str = "all", limit: int = 10) -> dict[str, Any]:
        response = self.client.get(
            "/internal/search",
            params={"q": query, "kind": kind, "limit": limit},
            **context_header_kwargs(),
        )
        response.raise_for_status()
        return response.json()

    def reindex(self) -> dict[str, Any]:
        response = self.client.post("/internal/search/reindex", **context_header_kwargs())
        response.raise_for_status()
        return response.json()
