"""Unit tests for SynchronizeMetadataUseCase.

Tests orchestration logic: correct dispatch of sync flags, dry-run mode,
error accumulation, and SyncResult population.  All I/O is mocked.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch, call

import pytest

from photo_meta_organizer.domain.models import (
    FileInfo,
    FileState,
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
    SyncResult,
)
from photo_meta_organizer.application.use_cases import SynchronizeMetadataUseCase
from photo_meta_organizer.domain.services import MetadataStateAnalyzer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HASH_A = "a" * 64
HASH_B = "b" * 64


def _make_metadata(path: str, file_hash: str, size_bytes: int = 100) -> ImageMetadata:
    return ImageMetadata(
        file_hash=file_hash,
        file_info=ImageFileInfo(
            name=path.split("/")[-1],
            path=path,
            size_bytes=size_bytes,
            mime_type="image/jpeg",
        ),
        dimensions=ImageDimensions(width=100, height=100),
        exif=ImageExifData(),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_retriever():
    return MagicMock()


@pytest.fixture
def mock_extractor():
    return MagicMock()


@pytest.fixture
def mock_repository():
    repo = MagicMock()
    repo.list_all.return_value = []
    repo.delete_by_path.return_value = True
    repo.delete.return_value = True
    return repo


@pytest.fixture
def mock_analyzer():
    return MagicMock(spec=MetadataStateAnalyzer)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSynchronizeMetadataUseCaseFlags:
    """Test that flags correctly control which actions are performed."""

    def _make_use_case(self, retriever, extractor, repository, analyzer):
        return SynchronizeMetadataUseCase(
            retriever=retriever,
            extractor=extractor,
            repository=repository,
            analyzer=analyzer,
        )

    def test_dry_run_does_not_write(self, mock_retriever, mock_extractor, mock_repository, mock_analyzer, tmp_path):
        """In dry_run mode, no save/delete should be called on the repository."""
        mock_retriever.list_files.return_value = iter([])
        mock_analyzer.analyze_changes.return_value = [
            FileState(file_path="/a.jpg", state="NEW", file_hash=HASH_A, size_bytes=100),
            FileState(file_path="/b.jpg", state="DELETED", file_hash=HASH_B),
        ]

        use_case = self._make_use_case(mock_retriever, mock_extractor, mock_repository, mock_analyzer)
        result = use_case.execute(
            cleanup_deleted=True, reprocess_modified=True, index_new=True, dry_run=True
        )

        mock_repository.save.assert_not_called()
        mock_repository.delete.assert_not_called()
        mock_repository.delete_by_path.assert_not_called()

        # Dry-run should still report counts
        assert result.new_files == 1
        assert result.deleted_entries == 1

    def test_returns_sync_result_type(self, mock_retriever, mock_extractor, mock_repository, mock_analyzer):
        mock_retriever.list_files.return_value = iter([])
        mock_analyzer.analyze_changes.return_value = []

        use_case = self._make_use_case(mock_retriever, mock_extractor, mock_repository, mock_analyzer)
        result = use_case.execute()
        assert isinstance(result, SyncResult)

    def test_duration_seconds_set(self, mock_retriever, mock_extractor, mock_repository, mock_analyzer):
        mock_retriever.list_files.return_value = iter([])
        mock_analyzer.analyze_changes.return_value = []

        use_case = self._make_use_case(mock_retriever, mock_extractor, mock_repository, mock_analyzer)
        result = use_case.execute()
        assert result.duration_seconds >= 0.0

    def test_stat_error_adds_to_errors(self, mock_extractor, mock_repository, mock_analyzer):
        """Files that cannot be stat'd are logged as errors."""
        from photo_meta_organizer.application.interfaces.image_retriever import RemoteFileHandle

        handle = RemoteFileHandle(
            original_path="/nonexistent/photo.jpg",
            filename="photo.jpg",
            size_bytes=0,
        )
        real_retriever = MagicMock()
        real_retriever.list_files.return_value = iter([handle])
        mock_analyzer.analyze_changes.return_value = []

        use_case = SynchronizeMetadataUseCase(
            retriever=real_retriever,
            extractor=mock_extractor,
            repository=mock_repository,
            analyzer=mock_analyzer,
        )
        result = use_case.execute()
        assert any("stat error" in e for e in result.errors)

    def test_unchanged_count_populated(self, mock_retriever, mock_extractor, mock_repository, mock_analyzer):
        mock_retriever.list_files.return_value = iter([])
        mock_analyzer.analyze_changes.return_value = [
            FileState(file_path="/a.jpg", state="UNCHANGED", file_hash=HASH_A, size_bytes=100),
            FileState(file_path="/b.jpg", state="UNCHANGED", file_hash=HASH_B, size_bytes=200),
        ]

        use_case = self._make_use_case(mock_retriever, mock_extractor, mock_repository, mock_analyzer)
        result = use_case.execute()
        assert result.unchanged_files == 2


class TestSyncResult:
    """Tests for the SyncResult domain model."""

    def test_total_changes_sums_new_modified_deleted(self):
        result = SyncResult(new_files=3, modified_files=2, deleted_entries=1, unchanged_files=10)
        assert result.total_changes == 6

    def test_total_changes_zero_when_nothing_changed(self):
        result = SyncResult()
        assert result.total_changes == 0

    def test_errors_default_empty(self):
        result = SyncResult()
        assert result.errors == []

    def test_duration_default_zero(self):
        result = SyncResult()
        assert result.duration_seconds == 0.0
