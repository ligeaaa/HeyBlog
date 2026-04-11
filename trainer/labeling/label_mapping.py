"""Frozen binary label mapping for the first baseline."""

from __future__ import annotations

from dataclasses import dataclass

from trainer.constants import DEFAULT_NEGATIVE_LABELS
from trainer.constants import DEFAULT_POSITIVE_LABELS


@dataclass(slots=True)
class LabelMapping:
    positive_labels: frozenset[str]
    negative_labels: frozenset[str]

    def normalize(self, label: str) -> str:
        return label.strip().lower()

    def classify(self, label: str) -> str:
        normalized = self.normalize(label)
        if normalized in self.positive_labels:
            return "positive"
        if normalized in self.negative_labels:
            return "negative"
        return "excluded"


def default_mapping() -> LabelMapping:
    return LabelMapping(
        positive_labels=frozenset(DEFAULT_POSITIVE_LABELS),
        negative_labels=frozenset(DEFAULT_NEGATIVE_LABELS),
    )
