"""One-step Qwen embedding cache, training, and evaluation pipeline."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from pathlib import Path
import sys
from typing import Any

from trainer.config import DatasetConfig
from trainer.config import qwen_embedding_lr_model_config
from trainer.constants import DEFAULT_RUN_ROOT
from trainer.evaluation.reports import build_full_run_summary
from trainer.io.artifact_writer import ensure_dir
from trainer.io.artifact_writer import write_json
from trainer.io.artifact_writer import write_text
from trainer.pipelines.build_embeddings import run_build_embeddings
from trainer.pipelines.evaluate_run import run_evaluate_run
from trainer.pipelines.prepare_dataset import run_prepare_dataset
from trainer.pipelines.train_baseline import run_train_baseline


def default_qwen_embedding_pipeline_id() -> str:
    """Return one run id shared by embedding, training, and summary artifacts."""

    return datetime.now(timezone.utc).strftime("%y%m%d%H%M")


def run_qwen_embedding_pipeline(
    *,
    source_csv: Path,
    dataset_version: str | None = None,
    run_id: str | None = None,
    dataset_config: DatasetConfig | None = None,
    summary_dir: Path | None = None,
) -> dict[str, Any]:
    """Run the complete Qwen embedding classifier pipeline.

    Args:
        source_csv: Raw label CSV containing `url`, `title`, `label`, and `text` columns.
        dataset_version: Optional prepared dataset version name.
        run_id: Optional shared id for embedding/model/summary directories.

    Returns:
        Summary paths and metrics for the completed pipeline.
    """

    pipeline_id = run_id or default_qwen_embedding_pipeline_id()
    config = qwen_embedding_lr_model_config()
    print(f"[qwen-pipeline] run_id={pipeline_id}", file=sys.stderr, flush=True)
    print(f"[qwen-pipeline] source_csv={source_csv}", file=sys.stderr, flush=True)

    prepared = run_prepare_dataset(source_csv=source_csv, dataset_version=dataset_version, config=dataset_config)
    dataset_dir = Path(str(prepared["dataset_dir"]))
    embedding_dir = config.embedding_root / "qwen_embedding_lr" / pipeline_id
    model_dir = config.run_root / "qwen_embedding_lr" / pipeline_id
    full_run_dir = ensure_dir(summary_dir or DEFAULT_RUN_ROOT / f"{pipeline_id}--qwen-embedding-run")

    print(f"[qwen-pipeline] dataset_dir={dataset_dir}", file=sys.stderr, flush=True)
    embedding_result = run_build_embeddings(dataset_dir=dataset_dir, output_dir=embedding_dir, model_config=config)
    manifest_path = Path(str(embedding_result["manifest_path"]))
    print(f"[qwen-pipeline] manifest_path={manifest_path}", file=sys.stderr, flush=True)

    train_result = run_train_baseline(
        dataset_dir=dataset_dir,
        model_name="qwen_embedding_lr",
        output_dir=model_dir,
        embedding_manifest=manifest_path,
    )
    evaluation = run_evaluate_run(run_dir=Path(str(train_result["run_dir"])))
    write_json(
        full_run_dir / "summary.json",
        {
            "dataset": prepared,
            "embeddings": embedding_result,
            "training": train_result,
            "evaluation": evaluation,
        },
    )
    write_text(full_run_dir / "report.md", build_full_run_summary([evaluation]))
    print(f"[qwen-pipeline] completed summary_dir={full_run_dir}", file=sys.stderr, flush=True)
    return {
        "dataset_dir": str(dataset_dir),
        "embedding_dir": str(embedding_dir),
        "manifest_path": str(manifest_path),
        "run_dir": str(train_result["run_dir"]),
        "summary_dir": str(full_run_dir),
        "evaluation": evaluation,
    }
