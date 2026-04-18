"""Validation helpers for trainer datasets."""

from __future__ import annotations

from collections import Counter

from trainer.dataset.schema import AggregatedSample
from trainer.dataset.schema import ResolutionRecord
from trainer.dataset.schema import SupervisedSample


def validate_aggregated_samples(samples: list[AggregatedSample]) -> None:
    sample_ids = [sample.sample_id for sample in samples]
    duplicates = [sample_id for sample_id, count in Counter(sample_ids).items() if count > 1]
    if duplicates:
        raise ValueError(f"Duplicate aggregated sample ids detected: {duplicates[:3]}")
    for sample in samples:
        if not sample.url:
            raise ValueError("Encountered aggregated sample with empty url")
        if not sample.domain:
            raise ValueError(f"Encountered aggregated sample with empty domain: {sample.sample_id}")


def validate_resolution_records(records: list[ResolutionRecord]) -> None:
    sample_ids = [record.sample_id for record in records]
    duplicates = [sample_id for sample_id, count in Counter(sample_ids).items() if count > 1]
    if duplicates:
        raise ValueError(f"Duplicate resolution records detected: {duplicates[:3]}")


def validate_split_samples(samples: list[SupervisedSample]) -> None:
    domain_to_split: dict[str, str] = {}
    for sample in samples:
        if sample.split is None:
            raise ValueError(f"Sample missing split assignment: {sample.sample_id}")
        existing = domain_to_split.get(sample.domain)
        if existing is None:
            domain_to_split[sample.domain] = sample.split
            continue
        if existing != sample.split:
            raise ValueError(f"Domain leakage detected for {sample.domain}: {existing} vs {sample.split}")
