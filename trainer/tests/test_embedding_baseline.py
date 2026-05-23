from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from trainer.config import qwen_embedding_lr_model_config
from trainer.features.embedding_features import build_embedding_input_texts
from trainer.features.embedding_store import CachedEmbeddingEncoder
from trainer.models.baseline_embedding import train_embedding_baseline
from trainer.models.registry import train_model
from trainer.pipelines.build_embeddings import run_build_embeddings
from trainer.tests.helpers import sample


class FakeEmbeddingEncoder:
    def encode(self, samples: list[Any]) -> np.ndarray[Any, Any]:
        rows: list[list[float]] = []
        for item in samples:
            text = f"{item.normalized_url} {item.title} {item.text}".lower()
            rows.append(
                [
                    1.0 if "blog" in text or "notes" in text or "journal" in text else 0.0,
                    1.0 if "company" in text or "product" in text or "pricing" in text else 0.0,
                    float(len(item.text) > 20),
                ]
            )
        return np.asarray(rows, dtype=np.float32)

    def encode_with_progress(self, samples: list[Any]) -> np.ndarray[Any, Any]:
        return self.encode(samples)


def test_embedding_input_includes_url_title_and_bounded_text() -> None:
    samples = [
        sample(
            "https://blog.alpha.example/",
            "Alpha Notes",
            "blog",
            text="first line\nsecond line with blog posts",
        )
    ]

    [text] = build_embedding_input_texts(samples, max_text_chars=18)

    assert text.startswith("Instruct: Given a web page URL")
    assert "URL: https://blog.alpha.example/" in text
    assert "Title: Alpha Notes" in text
    assert "Text: first line second " in text
    assert "with blog posts" not in text


def test_embedding_baseline_can_fit_and_predict_with_injected_encoder() -> None:
    samples = [
        sample("https://blog.alpha.example/", "Alpha Blog", "blog", text="personal notes and blog posts"),
        sample("https://alpha.example/company", "Alpha Inc", "non_blog", text="company product pricing"),
        sample("https://notes.beta.example/", "Beta Notes", "blog", text="journal entries"),
        sample("https://corp.beta.example/about", "About Beta", "non_blog", text="company profile"),
    ]
    model = train_embedding_baseline(
        samples,
        qwen_embedding_lr_model_config(),
        encoder=FakeEmbeddingEncoder(),
    )

    probabilities = model.predict_proba(samples)

    assert model.model_name == "qwen_embedding_lr"
    assert len(probabilities) == 4
    assert all(0.0 <= probability <= 1.0 for probability in probabilities)
    assert model.metadata["embedding_input_fields"] == ["normalized_url", "domain", "title", "text"]


def test_registry_supports_qwen_embedding_model_with_cache(tmp_path) -> None:
    samples = [
        sample("https://blog.alpha.example/", "Alpha Blog", "blog", text="personal blog"),
        sample("https://alpha.example/company", "Alpha Inc", "non_blog", text="company product"),
        sample("https://notes.beta.example/", "Beta Notes", "blog", text="notes journal"),
        sample("https://corp.beta.example/about", "About Beta", "non_blog", text="company profile"),
    ]
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    rows = [item.to_dict() for item in samples]
    (dataset_dir / "train.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    (dataset_dir / "val.jsonl").write_text("", encoding="utf-8")
    (dataset_dir / "test.jsonl").write_text("", encoding="utf-8")
    result = run_build_embeddings(dataset_dir=dataset_dir, output_dir=tmp_path / "embeddings", encoder=FakeEmbeddingEncoder())

    model = train_model(
        "qwen_embedding_lr",
        samples,
        qwen_embedding_lr_model_config(),
        embedding_manifest=Path(str(result["manifest_path"])),
    )

    assert model.model_name == "qwen_embedding_lr"


def test_build_embeddings_writes_cache_and_training_reads_it(tmp_path) -> None:
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    rows = [
        sample("https://blog.alpha.example/", "Alpha Blog", "blog", text="personal blog").to_dict(),
        sample("https://alpha.example/company", "Alpha Inc", "non_blog", text="company product").to_dict(),
        sample("https://notes.beta.example/", "Beta Notes", "blog", text="notes journal").to_dict(),
        sample("https://corp.beta.example/about", "About Beta", "non_blog", text="company profile").to_dict(),
    ]
    (dataset_dir / "train.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    (dataset_dir / "val.jsonl").write_text("", encoding="utf-8")
    (dataset_dir / "test.jsonl").write_text("", encoding="utf-8")

    result = run_build_embeddings(
        dataset_dir=dataset_dir,
        output_dir=tmp_path / "embeddings",
        encoder=FakeEmbeddingEncoder(),
    )

    manifest_path = result["manifest_path"]
    model = train_embedding_baseline(
        [
            sample("https://blog.alpha.example/", "Alpha Blog", "blog", text="personal blog"),
            sample("https://alpha.example/company", "Alpha Inc", "non_blog", text="company product"),
            sample("https://notes.beta.example/", "Beta Notes", "blog", text="notes journal"),
            sample("https://corp.beta.example/about", "About Beta", "non_blog", text="company profile"),
        ],
        qwen_embedding_lr_model_config(),
        encoder=CachedEmbeddingEncoder(Path(manifest_path)),
    )

    assert result["sample_count"] == 4
    assert result["embedding_dim"] == 3
    assert model.metadata["embedding_source"] == "cached"
