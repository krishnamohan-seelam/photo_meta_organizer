"""Test configuration, fixtures, and mock implementations.

This module provides:
1. Pytest configuration (markers, hooks, plugins)
2. Factory fixtures for creating test domain objects
3. Mock implementations demonstrating the dependency injection pattern
4. Fixtures for common test scenarios

The mock implementations serve educational purposes, demonstrating how
concrete classes implement the protocols and compose via dependency injection.
"""

import pytest
from contextlib import contextmanager
from datetime import datetime
from typing import BinaryIO, Generator, List, Optional
from io import BytesIO

from photo_meta_organizer.application.interfaces import (
    ImageMetadataExtractor,
    ImageMetadataRepository,
    ImageRetriever,
    RemoteFileHandle,
)
from photo_meta_organizer.domain.models import (
    CameraProfile,
    GpsCoordinates,
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageLocation,
    ImageMetadata,
)


# ============================================================================
# PYTEST CONFIGURATION & MARKERS
# ============================================================================


def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers",
        "unit: Unit tests for domain and application layers (no external dependencies)",
    )
    config.addinivalue_line(
        "markers",
        "integration: Integration tests requiring database or file system access",
    )


# ============================================================================
# FACTORY FIXTURES - Lightweight Object Creation
# ============================================================================


@pytest.fixture
def sample_file_handle() -> RemoteFileHandle:
    """Factory fixture creating a RemoteFileHandle for testing.

    Returns a typical file handle representing a JPEG image discovered
    during file system traversal.
    """
    return RemoteFileHandle(
        original_path="/photos/2024/01/vacation.jpg",
        filename="vacation.jpg",
        size_bytes=5_242_880,
    )


@pytest.fixture
def sample_file_handle_png() -> RemoteFileHandle:
    """Factory fixture creating a PNG RemoteFileHandle for testing."""
    return RemoteFileHandle(
        original_path="/photos/2024/02/landscape.png",
        filename="landscape.png",
        size_bytes=8_388_608,
    )


@pytest.fixture
def sample_image_location() -> GpsCoordinates:
    """Factory fixture for GpsCoordinates (GPS coordinates)."""
    return GpsCoordinates(latitude=37.7749, longitude=-122.4194)


@pytest.fixture
def sample_gps_coordinates() -> GpsCoordinates:
    """Factory fixture for GpsCoordinates (San Francisco)."""
    return GpsCoordinates(
        latitude=37.7749,
        longitude=-122.4194,
        altitude=10.0,
        datum="WGS84",
    )


@pytest.fixture
def sample_exif_data(sample_image_location: GpsCoordinates) -> ImageExifData:
    """Factory fixture for ImageExifData with realistic EXIF information."""
    return ImageExifData(
        camera_make="Sony",
        camera_model="A7III",
        f_stop=2.8,
        exposure_time="1/200",
        iso=800,
        focal_length="35mm",
        captured_at=datetime(2024, 1, 15, 14, 30, 0),
        camera_profile=CameraProfile.MIRRORLESS,
        location=sample_image_location,
        flash_fired=False,
        white_balance_mode="Auto",
        raw_tags={"LensModel": "Sony FE 35mm F1.4"},
    )


@pytest.fixture
def sample_exif_dslr() -> ImageExifData:
    """Sample EXIF from Sony SLT-A37 (DSLR from meta.txt sample)."""
    return ImageExifData(
        camera_make="Sony",
        camera_model="SLT-A37",
        camera_profile=CameraProfile.DSLR,
        captured_at=datetime(2022, 9, 21, 19, 49, 51),
        iso=100,
        f_stop=4.5,
        exposure_time="1/160",
        focal_length="28mm",
        focal_length_35mm="42mm",
        exposure_program="Manual",
        white_balance_mode="Manual",
        raw_tags={
            "LensModel": "DT 18-55mm F3.5-5.6 SAM",
            "Flash": "Flash fired, compulsory flash mode, return light detected",
            "FocalLengthIn35mmFilm": 42,
        },
    )


