"""Application layer interfaces and abstract base classes.

This module defines the contracts that infrastructure implementations must satisfy.
Protocols are used to decouple the application from specific implementations,
enabling easier testing and extensibility through dependency injection.

The interfaces follow the Dependency Inversion Principle: high-level modules
should depend on abstractions, not on low-level concrete implementations.

Component Architecture:
    The three core interfaces work together:

        1. ImageRetriever (Storage Backend)
           - Discovers files in local disk, S3, FTP, etc.
           - Provides file streams via get_file_stream()
           - Returns RemoteFileHandle for each file

        2. ImageMetadataExtractor (Processing) - Stateless
           - NO external dependencies (fully decoupled)
           - extract(file_handle, stream) -> ImageMetadata
           - Receives file streams as parameters
           - Same instance can process unlimited files

        3. ImageMetadataRepository (Persistence)
           - Accepts extracted ImageMetadata
           - save(metadata) persists to database
           - Implementations: TinyDB, MongoDB, Elasticsearch, etc.

    Orchestrator Pattern (ExtractorOrchestrator):
    - Coordinates interaction between Retriever and Extractor
    - Simplifies client code for batch operations
    - Manages stream fetching and passing

    This composition enables:
    - Swappable storage backends without changing extractor logic
    - Testability: easy to mock with BytesIO streams
    - Scalability: stateless extractor ready for parallel processing
    - Streaming: supports batching, filtering, custom iteration patterns

Example Wiring - Via Orchestrator (Recommended):
    >>> from application.orchestrators import ExtractorOrchestrator
    >>> retriever = LocalDiskRetriever(base_path="/photos")
    >>> extractor = DiskMetadataExtractor()  # Stateless
    >>> orchestrator = ExtractorOrchestrator(extractor, retriever)
    >>> all_metadata = orchestrator.extract_all()
    >>> repository = TinyDBRepository(db_path="./metadata.json")
    >>> for metadata in all_metadata:
    ...     repository.save(metadata)

Example Wiring - Manual (Custom Logic):
    >>> retriever = LocalDiskRetriever(base_path="/photos")
    >>> extractor = DiskMetadataExtractor()  # Stateless
    >>> repository = TinyDBRepository(db_path="./metadata.json")
    >>> for file_handle in retriever.list_files():
    ...     stream = retriever.get_file_stream(file_handle)
    ...     metadata = extractor.extract(file_handle, stream)
    ...     repository.save(metadata)

Exports:
    ImageMetadataExtractor: Protocol for extracting metadata from images.
    ImageMetadataRepository: Protocol for persisting image metadata.
    ImageRetriever: Protocol for discovering image files in storage.
    RemoteFileHandle: Value object for file metadata before processing.
"""

from photo_meta_organizer.application.interfaces.image_extractor import (
    ImageMetadataExtractor,
)
from photo_meta_organizer.application.interfaces.image_repository import (
    ImageMetadataRepository,
)
from photo_meta_organizer.application.interfaces.image_retriever import (
    ImageRetriever,
    RemoteFileHandle,
)

__all__ = [
    "ImageMetadataExtractor",
    "ImageMetadataRepository",
    "ImageRetriever",
    "RemoteFileHandle",
]
