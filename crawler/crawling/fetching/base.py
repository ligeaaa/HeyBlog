"""Fetch result shapes and fetcher protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class FetchResult:
    """Represent a successful HTTP fetch response."""

    url: str
    status_code: int
    text: str


@dataclass(slots=True)
class FetchAttempt:
    """Represent one batch fetch outcome keyed by the original request URL."""

    request_url: str
    result: FetchResult | None
    error_kind: str | None


class FetchingStrategy(Protocol):
    """Fetch one or more URLs for the crawler pipeline."""

    def fetch(self, url: str) -> FetchResult: ...

    def fetch_many(self, urls: list[str], *, max_concurrency: int) -> dict[str, FetchAttempt]: ...

