"""Keep the library analysed (ADR-003 R5, ticket 11): new photos get analysed on their own.

Off until the user turns it on. Even then, analysis starts by itself only when everything is in
its favour, so it never surprises anyone:

* the AI runtime and the model are installed (nothing is ever downloaded for this);
* the photos waiting are no more than the threshold (default 2,000); more than that and the app
  shows the count and asks instead (:attr:`KeepAnalysedState.NEEDS_APPROVAL`);
* nothing else is running and the user has been still for a while;
* on the desktop app, the computer is not on battery;
* the user has not paused an analysis (a paused job waits to be resumed or dismissed).

It is a periodic check, not an event handler: a photo found by a scan, a watched folder or an
import is simply "pending" until the next check finds the conditions met. The job it starts is an
ordinary ``analyze`` job, so it shows in the job pill and can be paused or cancelled there.
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from photo_meta_organizer.application.activity import ActivityTracker
from photo_meta_organizer.application.interfaces.analysis_repository import AnalysisRepository
from photo_meta_organizer.application.interfaces.image_repository import ImageMetadataRepository
from photo_meta_organizer.application.interfaces.state_store import StateStore
from photo_meta_organizer.application.jobs import JobConflictError, JobManager, JobStatus, Work

logger = logging.getLogger(__name__)

SETTING_KEY = "keep_analysed"
DEFAULT_THRESHOLD = 2000  # photos waiting, above which the user is asked first
IDLE_SECONDS = 30.0  # how long the user must have been still
CHECK_SECONDS = 30.0  # how often the conditions are looked at
ANALYZE_PARAMS = {"tags": True}


class KeepAnalysedState(StrEnum):
    OFF = "off"
    UP_TO_DATE = "up_to_date"  # nothing is waiting
    WAITING_FOR_MODEL = "waiting_for_model"  # the AI runtime or the model is not installed
    BUSY = "busy"  # an analysis (or other job) is running
    PAUSED = "paused"  # the user paused an analysis; it waits for Resume or Dismiss
    NEEDS_APPROVAL = "needs_approval"  # more photos wait than the threshold: ask first
    WAITING_FOR_IDLE = "waiting_for_idle"  # the user is busy right now
    ON_BATTERY = "on_battery"
    STALLED = "stalled"  # the last automatic run got nowhere (files that cannot be read)
    READY = "ready"  # all conditions hold: the next check starts an analysis


@dataclass(frozen=True)
class KeepAnalysedStatus:
    enabled: bool
    threshold: int
    pending: int
    state: KeepAnalysedState


class KeepAnalysed:
    def __init__(
        self,
        state: StateStore,
        photos: ImageMetadataRepository,
        analysis: AnalysisRepository,
        jobs: JobManager,
        *,
        model_id: str,
        folder: str,
        make_work: Callable[[], Work],
        model_ready: Callable[[], bool],
        activity: ActivityTracker,
        on_battery: Callable[[], bool] | None = None,
        threshold: int = DEFAULT_THRESHOLD,
        idle_seconds: float = IDLE_SECONDS,
        check_seconds: float = CHECK_SECONDS,
    ) -> None:
        self._state = state
        self._photos = photos
        self._analysis = analysis
        self._jobs = jobs
        self._model_id = model_id
        self._folder = folder
        self._make_work = make_work
        self._model_ready = model_ready
        self._activity = activity
        self._on_battery = on_battery
        self._threshold = threshold
        self._idle = idle_seconds
        self._check_every = check_seconds
        self._tried: int | None = None  # photos waiting when the last automatic run started
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- the setting ----------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._state.get(SETTING_KEY) == "1"

    def set_enabled(self, enabled: bool) -> None:
        self._state.set(SETTING_KEY, "1" if enabled else "0")
        self._tried = None
        self._wake.set()  # look now rather than at the next check

    # -- what is going on -----------------------------------------------------

    def status(self) -> KeepAnalysedStatus:
        pending = max(0, self._photos.count() - self._analysis.count_embeddings(self._model_id))
        return KeepAnalysedStatus(self.enabled, self._threshold, pending, self._assess(pending))

    def _assess(self, pending: int) -> KeepAnalysedState:
        if not self.enabled:
            return KeepAnalysedState.OFF
        if pending == 0:
            return KeepAnalysedState.UP_TO_DATE
        if not self._model_ready():
            return KeepAnalysedState.WAITING_FOR_MODEL
        jobs = self._jobs.list()
        if any(not j.status.is_terminal for j in jobs):
            return KeepAnalysedState.BUSY
        if any(j.kind == "analyze" and j.status is JobStatus.INTERRUPTED for j in jobs):
            return KeepAnalysedState.PAUSED
        if pending > self._threshold:
            return KeepAnalysedState.NEEDS_APPROVAL
        if self._activity.idle_for() < self._idle:
            return KeepAnalysedState.WAITING_FOR_IDLE
        if self._on_battery is not None and self._on_battery():
            return KeepAnalysedState.ON_BATTERY
        if self._tried == pending:
            return KeepAnalysedState.STALLED
        return KeepAnalysedState.READY

    # -- acting ---------------------------------------------------------------

    def tick(self) -> str | None:
        """Start an analysis if every condition holds; the new job's id, or ``None``."""
        status = self.status()
        if status.state is not KeepAnalysedState.READY:
            return None
        try:
            job = self._jobs.submit(
                "analyze", self._folder, self._make_work(), params=dict(ANALYZE_PARAMS)
            )
        except JobConflictError:
            return None
        except Exception:  # noqa: BLE001 - a failure here must not stop the checks
            logger.exception("Could not start the automatic analysis")
            return None
        self._tried = status.pending
        logger.info("Started analysing %d new photo(s) automatically", status.pending)
        return job.id

    def start(self) -> None:
        """Check in the background every ``check_seconds`` (idempotent)."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="keep-analysed", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(self._check_every)
            self._wake.clear()
            if self._stop.is_set():
                return
            try:
                self.tick()
            except Exception:  # noqa: BLE001
                logger.exception("Keep-analysed check failed")
