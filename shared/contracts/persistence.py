"""Pydantic models shared across persistence service boundaries."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict

from shared.contracts.enums import CrawlStatus


class ContractModel(BaseModel):
    """Shared base model with permissive extra-field handling."""

    model_config = ConfigDict(extra="ignore")


class BlogCreate(ContractModel):
    url: str
    normalized_url: str
    domain: str


class BlogUpsertResult(ContractModel):
    id: int
    inserted: bool


class BlogResultUpdate(ContractModel):
    crawl_status: CrawlStatus
    status_code: int | None
    friend_links_count: int
    metadata_captured: bool = False
    title: str | None = None
    icon_url: str | None = None


class BlogRecord(ContractModel):
    id: int
    url: str
    normalized_url: str
    domain: str
    title: str | None
    icon_url: str | None
    status_code: int | None
    crawl_status: CrawlStatus
    friend_links_count: int
    last_crawled_at: str | None
    created_at: str
    updated_at: str


class NeighborBlog(ContractModel):
    id: int
    domain: str | None
    title: str | None
    icon_url: str | None


class EdgeCreate(ContractModel):
    from_blog_id: int
    to_blog_id: int
    link_url_raw: str
    link_text: str | None = None


class EdgeRecord(ContractModel):
    id: int
    from_blog_id: int
    to_blog_id: int
    link_url_raw: str
    link_text: str | None
    discovered_at: str


class BlogRelation(EdgeRecord):
    neighbor_blog: NeighborBlog | None


class BlogDetail(BlogRecord):
    incoming_edges: list[BlogRelation]
    outgoing_edges: list[BlogRelation]


class BlogCatalogFilters(ContractModel):
    q: str | None
    site: str | None
    url: str | None
    status: str | None


class BlogCatalogPage(ContractModel):
    items: list[BlogRecord]
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool
    filters: BlogCatalogFilters
    sort: str


class StatsSnapshot(ContractModel):
    total_blogs: int
    total_edges: int
    average_friend_links: float
    status_counts: dict[str, int]
    pending_tasks: int
    processing_tasks: int
    failed_tasks: int
    finished_tasks: int


class GraphView(ContractModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    meta: dict[str, Any]


class GraphSnapshotManifest(ContractModel):
    version: str
    generated_at: str
    source: str
    has_stable_positions: bool
    total_nodes: int
    total_edges: int
    available_nodes: int
    available_edges: int
    graph_fingerprint: str | None = None
    file: str


class GraphSnapshot(GraphView):
    version: str
    generated_at: str


class SearchSnapshot(ContractModel):
    blogs: list[BlogRecord]
    edges: list[EdgeRecord]
    logs: list[dict[str, Any]]
