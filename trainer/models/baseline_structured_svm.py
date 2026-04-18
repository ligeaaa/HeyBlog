"""Structured-feature linear SVM baseline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.svm import SVC

from trainer.config import ModelConfig
from trainer.dataset.schema import SupervisedSample
from trainer.features.assemble import build_structured_feature_rows
from trainer.models.sklearn_utils import build_linear_svm
from trainer.models.sklearn_utils import positive_class_probabilities
from trainer.models.sklearn_utils import summarize_linear_weights


@dataclass(slots=True)
class StructuredSVMBaseline:
    model_name: str
    threshold: float
    vectorizer: DictVectorizer
    estimator: SVC
    metadata: dict[str, Any]

    def predict_proba(self, samples: list[SupervisedSample]) -> list[float]:
        rows = build_structured_feature_rows(samples)
        matrix = self.vectorizer.transform(rows)
        return positive_class_probabilities(self.estimator, matrix)

    def feature_summary(self) -> dict[str, Any]:
        feature_names = np.asarray(self.vectorizer.get_feature_names_out())
        return summarize_linear_weights(self.estimator, feature_names)

    def training_log(self) -> str:
        feature_count = len(self.vectorizer.get_feature_names_out())
        classes = ",".join(str(value) for value in self.estimator.classes_.tolist())
        return "\n".join(
            [
                "estimator=linear_svm",
                f"support_vectors={self.estimator.n_support_.tolist()}",
                f"feature_count={feature_count}",
                f"classes={classes}",
            ]
        )


def train_structured_svm_baseline(
    train_samples: list[SupervisedSample],
    model_config: ModelConfig,
) -> StructuredSVMBaseline:
    rows = build_structured_feature_rows(train_samples)
    labels = [1 if sample.binary_label == "blog" else 0 for sample in train_samples]
    vectorizer = DictVectorizer(sparse=True)
    matrix = vectorizer.fit_transform(rows)
    estimator = build_linear_svm(seed=model_config.seed, l2_strength=model_config.l2_strength)
    estimator.fit(matrix, labels)
    return StructuredSVMBaseline(
        model_name="structured_svm",
        threshold=model_config.threshold,
        vectorizer=vectorizer,
        estimator=estimator,
        metadata=model_config.to_dict(),
    )
