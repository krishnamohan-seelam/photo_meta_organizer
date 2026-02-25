"""Unit tests for application layer interfaces and dependency injection pattern.

These tests verify that:
1. Protocols are properly defined and documented
2. Mock implementations correctly satisfy protocol contracts
3. Stateless extractor design works correctly
4. ExtractorOrchestrator coordinates components properly
"""

import pytest
from io import BytesIO

from photo_meta_organizer.application.interfaces import (
    ImageMetadataExtractor,
    ImageMetadataRepository,
    ImageRetriever,
    RemoteFileHandle,
)
from photo_meta_organizer.domain.models import ImageMetadata
from tests.conftest import (
    MockImageMetadataRepository,
    MockImageRetriever,
    MockMetadataExtractor,
)


@pytest.mark.unit
class TestImageRetrieverProtocol:
    """Test ImageRetriever protocol compliance."""

    def test_mock_retriever_lists_files(self, mock_retriever: MockImageRetriever) -> None:
        """Test that mock retriever implements list_files() correctly."""
        files = list(mock_retriever.list_files())
        assert isinstance(files, list)
        assert len(files) > 0
        assert all(isinstance(f, RemoteFileHandle) for f in files)

    def test_mock_retriever_returns_file_stream(
        self, mock_retriever: MockImageRetriever, sample_file_handle: RemoteFileHandle
    ) -> None:
        """Test that mock retriever can return file stream for handles."""
        with mock_retriever.get_file_stream(sample_file_handle) as stream:
            assert isinstance(stream, BytesIO)
            # Should have some content
            content = stream.read()
            assert len(content) > 0

    def test_retriever_protocol_structural_typing(self, mock_retriever: MockImageRetriever) -> None:
        """Test that mock retriever satisfies ImageRetriever protocol via duck typing."""
        # If these methods exist and have right signatures, it's an ImageRetriever
        assert hasattr(mock_retriever, "list_files")
        assert callable(mock_retriever.list_files)
        assert hasattr(mock_retriever, "get_file_stream")
        assert callable(mock_retriever.get_file_stream)


@pytest.mark.unit
class TestImageMetadataExtractorDependencyInjection:
    """Test ImageMetadataExtractor protocol with stateless design."""

    def test_extractor_is_stateless(
        self,
        mock_extractor: MockMetadataExtractor,
        sample_file_handle: RemoteFileHandle,
        sample_file_handle_png: RemoteFileHandle,
        mock_retriever: MockImageRetriever,
    ) -> None:
        """Test that same extractor instance can process multiple files.

        The extractor is completely stateless - it has no external dependencies.
        It processes files via stream parameters passed to extract().
        """
        # Process first file (retrieve stream, extract metadata)
        with mock_retriever.get_file_stream(sample_file_handle) as stream1:
            metadata1 = mock_extractor.extract(sample_file_handle, stream1)
        assert metadata1 is not None
        assert metadata1.file_info.name == sample_file_handle.filename

        # Process second file with SAME extractor instance (still stateless)
        with mock_retriever.get_file_stream(sample_file_handle_png) as stream2:
            metadata2 = mock_extractor.extract(sample_file_handle_png, stream2)
        assert metadata2 is not None
        assert metadata2.file_info.name == sample_file_handle_png.filename

        # Metadata should be different, but extractor remains unchanged
        assert metadata1.file_hash != metadata2.file_hash

    def test_extractor_receives_stream_parameter(
        self,
        mock_extractor: MockMetadataExtractor,
        sample_file_handle: RemoteFileHandle,
    ) -> None:
        """Test that extractor processes file stream passed as parameter."""
        # Stream is provided as a parameter, not injected
        from io import BytesIO

        test_stream = BytesIO(b"test image data")

        metadata = mock_extractor.extract(sample_file_handle, test_stream)
        assert metadata is not None
        assert isinstance(metadata, ImageMetadata)

    def test_swappable_streams(
        self,
        mock_extractor: MockMetadataExtractor,
        sample_file_handle: RemoteFileHandle,
    ) -> None:
        """Test that extractor works with different stream sources.

        Same extractor can process streams from any source (local disk, S3, etc.)
        as long as they're BytesIO objects. This demonstrates decoupling.
        """
        from io import BytesIO

        # Streams could come from any backend
        stream1 = BytesIO(b"local disk image data")
        stream2 = BytesIO(b"s3 image data")

        # Same extractor processes both
        metadata1 = mock_extractor.extract(sample_file_handle, stream1)
        metadata2 = mock_extractor.extract(sample_file_handle, stream2)

        # Both produce same metadata structure (implementation doesn't care about source)
        assert type(metadata1) == type(metadata2)
        assert metadata1.file_hash == metadata2.file_hash  # Same file handle = same hash (mock)


