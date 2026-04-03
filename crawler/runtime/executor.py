"""Serial runtime executor preserving the existing crawler semantics."""

from __future__ import annotations

from threading import Thread
from typing import Callable


class SerialRuntimeExecutor:
    """Run crawler background work on a single daemon thread."""

    def start(self, target: Callable[[], None]) -> Thread:
        """Start the runtime loop on one background thread."""
        thread = Thread(target=target, daemon=True)
        thread.start()
        return thread

