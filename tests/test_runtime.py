"""Runtime contract tests for stop semantics and single-blog execution."""

from __future__ import annotations

from threading import Event
from threading import Lock
from threading import Thread

from crawler.runtime import CrawlerRuntimeService


class BlockingPipeline:
    """Pipeline stub that blocks inside the current blog until released."""

    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()
        self.lock = Lock()
        self.run_calls = 0
        self.active_runs = 0
        self.max_active_runs = 0

    def run_once(
        self,
        max_nodes: int | None = None,
        *,
        on_blog_start=None,
        on_blog_finish=None,
        on_blog_error=None,
        should_stop=None,
    ) -> dict[str, object]:
        with self.lock:
            self.run_calls += 1
            self.active_runs += 1
            self.max_active_runs = max(self.max_active_runs, self.active_runs)
        blog = {"id": 1, "url": "https://blog.example.com/"}
        if on_blog_start is not None:
            on_blog_start(blog)
        self.started.set()
        self.release.wait(timeout=2)
        if on_blog_finish is not None:
            on_blog_finish(blog, {"discovered": 0})
        with self.lock:
            self.active_runs -= 1
        return {"processed": 1, "discovered": 0, "failed": 0, "exports": {}}


def test_runtime_stop_waits_for_current_blog_to_finish_but_does_not_start_next_blog() -> None:
    """Stop should wait for the active blog to finish and then prevent a new one from starting."""
    pipeline = BlockingPipeline()
    runtime = CrawlerRuntimeService(pipeline)

    runtime.start()
    assert pipeline.started.wait(timeout=1)

    stopping_snapshot = runtime.stop()
    assert stopping_snapshot["runner_status"] == "stopping"

    pipeline.release.set()
    runtime._thread.join(timeout=2)  # noqa: SLF001 - test needs to wait for the background loop.

    status = runtime.status()
    assert status["runner_status"] == "idle"
    assert pipeline.run_calls == 1


def test_runtime_keeps_exactly_one_active_blog_per_runtime_in_phase_one() -> None:
    """The runtime should never execute more than one blog concurrently."""
    pipeline = BlockingPipeline()
    runtime = CrawlerRuntimeService(pipeline)

    runtime.start()
    assert pipeline.started.wait(timeout=1)

    second_start = []

    def try_start_again() -> None:
        second_start.append(runtime.start())

    contender = Thread(target=try_start_again)
    contender.start()
    contender.join(timeout=1)

    pipeline.release.set()
    runtime._thread.join(timeout=2)  # noqa: SLF001 - test needs to wait for the background loop.

    assert pipeline.max_active_runs == 1
    assert second_start
    assert second_start[0]["runner_status"] in {"running", "stopping", "starting"}
