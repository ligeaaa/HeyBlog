"""Shared dataset dataclasses."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class RawLabelRow:
    url: str
    title: str
    label: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AggregatedSample:
    sample_id: str
    url: str
    normalized_url: str
    domain: str
    title: str
    raw_labels: list[str]
    title_missing: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ResolutionRecord:
    sample_id: str
    url: str
    normalized_url: str
    domain: str
    title: str
    raw_labels: list[str]
    binary_label: str | None
    resolution_status: str
    resolution_reason: str
    title_missing: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SupervisedSample:
    sample_id: str
    url: str
    normalized_url: str
    domain: str
    title: str
    raw_labels: list[str]
    binary_label: str
    resolution_status: str
    resolution_reason: str
    title_missing: bool
    split: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
