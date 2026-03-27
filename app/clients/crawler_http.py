"""HTTP client wrapper for the crawler service."""

from __future__ import annotations

from typing import Any

import httpx


class CrawlerHttpClient:
    """Trigger crawler actions over HTTP."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 60.0) -> None:
        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_seconds)

    def bootstrap(self) -> dict[str, Any]:
        response = self.client.post("/internal/crawl/bootstrap")
        response.raise_for_status()
        return response.json()

    def runtime_status(self) -> dict[str, Any]:
        response = self.client.get("/internal/runtime/status")
        response.raise_for_status()
        return response.json()

    def current(self) -> dict[str, Any]:
        response = self.client.get("/internal/runtime/current")
        response.raise_for_status()
        return response.json()

    def start(self) -> dict[str, Any]:
        response = self.client.post("/internal/runtime/start")
        response.raise_for_status()
        return response.json()

    def stop(self) -> dict[str, Any]:
        response = self.client.post("/internal/runtime/stop")
        response.raise_for_status()
        return response.json()

    def run(self, max_nodes: int | None = None) -> dict[str, Any]:
        response = self.client.post("/internal/crawl/run", params={"max_nodes": max_nodes})
        response.raise_for_status()
        return response.json()

    def run_batch(self, max_nodes: int) -> dict[str, Any]:
        response = self.client.post("/internal/runtime/run-batch", json={"max_nodes": max_nodes})
        response.raise_for_status()
        return response.json()
