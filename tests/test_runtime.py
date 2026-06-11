"""Runtime contract tests for multi-worker execution and stop semantics."""

from __future__ import annotations

from threading import Event
from threading import Lock
from threading import Thread

from crawler.runtime import CrawlerRuntimeService
from crawler.runtime.capacity import CrawlerCapacityGate


class QueueRepository:
    """Claim one queued blog row at a time."""

    def __init__(self, blog_ids: list[int], *, raw_discovered_urls: int = 0) -> None:
        self.blog_ids = list(blog_ids)
        self.raw_discovered_urls = raw_discovered_urls
        self.lock = Lock()

    def get_next_waiting_blog(self) -> dict[str, object] | None:
        with self.lock:
            if not self.blog_ids:
                return None
            blog_id = self.blog_ids.pop(0)
            return {"id": blog_id, "url": f"https://blog{blog_id}.example.com/"}

    def stats(self) -> dict[str, int]:
        """Return raw URL count used by crawler capacity tests."""
        return {"raw_discovered_urls": self.raw_discovered_urls}


class BlockingQueuePipeline:
    """Pipeline stub that blocks one claimed blog until the test releases it."""

    def __init__(
        self,
        blog_ids: list[int],
        *,
        target_active_runs: int = 1,
        raw_discovered_urls: int = 0,
        raw_discovered_url_limit: int = 1_000_000,
    ) -> None:
        self.repository = QueueRepository(blog_ids, raw_discovered_urls=raw_discovered_urls)
        self.capacity_gate = CrawlerCapacityGate(
            self.repository,
            raw_discovered_url_limit=raw_discovered_url_limit,
        )
        self.target_active_runs = target_active_runs
        self.started = Event()
        self.target_active = Event()
        self.release = Event()
        self.lock = Lock()
        self.run_calls = 0
        self.active_runs = 0
        self.max_active_runs = 0
        self.on_start_hook = None

    def process_blog_row(
        self,
        row: dict[str, object],
        *,
        on_blog_start=None,
        on_blog_finish=None,
        on_blog_error=None,
    ) -> dict[str, int]:
        with self.lock:
            self.run_calls += 1
            self.active_runs += 1
            self.max_active_runs = max(self.max_active_runs, self.active_runs)
            if self.active_runs >= self.target_active_runs:
                self.target_active.set()

        if on_blog_start is not None:
            on_blog_start(row)
        if self.on_start_hook is not None:
            self.on_start_hook(row)
        self.started.set()
        self.release.wait(timeout=2)
        if on_blog_finish is not None:
            on_blog_finish(row, {"discovered": 0})
        with self.lock:
            self.active_runs -= 1
        return {"processed": 1, "discovered": 0, "failed": 0}

    def write_exports(self) -> dict[str, object]:
        return {}

    def run_once(
        self,
        max_nodes: int | None = None,
        *,
        on_blog_start=None,
        on_blog_finish=None,
        on_blog_error=None,
        should_stop=None,
    ) -> dict[str, object]:
        row = self.repository.get_next_waiting_blog()
        if row is None:
            return {"processed": 0, "discovered": 0, "failed": 0, "exports": {}}
        result = self.process_blog_row(
            row,
            on_blog_start=on_blog_start,
            on_blog_finish=on_blog_finish,
            on_blog_error=on_blog_error,
        )
        return {**result, "exports": {}}


class ExplodingPipeline:
    """Pipeline stub that fails inside one worker after claiming a blog."""

    def __init__(self) -> None:
        self.repository = QueueRepository([1])

    def process_blog_row(
        self,
        row: dict[str, object],
        *,
        on_blog_start=None,
        on_blog_finish=None,
        on_blog_error=None,
    ) -> dict[str, int]:
        if on_blog_start is not None:
            on_blog_start(row)
        raise RuntimeError("unexpected worker failure")

    def write_exports(self) -> dict[str, object]:
        return {}


