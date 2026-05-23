"""Shared helpers for trainer tests."""

from __future__ import annotations

from trainer.dataset.schema import SupervisedSample


def sample(url: str, title: str, label: str, *, text: str = "") -> SupervisedSample:
    """Build a compact supervised sample for model and feature tests."""

    domain = url.split("/")[2]
    return SupervisedSample(
        sample_id=url,
        url=url,
        normalized_url=url,
        domain=domain,
        title=title,
        text=text,
        raw_labels=["blog" if label == "blog" else "others"],
        binary_label=label,
        resolution_status="mapped",
        resolution_reason="test",
        title_missing=not bool(title),
        split="train",
    )
