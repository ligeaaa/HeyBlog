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
    """Return the current UTC timestamp in ISO-8601 format.

    Returns:
        Current time as an ISO-8601 UTC string.
    """
    return datetime.now(UTC).isoformat()


class CrawlerRuntimeService:
    """Manage crawler runtime execution state and control actions.

    Attributes:
        pipeline: Crawl pipeline used to process individual blog rows.
        executor: Thread launcher used for background runtime execution.
        worker_count: Number of runtime workers to run in parallel.
        priority_seed_normal_queue_slots: Number of normal queue claims allowed
            after a priority seed claim.
    """

    def __init__(
        self,
        pipeline: Any,
        executor: SerialRuntimeExecutor | None = None,
        *,
        worker_count: int = 1,
        priority_seed_normal_queue_slots: int = 2,
    ) -> None:
        """Initialize runtime state, workers, and synchronization primitives.

        Args:
            pipeline: Crawl pipeline reused by synchronous and background runs.
            executor: Optional executor used to start the background thread.
            worker_count: Requested number of runtime workers.
            priority_seed_normal_queue_slots: Fairness window size after a
                priority queue claim.

        Returns:
            ``None``. The runtime service stores its dependencies and prepares
            worker snapshots plus synchronization primitives.
        """
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
        """Return the current full runtime snapshot.

        Returns:
            Serialized runtime snapshot including per-worker status.
        """
        with self._lock:
            return self._snapshot.as_dict()

    def current(self) -> dict[str, Any]:
        """Return a compatibility-focused runtime snapshot.

        Returns:
            Runtime status centered on one representative active worker while
            still including full worker state.
        """
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
        """Start the background crawler loop if the runtime is currently idle.

        Returns:
            Updated runtime snapshot after the start request is processed.
        """
        with self._lock:
            if self._snapshot.runner_status in {"starting", "running", "stopping"}:
                return self._snapshot.as_dict()

            self._stop_event.clear()
            self._begin_run_locked("starting")
            self._thread = self.executor.start(self._run_background_loop)
            return self._snapshot.as_dict()

    def stop(self) -> dict[str, Any]:
        """Request the background loop to stop at the next safe checkpoint.

        Returns:
            Updated runtime snapshot after the stop request is recorded.
        """
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
        """Run a synchronous worker-pool batch when the runtime is idle.

        Args:
            max_nodes: Maximum number of blogs the batch may process.

        Returns:
            Result payload indicating whether the batch was accepted and, when
            accepted, the batch result plus runtime snapshot.
        """
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
        """Run the background crawler loop until work is exhausted or stopped.

        Returns:
            ``None``. Runtime state is updated in place.
        """
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
        """Run one worker-pool execution and aggregate the results.

        Args:
            max_nodes: Optional maximum number of blogs to process. ``None``
                means the worker pool runs until the queue is exhausted or
                stopped.

        Returns:
            Aggregate runtime result payload for the completed worker-pool run.
        """
        aggregate = RuntimeAggregate()
        pool_exhausted = Event()
        budget = {"remaining": max_nodes}
        fatal_error: dict[str, Exception | None] = {"error": None}
        # Workers all share one aggregate and one claim lock so runtime mode can
        # parallelize processing without changing queue-claim semantics.
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
        """Run one worker loop until the shared budget or queue is exhausted.

        Args:
            worker_index: One-based index of the worker being executed.
            aggregate: Shared aggregate counters updated by all workers.
            budget: Shared mutable remaining-budget payload.
            pool_exhausted: Event used to signal that no more work is available.
            fatal_error: Shared holder for the first fatal worker exception.

        Returns:
            ``None``. Worker progress is recorded via shared runtime state.
        """
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
                # Runtime mode intentionally reuses the pipeline callback hooks so
                # status snapshots stay aligned with one-shot crawl behavior.
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
        """Reserve one batch slot for a worker when the run is budget-limited.

        Args:
            budget: Shared mutable payload containing remaining batch capacity.

        Returns:
            ``True`` when the worker may continue processing, otherwise
            ``False`` when the batch budget is exhausted.
        """
        with self._lock:
            remaining = budget["remaining"]
            if remaining is None:
                return True
            if remaining <= 0:
                return False
            budget["remaining"] = remaining - 1
            return True

    def _release_budget_slot(self, budget: dict[str, int | None]) -> None:
        """Return one unused batch slot when no blog was actually processed.

        Args:
            budget: Shared mutable payload containing remaining batch capacity.

        Returns:
            ``None``. The remaining budget is incremented in place when needed.
        """
        with self._lock:
            remaining = budget["remaining"]
            if remaining is None:
                return
            budget["remaining"] = remaining + 1

    def _claim_next_waiting_blog(self) -> dict[str, Any] | None:
        """Claim one waiting blog while enforcing runtime fairness rules.

        Returns:
            The next claimed blog row, or ``None`` when no eligible work
            remains.
        """
        with self._claim_lock:
            if self._normal_slots_remaining_after_priority <= 0:
                priority_row = self._get_next_priority_blog()
                if priority_row is not None:
                    # One claimed priority seed opens a bounded fairness window
                    # for normal queue items before the next priority check.
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
        """Return the next priority blog from the repository, if supported.

        Returns:
            The next priority blog row, or ``None`` when unavailable.
        """
        getter = getattr(self.pipeline.repository, "get_next_priority_blog", None)
        if getter is None:
            return None
        return getter()

    def _get_next_waiting_blog(self, *, include_priority: bool) -> dict[str, Any] | None:
        """Return the next waiting blog from the repository.

        Args:
            include_priority: Whether the repository should allow priority rows
                in its general waiting query.

        Returns:
            The next waiting blog row, or ``None`` when the queue is empty.
        """
        getter = self.pipeline.repository.get_next_waiting_blog
        try:
            return getter(include_priority=include_priority)
        except TypeError:
            return getter()

    def _on_blog_start(self, worker_index: int, blog: dict[str, Any]) -> None:
        """Record that a worker has started crawling one blog.

        Args:
            worker_index: One-based worker index being updated.
            blog: Blog payload that the worker just started processing.

        Returns:
            ``None``. Runtime snapshot fields are updated in place.
        """
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
        """Record that a worker finished processing one blog successfully.

        Args:
            worker_index: One-based worker index being updated.
            blog: Blog payload that just finished processing.
            result: Result payload produced by ``process_blog_row``.

        Returns:
            ``None``. Runtime snapshot fields are updated in place.
        """
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
        """Record that a worker hit an error while processing one blog.

        Args:
            worker_index: One-based worker index being updated.
            blog: Blog payload that raised the error.
            error: Exception raised while processing the blog.

        Returns:
            ``None``. Runtime snapshot fields are updated in place.
        """
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
        """Reset runtime snapshot fields for a newly starting run.

        Args:
            status: Initial runner status to record, such as ``starting`` or
                ``running``.

        Returns:
            ``None``. Snapshot fields are reset in place. Caller must hold
            ``self._lock``.
        """
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
        """Finalize snapshot fields after a successful run completes.

        Args:
            result: Aggregate runtime result payload for the completed run.

        Returns:
            ``None``. Snapshot fields are updated in place. Caller must hold
            ``self._lock``.
        """
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
        """Record a runtime-level fatal error across the snapshot.

        Args:
            error: Fatal exception that aborted the runtime execution.

        Returns:
            ``None``. Snapshot fields are updated in place. Caller must hold
            ``self._lock``.
        """
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
        """Clear the compatibility-view current-blog fields on the snapshot.

        Returns:
            ``None``. Snapshot fields are reset in place. Caller must hold
            ``self._lock``.
        """
        self._snapshot.current_worker_id = None
        self._snapshot.current_blog_id = None
        self._snapshot.current_url = None
        self._snapshot.current_stage = None
        self._snapshot.task_started_at = None

    def _worker_locked(self, worker_index: int) -> RuntimeWorkerSnapshot:
        """Return the mutable worker snapshot for one worker index.

        Args:
            worker_index: One-based worker index to resolve.

        Returns:
            The mutable ``RuntimeWorkerSnapshot`` owned by that worker.
        """
        return self._snapshot.workers[worker_index - 1]

    def _set_worker_idle_locked(self, worker_index: int) -> None:
        """Clear one worker's current task fields after an iteration finishes.

        Args:
            worker_index: One-based worker index being updated.

        Returns:
            ``None``. Worker snapshot fields are updated in place. Caller must
            hold ``self._lock``.
        """
        worker = self._worker_locked(worker_index)
        worker.status = "idle"
        worker.current_blog_id = None
        worker.current_url = None
        worker.current_stage = None
        worker.task_started_at = None

    def _set_worker_waiting_locked(self, worker_index: int) -> None:
        """Mark one worker as temporarily waiting for more discovered work.

        Args:
            worker_index: One-based worker index being updated.

        Returns:
            ``None``. Worker snapshot fields are updated in place. Caller must
            hold ``self._lock``.
        """
        worker = self._worker_locked(worker_index)
        worker.status = "waiting"
        worker.current_blog_id = None
        worker.current_url = None
        worker.current_stage = "waiting_for_work"
        worker.task_started_at = None

    def _set_worker_error_idle_locked(self, worker_index: int) -> None:
        """Clear current task fields but preserve the worker's error status.

        Args:
            worker_index: One-based worker index being updated.

        Returns:
            ``None``. Worker snapshot fields are updated in place. Caller must
            hold ``self._lock``.
        """
        worker = self._worker_locked(worker_index)
        worker.current_blog_id = None
        worker.current_url = None
        worker.current_stage = "error"
        worker.task_started_at = None

    def _record_worker_result_locked(self, worker_index: int, result: dict[str, Any]) -> None:
        """Merge one processed-blog result into the worker's counters.

        Args:
            worker_index: One-based worker index being updated.
            result: Result payload returned by ``process_blog_row``.

        Returns:
            ``None``. Worker counters are updated in place. Caller must hold
            ``self._lock``.
        """
        worker = self._worker_locked(worker_index)
        worker.processed += int(result["processed"])
        worker.discovered += int(result["discovered"])
        worker.failed += int(result["failed"])
