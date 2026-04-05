"""Runtime-facing crawler state contracts."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from datetime import UTC
from datetime import datetime
from typing import Any


def _elapsed_seconds(started_at: str | None, *, now: datetime | None = None) -> float | None:
    if not started_at:
        return None
    try:
        started = datetime.fromisoformat(started_at)
    except ValueError:
        return None
    reference = now or datetime.now(UTC)
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    return round(max((reference - started).total_seconds(), 0.0), 1)


@dataclass(slots=True)
class RuntimeWorkerSnapshot:
    """Represent one crawler worker's current progress."""

    worker_id: str
    worker_index: int
    status: str = "idle"
    current_blog_id: int | None = None
    current_url: str | None = None
    current_stage: str | None = None
    task_started_at: str | None = None
    last_transition_at: str | None = None
    last_completed_at: str | None = None
    last_error: str | None = None
    processed: int = 0
    discovered: int = 0
    failed: int = 0

    def as_dict(self, *, now: datetime | None = None) -> dict[str, Any]:
        payload = asdict(self)
        payload["elapsed_seconds"] = _elapsed_seconds(self.task_started_at, now=now)
        return payload


@dataclass(slots=True)
class RuntimeSnapshot:
    """Represent crawler runtime state for UI and API consumers."""

    runner_status: str = "idle"
    active_run_id: str | None = None
    worker_count: int = 0
    active_workers: int = 0
    current_worker_id: str | None = None
    current_blog_id: int | None = None
    current_url: str | None = None
    current_stage: str | None = None
    task_started_at: str | None = None
    last_started_at: str | None = None
    last_stopped_at: str | None = None
    last_error: str | None = None
    last_result: dict[str, Any] | None = None
    workers: list[RuntimeWorkerSnapshot] = field(default_factory=list)

    def _selected_worker(self) -> RuntimeWorkerSnapshot | None:
        active = [worker for worker in self.workers if worker.status == "running"]
        if not active:
            active = [worker for worker in self.workers if worker.current_blog_id is not None]
        if not active:
            return None
        return sorted(active, key=lambda worker: worker.worker_index)[0]

    def as_dict(self) -> dict[str, Any]:
        """Return the public runtime payload shape."""
        now = datetime.now(UTC)
        payload = asdict(self)
        payload["workers"] = [worker.as_dict(now=now) for worker in self.workers]
        payload["active_workers"] = sum(1 for worker in self.workers if worker.current_blog_id is not None)
        payload["worker_count"] = len(self.workers)
        selected = self._selected_worker()
        if selected is not None:
            payload["current_worker_id"] = selected.worker_id
            payload["current_blog_id"] = selected.current_blog_id
            payload["current_url"] = selected.current_url
            payload["current_stage"] = selected.current_stage
            payload["task_started_at"] = selected.task_started_at
            payload["elapsed_seconds"] = _elapsed_seconds(selected.task_started_at, now=now)
        else:
            payload["elapsed_seconds"] = None
        return payload


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
