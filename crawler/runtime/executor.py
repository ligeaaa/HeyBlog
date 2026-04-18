"""Serial runtime executor preserving the existing crawler semantics."""

from __future__ import annotations

from threading import Thread
from typing import Callable


class SerialRuntimeExecutor:
    """Run crawler background work on one daemon thread.

    The runtime service depends on this seam so tests can substitute a custom
    executor without changing runtime orchestration logic.
    """

    def start(self, target: Callable[[], None]) -> Thread:
        """Start a background thread that runs the provided runtime target.

        Args:
            target: Zero-argument callable implementing the runtime loop.

        Returns:
            The started daemon ``Thread`` running the target callable.
        """
        thread = Thread(target=target, daemon=True)
        thread.start()
        return thread
