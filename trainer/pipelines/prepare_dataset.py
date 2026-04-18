"""Prepare trainer dataset artifacts from the raw CSV export."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from typing import Iterable
from typing import Protocol

from trainer.config import DatasetConfig
from trainer.dataset.builder import aggregate_rows
from trainer.dataset.builder import build_resolution_records
from trainer.dataset.builder import build_supervised_samples
from trainer.dataset.schema import ResolutionRecord
from trainer.dataset.schema import SupervisedSample
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


class _SerializableRow(Protocol):
    def to_dict(self) -> dict[str, Any]:
        ...


def default_dataset_version(source_csv: Path) -> str:
    """Build the default dataset version name from the raw export filename."""
    return f"{source_csv.stem}-baseline-v1"


def _resolve_prepare_inputs(
    *,
    source_csv: Path | None,
    dataset_version: str | None,
    config: DatasetConfig | None,
) -> tuple[Path, DatasetConfig, str, Path]:
    source = source_csv or discover_latest_export()
    dataset_config = config or DatasetConfig(source_csv=source)
    version = dataset_version or default_dataset_version(source)
    dataset_dir = ensure_dir(dataset_config.dataset_root / version)
    return source, dataset_config, version, dataset_dir


def _serialize_rows(rows: Iterable[_SerializableRow]) -> list[dict[str, Any]]:
    return [row.to_dict() for row in rows]


def _build_dataset_outputs(
    source: Path,
    dataset_config: DatasetConfig,
) -> tuple[list[ResolutionRecord], list[SupervisedSample], dict[str, object], dict[str, object]]:
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
    return resolution_records, supervised_with_splits, dataset_stats, split_manifest


def _write_split_exports(
    dataset_dir: Path,
    supervised_rows: list[dict[str, Any]],
    split_names: Iterable[str],
) -> None:
    for split in split_names:
        rows = [row for row in supervised_rows if row["split"] == split]
        write_jsonl(dataset_dir / f"{split}.jsonl", rows)


def _write_dataset_artifacts(
    *,
    source: Path,
    dataset_dir: Path,
    version: str,
    dataset_config: DatasetConfig,
    resolution_records: list[ResolutionRecord],
    supervised_with_splits: list[SupervisedSample],
    dataset_stats: dict[str, object],
    split_manifest: dict[str, object],
) -> None:
    resolution_rows = _serialize_rows(resolution_records)
    supervised_rows = _serialize_rows(supervised_with_splits)

    stage_raw_export(source, dataset_dir)
    write_jsonl(dataset_dir / "label_resolution.jsonl", resolution_rows)
    write_jsonl(dataset_dir / "full_supervised.jsonl", supervised_rows)
    # Each split export mirrors the full supervised export, filtered by split assignment.
    _write_split_exports(dataset_dir, supervised_rows, dataset_config.split_ratios)
    write_json(dataset_dir / "dataset_stats.json", dataset_stats)
    write_json(dataset_dir / "split_manifest.json", split_manifest)
    write_json(dataset_dir / "dataset_config.json", dataset_config.to_dict() | {"dataset_version": version})


def run_prepare_dataset(
    *,
    source_csv: Path | None = None,
    dataset_version: str | None = None,
    config: DatasetConfig | None = None,
) -> dict[str, object]:
    """Generate validated dataset artifacts from the latest or provided raw label export."""

    source, dataset_config, version, dataset_dir = _resolve_prepare_inputs(
        source_csv=source_csv,
        dataset_version=dataset_version,
        config=config,
    )
    # Build all in-memory records first so validation happens before any artifact is written.
    resolution_records, supervised_with_splits, dataset_stats, split_manifest = _build_dataset_outputs(
        source,
        dataset_config,
    )
    _write_dataset_artifacts(
        source=source,
        dataset_dir=dataset_dir,
        version=version,
        dataset_config=dataset_config,
        resolution_records=resolution_records,
        supervised_with_splits=supervised_with_splits,
        dataset_stats=dataset_stats,
        split_manifest=split_manifest,
    )

    return {
        "dataset_dir": str(dataset_dir),
        "dataset_version": version,
        "dataset_stats": dataset_stats,
        "split_manifest": split_manifest,
    }
