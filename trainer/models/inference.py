"""Model serialization and generic prediction helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trainer.dataset.schema import SupervisedSample
from trainer.io.artifact_writer import read_pickle
from trainer.io.artifact_writer import write_pickle


@dataclass(slots=True)
class PredictionRow:
    sample_id: str
    url: str
    title: str
    domain: str
    raw_labels: list[str]
    gold_label: str
    pred_label: str
    prob_blog: float
    split: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "url": self.url,
            "title": self.title,
            "domain": self.domain,
            "raw_labels": ",".join(self.raw_labels),
            "gold_label": self.gold_label,
            "pred_label": self.pred_label,
            "prob_blog": round(self.prob_blog, 6),
            "split": self.split,
        }


def save_model(path: Path, model: Any) -> None:
    write_pickle(path, model)


def load_model(path: Path) -> Any:
    return read_pickle(path)


def build_prediction_rows(
    samples: list[SupervisedSample],
    probabilities: list[float],
    *,
    threshold: float,
) -> list[PredictionRow]:
    rows: list[PredictionRow] = []
    for sample, probability in zip(samples, probabilities, strict=True):
        pred_label = "blog" if probability >= threshold else "non_blog"
        rows.append(
            PredictionRow(
                sample_id=sample.sample_id,
                url=sample.url,
                title=sample.title,
                domain=sample.domain,
                raw_labels=list(sample.raw_labels),
                gold_label=sample.binary_label,
                pred_label=pred_label,
                prob_blog=probability,
                split=sample.split or "unknown",
            )
        )
    return rows
