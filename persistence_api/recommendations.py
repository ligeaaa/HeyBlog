"""Recommendation helpers for blog discovery detail views."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from persistence_api.models import EdgeModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def collect_friends_of_friends_candidates(
    session: Session,
    *,
    blog_id: int,
    direct_outgoing_ids: set[int],
    excluded_blog_ids: set[int],
) -> dict[int, set[int]]:
    """Return candidate blog ids mapped to the direct neighbors that point to them."""
    if not direct_outgoing_ids:
        return {}

    candidate_edges = session.scalars(
        select(EdgeModel)
        .where(EdgeModel.from_blog_id.in_(direct_outgoing_ids))
        .order_by(EdgeModel.from_blog_id.asc(), EdgeModel.to_blog_id.asc())
    ).all()

    recommendation_map: dict[int, set[int]] = {}
    for edge in candidate_edges:
        candidate_id = int(edge.to_blog_id)
        via_blog_id = int(edge.from_blog_id)
        if candidate_id == blog_id or candidate_id in excluded_blog_ids:
            continue
        recommendation_map.setdefault(candidate_id, set()).add(via_blog_id)
    return recommendation_map
