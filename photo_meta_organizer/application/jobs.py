"""Background jobs for long-running work started from the API (PMO-18, ADR-003 R5a).

An HTTP request that indexes 10k photos cannot stay open for the whole run, so the
API submits the work here and returns a job id at once. Each job runs on its own
daemon thread; the client polls a snapshot for progress and the final counts,
including every per-file error (flaw B-21: failures used to be silently dropped).

Rules:
    * Two active jobs may not touch overlapping folders (same folder, or one inside
      the other): an index and a sync of the same tree would race on the same
      records. Unrelated folders run side by side; the repository is thread-safe
      (ADR-001, PMO-08).
    * Cancel is cooperative: the work function polls ``ctx.cancel_requested()`` and
      reports ``JobOutcome(cancelled=True)`` if it stopped early. A request that came
      too late leaves the job ``succeeded`` (with ``cancel_requested`` still true).
    * Only the most recent ``history`` jobs are kept. With a ``JobStore`` they are
      written through to it (progress at most once a second) and survive a restart:
      a job still active when the process ended comes back ``interrupted``, and so
      does one stopped by ``shutdown()``. An interrupted job is never restarted on
      its own: the user resumes it (``resume``, with work rebuilt from its
      ``params``) or dismisses it (``dismiss``).
    * A change worth telling the UI about (a new job, progress at most four times a second,
      a job ending) goes to the ``on_event`` callback, outside the manager's lock. Each change
      is numbered when it happens and a numbered change is dropped if a later one has already
      been delivered, so the last event a listener gets for a job is always its latest state.
"""

import builtins
import copy
import os
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from photo_meta_organizer.application.events import JOB_FINISHED, JOB_PROGRESS

if TYPE_CHECKING:
    from photo_meta_organizer.application.interfaces.job_store import JobStore

INTERRUPTED_MESSAGE = "Interrupted: the app stopped while this job was running."
DISMISSED_MESSAGE = "Interrupted, then dismissed."
PROGRESS_SAVE_SECONDS = 1.0  # progress reaches the store at most this often
PROGRESS_EVENT_SECONDS = 0.25  # ... and the event callback at most this often

JobEventHandler = Callable[[str, "Job"], None]  # (events.JOB_PROGRESS | JOB_FINISHED, snapshot)


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"  # stopped by the app ending; can be resumed or dismissed

    @property
    def is_terminal(self) -> bool:
        """Not queued or running: the job holds no folder and no thread."""
        return self not in (JobStatus.QUEUED, JobStatus.RUNNING)


@dataclass
class Job:
    """A snapshot of one job. ``get``/``list`` return copies, never the live record."""

    id: str
    kind: str
    folder_path: str
    status: JobStatus = JobStatus.QUEUED
    total: int | None = None
    processed: int = 0
    failed_count: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    message: str = ""
    params: dict[str, Any] = field(default_factory=dict)  # what resuming needs to rebuild it
    cancel_requested: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass
class JobOutcome:
    """What a work function returns when it finishes (normally or after a cancel).

    ``counts["failed"]``, when present, becomes the job's final ``failed_count``.
    """

    message: str = ""
    counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False


class JobConflictError(Exception):
    """A job is already running on the same (or an overlapping) folder."""

    def __init__(self, active_job_id: str, folder_path: str) -> None:
        super().__init__(f"Job {active_job_id} is already running on '{folder_path}'.")
        self.active_job_id = active_job_id
        self.folder_path = folder_path


class JobStateError(Exception):
    """The job is not in a state that allows this (only an interrupted job resumes)."""


class JobContext:
    """Handed to the work function: report progress, check for cancel."""

    def __init__(self, manager: "JobManager", job_id: str, cancel_event: threading.Event):
        self._manager = manager
        self._job_id = job_id
        self._cancel_event = cancel_event

    def report_progress(self, total: int | None, processed: int, failed: int) -> None:
        self._manager._update(self._job_id, total=total, processed=processed, failed_count=failed)

    def cancel_requested(self) -> bool:
        return self._cancel_event.is_set()

    def wait_for_cancel(self, timeout: float) -> bool:
        return self._cancel_event.wait(timeout)


