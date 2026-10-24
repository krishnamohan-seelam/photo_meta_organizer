"""ADR-003 R4 (ticket 05): one Scan replaces index and sync."""

import threading
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import BinaryIO

import pytest
from tests.conftest import FakeExtractor

from photo_meta_organizer.application.composition import build_scan
from photo_meta_organizer.application.interfaces.image_retriever import RemoteFileHandle
from photo_meta_organizer.application.use_cases.scan_library import ScanLibrary, ScanOptions
from photo_meta_organizer.domain.models import ImageMetadata
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import SqliteRepository


class RecordingRepository(SqliteRepository):
    """Records which threads write, and how many records each write carries."""

    def __init__(self, db_path: str) -> None:
        super().__init__(db_path)
        self.writer_threads: set[int] = set()
        self.batch_sizes: list[int] = []

    def save_many(self, items: Sequence[ImageMetadata]) -> None:
        self.writer_threads.add(threading.get_ident())
        self.batch_sizes.append(len(items))
        super().save_many(items)


class FlakyExtractor(FakeExtractor):
    """Fails on files whose name starts with ``bad``."""

    def extract(self, file_handle: RemoteFileHandle, stream: BinaryIO) -> ImageMetadata:
        if file_handle.filename.startswith("bad"):
            raise RuntimeError("corrupt EXIF")
        return super().extract(file_handle, stream)


@pytest.fixture
def photos(tmp_path: Path) -> Path:
    root = tmp_path / "photos"
    root.mkdir()
    for i in range(30):
        (root / f"p{i:02d}.jpg").write_bytes(f"photo {i}".encode())
    return root


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[RecordingRepository]:
    repository = RecordingRepository(str(tmp_path / "photos.db"))
    yield repository
    repository.close()


def _scan_of(
    root: Path, repo: SqliteRepository, extractor: FakeExtractor | None = None
) -> ScanLibrary:
    from photo_meta_organizer.infrastructure.retriever.filtered_retriever import (
        ExtensionFilteredRetriever,
    )
    from photo_meta_organizer.infrastructure.retriever.local_disk_retriever import (
        LocalDiskRetriever,
    )

    retriever = ExtensionFilteredRetriever(LocalDiskRetriever(str(root)), {".jpg"})
    return ScanLibrary(retriever, extractor or FakeExtractor(), repo)


def test_new_files_are_extracted_in_parallel_and_written_by_one_thread_in_batches(
    photos: Path, repo: RecordingRepository
) -> None:
    result = _scan_of(photos, repo).execute(ScanOptions(workers=4), scope_root=str(photos))

    assert (result.new_files, result.errors) == (30, [])
    assert repo.count() == 30
    assert len(repo.writer_threads) == 1
    assert threading.get_ident() not in repo.writer_threads
    assert max(repo.batch_sizes) > 1  # batched, not one write per file
    assert sum(repo.batch_sizes) == 30


def test_one_worker_and_many_workers_build_the_same_library(photos: Path, tmp_path: Path) -> None:
    libraries = []
    for workers in (1, 6):
        repository = SqliteRepository(str(tmp_path / f"w{workers}.db"))
        _scan_of(photos, repository).execute(ScanOptions(workers=workers))
        libraries.append(sorted((f.path, f.file_hash) for f in repository.list_files()))
        repository.close()

    assert libraries[0] == libraries[1]


def test_a_second_scan_only_reads_what_changed(photos: Path, repo: RecordingRepository) -> None:
    scan = _scan_of(photos, repo)
    scan.execute(ScanOptions())
    (photos / "p00.jpg").write_bytes(b"edited, and longer than before")
    (photos / "new.jpg").write_bytes(b"new")

    result = scan.execute(ScanOptions())

    assert (result.new_files, result.modified_files, result.unchanged_files) == (1, 1, 29)


def test_a_file_that_fails_to_extract_is_reported_and_the_rest_are_saved(
    photos: Path, repo: RecordingRepository
) -> None:
    (photos / "bad.jpg").write_bytes(b"broken")

    result = _scan_of(photos, repo, FlakyExtractor()).execute(ScanOptions(workers=3))

    assert result.new_files == 30
    assert len(result.errors) == 1
    assert "bad.jpg" in result.errors[0] and "corrupt EXIF" in result.errors[0]


