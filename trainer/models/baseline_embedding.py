"""Dense embedding baseline over URL, title, and extracted page text."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Protocol

import numpy as np
from sklearn.linear_model import LogisticRegression

from trainer.config import ModelConfig
from trainer.dataset.schema import SupervisedSample
from trainer.features.embedding_features import BLOG_CLASSIFICATION_INSTRUCTION
from trainer.features.embedding_store import CachedEmbeddingEncoder
from trainer.models.sklearn_utils import build_logistic_regression
from trainer.models.sklearn_utils import build_training_log
from trainer.models.sklearn_utils import positive_class_probabilities
from trainer.models.sklearn_utils import summarize_weight_vector


class EmbeddingEncoder(Protocol):
    """Minimal encoder contract required by the embedding baseline."""

    def encode(self, samples: list[SupervisedSample]) -> np.ndarray[Any, Any]:
        """Return a dense numeric matrix for the provided supervised samples."""


@dataclass(slots=True)
class EmbeddingBaseline:
    model_name: str
    threshold: float
    encoder: EmbeddingEncoder
    estimator: LogisticRegression
    metadata: dict[str, Any]

    def _transform(self, samples: list[SupervisedSample]) -> np.ndarray[Any, Any]:
        matrix = np.asarray(self.encoder.encode(samples), dtype=np.float32)
        if matrix.ndim != 2:
            raise ValueError(f"Embedding encoder returned a non-matrix shape: {matrix.shape}")
        return matrix

    def predict_proba(self, samples: list[SupervisedSample]) -> list[float]:
        return positive_class_probabilities(self.estimator, self._transform(samples))

    def feature_summary(self) -> dict[str, Any]:
        feature_count = int(np.asarray(self.estimator.coef_[0]).ravel().size)
        feature_names = np.asarray([f"embedding:{index}" for index in range(feature_count)], dtype=object)
        weights = np.asarray(self.estimator.coef_[0], dtype=float).ravel()
        return summarize_weight_vector(weights, feature_names)

    def training_log(self) -> str:
        feature_count = int(np.asarray(self.estimator.coef_[0]).ravel().size)
        return build_training_log(self.estimator, feature_count=feature_count)


def default_embedding_manifest_path(model_config: ModelConfig) -> Any:
    """Return the latest cached embedding manifest for the configured model."""

    model_dir = model_config.embedding_root / "qwen_embedding_lr"
    if not model_dir.exists():
        raise FileNotFoundError(f"No embedding cache directory found: {model_dir}. Run build-embeddings first.")
    candidates = sorted(path / "manifest.json" for path in model_dir.iterdir() if (path / "manifest.json").exists())
    if not candidates:
        raise FileNotFoundError(f"No embedding manifest found under {model_dir}. Run build-embeddings first.")
    return candidates[-1]


def train_embedding_baseline(
    train_samples: list[SupervisedSample],
    model_config: ModelConfig,
    *,
    encoder: EmbeddingEncoder | None = None,
    embedding_manifest: Path | None = None,
) -> EmbeddingBaseline:
    if encoder is None:
        manifest_path = embedding_manifest or default_embedding_manifest_path(model_config)
        print(f"[train:qwen_embedding_lr] loading cached embeddings manifest={manifest_path}", flush=True)
        encoder = CachedEmbeddingEncoder(manifest_path)
    print(f"[train:qwen_embedding_lr] selecting cached train embeddings samples={len(train_samples)}", flush=True)
    matrix = np.asarray(encoder.encode(train_samples), dtype=np.float32)
    print(f"[train:qwen_embedding_lr] fitting logistic regression rows={matrix.shape[0]} dims={matrix.shape[1]}", flush=True)
    labels = [1 if sample.binary_label == "blog" else 0 for sample in train_samples]
    estimator = build_logistic_regression(
        seed=model_config.seed,
        epochs=model_config.epochs,
        l2_strength=model_config.l2_strength,
    )
    estimator.fit(matrix, labels)
    return EmbeddingBaseline(
        model_name=model_config.model_name,
        threshold=model_config.threshold,
        encoder=encoder,
        estimator=estimator,
        metadata=model_config.to_dict()
        | {
            "embedding_task_description": BLOG_CLASSIFICATION_INSTRUCTION,
            "embedding_input_fields": ["normalized_url", "domain", "title", "text"],
            "embedding_source": "cached",
            "embedding_manifest_path": str(getattr(encoder, "manifest_path", "")),
        },
    )
