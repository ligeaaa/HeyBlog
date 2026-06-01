"""Model-consensus URL filter implementation and compatibility wrapper."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from dataclasses import field
import logging
from pathlib import Path
import pickle
import sys
from typing import Any

from crawler.crawling.decisions.base import DECIDER_ROLE_SUCCESS
from crawler.crawling.decisions.base import FilterDecision
from crawler.crawling.decisions.base import StaticStatusUrlFilter
from crawler.crawling.decisions.base import UrlCandidateContext
from crawler.crawling.normalization import normalize_url
from crawler.domain.decision_outcome import DecisionOutcome
from shared.observability import get_logger
from shared.observability import log_event

DEFAULT_MODEL_THRESHOLD = 0.5
DEFAULT_MODEL_WEIGHT = 1.0
SUPPORTED_CONSENSUS_STRATEGIES = frozenset({"any_blog", "majority_blog", "weighted_average"})
LOGGER = get_logger(__name__)


@dataclass(slots=True, frozen=True)
class ConsensusSample:
    """Carry the minimal crawler-owned fields needed for model inference.

    Attributes:
        sample_id: Stable identifier for the candidate URL being scored.
        url: Original candidate URL under evaluation.
        normalized_url: Normalized form used by URL-based features.
        domain: Host/domain portion of the normalized URL.
        title: Best-effort title-like text built from link/context metadata.
        raw_labels: Empty placeholder preserved for model compatibility.
        binary_label: Placeholder label value unused during inference.
        resolution_status: Marker explaining that the sample is inference-only.
        resolution_reason: Marker identifying crawler model-consensus scoring.
        title_missing: Whether the synthetic title-like text was empty.
        split: Synthetic dataset split marker for compatibility.
    """

    sample_id: str
    url: str
    normalized_url: str
    domain: str
    title: str
    raw_labels: list[str]
    binary_label: str
    resolution_status: str
    resolution_reason: str
    title_missing: bool
    split: str | None = None


def load_model(path: Path) -> Any:
    """Load one serialized consensus model without importing trainer helpers.

    Args:
        path: Filesystem path to the pickled model artifact.

    Returns:
        The deserialized model object.
    """
    _add_legacy_model_package_path()
    with path.open("rb") as handle:
        return pickle.load(handle)


def _add_legacy_model_package_path() -> None:
    """Expose migrated training modules for legacy pickle artifacts.

    Existing ``model.joblib`` files were serialized before the model code moved
    to ``HeyBlog_model/`` and still reference modules such as
    ``trainer.models.baseline_tfidf_svm``. Adding the model repository root to
    ``sys.path`` lets those legacy artifacts load while keeping the package out
    of the business runtime's install metadata.
    """
    project_root = Path(__file__).resolve().parents[3]
    candidate_roots = (
        project_root / "HeyBlog_model",
        project_root.parent / "HeyBlog_model",
    )
    for model_repo_root in candidate_roots:
        if model_repo_root.exists() and str(model_repo_root) not in sys.path:
            sys.path.append(str(model_repo_root))
            return


@dataclass(slots=True, frozen=True)
class LoadedConsensusModel:
    """Bundle one loaded trainer model with threshold and quality weight.

    Attributes:
        model_name: Name of the model directory under the trainer model root.
        run_dir: Concrete run directory containing the serialized model.
        predictor: Loaded model object exposing ``predict_proba``.
        threshold: Probability threshold above which the model votes ``blog``.
        weight: Runtime consensus weight derived from validation metrics.
    """

    model_name: str
    run_dir: Path
    predictor: Any
    threshold: float
    weight: float = DEFAULT_MODEL_WEIGHT


def _latest_child(path: Path) -> Path | None:
    """Return the latest timestamped run directory inside one model directory.

    Args:
        path: Model directory whose child run directories should be inspected.

    Returns:
        The lexicographically latest child directory, or ``None`` when the
        directory does not exist or contains no run subdirectories.
    """
    if not path.exists():
        return None
    children = sorted((child for child in path.iterdir() if child.is_dir()), key=lambda child: child.name)
    if not children:
        return None
    return children[-1]


def _discover_latest_runs(model_root: Path) -> dict[str, Path]:
    """Discover the latest available run for every trainer model directory.

    Args:
        model_root: Root directory containing per-model run subdirectories.

    Returns:
        A mapping of model name to its latest run directory. The mapping is
        empty when the root does not exist or contains no usable model runs.
    """
    if not model_root.exists():
        return {}

    runs: dict[str, Path] = {}
    for model_dir in sorted((child for child in model_root.iterdir() if child.is_dir()), key=lambda child: child.name):
        latest_run = _latest_child(model_dir)
        if latest_run is not None:
            runs[model_dir.name] = latest_run
    return runs


def _read_threshold(run_dir: Path, predictor: Any) -> float:
    """Resolve the probability threshold for one loaded trainer model.

    Args:
        run_dir: Run directory that may contain a ``config.json`` fallback.
        predictor: Loaded model object that may expose a ``threshold`` field.

    Returns:
        The threshold used to convert probabilities into ``blog`` or
        ``non_blog`` labels.
    """
    if hasattr(predictor, "threshold"):
        return float(predictor.threshold)

    config_path = run_dir / "config.json"
    if config_path.exists():
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        return float(payload.get("model_config", {}).get("threshold", DEFAULT_MODEL_THRESHOLD))

    return float(DEFAULT_MODEL_THRESHOLD)


def _read_model_weight(run_dir: Path) -> float:
    """Resolve one model's consensus weight from validation metrics.

    Args:
        run_dir: Run directory that may contain a ``metrics.json`` file.

    Returns:
        A positive consensus weight. F1 is preferred because the runtime
        decision is thresholded classification; PR-AUC is used as the fallback
        ranking metric, then ``1.0`` when no usable metric exists.
    """
    metrics_path = run_dir / "metrics.json"
    if not metrics_path.exists():
        return DEFAULT_MODEL_WEIGHT

    try:
        payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return DEFAULT_MODEL_WEIGHT

    for key in ("f1", "pr_auc", "accuracy"):
        value = payload.get(key)
        if isinstance(value, int | float) and math.isfinite(float(value)) and float(value) > 0:
            return float(value)
    return DEFAULT_MODEL_WEIGHT


@dataclass(slots=True)
class ModelConsensusFilter(StaticStatusUrlFilter):
    """Vote across the latest trainer models before keeping crawler candidates.

    Attributes:
        model_root: Root directory containing serialized trainer model runs.
        strategy: Consensus strategy used to combine individual model scores.
        consensus_threshold: Threshold used by the weighted-average strategy.
        loaded_models: Cached loaded models discovered lazily on first use.
    """

    model_root: Path
    strategy: str = "weighted_average"
    consensus_threshold: float = DEFAULT_MODEL_THRESHOLD
    kind: str = field(init=False, default="model_consensus")
    filter_kind: str = field(init=False, default="model")
    filter_reason: str = field(init=False, default="model_consensus_all_non_blog")
    decider_role: str = field(init=False, default=DECIDER_ROLE_SUCCESS)
    loaded_models: tuple[LoadedConsensusModel, ...] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        """Normalize and validate the configured model-consensus strategy."""
        normalized_strategy = self.strategy.strip().lower()
        if normalized_strategy not in SUPPORTED_CONSENSUS_STRATEGIES:
            raise ValueError(f"unknown_model_consensus_strategy:{self.strategy}")
        self.strategy = normalized_strategy
        self.consensus_threshold = float(self.consensus_threshold)

    def _ensure_models_loaded(self) -> tuple[LoadedConsensusModel, ...]:
        """Load and cache the latest available trainer models on demand.

        Returns:
            A tuple of loaded models. The tuple is empty when no usable model
            artifacts exist under the configured model root.
        """
        if self.loaded_models is not None:
            return self.loaded_models

        models: list[LoadedConsensusModel] = []
        for model_name, run_dir in _discover_latest_runs(self.model_root).items():
            model_path = run_dir / "model.joblib"
            if not model_path.exists():
                continue
            try:
                predictor = load_model(model_path)
                models.append(
                    LoadedConsensusModel(
                        model_name=model_name,
                        run_dir=run_dir,
                        predictor=predictor,
                        threshold=_read_threshold(run_dir, predictor),
                        weight=_read_model_weight(run_dir),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                # One corrupt or incompatible model artifact should not block
                # the crawler from evaluating the rest of the available runs.
                log_event(
                    LOGGER,
                    event="model.consensus.load_failed",
                    message="skipping consensus model load",
                    level=logging.WARNING,
                    stage="model_consensus",
                    model_name=model_name,
                    model_path=str(model_path),
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
                continue

        self.loaded_models = tuple(models)
        if not self.loaded_models:
            log_event(
                LOGGER,
                event="model.consensus.no_models_loaded",
                message="no consensus models were loaded",
                level=logging.WARNING,
                stage="model_consensus",
                model_root=str(self.model_root),
            )
        return self.loaded_models

    def _build_sample(
        self,
        url: str,
        *,
        link_text: str,
        context_text: str,
    ) -> ConsensusSample:
        """Convert one crawler candidate URL into a trainer inference sample.

        Args:
            url: Candidate absolute URL under evaluation.
            link_text: Visible anchor text extracted for the URL.
            context_text: Nearby text around the extracted link.

        Returns:
            A crawler-owned ``ConsensusSample`` carrying the normalized URL and
            a title-like text fallback so serialized models can score the URL.
        """
        normalized = normalize_url(url)
        title = next(
            (
                value.strip()
                for value in (link_text, context_text, normalized.domain)
                if value and value.strip()
            ),
            "",
        )
        return ConsensusSample(
            sample_id=normalized.normalized_url,
            url=url,
            normalized_url=normalized.normalized_url,
            domain=normalized.domain,
            title=title,
            raw_labels=[],
            binary_label="non_blog",
            resolution_status="inference_only",
            resolution_reason="crawler_model_consensus",
            title_missing=not bool(title),
            split="crawler",
        )

    def _should_reject(self, probabilities: list[tuple[float, LoadedConsensusModel]]) -> bool:
        """Return whether combined model evidence rejects the candidate URL.

        Args:
            probabilities: Usable ``(probability, loaded_model)`` pairs.

        Returns:
            ``True`` when the configured consensus strategy classifies the
            candidate as non-blog strongly enough to reject it.
        """
        if self.strategy == "any_blog":
            return all(probability < loaded.threshold for probability, loaded in probabilities)

        if self.strategy == "majority_blog":
            blog_votes = sum(1 for probability, loaded in probabilities if probability >= loaded.threshold)
            required_votes = math.ceil(len(probabilities) / 2)
            return blog_votes < required_votes

        total_weight = sum(loaded.weight for _, loaded in probabilities)
        if total_weight <= 0:
            return False
        weighted_probability = sum(probability * loaded.weight for probability, loaded in probabilities) / total_weight
        return weighted_probability < self.consensus_threshold

    def apply(self, candidate: UrlCandidateContext) -> FilterDecision:
        """Keep or reject a URL using the configured model consensus strategy."""
        models = self._ensure_models_loaded()
        if not models:
            return self.accept()

        sample = self._build_sample(
            candidate.normalized_url,
            link_text=candidate.link_text,
            context_text=candidate.context_text,
        )
        probabilities: list[tuple[float, LoadedConsensusModel]] = []
        for loaded in models:
            try:
                probability = float(loaded.predictor.predict_proba([sample])[0])
            except Exception:  # noqa: BLE001
                continue
            probabilities.append((probability, loaded))

        if not probabilities:
            return self.accept()

        if self._should_reject(probabilities):
            return self.reject()
        return self.confirm(accepted_by="model")


@dataclass(slots=True)
class ModelConsensusDecider:
    """Expose the legacy decision-step interface on top of the new filter."""

    model_root: Path
    strategy: str = "weighted_average"
    consensus_threshold: float = DEFAULT_MODEL_THRESHOLD
    _filter: ModelConsensusFilter = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._filter = ModelConsensusFilter(
            model_root=self.model_root,
            strategy=self.strategy,
            consensus_threshold=self.consensus_threshold,
        )

    def decide(
        self,
        url: str,
        source_domain: str,
        *,
        link_text: str = "",
        context_text: str = "",
    ) -> DecisionOutcome:
        """Return a compatibility decision payload for older call sites."""
        decision = self._filter.apply(
            UrlCandidateContext(
                source_blog_id=0,
                source_domain=source_domain,
                normalized_url=normalize_url(url).normalized_url,
                link_text=link_text,
                context_text=context_text,
            )
        )
        if not decision.accepted:
            return DecisionOutcome(accepted=False, score=0.0, reasons=(self._filter.filter_reason,))
        if not self._filter._ensure_models_loaded():
            return DecisionOutcome(accepted=True, score=0.0, reasons=("model_consensus_skipped_no_models",))
        return DecisionOutcome(accepted=True, score=0.0, reasons=("model_consensus_kept",))
