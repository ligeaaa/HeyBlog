"""Structured-feature baseline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression

from trainer.config import ModelConfig
from trainer.dataset.schema import SupervisedSample
from trainer.features.assemble import build_structured_feature_rows
from trainer.models.sklearn_utils import build_logistic_regression
from trainer.models.sklearn_utils import build_training_log
from trainer.models.sklearn_utils import positive_class_probabilities
from trainer.models.sklearn_utils import summarize_linear_weights


@dataclass(slots=True)
class StructuredBaseline:
    model_name: str
    threshold: float
    vectorizer: DictVectorizer
    estimator: LogisticRegression
    metadata: dict[str, Any]

    def predict_proba(self, samples: list[SupervisedSample]) -> list[float]:
        rows = build_structured_feature_rows(samples)
        matrix = self.vectorizer.transform(rows)
        return positive_class_probabilities(self.estimator, matrix)

    def feature_summary(self) -> dict[str, Any]:
        feature_names = np.asarray(self.vectorizer.get_feature_names_out())
        return summarize_linear_weights(self.estimator, feature_names)

    def training_log(self) -> str:
        feature_names = np.asarray(self.vectorizer.get_feature_names_out())
        return build_training_log(self.estimator, feature_count=int(feature_names.size))


def train_structured_baseline(
    train_samples: list[SupervisedSample],
    model_config: ModelConfig,
) -> StructuredBaseline:
    rows = build_structured_feature_rows(train_samples)
    labels = [1 if sample.binary_label == "blog" else 0 for sample in train_samples]
    vectorizer = DictVectorizer(sparse=True)
    matrix = vectorizer.fit_transform(rows)
    estimator = build_logistic_regression(
        seed=model_config.seed,
        epochs=model_config.epochs,
        l2_strength=model_config.l2_strength,
    )
    estimator.fit(matrix, labels)
    return StructuredBaseline(
        model_name=model_config.model_name,
        threshold=model_config.threshold,
        vectorizer=vectorizer,
        estimator=estimator,
        metadata=model_config.to_dict(),
    )
