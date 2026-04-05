"""Shared persistence contracts used across services."""

from shared.contracts.enums import CrawlStatus
from shared.contracts.persistence import BlogCatalogFilters
from shared.contracts.persistence import BlogCatalogPage
from shared.contracts.persistence import BlogCreate
from shared.contracts.persistence import BlogDetail
from shared.contracts.persistence import BlogRecord
from shared.contracts.persistence import BlogRelation
from shared.contracts.persistence import BlogResultUpdate
from shared.contracts.persistence import BlogUpsertResult
from shared.contracts.persistence import EdgeCreate
from shared.contracts.persistence import EdgeRecord
from shared.contracts.persistence import GraphSnapshot
from shared.contracts.persistence import GraphSnapshotManifest
from shared.contracts.persistence import GraphView
from shared.contracts.persistence import NeighborBlog
from shared.contracts.persistence import SearchSnapshot
from shared.contracts.persistence import StatsSnapshot

__all__ = [
    "BlogCatalogFilters",
    "BlogCatalogPage",
    "BlogCreate",
    "BlogDetail",
    "BlogRecord",
    "BlogRelation",
    "BlogResultUpdate",
    "BlogUpsertResult",
    "CrawlStatus",
    "EdgeCreate",
    "EdgeRecord",
    "GraphSnapshot",
    "GraphSnapshotManifest",
    "GraphView",
    "NeighborBlog",
    "SearchSnapshot",
    "StatsSnapshot",
]
