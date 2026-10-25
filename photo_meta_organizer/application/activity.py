"""When did the user last do something? (ticket 11: background work waits for the app to be idle)"""

import threading
import time
from collections.abc import Callable


class ActivityTracker:
    """Remembers the last time a request that means someone is using the app arrived."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._last: float | None = None

    def touch(self) -> None:
        with self._lock:
            self._last = self._clock()

    def idle_for(self) -> float:
        """Seconds since the last touch; infinite if there has been none."""
        with self._lock:
            return float("inf") if self._last is None else self._clock() - self._last
