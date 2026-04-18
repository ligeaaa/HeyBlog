"""Structured-feature random forest baseline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction import DictVectorizer

from trainer.config import ModelConfig
from trainer.dataset.schema import SupervisedSample
from trainer.features.assemble import build_structured_feature_rows
from trainer.models.sklearn_utils import build_random_forest
from trainer.models.sklearn_utils import positive_class_probabilities
from trainer.models.sklearn_utils import summarize_feature_importances


@dataclass(slots=True)
class StructuredRandomForestBaseline:
    model_name: str
    threshold: float
    vectorizer: DictVectorizer
    estimator: RandomForestClassifier
    metadata: dict[str, Any]

    def predict_proba(self, samples: list[SupervisedSample]) -> list[float]:
        rows = build_structured_feature_rows(samples)
        matrix = self.vectorizer.transform(rows)
        return positive_class_probabilities(self.estimator, matrix)

    def feature_summary(self) -> dict[str, Any]:
        feature_names = np.asarray(self.vectorizer.get_feature_names_out())
        return summarize_feature_importances(self.estimator, feature_names)

    def training_log(self) -> str:
        feature_count = len(self.vectorizer.get_feature_names_out())
        classes = ",".join(str(value) for value in self.estimator.classes_.tolist())
        return "\n".join(
            [
                "estimator=random_forest",
                f"n_estimators={self.estimator.n_estimators}",
                f"feature_count={feature_count}",
                f"classes={classes}",
            ]
        )


def train_structured_rf_baseline(
    train_samples: list[SupervisedSample],
    model_config: ModelConfig,
) -> StructuredRandomForestBaseline:
    rows = build_structured_feature_rows(train_samples)
    labels = [1 if sample.binary_label == "blog" else 0 for sample in train_samples]
    vectorizer = DictVectorizer(sparse=True)
    matrix = vectorizer.fit_transform(rows)
    estimator = build_random_forest(seed=model_config.seed, estimators=model_config.rf_estimators)
    estimator.fit(matrix, labels)
    return StructuredRandomForestBaseline(
        model_name=model_config.model_name,
        threshold=model_config.threshold,
        vectorizer=vectorizer,
        estimator=estimator,
        metadata=model_config.to_dict(),
    )
