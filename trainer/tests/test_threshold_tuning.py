from trainer.dataset.schema import SupervisedSample
from trainer.pipelines.train_baseline import _tune_threshold


class FixedProbabilityModel:
    """Tiny model stub used to exercise validation threshold tuning."""

    def __init__(self, probabilities: list[float]) -> None:
        self.probabilities = probabilities
        self.threshold = 0.5
        self.metadata: dict[str, float] = {}

    def predict_proba(self, samples: list[SupervisedSample]) -> list[float]:
        return self.probabilities[: len(samples)]


def _sample(index: int, label: str) -> SupervisedSample:
    return SupervisedSample(
        sample_id=f"sample-{index}",
        url=f"https://example.com/{index}",
        normalized_url=f"https://example.com/{index}",
        domain="example.com",
        title=f"Sample {index}",
        raw_labels=[label],
        binary_label=label,
        resolution_status="mapped",
        resolution_reason="test",
        title_missing=False,
        split="val",
    )


def test_tune_threshold_updates_model_and_metadata() -> None:
    samples = [
        _sample(1, "blog"),
        _sample(2, "blog"),
        _sample(3, "non_blog"),
        _sample(4, "non_blog"),
    ]
    model = FixedProbabilityModel([0.45, 0.42, 0.40, 0.05])

    summary = _tune_threshold(model, samples)

    assert summary["threshold"] == 0.42
    assert summary["val_f1"] == 1.0
    assert model.threshold == 0.42
    assert model.metadata["selected_threshold"] == 0.42
