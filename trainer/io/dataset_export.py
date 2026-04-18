"""Source dataset discovery and raw CSV loading."""

from __future__ import annotations

import csv
from pathlib import Path

from trainer.constants import DEFAULT_DATA_ROOT
from trainer.constants import DEFAULT_SOURCE_GLOB
from trainer.dataset.schema import RawLabelRow
from trainer.io.artifact_writer import copy_file


def discover_latest_export(data_root: Path = DEFAULT_DATA_ROOT) -> Path:
    matches = sorted(data_root.glob(DEFAULT_SOURCE_GLOB))
    if not matches:
        raise FileNotFoundError(f"No labeled training CSV matched {DEFAULT_SOURCE_GLOB} under {data_root}")
    return matches[-1]


def load_raw_label_rows(path: Path) -> list[RawLabelRow]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: list[RawLabelRow] = []
        for raw in reader:
            rows.append(
                RawLabelRow(
                    url=str(raw.get("url", "")).strip(),
                    title=str(raw.get("title", "")).strip(),
                    label=str(raw.get("label", "")).strip(),
                )
            )
    return rows


def stage_raw_export(source_csv: Path, dataset_dir: Path) -> Path:
    destination = dataset_dir / "raw_export.csv"
    copy_file(source_csv, destination)
    return destination
