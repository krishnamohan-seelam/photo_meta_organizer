"""Where background jobs are kept between runs of the app (ADR-003 R5a)."""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from photo_meta_organizer.application.jobs import Job


class JobStore(Protocol):
    """Persists job snapshots; ``JobManager`` writes through to it."""

    def save(self, job: "Job") -> None:
        """Insert or replace the stored copy of ``job``."""
        ...

    def load(self, limit: int) -> "list[Job]":
        """The ``limit`` most recently created jobs, newest first."""
        ...

    def delete(self, job_ids: Sequence[str]) -> None:
        """Forget these jobs (unknown ids are ignored)."""
        ...

    def interrupt_active(self, message: str) -> int:
        """Mark every queued or running job ``interrupted`` with ``message``; return how many.

        Called once at startup: a job still active then was stopped by the process ending.
        """
        ...
