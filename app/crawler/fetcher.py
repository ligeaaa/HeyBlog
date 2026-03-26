from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(slots=True)
class FetchResult:
    url: str
    status_code: int
    text: str


class Fetcher:
    def __init__(self, *, user_agent: str, timeout_seconds: float) -> None:
        self.client = httpx.Client(
            headers={"User-Agent": user_agent},
            follow_redirects=True,
            timeout=timeout_seconds,
        )

    def fetch(self, url: str) -> FetchResult:
        response = self.client.get(url)
        response.raise_for_status()
        return FetchResult(url=str(response.url), status_code=response.status_code, text=response.text)