Work = Callable[[JobContext], JobOutcome]


def _normalise(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _overlaps(a: str, b: str) -> bool:
    try:
        common = os.path.commonpath([a, b])
    except ValueError:  # different drives on Windows
        return False
    return common in (a, b)


class JobManager:
    """Runs jobs on background threads and keeps their recent history."""

    def __init__(
        self,
        max_errors: int = 100,
        history: int = 50,
        store: "JobStore | None" = None,
        on_event: JobEventHandler | None = None,
    ) -> None:
        self._max_errors = max_errors
        self._on_event = on_event
        self._history = history
        self._store = store
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}  # insertion order = submission order
        self._cancel_events: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._done: dict[str, threading.Event] = {}
        self._saved_at: dict[str, float] = {}
        self._announced_at: dict[str, float] = {}
        self._event_seq: dict[str, int] = {}  # per job: numbers changes, under ``_lock``
        self._published_seq: dict[str, int] = (
            {}
        )  # per job: last delivered, under ``_announce_lock``
        self._announce_lock = threading.Lock()
        self._paused: set[str] = set()  # jobs asked to pause rather than cancel
        if store is not None:
            store.interrupt_active(INTERRUPTED_MESSAGE)
            for job in reversed(store.load(history)):
                self._jobs[job.id] = job

    def submit(
        self, kind: str, folder_path: str, work: Work, params: dict[str, Any] | None = None
    ) -> Job:
        """Start ``work`` on a new thread and return the queued job.

        ``params`` are stored with the job: what ``resume`` needs to rebuild the work.

        Raises:
            JobConflictError: An active job's folder overlaps ``folder_path``.
        """
        with self._lock:
            self._check_folder_free(folder_path)
            job = Job(
                id=uuid.uuid4().hex,
                kind=kind,
                folder_path=os.path.abspath(folder_path),
                params=dict(params or {}),
            )
            self._jobs[job.id] = job
            thread = self._prepare(job, work)
            self._trim_history()
            stamped = self._stamp(job)
        self._announce(JOB_PROGRESS, stamped)
        thread.start()
        return stamped[1]

    def resume(self, job_id: str, work: Work) -> Job:
        """Run an interrupted job again, under the same id, with ``work`` rebuilt from its
        ``params``. Its progress starts from zero; the work itself skips what is done.

        Raises:
            KeyError: Unknown job.
            JobStateError: The job is not interrupted.
            JobConflictError: An active job's folder overlaps this one's.
        """
        with self._lock:
            job = self._interrupted(job_id)
            self._check_folder_free(job.folder_path)
            fresh = Job(
                id=job.id,
                kind=job.kind,
                folder_path=job.folder_path,
                params=job.params,
                created_at=job.created_at,
            )
            self._jobs[job_id] = fresh
            thread = self._prepare(fresh, work)
            stamped = self._stamp(fresh)
        self._announce(JOB_PROGRESS, stamped)
        thread.start()
        return stamped[1]

    def dismiss(self, job_id: str) -> Job:
        """Give up on an interrupted job: it ends ``cancelled`` and is not offered again.

        Raises:
            KeyError: Unknown job.
            JobStateError: The job is not interrupted.
        """
        with self._lock:
            job = self._interrupted(job_id)
            job.status = JobStatus.CANCELLED
            job.message = DISMISSED_MESSAGE
            job.finished_at = datetime.now()
            self._save(job)
            stamped = self._stamp(job)
        self._announce(JOB_FINISHED, stamped)
        return stamped[1]

    def pause(self, job_id: str) -> Job:
        """Ask a job to stop and wait to be resumed: it ends ``interrupted`` (Resume / Dismiss).

        Cooperative, like cancel: the work finishes what is in hand. Resuming runs it again with
        its stored parameters, which is cheap because the work skips what is done.

        Raises:
            KeyError: Unknown job.
            JobStateError: The job is not running.
        """
        with self._lock:
            job = self._jobs[job_id]
            if job.status.is_terminal:
                raise JobStateError(f"Job {job_id} is {job.status.value}, not running.")
            self._paused.add(job_id)
            self._cancel_events[job_id].set()
            stamped = self._stamp(job)
        self._announce(JOB_PROGRESS, stamped)
        return stamped[1]

    def get(self, job_id: str) -> Job:
        """Snapshot of one job. Raises ``KeyError`` if unknown (or aged out)."""
        with self._lock:
            return copy.deepcopy(self._jobs[job_id])

    def list(self) -> list[Job]:
        """Snapshots of the kept jobs, newest first."""
        with self._lock:
            return [copy.deepcopy(j) for j in reversed(self._jobs.values())]

    def cancel(self, job_id: str) -> Job:
        """Ask a job to stop. A finished job is returned unchanged."""
        with self._lock:
            job = self._jobs[job_id]
            asked = not job.status.is_terminal
            if asked:
                self._paused.discard(job_id)
                job.cancel_requested = True
                self._cancel_events[job_id].set()
                self._save(job)
            stamped = self._stamp(job)
        if asked:
            self._announce(JOB_PROGRESS, stamped)
        return stamped[1]

    def wait(self, job_id: str, timeout: float | None = None) -> Job:
        """Block until the job finishes (or ``timeout``), then return its snapshot."""
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            done = self._done.get(job_id)  # none for a job loaded from the store
        if done is not None:
            done.wait(timeout)
        return self.get(job_id)

    def shutdown(self, timeout: float = 10.0) -> None:
        """Stop every active job and wait for their threads.

        A job that stops early because of this ends ``interrupted``, not ``cancelled``:
        the user did not ask for it, so it is offered for resuming next time.
        """
        with self._lock:
            active = [jid for jid, j in self._jobs.items() if not j.status.is_terminal]
            for jid in active:
                self._cancel_events[jid].set()
            threads = [self._threads[jid] for jid in active if jid in self._threads]
        for thread in threads:
            thread.join(timeout)

    # -- internals ------------------------------------------------------------

    def _interrupted(self, job_id: str) -> Job:
        """The live record of an interrupted job (lock held)."""
        job = self._jobs[job_id]
        if job.status is not JobStatus.INTERRUPTED:
            raise JobStateError(f"Job {job_id} is {job.status.value}, not interrupted.")
        return job

    def _check_folder_free(self, folder_path: str) -> None:
        """Raise ``JobConflictError`` if an active job's folder overlaps (lock held)."""
        folder = _normalise(folder_path)
        for job in self._jobs.values():
            if not job.status.is_terminal and _overlaps(_normalise(job.folder_path), folder):
                raise JobConflictError(job.id, job.folder_path)

    def _prepare(self, job: Job, work: Work) -> threading.Thread:
        """Save the queued job and make its (unstarted) thread (lock held)."""
        cancel_event = threading.Event()
        self._cancel_events[job.id] = cancel_event
        self._done[job.id] = threading.Event()
        thread = threading.Thread(
            target=self._run,
            args=(job.id, work, JobContext(self, job.id, cancel_event)),
            name=f"job-{job.kind}-{job.id[:8]}",
            daemon=True,
        )
        self._threads[job.id] = thread
        self._save(job)
        return thread

    def _run(self, job_id: str, work: Work, ctx: JobContext) -> None:
        self._update(job_id, status=JobStatus.RUNNING, started_at=datetime.now())
        try:
            outcome = work(ctx)
        except Exception as exc:  # the job fails, the server does not
            self._update(
                job_id,
                status=JobStatus.FAILED,
                message=f"{type(exc).__name__}: {exc}",
                finished_at=datetime.now(),
            )
        else:
            # The work says whether it stopped early. A cancel that arrived after the
            # last file was already in hand changed nothing, so the job succeeded. One
            # nobody asked for came from shutdown(): the job can be resumed.
            final: dict[str, object] = {}
            if "failed" in outcome.counts:
                final["failed_count"] = outcome.counts["failed"]
            self._update(
                job_id,
                **final,
                status=self._stopped_status(job_id) if outcome.cancelled else JobStatus.SUCCEEDED,
                message=self._paused_message(job_id, outcome),
                counts=dict(outcome.counts),
                errors=self._cap(outcome.errors),
                finished_at=datetime.now(),
            )
        finally:
            with self._lock:
                self._threads.pop(job_id, None)
                done = self._done.get(job_id)
            if done is not None:
                done.set()

    def _paused_message(self, job_id: str, outcome: JobOutcome) -> str:
        with self._lock:
            paused = job_id in self._paused
            self._paused.discard(job_id)
        return f"Paused. {outcome.message}" if paused and outcome.cancelled else outcome.message

    def _stopped_status(self, job_id: str) -> JobStatus:
        with self._lock:
            job = self._jobs.get(job_id)
            asked = job is not None and job.cancel_requested
        return JobStatus.CANCELLED if asked else JobStatus.INTERRUPTED

    def _cap(self, errors: builtins.list[str]) -> builtins.list[str]:
        if len(errors) <= self._max_errors:
            return list(errors)
        extra = len(errors) - self._max_errors
        return list(errors[: self._max_errors]) + [f"... and {extra} more error(s)"]

    def _update(self, job_id: str, **changes: object) -> None:
        progress_only = changes.keys() <= {"total", "processed", "failed_count"}
        now = time.monotonic()
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for name, value in changes.items():
                setattr(job, name, value)
            if not progress_only or now - self._saved_at.get(job_id, 0.0) >= PROGRESS_SAVE_SECONDS:
                self._save(job)
            finished = job.status.is_terminal
            due = now - self._announced_at.get(job_id, 0.0) >= PROGRESS_EVENT_SECONDS
            announce = self._on_event is not None and (finished or not progress_only or due)
            stamped = self._stamp(job) if announce else None
        if stamped is not None:
            self._announce(JOB_FINISHED if finished else JOB_PROGRESS, stamped)

    def _stamp(self, job: Job) -> tuple[int, Job]:
        """A snapshot of ``job`` numbered in the order its changes happened (lock held)."""
        number = self._event_seq.get(job.id, 0) + 1
        self._event_seq[job.id] = number
        return number, copy.deepcopy(job)

    def _announce(self, event_type: str, stamped: tuple[int, Job]) -> None:
        """Tell ``on_event`` about a numbered change, unless a later one was delivered first.

        Called with the manager's lock released, so two threads can arrive out of order (a
        cancel and the job finishing); the number settles it. The callback runs under
        ``_announce_lock`` to keep deliveries in order, and must not call back into the manager.
        """
        if self._on_event is None:
            return
        number, job = stamped
        with self._announce_lock:
            if number <= self._published_seq.get(job.id, 0):
                return
            self._published_seq[job.id] = number
            self._announced_at[job.id] = time.monotonic()
            self._on_event(event_type, job)

    def _save(self, job: Job) -> None:
        """Write the job through to the store, if there is one (lock held)."""
        if self._store is None:
            return
        self._store.save(job)
        self._saved_at[job.id] = time.monotonic()

    def _trim_history(self) -> None:
        """Drop the oldest finished jobs beyond ``history`` (caller holds the lock).

        An interrupted job stays until the user resumes or dismisses it.
        """
        excess = len(self._jobs) - self._history
        if excess <= 0:
            return
        droppable = [
            jid
            for jid, j in self._jobs.items()
            if j.status.is_terminal and j.status is not JobStatus.INTERRUPTED
        ]
        dropped = droppable[:excess]
        for jid in dropped:
            del self._jobs[jid]
            self._cancel_events.pop(jid, None)
            self._done.pop(jid, None)
            self._saved_at.pop(jid, None)
            self._announced_at.pop(jid, None)
            self._event_seq.pop(jid, None)
            self._published_seq.pop(jid, None)
        if dropped and self._store is not None:
            self._store.delete(dropped)
