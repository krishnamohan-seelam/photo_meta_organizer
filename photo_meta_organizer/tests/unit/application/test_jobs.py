"""PMO-18: in-process background jobs (index now, sync in PMO-19)."""

import threading

import pytest
from photo_meta_organizer.application.jobs import (
    JobConflictError,
    JobManager,
    JobOutcome,
    JobStatus,
)


def _blocked_until(event: threading.Event):
    """A work function that finishes once ``event`` is set."""

    def work(ctx):
        event.wait(5)
        return JobOutcome()

    return work


def _run(manager: JobManager, folder: str, outcome: JobOutcome | None = None):
    """Submit a job that returns ``outcome`` at once and wait for it."""
    return _wait(manager, manager.submit("index", folder, lambda ctx: outcome or JobOutcome()).id)


def _wait(manager: JobManager, job_id: str):
    job = manager.wait(job_id, timeout=5)
    assert job.status.is_terminal, f"job still {job.status}"
    return job


@pytest.mark.unit
class TestJobManager:
    def test_successful_job_reports_outcome_and_progress(self, tmp_path) -> None:
        manager = JobManager()

        def work(ctx):
            ctx.report_progress(total=3, processed=3, failed=1)
            return JobOutcome(
                message="done", counts={"indexed": 2, "failed": 1}, errors=["bad.jpg: boom"]
            )

        job = manager.submit("index", str(tmp_path), work)
        assert job.status in (JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.SUCCEEDED)

        done = _wait(manager, job.id)
        assert done.status is JobStatus.SUCCEEDED
        assert (done.total, done.processed, done.failed_count) == (3, 3, 1)
        assert done.counts == {"indexed": 2, "failed": 1}
        assert done.errors == ["bad.jpg: boom"]
        assert done.message == "done"
        assert done.started_at is not None and done.finished_at is not None

    def test_exception_marks_job_failed_with_message(self, tmp_path) -> None:
        manager = JobManager()

        def work(ctx):
            raise RuntimeError("database is locked")

        done = _wait(manager, manager.submit("index", str(tmp_path), work).id)
        assert done.status is JobStatus.FAILED
        assert "database is locked" in done.message

    def test_cancel_sets_flag_and_ends_cancelled(self, tmp_path) -> None:
        manager = JobManager()
        started = threading.Event()

        def work(ctx):
            started.set()
            while not ctx.cancel_requested():
                ctx.wait_for_cancel(0.01)
            return JobOutcome(message="stopped early", cancelled=True)

        job = manager.submit("index", str(tmp_path), work)
        assert started.wait(5)
        assert manager.cancel(job.id).id == job.id

        done = _wait(manager, job.id)
        assert done.status is JobStatus.CANCELLED
        assert done.message == "stopped early"

    def test_cancel_unknown_job_raises_key_error(self) -> None:
        with pytest.raises(KeyError):
            JobManager().cancel("nope")

    def test_second_job_on_same_or_nested_folder_is_rejected(self, tmp_path) -> None:
        manager = JobManager()
        release = threading.Event()
        first = manager.submit(
            "index", str(tmp_path), lambda ctx: (release.wait(5), JobOutcome())[1]
        )

        try:
            with pytest.raises(JobConflictError) as exc:
                manager.submit("sync", str(tmp_path), lambda ctx: JobOutcome())
            assert exc.value.active_job_id == first.id
            with pytest.raises(JobConflictError):
                manager.submit("index", str(tmp_path / "sub"), lambda ctx: JobOutcome())
            with pytest.raises(JobConflictError):
                manager.submit("index", str(tmp_path.parent), lambda ctx: JobOutcome())
        finally:
            release.set()
        _wait(manager, first.id)

        # Once finished, the folder is free again.
        again = manager.submit("index", str(tmp_path), lambda ctx: JobOutcome())
        assert _wait(manager, again.id).status is JobStatus.SUCCEEDED

    def test_unrelated_folders_run_side_by_side(self, tmp_path) -> None:
        manager = JobManager()
        (tmp_path / "a").mkdir()
        (tmp_path / "ab").mkdir()  # prefix of the name, not of the path
        release = threading.Event()
        a = manager.submit(
            "index", str(tmp_path / "a"), lambda ctx: (release.wait(5), JobOutcome())[1]
        )
        b = manager.submit("index", str(tmp_path / "ab"), lambda ctx: JobOutcome())
        assert _wait(manager, b.id).status is JobStatus.SUCCEEDED
        release.set()
        _wait(manager, a.id)

    def test_snapshots_are_copies(self, tmp_path) -> None:
        manager = JobManager()
        job = _wait(
            manager, manager.submit("index", str(tmp_path), lambda ctx: JobOutcome(errors=["x"])).id
        )
        job.errors.append("tampered")
        assert manager.get(job.id).errors == ["x"]

    def test_error_list_is_capped(self, tmp_path) -> None:
        manager = JobManager(max_errors=3)
        job = _wait(
            manager,
            manager.submit(
                "index", str(tmp_path), lambda ctx: JobOutcome(errors=[f"e{i}" for i in range(10)])
            ).id,
        )
        assert job.errors[:3] == ["e0", "e1", "e2"]
        assert len(job.errors) == 4 and "7 more" in job.errors[-1]

    def test_list_is_newest_first_and_history_is_bounded(self, tmp_path) -> None:
        manager = JobManager(history=2)
        ids = [
            _wait(manager, manager.submit("index", str(tmp_path), lambda ctx: JobOutcome()).id).id
            for _ in range(3)
        ]
        listed = [j.id for j in manager.list()]
        assert listed == [ids[2], ids[1]]
        with pytest.raises(KeyError):
            manager.get(ids[0])

    def test_shutdown_cancels_running_jobs(self, tmp_path) -> None:
        manager = JobManager()
        started = threading.Event()

        def work(ctx):
            started.set()
            ctx.wait_for_cancel(5)
            return JobOutcome(cancelled=ctx.cancel_requested())

        job = manager.submit("index", str(tmp_path), work)
        assert started.wait(5)
        manager.shutdown(timeout=5)
        assert manager.get(job.id).status is JobStatus.CANCELLED
