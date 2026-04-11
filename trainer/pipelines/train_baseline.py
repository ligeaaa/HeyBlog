"""Train one configured baseline on a prepared dataset."""

from __future__ import annotations

from datetime import datetime
from datetime import UTC
from pathlib import Path

from trainer.config import ModelConfig
from trainer.config import structured_model_config
from trainer.config import tfidf_model_config
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
    if model_name == "tfidf":
        return tfidf_model_config()
    raise ValueError(f"Unsupported trainer model: {model_name}")


def default_run_id(model_name: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}--{model_name}"


def run_train_baseline(
    *,
    dataset_dir: Path,
    model_name: str,
    output_dir: Path | None = None,
) -> dict[str, object]:
    model_config = _default_model_config(model_name)
    train_samples = _deserialize_samples(read_jsonl(dataset_dir / "train.jsonl"))
    trained_model = train_model(model_name, train_samples, model_config)
    run_dir = ensure_dir(output_dir or (model_config.run_root / default_run_id(model_name)))
    save_model(run_dir / "model.joblib", trained_model)
    write_json(
        run_dir / "config.json",
        {
            "dataset_dir": str(dataset_dir),
            "model_name": model_name,
            "model_config": model_config.to_dict(),
        },
    )
    write_json(run_dir / "feature_summary.json", trained_model.feature_summary())
    write_text(run_dir / "train.log", "\n".join(f"{loss:.6f}" for loss in trained_model.estimator.loss_history) + "\n")
    return {
        "run_dir": str(run_dir),
        "model_name": model_name,
        "dataset_dir": str(dataset_dir),
    }
