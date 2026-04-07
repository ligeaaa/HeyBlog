"""Unit tests for Fetcher single and batch request behavior."""

from __future__ import annotations

import asyncio

import httpx

from crawler.crawling.fetching.base import PageTooLargeError
from crawler.fetcher import Fetcher


class FakeStreamResponse:
    """Minimal streaming response stub for fetcher tests."""

    def __init__(
        self,
        url: str,
        *,
        status_code: int = 200,
        body: bytes = b"<html></html>",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.url = url
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}
        self.encoding = "utf-8"
        self.request = httpx.Request("GET", url)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            response = httpx.Response(
                self.status_code,
                request=self.request,
                content=self._body,
                headers=self.headers,
            )
            raise httpx.HTTPStatusError("http error", request=self.request, response=response)

    def iter_bytes(self):
        yield self._body

    async def aiter_bytes(self):
        yield self._body


class FakeStreamContext:
    """Sync context manager for one fake stream response."""

    def __init__(self, outcome: object) -> None:
        self.outcome = outcome

    def __enter__(self) -> FakeStreamResponse:
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class FakeAsyncStreamContext:
    """Async context manager for one fake stream response."""

    def __init__(self, outcome: object) -> None:
        self.outcome = outcome

    async def __aenter__(self) -> FakeStreamResponse:
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakeClient:
    """Minimal sync client stub for single-fetch tests."""

    responses: dict[str, object] = {}

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def stream(self, method: str, url: str, **kwargs: object) -> FakeStreamContext:
        return FakeStreamContext(type(self).responses[url])


class FakeAsyncClient:
    """Minimal async client stub for fetch_many tests."""

    created_kwargs: dict[str, object] | None = None
    responses: dict[str, object] = {}
    started: list[str] = []
    request_timeouts: list[float | None] = []
    max_inflight: int = 0
    inflight: int = 0

    def __init__(self, **kwargs: object) -> None:
        type(self).created_kwargs = kwargs

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def stream(self, method: str, url: str, **kwargs: object) -> FakeAsyncStreamContext:
        type(self).started.append(url)
        type(self).request_timeouts.append(kwargs.get("timeout") if "timeout" in kwargs else None)
        type(self).inflight += 1
        type(self).max_inflight = max(type(self).max_inflight, type(self).inflight)
        outcome = type(self).responses[url]

        class _Ctx(FakeAsyncStreamContext):
            async def __aenter__(self_nonlocal) -> FakeStreamResponse:
                try:
                    await asyncio.sleep(0.01)
                    return await super().__aenter__()
                finally:
                    FakeAsyncClient.inflight -= 1

        return _Ctx(outcome)


def reset_fake_async_client() -> None:
    """Reset global state between async client tests."""
    FakeAsyncClient.created_kwargs = None
    FakeAsyncClient.responses = {}
    FakeAsyncClient.started = []
    FakeAsyncClient.request_timeouts = []
    FakeAsyncClient.max_inflight = 0
    FakeAsyncClient.inflight = 0


def build_response(
    url: str,
    *,
    status_code: int = 200,
    text: str = "<html></html>",
    headers: dict[str, str] | None = None,
) -> FakeStreamResponse:
    """Build a streaming response bound to the request URL."""
    return FakeStreamResponse(
        url,
        status_code=status_code,
        body=text.encode("utf-8"),
        headers=headers,
    )


def test_fetch_many_respects_max_concurrency(monkeypatch) -> None:
    """Batch fetching should not exceed the configured concurrency limit."""
    reset_fake_async_client()
    monkeypatch.setattr("crawler.fetcher.httpx.AsyncClient", FakeAsyncClient)
    fetcher = Fetcher(user_agent="TestAgent/1.0", timeout_seconds=3.0, max_page_bytes=1024)
    FakeAsyncClient.responses = {
        f"https://example.com/{index}": build_response(f"https://example.com/{index}")
        for index in range(5)
    }

    results = fetcher.fetch_many(list(FakeAsyncClient.responses), max_concurrency=2)

    assert len(results) == 5
    assert FakeAsyncClient.max_inflight <= 2