@pytest.fixture
def sample_exif_mobile() -> ImageExifData:
    """Sample EXIF from Xiaomi MI4 (mobile from meta2.txt sample)."""
    return ImageExifData(
        camera_make="Xiaomi",
        camera_model="MI4",
        camera_profile=CameraProfile.MOBILE,
        captured_at=datetime(2019, 1, 15, 12, 59, 32),
        iso=100,
        f_stop=1.69,
        exposure_time="0.01",
        focal_length="3.9mm",
        location=GpsCoordinates(
            latitude=17.509277,
            longitude=78.367018,
            altitude=0.0,
        ),
        white_balance_mode="Auto",
        flash_fired=False,
        raw_tags={
            "GPSDate": "2019-01-15",
            "GainControl": "Low gain up",
            "SubSecTime": "203048",
        },
    )


@pytest.fixture
def sample_image_metadata(sample_exif_data: ImageExifData) -> ImageMetadata:
    """Factory fixture creating realistic ImageMetadata for testing.

    Returns a complete, valid ImageMetadata entity matching PRD specification.
    """
    return ImageMetadata(
        file_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        file_info=ImageFileInfo(
            name="vacation.jpg",
            path="/photos/2024/01/vacation.jpg",
            size_bytes=5_242_880,
            mime_type="image/jpeg",
        ),
        dimensions=ImageDimensions(width=4000, height=3000),
        exif=sample_exif_data,
        labels=["beach", "sunset", "vacation"],
        added_at=datetime(2024, 2, 16, 10, 30, 0),
    )


@pytest.fixture
def sample_image_metadata_minimal() -> ImageMetadata:
    """Factory fixture for minimal ImageMetadata (no EXIF data).

    Useful for testing scenarios where a file lacks EXIF information.
    """
    return ImageMetadata(
        file_hash="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f",
        file_info=ImageFileInfo(
            name="no_exif.jpg",
            path="/photos/no_exif.jpg",
            size_bytes=1_048_576,
            mime_type="image/jpeg",
        ),
        dimensions=ImageDimensions(width=1920, height=1080),
        exif=ImageExifData(),  # Empty EXIF
        labels=[],
    )


# ============================================================================
# MOCK IMPLEMENTATIONS - Demonstrating Dependency Injection Pattern
# ============================================================================


class MockImageRetriever:
    """Mock implementation of ImageRetriever protocol.

    This demonstrates the retriever role in the dependency injection pattern.
    Real implementations would read from local disk, S3, FTP, etc.

    Attributes:
        files: List of RemoteFileHandle objects to return on list_files().
    """

    def __init__(self, files: Optional[List[RemoteFileHandle]] = None):
        """Initialize with optional list of files to discover.

        Args:
            files: List of RemoteFileHandle objects to simulate discovery.
                   If None, defaults to empty list.
        """
        self.files = files or []

    def list_files(self) -> Generator[RemoteFileHandle, None, None]:
        """Yield the configured file handles.

        Yields:
            RemoteFileHandle objects for testing.
        """
        for file_handle in self.files:
            yield file_handle

    @contextmanager
    def get_file_stream(self, file_handle: RemoteFileHandle) -> Generator[BinaryIO, None, None]:
        """Return a mock file stream as a context manager.

        Args:
            file_handle: The RemoteFileHandle describing the file.

        Yields:
            A BytesIO object containing dummy image data.
        """
        # For testing, return dummy JPEG header + data
        jpeg_header = b"\xff\xd8\xff\xe0"  # JPEG SOI + APP0 marker
        yield BytesIO(jpeg_header + b"fake image data")


class MockMetadataExtractor:
    """Mock implementation of ImageMetadataExtractor protocol.

    This demonstrates a stateless extractor implementation that processes
    file streams without any external dependencies.

    Design Benefits:
    - No constructor dependencies (fully stateless)
    - File stream passed as parameter (not injected)
    - Easy to test with mock BytesIO streams
    - Can be used with any file retrieval system
    - Ready for parallel processing or streaming patterns
    """

    def extract(self, file_handle: RemoteFileHandle, stream: BinaryIO) -> ImageMetadata:
        """Extract metadata from a file stream.

        This method is completely stateless. It receives both the file handle
        (metadata about the file) and the stream (actual content) as parameters.

        In a real implementation, would:
        1. Read from stream using exifread
        2. Compute SHA256 hash of stream content
        3. Validate image format (JPEG, PNG, etc.)
        4. Return ImageMetadata with all extracted fields

        For testing, returns minimal metadata without stream inspection.

        Args:
            file_handle: RemoteFileHandle describing the file metadata.
            stream: BytesIO containing the file's binary content.

        Returns:
            ImageMetadata with extracted data.
        """
        # For testing, return minimal metadata without inspecting stream
        return ImageMetadata(
            file_hash="mock_hash_" + file_handle.filename,
            file_info=ImageFileInfo(
                name=file_handle.filename,
                path=file_handle.original_path,
                size_bytes=file_handle.size_bytes,
                mime_type="image/jpeg",
            ),
            dimensions=ImageDimensions(width=1920, height=1080),
            exif=ImageExifData(),
        )


