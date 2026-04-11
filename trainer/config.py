"""Typed configuration for trainer pipelines."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trainer.constants import DEFAULT_DATASET_ROOT
from trainer.constants import DEFAULT_L2_STRENGTH
from trainer.constants import DEFAULT_LEARNING_RATE
from trainer.constants import DEFAULT_MIN_DF
from trainer.constants import DEFAULT_NEGATIVE_LABELS
from trainer.constants import DEFAULT_POSITIVE_LABELS
from trainer.constants import DEFAULT_RANDOM_SEED
from trainer.constants import DEFAULT_RUN_ROOT
from trainer.constants import DEFAULT_SPLIT_RATIOS
from trainer.constants import DEFAULT_STRUCTURED_EPOCHS
from trainer.constants import DEFAULT_TFIDF_EPOCHS
from trainer.constants import DEFAULT_THRESHOLD
from trainer.constants import DEFAULT_TITLE_WORD_NGRAM_RANGE
from trainer.constants import DEFAULT_URL_CHAR_NGRAM_RANGE


@dataclass(slots=True)
class DatasetConfig:
    source_csv: Path
    dataset_root: Path = DEFAULT_DATASET_ROOT
    positive_labels: tuple[str, ...] = DEFAULT_POSITIVE_LABELS
    negative_labels: tuple[str, ...] = DEFAULT_NEGATIVE_LABELS
    split_seed: int = DEFAULT_RANDOM_SEED
    split_ratios: dict[str, float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.split_ratios is None:
            self.split_ratios = dict(DEFAULT_SPLIT_RATIOS)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source_csv"] = str(self.source_csv)
        payload["dataset_root"] = str(self.dataset_root)
        return payload


@dataclass(slots=True)
class ModelConfig:
    model_name: str
    run_root: Path = DEFAULT_RUN_ROOT
    seed: int = DEFAULT_RANDOM_SEED
    threshold: float = DEFAULT_THRESHOLD
    epochs: int = DEFAULT_STRUCTURED_EPOCHS
    learning_rate: float = DEFAULT_LEARNING_RATE
    l2_strength: float = DEFAULT_L2_STRENGTH
    url_char_ngram_range: tuple[int, int] = DEFAULT_URL_CHAR_NGRAM_RANGE
    title_word_ngram_range: tuple[int, int] = DEFAULT_TITLE_WORD_NGRAM_RANGE
    min_df: int = DEFAULT_MIN_DF

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["run_root"] = str(self.run_root)
        return payload


def structured_model_config() -> ModelConfig:
    return ModelConfig(model_name="structured", epochs=DEFAULT_STRUCTURED_EPOCHS)


def tfidf_model_config() -> ModelConfig:
    return ModelConfig(model_name="tfidf", epochs=DEFAULT_TFIDF_EPOCHS)
