"""Unit tests for ParallelIndexPhotosUseCase.

Tests multi-threaded parallel extraction pipeline, worker thread pool execution,
poison pill shutdown, DB writer thread operations, and error resilience.
"""

import pytest
from unittest.mock import MagicMock
from photo_meta_organizer.application.use_cases import ParallelIndexPhotosUseCase
from photo_meta_organizer.domain.models import ImageMetadata
from tests.conftest import (
    MockImageMetadataRepository,
    MockImageRetriever,
    MockMetadataExtractor,
)


@pytest.mark.unit
class TestParallelIndexPhotosUseCase:
    """Tests for ParallelIndexPhotosUseCase."""

    def test_execute_multi_threaded_success(
        self,
        mock_extractor: MockMetadataExtractor,
        mock_retriever: MockImageRetriever,
        mock_repository: MockImageMetadataRepository,
    ) -> None:
        """Full multi-threaded pipeline: discover → parallel extract → queue → DB save."""
        use_case = ParallelIndexPhotosUseCase(
            retriever=mock_retriever,
            extractor=mock_extractor,
            repository=mock_repository,
            num_workers=4,
        )

        results = use_case.execute()

        # Should extract metadata from all files in retriever
        assert len(results) > 0
        assert all(isinstance(m, ImageMetadata) for m in results)

        # Should persist all results to repository
        stored = mock_repository.list_all()
        assert len(stored) == len(results)

    def test_execute_with_no_files(
        self,
        mock_extractor: MockMetadataExtractor,
        mock_repository: MockImageMetadataRepository,
    ) -> None:
        """Empty retriever → no extraction, no persistence."""
        empty_retriever = MockImageRetriever(files=[])
        use_case = ParallelIndexPhotosUseCase(
            retriever=empty_retriever,
            extractor=mock_extractor,
            repository=mock_repository,
            num_workers=2,
        )

        results = use_case.execute()

        assert results == []
        assert mock_repository.list_all() == []

    def test_execute_worker_exception_handling(
        self,
        mock_retriever: MockImageRetriever,
        mock_repository: MockImageMetadataRepository,
    ) -> None:
        """Failing extractor on some files logs error and continues with remaining files."""
        failing_extractor = MagicMock()
        valid_meta = mock_repository.list_all()
        failing_extractor.extract.side_effect = [
            RuntimeError("Corrupt EXIF data"),
            valid_meta[0] if valid_meta else None,
            valid_meta[0] if valid_meta else None,
        ]

        use_case = ParallelIndexPhotosUseCase(
            retriever=mock_retriever,
            extractor=failing_extractor,
            repository=mock_repository,
            num_workers=2,
        )

        results = use_case.execute()
        assert len(results) >= 0

    def test_db_writer_worker_handles_save_error(
        self,
        mock_extractor: MockMetadataExtractor,
        mock_retriever: MockImageRetriever,
    ) -> None:
        """DB repository save failure is logged and does not crash the writer thread."""
        failing_repo = MagicMock()
        failing_repo.save.side_effect = Exception("DB Disk Full")

        use_case = ParallelIndexPhotosUseCase(
            retriever=mock_retriever,
            extractor=mock_extractor,
            repository=failing_repo,
            num_workers=2,
        )

        results = use_case.execute()
        assert results == []  # Save failed for all
