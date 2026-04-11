"""Resolve raw multi-label annotations into one binary supervision decision."""

from __future__ import annotations

from dataclasses import dataclass

from trainer.labeling.label_mapping import LabelMapping


@dataclass(slots=True)
class LabelResolution:
    binary_label: str | None
    resolution_status: str
    resolution_reason: str


def resolve_labels(labels: list[str], mapping: LabelMapping) -> LabelResolution:
    normalized = sorted({mapping.normalize(label) for label in labels if label.strip()})
    if not normalized:
        return LabelResolution(
            binary_label=None,
            resolution_status="unlabeled",
            resolution_reason="no_labels",
        )

    buckets = {mapping.classify(label) for label in normalized}
    if "positive" in buckets and "negative" in buckets:
        return LabelResolution(
            binary_label=None,
            resolution_status="conflict_review",
            resolution_reason="positive_and_negative_labels",
        )
    if len(buckets) > 1 and "excluded" in buckets:
        return LabelResolution(
            binary_label=None,
            resolution_status="conflict_review",
            resolution_reason="mapped_and_excluded_labels",
        )
    if buckets == {"positive"}:
        return LabelResolution(
            binary_label="blog",
            resolution_status="mapped",
            resolution_reason="positive_only",
        )
    if buckets == {"negative"}:
        return LabelResolution(
            binary_label="non_blog",
            resolution_status="mapped",
            resolution_reason="negative_only",
        )
    return LabelResolution(
        binary_label=None,
        resolution_status="excluded",
        resolution_reason="excluded_only",
    )
