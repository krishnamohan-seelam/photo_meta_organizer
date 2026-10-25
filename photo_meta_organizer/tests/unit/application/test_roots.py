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
