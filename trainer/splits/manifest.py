"""Split manifest and stats helpers."""

from __future__ import annotations

from collections import Counter

from trainer.dataset.schema import SupervisedSample


def build_split_manifest(
    samples: list[SupervisedSample],
    *,
    split_seed: int,
    split_ratios: dict[str, float],
) -> dict[str, object]:
    counts_by_split: dict[str, dict[str, int]] = {}
    domains_by_split: dict[str, int] = {}
    for split in split_ratios:
        split_samples = [sample for sample in samples if sample.split == split]
        label_counts = Counter(sample.binary_label for sample in split_samples)
        counts_by_split[split] = dict(sorted(label_counts.items()))
        domains_by_split[split] = len({sample.domain for sample in split_samples})
    return {
        "split_seed": split_seed,
        "split_ratios": split_ratios,
        "sample_counts": {split: len([sample for sample in samples if sample.split == split]) for split in split_ratios},
        "label_counts": counts_by_split,
        "domain_counts": domains_by_split,
    }
