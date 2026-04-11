"""Domain-aware split assignment."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
import random

from trainer.dataset.schema import SupervisedSample


def _split_counts(samples: list[SupervisedSample]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for sample in samples:
        counts[sample.binary_label] += 1
    return counts


def assign_group_splits(
    samples: list[SupervisedSample],
    *,
    seed: int,
    ratios: dict[str, float],
) -> list[SupervisedSample]:
    groups: dict[str, list[SupervisedSample]] = {}
    for sample in samples:
        groups.setdefault(sample.domain, []).append(sample)

    global_total = len(samples)
    global_positive = sum(1 for sample in samples if sample.binary_label == "blog")
    global_positive_ratio = (global_positive / global_total) if global_total else 0.0
    targets = {split: ratios[split] * global_total for split in ratios}

    rng = random.Random(seed)
    domain_items = list(groups.items())
    rng.shuffle(domain_items)
    domain_items.sort(key=lambda item: (-len(item[1]), item[0]))

    allocations = {split: [] for split in ratios}
    total_by_split = Counter()
    positive_by_split = Counter()

    for domain, domain_samples in domain_items:
        group_total = len(domain_samples)
        group_positive = sum(1 for sample in domain_samples if sample.binary_label == "blog")
        candidate_scores: list[tuple[float, float, str]] = []
        for split in ratios:
            new_total = total_by_split[split] + group_total
            new_positive = positive_by_split[split] + group_positive
            positive_ratio = (new_positive / new_total) if new_total else 0.0
            remaining_capacity = targets[split] - total_by_split[split]
            remaining_ratio = remaining_capacity / max(targets[split], 1.0)
            ratio_penalty = abs(positive_ratio - global_positive_ratio)
            candidate_scores.append((remaining_ratio, -ratio_penalty, split))
        _, _, chosen_split = max(candidate_scores, key=lambda item: (item[0], item[1], item[2]))
        allocations[chosen_split].append(domain)
        total_by_split[chosen_split] += group_total
        positive_by_split[chosen_split] += group_positive

    domain_to_split = {
        domain: split
        for split, domains in allocations.items()
        for domain in domains
    }
    assigned = [replace(sample, split=domain_to_split[sample.domain]) for sample in samples]
    return _rebalance_if_needed(assigned, ratios)


def _rebalance_if_needed(samples: list[SupervisedSample], ratios: dict[str, float]) -> list[SupervisedSample]:
    by_split = {split: [sample for sample in samples if sample.split == split] for split in ratios}
    empties = [split for split, values in by_split.items() if not values]
    if not empties:
        return samples
    donors = sorted((split for split in ratios if by_split[split]), key=lambda split: len(by_split[split]), reverse=True)
    domain_to_split = {sample.domain: sample.split for sample in samples}
    for empty_split in empties:
        for donor in donors:
            donor_domains = {}
            for sample in by_split[donor]:
                donor_domains.setdefault(sample.domain, []).append(sample)
            movable = sorted(donor_domains.items(), key=lambda item: len(item[1]))
            if not movable:
                continue
            domain, _ = movable[0]
            domain_to_split[domain] = empty_split
            break
    return [replace(sample, split=domain_to_split[sample.domain]) for sample in samples]
