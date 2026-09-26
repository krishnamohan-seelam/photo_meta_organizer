"""Progress reporting port for long-running use cases (PMO-22).

The console progress bar (``infrastructure.metrics.ProgressReporter``, tqdm) is one
implementation; an API job reports through its own callback instead and needs none,
so the default is ``NullProgress``.
"""

from typing import Any, Optional, Protocol


class ProgressSink(Protocol):
    """Receives coarse progress events from an indexing run. Must be thread-safe."""

    def start(self, total: Optional[int] = None, desc: str = "") -> None: ...

    def update(self, n: int = 1, metadata: Optional[Any] = None) -> None: ...

    def record_error(self, error_type: str = "unknown") -> None: ...

    def stop(self) -> Any: ...


class NullProgress:
    """A ``ProgressSink`` that ignores everything."""

    def start(self, total: Optional[int] = None, desc: str = "") -> None:
        pass

    def update(self, n: int = 1, metadata: Optional[Any] = None) -> None:
        pass

    def record_error(self, error_type: str = "unknown") -> None:
        pass

    def stop(self) -> None:
        pass
