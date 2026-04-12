"""Shared sklearn + numpy helpers for trainer baselines."""

from __future__ import annotations

from typing import Any
from typing import Iterable

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.naive_bayes import ComplementNB
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC


def identity_analyzer(document: Iterable[str]) -> list[str]:
    """Return pre-tokenized documents unchanged for sklearn vectorizers."""

    return list(document)


def build_logistic_regression(
    *,
    seed: int,
    epochs: int,
    l2_strength: float,
) -> LogisticRegression:
    """Create a deterministic binary logistic regression model for sparse trainer features."""

    regularization = max(l2_strength, 1e-6)
    return LogisticRegression(
        solver="liblinear",
        class_weight="balanced",
        random_state=seed,
        max_iter=max(100, epochs * 10),
        C=1.0 / regularization,
    )


def build_linear_svm(
    *,
    seed: int,
    l2_strength: float,
) -> SVC:
    """Create a linear SVM with probability output for sparse trainer features."""

    regularization = max(l2_strength, 1e-6)
    return SVC(
        kernel="linear",
        probability=True,
        class_weight="balanced",
        random_state=seed,
        C=1.0 / regularization,
    )


def build_complement_nb(*, alpha: float) -> ComplementNB:
    """Create a Complement Naive Bayes estimator for sparse TF-IDF features."""

    return ComplementNB(alpha=max(alpha, 1e-6))


def build_random_forest(
    *,
    seed: int,
    estimators: int,
) -> RandomForestClassifier:
    """Create a deterministic random forest for structured trainer features."""

    return RandomForestClassifier(
        n_estimators=max(estimators, 10),
        class_weight="balanced",
        random_state=seed,
        n_jobs=-1,
    )


def positive_class_probabilities(estimator: Any, matrix: Any) -> list[float]:
    """Return blog-class probabilities as plain Python floats."""

    class_list = estimator.classes_.tolist()
    positive_index = class_list.index(1)
    probabilities = np.asarray(estimator.predict_proba(matrix)[:, positive_index], dtype=float)
    return probabilities.tolist()


def summarize_weight_vector(
    weights: np.ndarray[Any, Any],
    feature_names: np.ndarray[Any, Any],
    *,
    limit: int = 20,
) -> dict[str, Any]:
    """Build a stable feature summary from a binary feature-weight vector."""

    if feature_names.size == 0:
        return {
            "positive_weights": [],
            "negative_weights": [],
            "weight_density": {"nonzero": 0, "zero": 0},
        }

    weights = np.asarray(weights, dtype=float)
    order = np.argsort(weights)
    positive_indices = order[::-1][:limit]
    negative_indices = order[:limit]
    nonzero_count = int(np.count_nonzero(weights))
    total_count = int(weights.size)

    def _rows(indices: np.ndarray[Any, Any]) -> list[dict[str, float | str]]:
        return [
            {
                "feature": str(feature_names[index]),
                "weight": round(float(weights[index]), 6),
            }
            for index in indices
        ]

    return {
        "positive_weights": _rows(positive_indices),
        "negative_weights": _rows(negative_indices),
        "weight_density": {"nonzero": nonzero_count, "zero": total_count - nonzero_count},
    }


def summarize_linear_weights(
    estimator: LogisticRegression | SVC,
    feature_names: np.ndarray[Any, Any],
    *,
    limit: int = 20,
) -> dict[str, Any]:
    """Build a stable feature summary from a linear estimator coefficient vector."""

    raw_weights = estimator.coef_[0]
    if hasattr(raw_weights, "toarray"):
        weight_vector = np.asarray(raw_weights.toarray()).ravel()
    else:
        weight_vector = np.asarray(raw_weights, dtype=float).ravel()
    return summarize_weight_vector(weight_vector, feature_names, limit=limit)


def summarize_feature_importances(
    estimator: RandomForestClassifier,
    feature_names: np.ndarray[Any, Any],
    *,
    limit: int = 20,
) -> dict[str, Any]:
    """Build a stable feature-importance summary for tree ensembles."""

    if feature_names.size == 0:
        return {"feature_importances": [], "importance_density": {"nonzero": 0, "zero": 0}}

    importances = np.asarray(estimator.feature_importances_, dtype=float)
    order = np.argsort(importances)[::-1][:limit]
    nonzero_count = int(np.count_nonzero(importances))
    total_count = int(importances.size)
    return {
        "feature_importances": [
            {"feature": str(feature_names[index]), "importance": round(float(importances[index]), 6)}
            for index in order
        ],
        "importance_density": {"nonzero": nonzero_count, "zero": total_count - nonzero_count},
    }


def build_training_log(estimator: LogisticRegression, *, feature_count: int) -> str:
    """Emit a compact text summary for the saved train.log artifact."""

    iterations = np.asarray(estimator.n_iter_, dtype=int).tolist()
    classes = ",".join(str(value) for value in estimator.classes_.tolist())
    return "\n".join(
        [
            f"solver={estimator.solver}",
            f"iterations={iterations}",
            f"feature_count={feature_count}",
            f"classes={classes}",
        ]
    )
