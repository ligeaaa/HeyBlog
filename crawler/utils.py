"""Shared low-level helpers for crawler modules."""

from __future__ import annotations

from collections.abc import Hashable
from collections.abc import Iterable
from typing import TypeVar


ValueT = TypeVar("ValueT", bound=Hashable)


def clean_text(value: str) -> str:
    """Normalize extracted text for matching and context handling."""
    return " ".join(value.split()).strip()


def text_contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    """Return True when lower-cased text contains any provided keyword."""
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def unique_in_order(values: Iterable[ValueT], *, limit: int | None = None) -> list[ValueT]:
    """Return the first unique values while preserving discovery order."""
    unique_values: list[ValueT] = []
    seen: set[ValueT] = set()

    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
        if limit is not None and len(unique_values) >= limit:
            break

    return unique_values
