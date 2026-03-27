"""In-memory crawler runtime state and control loop."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event
from threading import Lock
from threading import Thread
from typing import Any
from uuid import uuid4

from app.crawler.pipeline import CrawlPipeline


def utc_now() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


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


class CrawlerRuntimeService:
    """Manage crawler execution state and control actions."""

    def __init__(self, pipeline: CrawlPipeline) -> None:
        self.pipeline = pipeline
        self._snapshot = RuntimeSnapshot()
        self._lock = Lock()
        self._stop_event = Event()
        self._thread: Thread | None = None

    def status(self) -> dict[str, Any]:
        """Return the current runtime snapshot."""
        with self._lock:
            return asdict(self._snapshot)

    def current(self) -> dict[str, Any]:
        """Return the active blog currently being processed."""
        snapshot = self.status()
        return {
            "runner_status": snapshot["runner_status"],
            "active_run_id": snapshot["active_run_id"],
            "current_blog_id": snapshot["current_blog_id"],
            "current_url": snapshot["current_url"],
            "current_stage": snapshot["current_stage"],
            "last_started_at": snapshot["last_started_at"],
            "last_error": snapshot["last_error"],
        }

    def start(self) -> dict[str, Any]:
        """Start the background crawler loop."""
        with self._lock:
            if self._snapshot.runner_status in {"starting", "running", "stopping"}:
                return asdict(self._snapshot)

            self._stop_event.clear()
            self._snapshot.runner_status = "starting"
            self._snapshot.active_run_id = str(uuid4())
            self._snapshot.last_started_at = utc_now()
            self._snapshot.last_error = None
            self._snapshot.last_result = None

            self._thread = Thread(target=self._run_background_loop, daemon=True)
            self._thread.start()
            return asdict(self._snapshot)

    def stop(self) -> dict[str, Any]:
        """Request the background loop to stop after the current safe checkpoint."""
        with self._lock:
            if self._snapshot.runner_status == "idle":
                return asdict(self._snapshot)

            self._stop_event.set()
            self._snapshot.runner_status = "stopping"
            return asdict(self._snapshot)

    def run_batch(self, max_nodes: int) -> dict[str, Any]:
        """Run a synchronous batch when the background loop is idle."""
        with self._lock:
            if self._snapshot.runner_status in {"starting", "running", "stopping"}:
                return {
                    "accepted": False,
                    "reason": "runtime_busy",
                    "runtime": asdict(self._snapshot),
                }
            self._snapshot.runner_status = "running"
            self._snapshot.active_run_id = str(uuid4())
            self._snapshot.last_started_at = utc_now()
            self._snapshot.last_error = None
            self._snapshot.last_result = None

        try:
            result = self.pipeline.run_once(
                max_nodes=max_nodes,
                on_blog_start=self._on_blog_start,
                on_blog_finish=self._on_blog_finish,
                on_blog_error=self._on_blog_error,
                should_stop=self._stop_event.is_set,
            )
            with self._lock:
                self._snapshot.runner_status = "idle"
                self._snapshot.current_blog_id = None
                self._snapshot.current_url = None
                self._snapshot.current_stage = None
                self._snapshot.last_stopped_at = utc_now()
                self._snapshot.last_result = result
                return {
                    "accepted": True,
                    "mode": "batch",
                    "result": result,
                    "runtime": asdict(self._snapshot),
                }
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._snapshot.runner_status = "error"
                self._snapshot.last_error = str(exc)
                self._snapshot.last_stopped_at = utc_now()
                raise

    def _run_background_loop(self) -> None:
        """Run the crawler continuously until idle or stop is requested."""
        with self._lock:
            self._snapshot.runner_status = "running"

        aggregate = {"processed": 0, "discovered": 0, "failed": 0, "exports": {}}

        try:
            while not self._stop_event.is_set():
                result = self.pipeline.run_once(
                    max_nodes=1,
                    on_blog_start=self._on_blog_start,
                    on_blog_finish=self._on_blog_finish,
                    on_blog_error=self._on_blog_error,
                    should_stop=self._stop_event.is_set,
                )
                aggregate["processed"] += int(result["processed"])
                aggregate["discovered"] += int(result["discovered"])
                aggregate["failed"] += int(result["failed"])
                aggregate["exports"] = result["exports"]

                if result["processed"] == 0:
                    break
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._snapshot.runner_status = "error"
                self._snapshot.last_error = str(exc)
                self._snapshot.last_stopped_at = utc_now()
                self._snapshot.current_blog_id = None
                self._snapshot.current_url = None
                self._snapshot.current_stage = None
            return

        with self._lock:
            self._snapshot.runner_status = "idle"
            self._snapshot.current_blog_id = None
            self._snapshot.current_url = None
            self._snapshot.current_stage = None
            self._snapshot.last_stopped_at = utc_now()
            self._snapshot.last_result = aggregate
            self._stop_event.clear()

    def _on_blog_start(self, blog: dict[str, Any]) -> None:
        with self._lock:
            self._snapshot.runner_status = "running"
            self._snapshot.current_blog_id = int(blog["id"])
            self._snapshot.current_url = str(blog["url"])
            self._snapshot.current_stage = "crawling"

    def _on_blog_finish(self, blog: dict[str, Any], result: dict[str, Any]) -> None:
        with self._lock:
            self._snapshot.current_blog_id = int(blog["id"])
            self._snapshot.current_url = str(blog["url"])
            self._snapshot.current_stage = "completed"
            self._snapshot.last_result = result

    def _on_blog_error(self, blog: dict[str, Any], error: Exception) -> None:
        with self._lock:
            self._snapshot.current_blog_id = int(blog["id"])
            self._snapshot.current_url = str(blog["url"])
            self._snapshot.current_stage = "error"
            self._snapshot.last_error = str(error)
