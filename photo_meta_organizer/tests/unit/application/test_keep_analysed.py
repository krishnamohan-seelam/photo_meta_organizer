"""Keep the library analysed: starts by itself only when every guardrail holds (ticket 11)."""

import threading

import pytest

from photo_meta_organizer.application.activity import ActivityTracker
from photo_meta_organizer.application.jobs import JobManager, JobOutcome, JobStatus
from photo_meta_organizer.application.keep_analysed import (
    SETTING_KEY,
    KeepAnalysed,
    KeepAnalysedState,
)


class State:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value


class Photos:
    def __init__(self, total: int) -> None:
        self.total = total

    def count(self) -> int:
        return self.total


class Analysis:
    def __init__(self, done: int = 0) -> None:
        self.done = done

    def count_embeddings(self, model_id: str) -> int:
        return self.done


class Clock:
    now = 1000.0

    def __call__(self) -> float:
        return self.now


class Rig:
    def __init__(self, *, total=10, done=0, threshold=2000):
        self.state = State()
        self.photos = Photos(total)
        self.analysis = Analysis(done)
        self.jobs = JobManager()
        self.clock = Clock()
        self.activity = ActivityTracker(self.clock)
        self.ready = True
        self.battery = False
        self.started = 0
        self.keep = KeepAnalysed(
            self.state,
            self.photos,
            self.analysis,
            self.jobs,
            model_id="m",
            folder="models",
            make_work=self._work,
            model_ready=lambda: self.ready,
            activity=self.activity,
            on_battery=lambda: self.battery,
            threshold=threshold,
            idle_seconds=30.0,
        )

    def _work(self):
        self.started += 1
        return lambda ctx: JobOutcome(message="done")

    def enable(self):
        self.keep.set_enabled(True)

    def state_now(self) -> KeepAnalysedState:
        return self.keep.status().state

    def finish_jobs(self):
        for job in self.jobs.list():
            self.jobs.wait(job.id, timeout=5)


@pytest.fixture
def rig():
    return Rig()


def test_it_is_off_until_the_user_turns_it_on(rig) -> None:
    assert rig.keep.enabled is False and rig.state_now() is KeepAnalysedState.OFF
    assert rig.keep.tick() is None and rig.started == 0


def test_the_setting_is_remembered(rig) -> None:
    rig.enable()
    assert rig.state.values[SETTING_KEY] == "1" and rig.keep.enabled
    rig.keep.set_enabled(False)
    assert not rig.keep.enabled


def test_with_everything_in_its_favour_it_starts_an_ordinary_analyze_job(rig) -> None:
    rig.enable()
    assert rig.state_now() is KeepAnalysedState.READY
    job_id = rig.keep.tick()
    assert job_id is not None
    job = rig.jobs.get(job_id)
    assert (job.kind, job.folder_path.endswith("models"), job.params) == (
        "analyze",
        True,
        {"tags": True},
    )
    assert rig.started == 1


def test_nothing_waiting_means_up_to_date(rig) -> None:
    rig.enable()
    rig.analysis.done = 10
    assert rig.state_now() is KeepAnalysedState.UP_TO_DATE
    assert rig.keep.tick() is None


def test_it_waits_for_the_model_and_never_downloads_it(rig) -> None:
    rig.enable()
    rig.ready = False
    assert rig.state_now() is KeepAnalysedState.WAITING_FOR_MODEL
    assert rig.keep.tick() is None


def test_more_photos_than_the_threshold_asks_instead_of_starting() -> None:
    rig = Rig(total=2500, threshold=2000)
    rig.enable()
    status = rig.keep.status()
    assert (status.state, status.pending, status.threshold) == (
        KeepAnalysedState.NEEDS_APPROVAL,
        2500,
        2000,
    )
    assert rig.keep.tick() is None and rig.started == 0


def test_exactly_the_threshold_still_starts() -> None:
    rig = Rig(total=2000, threshold=2000)
    rig.enable()
    assert rig.state_now() is KeepAnalysedState.READY


def test_it_waits_while_the_user_is_busy_then_starts(rig) -> None:
    rig.enable()
    rig.activity.touch()
    rig.clock.now += 10
    assert rig.state_now() is KeepAnalysedState.WAITING_FOR_IDLE
    assert rig.keep.tick() is None
    rig.clock.now += 25  # 35 s of quiet
    assert rig.state_now() is KeepAnalysedState.READY


