"""Base class for input backends.

Each backend runs its own daemon thread, reads from some source (an input
device, a subprocess, stdin), translates what it reads into
:class:`~nostalgiabox.actions.InputEvent` values, and pushes them onto the
shared queue provided at :meth:`start`.
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from queue import Queue

from ..actions import InputEvent

log = logging.getLogger(__name__)


class InputBackend(ABC):
    """A source of remote-control events running on a background thread."""

    name = "input"

    def __init__(self) -> None:
        self._queue: "Queue[InputEvent]" = Queue()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self, queue: "Queue[InputEvent]") -> None:
        """Begin reading events onto ``queue`` from a background thread."""
        self._queue = queue
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_guarded, name=f"input-{self.name}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def emit(self, event: InputEvent) -> None:
        self._queue.put(event)

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    def _run_guarded(self) -> None:
        try:
            self._run()
        except Exception:  # noqa: BLE001 - a bad backend must not take down the TV
            log.exception("input backend %r crashed", self.name)

    @abstractmethod
    def _run(self) -> None:
        """Read from the source until :attr:`stopping` becomes true."""

    def _close(self) -> None:
        """Release any resources (override if needed)."""


__all__ = ["InputBackend"]
