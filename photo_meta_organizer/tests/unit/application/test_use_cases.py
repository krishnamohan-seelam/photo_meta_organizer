"""Unit tests for application use cases.

Tests for IndexPhotosUseCase verifying it correctly coordinates
the ExtractorOrchestrator and repository for the full pipeline.
"""

import pytest
from typing import List

from photo_meta_organizer.application.use_cases import IndexPhotosUseCase
from photo_meta_organizer.domain.models import ImageMetadata
from tests.conftest import (
    MockImageMetadataRepository,
    MockImageRetriever,
    MockMetadataExtractor,
)


@pytest.mark.unit
class TestIndexPhotosUseCase:
    """Tests for IndexPhotosUseCase."""

    def test_execute_extracts_and_persists(
        self,
        mock_extractor: MockMetadataExtractor,
        mock_retriever: MockImageRetriever,
        mock_repository: MockImageMetadataRepository,
    ) -> None:
        """Full pipeline: discover → extract → persist."""
        use_case = IndexPhotosUseCase(
            retriever=mock_retriever,
            extractor=mock_extractor,
            repository=mock_repository,
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
        use_case = IndexPhotosUseCase(
            retriever=empty_retriever,
            extractor=mock_extractor,
            repository=mock_repository,
        )

        results = use_case.execute()

        assert results == []
        assert mock_repository.list_all() == []

    def test_execute_returns_extracted_metadata(
        self,
        mock_extractor: MockMetadataExtractor,
        mock_retriever: MockImageRetriever,
        mock_repository: MockImageMetadataRepository,
    ) -> None:
        """Returned list matches what was persisted."""
        use_case = IndexPhotosUseCase(
            retriever=mock_retriever,
            extractor=mock_extractor,
            repository=mock_repository,
        )

        results = use_case.execute()
        stored = mock_repository.list_all()

        # Results should match stored records
        assert len(results) == len(stored)
        for result in results:
            assert mock_repository.get_by_filehash(result.file_hash) is not None
