"""A tiny pure-Python sparse logistic regression implementation."""

from __future__ import annotations

from collections import Counter
import math
import random


def _sigmoid(value: float) -> float:
    clipped = max(min(value, 35.0), -35.0)
    return 1.0 / (1.0 + math.exp(-clipped))


class SparseLogisticRegression:
    """Train logistic regression over sparse feature dictionaries."""

    def __init__(
        self,
        *,
        learning_rate: float,
        l2_strength: float,
        epochs: int,
        seed: int,
    ) -> None:
        self.learning_rate = learning_rate
        self.l2_strength = l2_strength
        self.epochs = epochs
        self.seed = seed
        self.weights: dict[str, float] = {}
        self.bias = 0.0
        self.loss_history: list[float] = []

    def fit(self, rows: list[dict[str, float]], labels: list[int]) -> "SparseLogisticRegression":
        examples = list(zip(rows, labels))
        rng = random.Random(self.seed)
        if not examples:
            raise ValueError("Cannot fit logistic regression with no training rows")
        positive_count = sum(labels)
        negative_count = len(labels) - positive_count
        class_weight = {
            0: (len(labels) / (2 * max(1, negative_count))),
            1: (len(labels) / (2 * max(1, positive_count))),
        }
        for _ in range(self.epochs):
            rng.shuffle(examples)
            total_loss = 0.0
            for features, label in examples:
                score = self.decision_function(features)
                probability = _sigmoid(score)
                weight = class_weight[label]
                error = label - probability
                self.bias += self.learning_rate * error * weight
                for name, value in features.items():
                    current = self.weights.get(name, 0.0)
                    gradient = (error * value * weight) - (self.l2_strength * current)
                    self.weights[name] = current + self.learning_rate * gradient
                probability = min(max(probability, 1e-9), 1 - 1e-9)
                total_loss += -weight * ((label * math.log(probability)) + ((1 - label) * math.log(1 - probability)))
            self.loss_history.append(total_loss / len(examples))
        return self

    def decision_function(self, features: dict[str, float]) -> float:
        score = self.bias
        for name, value in features.items():
            score += self.weights.get(name, 0.0) * value
        return score

    def predict_proba(self, rows: list[dict[str, float]]) -> list[float]:
        return [_sigmoid(self.decision_function(features)) for features in rows]

    def top_weight_summary(self, *, limit: int = 20) -> dict[str, list[dict[str, float]]]:
        sorted_items = sorted(self.weights.items(), key=lambda item: item[1])
        negative = [{"feature": name, "weight": round(weight, 6)} for name, weight in sorted_items[:limit]]
        positive = [
            {"feature": name, "weight": round(weight, 6)}
            for name, weight in sorted(self.weights.items(), key=lambda item: item[1], reverse=True)[:limit]
        ]
        density = Counter("nonzero" if weight else "zero" for weight in self.weights.values())
        return {
            "positive_weights": positive,
            "negative_weights": negative,
            "weight_density": dict(density),
        }