class MockImageMetadataRepository:
    """Mock implementation of ImageMetadataRepository protocol.

    This in-memory repository demonstrates the persistence interface.
    Real implementations would use TinyDB, MongoDB, DynamoDB, etc.

    Attributes:
        storage: Dict mapping file_hash -> ImageMetadata for in-memory storage.
    """

    def __init__(self):
        """Initialize with empty in-memory storage."""
        self.storage: dict[str, ImageMetadata] = {}

    def save(self, metadata: ImageMetadata) -> None:
        """Persist metadata to in-memory storage (upsert semantics).

        Args:
            metadata: ImageMetadata to store.
        """
        self.storage[metadata.file_hash] = metadata

    def get_by_filehash(self, file_hash: str) -> Optional[ImageMetadata]:
        """Retrieve metadata by file hash.

        Args:
            file_hash: The SHA256 hash of the file.

        Returns:
            ImageMetadata if found, None otherwise.
        """
        return self.storage.get(file_hash)

    def get_by_path(self, path: str) -> Optional[ImageMetadata]:
        """Retrieve metadata by file path.

        Args:
            path: The file path/storage key.

        Returns:
            ImageMetadata if found, None otherwise.
        """
        return next(
            (metadata for metadata in self.storage.values() if metadata.file_info.path == path),
            None,
        )

    def list_all(self) -> List[ImageMetadata]:
        """Retrieve all stored metadata.

        Returns:
            List of all ImageMetadata objects.
        """
        return list(self.storage.values())

    def delete(self, file_hash: str) -> bool:
        """Delete metadata by file hash.

        Args:
            file_hash: The SHA256 hash of the file to delete.

        Returns:
            True if deleted, False if not found.
        """
        if file_hash in self.storage:
            del self.storage[file_hash]
            return True
        return False

    def bulk_save(self, metadata_list: List[ImageMetadata]) -> None:
        """Save multiple metadata objects.

        Args:
            metadata_list: List of ImageMetadata objects to save.
        """
        for metadata in metadata_list:
            self.save(metadata)


# ============================================================================
# DEPENDENCY INJECTION FIXTURES - Wired Mocks
# ============================================================================


@pytest.fixture
def mock_retriever(sample_file_handle: RemoteFileHandle) -> MockImageRetriever:
    """Fixture providing a MockImageRetriever with sample files.

    Useful for testing retriever behavior in isolation.
    """
    return MockImageRetriever(files=[sample_file_handle])


@pytest.fixture
def mock_extractor() -> MockMetadataExtractor:
    """Fixture providing a stateless metadata extractor.

    This demonstrates the new design principle:
    - Extractor has NO external dependencies
    - Stateless and pure (same instance works everywhere)
    - Stream is passed as parameter, not injected
    - Easy to test with mock BytesIO streams
    """
    return MockMetadataExtractor()


@pytest.fixture
def mock_repository() -> MockImageMetadataRepository:
    """Fixture providing an in-memory mock repository."""
    return MockImageMetadataRepository()


# ============================================================================
# INTEGRATION FIXTURE - Full Pipeline
# ============================================================================


@pytest.fixture
def di_wired_components(
    mock_retriever: MockImageRetriever,
    mock_extractor: MockMetadataExtractor,
    mock_repository: MockImageMetadataRepository,
) -> dict:
    """Fixture providing all three components wired together via DI.

    This represents the composition root where dependencies are injected.
    In production, this would be in main.py or a dedicated DI container.

    Returns:
        Dictionary with 'retriever', 'extractor', 'repository' components.
    """
    return {
        "retriever": mock_retriever,
        "extractor": mock_extractor,
        "repository": mock_repository,
    }
