"""Suggested roots (ADR-003 R11, ticket 09): a few folders to tick, never a silent guess."""

from pathlib import Path

from photo_meta_organizer.application.roots import suggest_roots

BASE = Path(Path.cwd().anchor)  # a drive root on Windows, "/" elsewhere


def _p(*parts: str) -> str:
    return str(BASE.joinpath(*parts))


def test_a_folder_inside_another_is_folded_into_it() -> None:
    found = suggest_roots({_p("photos"): 3, _p("photos", "2020"): 5, _p("photos", "2020", "x"): 1})
    assert [(s.path, s.file_count) for s in found] == [(_p("photos"), 9)]


def test_unrelated_folders_stay_separate() -> None:
    found = suggest_roots({_p("a", "x"): 2, _p("b", "y"): 3})
    assert [s.path for s in found] == [_p("a", "x"), _p("b", "y")]


def test_three_sibling_folders_become_their_parent() -> None:
    found = suggest_roots({_p("lib", "2019"): 1, _p("lib", "2020"): 2, _p("lib", "2021"): 4})
    assert [(s.path, s.file_count) for s in found] == [(_p("lib"), 7)]


def test_two_siblings_stay_as_they_are() -> None:
    found = suggest_roots({_p("lib", "2019"): 1, _p("lib", "2020"): 2})
    assert len(found) == 2


def test_never_suggests_a_drive_or_filesystem_root() -> None:
    found = suggest_roots({_p("a"): 1, _p("b"): 1, _p("c"): 1})
    assert [s.path for s in found] == [_p("a"), _p("b"), _p("c")]


def test_no_files_no_suggestions() -> None:
    assert suggest_roots({}) == []


# ---- scan_roots: the scan every start runs on the library's roots


class _Roots:
    def __init__(self, *paths: str) -> None:
        self._paths = paths

    def list_roots(self):
        from datetime import datetime

        from photo_meta_organizer.application.roots import Root

        return [Root(p, datetime(2026, 10, 25)) for p in self._paths]


def _run(paths, online, make_work=None, jobs=None):
    from photo_meta_organizer.application.jobs import JobManager, JobOutcome
    from photo_meta_organizer.application.roots import scan_roots

    jobs = jobs or JobManager()
    started: list[str] = []

    def default_work(folder, params):
        started.append(folder)
        return lambda ctx: JobOutcome(message="ok")

    ids = scan_roots(_Roots(*paths), jobs, make_work or default_work, online=online)
    for job_id in ids:
        jobs.wait(job_id, timeout=5)
    return ids, started, jobs


def test_every_readable_root_is_scanned_without_removing_anything() -> None:
    ids, started, jobs = _run([_p("a"), _p("b")], online=lambda path: True)
    assert started == [_p("a"), _p("b")] and len(ids) == 2
    assert all(j.kind == "sync" and j.params["remove_missing"] is False for j in jobs.list())


def test_an_offline_root_is_skipped_without_a_job_or_an_error() -> None:
    ids, started, jobs = _run([_p("usb"), _p("home")], online=lambda path: path != _p("usb"))
    assert started == [_p("home")] and len(ids) == 1 and len(jobs.list()) == 1


def test_a_root_that_cannot_start_does_not_stop_the_others() -> None:
    from photo_meta_organizer.application.jobs import JobOutcome

    def make_work(folder, params):
        if folder == _p("bad"):
            raise RuntimeError("no scanner for this root")
        return lambda ctx: JobOutcome(message="ok")

    ids, _, _ = _run([_p("bad"), _p("good")], online=lambda path: True, make_work=make_work)
    assert len(ids) == 1


def test_a_root_already_being_scanned_is_left_to_that_job() -> None:
    import threading

    from photo_meta_organizer.application.jobs import JobManager, JobOutcome

    jobs = JobManager()
    release = threading.Event()
    jobs.submit("sync", _p("a"), lambda ctx: (release.wait(5), JobOutcome())[1])
    try:
        ids, _, _ = _run([_p("a", "inner"), _p("b")], online=lambda path: True, jobs=jobs)
        assert len(ids) == 1  # the nested root conflicts with the running scan of its parent
    finally:
        release.set()
        jobs.shutdown()
