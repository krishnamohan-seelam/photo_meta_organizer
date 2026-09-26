"""Integration tests for the full metadata sync pipeline.

These tests exercise the complete flow from disk scan through change detection
to repository updates, using real files on a temporary file system and a real
SQLite repository (ADR-001).  No mocks — only the image extractor is stubbed to
avoid requiring actual image files with EXIF data.
"""

import shutil
from contextlib import contextmanager
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Generator
from unittest.mock import MagicMock

import pytest

from photo_meta_organizer.application.interfaces.image_retriever import RemoteFileHandle
from photo_meta_organizer.application.use_cases import SynchronizeMetadataUseCase
from photo_meta_organizer.domain.models import (
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.domain.services import MetadataStateAnalyzer
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import (
    SqliteRepository,
)
from photo_meta_organizer.infrastructure.retriever.local_disk_retriever import (
    LocalDiskRetriever,
)
from photo_meta_organizer.infrastructure.retriever.filtered_retriever import (
    ExtensionFilteredRetriever,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


class FakeExtractor:
    """Stub extractor: produces predictable metadata from the file handle."""

    def extract(self, file_handle: RemoteFileHandle, stream: BinaryIO) -> ImageMetadata:
        content = stream.read()
        import hashlib

        h = hashlib.sha256(content).hexdigest()
        return ImageMetadata(
            file_hash=h,
            file_info=ImageFileInfo(
                name=file_handle.filename,
                path=file_handle.original_path,
                size_bytes=file_handle.size_bytes,
                mime_type="image/jpeg",
            ),
            dimensions=ImageDimensions(width=100, height=100),
            exif=ImageExifData(),
        )

    @contextmanager
    def get_file_stream(self, file_handle):
        """Not a retriever method – extractor doesn't need this."""
        yield BytesIO(b"")


@pytest.fixture
def photo_dir(tmp_path) -> Path:
    """Create a temporary photo directory with a few test images."""
    d = tmp_path / "photos"
    d.mkdir()
    (d / "photo1.jpg").write_bytes(b"photo1_content")
    (d / "photo2.jpg").write_bytes(b"photo2_content")
    (d / "photo3.jpg").write_bytes(b"photo3_content")
    return d


@pytest.fixture
def db_path(tmp_path) -> str:
    """Temp path for the SQLite database file."""
    return str(tmp_path / "metadata.db")


@pytest.fixture
def repository(db_path) -> SqliteRepository:
    return SqliteRepository(db_path=db_path)


@pytest.fixture
def retriever(photo_dir):
    base = LocalDiskRetriever(base_path=str(photo_dir))
    return ExtensionFilteredRetriever(base, IMAGE_EXTENSIONS)


@pytest.fixture
def extractor():
    return FakeExtractor()


@pytest.fixture
def use_case(retriever, extractor, repository):
    return SynchronizeMetadataUseCase(
        retriever=retriever,
        extractor=extractor,
        repository=repository,
    )


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSyncIntegration:
    """End-to-end sync scenarios using real files and repository."""

    def test_initial_sync_indexes_all_new_files(self, use_case, repository):
        """First sync on an empty DB should index all photos."""
        result = use_case.execute(
            index_new=True, reprocess_modified=True, cleanup_deleted=False
        )

        assert result.new_files == 3
        assert result.modified_files == 0
        assert result.deleted_entries == 0
        assert result.unchanged_files == 0
        assert len(result.errors) == 0
        assert repository.count() == 3

    def test_second_sync_unchanged_skips_all(self, use_case, repository):
        """Second sync should find all files UNCHANGED and skip hashing."""
        use_case.execute(index_new=True)
        result = use_case.execute(index_new=True)

        assert result.unchanged_files == 3
        assert result.new_files == 0
        assert result.modified_files == 0

    def test_new_file_detected_after_first_sync(self, use_case, repository, photo_dir):
        """Adding a new file after initial sync should be detected on next sync."""
        use_case.execute(index_new=True)

        # Add a new file
        (photo_dir / "new_arrival.jpg").write_bytes(b"brand_new")
        result = use_case.execute(index_new=True)

        assert result.new_files == 1
        assert result.unchanged_files == 3

    def test_deleted_file_cleaned_up(self, use_case, repository, photo_dir):
        """Deleted files should be removed from DB when cleanup_deleted=True."""
        use_case.execute(index_new=True)
        assert repository.count() == 3

        (photo_dir / "photo1.jpg").unlink()
        result = use_case.execute(cleanup_deleted=True, index_new=False)

        assert result.deleted_entries == 1
        assert repository.count() == 2

    def test_deleted_file_kept_when_no_cleanup(self, use_case, repository, photo_dir):
        """Without --cleanup-deleted, orphaned entries stay in DB."""
        use_case.execute(index_new=True)
        (photo_dir / "photo1.jpg").unlink()

        result = use_case.execute(cleanup_deleted=False, index_new=False)
        assert result.deleted_entries == 0
        assert repository.count() == 3  # Orphaned entry still present

    def test_modified_file_reprocessed(self, use_case, repository, photo_dir):
        """Modified file (different size → different hash) should be re-extracted."""
        use_case.execute(index_new=True)

        # Overwrite with different content
        (photo_dir / "photo2.jpg").write_bytes(b"completely_different_content_here")
        result = use_case.execute(reprocess_modified=True)

        assert result.modified_files == 1
        assert result.unchanged_files == 2

    def test_modified_file_skipped_when_flag_off(self, use_case, repository, photo_dir):
        """Modified files are not reprocessed when reprocess_modified=False."""
        use_case.execute(index_new=True)
        (photo_dir / "photo2.jpg").write_bytes(b"different_content_here")

        result = use_case.execute(
            reprocess_modified=False, index_new=False, cleanup_deleted=False
        )
        assert result.modified_files == 0

    def test_dry_run_does_not_change_repository(self, use_case, repository):
        """Dry run should report what would happen without touching the DB."""
        result = use_case.execute(index_new=True, dry_run=True)

        assert result.new_files == 3
        assert repository.count() == 0  # Nothing actually written

    def test_large_batch_mostly_unchanged_one_deleted(
        self, retriever, extractor, db_path, tmp_path
    ):
        """Realistic scenario: 10 photos, 9 unchanged, 1 deleted → only 1 deleted."""
        photo_dir = tmp_path / "large_batch"
        photo_dir.mkdir()
        for i in range(10):
            (photo_dir / f"img{i:04d}.jpg").write_bytes(f"photo{i}".encode())

        base = LocalDiskRetriever(base_path=str(photo_dir))
        ret = ExtensionFilteredRetriever(base, IMAGE_EXTENSIONS)
        repo = SqliteRepository(db_path=db_path)

        uc = SynchronizeMetadataUseCase(
            retriever=ret, extractor=extractor, repository=repo
        )
        uc.execute(index_new=True)
        assert repo.count() == 10

        # Delete 1 photo
        (photo_dir / "img0003.jpg").unlink()
        result = uc.execute(
            cleanup_deleted=True, index_new=False, reprocess_modified=False
        )

        assert result.deleted_entries == 1
        assert result.unchanged_files == 9
        assert repo.count() == 9

    def test_sync_result_total_changes(self, use_case, repository, photo_dir):
        """total_changes should equal sum of new + modified + deleted."""
        result = use_case.execute(index_new=True)
        assert (
            result.total_changes
            == result.new_files + result.modified_files + result.deleted_entries
        )


# ---------------------------------------------------------------------------
# PMO-05: MODIFIED replaces the old record and keeps the user's curation (B-01)
# ---------------------------------------------------------------------------


def _bump_mtime(path: Path, seconds: float = 60.0) -> None:
    """Move a file's mtime without touching its bytes."""
    import os

    st = path.stat()
    os.utime(path, (st.st_atime + seconds, st.st_mtime + seconds))


def _sha(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


class CountingExtractor(FakeExtractor):
    def __init__(self) -> None:
        self.extracted: list[str] = []

    def extract(self, file_handle, stream):
        self.extracted.append(file_handle.filename)
        return super().extract(file_handle, stream)


@pytest.mark.integration
class TestSyncReplacesModifiedRecord:
    def _curate(self, repository, photo_dir, name="photo2.jpg"):
        record = repository.get_by_path(str((photo_dir / name).resolve()))
        assert record is not None
        repository.update_metadata(
            record.file_hash,
            {"rating": 5, "flagged": True, "labels": ["keeper", "trip"]},
        )
        return record.file_hash

    def test_edit_that_changes_content_and_size_leaves_one_record(
        self, use_case, repository, photo_dir
    ):
        use_case.execute()
        old_hash = self._curate(repository, photo_dir)

        (photo_dir / "photo2.jpg").write_bytes(b"completely_different_content_here")
        result = use_case.execute()

        assert result.modified_files == 1
        assert repository.count() == 3  # not 4: the old record is gone
        assert repository.get_by_filehash(old_hash) is None
        assert (
            sum(1 for r in repository.list_all() if r.file_info.name == "photo2.jpg")
            == 1
        )

    def test_rating_flag_and_labels_survive_the_edit(
        self, use_case, repository, photo_dir
    ):
        use_case.execute()
        self._curate(repository, photo_dir)

        (photo_dir / "photo2.jpg").write_bytes(b"completely_different_content_here")
        use_case.execute()

        edited = repository.get_by_filehash(_sha(b"completely_different_content_here"))
        assert (edited.rating, edited.flagged, edited.labels) == (
            5,
            True,
            ["keeper", "trip"],
        )

    def test_edit_that_makes_it_identical_to_another_photo_keeps_both_curations(
        self, use_case, repository, photo_dir
    ):
        use_case.execute()
        self._curate(repository, photo_dir, "photo2.jpg")
        other = repository.get_by_filehash(_sha(b"photo3_content"))
        repository.update_metadata(other.file_hash, {"add_tags": ["from-photo3"]})

        (photo_dir / "photo2.jpg").write_bytes(b"photo3_content")
        use_case.execute()

        assert repository.count() == 2
        merged = repository.get_by_filehash(_sha(b"photo3_content"))
        assert merged.rating == 5
        assert set(merged.labels) == {"keeper", "trip", "from-photo3"}

    def test_new_copy_of_a_curated_photo_does_not_reset_its_curation(
        self, use_case, repository, photo_dir
    ):
        use_case.execute()
        self._curate(repository, photo_dir, "photo1.jpg")

        (photo_dir / "photo1_copy.jpg").write_bytes(b"photo1_content")
        use_case.execute()

        assert repository.get_by_filehash(_sha(b"photo1_content")).rating == 5


# ---------------------------------------------------------------------------
# PMO-06: (size, mtime) fingerprint, backfill and --rehash (B-02)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSyncMtimeFingerprint:
    def _use_case(self, retriever, repository, extractor=None):
        extractor = extractor or CountingExtractor()
        return (
            SynchronizeMetadataUseCase(
                retriever=retriever, extractor=extractor, repository=repository
            ),
            extractor,
        )

    def test_same_size_edit_is_detected_once_the_mtime_moves(
        self, retriever, repository, photo_dir
    ):
        uc, extractor = self._use_case(retriever, repository)
        uc.execute()
        target = photo_dir / "photo1.jpg"
        edited = b"X" * len(target.read_bytes())  # same size, different bytes
        target.write_bytes(edited)
        _bump_mtime(target)

        result = uc.execute()

        assert result.modified_files == 1
        assert repository.get_by_filehash(_sha(edited)) is not None
        assert repository.count() == 3

    def test_unchanged_files_are_not_rehashed_or_reextracted(
        self, retriever, repository, photo_dir
    ):
        uc, extractor = self._use_case(retriever, repository)
        uc.execute()
        extractor.extracted.clear()

        result = uc.execute()

        assert result.unchanged_files == 3
        assert result.fingerprints_refreshed == 0
        assert extractor.extracted == []

    def test_touch_records_the_new_mtime_without_reextracting(
        self, retriever, repository, photo_dir
    ):
        uc, extractor = self._use_case(retriever, repository)
        uc.execute()
        extractor.extracted.clear()
        target = photo_dir / "photo1.jpg"
        _bump_mtime(target)

        first = uc.execute()
        second = uc.execute()

        assert first.unchanged_files == 3 and first.modified_files == 0
        assert first.fingerprints_refreshed == 1
        assert extractor.extracted == []
        assert second.fingerprints_refreshed == 0  # caught up

    def test_legacy_records_are_backfilled_not_rehashed(
        self, retriever, repository, photo_dir
    ):
        uc, extractor = self._use_case(retriever, repository)
        uc.execute()
        with repository.lock, repository.connection:  # simulate a pre-PMO-06 database
            repository.connection.execute("UPDATE photos SET mtime = NULL")
        extractor.extracted.clear()

        first = uc.execute()
        second = uc.execute()

        assert first.unchanged_files == 3 and first.modified_files == 0
        assert first.fingerprints_refreshed == 3
        assert extractor.extracted == []
        assert second.fingerprints_refreshed == 0
        assert all(r.file_info.modified_time is not None for r in repository.list_all())

    def test_dry_run_reports_the_backfill_but_writes_nothing(
        self, retriever, repository, photo_dir
    ):
        uc, _ = self._use_case(retriever, repository)
        uc.execute()
        with repository.lock, repository.connection:
            repository.connection.execute("UPDATE photos SET mtime = NULL")

        result = uc.execute(dry_run=True)

        assert result.fingerprints_refreshed == 3
        assert all(r.file_info.modified_time is None for r in repository.list_all())

    def test_rehash_catches_an_edit_that_kept_size_and_mtime(
        self, retriever, repository, photo_dir
    ):
        import os

        uc, _ = self._use_case(retriever, repository)
        uc.execute()
        target = photo_dir / "photo1.jpg"
        stat = target.stat()
        edited = b"Y" * len(target.read_bytes())
        target.write_bytes(edited)
        os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))  # forge the old mtime

        assert uc.execute().modified_files == 0  # the cheap check cannot see it
        result = uc.execute(rehash=True)

        assert result.modified_files == 1
        assert repository.get_by_filehash(_sha(edited)) is not None


# ---------------------------------------------------------------------------
# PMO-19: sync is scoped to its root; progress and cancel for the job API
# ---------------------------------------------------------------------------


def _use_case(root: Path, repo: SqliteRepository) -> SynchronizeMetadataUseCase:
    retriever = ExtensionFilteredRetriever(LocalDiskRetriever(str(root)), IMAGE_EXTENSIONS)
    return SynchronizeMetadataUseCase(retriever, FakeExtractor(), repo)


class TestSyncScope:
    def test_cleanup_of_one_folder_keeps_records_from_another(self, tmp_path) -> None:
        a, b = tmp_path / "a", tmp_path / "b"
        a.mkdir()
        b.mkdir()
        (a / "a1.jpg").write_bytes(b"a1")
        (b / "b1.jpg").write_bytes(b"b1")
        repo = SqliteRepository(":memory:")
        _use_case(a, repo).execute(scope_root=str(a))
        _use_case(b, repo).execute(scope_root=str(b))
        assert repo.count() == 2

        (a / "a1.jpg").unlink()
        result = _use_case(a, repo).execute(cleanup_deleted=True, scope_root=str(a))

        assert result.deleted_entries == 1
        assert [m.file_info.name for m in repo.list_all()] == ["b1.jpg"]

    def test_sibling_with_common_name_prefix_is_out_of_scope(self, tmp_path) -> None:
        a, ab = tmp_path / "a", tmp_path / "ab"
        a.mkdir()
        ab.mkdir()
        (ab / "x.jpg").write_bytes(b"x")
        repo = SqliteRepository(":memory:")
        _use_case(ab, repo).execute(scope_root=str(ab))

        result = _use_case(a, repo).execute(cleanup_deleted=True, scope_root=str(a))
        assert result.deleted_entries == 0
        assert repo.count() == 1

    def test_progress_and_cancel(self, tmp_path) -> None:
        root = tmp_path / "many"
        root.mkdir()
        for i in range(20):
            (root / f"p{i}.jpg").write_bytes(f"content {i}".encode())
        repo = SqliteRepository(":memory:")

        seen: list[tuple[int, int]] = []
        result = _use_case(root, repo).execute(
            scope_root=str(root), progress=lambda done, total: seen.append((done, total))
        )
        assert result.new_files == 20 and not result.cancelled
        assert seen[-1] == (20, 20)

        for i in range(20, 40):
            (root / f"p{i}.jpg").write_bytes(f"content {i}".encode())
        calls = []

        def cancel_after_five() -> bool:
            calls.append(1)
            return len(calls) > 5

        result = _use_case(root, repo).execute(
            scope_root=str(root), should_cancel=cancel_after_five
        )
        assert result.cancelled is True
        assert 0 < result.new_files < 20
        assert repo.count() == 20 + result.new_files
