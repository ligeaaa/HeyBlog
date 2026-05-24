"""Evaluate runtime model-consensus strategies on a prepared trainer split."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trainer.dataset.schema import SupervisedSample
from trainer.evaluation.metrics import compute_metrics
from trainer.io.artifact_writer import ensure_dir
from trainer.io.artifact_writer import write_csv
from trainer.io.artifact_writer import write_json
from trainer.io.dataset_reader import read_jsonl
from trainer.models.inference import PredictionRow
from trainer.models.inference import load_model


DEFAULT_CONSENSUS_STRATEGIES = ("weighted_average", "majority_blog", "any_blog")
DEFAULT_CONSENSUS_THRESHOLD = 0.5
DEFAULT_MODEL_THRESHOLD = 0.5
DEFAULT_MODEL_WEIGHT = 1.0


@dataclass(slots=True)
class RuntimeConsensusModel:
    """Loaded runtime model metadata used for offline consensus evaluation.

    Attributes:
        model_name: Runtime model family name under the model root.
        run_dir: Concrete runtime run directory selected for evaluation.
        predictor: Loaded predictor exposing ``predict_proba``.
        threshold: Per-model blog threshold used by vote-based strategies.
        weight: Model quality weight used by weighted-average consensus.
    """

    model_name: str
    run_dir: Path
    predictor: Any
    threshold: float
    weight: float


def _latest_child(path: Path) -> Path | None:
    """Return the lexicographically latest run directory below ``path``.

    Args:
        path: Runtime model family directory to inspect.

    Returns:
        Latest child directory, or ``None`` when the family has no runs.
    """
    if not path.exists():
        return None
    children = sorted((child for child in path.iterdir() if child.is_dir()), key=lambda child: child.name)
    if not children:
        return None
    return children[-1]


def _discover_latest_runs(model_root: Path) -> dict[str, Path]:
    """Discover the latest run directory for every runtime model family.

    Args:
        model_root: Runtime model root such as
            ``runtime_resources/models/url_decision/current``.

    Returns:
        Mapping of model family name to selected latest run directory.
    """
    if not model_root.exists():
        raise FileNotFoundError(f"Runtime model root does not exist: {model_root}")

    runs: dict[str, Path] = {}
    for model_dir in sorted((child for child in model_root.iterdir() if child.is_dir()), key=lambda child: child.name):
        latest_run = _latest_child(model_dir)
        if latest_run is not None:
            runs[model_dir.name] = latest_run
    if not runs:
        raise FileNotFoundError(f"No runtime model runs found under: {model_root}")
    return runs


def _read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object or return an empty mapping when the file is absent.

    Args:
        path: JSON file to read.

    Returns:
        Parsed object when present and valid, otherwise an empty dict.
    """
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_threshold(run_dir: Path, predictor: Any) -> float:
    """Resolve the per-model threshold for one runtime model.

    Args:
        run_dir: Runtime run directory containing optional config metadata.
        predictor: Loaded predictor that may carry a ``threshold`` attribute.

    Returns:
        Threshold used by vote-based consensus strategies.
    """
    if hasattr(predictor, "threshold"):
        return float(predictor.threshold)
    config = _read_json(run_dir / "config.json")
    model_config = config.get("model_config", {})
    if isinstance(model_config, dict):
        return float(model_config.get("threshold", DEFAULT_MODEL_THRESHOLD))
    return DEFAULT_MODEL_THRESHOLD


def _read_weight(run_dir: Path) -> float:
    """Resolve a positive runtime consensus weight from model metrics.

    Args:
        run_dir: Runtime run directory containing optional ``metrics.json``.

    Returns:
        F1, PR-AUC, accuracy, or ``1.0`` if no positive metric is available.
    """
    metrics = _read_json(run_dir / "metrics.json")
    for key in ("f1", "pr_auc", "accuracy"):
        value = metrics.get(key)
        if isinstance(value, int | float) and math.isfinite(float(value)) and float(value) > 0:
            return float(value)
    return DEFAULT_MODEL_WEIGHT


