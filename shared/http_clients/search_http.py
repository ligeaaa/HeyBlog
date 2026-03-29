"""HTTP client wrapper for the search service."""

from __future__ import annotations

from typing import Any

import httpx


class SearchHttpClient:
    """Query the search service over HTTP."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 10.0) -> None:
        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_seconds)

    def search(self, query: str) -> dict[str, Any]:
        response = self.client.get("/internal/search", params={"q": query})
        response.raise_for_status()
        return response.json()

    def reindex(self) -> dict[str, Any]:
        response = self.client.post("/internal/search/reindex")
        response.raise_for_status()
        return response.json()

