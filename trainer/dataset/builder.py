"""Build trainer datasets from the raw label export CSV."""

from __future__ import annotations

from collections import defaultdict

from crawler.crawling.normalization import normalize_url
from trainer.dataset.schema import AggregatedSample
from trainer.dataset.schema import RawLabelRow
from trainer.dataset.schema import ResolutionRecord
from trainer.dataset.schema import SupervisedSample
from trainer.labeling.label_mapping import LabelMapping
from trainer.labeling.resolution import resolve_labels


def _pick_title(current: str, candidate: str) -> str:
    if candidate and not current:
        return candidate
    if candidate and len(candidate) > len(current):
        return candidate
    return current


def aggregate_rows(rows: list[RawLabelRow], mapping: LabelMapping) -> list[AggregatedSample]:
    buckets: dict[str, dict[str, object]] = defaultdict(
        lambda: {"url": "", "title": "", "labels": set(), "domain": "", "normalized_url": ""}
    )
    for row in rows:
        normalized = normalize_url(row.url)
        sample = buckets[normalized.normalized_url]
        sample["url"] = sample["url"] or row.url
        sample["normalized_url"] = normalized.normalized_url
        sample["domain"] = normalized.domain
        sample["title"] = _pick_title(str(sample["title"]), row.title)
        if row.label.strip():
            labels = sample["labels"]
            assert isinstance(labels, set)
            labels.add(mapping.normalize(row.label))

    aggregated: list[AggregatedSample] = []
    for normalized_url, payload in sorted(buckets.items()):
        title = str(payload["title"]).strip()
        aggregated.append(
            AggregatedSample(
                sample_id=normalized_url,
                url=str(payload["url"]),
                normalized_url=normalized_url,
                domain=str(payload["domain"]),
                title=title,
                raw_labels=sorted(str(label) for label in payload["labels"]),
                title_missing=not bool(title),
            )
        )
    return aggregated


def build_resolution_records(
    aggregated_samples: list[AggregatedSample],
    mapping: LabelMapping,
) -> list[ResolutionRecord]:
    records: list[ResolutionRecord] = []
    for sample in aggregated_samples:
        resolved = resolve_labels(sample.raw_labels, mapping)
        records.append(
            ResolutionRecord(
                sample_id=sample.sample_id,
                url=sample.url,
                normalized_url=sample.normalized_url,
                domain=sample.domain,
                title=sample.title,
                raw_labels=list(sample.raw_labels),
                binary_label=resolved.binary_label,
                resolution_status=resolved.resolution_status,
                resolution_reason=resolved.resolution_reason,
                title_missing=sample.title_missing,
            )
        )
    return records


def build_supervised_samples(resolution_records: list[ResolutionRecord]) -> list[SupervisedSample]:
    samples: list[SupervisedSample] = []
    for record in resolution_records:
        if record.resolution_status != "mapped" or record.binary_label is None:
            continue
        samples.append(
            SupervisedSample(
                sample_id=record.sample_id,
                url=record.url,
                normalized_url=record.normalized_url,
                domain=record.domain,
                title=record.title,
                raw_labels=list(record.raw_labels),
                binary_label=record.binary_label,
                resolution_status=record.resolution_status,
                resolution_reason=record.resolution_reason,
                title_missing=record.title_missing,
            )
        )
    return samples
