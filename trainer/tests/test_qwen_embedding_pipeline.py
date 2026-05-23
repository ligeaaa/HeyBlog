from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from trainer.config import DatasetConfig
from trainer.config import qwen_embedding_lr_model_config
from trainer.pipelines.qwen_embedding_run import run_qwen_embedding_pipeline


class FakeEmbeddingEncoder:
    def encode_with_progress(self, samples: list[Any]) -> np.ndarray[Any, Any]:
        rows: list[list[float]] = []
        for item in samples:
            text = f"{item.normalized_url} {item.title} {item.text}".lower()
            rows.append(
                [
                    1.0 if "blog" in text or "notes" in text or "journal" in text else 0.0,
                    1.0 if "company" in text or "product" in text else 0.0,
                    float(len(item.text) > 10),
                ]
            )
        return np.asarray(rows, dtype=np.float32)


def test_qwen_embedding_pipeline_uses_one_manifest(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "labels-with-text.csv"
    source.write_text(
        "\n".join(
            [
                "url,title,label,text",
                "https://blog.alpha.example/,Alpha Blog,blog,alpha personal posts",
                "https://alpha.example/company,Alpha Inc,others,alpha product page",
                "https://notes.beta.example/,Beta Notes,blog,beta journal",
                "https://beta.example/about,About Beta,others,beta company",
                "https://journal.gamma.example/,Gamma Journal,blog,gamma essays",
                "https://gamma.example/team,Gamma Team,others,gamma team page",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = qwen_embedding_lr_model_config()
    config.embedding_root = tmp_path / "embeddings"
    config.run_root = tmp_path / "models"
    monkeypatch.setattr("trainer.pipelines.qwen_embedding_run.qwen_embedding_lr_model_config", lambda: config)
    monkeypatch.setattr("trainer.pipelines.build_embeddings.QwenEmbeddingEncoder", lambda **kwargs: FakeEmbeddingEncoder())

    result = run_qwen_embedding_pipeline(
        source_csv=source,
        dataset_version="test-with-text",
        run_id="test-run",
        dataset_config=DatasetConfig(source_csv=source, dataset_root=tmp_path / "datasets"),
        summary_dir=tmp_path / "runs" / "test-run--qwen-embedding-run",
    )

    manifest_path = Path(result["manifest_path"])
    run_dir = Path(result["run_dir"])
    config_payload = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    assert manifest_path == tmp_path / "embeddings" / "qwen_embedding_lr" / "test-run" / "manifest.json"
    assert config_payload["embedding_manifest"] == str(manifest_path)
    assert (run_dir / "metrics.json").exists()
