"""RootWatcher: debounce, scan what changed, flood fallback, roots coming and going (ticket 10)."""

import os
from datetime import datetime

import pytest
from tests.fakes import FakeFolderWatcher

from photo_meta_organizer.application.jobs import JobManager, JobOutcome
from photo_meta_organizer.application.root_watcher import RootWatcher
from photo_meta_organizer.application.roots import Root


class Roots:
    def __init__(self, *paths: str) -> None:
        self.paths = list(paths)

    def list_roots(self):
        return [Root(p, datetime(2026, 10, 25)) for p in self.paths]


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "photos"
    for sub in ("a", "b", "a/inner"):
        (root / sub).mkdir(parents=True)
    return root


class Rig:
    def __init__(self, roots, online=None, flood=1000):
        self.roots = Roots(*roots)
        self.clock = Clock()
        self.fake = FakeFolderWatcher()
        self.scans: list[str] = []
        self.jobs = JobManager()
        self.offline: set[str] = set()
        self.watcher = RootWatcher(
            self.roots,
            self.jobs,
            self._work,
            self.fake,
            quiet_seconds=5.0,
            flood_directories=flood,
            recheck_seconds=30.0,
            online=online or (lambda path: path not in self.offline and os.path.isdir(path)),
            clock=self.clock,
        )

    def _work(self, folder, params):
        self.scans.append(folder)
        return lambda ctx: JobOutcome(message="ok")

    def settle(self):
        for job in self.jobs.list():
            self.jobs.wait(job.id, timeout=5)


@pytest.fixture
def rig(library):
    rig = Rig([str(library)])
    rig.watcher.tick()  # first look: starts watching, scans nothing
    return rig


def test_the_readable_roots_are_watched_and_nothing_is_scanned_for_that(rig, library) -> None:
    assert rig.fake.started == [(str(library),)]
    assert rig.scans == []


def test_nothing_is_scanned_until_the_changes_have_been_quiet(rig, library) -> None:
    rig.fake.emit(str(library / "a" / "new.jpg"))
    rig.clock.advance(4)
    rig.watcher.tick()
    assert rig.scans == []
    rig.fake.emit(str(library / "a" / "newer.jpg"))  # more activity restarts the wait
    rig.clock.advance(4)
    rig.watcher.tick()
    assert rig.scans == []
    rig.clock.advance(2)
    rig.watcher.tick()
    assert rig.scans == [str(library / "a")]


def test_only_the_folders_that_changed_are_scanned(rig, library) -> None:
    rig.fake.emit(str(library / "a" / "1.jpg"), str(library / "b" / "2.jpg"))
    rig.clock.advance(6)
    rig.watcher.tick()
    assert sorted(rig.scans) == sorted([str(library / "a"), str(library / "b")])


def test_a_folder_inside_another_changed_folder_is_covered_by_it(rig, library) -> None:
    rig.fake.emit(str(library / "a" / "1.jpg"), str(library / "a" / "inner" / "2.jpg"))
    rig.clock.advance(6)
    rig.watcher.tick()
    assert rig.scans == [str(library / "a")]


def test_files_that_are_not_photos_are_ignored(rig, library) -> None:
    rig.fake.emit(str(library / "a" / "notes.txt"), str(library / "a" / "x.jpg.tmp"))
    rig.clock.advance(6)
    rig.watcher.tick()
    assert rig.scans == []


def test_a_folder_that_was_deleted_is_scanned_from_its_nearest_parent(rig, library) -> None:
    rig.fake.emit(str(library / "gone" / "deep" / "1.jpg"))  # the folder no longer exists
    rig.clock.advance(6)
    rig.watcher.tick()
    assert rig.scans == [str(library)]


def test_a_flood_of_folders_scans_the_whole_root_once(library) -> None:
    rig = Rig([str(library)], flood=2)
    rig.watcher.tick()
    rig.fake.emit(*(str(library / sub / "x.jpg") for sub in ("a", "b", "a/inner")))
    rig.clock.advance(6)
    rig.watcher.tick()
    assert rig.scans == [str(library)]


def test_changes_outside_the_roots_are_ignored(rig, tmp_path) -> None:
    rig.fake.emit(str(tmp_path / "elsewhere" / "x.jpg"))
    rig.clock.advance(6)
    rig.watcher.tick()
    assert rig.scans == []


def test_a_folder_that_is_busy_is_tried_again_after_the_next_quiet_spell(library) -> None:
    import threading

    rig = Rig([str(library)])
    rig.watcher.tick()
    release = threading.Event()
    rig.jobs.submit("sync", str(library), lambda ctx: (release.wait(5), JobOutcome())[1])
    try:
        rig.fake.emit(str(library / "a" / "1.jpg"))
        rig.clock.advance(6)
        rig.watcher.tick()
        assert len(rig.jobs.list()) == 1  # the whole root is being scanned already: no new job
    finally:
        release.set()
        rig.settle()
    rig.clock.advance(6)
    rig.watcher.tick()
    assert [j.folder_path for j in rig.jobs.list()][0] == str(library / "a")


def test_an_unplugged_root_stops_being_watched_without_a_scan_or_an_error(
    library, tmp_path
) -> None:
    usb = tmp_path / "usb"
    usb.mkdir()
    rig = Rig([str(library), str(usb)])
    rig.watcher.tick()
    assert rig.fake.started[-1] == tuple(sorted([str(library), str(usb)]))

    rig.offline.add(str(usb))
    rig.watcher.recheck()
    rig.watcher.tick()
    assert rig.fake.started[-1] == (str(library),)
    assert rig.scans == []


def test_a_root_that_comes_back_is_watched_again_and_scanned(library, tmp_path) -> None:
    usb = tmp_path / "usb"
    usb.mkdir()
    rig = Rig([str(library), str(usb)])
    rig.offline.add(str(usb))
    rig.watcher.tick()
    assert rig.fake.started == [(str(library),)]

    rig.offline.clear()
    rig.clock.advance(31)  # the timer, no hint needed
    rig.watcher.tick()
    assert rig.fake.started[-1] == tuple(sorted([str(library), str(usb)]))
    assert rig.scans == [str(usb)]


def test_a_newly_added_root_is_picked_up_on_recheck(rig, tmp_path) -> None:
    extra = tmp_path / "more"
    extra.mkdir()
    rig.roots.paths.append(str(extra))
    rig.watcher.recheck()
    rig.watcher.tick()
    assert str(extra) in rig.fake.started[-1]


def test_the_roots_are_not_looked_at_again_before_the_timer(rig, tmp_path) -> None:
    extra = tmp_path / "more"
    extra.mkdir()
    rig.roots.paths.append(str(extra))
    rig.clock.advance(10)
    rig.watcher.tick()
    assert len(rig.fake.started) == 1


def test_stopping_stops_the_watch(rig) -> None:
    rig.watcher.stop()
    assert rig.fake.stopped == 1