class RecordingPipeline:
    """A fast pipeline that records claim order for queue assertions."""

    def __init__(self, repository: QueueRepository) -> None:
        self.repository = repository
        self.processed_ids: list[int] = []

    def process_blog_row(
        self,
        row: dict[str, object],
        *,
        on_blog_start=None,
        on_blog_finish=None,
        on_blog_error=None,
    ) -> dict[str, int]:
        if on_blog_start is not None:
            on_blog_start(row)
        self.processed_ids.append(int(row["id"]))
        if on_blog_finish is not None:
            on_blog_finish(row, {"discovered": 0})
        return {"processed": 1, "discovered": 0, "failed": 0}

    def write_exports(self) -> dict[str, object]:
        return {}


class FailThenSucceedPipeline:
    """Simulate one failed blog followed by a successful continuation."""

    def __init__(self) -> None:
        self.repository = QueueRepository([1, 2])
        self.processed_ids: list[int] = []
        self.failed_ids: list[int] = []

    def process_blog_row(
        self,
        row: dict[str, object],
        *,
        on_blog_start=None,
        on_blog_finish=None,
        on_blog_error=None,
    ) -> dict[str, int]:
        blog_id = int(row["id"])
        if on_blog_start is not None:
            on_blog_start(row)
        self.processed_ids.append(blog_id)
        if blog_id == 1:
            error = TimeoutError("blog crawl timed out after 60 seconds")
            self.failed_ids.append(blog_id)
            if on_blog_error is not None:
                on_blog_error(row, error)
            return {"processed": 1, "discovered": 0, "failed": 1}
        if on_blog_finish is not None:
            on_blog_finish(row, {"discovered": 0})
        return {"processed": 1, "discovered": 0, "failed": 0}

    def write_exports(self) -> dict[str, object]:
        return {}


class IdleSchedulerPipeline:
    """Pipeline stub that never has queued work but records start attempts."""

    def __init__(self) -> None:
        self.repository = QueueRepository([])
        self.capacity_gate = CrawlerCapacityGate(self.repository, raw_discovered_url_limit=-1)
        self.export_calls = 0

    def process_blog_row(
        self,
        row: dict[str, object],
        *,
        on_blog_start=None,
        on_blog_finish=None,
        on_blog_error=None,
    ) -> dict[str, int]:
        if on_blog_start is not None:
            on_blog_start(row)
        if on_blog_finish is not None:
            on_blog_finish(row, {"discovered": 0})
        return {"processed": 1, "discovered": 0, "failed": 0}

    def write_exports(self) -> dict[str, object]:
        self.export_calls += 1
        return {}


def test_runtime_stop_waits_for_active_workers_to_finish_without_starting_more_blogs() -> None:
    """Stop should let the current worker set finish, then prevent any new blog from starting."""
    pipeline = BlockingQueuePipeline([1, 2, 3, 4, 5, 6], target_active_runs=3)
    runtime = CrawlerRuntimeService(pipeline, worker_count=3)

    runtime.start()
    assert pipeline.target_active.wait(timeout=1)

    stopping_snapshot = runtime.stop()
    assert stopping_snapshot["runner_status"] == "stopping"
    assert stopping_snapshot["active_workers"] == 3
    assert {worker["status"] for worker in stopping_snapshot["workers"]} == {"stopping"}

    pipeline.release.set()
    runtime._thread.join(timeout=2)  # noqa: SLF001 - test waits for the background loop.

    status = runtime.status()
    assert status["runner_status"] == "idle"
    assert pipeline.run_calls == 3
    assert status["worker_count"] == 3


def test_runtime_can_process_multiple_active_blogs_concurrently() -> None:
    """Configured worker count should allow multiple blogs to run at the same time."""
    pipeline = BlockingQueuePipeline([1, 2, 3], target_active_runs=3)
    runtime = CrawlerRuntimeService(pipeline, worker_count=3)

    runtime.start()
    assert pipeline.target_active.wait(timeout=1)

    snapshot = runtime.status()
    assert snapshot["runner_status"] in {"running", "stopping"}
    assert snapshot["worker_count"] == 3
    assert snapshot["active_workers"] == 3
    assert len(snapshot["workers"]) == 3
    assert {worker["worker_id"] for worker in snapshot["workers"]} == {
        "worker-1",
        "worker-2",
        "worker-3",
    }
    assert all(worker["elapsed_seconds"] is not None for worker in snapshot["workers"])

    pipeline.release.set()
    runtime._thread.join(timeout=2)  # noqa: SLF001 - test waits for the background loop.

    assert pipeline.max_active_runs == 3


