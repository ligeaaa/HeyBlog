"""Shared schemas for the lightweight blog classification agent."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class BlogJudgeInput:
    """Describe the evidence sent to the LLM classifier.

    Args:
        url: Original sample URL from the dataset.
        title: Title string paired with the URL.
        page_text: Optional normalized page text extracted from the fetched page.
    """

    url: str
    title: str
    page_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of the input."""
        return asdict(self)


@dataclass(slots=True)
class ProviderSelection:
    """Resolve one concrete provider/model pair for a classifier run.

    Args:
        provider: Normalized provider name used to choose credentials.
        model: Concrete model identifier sent to the LLM SDK.
        api_key: API key for the selected provider.
        base_url: Optional provider-specific base URL.
    """

    provider: str
    model: str
    api_key: str
    base_url: str | None = None


@dataclass(slots=True)
class PageFetchOutcome:
    """Represent the normalized fetch outcome for one dataset row.

    Args:
        request_url: Original request URL from the dataset.
        final_url: Final URL after redirects when fetching succeeded.
        page_text: Normalized text extracted from the fetched HTML.
        fetch_status: ``success`` or ``failed``.
        error_kind: Stable error kind for failed fetches.
        used_page_content: Whether the classifier may rely on fetched page text.
    """

    request_url: str
    final_url: str | None
    page_text: str | None
    fetch_status: str
    error_kind: str | None
    used_page_content: bool

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of the fetch outcome."""
        return asdict(self)


@dataclass(slots=True)
class BlogJudgeResult:
    """Represent the classifier decision for one dataset row.

    Args:
        pred_label: Final predicted label or ``None`` when classification failed.
        reason: Short explanation emitted by the LLM.
        provider: Provider name used for the call.
        model: Concrete model identifier used for the call.
        llm_status: ``success`` or ``failed``.
        raw_response: Optional raw text emitted by the LLM for debugging.
    """

    pred_label: str | None
    reason: str
    provider: str
    model: str
    llm_status: str
    raw_response: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of the classifier result."""
        return asdict(self)


@dataclass(slots=True)
class EvalManifestRow:
    """Store one auditable per-row eval record.

    Args:
        url: Original dataset URL.
        title: Original dataset title.
        gold_label: Gold binary label.
        pred_label: Predicted label or ``None`` on classifier failure.
        fetch_status: ``success`` or ``failed``.
        error_kind: Stable fetch failure kind when present.
        used_page_content: Whether fetched page text was used.
        reason: Human-readable classifier reason or failure text.
        final_url: Final fetched URL on success, otherwise ``None``.
        provider: LLM provider used for classification.
        model: Concrete model identifier used.
        llm_status: ``success`` or ``failed``.
    """

    url: str
    title: str
    gold_label: str
    pred_label: str | None
    fetch_status: str
    error_kind: str | None
    used_page_content: bool
    reason: str
    final_url: str | None
    provider: str
    model: str
    llm_status: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of the manifest row."""
        return asdict(self)


@dataclass(slots=True)
class EvalSummary:
    """Store the top-level metrics and coverage summary for one eval run.

    Args:
        total_rows: Total dataset rows attempted in the run.
        rows_with_pred_label: Rows that produced a final prediction.
        rows_with_page_content: Rows that successfully fetched page text.
        tp: True positives among rows with predictions.
        tn: True negatives among rows with predictions.
        fp: False positives among rows with predictions.
        fn: False negatives among rows with predictions.
        precision: Precision over rows with predictions.
        recall: Recall over rows with predictions.
        f1: F1 score over rows with predictions.
        accuracy: Accuracy over rows with predictions.
        page_fetch_coverage: Fraction of total rows with fetched page content.
        classification_coverage: Fraction of total rows with predictions.
        eval_seconds: Total wall-clock seconds spent in the eval run.
    """

    total_rows: int
    rows_with_pred_label: int
    rows_with_page_content: int
    tp: int
    tn: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    accuracy: float
    page_fetch_coverage: float
    classification_coverage: float
    eval_seconds: float

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of the summary."""
        return asdict(self)
