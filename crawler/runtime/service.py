"""In-memory crawler runtime state and control loop."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from threading import Event
from threading import Lock
from threading import Thread
from time import sleep
from typing import Any
from uuid import uuid4

from crawler.contracts.runtime import RuntimeAggregate
from crawler.contracts.runtime import RuntimeSnapshot
from crawler.contracts.runtime import RuntimeWorkerSnapshot
from crawler.runtime.executor import SerialRuntimeExecutor


def utc_now() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


class CrawlerRuntimeService:
    """Manage crawler execution state and control actions."""

    def __init__(
        self,
        pipeline: Any,
        executor: SerialRuntimeExecutor | None = None,
        *,
        worker_count: int = 1,
        priority_seed_normal_queue_slots: int = 2,
    ) -> None:
        self.pipeline = pipeline
        self.executor = executor or SerialRuntimeExecutor()
        self.worker_count = max(1, worker_count)
        self.priority_seed_normal_queue_slots = max(1, priority_seed_normal_queue_slots)
        self._normal_slots_remaining_after_priority = 0
        self._snapshot = RuntimeSnapshot(
            worker_count=self.worker_count,
            workers=[
                RuntimeWorkerSnapshot(worker_id=f"worker-{index}", worker_index=index)
                for index in range(1, self.worker_count + 1)
            ],
        )
        self._lock = Lock()
        self._claim_lock = Lock()
        self._stop_event = Event()
        self._thread: Thread | None = None

    def status(self) -> dict[str, Any]:
        """Return the current runtime snapshot."""
        with self._lock:
            return self._snapshot.as_dict()

    def current(self) -> dict[str, Any]:
        """Return one representative active worker for compatibility callers."""
        snapshot = self.status()
        return {
            "runner_status": snapshot["runner_status"],
            "active_run_id": snapshot["active_run_id"],
            "worker_count": snapshot["worker_count"],
            "active_workers": snapshot["active_workers"],
            "current_worker_id": snapshot["current_worker_id"],
            "current_blog_id": snapshot["current_blog_id"],
            "current_url": snapshot["current_url"],
            "current_stage": snapshot["current_stage"],
            "task_started_at": snapshot["task_started_at"],
            "elapsed_seconds": snapshot["elapsed_seconds"],
            "last_started_at": snapshot["last_started_at"],
            "last_stopped_at": snapshot["last_stopped_at"],
            "last_error": snapshot["last_error"],
            "last_result": snapshot["last_result"],
            "workers": snapshot["workers"],
        }

    def start(self) -> dict[str, Any]:
        """Start the background crawler loop."""
        with self._lock:
            if self._snapshot.runner_status in {"starting", "running", "stopping"}:
                return self._snapshot.as_dict()

            self._stop_event.clear()
            self._begin_run_locked("starting")
            self._thread = self.executor.start(self._run_background_loop)
            return self._snapshot.as_dict()

    def stop(self) -> dict[str, Any]:
        """Request the background loop to stop after the current safe checkpoint."""
        with self._lock:
            if self._snapshot.runner_status == "idle":
                return self._snapshot.as_dict()

            self._stop_event.set()
            self._snapshot.runner_status = "stopping"
            for worker in self._snapshot.workers:
                if worker.current_blog_id is not None:
                    worker.status = "stopping"
            return self._snapshot.as_dict()

    def run_batch(self, max_nodes: int) -> dict[str, Any]:
        """Run a synchronous batch when the background loop is idle."""
        with self._lock:
            if self._snapshot.runner_status in {"starting", "running", "stopping"}:
                return {
                    "accepted": False,
                    "reason": "runtime_busy",
                    "runtime": self._snapshot.as_dict(),
                }
            self._stop_event.clear()
            self._normal_slots_remaining_after_priority = 0
            self._begin_run_locked("running")

        try:
            result = self._run_worker_pool(max_nodes=max_nodes)
            with self._lock:
                self._finish_run_locked(result)
                self._stop_event.clear()
                return {
                    "accepted": True,
                    "mode": "batch",
                    "result": result,
                    "runtime": self._snapshot.as_dict(),
                }
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._record_error_locked(exc)
                raise

    def _run_background_loop(self) -> None:
        """Run the crawler continuously until idle or stop is requested."""
        with self._lock:
            self._snapshot.runner_status = "running"
            self._normal_slots_remaining_after_priority = 0

        try:
            result = self._run_worker_pool(max_nodes=None)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._record_error_locked(exc)
            return

        with self._lock:
            self._finish_run_locked(result)
            self._stop_event.clear()

    def _run_worker_pool(self, *, max_nodes: int | None) -> dict[str, Any]:
        """Run one runtime execution using a fixed worker pool."""
        aggregate = RuntimeAggregate()
        pool_exhausted = Event()
        budget = {"remaining": max_nodes}
        fatal_error: dict[str, Exception | None] = {"error": None}
        threads = [
            Thread(
                target=self._worker_loop,
                kwargs={
                    "worker_index": worker_index,
                    "aggregate": aggregate,
                    "budget": budget,
                    "pool_exhausted": pool_exhausted,
                    "fatal_error": fatal_error,
                },
                daemon=True,
                name=f"crawler-worker-{worker_index}",
            )
            for worker_index in range(1, self.worker_count + 1)
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        if fatal_error["error"] is not None:
            raise fatal_error["error"]
        aggregate.exports = self.pipeline.write_exports()
        return aggregate.as_result()

    def _worker_loop(
        self,
        *,
        worker_index: int,
        aggregate: RuntimeAggregate,
        budget: dict[str, int | None],
        pool_exhausted: Event,
        fatal_error: dict[str, Exception | None],
    ) -> None:
        """Run one runtime worker until the shared budget or queue is exhausted."""
        while not self._stop_event.is_set() and not pool_exhausted.is_set():
            if not self._claim_budget_slot(budget):
                return

            row = self._claim_next_waiting_blog()
            if row is None:
                self._release_budget_slot(budget)
                with self._lock:
                    self._set_worker_waiting_locked(worker_index)
                    has_other_active_workers = any(
                        worker.current_blog_id is not None and worker.worker_index != worker_index
                        for worker in self._snapshot.workers
                    )
                if has_other_active_workers:
                    sleep(0.1)
                    continue
                with self._lock:
                    self._set_worker_idle_locked(worker_index)
                pool_exhausted.set()
                return

            try:
                result = self.pipeline.process_blog_row(
                    row,
                    on_blog_start=lambda blog, wid=worker_index: self._on_blog_start(wid, blog),
                    on_blog_finish=lambda blog, payload, wid=worker_index: self._on_blog_finish(wid, blog, payload),
                    on_blog_error=lambda blog, error, wid=worker_index: self._on_blog_error(wid, blog, error),
                )
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    worker = self._worker_locked(worker_index)
                    worker.status = "error"
                    worker.current_blog_id = int(row["id"])
                    worker.current_url = str(row["url"])
                    worker.current_stage = "error"
                    worker.task_started_at = None
                    worker.last_transition_at = utc_now()
                    worker.last_completed_at = worker.last_transition_at
                    worker.last_error = str(exc)
                    self._snapshot.last_error = str(exc)
                    if fatal_error["error"] is None:
                        fatal_error["error"] = exc
                self._stop_event.set()
                pool_exhausted.set()
                return

            with self._lock:
                aggregate.processed += int(result["processed"])
                aggregate.discovered += int(result["discovered"])
                aggregate.failed += int(result["failed"])
                self._record_worker_result_locked(worker_index, result)
                if result["failed"] > 0:
                    self._set_worker_error_idle_locked(worker_index)
                else:
                    self._set_worker_idle_locked(worker_index)

    def _claim_budget_slot(self, budget: dict[str, int | None]) -> bool:
        """Reserve one execution slot for a worker when running a limited batch."""
        with self._lock:
            remaining = budget["remaining"]
            if remaining is None:
                return True
            if remaining <= 0:
                return False
            budget["remaining"] = remaining - 1
            return True

    def _release_budget_slot(self, budget: dict[str, int | None]) -> None:
        """Return one unused batch slot when no blog was actually processed."""
        with self._lock:
            remaining = budget["remaining"]
            if remaining is None:
                return
            budget["remaining"] = remaining + 1

    def _claim_next_waiting_blog(self) -> dict[str, Any] | None:
        """Claim exactly one waiting blog under a runtime-local lock."""
        with self._claim_lock:
            if self._normal_slots_remaining_after_priority <= 0:
                priority_row = self._get_next_priority_blog()
                if priority_row is not None:
                    self._normal_slots_remaining_after_priority = self.priority_seed_normal_queue_slots
                    return priority_row

            row = self._get_next_waiting_blog(include_priority=self._normal_slots_remaining_after_priority <= 0)
            if row is not None:
                if self._normal_slots_remaining_after_priority > 0:
                    self._normal_slots_remaining_after_priority -= 1
                return row

            if self._normal_slots_remaining_after_priority > 0:
                priority_row = self._get_next_priority_blog()
                if priority_row is not None:
                    self._normal_slots_remaining_after_priority = self.priority_seed_normal_queue_slots
                    return priority_row
                self._normal_slots_remaining_after_priority = 0
            return None

    def _get_next_priority_blog(self) -> dict[str, Any] | None:
        getter = getattr(self.pipeline.repository, "get_next_priority_blog", None)
        if getter is None:
            return None
        return getter()

    def _get_next_waiting_blog(self, *, include_priority: bool) -> dict[str, Any] | None:
        getter = self.pipeline.repository.get_next_waiting_blog
        try:
            return getter(include_priority=include_priority)
        except TypeError:
            return getter()

    def _on_blog_start(self, worker_index: int, blog: dict[str, Any]) -> None:
        with self._lock:
            self._snapshot.runner_status = "running"
            worker = self._worker_locked(worker_index)
            worker.status = "running"
            worker.current_blog_id = int(blog["id"])
            worker.current_url = str(blog["url"])
            worker.current_stage = "crawling"
            worker.task_started_at = utc_now()
            worker.last_transition_at = worker.task_started_at
            worker.last_error = None

    def _on_blog_finish(self, worker_index: int, blog: dict[str, Any], result: dict[str, Any]) -> None:
        with self._lock:
            worker = self._worker_locked(worker_index)
            worker.status = "running"
            worker.current_blog_id = int(blog["id"])
            worker.current_url = str(blog["url"])
            worker.current_stage = "completed"
            worker.last_transition_at = utc_now()
            worker.last_completed_at = worker.last_transition_at
            self._snapshot.last_result = result

    def _on_blog_error(self, worker_index: int, blog: dict[str, Any], error: Exception) -> None:
        with self._lock:
            worker = self._worker_locked(worker_index)
            worker.status = "error"
            worker.current_blog_id = int(blog["id"])
            worker.current_url = str(blog["url"])
            worker.current_stage = "error"
            worker.last_transition_at = utc_now()
            worker.last_completed_at = worker.last_transition_at
            worker.last_error = str(error)
            self._snapshot.last_error = str(error)

    def _begin_run_locked(self, status: str) -> None:
        self._snapshot.runner_status = status
        self._snapshot.active_run_id = str(uuid4())
        self._snapshot.worker_count = self.worker_count
        self._snapshot.active_workers = 0
        self._snapshot.last_started_at = utc_now()
        self._snapshot.last_stopped_at = None
        self._snapshot.last_error = None
        self._snapshot.last_result = None
        self._clear_current_blog_locked()
        for worker in self._snapshot.workers:
            worker.status = "idle"
            worker.current_blog_id = None
            worker.current_url = None
            worker.current_stage = None
            worker.task_started_at = None
            worker.last_transition_at = None
            worker.last_completed_at = None
            worker.last_error = None
            worker.processed = 0
            worker.discovered = 0
            worker.failed = 0

    def _finish_run_locked(self, result: dict[str, Any]) -> None:
        self._snapshot.runner_status = "idle"
        self._snapshot.last_stopped_at = utc_now()
        self._snapshot.last_result = result
        self._clear_current_blog_locked()
        for worker in self._snapshot.workers:
            if worker.status != "error":
                worker.status = "idle"
            worker.current_blog_id = None
            worker.current_url = None
            worker.current_stage = None
            worker.task_started_at = None

    def _record_error_locked(self, error: Exception) -> None:
        self._snapshot.runner_status = "error"
        self._snapshot.last_error = str(error)
        stopped_at = utc_now()
        self._snapshot.last_stopped_at = stopped_at
        self._clear_current_blog_locked()
        for worker in self._snapshot.workers:
            if worker.current_blog_id is not None and worker.status != "error":
                worker.status = "error"
                worker.current_stage = "error"
                worker.last_error = worker.last_error or str(error)
            elif worker.status != "error":
                worker.status = "idle"
                worker.current_stage = None
            worker.current_blog_id = None
            worker.current_url = None
            worker.task_started_at = None
            worker.last_transition_at = stopped_at

    def _clear_current_blog_locked(self) -> None:
        self._snapshot.current_worker_id = None
        self._snapshot.current_blog_id = None
        self._snapshot.current_url = None
        self._snapshot.current_stage = None
        self._snapshot.task_started_at = None

    def _worker_locked(self, worker_index: int) -> RuntimeWorkerSnapshot:
        """Return the mutable worker snapshot for one worker index."""
        return self._snapshot.workers[worker_index - 1]

    def _set_worker_idle_locked(self, worker_index: int) -> None:
        """Clear one worker's current task fields after a loop iteration finishes."""
        worker = self._worker_locked(worker_index)
        worker.status = "idle"
        worker.current_blog_id = None
        worker.current_url = None
        worker.current_stage = None
        worker.task_started_at = None

    def _set_worker_waiting_locked(self, worker_index: int) -> None:
        """Mark one worker as temporarily waiting for more discovered work."""
        worker = self._worker_locked(worker_index)
        worker.status = "waiting"
        worker.current_blog_id = None
        worker.current_url = None
        worker.current_stage = "waiting_for_work"
        worker.task_started_at = None

    def _set_worker_error_idle_locked(self, worker_index: int) -> None:
        """Clear current task fields but preserve the worker's error status."""
        worker = self._worker_locked(worker_index)
        worker.current_blog_id = None
        worker.current_url = None
        worker.current_stage = "error"
        worker.task_started_at = None

    def _record_worker_result_locked(self, worker_index: int, result: dict[str, Any]) -> None:
        """Merge one processed blog result into the owning worker counters."""
        worker = self._worker_locked(worker_index)
        worker.processed += int(result["processed"])
        worker.discovered += int(result["discovered"])
        worker.failed += int(result["failed"])
