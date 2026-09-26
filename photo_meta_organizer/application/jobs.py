"""In-process background jobs for long-running work started from the API (PMO-18).

An HTTP request that indexes 10k photos cannot stay open for the whole run, so the
API submits the work here and returns a job id at once. Each job runs on its own
daemon thread; the client polls a snapshot for progress and the final counts,
including every per-file error (flaw B-21: failures used to be silently dropped).

Rules:
    * Two active jobs may not touch overlapping folders (same folder, or one inside
      the other): an index and a sync of the same tree would race on the same
      records. Unrelated folders run side by side; the repository is thread-safe
      (ADR-001, PMO-08).
    * Cancel is cooperative: the work function polls ``ctx.cancel_requested()``.
    * Only the most recent ``history`` jobs are kept; nothing is persisted, so a
      restart forgets them (the data they wrote is of course kept).
"""

import builtins
import copy
import os
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED)


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

    def __init__(self, max_errors: int = 100, history: int = 50) -> None:
        self._max_errors = max_errors
        self._history = history
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}  # insertion order = submission order
        self._cancel_events: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._done: dict[str, threading.Event] = {}

    def submit(self, kind: str, folder_path: str, work: Work) -> Job:
        """Start ``work`` on a new thread and return the queued job.

        Raises:
            JobConflictError: An active job's folder overlaps ``folder_path``.
        """
        folder = _normalise(folder_path)
        with self._lock:
            for job in self._jobs.values():
                if not job.status.is_terminal and _overlaps(_normalise(job.folder_path), folder):
                    raise JobConflictError(job.id, job.folder_path)
            job = Job(id=uuid.uuid4().hex, kind=kind, folder_path=os.path.abspath(folder_path))
            self._jobs[job.id] = job
            cancel_event = threading.Event()
            self._cancel_events[job.id] = cancel_event
            self._done[job.id] = threading.Event()
            thread = threading.Thread(
                target=self._run,
                args=(job.id, work, JobContext(self, job.id, cancel_event)),
                name=f"job-{kind}-{job.id[:8]}",
                daemon=True,
            )
            self._threads[job.id] = thread
            self._trim_history()
            snapshot = copy.deepcopy(job)
        thread.start()
        return snapshot

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
            if not job.status.is_terminal:
                job.cancel_requested = True
                self._cancel_events[job_id].set()
            return copy.deepcopy(job)

    def wait(self, job_id: str, timeout: float | None = None) -> Job:
        """Block until the job finishes (or ``timeout``), then return its snapshot."""
        with self._lock:
            done = self._done[job_id]
        done.wait(timeout)
        return self.get(job_id)

    def shutdown(self, timeout: float = 10.0) -> None:
        """Cancel every active job and wait for their threads."""
        with self._lock:
            active = [jid for jid, j in self._jobs.items() if not j.status.is_terminal]
            for jid in active:
                self._jobs[jid].cancel_requested = True
                self._cancel_events[jid].set()
            threads = [self._threads[jid] for jid in active if jid in self._threads]
        for thread in threads:
            thread.join(timeout)

    # -- internals ------------------------------------------------------------

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
            cancelled = outcome.cancelled or ctx.cancel_requested()
            final: dict[str, object] = {}
            if "failed" in outcome.counts:
                final["failed_count"] = outcome.counts["failed"]
            self._update(
                job_id,
                **final,
                status=JobStatus.CANCELLED if cancelled else JobStatus.SUCCEEDED,
                message=outcome.message,
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

    def _cap(self, errors: builtins.list[str]) -> builtins.list[str]:
        if len(errors) <= self._max_errors:
            return list(errors)
        extra = len(errors) - self._max_errors
        return list(errors[: self._max_errors]) + [f"... and {extra} more error(s)"]

    def _update(self, job_id: str, **changes: object) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for name, value in changes.items():
                setattr(job, name, value)

    def _trim_history(self) -> None:
        """Drop the oldest finished jobs beyond ``history`` (caller holds the lock)."""
        excess = len(self._jobs) - self._history
        if excess <= 0:
            return
        for jid in [jid for jid, j in self._jobs.items() if j.status.is_terminal][:excess]:
            del self._jobs[jid]
            self._cancel_events.pop(jid, None)
            self._done.pop(jid, None)
