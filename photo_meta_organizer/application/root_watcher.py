"""Keep the library in step with its roots while the app runs (ADR-003 R11, ticket 10).

New and changed photos appear without a manual scan: the readable roots are watched, the
folders where something changed are collected, and once they have been quiet for a while only
those folders are scanned. A flood of changes (a big copy, a restored backup) falls back to
scanning the whole root. A root that cannot be read (an unplugged drive) is simply not watched;
it is checked again on a timer and when told to (:meth:`RootWatcher.recheck`), and scanned when it
comes back. Nothing here reads a photo or reports an error for an absent drive.

The API and the desktop backend start one; the CLI never does. All timing goes through
:meth:`tick`, so tests drive it with a clock instead of sleeping.
"""

import logging
import os
import threading
import time
from collections.abc import Callable

from photo_meta_organizer.application.interfaces.folder_watcher import FolderWatcher, WatchHandle
from photo_meta_organizer.application.interfaces.root_store import RootStore
from photo_meta_organizer.application.jobs import JobManager
from photo_meta_organizer.application.roots import WorkFactory, is_online, start_scan
from photo_meta_organizer.domain.formats import is_image_filename

logger = logging.getLogger(__name__)

QUIET_SECONDS = 5.0  # changes must stop for this long before anything is scanned
FLOOD_DIRECTORIES = 1000  # more distinct folders than this: scan the whole root instead
RECHECK_SECONDS = 30.0  # how often roots are tested for coming and going
TICK_SECONDS = 0.5


def _key(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _within(path: str, folder: str) -> bool:
    return _key(path) == _key(folder) or _key(path).startswith(_key(folder).rstrip(os.sep) + os.sep)


class RootWatcher:
    def __init__(
        self,
        roots: RootStore,
        jobs: JobManager,
        make_work: WorkFactory,
        watcher: FolderWatcher,
        *,
        quiet_seconds: float = QUIET_SECONDS,
        flood_directories: int = FLOOD_DIRECTORIES,
        recheck_seconds: float = RECHECK_SECONDS,
        online: Callable[[str], bool] = is_online,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._roots = roots
        self._jobs = jobs
        self._make_work = make_work
        self._watcher = watcher
        self._quiet = quiet_seconds
        self._flood = flood_directories
        self._recheck_every = recheck_seconds
        self._online = online
        self._clock = clock

        self._lock = threading.Lock()
        self._pending: set[str] = set()  # folders where something changed
        self._last_change = 0.0
        self._watched: dict[str, str] = {}  # normalised -> as stored: the roots being watched
        self._handle: WatchHandle | None = None
        self._next_check = 0.0
        self._recheck_wanted = True
        self._seen_online = False  # False until the first look at the roots
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> None:
        """Begin watching and ticking in the background (idempotent)."""
        if self._thread is not None:
            return
        self.tick()  # watch the readable roots now; the start-up scan covers their content
        self._thread = threading.Thread(target=self._run, name="root-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        self._stop_watching()

    def recheck(self) -> None:
        """Look at the roots again at the next tick: a drive may have come or gone, or a root
        was added or removed."""
        self._recheck_wanted = True

    # -- input ----------------------------------------------------------------

    def on_change(self, path: str) -> None:
        """A file or folder under a watched root changed (called from the watcher's thread)."""
        folder = os.path.dirname(path)
        if not folder or (os.path.splitext(path)[1] and not is_image_filename(path)):
            return  # an editor's temp file, a sidecar, a cache: not a photo
        with self._lock:
            self._pending.add(folder)
            self._last_change = self._clock()

    # -- the work, one step at a time ----------------------------------------

    def tick(self) -> None:
        """Re-check the roots if due, then scan whatever has been quiet long enough."""
        now = self._clock()
        if self._recheck_wanted or now >= self._next_check:
            self._recheck_wanted = False
            self._next_check = now + self._recheck_every
            self._refresh()
        self._flush(now)

    def _run(self) -> None:
        while not self._stop.wait(TICK_SECONDS):
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - a bad tick must not end the watching
                logger.exception("Root watcher tick failed")

    def _refresh(self) -> None:
        """Watch exactly the readable roots; scan the ones that have just come back."""
        online = {_key(r.path): r.path for r in self._roots.list_roots() if self._online(r.path)}
        came_back = [path for key, path in online.items() if key not in self._watched]
        if online.keys() != self._watched.keys():
            self._stop_watching()
            if online:
                self._handle = self._watcher.start(sorted(online.values()), self.on_change)
            self._watched = online
        if self._seen_online:
            for path in came_back:
                self._scan(path)
        self._seen_online = True

    def _flush(self, now: float) -> None:
        with self._lock:
            if not self._pending or now - self._last_change < self._quiet:
                return
            folders, self._pending = self._pending, set()
        for target in self._targets(folders):
            if not self._scan(target):  # busy: try again after the next quiet spell
                with self._lock:
                    self._pending.add(target)
                    self._last_change = now

    def _targets(self, folders: set[str]) -> list[str]:
        """The folders to scan for these changes: each as deep as it can be, none inside another."""
        by_root: dict[str, set[str]] = {}
        for folder in folders:
            root = self._root_of(folder)
            if root is not None:
                by_root.setdefault(root, set()).add(folder)
        targets: list[str] = []
        for root, inside in sorted(by_root.items()):
            if len(inside) > self._flood:
                targets.append(root)
                continue
            existing = {self._nearest_existing(folder, root) for folder in inside}
            targets += [
                t for t in sorted(existing) if not any(_within(t, o) and o != t for o in existing)
            ]
        return targets

    def _root_of(self, folder: str) -> str | None:
        """The watched root holding ``folder`` (the deepest, if roots are nested)."""
        holding = [root for root in self._watched.values() if _within(folder, root)]
        return max(holding, key=len) if holding else None

    def _nearest_existing(self, folder: str, root: str) -> str:
        """``folder``, or its closest ancestor that still exists (it may have been deleted)."""
        while _key(folder) != _key(root) and not os.path.isdir(folder):
            folder = os.path.dirname(folder)
        return folder

    def _scan(self, folder: str) -> bool:
        """Start a scan of ``folder``; False if another job holds it (so try again later)."""
        try:
            return start_scan(self._jobs, self._make_work, folder) is not None
        except Exception:  # noqa: BLE001 - one folder failing must not stop the others
            logger.exception("Could not start the scan of %s", folder)
            return True  # not busy: do not retry in a loop

    def _stop_watching(self) -> None:
        if self._handle is not None:
            self._handle.stop()
            self._handle = None
        self._watched = {}
