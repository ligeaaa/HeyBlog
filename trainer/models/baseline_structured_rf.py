"""Legacy structured random-forest model class for runtime unpickling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction import DictVectorizer

from trainer.models.features import build_structured_feature_rows
from trainer.models.sklearn_utils import positive_class_probabilities


@dataclass(slots=True)
class StructuredRandomForestBaseline:
    """Structured random-forest baseline compatible with legacy artifacts."""

    model_name: str
    threshold: float
    vectorizer: DictVectorizer
    estimator: RandomForestClassifier
    metadata: dict[str, Any]

    def predict_proba(self, samples: list[object]) -> list[float]:
        """Return blog probabilities for runtime samples."""
        return positive_class_probabilities(self.estimator, self.vectorizer.transform(build_structured_feature_rows(samples)))

