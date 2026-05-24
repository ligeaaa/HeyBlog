"""Train one configured baseline on a prepared dataset."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from pathlib import Path

from trainer.config import ModelConfig
from trainer.config import hybrid_mlp_model_config
from trainer.config import qwen_embedding_lr_model_config
from trainer.config import structured_model_config
from trainer.config import structured_lr_model_config
from trainer.config import structured_rf_model_config
from trainer.config import structured_svm_model_config
from trainer.config import tfidf_model_config
from trainer.config import tfidf_lr_model_config
from trainer.config import tfidf_nb_model_config
from trainer.config import tfidf_svm_model_config
from trainer.io.artifact_writer import ensure_dir
from trainer.io.artifact_writer import write_json
from trainer.io.artifact_writer import write_text
from trainer.io.dataset_reader import read_jsonl
from trainer.models.inference import save_model
from trainer.models.registry import train_model
from trainer.dataset.schema import SupervisedSample


def _deserialize_samples(rows: list[dict[str, object]]) -> list[SupervisedSample]:
    return [SupervisedSample(**row) for row in rows]


def _default_model_config(model_name: str) -> ModelConfig:
    if model_name == "structured":
        return structured_model_config()
    if model_name == "structured_lr":
        return structured_lr_model_config()
    if model_name == "structured_svm":
        return structured_svm_model_config()
    if model_name == "structured_rf":
        return structured_rf_model_config()
    if model_name == "tfidf":
        return tfidf_model_config()
    if model_name == "tfidf_lr":
        return tfidf_lr_model_config()
    if model_name == "tfidf_svm":
        return tfidf_svm_model_config()
    if model_name == "tfidf_nb":
        return tfidf_nb_model_config()
    if model_name == "qwen_embedding_lr":
        return qwen_embedding_lr_model_config()
    if model_name == "hybrid_mlp":
        return hybrid_mlp_model_config()
    raise ValueError(f"Unsupported trainer model: {model_name}")


def default_run_id() -> str:
    """Return the timestamp identifier for one trainer run."""
    return datetime.now(timezone.utc).strftime("%y%m%d%H%M")


def _f1_for_threshold(labels: list[str], probabilities: list[float], threshold: float) -> float:
    """Compute binary blog-class F1 for one probability threshold.

    Args:
        labels: Gold binary labels aligned to ``probabilities``.
        probabilities: Blog-class probabilities emitted by the trained model.
        threshold: Candidate probability threshold.

    Returns:
        F1 score for the provided threshold.
    """

    tp = fp = fn = 0
    for label, probability in zip(labels, probabilities, strict=True):
        predicted_blog = probability >= threshold
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


def _tune_threshold(model: object, val_samples: list[SupervisedSample]) -> dict[str, float | int]:
    """Select the validation-set F1-optimal threshold for a trained model.

    Args:
        model: Trained model exposing ``predict_proba`` and ``threshold``.
        val_samples: Validation samples held out by the prepared dataset.

    Returns:
        Summary containing the selected threshold and validation F1.
    """

    if not val_samples or not hasattr(model, "predict_proba"):
        return {"threshold": float(getattr(model, "threshold", 0.5)), "val_f1": 0.0, "val_samples": 0}
    probabilities = [float(value) for value in model.predict_proba(val_samples)]  # type: ignore[attr-defined]
    labels = [sample.binary_label for sample in val_samples]
    candidates = sorted({0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9} | {round(value, 6) for value in probabilities})
    best_threshold = float(getattr(model, "threshold", 0.5))
    best_f1 = -1.0
    for threshold in candidates:
        score = _f1_for_threshold(labels, probabilities, threshold)
        if score > best_f1 or (score == best_f1 and abs(threshold - 0.5) < abs(best_threshold - 0.5)):
            best_threshold = threshold
            best_f1 = score
    setattr(model, "threshold", best_threshold)
    metadata = getattr(model, "metadata", None)
    if isinstance(metadata, dict):
        metadata["threshold"] = best_threshold
        metadata["selected_threshold"] = best_threshold
        metadata["selected_threshold_val_f1"] = round(best_f1, 6)
    return {"threshold": best_threshold, "val_f1": round(best_f1, 6), "val_samples": len(val_samples)}


def run_train_baseline(
    *,
    dataset_dir: Path,
    model_name: str,
    output_dir: Path | None = None,
    embedding_manifest: Path | None = None,
) -> dict[str, object]:
    model_config = _default_model_config(model_name)
    print(f"[train] dataset_dir={dataset_dir}", flush=True)
    print(f"[train] model={model_name}", flush=True)
    train_samples = _deserialize_samples(read_jsonl(dataset_dir / "train.jsonl"))
    val_samples = _deserialize_samples(read_jsonl(dataset_dir / "val.jsonl"))
    print(f"[train] loaded train samples={len(train_samples)}", flush=True)
    trained_model = train_model(model_name, train_samples, model_config, embedding_manifest=embedding_manifest)
    threshold_summary = _tune_threshold(trained_model, val_samples)
    print(
        f"[train] selected threshold={threshold_summary['threshold']} val_f1={threshold_summary['val_f1']}",
        flush=True,
    )
    if output_dir:
        run_dir = ensure_dir(output_dir)
    else:
        run_dir = ensure_dir(model_config.run_root / model_name / default_run_id())
    print(f"[train] writing artifacts to {run_dir}", flush=True)
    save_model(run_dir / "model.joblib", trained_model)
    write_json(
        run_dir / "config.json",
        {
            "dataset_dir": str(dataset_dir),
            "model_name": model_name,
            "model_config": model_config.to_dict(),
            "embedding_manifest": str(embedding_manifest) if embedding_manifest else None,
            "selected_threshold": threshold_summary,
        },
    )
    write_json(run_dir / "feature_summary.json", trained_model.feature_summary())
    write_text(run_dir / "train.log", trained_model.training_log() + "\n")
    return {
        "run_dir": str(run_dir),
        "model_name": model_name,
        "dataset_dir": str(dataset_dir),
    }
