"""LiteLLM-backed single-task blog classifier."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from agent.config import AgentSettings
from agent.schema import BlogJudgeInput
from agent.schema import BlogJudgeResult
from agent.schema import ProviderSelection


@dataclass(slots=True)
class ClassifierTask:
    """Bundle the row index and classifier input for async execution.

    Args:
        index: Original row position so async results can be restored in order.
        evidence: Structured evidence passed to the classifier.
    """

    index: int
    evidence: BlogJudgeInput


class BlogClassifier:
    """Classify whether a URL/title pair represents a personal blog.

    Args:
        settings: Agent runtime settings including provider limits.
        provider: Concrete provider/model selection used for calls.
        completion_fn: Optional injected completion function for tests.
    """

    def __init__(
        self,
        settings: AgentSettings,
        provider: ProviderSelection,
        *,
        completion_fn: Callable[..., Any] | None = None,
    ) -> None:
        self._settings = settings
        self._provider = provider
        self._completion_fn = completion_fn

    async def classify_many(
        self,
        inputs: Sequence[BlogJudgeInput],
        *,
        progress_callback: Callable[[], None] | None = None,
    ) -> list[BlogJudgeResult]:
        """Classify many rows with bounded concurrency and rate limits.

        Args:
            inputs: Ordered classifier inputs to evaluate.
            progress_callback: Optional callback invoked once per completed
                classification task so callers can update progress displays.

        Returns:
            Ordered classifier results aligned to the original inputs.
        """
        semaphore = asyncio.Semaphore(self._settings.classification_max_concurrency)
        limiter = _RateLimiter(self._settings.classification_requests_per_minute)
        tasks = [ClassifierTask(index=index, evidence=evidence) for index, evidence in enumerate(inputs)]

        async def _run(task: ClassifierTask) -> tuple[int, BlogJudgeResult]:
            async with semaphore:
                await limiter.acquire()
                result = await asyncio.to_thread(self.classify_one, task.evidence)
                if progress_callback is not None:
                    progress_callback()
                return task.index, result

        ordered: list[BlogJudgeResult | None] = [None] * len(tasks)
        for index, result in await asyncio.gather(*(_run(task) for task in tasks)):
            ordered[index] = result
        return [result for result in ordered if result is not None]

    def classify_one(self, evidence: BlogJudgeInput) -> BlogJudgeResult:
        """Classify one row using the configured LiteLLM provider.

        Args:
            evidence: URL/title/page-text evidence bundle for one sample.

        Returns:
            A structured classification result. On SDK or parsing failure, the
            result contains ``pred_label=None`` and ``llm_status='failed'``.
        """
        prompt = _build_messages(evidence)
        try:
            completion = self._call_completion(
                model=self._provider.model,
                custom_llm_provider=self._provider.provider,
                messages=prompt,
                api_key=self._provider.api_key,
                api_base=self._provider.base_url,
                temperature=0,
            )
            raw_text = _extract_content(completion)
            payload = _parse_json_payload(raw_text)
            pred_label = payload.get("pred_label")
            reason = str(payload.get("reason", "")).strip() or "classifier returned no reason"
            if pred_label not in {"blog", "non_blog"}:
                raise ValueError(f"unexpected pred_label: {pred_label!r}")
            return BlogJudgeResult(
                pred_label=pred_label,
                reason=reason,
                provider=self._provider.provider,
                model=self._provider.model,
                llm_status="success",
                raw_response=raw_text,
            )
        except Exception as exc:  # noqa: BLE001 - eval must persist the failure instead of crashing.
            return BlogJudgeResult(
                pred_label=None,
                reason=f"classification_failed: {exc}",
                provider=self._provider.provider,
                model=self._provider.model,
                llm_status="failed",
                raw_response=None,
            )

    def _call_completion(self, **kwargs: Any) -> Any:
        """Call LiteLLM or the injected completion function.

        Args:
            **kwargs: Completion arguments forwarded to the underlying client.

        Returns:
            The raw completion response object.
        """
        if self._completion_fn is not None:
            return self._completion_fn(**kwargs)
        try:
            from litellm import completion
        except ImportError as exc:  # pragma: no cover - exercised only when the optional extra is missing.
            raise RuntimeError("litellm is not installed; run `pip install -e '.[agent]'` first") from exc
        return completion(**kwargs)


def _build_messages(evidence: BlogJudgeInput) -> list[dict[str, str]]:
    """Build the system and user messages for one classification call.

    Args:
        evidence: URL/title/page-text evidence for one sample.

        Returns:
            A chat-message list suitable for LiteLLM completion calls.
    """
    page_text = (evidence.page_text or "").strip()
    if not page_text:
        page_text = "[page fetch unavailable]"
    return [
        {
            "role": "system",
            "content": (
                "You classify whether a URL and title belong to a personal or independent blog. "
                "Return strict JSON only with keys pred_label and reason. "
                "Use pred_label=blog for personal blogs, note sites, and individual publishing homes. "
                "Use pred_label=non_blog for companies, products, docs, directories, tools, SaaS, or generic sites."
            ),
        },
        {
            "role": "user",
            "content": (
                f"URL: {evidence.url}\n"
                f"Title: {evidence.title or '[missing title]'}\n"
                f"Page text:\n{page_text}\n\n"
                'Respond as JSON: {"pred_label":"blog|non_blog","reason":"short explanation"}'
            ),
        },
    ]


def _extract_content(response: Any) -> str:
    """Extract assistant text from a LiteLLM-like response object.

    Args:
        response: Completion response object or compatible dict.

    Returns:
        Assistant text content to parse as JSON.
    """
    if isinstance(response, dict):
        choices = response.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            return str(message.get("content", ""))
    choices = getattr(response, "choices", None)
    if choices:
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if content is not None:
            return str(content)
    raise ValueError("completion response did not contain assistant content")


def _parse_json_payload(raw_text: str) -> dict[str, Any]:
    """Parse a strict or fenced JSON payload from model output.

    Args:
        raw_text: Assistant text emitted by the model.

    Returns:
        Parsed JSON object.
    """
    stripped = raw_text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].lstrip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("assistant response did not contain a JSON object")
    return json.loads(stripped[start : end + 1])


class _RateLimiter:
    """Limit average LLM request rate across concurrent classifier tasks.

    Args:
        requests_per_minute: Maximum request budget to allow per minute.
    """

    def __init__(self, requests_per_minute: int) -> None:
        self._interval = 60.0 / max(1, requests_per_minute)
        self._lock = asyncio.Lock()
        self._next_available = 0.0

    async def acquire(self) -> None:
        """Wait until one more request can be issued within the rate limit."""
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            wait_seconds = max(0.0, self._next_available - now)
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
                now = loop.time()
            self._next_available = max(self._next_available, now) + self._interval
