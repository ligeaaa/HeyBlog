"""Dataset summary statistics."""

from __future__ import annotations

from collections import Counter

from trainer.dataset.schema import ResolutionRecord
from trainer.dataset.schema import SupervisedSample


def build_dataset_stats(
    resolution_records: list[ResolutionRecord],
    supervised_samples: list[SupervisedSample],
) -> dict[str, object]:
    raw_label_counts: Counter[str] = Counter()
    resolution_counts: Counter[str] = Counter()
    binary_counts: Counter[str] = Counter()
    title_missing_total = 0
    for record in resolution_records:
        resolution_counts[record.resolution_status] += 1
        title_missing_total += int(record.title_missing)
        for label in record.raw_labels:
            raw_label_counts[label] += 1
    for sample in supervised_samples:
        binary_counts[sample.binary_label] += 1
    total_records = len(resolution_records)
    return {
        "total_records": total_records,
        "supervised_records": len(supervised_samples),
        "resolution_counts": dict(sorted(resolution_counts.items())),
        "binary_label_counts": dict(sorted(binary_counts.items())),
        "raw_label_counts": dict(sorted(raw_label_counts.items())),
        "title_missing_count": title_missing_total,
        "title_missing_ratio": round(title_missing_total / total_records, 6) if total_records else 0.0,
    }
