"""Lookup table for supported trainer baselines."""

from __future__ import annotations

from trainer.config import ModelConfig
from trainer.dataset.schema import SupervisedSample
from trainer.models.baseline_structured import StructuredBaseline
from trainer.models.baseline_structured import train_structured_baseline
from trainer.models.baseline_tfidf import TfidfBaseline
from trainer.models.baseline_tfidf import train_tfidf_baseline


SupportedModel = StructuredBaseline | TfidfBaseline


def train_model(
    model_name: str,
    train_samples: list[SupervisedSample],
    model_config: ModelConfig,
) -> SupportedModel:
    if model_name == "structured":
        return train_structured_baseline(train_samples, model_config)
    if model_name == "tfidf":
        return train_tfidf_baseline(train_samples, model_config)
    raise ValueError(f"Unsupported trainer model: {model_name}")