def _load_runtime_models(model_root: Path) -> list[RuntimeConsensusModel]:
    """Load all latest runtime models for consensus evaluation.

    Args:
        model_root: Runtime model root containing model-family run directories.

    Returns:
        Loaded runtime models sorted by model family name.
    """
    models: list[RuntimeConsensusModel] = []
    for model_name, run_dir in _discover_latest_runs(model_root).items():
        model_path = run_dir / "model.joblib"
        if not model_path.exists():
            continue
        predictor = load_model(model_path)
        models.append(
            RuntimeConsensusModel(
                model_name=model_name,
                run_dir=run_dir,
                predictor=predictor,
                threshold=_read_threshold(run_dir, predictor),
                weight=_read_weight(run_dir),
            )
        )
    if not models:
        raise FileNotFoundError(f"No loadable model.joblib artifacts found under: {model_root}")
    return models


def _load_split_samples(dataset_dir: Path, split: str) -> list[SupervisedSample]:
    """Load a prepared supervised split from a trainer dataset directory.

    Args:
        dataset_dir: Prepared trainer dataset directory.
        split: Split name, usually ``test`` or ``val``.

    Returns:
        Deserialized supervised samples from ``<split>.jsonl``.
    """
    split_path = dataset_dir / f"{split}.jsonl"
    if not split_path.exists():
        raise FileNotFoundError(f"Missing dataset split: {split_path}")
    return [SupervisedSample(**row) for row in read_jsonl(split_path)]


def _predict_by_model(
    models: list[RuntimeConsensusModel],
    samples: list[SupervisedSample],
) -> dict[str, list[float]]:
    """Run all models on the same sample list.

    Args:
        models: Runtime models to evaluate.
        samples: Supervised samples used as model input.

    Returns:
        Mapping of model family name to blog probabilities.
    """
    return {loaded.model_name: [float(value) for value in loaded.predictor.predict_proba(samples)] for loaded in models}


def _classify_sample(
    *,
    strategy: str,
    sample_index: int,
    models: list[RuntimeConsensusModel],
    probabilities: dict[str, list[float]],
    consensus_threshold: float,
) -> tuple[str, float, int]:
    """Classify one sample using a runtime consensus strategy.

    Args:
        strategy: Strategy name: ``weighted_average``, ``majority_blog``, or
            ``any_blog``.
        sample_index: Index of the sample in the shared probability arrays.
        models: Loaded runtime models in deterministic order.
        probabilities: Per-model blog probabilities.
        consensus_threshold: Global weighted-average threshold.

    Returns:
        Tuple of predicted label, aggregate blog probability/score, and count
        of per-model blog votes.
    """
    blog_votes = 0
    weighted_sum = 0.0
    total_weight = 0.0
    for loaded in models:
        probability = probabilities[loaded.model_name][sample_index]
        if probability >= loaded.threshold:
            blog_votes += 1
        weighted_sum += probability * loaded.weight
        total_weight += loaded.weight

    weighted_probability = weighted_sum / total_weight if total_weight > 0 else 0.0
    if strategy == "weighted_average":
        return ("blog" if weighted_probability >= consensus_threshold else "non_blog", weighted_probability, blog_votes)
    if strategy == "majority_blog":
        required_votes = math.ceil(len(models) / 2)
        return ("blog" if blog_votes >= required_votes else "non_blog", blog_votes / len(models), blog_votes)
    if strategy == "any_blog":
        return ("blog" if blog_votes > 0 else "non_blog", blog_votes / len(models), blog_votes)
    raise ValueError(f"unknown_runtime_consensus_strategy:{strategy}")


def _prediction_rows_for_strategy(
    *,
    strategy: str,
    samples: list[SupervisedSample],
    models: list[RuntimeConsensusModel],
    probabilities: dict[str, list[float]],
    consensus_threshold: float,
) -> list[PredictionRow]:
    """Build prediction rows for one consensus strategy.

    Args:
        strategy: Consensus strategy being evaluated.
        samples: Gold-labeled supervised samples.
        models: Loaded runtime models.
        probabilities: Per-model blog probabilities for all samples.
        consensus_threshold: Global weighted-average threshold.

    Returns:
        Prediction rows compatible with shared trainer metrics helpers.
    """
    rows: list[PredictionRow] = []
    for index, sample in enumerate(samples):
        pred_label, score, _blog_votes = _classify_sample(
            strategy=strategy,
            sample_index=index,
            models=models,
            probabilities=probabilities,
            consensus_threshold=consensus_threshold,
        )
        rows.append(
            PredictionRow(
                sample_id=sample.sample_id,
                url=sample.url,
                title=sample.title,
                domain=sample.domain,
                raw_labels=list(sample.raw_labels),
                gold_label=sample.binary_label,
                pred_label=pred_label,
                prob_blog=score,
                split=sample.split or "unknown",
            )
        )
    return rows