def test_a_failed_write_is_reported_per_file(photos: Path, tmp_path: Path) -> None:
    class RefusingRepository(SqliteRepository):
        def save_many(self, items: Sequence[ImageMetadata]) -> None:
            for item in items:
                self.save(item)

        def save(self, metadata: ImageMetadata, *, overwrite_curation: bool = False) -> None:
            if metadata.file_info.name == "p07.jpg":
                raise OSError("disk full")
            super().save(metadata, overwrite_curation=overwrite_curation)

    repository = RefusingRepository(str(tmp_path / "refusing.db"))
    result = _scan_of(photos, repository).execute(ScanOptions(workers=2))

    assert result.new_files == 29
    assert len(result.errors) == 1 and "p07.jpg" in result.errors[0]
    assert repository.count() == 29
    repository.close()


def test_progress_reaches_the_total(photos: Path, repo: RecordingRepository) -> None:
    seen: list[tuple[int, int]] = []

    _scan_of(photos, repo).execute(
        ScanOptions(workers=4), progress=lambda done, total: seen.append((done, total))
    )

    assert seen[-1] == (30, 30)
    assert [done for done, _ in seen] == sorted(done for done, _ in seen)


def test_cancelling_stops_extracting_and_keeps_what_was_done(
    photos: Path, repo: RecordingRepository
) -> None:
    calls: list[int] = []

    def cancel_after_a_few() -> bool:
        calls.append(1)
        return len(calls) > 6

    result = _scan_of(photos, repo).execute(
        ScanOptions(workers=2), should_cancel=cancel_after_a_few
    )

    assert result.cancelled is True
    assert 0 < result.new_files < 30
    assert repo.count() == result.new_files


def test_dry_run_reads_nothing_and_writes_nothing(photos: Path, repo: RecordingRepository) -> None:
    result = _scan_of(photos, repo).execute(ScanOptions(dry_run=True))

    assert result.new_files == 30
    assert repo.count() == 0
    assert repo.batch_sizes == []


def test_the_composition_root_builds_a_scan_of_a_folder(
    photos: Path, repo: RecordingRepository
) -> None:
    (photos / "notes.txt").write_text("not a photo")
    (photos / "a.png").write_bytes(b"\x89PNG\r\n\x1a\nnot really")

    scan = build_scan(str(photos), repo)

    assert isinstance(scan, ScanLibrary)
    result = scan.execute(ScanOptions(dry_run=True), scope_root=str(photos))
    assert result.new_files == 31  # images only: the .txt is not listed


def test_a_moved_file_keeps_its_curation_when_missing_files_are_removed(
    photos: Path, repo: RecordingRepository
) -> None:
    from photo_meta_organizer.domain.curation import SetRating

    scan = _scan_of(photos, repo)
    scan.execute(ScanOptions())
    moved = repo.find_by_paths([str(photos / "p03.jpg")])[0]
    repo.apply(moved.file_hash, SetRating(5))
    (photos / "sub").mkdir()
    (photos / "p03.jpg").rename(photos / "sub" / "p03.jpg")

    result = scan.execute(ScanOptions(remove_missing=True))

    assert (result.new_files, result.deleted_entries) == (1, 1)
    photo = repo.get_by_filehash(moved.file_hash)
    assert photo is not None and photo.rating == 5
    assert photo.file_info.path == str(photos / "sub" / "p03.jpg")


def test_a_failing_progress_callback_does_not_hang_the_scan(
    photos: Path, repo: RecordingRepository
) -> None:
    def explode(done: int, total: int) -> None:
        if done > 5:
            raise RuntimeError("UI went away")

    result = _scan_of(photos, repo).execute(ScanOptions(workers=4), progress=explode)

    assert result.new_files == 30
    assert repo.count() == 30


def test_an_extractor_that_returns_nothing_is_reported(
    photos: Path, repo: RecordingRepository
) -> None:
    class Silent(FakeExtractor):
        def extract(self, file_handle: RemoteFileHandle, stream: BinaryIO) -> ImageMetadata:
            if file_handle.filename == "p01.jpg":
                return None  # type: ignore[return-value]
            return super().extract(file_handle, stream)

    result = _scan_of(photos, repo, Silent()).execute(ScanOptions())

    assert result.new_files == 29
    assert result.errors == [f"no metadata extracted: {photos / 'p01.jpg'}"]
