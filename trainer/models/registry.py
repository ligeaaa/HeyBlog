"""Lookup table for supported trainer baselines."""

from __future__ import annotations

from pathlib import Path

from trainer.config import ModelConfig
from trainer.dataset.schema import SupervisedSample
from trainer.models.baseline_structured import StructuredBaseline
from trainer.models.baseline_structured import train_structured_baseline
from trainer.models.baseline_structured_rf import StructuredRandomForestBaseline
from trainer.models.baseline_structured_rf import train_structured_rf_baseline
from trainer.models.baseline_structured_svm import StructuredSVMBaseline
from trainer.models.baseline_structured_svm import train_structured_svm_baseline
from trainer.models.baseline_embedding import EmbeddingBaseline
from trainer.models.baseline_embedding import train_embedding_baseline
from trainer.models.baseline_tfidf_nb import TfidfNaiveBayesBaseline
from trainer.models.baseline_tfidf_nb import train_tfidf_nb_baseline
from trainer.models.baseline_tfidf import TfidfBaseline
from trainer.models.baseline_tfidf import train_tfidf_baseline
from trainer.models.baseline_tfidf_svm import TfidfSVMBaseline
from trainer.models.baseline_tfidf_svm import train_tfidf_svm_baseline


SupportedModel = (
    StructuredBaseline
    | StructuredSVMBaseline
    | StructuredRandomForestBaseline
    | TfidfBaseline
    | TfidfSVMBaseline
    | TfidfNaiveBayesBaseline
    | EmbeddingBaseline
)


def train_model(
    model_name: str,
    train_samples: list[SupervisedSample],
    model_config: ModelConfig,
    *,
    embedding_manifest: Path | None = None,
) -> SupportedModel:
    if model_name == "structured":
        return train_structured_baseline(train_samples, model_config)
    if model_name == "structured_lr":
        return train_structured_baseline(train_samples, model_config)
    if model_name == "structured_svm":
        return train_structured_svm_baseline(train_samples, model_config)
    if model_name == "structured_rf":
        return train_structured_rf_baseline(train_samples, model_config)
    if model_name == "tfidf":
        return train_tfidf_baseline(train_samples, model_config)
    if model_name == "tfidf_lr":
        return train_tfidf_baseline(train_samples, model_config)
    if model_name == "tfidf_svm":
        return train_tfidf_svm_baseline(train_samples, model_config)
    if model_name == "tfidf_nb":
        return train_tfidf_nb_baseline(train_samples, model_config)
    if model_name == "qwen_embedding_lr":
        return train_embedding_baseline(train_samples, model_config, embedding_manifest=embedding_manifest)
    raise ValueError(f"Unsupported trainer model: {model_name}")