def _build_prediction_export_rows(
    *,
    samples: list[SupervisedSample],
    models: list[RuntimeConsensusModel],
    probabilities: dict[str, list[float]],
    predictions_by_strategy: dict[str, list[PredictionRow]],
    consensus_threshold: float,
) -> list[dict[str, Any]]:
    """Build a CSV-friendly per-sample consensus comparison table.

    Args:
        samples: Gold-labeled supervised samples.
        models: Loaded runtime models.
        probabilities: Per-model blog probabilities for all samples.
        predictions_by_strategy: Prediction rows keyed by strategy name.
        consensus_threshold: Global weighted-average threshold.

    Returns:
        Rows containing gold label, strategy predictions, votes, and per-model
        probabilities.
    """
    rows: list[dict[str, Any]] = []
    for index, sample in enumerate(samples):
        export_row: dict[str, Any] = {
            "sample_id": sample.sample_id,
            "url": sample.url,
            "title": sample.title,
            "gold_label": sample.binary_label,
        }
        for strategy, predictions in predictions_by_strategy.items():
            pred_label, score, blog_votes = _classify_sample(
                strategy=strategy,
                sample_index=index,
                models=models,
                probabilities=probabilities,
                consensus_threshold=consensus_threshold,
            )
            export_row[f"{strategy}_label"] = pred_label
            export_row[f"{strategy}_score"] = round(score, 6)
            export_row[f"{strategy}_blog_votes"] = blog_votes
            if predictions[index].pred_label != pred_label:
                raise AssertionError("strategy prediction export mismatch")
        export_row["per_model_probabilities"] = ";".join(
            f"{loaded.model_name}:{probabilities[loaded.model_name][index]:.6f}:w={loaded.weight:.6f}:t={loaded.threshold:.6f}"
            for loaded in models
        )
        rows.append(export_row)
    return rows


def _f1_for_threshold(labels: list[str], scores: list[float], threshold: float) -> float:
    """Compute blog-class F1 for one aggregate-score threshold.

    Args:
        labels: Gold labels aligned to aggregate scores.
        scores: Weighted blog probabilities.
        threshold: Candidate weighted-average threshold.

    Returns:
        Binary blog-class F1 for the threshold.
    """
    tp = fp = fn = 0
    for label, score in zip(labels, scores, strict=True):
        predicted_blog = score >= threshold
        actual_blog = label == "blog"
        if predicted_blog and actual_blog:
            tp += 1
        elif predicted_blog and not actual_blog:
            fp += 1
        elif not predicted_blog and actual_blog:
            fn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    if precision + recall == 0.0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _weighted_scores(
    *,
    models: list[RuntimeConsensusModel],
    probabilities: dict[str, list[float]],
    sample_count: int,
) -> list[float]:
    """Compute weighted-average blog probabilities for all samples.

    Args:
        models: Loaded runtime models.
        probabilities: Per-model blog probabilities.
        sample_count: Number of samples to score.

    Returns:
        Weighted blog probability for each sample.
    """
    total_weight = sum(loaded.weight for loaded in models)
    if total_weight <= 0:
        return [0.0 for _ in range(sample_count)]
    return [
        sum(probabilities[loaded.model_name][index] * loaded.weight for loaded in models) / total_weight
        for index in range(sample_count)
    ]


