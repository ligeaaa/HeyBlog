"""Shared HTTP client helpers for cross-service request context."""

from __future__ import annotations

from shared.observability.logging import REQUEST_ID_HEADER
from shared.observability.logging import get_request_id


def context_headers() -> dict[str, str]:
    """Return headers that should be propagated to downstream services.

    Returns:
        A small header mapping containing the active request id when available,
        otherwise an empty mapping.
    """

    request_id = get_request_id()
    if not request_id:
        return {}
    return {REQUEST_ID_HEADER: request_id}


def context_header_kwargs() -> dict[str, dict[str, str]]:
    """Return request kwargs containing context headers only when needed.

    Returns:
        ``{"headers": ...}`` when a request id is active; otherwise an empty
        mapping so lightweight test doubles that do not accept ``headers`` keep
        working.
    """

    headers = context_headers()
    if not headers:
        return {}
    return {"headers": headers}
