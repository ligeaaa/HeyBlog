"""Runtime-facing crawler state contracts."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from typing import Any


@dataclass(slots=True)
class RuntimeSnapshot:
    """Represent crawler runtime state for UI and API consumers."""

    runner_status: str = "idle"
    active_run_id: str | None = None
    current_blog_id: int | None = None
    current_url: str | None = None
    current_stage: str | None = None
    last_started_at: str | None = None
    last_stopped_at: str | None = None
    last_error: str | None = None
    last_result: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return the public runtime payload shape."""
        return asdict(self)


@dataclass(slots=True)
class RuntimeAggregate:
    """Accumulate the background loop totals across single-blog batches."""

    processed: int = 0
    discovered: int = 0
    failed: int = 0
    exports: dict[str, Any] = field(default_factory=dict)

    def include(self, result: dict[str, Any]) -> None:
        """Merge one run_once result into the aggregate counters."""
        self.processed += int(result["processed"])
        self.discovered += int(result["discovered"])
        self.failed += int(result["failed"])
        self.exports = dict(result["exports"])

    def as_result(self) -> dict[str, Any]:
        """Return the aggregate payload using the existing dict contract."""
        return {
            "processed": self.processed,
            "discovered": self.discovered,
            "failed": self.failed,
            "exports": dict(self.exports),
        }

