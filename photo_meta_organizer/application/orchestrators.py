"""Orchestrators for coordinating application-level workflows.

This module contains orchestrator classes that coordinate interactions between
multiple application interfaces (e.g., ImageMetadataExtractor and ImageRetriever).

Orchestrators follow Clean Architecture principles:
- They depend on application interfaces (Protocols), not implementations
- They coordinate behavior but don't contain business logic
- They are easily testable through dependency injection
- They provide convenient APIs for common workflows

Example:
    >>> retriever = LocalDiskRetriever(base_path="/photos")
    >>> extractor = DiskMetadataExtractor()  # No dependencies needed
    >>> orchestrator = ExtractorOrchestrator(extractor, retriever)
    >>> metadata_list = orchestrator.extract_all()
"""

from io import BytesIO
from typing import List

from photo_meta_organizer.application.interfaces.image_extractor import (
    ImageMetadataExtractor,
)
from photo_meta_organizer.application.interfaces.image_retriever import (
    ImageRetriever,
)
from photo_meta_organizer.domain.models import ImageMetadata


class ExtractorOrchestrator:
    """Coordinates batch metadata extraction across multiple files.

    This orchestrator provides a convenient high-level API for extracting
    metadata from all files discovered by an ImageRetriever. It bridges
    the retriever (which finds files and reads streams) with the extractor
    (which processes file streams), simplifying the client API while
    maintaining the flexibility and testability of the underlying interfaces.

    Responsibilities:
        - Iterating through files discovered by retriever
        - Fetching file streams from retriever
        - Passing streams to extractor for processing
        - Collecting and returning results

    Constructor Injection:
        Both dependencies are injected via constructor, enabling easy
        mocking for tests and flexible composition.

    Attributes:
        _extractor: An ImageMetadataExtractor implementation that extracts
                   metadata from provided file streams (stateless).
        _retriever: An ImageRetriever implementation that discovers files
                   and provides file streams.

    Example:
        >>> from infrastructure.retriever.local_disk_retriever import LocalDiskRetriever
        >>> from infrastructure.extractors import DiskMetadataExtractor
        >>>
        >>> retriever = LocalDiskRetriever(base_path="/photos")
        >>> extractor = DiskMetadataExtractor()  # Stateless, no dependencies
        >>> orchestrator = ExtractorOrchestrator(extractor, retriever)
        >>> all_metadata = orchestrator.extract_all()
        >>> for metadata in all_metadata:
        ...     print(f"{metadata.filename}: {metadata.dimensions}")
    """

    def __init__(
        self,
        extractor: ImageMetadataExtractor,
        retriever: ImageRetriever,
    ) -> None:
        """Initialize the orchestrator with extractor and retriever.

        Args:
            extractor: An ImageMetadataExtractor for processing file streams.
                      Must be stateless (no external dependencies).
            retriever: An ImageRetriever for discovering files and providing streams.
        """
        self._extractor = extractor
        self._retriever = retriever

    def extract_all(self) -> List[ImageMetadata]:
        """Extract metadata from all files discovered by the retriever.

        Iterates through all files returned by the retriever, fetches their
        streams, and passes them to the extractor for metadata processing.
        Returns results as a list for immediate access.

        Flow:
            1. Retriever discovers files (list_files)
            2. For each file, retriever provides stream (get_file_stream)
            3. Extractor processes stream to extract metadata
            4. Results collected and returned as list

        Returns:
            A list of ImageMetadata objects, one for each successfully
            processed file. Empty list if no files are discovered.

        Raises:
            IOError: If a file cannot be read via the retriever.
            ValueError: If metadata extraction fails for a file.

        Note:
            For large file collections, consider using extract_streaming()
            (when available) to avoid loading all results in memory.
        """
        results: List[ImageMetadata] = []
        for file_handle in self._retriever.list_files():
            with self._retriever.get_file_stream(file_handle) as stream:
                metadata = self._extractor.extract(file_handle, stream)
            results.append(metadata)
        return results
