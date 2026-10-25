"""Jobs survive a restart (ADR-003 R5a, ticket 07).

A restart is a new repository and a new ``JobManager`` on the same database file.
"""

import threading

import pytest

from photo_meta_organizer.application.composition import build_job_store, build_repository
from photo_meta_organizer.application.jobs import (
    JobConflictError,
    JobManager,
    JobOutcome,
    JobStateError,
    JobStatus,
)


def _manager(db_path) -> JobManager:
    return JobManager(store=build_job_store(build_repository(str(db_path))))


def _finished(manager: JobManager, job_id: str):
    job = manager.wait(job_id, timeout=5)
    assert job.status.is_terminal, f"job still {job.status}"
    return job


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "photos.db"


def test_a_finished_job_is_still_listed_after_a_restart(db_path, tmp_path) -> None:
    before = _manager(db_path)

    def work(ctx):
        ctx.report_progress(total=3, processed=3, failed=1)
        return JobOutcome(
            message="Indexed 2.", counts={"indexed": 2, "failed": 1}, errors=["bad.jpg: boom"]
        )

    job = before.submit("index", str(tmp_path), work, params={"workers": 2})
    done = _finished(before, job.id)

    after = _manager(db_path)
    [kept] = after.list()
    assert kept.id == job.id
    assert kept.kind == "index"
    assert kept.folder_path == done.folder_path
    assert kept.status is JobStatus.SUCCEEDED
    assert (kept.total, kept.processed, kept.failed_count) == (3, 3, 1)
    assert kept.counts == {"indexed": 2, "failed": 1}
    assert kept.errors == ["bad.jpg: boom"]
    assert kept.message == "Indexed 2."
    assert kept.params == {"workers": 2}
    assert kept.created_at == done.created_at
    assert kept.started_at == done.started_at
    assert kept.finished_at == done.finished_at


def _running(manager: JobManager, folder: str, params=None):
    """Submit a job that runs until it is told to stop; return it once it has started."""
    started = threading.Event()

    def work(ctx):
        started.set()
        ctx.wait_for_cancel(5)
        return JobOutcome(cancelled=True)

    job = manager.submit("sync", folder, work, params=params)
    assert started.wait(5)
    return job


def test_a_job_still_running_when_the_app_ended_comes_back_interrupted(db_path, tmp_path) -> None:
    before = _manager(db_path)
    job = _running(before, str(tmp_path))  # the process "dies": no shutdown()

    after = _manager(db_path)
    kept = after.get(job.id)
    assert kept.status is JobStatus.INTERRUPTED
    assert "Interrupted" in kept.message
    before.shutdown(timeout=5)  # let the thread end; the restarted manager is unaffected
    assert after.get(job.id).status is JobStatus.INTERRUPTED


def test_a_job_stopped_by_shutdown_comes_back_interrupted(db_path, tmp_path) -> None:
    before = _manager(db_path)
    job = _running(before, str(tmp_path))
    before.shutdown(timeout=5)

    assert _manager(db_path).get(job.id).status is JobStatus.INTERRUPTED


def test_a_job_the_user_cancelled_stays_cancelled(db_path, tmp_path) -> None:
    before = _manager(db_path)
    job = _running(before, str(tmp_path))
    before.cancel(job.id)
    _finished(before, job.id)

    assert _manager(db_path).get(job.id).status is JobStatus.CANCELLED


def test_resuming_runs_the_job_again_under_the_same_id(db_path, tmp_path) -> None:
    before = _manager(db_path)
    job = _running(before, str(tmp_path), params={"rehash": True})
    before.shutdown(timeout=5)

    after = _manager(db_path)
    resumed = after.resume(job.id, lambda ctx: JobOutcome(message="Synced.", counts={"new": 1}))
    assert resumed.id == job.id
    done = _finished(after, job.id)
    assert done.status is JobStatus.SUCCEEDED
    assert done.message == "Synced."
    assert done.params == {"rehash": True}
    assert done.created_at == after.get(job.id).created_at
    assert [j.id for j in after.list()] == [job.id]

    assert _manager(db_path).get(job.id).status is JobStatus.SUCCEEDED


def test_dismissing_ends_the_job_for_good(db_path, tmp_path) -> None:
    before = _manager(db_path)
    job = _running(before, str(tmp_path))
    before.shutdown(timeout=5)

    after = _manager(db_path)
    assert after.dismiss(job.id).status is JobStatus.CANCELLED
    assert _manager(db_path).get(job.id).status is JobStatus.CANCELLED


def test_only_an_interrupted_job_can_be_resumed_or_dismissed(db_path, tmp_path) -> None:
    manager = _manager(db_path)
    job = _finished(manager, manager.submit("index", str(tmp_path), lambda ctx: JobOutcome()).id)

    with pytest.raises(JobStateError):
        manager.resume(job.id, lambda ctx: JobOutcome())
    with pytest.raises(JobStateError):
        manager.dismiss(job.id)
    with pytest.raises(KeyError):
        manager.resume("nope", lambda ctx: JobOutcome())


def test_resuming_waits_for_a_free_folder(db_path, tmp_path) -> None:
    before = _manager(db_path)
    job = _running(before, str(tmp_path))
    before.shutdown(timeout=5)

    after = _manager(db_path)
    busy = _running(after, str(tmp_path))
    with pytest.raises(JobConflictError):
        after.resume(job.id, lambda ctx: JobOutcome())
    after.shutdown(timeout=5)
    assert after.get(busy.id).status is JobStatus.INTERRUPTED


def test_history_trimmed_in_memory_is_trimmed_in_the_store(db_path, tmp_path) -> None:
    store = build_job_store(build_repository(str(db_path)))
    manager = JobManager(store=store, history=2)
    ids = [
        _finished(manager, manager.submit("index", str(tmp_path), lambda ctx: JobOutcome()).id).id
        for _ in range(3)
    ]
    assert [j.id for j in store.load(10)] == [ids[2], ids[1]]


def test_old_history_is_trimmed_but_never_an_interrupted_job(db_path, tmp_path) -> None:
    store = build_job_store(build_repository(str(db_path)))
    leftover = JobManager(store=store)
    stuck = leftover.submit("index", str(tmp_path / "a"), lambda ctx: _wait(ctx))
    leftover.shutdown(timeout=5)
    assert _finished(leftover, stuck.id).status is JobStatus.INTERRUPTED

    manager = JobManager(history=2, store=store)
    for i in range(3):
        _finished(manager, manager.submit("index", str(tmp_path / str(i)), _quick).id)
    kept = {j.id: j.status for j in manager.list()}
    assert kept[stuck.id] is JobStatus.INTERRUPTED
    assert len(kept) == 2  # the interrupted job and the newest; older finished ones are trimmed


def _quick(ctx) -> JobOutcome:
    return JobOutcome(message="ok")


def _wait(ctx) -> JobOutcome:
    ctx.wait_for_cancel(5)
    return JobOutcome(message="stopped", cancelled=True)
