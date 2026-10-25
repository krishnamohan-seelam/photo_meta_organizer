"""An in-process event bus behind ``GET /api/events`` (ADR-003 R5b).

Job threads and request handlers publish what changed; the SSE endpoint hands it to the
browser, so the UI no longer polls. Every event has an id that only grows. The bus keeps the
last ``capacity`` events so a client that dropped its connection can reconnect with
``Last-Event-ID`` and be replayed what it missed. If it was away for longer than the buffer
reaches, ``read_after`` says so and the client reloads instead of guessing. Ids on the wire carry
the bus's ``run_id`` (``<run>.<n>``), so an id from before a server restart is recognised as
another run's even when its number happens to fall inside the new buffer.
"""

import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

JOB_PROGRESS = "job_progress"
JOB_FINISHED = "job_finished"
LIBRARY_CHANGED = "library_changed"
RESYNC = "resync"


@dataclass(frozen=True)
class Event:
    id: int
    type: str
    data: dict[str, Any] = field(default_factory=dict)


class EventBus:
    """Thread-safe publish and a blocking, resumable read."""

    def __init__(self, capacity: int = 200) -> None:
        self._buffer: deque[Event] = deque(maxlen=capacity)
        self._last_id = 0
        self._closed = False
        self.run_id = uuid.uuid4().hex[:8]
        self._changed = threading.Condition()

    @property
    def last_id(self) -> int:
        """Id of the newest event, 0 before the first."""
        with self._changed:
            return self._last_id

    def publish(self, type: str, data: dict[str, Any] | None = None) -> Event:
        """Add an event and wake every reader."""
        with self._changed:
            self._last_id += 1
            event = Event(self._last_id, type, dict(data or {}))
            self._buffer.append(event)
            self._changed.notify_all()
            return event

    def read_after(self, last_id: int, timeout: float) -> list[Event] | None:
        """Events newer than ``last_id``, waiting up to ``timeout`` seconds for one.

        Returns an empty list on timeout (or once the bus is closed) and ``None`` when
        ``last_id`` is older than the buffer reaches or newer than any event published: the
        caller missed something it cannot be sent, or belongs to another run, and must resync.
        """
        with self._changed:
            if not self._closed and last_id == self._last_id:
                self._changed.wait(timeout)
            if last_id > self._last_id or self._missed(last_id):
                return None
            return [e for e in self._buffer if e.id > last_id]

    def wire_id(self, event_id: int) -> str:
        """The id as sent to clients: the number, tagged with this run of the bus."""
        return f"{self.run_id}.{event_id}"

    def parse_wire_id(self, text: str | None) -> tuple[int | None, bool]:
        """Read a client's ``Last-Event-ID`` as ``(event id, stale)``.

        ``stale`` is true for an id that belongs to another run of the server: the client must
        resync, whatever the number says. A missing or malformed id is a fresh connection.
        """
        run, _, number = (text or "").partition(".")
        if not number.isdigit():
            return None, False
        return (int(number), False) if run == self.run_id else (None, True)

    def close(self) -> None:
        """Release every waiting reader (the server is stopping)."""
        with self._changed:
            self._closed = True
            self._changed.notify_all()

    @property
    def closed(self) -> bool:
        with self._changed:
            return self._closed

    def _missed(self, last_id: int) -> bool:
        """True if events after ``last_id`` have already left the buffer (lock held)."""
        if not self._buffer:
            return last_id < self._last_id
        return self._buffer[0].id > last_id + 1