@pytest.mark.unit
class TestImageMetadataRepositoryProtocol:
    """Test ImageMetadataRepository protocol compliance."""

    def test_repository_save_and_retrieve(
        self,
        mock_repository: MockImageMetadataRepository,
        sample_image_metadata,
    ) -> None:
        """Test basic save and retrieve operations."""
        mock_repository.save(sample_image_metadata)
        retrieved = mock_repository.get_by_filehash(sample_image_metadata.file_hash)
        assert retrieved == sample_image_metadata

    def test_repository_get_by_nonexistent_hash(
        self, mock_repository: MockImageMetadataRepository
    ) -> None:
        """Test retrieving non-existent metadata returns None."""
        result = mock_repository.get_by_filehash("nonexistent_hash")
        assert result is None

    def test_repository_get_by_path(
        self,
        mock_repository: MockImageMetadataRepository,
        sample_image_metadata,
    ) -> None:
        """Test retrieving metadata by file path."""
        mock_repository.save(sample_image_metadata)
        retrieved = mock_repository.get_by_path(sample_image_metadata.file_info.path)
        assert retrieved == sample_image_metadata

    def test_repository_list_all(
        self,
        mock_repository: MockImageMetadataRepository,
        sample_image_metadata,
        sample_image_metadata_minimal,
    ) -> None:
        """Test listing all stored metadata."""
        mock_repository.save(sample_image_metadata)
        mock_repository.save(sample_image_metadata_minimal)
        all_metadata = mock_repository.list_all()
        assert len(all_metadata) == 2

    def test_repository_delete(
        self,
        mock_repository: MockImageMetadataRepository,
        sample_image_metadata,
    ) -> None:
        """Test deleting metadata by hash."""
        mock_repository.save(sample_image_metadata)
        deleted = mock_repository.delete(sample_image_metadata.file_hash)
        assert deleted is True
        assert mock_repository.get_by_filehash(sample_image_metadata.file_hash) is None

    def test_repository_delete_nonexistent(
        self, mock_repository: MockImageMetadataRepository
    ) -> None:
        """Test deleting non-existent metadata returns False."""
        result = mock_repository.delete("nonexistent_hash")
        assert result is False

    def test_repository_bulk_save(
        self,
        mock_repository: MockImageMetadataRepository,
        sample_image_metadata,
        sample_image_metadata_minimal,
    ) -> None:
        """Test bulk save operation."""
        metadata_list = [sample_image_metadata, sample_image_metadata_minimal]
        mock_repository.bulk_save(metadata_list)
        assert len(mock_repository.list_all()) == 2

    def test_repository_upsert_semantics(
        self,
        mock_repository: MockImageMetadataRepository,
        sample_image_metadata,
    ) -> None:
        """Test that repository.save() implements upsert (update if exists)."""
        # First save
        mock_repository.save(sample_image_metadata)
        list1 = mock_repository.list_all()
        assert len(list1) == 1

        # Save again with same hash (should update, not duplicate)
        mock_repository.save(sample_image_metadata)
        list2 = mock_repository.list_all()
        assert len(list2) == 1  # Still only one entry


