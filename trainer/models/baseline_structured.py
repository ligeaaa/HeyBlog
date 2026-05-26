"""Legacy structured logistic-regression model class for runtime unpickling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression

from trainer.models.features import build_structured_feature_rows
from trainer.models.sklearn_utils import positive_class_probabilities


@dataclass(slots=True)
class StructuredBaseline:
    """Structured-feature baseline compatible with legacy pickle artifacts."""

    model_name: str
    threshold: float
    vectorizer: DictVectorizer
    estimator: LogisticRegression
    metadata: dict[str, Any]

    def predict_proba(self, samples: list[object]) -> list[float]:
        """Return blog probabilities for runtime samples."""
        return positive_class_probabilities(self.estimator, self.vectorizer.transform(build_structured_feature_rows(samples)))

