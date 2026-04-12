"""Shared low-level helpers for crawler modules."""

from __future__ import annotations

from collections.abc import Hashable
from collections.abc import Iterable
from typing import TypeVar


ValueT = TypeVar("ValueT", bound=Hashable)


def clean_text(value: str) -> str:
    """Normalize extracted text for matching and context handling.

    Args:
        value: Raw text captured from HTML content.

    Returns:
        The text collapsed to single spaces and stripped of surrounding
        whitespace.
    """
    return " ".join(value.split()).strip()


def text_contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    """Return whether lower-cased text contains any provided keyword.

    Args:
        text: Source text to inspect.
        keywords: Lower-case substrings that should trigger a match.

    Returns:
        ``True`` when any keyword is present in the normalized text.
    """
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def unique_in_order(values: Iterable[ValueT], *, limit: int | None = None) -> list[ValueT]:
    """Return the first unique values while preserving discovery order.

    Args:
        values: Iterable of hashable values that may contain duplicates.
        limit: Optional maximum number of unique values to return.

    Returns:
        A list containing unique values in the order they were first seen.
    """
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
