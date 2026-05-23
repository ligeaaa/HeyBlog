"""Generate reusable Qwen embedding artifacts for prepared trainer datasets."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from pathlib import Path
import sys
from typing import Any

import numpy as np

from trainer.config import ModelConfig
from trainer.config import qwen_embedding_lr_model_config
from trainer.dataset.schema import SupervisedSample
from trainer.features.embedding_features import BLOG_CLASSIFICATION_INSTRUCTION
from trainer.features.embedding_features import QwenEmbeddingEncoder
from trainer.io.artifact_writer import ensure_dir
from trainer.io.artifact_writer import write_json
from trainer.io.dataset_reader import read_jsonl


def _deserialize_samples(rows: list[dict[str, object]]) -> list[SupervisedSample]:
    """Deserialize prepared JSONL rows into supervised samples."""

    return [SupervisedSample(**row) for row in rows]


def default_embedding_run_id() -> str:
    """Return a timestamp identifier for one embedding generation run."""

    return datetime.now(timezone.utc).strftime("%y%m%d%H%M")


def _read_all_split_samples(dataset_dir: Path) -> list[SupervisedSample]:
    """Load train, val, and test samples in stable split order."""

    samples: list[SupervisedSample] = []
    for split in ("train", "val", "test"):
        split_samples = _deserialize_samples(read_jsonl(dataset_dir / f"{split}.jsonl"))
        samples.extend(split_samples)
    return samples


def run_build_embeddings(
    *,
    dataset_dir: Path,
    output_dir: Path | None = None,
    model_config: ModelConfig | None = None,
    encoder: QwenEmbeddingEncoder | None = None,
) -> dict[str, Any]:
    """Generate and save Qwen embeddings for a prepared dataset.

    Args:
        dataset_dir: Prepared trainer dataset directory containing split JSONL files.
        output_dir: Optional destination directory for embedding artifacts.
        model_config: Optional model config for overriding embedding parameters.

    Returns:
        Artifact metadata including the embedding manifest path.
    """

    config = model_config or qwen_embedding_lr_model_config()
    run_dir = ensure_dir(output_dir or config.embedding_root / "qwen_embedding_lr" / default_embedding_run_id())
    samples = _read_all_split_samples(dataset_dir)
    print(f"[embeddings] dataset_dir={dataset_dir}", file=sys.stderr, flush=True)
    print(f"[embeddings] output_dir={run_dir}", file=sys.stderr, flush=True)
    print(f"[embeddings] loaded samples={len(samples)}", file=sys.stderr, flush=True)

    encoder = encoder or QwenEmbeddingEncoder(
        model_name=config.text_embedding_model_name,
        max_length=config.text_embedding_max_length,
        max_text_chars=config.text_embedding_max_text_chars,
        batch_size=config.text_embedding_batch_size,
        task_description=BLOG_CLASSIFICATION_INSTRUCTION,
    )
    matrix = encoder.encode_with_progress(samples)
    matrix_path = run_dir / "embeddings.npz"
    np.savez_compressed(
        matrix_path,
        embeddings=matrix.astype(np.float32, copy=False),
        sample_ids=np.asarray([sample.sample_id for sample in samples], dtype=str),
    )
    manifest = {
        "dataset_dir": str(dataset_dir),
        "matrix_path": matrix_path.name,
        "sample_count": len(samples),
        "embedding_dim": int(matrix.shape[1]) if matrix.ndim == 2 and matrix.shape[0] else 0,
        "model_name": config.text_embedding_model_name,
        "max_length": config.text_embedding_max_length,
        "max_text_chars": config.text_embedding_max_text_chars,
        "batch_size": config.text_embedding_batch_size,
        "task_description": BLOG_CLASSIFICATION_INSTRUCTION,
        "input_fields": ["normalized_url", "domain", "title", "text"],
    }
    manifest_path = run_dir / "manifest.json"
    write_json(manifest_path, manifest)
    print(f"[embeddings] saved matrix={matrix_path}", file=sys.stderr, flush=True)
    print(f"[embeddings] saved manifest={manifest_path}", file=sys.stderr, flush=True)
    return {
        "embedding_dir": str(run_dir),
        "manifest_path": str(manifest_path),
        "dataset_dir": str(dataset_dir),
        "sample_count": len(samples),
        "embedding_dim": manifest["embedding_dim"],
    }