def test_fetch_many_returns_partial_results_when_one_url_fails(monkeypatch) -> None:
    """One failed URL should not prevent the rest of the batch from succeeding."""
    reset_fake_async_client()
    monkeypatch.setattr("crawler.fetcher.httpx.AsyncClient", FakeAsyncClient)
    fetcher = Fetcher(user_agent="TestAgent/1.0", timeout_seconds=3.0, max_page_bytes=1024)
    FakeAsyncClient.responses = {
        "https://example.com/ok": build_response("https://example.com/ok"),
        "https://example.com/timeout": httpx.ReadTimeout(
            "timed out",
            request=httpx.Request("GET", "https://example.com/timeout"),
        ),
    }

    results = fetcher.fetch_many(list(FakeAsyncClient.responses), max_concurrency=2)

    assert results["https://example.com/ok"].result is not None
    assert results["https://example.com/ok"].error_kind is None
    assert results["https://example.com/timeout"].result is None
    assert results["https://example.com/timeout"].error_kind == "timeout"


def test_fetch_many_preserves_input_key_space(monkeypatch) -> None:
    """Batch results should stay keyed by the original request URL."""
    reset_fake_async_client()
    monkeypatch.setattr("crawler.fetcher.httpx.AsyncClient", FakeAsyncClient)
    fetcher = Fetcher(user_agent="TestAgent/1.0", timeout_seconds=3.0, max_page_bytes=1024)
    FakeAsyncClient.responses = {
        "https://example.com/source": build_response(
            "https://example.com/final",
            text="<html>redirected</html>",
        )
    }

    results = fetcher.fetch_many(["https://example.com/source"], max_concurrency=1)

    assert list(results) == ["https://example.com/source"]
    assert results["https://example.com/source"].request_url == "https://example.com/source"
    assert results["https://example.com/source"].result is not None
    assert results["https://example.com/source"].result.url == "https://example.com/final"


def test_fetch_many_reuses_fetch_contract_for_headers_timeout_and_redirects(monkeypatch) -> None:
    """Batch fetching should reuse the same HTTP contract as single fetches."""
    reset_fake_async_client()
    monkeypatch.setattr("crawler.fetcher.httpx.AsyncClient", FakeAsyncClient)
    fetcher = Fetcher(user_agent="TestAgent/1.0", timeout_seconds=7.5, max_page_bytes=1024)
    FakeAsyncClient.responses = {
        "https://example.com/ok": build_response("https://example.com/ok")
    }

    fetcher.fetch_many(["https://example.com/ok"], max_concurrency=1)

    assert FakeAsyncClient.created_kwargs == {
        "headers": {"User-Agent": "TestAgent/1.0"},
        "follow_redirects": True,
        "timeout": 7.5,
    }
    assert FakeAsyncClient.request_timeouts == [None]


def test_fetch_many_allows_per_call_timeout_override(monkeypatch) -> None:
    """Batch fetching should allow callers to tighten the timeout per crawl budget."""
    reset_fake_async_client()
    monkeypatch.setattr("crawler.fetcher.httpx.AsyncClient", FakeAsyncClient)
    fetcher = Fetcher(user_agent="TestAgent/1.0", timeout_seconds=7.5, max_page_bytes=1024)
    FakeAsyncClient.responses = {
        "https://example.com/ok": build_response("https://example.com/ok")
    }

    fetcher.fetch_many(["https://example.com/ok"], max_concurrency=1, timeout_seconds=2.25)

    assert FakeAsyncClient.request_timeouts == [2.25]


def test_fetch_many_classifies_failures_by_error_kind(monkeypatch) -> None:
    """Batch fetching should expose stable error kinds for expected failure classes."""
    reset_fake_async_client()
    monkeypatch.setattr("crawler.fetcher.httpx.AsyncClient", FakeAsyncClient)
    fetcher = Fetcher(user_agent="TestAgent/1.0", timeout_seconds=3.0, max_page_bytes=1024)
    failing_response = build_response("https://example.com/http-error", status_code=503)
    FakeAsyncClient.responses = {
        "https://example.com/request-error": httpx.RequestError(
            "boom",
            request=httpx.Request("GET", "https://example.com/request-error"),
        ),
        "https://example.com/http-error": failing_response,
        "https://example.com/timeout": httpx.ReadTimeout(
            "timed out",
            request=httpx.Request("GET", "https://example.com/timeout"),
        ),
    }

    results = fetcher.fetch_many(list(FakeAsyncClient.responses), max_concurrency=3)

    assert results["https://example.com/request-error"].error_kind == "request_error"
    assert results["https://example.com/http-error"].error_kind == "http_status"
    assert results["https://example.com/timeout"].error_kind == "timeout"


