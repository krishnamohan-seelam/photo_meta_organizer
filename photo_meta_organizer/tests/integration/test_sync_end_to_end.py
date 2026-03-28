"""Integration tests for the full metadata sync pipeline.

These tests exercise the complete flow from disk scan through change detection
to repository updates, using real files on a temporary file system and a real
TinyDB repository.  No mocks — only the image extractor is stubbed to avoid
requiring actual image files with EXIF data.
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
from photo_meta_organizer.infrastructure.repositories.tinydb_repository import TinyDBRepository
from photo_meta_organizer.infrastructure.retriever.local_disk_retriever import LocalDiskRetriever
from photo_meta_organizer.infrastructure.retriever.filtered_retriever import ExtensionFilteredRetriever


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
    """Temp path for TinyDB JSON file."""
    return str(tmp_path / "metadata.db.json")


@pytest.fixture
def repository(db_path) -> TinyDBRepository:
    return TinyDBRepository(db_path=db_path)


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
        result = use_case.execute(index_new=True, reprocess_modified=True, cleanup_deleted=False)

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

        result = use_case.execute(reprocess_modified=False, index_new=False, cleanup_deleted=False)
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
        repo = TinyDBRepository(db_path=db_path)

        uc = SynchronizeMetadataUseCase(retriever=ret, extractor=extractor, repository=repo)
        uc.execute(index_new=True)
        assert repo.count() == 10

        # Delete 1 photo
        (photo_dir / "img0003.jpg").unlink()
        result = uc.execute(cleanup_deleted=True, index_new=False, reprocess_modified=False)

        assert result.deleted_entries == 1
        assert result.unchanged_files == 9
        assert repo.count() == 9

    def test_sync_result_total_changes(self, use_case, repository, photo_dir):
        """total_changes should equal sum of new + modified + deleted."""
        result = use_case.execute(index_new=True)
        assert result.total_changes == result.new_files + result.modified_files + result.deleted_entries
