"""Shared enums for persistence contracts."""

from enum import StrEnum


class CrawlStatus(StrEnum):
    WAITING = "WAITING"
    PROCESSING = "PROCESSING"
    FINISHED = "FINISHED"
    FAILED = "FAILED"
