"""Legacy sklearn helpers referenced by runtime model pickles."""

from __future__ import annotations

from typing import Any
from typing import Iterable

import numpy as np


def identity_analyzer(document: Iterable[str]) -> list[str]:
    """Return pre-tokenized documents unchanged for sklearn vectorizers."""
    return list(document)


def positive_class_probabilities(estimator: Any, matrix: Any) -> list[float]:
    """Return blog-class probabilities as plain Python floats."""
    class_list = estimator.classes_.tolist()
    positive_index = class_list.index(1)
    probabilities = np.asarray(estimator.predict_proba(matrix)[:, positive_index], dtype=float)
    return probabilities.tolist()


def summarize_linear_weights(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Return an empty feature summary for runtime-only compatibility."""
    del args, kwargs
    return {}


def summarize_feature_importances(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Return an empty feature summary for runtime-only compatibility."""
    del args, kwargs
    return {}


def summarize_weight_vector(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Return an empty feature summary for runtime-only compatibility."""
    del args, kwargs
    return {}