def test_runtime_rejects_second_start_while_multi_worker_run_is_active() -> None:
    """Concurrent start calls should not create another runtime run while workers are active."""
    pipeline = BlockingQueuePipeline([1, 2, 3], target_active_runs=3)
    runtime = CrawlerRuntimeService(pipeline, worker_count=3)

    runtime.start()
    assert pipeline.target_active.wait(timeout=1)

    second_start: list[dict[str, object]] = []

    def try_start_again() -> None:
        second_start.append(runtime.start())

    contender = Thread(target=try_start_again)
    contender.start()
    contender.join(timeout=1)

    pipeline.release.set()
    runtime._thread.join(timeout=2)  # noqa: SLF001 - test waits for the background loop.

    assert second_start
    assert second_start[0]["runner_status"] in {"running", "stopping", "starting"}


def test_runtime_records_fatal_worker_errors_and_clears_stale_current_task_fields() -> None:
    """Unexpected worker exceptions should surface as runtime errors with clean snapshots."""
    runtime = CrawlerRuntimeService(ExplodingPipeline(), worker_count=1)

    runtime.start()
    runtime._thread.join(timeout=2)  # noqa: SLF001 - test waits for the background loop.

    snapshot = runtime.status()
    assert snapshot["runner_status"] == "error"
    assert snapshot["last_error"] == "unexpected worker failure"
    assert snapshot["current_blog_id"] is None
    assert snapshot["current_url"] is None
    assert snapshot["workers"][0]["status"] == "error"
    assert snapshot["workers"][0]["current_blog_id"] is None
    assert snapshot["workers"][0]["current_url"] is None


def test_runtime_claims_waiting_blogs_in_queue_order() -> None:
    """Runtime batches should keep claiming ordinary waiting blogs until the limit is reached."""
    pipeline = RecordingPipeline(QueueRepository([1, 2, 3]))
    runtime = CrawlerRuntimeService(pipeline, worker_count=1)

    result = runtime.run_batch(3)

    assert result["accepted"] is True
    assert pipeline.processed_ids == [1, 2, 3]


def test_runtime_continues_to_next_waiting_blog_after_one_timeout_failure() -> None:
    """A failed blog should not stop the runtime from claiming the next queued blog."""
    pipeline = FailThenSucceedPipeline()
    runtime = CrawlerRuntimeService(pipeline, worker_count=1)

    result = runtime.run_batch(2)

    assert result["accepted"] is True
    assert result["result"]["processed"] == 2
    assert result["result"]["failed"] == 1
    assert pipeline.failed_ids == [1]
    assert pipeline.processed_ids == [1, 2]


def test_runtime_rejects_start_when_raw_discovered_url_limit_is_reached() -> None:
    """Runtime start should not open crawler work once raw URLs hit the configured limit."""
    pipeline = BlockingQueuePipeline(
        [1],
        raw_discovered_urls=1_000_000,
        raw_discovered_url_limit=1_000_000,
    )
    runtime = CrawlerRuntimeService(pipeline, worker_count=1)

    result = runtime.start()

    assert result["accepted"] is False
    assert result["reason"] == "raw_discovered_url_limit_reached"
    assert result["capacity"]["raw_count"] == 1_000_000
    assert pipeline.run_calls == 0
    assert runtime.status()["runner_status"] == "idle"


def test_runtime_auto_scheduler_starts_idle_runtime() -> None:
    """Hourly scheduler checks should wake an idle runtime by calling start."""
    pipeline = IdleSchedulerPipeline()
    runtime = CrawlerRuntimeService(
        pipeline,
        worker_count=1,
        auto_start_interval_seconds=0.01,
    )

    runtime.start_auto_scheduler()
    try:
        assert runtime._scheduler_thread is not None  # noqa: SLF001 - test inspects scheduler thread.
        assert runtime._scheduler_thread.is_alive()  # noqa: SLF001 - test inspects scheduler thread.
        assert pipeline.export_calls == 0

        runtime._scheduler_stop_event.wait(0.05)  # noqa: SLF001 - give the scheduler one tick window.

        assert pipeline.export_calls >= 1
        runtime.stop_auto_scheduler()
        if runtime._scheduler_thread is not None:
            runtime._scheduler_thread.join(timeout=2)
        if runtime._thread is not None:
            runtime._thread.join(timeout=2)
        assert runtime.status()["runner_status"] == "idle"
    finally:
        runtime.stop_auto_scheduler()
        if runtime._scheduler_thread is not None:
            runtime._scheduler_thread.join(timeout=2)