def test_fetch_many_classifies_invalid_url_without_failing_the_batch(monkeypatch) -> None:
    """Malformed URLs should be downgraded to a failed attempt instead of crashing the batch."""
    reset_fake_async_client()
    monkeypatch.setattr("crawler.fetcher.httpx.AsyncClient", FakeAsyncClient)
    fetcher = Fetcher(user_agent="TestAgent/1.0", timeout_seconds=3.0, max_page_bytes=1024)
    FakeAsyncClient.responses = {
        "https://example.com/ok": build_response("https://example.com/ok"),
        "bad://url": httpx.InvalidURL("invalid url"),
    }

    results = fetcher.fetch_many(list(FakeAsyncClient.responses), max_concurrency=2)

    assert results["https://example.com/ok"].result is not None
    assert results["bad://url"].result is None
    assert results["bad://url"].error_kind == "invalid_url"


def test_fetch_many_requires_unique_request_urls() -> None:
    """Duplicate request URLs should be rejected explicitly instead of being silently collapsed."""
    fetcher = Fetcher(user_agent="TestAgent/1.0", timeout_seconds=3.0, max_page_bytes=1024)

    try:
        fetcher.fetch_many(["https://example.com/a", "https://example.com/a"], max_concurrency=2)
    except ValueError as exc:
        assert "unique request URLs" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("fetch_many should reject duplicate URLs")


def test_fetch_many_sync_wrapper_rejects_running_event_loop(monkeypatch) -> None:
    """The sync wrapper should fail clearly when called from an existing event loop."""
    reset_fake_async_client()
    monkeypatch.setattr("crawler.fetcher.httpx.AsyncClient", FakeAsyncClient)
    fetcher = Fetcher(user_agent="TestAgent/1.0", timeout_seconds=3.0, max_page_bytes=1024)
    FakeAsyncClient.responses = {
        "https://example.com/ok": build_response("https://example.com/ok")
    }

    async def run() -> None:
        try:
            fetcher.fetch_many(["https://example.com/ok"], max_concurrency=1)
        except RuntimeError as exc:
            assert "running asyncio event loop" in str(exc)
        else:  # pragma: no cover - defensive
            raise AssertionError("fetch_many should reject calls from a running event loop")

    asyncio.run(run())


def test_fetch_many_async_supports_callers_with_running_event_loop(monkeypatch) -> None:
    """Async callers should be able to use the public async batch-fetch API directly."""
    reset_fake_async_client()
    monkeypatch.setattr("crawler.fetcher.httpx.AsyncClient", FakeAsyncClient)
    fetcher = Fetcher(user_agent="TestAgent/1.0", timeout_seconds=3.0, max_page_bytes=1024)
    FakeAsyncClient.responses = {
        "https://example.com/ok": build_response("https://example.com/ok")
    }

    async def run() -> None:
        results = await fetcher.fetch_many_async(["https://example.com/ok"], max_concurrency=1)
        assert results["https://example.com/ok"].result is not None
        assert results["https://example.com/ok"].error_kind is None

    asyncio.run(run())


def test_fetch_rejects_large_page_from_content_length(monkeypatch) -> None:
    """Single fetches should reject oversized pages before reading the full body."""
    FakeClient.responses = {
        "https://example.com/huge": build_response(
            "https://example.com/huge",
            text="x" * 32,
            headers={"content-length": "32"},
        )
    }
    monkeypatch.setattr("crawler.crawling.fetching.httpx_fetcher.httpx.Client", FakeClient)
    fetcher = Fetcher(user_agent="TestAgent/1.0", timeout_seconds=3.0, max_page_bytes=16)

    try:
        fetcher.fetch("https://example.com/huge")
    except PageTooLargeError as exc:
        assert "max size limit" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("fetch should reject oversized pages")


def test_fetch_many_classifies_page_too_large(monkeypatch) -> None:
    """Batch fetching should downgrade oversized pages to a stable error kind."""
    reset_fake_async_client()
    monkeypatch.setattr("crawler.fetcher.httpx.AsyncClient", FakeAsyncClient)
    fetcher = Fetcher(user_agent="TestAgent/1.0", timeout_seconds=3.0, max_page_bytes=16)
    FakeAsyncClient.responses = {
        "https://example.com/huge": build_response(
            "https://example.com/huge",
            text="x" * 32,
            headers={"content-length": "32"},
        )
    }

    results = fetcher.fetch_many(["https://example.com/huge"], max_concurrency=1)

    assert results["https://example.com/huge"].result is None
    assert results["https://example.com/huge"].error_kind == "page_too_large"
