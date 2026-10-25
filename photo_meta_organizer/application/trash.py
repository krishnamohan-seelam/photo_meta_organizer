"""Removing photos from the library, with a short window to undo it (ADR-003 R11, ticket 12).

``ImageMetadataRepository.remove_assets`` hides photos at once. Here they are deleted for good
once :data:`UNDO_SECONDS` have passed, and all of them when the app starts. Deleting for good
also remembers each file's path (and the size and mtime it had), so a scan does not bring the
photo straight back; a file whose content changed is scanned as a different photo. Files on disk
are never touched.
"""

import logging
import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from photo_meta_organizer.application.interfaces.image_repository import ImageMetadataRepository
from photo_meta_organizer.domain.datetimes import utc_now_naive

logger = logging.getLogger(__name__)

UNDO_SECONDS = 30  # how long a removal can be undone
CHECK_SECONDS = 5.0  # how often removals past that are purged


class TrashPurger:
    def __init__(
        self,
        repository: ImageMetadataRepository,
        *,
        undo_seconds: float = UNDO_SECONDS,
        check_seconds: float = CHECK_SECONDS,
        now: Callable[[], datetime] = utc_now_naive,
    ) -> None:
        self._repository = repository
        self._undo = undo_seconds
        self._check_every = check_seconds
        self._now = now
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def purge_all(self) -> int:
        """Delete every removed photo for good (at start: nothing is left to undo)."""
        return self._repository.purge_removed(None)

    def tick(self) -> int:
        """Delete the photos removed more than ``undo_seconds`` ago; how many went."""
        return self._repository.purge_removed(self._now() - timedelta(seconds=self._undo))

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="trash-purger", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self._check_every):
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - a failed purge is tried again at the next check
                logger.exception("Could not purge removed photos")