def test_runtime_auto_scheduler_skips_busy_runtime() -> None:
    """Scheduler checks should not restart a runtime that is already running."""
    pipeline = BlockingQueuePipeline([1], target_active_runs=1)
    runtime = CrawlerRuntimeService(
        pipeline,
        worker_count=1,
        auto_start_interval_seconds=0.01,
    )

    runtime.start()
    assert pipeline.started.wait(timeout=1)

    scheduler_result = runtime.start_auto_scheduler()
    assert scheduler_result["accepted"] is True
    runtime._scheduler_stop_event.wait(0.03)  # noqa: SLF001 - let the scheduler tick once.

    assert pipeline.run_calls == 1
    assert runtime.status()["runner_status"] in {"running", "stopping"}

    pipeline.release.set()
    runtime._thread.join(timeout=2)  # noqa: SLF001 - test waits for the background loop.
    runtime.stop_auto_scheduler()
    if runtime._scheduler_thread is not None:
        runtime._scheduler_thread.join(timeout=2)


def test_runtime_auto_scheduler_retries_after_error_state() -> None:
    """Scheduler checks should treat an errored runtime as not working."""
    pipeline = RecordingPipeline(QueueRepository([1, 2]))
    runtime = CrawlerRuntimeService(
        pipeline,
        worker_count=1,
        auto_start_interval_seconds=0.01,
    )
    with runtime._lock:  # noqa: SLF001 - test seeds a prior failed runtime state.
        runtime._snapshot.runner_status = "error"
        runtime._snapshot.last_error = "previous export failure"

    runtime.start_auto_scheduler()
    try:
        runtime._scheduler_stop_event.wait(0.05)  # noqa: SLF001 - let the scheduler tick once.

        runtime.stop_auto_scheduler()
        if runtime._scheduler_thread is not None:
            runtime._scheduler_thread.join(timeout=2)
        if runtime._thread is not None:
            runtime._thread.join(timeout=2)

        assert pipeline.processed_ids == [1, 2]
        assert runtime.status()["runner_status"] == "idle"
    finally:
        runtime.stop_auto_scheduler()
        if runtime._scheduler_thread is not None:
            runtime._scheduler_thread.join(timeout=2)


def test_runtime_allows_start_when_raw_discovered_url_limit_is_disabled() -> None:
    """A -1 raw URL limit should disable crawler capacity gating."""
    pipeline = BlockingQueuePipeline(
        [1],
        raw_discovered_urls=2_000_000,
        raw_discovered_url_limit=-1,
    )
    runtime = CrawlerRuntimeService(pipeline, worker_count=1)

    runtime.start()
    assert pipeline.started.wait(timeout=1)
    pipeline.release.set()
    runtime._thread.join(timeout=2)  # noqa: SLF001 - test waits for the background loop.

    assert pipeline.run_calls == 1
    assert runtime.status()["runner_status"] == "idle"


def test_runtime_stops_before_next_claim_when_raw_discovered_url_limit_is_reached() -> None:
    """A running runtime should finish current work and stop before claiming more blogs."""
    pipeline = BlockingQueuePipeline(
        [1, 2],
        raw_discovered_urls=999_999,
        raw_discovered_url_limit=1_000_000,
    )
    runtime = CrawlerRuntimeService(pipeline, worker_count=1)
    pipeline.on_start_hook = lambda _row: setattr(pipeline.repository, "raw_discovered_urls", 1_000_000)
    pipeline.release.set()

    result = runtime.run_batch(2)

    assert result["accepted"] is True
    assert result["result"]["processed"] == 1
    assert result["result"]["stop_reason"] == "raw_discovered_url_limit_reached"
