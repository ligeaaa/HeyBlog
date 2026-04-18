"""End-to-end trainer execution for both baselines."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from trainer.constants import DEFAULT_MODELS
from trainer.constants import DEFAULT_RUN_ROOT
from trainer.evaluation.reports import build_full_run_summary
from trainer.io.artifact_writer import ensure_dir
from trainer.io.artifact_writer import write_json
from trainer.io.artifact_writer import write_text
from trainer.pipelines.evaluate_run import run_evaluate_run
from trainer.pipelines.prepare_dataset import run_prepare_dataset
from trainer.pipelines.train_baseline import run_train_baseline


def run_full_pipeline(
    *,
    source_csv: Path | None = None,
    dataset_version: str | None = None,
) -> dict[str, object]:
    prepared = run_prepare_dataset(source_csv=source_csv, dataset_version=dataset_version)
    dataset_dir = Path(prepared["dataset_dir"])
    full_run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "--full-run"
    full_run_dir = ensure_dir(DEFAULT_RUN_ROOT / full_run_id)
    results: list[dict[str, object]] = []
    for model_name in DEFAULT_MODELS:
        train_result = run_train_baseline(dataset_dir=dataset_dir, model_name=model_name)
        model_run_dir = Path(train_result["run_dir"])
        results.append(run_evaluate_run(run_dir=model_run_dir))
    write_json(full_run_dir / "summary.json", {"dataset_dir": str(dataset_dir), "results": results})
    write_text(full_run_dir / "report.md", build_full_run_summary(results))
    return {
        "dataset_dir": str(dataset_dir),
        "full_run_dir": str(full_run_dir),
        "results": results,
    }
