"""``FolderWatcher`` on the ``watchfiles`` package (operating-system change notifications).

One daemon thread per watch. A folder that disappears (an unplugged drive) can make the watch
raise; that ends the thread quietly, and the root watcher's periodic re-check notices the
folder is gone and starts a new watch for what is still there.
"""

import logging
import threading
from collections.abc import Callable, Sequence

import watchfiles

logger = logging.getLogger(__name__)

# Events closer together than this are reported as one batch by watchfiles itself.
BATCH_MS = 500


class _Handle:
    def __init__(self, stop: threading.Event, thread: threading.Thread) -> None:
        self._stop = stop
        self._thread = thread

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not threading.current_thread():
            self._thread.join(timeout=5)


class WatchfilesFolderWatcher:
    def start(self, folders: Sequence[str], on_change: Callable[[str], None]) -> _Handle:
        stop = threading.Event()
        paths = list(folders)

        def run() -> None:
            try:
                for changes in watchfiles.watch(
                    *paths,
                    stop_event=stop,
                    debounce=BATCH_MS,
                    raise_interrupt=False,
                    ignore_permission_denied=True,
                ):
                    for _kind, path in changes:
                        on_change(path)
            except Exception:  # noqa: BLE001 - a vanished folder must not take the app down
                if not stop.is_set():
                    logger.warning("Stopped watching %s", paths, exc_info=True)

        thread = threading.Thread(target=run, name="folder-watcher", daemon=True)
        thread.start()
        return _Handle(stop, thread)
