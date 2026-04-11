"""Prepare trainer dataset artifacts from the raw CSV export."""

from __future__ import annotations

from pathlib import Path

from trainer.config import DatasetConfig
from trainer.dataset.builder import aggregate_rows
from trainer.dataset.builder import build_resolution_records
from trainer.dataset.builder import build_supervised_samples
from trainer.dataset.stats import build_dataset_stats
from trainer.dataset.validators import validate_aggregated_samples
from trainer.dataset.validators import validate_resolution_records
from trainer.dataset.validators import validate_split_samples
from trainer.io.artifact_writer import ensure_dir
from trainer.io.artifact_writer import write_json
from trainer.io.artifact_writer import write_jsonl
from trainer.io.dataset_export import discover_latest_export
from trainer.io.dataset_export import load_raw_label_rows
from trainer.io.dataset_export import stage_raw_export
from trainer.labeling.label_mapping import default_mapping
from trainer.splits.group_split import assign_group_splits
from trainer.splits.manifest import build_split_manifest


def default_dataset_version(source_csv: Path) -> str:
    return f"{source_csv.stem}-baseline-v1"


def run_prepare_dataset(
    *,
    source_csv: Path | None = None,
    dataset_version: str | None = None,
    config: DatasetConfig | None = None,
) -> dict[str, object]:
    source = source_csv or discover_latest_export()
    dataset_config = config or DatasetConfig(source_csv=source)
    version = dataset_version or default_dataset_version(source)
    dataset_dir = ensure_dir(dataset_config.dataset_root / version)
    mapping = default_mapping()
    raw_rows = load_raw_label_rows(source)
    aggregated = aggregate_rows(raw_rows, mapping)
    validate_aggregated_samples(aggregated)
    resolution_records = build_resolution_records(aggregated, mapping)
    validate_resolution_records(resolution_records)
    supervised_samples = build_supervised_samples(resolution_records)
    supervised_with_splits = assign_group_splits(
        supervised_samples,
        seed=dataset_config.split_seed,
        ratios=dataset_config.split_ratios,
    )
    validate_split_samples(supervised_with_splits)
    dataset_stats = build_dataset_stats(resolution_records, supervised_with_splits)
    split_manifest = build_split_manifest(
        supervised_with_splits,
        split_seed=dataset_config.split_seed,
        split_ratios=dataset_config.split_ratios,
    )

    stage_raw_export(source, dataset_dir)
    write_jsonl(dataset_dir / "label_resolution.jsonl", [record.to_dict() for record in resolution_records])
    write_jsonl(dataset_dir / "full_supervised.jsonl", [sample.to_dict() for sample in supervised_with_splits])
    for split in ("train", "val", "test"):
        rows = [sample.to_dict() for sample in supervised_with_splits if sample.split == split]
        write_jsonl(dataset_dir / f"{split}.jsonl", rows)
    write_json(dataset_dir / "dataset_stats.json", dataset_stats)
    write_json(dataset_dir / "split_manifest.json", split_manifest)
    write_json(dataset_dir / "dataset_config.json", dataset_config.to_dict() | {"dataset_version": version})

    return {
        "dataset_dir": str(dataset_dir),
        "dataset_version": version,
        "dataset_stats": dataset_stats,
        "split_manifest": split_manifest,
    }
