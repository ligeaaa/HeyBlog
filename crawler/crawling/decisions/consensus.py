"""Model-consensus URL decision step for crawler candidate filtering."""

from __future__ import annotations

import json
from dataclasses import dataclass
from dataclasses import field
import logging
from pathlib import Path
import pickle
from typing import Any

from crawler.crawling.normalization import normalize_url
from crawler.domain.decision_outcome import DecisionOutcome

DEFAULT_MODEL_THRESHOLD = 0.5
LOGGER = logging.getLogger(__name__)


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
    with path.open("rb") as handle:
        return pickle.load(handle)


@dataclass(slots=True, frozen=True)
class LoadedConsensusModel:
    """Bundle one loaded trainer model with the threshold used for voting.

    Attributes:
        model_name: Name of the model directory under the trainer model root.
        run_dir: Concrete run directory containing the serialized model.
        predictor: Loaded model object exposing ``predict_proba``.
        threshold: Probability threshold above which the model votes ``blog``.
    """

    model_name: str
    run_dir: Path
    predictor: Any
    threshold: float


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


@dataclass(slots=True)
class ModelConsensusDecider:
    """Vote across the latest trainer models before keeping crawler candidates.

    Attributes:
        model_root: Root directory containing serialized trainer model runs.
        loaded_models: Cached loaded models discovered lazily on first use.
    """

    model_root: Path
    loaded_models: tuple[LoadedConsensusModel, ...] | None = field(default=None, init=False, repr=False)

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
                    )
                )
            except Exception as exc:  # noqa: BLE001
                # One corrupt or incompatible model artifact should not block
                # the crawler from evaluating the rest of the available runs.
                LOGGER.warning(
                    "Skipping consensus model load for %s from %s: %s: %s",
                    model_name,
                    model_path,
                    type(exc).__name__,
                    exc,
                )
                continue

        self.loaded_models = tuple(models)
        if not self.loaded_models:
            LOGGER.warning("No consensus models were loaded from %s", self.model_root)
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

    def decide(
        self,
        url: str,
        source_domain: str,
        *,
        link_text: str = "",
        context_text: str = "",
    ) -> DecisionOutcome:
        """Keep a URL unless every available model votes ``non_blog``.

        Args:
            url: Absolute extracted URL being evaluated.
            source_domain: Domain of the page from which the URL was extracted.
                The current consensus models do not use this field directly,
                but it remains part of the decision interface.
            link_text: Visible anchor text associated with the URL.
            context_text: Nearby context text associated with the URL.

        Returns:
            A ``DecisionOutcome`` that rejects only when every loaded model
            predicts ``non_blog``. When no models are available, the URL is
            allowed through unchanged.
        """
        del source_domain
        models = self._ensure_models_loaded()
        if not models:
            return DecisionOutcome(
                accepted=True,
                score=0.0,
                reasons=("model_consensus_skipped_no_models",),
            )

        sample = self._build_sample(url, link_text=link_text, context_text=context_text)
        blog_votes = 0
        max_probability = 0.0
        usable_models = 0
        for loaded in models:
            try:
                probability = float(loaded.predictor.predict_proba([sample])[0])
            except Exception:  # noqa: BLE001
                continue
            usable_models += 1
            max_probability = max(max_probability, probability)
            if probability >= loaded.threshold:
                blog_votes += 1

        if usable_models == 0:
            return DecisionOutcome(
                accepted=True,
                score=0.0,
                reasons=("model_consensus_skipped_no_models",),
            )

        if blog_votes == 0:
            return DecisionOutcome(
                accepted=False,
                score=max_probability,
                reasons=("model_consensus_all_non_blog",),
            )

        return DecisionOutcome(
            accepted=True,
            score=max_probability,
            reasons=("model_consensus_kept",),
        )