def test_on_battery_it_waits(rig) -> None:
    rig.enable()
    rig.battery = True
    assert rig.state_now() is KeepAnalysedState.ON_BATTERY
    assert rig.keep.tick() is None
    rig.battery = False
    assert rig.state_now() is KeepAnalysedState.READY


def test_it_does_not_start_while_another_job_runs(rig) -> None:
    rig.enable()
    release = threading.Event()
    rig.jobs.submit("sync", "photos", lambda ctx: (release.wait(5), JobOutcome())[1])
    try:
        assert rig.state_now() is KeepAnalysedState.BUSY
        assert rig.keep.tick() is None
    finally:
        release.set()
        rig.finish_jobs()


def test_a_paused_analysis_is_left_alone_until_the_user_resumes_or_dismisses_it(rig) -> None:
    rig.enable()
    started = threading.Event()

    def slow(ctx):
        started.set()
        ctx.wait_for_cancel(5)
        return JobOutcome(cancelled=True, message="stopped")

    job = rig.jobs.submit("analyze", "models", slow)
    started.wait(5)
    rig.jobs.pause(job.id)
    paused = rig.jobs.wait(job.id, timeout=5)
    assert paused.status is JobStatus.INTERRUPTED and paused.message.startswith("Paused")
    assert rig.state_now() is KeepAnalysedState.PAUSED
    assert rig.keep.tick() is None

    rig.jobs.dismiss(job.id)
    assert rig.state_now() is KeepAnalysedState.READY


def test_a_run_that_got_nowhere_is_not_repeated_endlessly() -> None:
    rig = Rig(total=10)
    rig.enable()
    assert rig.keep.tick() is not None
    rig.finish_jobs()  # it "analysed" nothing: the same 10 photos still wait
    assert rig.state_now() is KeepAnalysedState.STALLED
    assert rig.keep.tick() is None

    rig.photos.total = 12  # new photos arrive: worth another go
    assert rig.state_now() is KeepAnalysedState.READY


def test_turning_it_off_and_on_again_clears_the_stall(rig) -> None:
    rig.enable()
    rig.keep.tick()
    rig.finish_jobs()
    assert rig.state_now() is KeepAnalysedState.STALLED
    rig.keep.set_enabled(False)
    rig.keep.set_enabled(True)
    assert rig.state_now() is KeepAnalysedState.READY


def test_a_job_that_cannot_be_built_does_not_stop_the_checks(rig) -> None:
    rig.enable()

    def broken():
        raise RuntimeError("no model after all")

    rig.keep._make_work = broken
    assert rig.keep.tick() is None  # logged, not raised
    assert rig.jobs.list() == []


def test_the_background_thread_checks_and_stops_cleanly() -> None:
    rig = Rig()
    rig.keep._check_every = 0.02
    rig.enable()
    rig.keep.start()
    for _ in range(100):
        if rig.started:
            break
        threading.Event().wait(0.02)
    rig.keep.stop()
    assert rig.started >= 1


class TestPause:
    def test_a_running_job_pauses_and_can_be_resumed(self, tmp_path) -> None:
        manager = JobManager()
        started = threading.Event()

        def work(ctx):
            started.set()
            ctx.wait_for_cancel(5)
            return JobOutcome(cancelled=True, message="stopped early")

        job = manager.submit("analyze", str(tmp_path), work)
        started.wait(5)
        manager.pause(job.id)
        done = manager.wait(job.id, timeout=5)
        assert done.status is JobStatus.INTERRUPTED
        assert done.cancel_requested is False and done.message == "Paused. stopped early"

    def test_cancelling_a_pausing_job_cancels_it(self, tmp_path) -> None:
        manager = JobManager()
        started = threading.Event()

        def work(ctx):
            started.set()
            ctx.wait_for_cancel(5)
            return JobOutcome(cancelled=True)

        job = manager.submit("analyze", str(tmp_path), work)
        started.wait(5)
        manager.pause(job.id)
        manager.cancel(job.id)
        assert manager.wait(job.id, timeout=5).status is JobStatus.CANCELLED

    def test_a_finished_job_cannot_be_paused(self, tmp_path) -> None:
        from photo_meta_organizer.application.jobs import JobStateError

        manager = JobManager()
        job = manager.submit("analyze", str(tmp_path), lambda ctx: JobOutcome())
        manager.wait(job.id, timeout=5)
        with pytest.raises(JobStateError):
            manager.pause(job.id)
        with pytest.raises(KeyError):
            manager.pause("nope")
