"""Ticket 04: a File that disappears is flagged missing, not forgotten."""

import hashlib
import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from tests.conftest import FakeExtractor

from photo_meta_organizer.application.use_cases import (
    RootUnavailableError,
    ScanLibrary,
    ScanOptions,
)
from photo_meta_organizer.domain.analysis import AiTag, Embedding
from photo_meta_organizer.domain.curation import AddTag, SetRating
from photo_meta_organizer.domain.models import SyncResult
from photo_meta_organizer.infrastructure.repositories.sqlite_analysis_repository import (
    SqliteAnalysisRepository,
)
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import SqliteRepository
from photo_meta_organizer.infrastructure.retriever.filtered_retriever import (
    ExtensionFilteredRetriever,
)
from photo_meta_organizer.infrastructure.retriever.local_disk_retriever import (
    LocalDiskRetriever,
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


Library = tuple[Path, SqliteRepository]


def _scan(root: Path, repo: SqliteRepository, **options: bool) -> SyncResult:
    retriever = ExtensionFilteredRetriever(LocalDiskRetriever(str(root)), IMAGE_EXTENSIONS)
    use_case = ScanLibrary(retriever, FakeExtractor(), repo)
    return use_case.execute(ScanOptions(**options), scope_root=str(root))


@pytest.fixture
def library(tmp_path: Path) -> Iterator[Library]:
    root = tmp_path / "photos"
    (root / "trip").mkdir(parents=True)
    (root / "trip" / "beach.jpg").write_bytes(b"beach")
    (root / "home.jpg").write_bytes(b"home")
    repo = SqliteRepository(str(tmp_path / "photos.db"))
    _scan(root, repo)
    yield root, repo
    repo.close()


def test_a_file_not_found_is_flagged_missing_and_kept(library: Library) -> None:
    root, repo = library
    (root / "home.jpg").unlink()

    result = _scan(root, repo)

    assert result.missing_files == 1
    assert repo.count() == 2
    home = repo.get_by_filehash(_sha(b"home"))
    assert home is not None
    assert home.file_info.missing_since is not None
    assert repo.get_by_filehash(_sha(b"beach")).file_info.missing_since is None


def test_the_flag_is_cleared_when_the_path_reappears(library: Library) -> None:
    root, repo = library
    (root / "home.jpg").rename(root.parent / "away.jpg")
    _scan(root, repo)
    (root.parent / "away.jpg").rename(root / "home.jpg")

    result = _scan(root, repo)

    assert result.found_again == 1
    assert repo.get_by_filehash(_sha(b"home")).file_info.missing_since is None


def test_a_rescan_keeps_the_time_the_file_first_went_missing(library: Library) -> None:
    root, repo = library
    (root / "home.jpg").unlink()
    _scan(root, repo)
    first = repo.get_by_filehash(_sha(b"home")).file_info.missing_since

    _scan(root, repo)

    assert repo.get_by_filehash(_sha(b"home")).file_info.missing_since == first


def test_moving_a_folder_out_and_back_loses_nothing(library: Library, tmp_path: Path) -> None:
    root, repo = library
    beach = _sha(b"beach")
    repo.apply(beach, SetRating(5))
    repo.apply(beach, AddTag("summer"))

    shutil.move(str(root / "trip"), str(tmp_path / "trip"))
    _scan(root, repo)
    shutil.move(str(tmp_path / "trip"), str(root / "trip"))
    result = _scan(root, repo)

    assert (result.new_files, result.modified_files) == (0, 0)
    photo = repo.get_by_filehash(beach)
    assert (photo.rating, photo.labels, photo.file_info.missing_since) == (5, ["summer"], None)
    assert repo.count() == 2


def test_dry_run_counts_missing_files_without_flagging_them(library: Library) -> None:
    root, repo = library
    (root / "home.jpg").unlink()

    result = _scan(root, repo, dry_run=True)

    assert result.missing_files == 1
    assert repo.get_by_filehash(_sha(b"home")).file_info.missing_since is None


def test_remove_missing_forgets_the_file_and_its_orphaned_photo(library: Library) -> None:
    root, repo = library
    (root / "home.jpg").unlink()

    analysis = SqliteAnalysisRepository(repo.connection, repo.lock)
    analysis.save_embeddings([Embedding(file_hash=_sha(b"home"), model_id="m", vector=(1.0, 0.0))])
    analysis.save_ai_tags(_sha(b"home"), [AiTag("kitchen", 0.5, "m")])

    result = _scan(root, repo, remove_missing=True)

    assert (result.deleted_entries, result.missing_files) == (1, 0)
    assert repo.get_by_filehash(_sha(b"home")) is None
    assert repo.count() == 1
    assert analysis.count_embeddings("m") == 0
    assert analysis.list_ai_tags(_sha(b"home")) == []


def test_a_photo_with_a_present_copy_is_not_missing(library: Library) -> None:
    root, repo = library
    (root / "copy-of-home.jpg").write_bytes(b"home")
    _scan(root, repo)
    (root / "home.jpg").unlink()

    _scan(root, repo)

    home = repo.get_by_filehash(_sha(b"home"))
    assert home.file_info.path.endswith("copy-of-home.jpg")  # the present file is primary
    assert home.file_info.missing_since is None


def test_an_unavailable_root_fails_and_changes_nothing(library: Library, tmp_path: Path) -> None:
    root, repo = library
    retriever = ExtensionFilteredRetriever(LocalDiskRetriever(str(root)), IMAGE_EXTENSIONS)
    use_case = ScanLibrary(retriever, FakeExtractor(), repo)
    root.rename(tmp_path / "unplugged")  # the drive went away after the scan was set up

    with pytest.raises(RootUnavailableError):
        use_case.execute(ScanOptions(remove_missing=True), scope_root=str(root))

    assert repo.count() == 2
    assert all(f.missing_since is None for f in repo.list_files())


def test_the_api_reports_when_a_photos_file_is_missing(library: Library, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from photo_meta_organizer.api.app import create_app

    root, repo = library
    (root / "home.jpg").unlink()
    _scan(root, repo)

    client = TestClient(create_app(db_path=str(tmp_path / "photos.db")))
    home = client.get(f"/api/photos/{_sha(b'home')}").json()
    beach = client.get(f"/api/photos/{_sha(b'beach')}").json()

    assert home["file_info"]["missing_since"] is not None
    assert beach["file_info"]["missing_since"] is None


def _unreadable(monkeypatch: pytest.MonkeyPatch, folder: Path) -> None:
    real_scandir = os.scandir

    def scandir(path: object = ".") -> object:
        if os.path.normcase(os.fspath(path)) == os.path.normcase(str(folder)):  # type: ignore[arg-type]
            raise PermissionError(13, "Access is denied", str(folder))
        return real_scandir(path)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "scandir", scandir)


def test_files_in_a_folder_the_scan_could_not_read_are_left_alone(
    library: Library, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, repo = library
    _unreadable(monkeypatch, root / "trip")

    result = _scan(root, repo, remove_missing=True)

    assert (result.deleted_entries, result.missing_files) == (0, 0)
    beach = repo.get_by_filehash(_sha(b"beach"))
    assert beach is not None and beach.file_info.missing_since is None


def test_a_modified_file_found_again_is_no_longer_missing_even_unprocessed(
    library: Library,
) -> None:
    root, repo = library
    (root / "home.jpg").rename(root.parent / "away.jpg")
    _scan(root, repo)
    (root.parent / "away.jpg").rename(root / "home.jpg")
    (root / "home.jpg").write_bytes(b"home, edited while away")

    result = _scan(root, repo, reprocess_modified=False)

    assert result.found_again == 1
    assert all(f.missing_since is None for f in repo.list_files())