@pytest.mark.unit
class TestDependencyInjectionComposition:
    """Test complete DI composition with orchestrator pattern."""

    def test_full_pipeline_with_orchestrator(
        self,
        mock_extractor: MockMetadataExtractor,
        mock_retriever: MockImageRetriever,
        mock_repository: MockImageMetadataRepository,
    ) -> None:
        """Test complete data flow using ExtractorOrchestrator.

        Demonstrates the full application flow:
        Orchestrator → Retriever (discover files + get streams) →
        Extractor (process streams) → Repository (persist)
        """
        from photo_meta_organizer.application.orchestrators import ExtractorOrchestrator

        # Wire components via orchestrator
        orchestrator = ExtractorOrchestrator(mock_extractor, mock_retriever)

        # 1. Orchestrator discovers files and extracts metadata
        metadata_list = orchestrator.extract_all()
        assert len(metadata_list) > 0

        # 2. Persist extracted metadata to repository
        for metadata in metadata_list:
            mock_repository.save(metadata)

        # 3. Verify persistence
        all_stored = mock_repository.list_all()
        assert len(all_stored) == len(metadata_list)

    def test_manual_pipeline_without_orchestrator(
        self,
        mock_extractor: MockMetadataExtractor,
        mock_retriever: MockImageRetriever,
        mock_repository: MockImageMetadataRepository,
    ) -> None:
        """Test data flow without orchestrator (manual control).

        This demonstrates that extractor can be used directly for
        custom iteration patterns and filtering.
        """
        # 1. Discover files
        files = list(mock_retriever.list_files())
        assert len(files) > 0

        # 2. Process each file (manual iteration = custom control)
        for file_handle in files:
            # Orchestrator normally does this, but we can too
            with mock_retriever.get_file_stream(file_handle) as stream:
                metadata = mock_extractor.extract(file_handle, stream)
            mock_repository.save(metadata)

        # 3. Verify persistence
        all_stored = mock_repository.list_all()
        assert len(all_stored) == len(files)

    def test_stateless_extractor_enables_parallelism(
        self, sample_file_handle: RemoteFileHandle
    ) -> None:
        """Test that stateless extractor design enables parallel processing.

        Without injected dependencies, multiple extractor instances can
        safely process different files in parallel threads/processes.
        """
        from io import BytesIO

        retriever = MockImageRetriever(files=[sample_file_handle])
        repository = MockImageMetadataRepository()

        # Multiple stateless extractor instances (no shared state)
        extractor1 = MockMetadataExtractor()  # No dependencies
        extractor2 = MockMetadataExtractor()  # No dependencies
        extractor3 = MockMetadataExtractor()  # No dependencies

        # All independent, safe for parallel execution
        assert extractor1 is not extractor2
        assert extractor2 is not extractor3

        # Each can process files independently
        with retriever.get_file_stream(sample_file_handle) as stream:
            metadata1 = extractor1.extract(sample_file_handle, stream)
            metadata2 = extractor2.extract(sample_file_handle, stream)
            metadata3 = extractor3.extract(sample_file_handle, stream)

        # Same results from same stateless logic
        assert metadata1.file_hash == metadata2.file_hash == metadata3.file_hash

    def test_extractor_decoupled_from_retrieval_source(self) -> None:
        """Test that extractor works with any BytesIO source.

        Extractor doesn't know or care where streams come from.
        Enables composition with any storage backend.
        """
        from io import BytesIO

        # File handle could come from any source
        file_handle = RemoteFileHandle(
            original_path="/photos/test.jpg",
            filename="test.jpg",
            size_bytes=5000000,
        )

        extractor = MockMetadataExtractor()  # Stateless

        # Different stream sources (local disk, S3, FTP, memory, etc.)
        local_stream = BytesIO(b"local disk data")
        s3_stream = BytesIO(b"s3 data")
        ftp_stream = BytesIO(b"ftp data")

        # Same extractor works with all sources
        local_metadata = extractor.extract(file_handle, local_stream)
        s3_metadata = extractor.extract(file_handle, s3_stream)
        ftp_metadata = extractor.extract(file_handle, ftp_stream)

        # Same processing logic for all sources
        assert type(local_metadata) == type(s3_metadata) == type(ftp_metadata)
