"""Runtime contract tests for multi-worker execution and stop semantics."""

from __future__ import annotations

from threading import Event
from threading import Lock
from threading import Thread

from crawler.runtime import CrawlerRuntimeService


class QueueRepository:
    """Claim one queued blog row at a time."""

    def __init__(self, blog_ids: list[int]) -> None:
        self.blog_ids = list(blog_ids)
        self.lock = Lock()

    def get_next_waiting_blog(self) -> dict[str, object] | None:
        with self.lock:
            if not self.blog_ids:
                return None
            blog_id = self.blog_ids.pop(0)
            return {"id": blog_id, "url": f"https://blog{blog_id}.example.com/"}


class BlockingQueuePipeline:
    """Pipeline stub that blocks one claimed blog until the test releases it."""

    def __init__(self, blog_ids: list[int], *, target_active_runs: int = 1) -> None:
        self.repository = QueueRepository(blog_ids)
        self.target_active_runs = target_active_runs
        self.started = Event()
        self.target_active = Event()
        self.release = Event()
        self.lock = Lock()
        self.run_calls = 0
        self.active_runs = 0
        self.max_active_runs = 0

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
