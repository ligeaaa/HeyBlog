"""Structured-feature baseline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from trainer.config import ModelConfig
from trainer.dataset.schema import SupervisedSample
from trainer.features.assemble import build_structured_feature_rows
from trainer.models.simple_logistic import SparseLogisticRegression


@dataclass(slots=True)
class StructuredBaseline:
    model_name: str
    threshold: float
    estimator: SparseLogisticRegression
    metadata: dict[str, Any]

    def predict_proba(self, samples: list[SupervisedSample]) -> list[float]:
        rows = build_structured_feature_rows(samples)
        return self.estimator.predict_proba(rows)

    def feature_summary(self) -> dict[str, Any]:
        return self.estimator.top_weight_summary()


def train_structured_baseline(
    train_samples: list[SupervisedSample],
    model_config: ModelConfig,
) -> StructuredBaseline:
    rows = build_structured_feature_rows(train_samples)
    labels = [1 if sample.binary_label == "blog" else 0 for sample in train_samples]
    estimator = SparseLogisticRegression(
        learning_rate=model_config.learning_rate,
        l2_strength=model_config.l2_strength,
        epochs=model_config.epochs,
        seed=model_config.seed,
    ).fit(rows, labels)
    return StructuredBaseline(
        model_name="structured",
        threshold=model_config.threshold,
        estimator=estimator,
        metadata=model_config.to_dict(),
    )
