"""Runtime-facing crawler state contracts."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from datetime import UTC
from datetime import datetime
from typing import Any


def _elapsed_seconds(started_at: str | None, *, now: datetime | None = None) -> float | None:
    """Return rounded elapsed seconds from an ISO timestamp.

    Args:
        started_at: ISO-8601 timestamp string representing when work started.
        now: Optional reference timestamp used primarily by tests.

    Returns:
        Rounded elapsed seconds, or ``None`` when the timestamp is missing or
        invalid.
    """
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
    """Represent the current and recent state of one runtime worker.

    Attributes:
        worker_id: Stable public identifier for the worker.
        worker_index: One-based worker index used for deterministic ordering.
        status: Current worker state such as ``idle`` or ``running``.
        current_blog_id: Blog currently assigned to the worker, if any.
        current_url: URL of the blog currently assigned to the worker.
        current_stage: Human-readable sub-stage within the worker lifecycle.
        task_started_at: ISO timestamp recording when the current task began.
        last_transition_at: ISO timestamp for the worker's most recent status
            transition.
        last_completed_at: ISO timestamp for the most recently completed task.
        last_error: Last error message observed for this worker.
        processed: Total number of processed blogs handled by this worker in the
            active run.
        discovered: Total number of discovered child links produced by this
            worker in the active run.
        failed: Total number of failed blog attempts recorded for this worker in
            the active run.
    """

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
        """Serialize the worker snapshot to the public API payload shape.

        Args:
            now: Optional reference timestamp used to compute elapsed time.

        Returns:
            A dictionary version of the snapshot with an added
            ``elapsed_seconds`` field.
        """
        payload = asdict(self)
        payload["elapsed_seconds"] = _elapsed_seconds(self.task_started_at, now=now)
        return payload


@dataclass(slots=True)
class RuntimeSnapshot:
    """Represent the aggregate crawler runtime state exposed over the API.

    Attributes:
        runner_status: Overall runtime status such as ``idle`` or ``running``.
        active_run_id: Unique identifier for the currently active run, if any.
        worker_count: Total number of configured runtime workers.
        active_workers: Number of workers currently assigned a blog.
        current_worker_id: Representative active worker chosen for legacy API
            compatibility.
        current_blog_id: Blog currently exposed through the compatibility view.
        current_url: URL currently exposed through the compatibility view.
        current_stage: Stage currently exposed through the compatibility view.
        task_started_at: Start timestamp for the compatibility-view worker.
        last_started_at: Timestamp of the most recent run start.
        last_stopped_at: Timestamp of the most recent run completion or stop.
        last_error: Most recent runtime-level error message.
        last_result: Most recent aggregate run result payload.
        workers: Per-worker runtime snapshots.
    """

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
        """Select the worker exposed through the compatibility snapshot fields.

        Returns:
            The first active worker by index, or ``None`` when no worker is
            currently active.
        """
        active = [worker for worker in self.workers if worker.status == "running"]
        if not active:
            active = [worker for worker in self.workers if worker.current_blog_id is not None]
        if not active:
            return None
        return sorted(active, key=lambda worker: worker.worker_index)[0]

    def as_dict(self) -> dict[str, Any]:
        """Serialize the runtime snapshot to the public API payload shape.

        Returns:
            A dictionary containing aggregate runtime status plus serialized
            per-worker snapshots and compatibility fields.
        """
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
    """Accumulate totals across one runtime worker-pool execution.

    Attributes:
        processed: Total number of processed blogs.
        discovered: Total number of discovered outbound links.
        failed: Total number of failed blog attempts.
        exports: Export payload returned after the run writes graph snapshots.
    """

    processed: int = 0
    discovered: int = 0
    failed: int = 0
    exports: dict[str, Any] = field(default_factory=dict)

    def include(self, result: dict[str, Any]) -> None:
        """Merge one single-batch result into the aggregate counters.

        Args:
            result: ``run_once``-style result payload containing processed,
                discovered, failed, and export fields.

        Returns:
            ``None``. The aggregate is updated in place.
        """
        self.processed += int(result["processed"])
        self.discovered += int(result["discovered"])
        self.failed += int(result["failed"])
        self.exports = dict(result["exports"])

    def as_result(self) -> dict[str, Any]:
        """Return the aggregate counters using the crawler's dict contract.

        Returns:
            A dictionary containing the aggregate processed, discovered, failed,
            and export values for the runtime execution.
        """
        return {
            "processed": self.processed,
            "discovered": self.discovered,
            "failed": self.failed,
            "exports": dict(self.exports),
        }
