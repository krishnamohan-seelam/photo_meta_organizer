"""Port for watching folders for changes (ADR-003 R11, ticket 10).

The watcher only says that something under a folder changed; it reads no files. What to do about
it (wait for quiet, scan the affected folders) is the ``RootWatcher``'s business (in
``application/root_watcher.py``). A real implementation uses the operating system's change
notifications; tests use a fake that emits paths on demand.
"""

from collections.abc import Callable, Sequence
from typing import Protocol


class WatchHandle(Protocol):
    """A running watch, to be stopped when the folders it covers change."""

    def stop(self) -> None:
        """Stop watching and release the operating system's resources. Safe to call twice."""
        ...


class FolderWatcher(Protocol):
    def start(self, folders: Sequence[str], on_change: Callable[[str], None]) -> WatchHandle:
        """Watch ``folders`` (and everything under them) without blocking.

        ``on_change`` gets the absolute path of each file or folder that was added, changed or
        removed. It is called from the watcher's own thread and must return quickly.
        """
        ...
