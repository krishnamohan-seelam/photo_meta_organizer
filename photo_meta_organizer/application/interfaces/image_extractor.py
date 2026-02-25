"""Image metadata extraction interface for domain-agnostic file processing.

This module defines the contract for extracting metadata from image files.
By using a Protocol-based interface, implementations can be plugged in
for different image formats and metadata sources.

Extraction follows Clean Architecture principles:

    1. Extractor has NO external dependencies (fully stateless)
    2. File stream is passed as a parameter (not injected)
    3. The extract() method processes individual files with provided stream
    4. Testability: easy to mock with BytesIO streams

Metadata extraction is responsible for:
- Reading from provided file stream (BytesIO)
- Extracting embedded metadata (EXIF, IPTC, etc.)
- Computing file hashes for duplicate detection
- Validating image format and dimensions
- Normalizing metadata into domain entities

The Protocol is designed for flexible composition:

- **Via ExtractorOrchestrator** (recommended for batch extraction):
    >>> from application.orchestrators import ExtractorOrchestrator
    >>> retriever = LocalDiskRetriever(base_path="/photos")
    >>> extractor = DiskMetadataExtractor()  # Stateless, no dependencies
    >>> orchestrator = ExtractorOrchestrator(extractor, retriever)
    >>> all_metadata = orchestrator.extract_all()

- **Direct use** (for custom iteration logic):
    >>> retriever = LocalDiskRetriever(base_path="/photos")
    >>> extractor = DiskMetadataExtractor()
    >>> for file_handle in retriever.list_files():
    ...     stream = retriever.get_file_stream(file_handle)
    ...     metadata = extractor.extract(file_handle, stream)
"""

from io import BytesIO
from typing import Protocol

from photo_meta_organizer.application.interfaces.image_retriever import (
    RemoteFileHandle,
)
from photo_meta_organizer.domain.models import ImageMetadata


class ImageMetadataExtractor(Protocol):
    """Protocol defining the contract for image metadata extraction.

    Implementations of this protocol extract metadata from image files
    by processing provided file streams. The protocol uses structural typing,
    allowing any class implementing these methods to be treated as an
    ImageMetadataExtractor.

    Design Principle - Stateless Processing:
        - Extractor contains NO external dependencies
        - File stream is provided as a parameter
        - Extract logic is pure and reusable
        - Easy to test with mock BytesIO streams

    Methods:
        extract: Extract metadata from a file stream.
    """

    def extract(self, file_handle: RemoteFileHandle, stream: BytesIO) -> ImageMetadata:
        """Extract metadata from an image file stream.

        This method is completely stateless. It receives both the file handle
        (metadata about the file) and the stream (actual file content) as
        parameters. This design enables:
        - No constructor dependencies needed
        - Easy mocking with BytesIO for testing
        - Composable with any file retrieval system
        - Parallel processing without state management

        Args:
            file_handle: RemoteFileHandle describing the file metadata.
                        Includes filename, path, and size.
            stream: BytesIO containing the file's binary content.
                   Positioned at start of file.

        Returns:
            ImageMetadata: A domain entity containing extracted metadata.

        Raises:
            IOError: If the stream cannot be read.
            ValueError: If the file is not a valid image or metadata is invalid.

        Note:
            The implementation must handle various image formats and
            gracefully handle missing or corrupted metadata. Errors should
            log details but not crash (for resilience during batch processing).
        """
        ...