def _tune_weighted_threshold(
    *,
    dataset_dir: Path,
    models: list[RuntimeConsensusModel],
    split: str,
) -> dict[str, Any]:
    """Tune weighted-average consensus threshold on a validation split.

    Args:
        dataset_dir: Prepared trainer dataset directory.
        models: Loaded runtime models reused for validation inference.
        split: Validation split name.

    Returns:
        Threshold-selection summary with selected threshold and validation F1.
    """
    samples = _load_split_samples(dataset_dir, split)
    probabilities = _predict_by_model(models, samples)
    scores = _weighted_scores(models=models, probabilities=probabilities, sample_count=len(samples))
    labels = [sample.binary_label for sample in samples]
    candidates = sorted({0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9} | {round(score, 6) for score in scores})
    best_threshold = DEFAULT_CONSENSUS_THRESHOLD
    best_f1 = -1.0
    for threshold in candidates:
        score = _f1_for_threshold(labels, scores, threshold)
        if score > best_f1 or (score == best_f1 and abs(threshold - 0.5) < abs(best_threshold - 0.5)):
            best_threshold = threshold
            best_f1 = score
    return {
        "strategy": "weighted_average",
        "split": split,
        "threshold": best_threshold,
        "val_f1": round(best_f1, 6),
        "samples": len(samples),
    }


def run_evaluate_runtime_consensus(
    *,
    dataset_dir: Path,
    model_root: Path,
    output_dir: Path,
    split: str = "test",
    strategies: tuple[str, ...] = DEFAULT_CONSENSUS_STRATEGIES,
    consensus_threshold: float = DEFAULT_CONSENSUS_THRESHOLD,
    tune_weighted_threshold_split: str | None = None,
) -> dict[str, Any]:
    """Evaluate runtime model-consensus strategies against one dataset split.

    Args:
        dataset_dir: Prepared trainer dataset directory containing split JSONL.
        model_root: Runtime model root to evaluate.
        output_dir: Directory where summary and prediction CSV are written.
        split: Dataset split name to evaluate.
        strategies: Consensus strategies to compare.
        consensus_threshold: Threshold for weighted-average consensus.
        tune_weighted_threshold_split: Optional validation split name used to
            select the weighted-average threshold before evaluating ``split``.

    Returns:
        Serializable summary containing model metadata, metrics, and artifact
        paths.
    """
    normalized_strategies = tuple(strategy.strip().lower() for strategy in strategies)
    samples = _load_split_samples(dataset_dir, split)
    models = _load_runtime_models(model_root)
    threshold_tuning: dict[str, Any] | None = None
    if tune_weighted_threshold_split is not None:
        threshold_tuning = _tune_weighted_threshold(
            dataset_dir=dataset_dir,
            models=models,
            split=tune_weighted_threshold_split,
        )
        consensus_threshold = float(threshold_tuning["threshold"])
    probabilities = _predict_by_model(models, samples)

    predictions_by_strategy = {
        strategy: _prediction_rows_for_strategy(
            strategy=strategy,
            samples=samples,
            models=models,
            probabilities=probabilities,
            consensus_threshold=consensus_threshold,
        )
        for strategy in normalized_strategies
    }
    metrics_by_strategy = {
        strategy: compute_metrics(predictions)
        for strategy, predictions in predictions_by_strategy.items()
    }

    output_dir = ensure_dir(output_dir)
    prediction_rows = _build_prediction_export_rows(
        samples=samples,
        models=models,
        probabilities=probabilities,
        predictions_by_strategy=predictions_by_strategy,
        consensus_threshold=consensus_threshold,
    )
    fieldnames = list(prediction_rows[0].keys()) if prediction_rows else ["sample_id", "url", "title", "gold_label"]
    predictions_path = output_dir / f"runtime_consensus_{split}_predictions.csv"
    summary_path = output_dir / f"runtime_consensus_{split}_summary.json"
    write_csv(predictions_path, fieldnames=fieldnames, rows=prediction_rows)

    summary: dict[str, Any] = {
        "dataset_dir": str(dataset_dir),
        "model_root": str(model_root),
        "output_dir": str(output_dir),
        "split": split,
        "consensus_threshold": consensus_threshold,
        "threshold_tuning": threshold_tuning,
        "models": [
            {
                "model_name": loaded.model_name,
                "run_dir": str(loaded.run_dir),
                "threshold": loaded.threshold,
                "weight": loaded.weight,
            }
            for loaded in models
        ],
        "metrics": metrics_by_strategy,
        "predictions_path": str(predictions_path),
        "summary_path": str(summary_path),
    }
    write_json(summary_path, summary)
    return summary
