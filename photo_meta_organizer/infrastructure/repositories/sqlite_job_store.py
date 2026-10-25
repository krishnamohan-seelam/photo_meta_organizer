"""SQLite implementation of ``JobStore`` (ADR-003 R5a, ticket 07).

Shares the connection and lock of a sibling :class:`SqliteRepository` (pass
``repo.connection`` and ``repo.lock``), like the collection and analysis repositories; the
``jobs`` table comes from that repository's migrations (0004).
"""

import json
import sqlite3
import threading
from collections.abc import Sequence
from datetime import datetime

from photo_meta_organizer.application.jobs import Job, JobStatus

_COLUMNS = (
    "id, kind, folder, status, total, processed, failed, counts, errors, message, params, "
    "cancel_requested, created_at, started_at, finished_at"
)


def _to_text(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _to_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


class SqliteJobStore:
    """Job history in the library's ``jobs`` table."""

    def __init__(self, connection: sqlite3.Connection, lock: threading.RLock) -> None:
        self._conn = connection
        self._lock = lock

    def save(self, job: Job) -> None:
        row = (
            job.id,
            job.kind,
            job.folder_path,
            job.status.value,
            job.total,
            job.processed,
            job.failed_count,
            json.dumps(job.counts),
            json.dumps(job.errors),
            job.message,
            json.dumps(job.params),
            int(job.cancel_requested),
            job.created_at.isoformat(),
            _to_text(job.started_at),
            _to_text(job.finished_at),
        )
        with self._lock, self._conn:
            self._conn.execute(
                f"INSERT OR REPLACE INTO jobs ({_COLUMNS}) VALUES ({', '.join('?' * len(row))})",
                row,
            )

    def load(self, limit: int) -> list[Job]:
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {_COLUMNS} FROM jobs ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_job(row) for row in rows]

    def delete(self, job_ids: Sequence[str]) -> None:
        with self._lock, self._conn:
            self._conn.executemany("DELETE FROM jobs WHERE id = ?", [(i,) for i in job_ids])

    def interrupt_active(self, message: str) -> int:
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "UPDATE jobs SET status = ?, message = ?, finished_at = ? WHERE status IN (?, ?)",
                (
                    JobStatus.INTERRUPTED.value,
                    message,
                    datetime.now().isoformat(),
                    JobStatus.QUEUED.value,
                    JobStatus.RUNNING.value,
                ),
            )
        return cursor.rowcount


def _job(row: sqlite3.Row | tuple) -> Job:
    (
        job_id,
        kind,
        folder,
        status,
        total,
        processed,
        failed,
        counts,
        errors,
        message,
        params,
        cancel_requested,
        created_at,
        started_at,
        finished_at,
    ) = tuple(row)
    return Job(
        id=job_id,
        kind=kind,
        folder_path=folder,
        status=JobStatus(status),
        total=total,
        processed=processed,
        failed_count=failed,
        counts=json.loads(counts),
        errors=json.loads(errors),
        message=message,
        params=json.loads(params),
        cancel_requested=bool(cancel_requested),
        created_at=datetime.fromisoformat(created_at),
        started_at=_to_datetime(started_at),
        finished_at=_to_datetime(finished_at),
    )
