"""Unit tests for preprocessing-side page fetching behavior."""

from __future__ import annotations

from dataclasses import dataclass

from agent.config import AgentSettings
from data_preprocessing.fetching import PageFetcher
from crawler.crawling.fetching.base import FetchAttempt
from crawler.crawling.fetching.base import FetchResult


@dataclass
class StubFetcher:
    responses: list[dict[str, FetchAttempt]]

    def __post_init__(self) -> None:
        self.calls: list[list[str]] = []

    def fetch_many(self, urls: list[str], *, max_concurrency: int, timeout_seconds: float | None = None):
        self.calls.append(list(urls))
        return self.responses.pop(0)


def _settings() -> AgentSettings:
    return AgentSettings(
        default_provider="deepseek",
        default_model="deepseek-chat",
        provider_configs={"deepseek": object()},  # type: ignore[arg-type]
    )


def test_page_fetcher_retries_timeout_and_preserves_final_url() -> None:
    request_url = "https://example.com"
    stub = StubFetcher(
        responses=[
            {
                request_url: FetchAttempt(
                    request_url=request_url,
                    result=None,
                    error_kind="timeout",
                )
            },
            {
                request_url: FetchAttempt(
                    request_url=request_url,
                    result=FetchResult(
                        url="https://example.com/final",
                        status_code=200,
                        text="<html><body>Hello</body></html>",
                    ),
                    error_kind=None,
                )
            },
        ]
    )

    outcome = PageFetcher(_settings(), fetcher=stub).fetch_many([request_url])[request_url]

    assert stub.calls == [[request_url], [request_url]]
    assert outcome.fetch_status == "success"
    assert outcome.final_url == "https://example.com/final"
    assert outcome.used_page_content is True


def test_page_fetcher_marks_failed_fetches_with_null_final_url() -> None:
    request_url = "https://example.com"
    stub = StubFetcher(
        responses=[
            {
                request_url: FetchAttempt(
                    request_url=request_url,
                    result=None,
                    error_kind="http_status",
                )
            }
        ]
    )

    outcome = PageFetcher(_settings(), fetcher=stub).fetch_many([request_url])[request_url]

    assert outcome.fetch_status == "failed"
    assert outcome.error_kind == "http_status"
    assert outcome.final_url is None
    assert outcome.used_page_content is False
