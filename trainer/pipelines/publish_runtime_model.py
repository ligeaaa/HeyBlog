"""Publish trained trainer runs into runtime_resources."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from pathlib import Path
import shutil
from typing import Any

from trainer.io.artifact_writer import ensure_dir
from trainer.io.artifact_writer import write_json
from trainer.io.dataset_reader import read_json


RUNTIME_MODEL_FILENAMES = (
    "model.joblib",
    "config.json",
    "metrics.json",
    "confusion_matrix.json",
    "feature_summary.json",
    "report.md",
    "train.log",
)


def _copy_runtime_files(run_dir: Path, destination: Path) -> list[str]:
    """Copy runtime-relevant files from a trained run directory.

    Args:
        run_dir: Source trainer run directory.
        destination: Target runtime model directory.

    Returns:
        Sorted list of copied file names.
    """

    copied: list[str] = []
    for filename in RUNTIME_MODEL_FILENAMES:
        source = run_dir / filename
        if not source.exists():
            continue
        shutil.copy2(source, destination / filename)
        copied.append(filename)
    return copied


def publish_runtime_model(
    *,
    run_dir: Path,
    runtime_root: Path = Path("runtime_resources/models/url_decision/current"),
    model_name: str | None = None,
) -> dict[str, Any]:
    """Publish one trained run to the runtime model root.

    Args:
        run_dir: Trainer run directory containing ``model.joblib`` and
            evaluation artifacts.
        runtime_root: Runtime model root loaded by crawler consensus.
        model_name: Optional destination model directory name. Defaults to the
            model name recorded in ``config.json``.

    Returns:
        Manifest payload describing the copied model.
    """

    config = read_json(run_dir / "config.json")
    metrics = read_json(run_dir / "metrics.json") if (run_dir / "metrics.json").exists() else {}
    resolved_model_name = model_name or str(config["model_name"])
    run_id = run_dir.name
    destination = ensure_dir(runtime_root / resolved_model_name / run_id)
    copied_files = _copy_runtime_files(run_dir, destination)
    if "model.joblib" not in copied_files:
        raise FileNotFoundError(f"missing model.joblib in {run_dir}")

    manifest = {
        "published_at": datetime.now(timezone.utc).isoformat(),
        "source_run_dir": str(run_dir),
        "runtime_root": str(runtime_root),
        "model_name": resolved_model_name,
        "run_id": run_id,
        "destination": str(destination),
        "copied_files": copied_files,
        "dataset_dir": config.get("dataset_dir"),
        "selected_threshold": config.get("selected_threshold"),
        "metrics": metrics,
    }
    write_json(destination / "runtime_manifest.json", manifest)
    write_json(runtime_root / "latest_manifest.json", manifest)
    return manifest
