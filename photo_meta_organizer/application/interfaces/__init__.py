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

    The scan (``application.use_cases.scan_library.ScanLibrary``, built by
    ``application.composition.build_scan``) wires the three together.

    This composition enables:
    - Swappable storage backends without changing extractor logic
    - Testability: easy to mock with BytesIO streams
    - Scalability: stateless extractor ready for parallel processing
    - Streaming: supports batching, filtering, custom iteration patterns

Example Wiring - Via the scan (Recommended):
    >>> scan = build_scan("/photos", build_repository("photos.db"))
    >>> result = scan.execute(ScanOptions(workers=4), scope_root="/photos")

Example Wiring - Manual (Custom Logic):
    >>> retriever = LocalDiskRetriever(base_path="/photos")
    >>> extractor = DiskMetadataExtractor()  # Stateless
    >>> repository = SqliteRepository(db_path="photos.db")
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

from photo_meta_organizer.application.interfaces.analysis_repository import (
    AnalysisRepository,
    PendingPhoto,
)
from photo_meta_organizer.application.interfaces.collection_repository import (
    CollectionRecord,
    CollectionRepository,
)
from photo_meta_organizer.application.interfaces.image_embedder import ImageEmbedder
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
from photo_meta_organizer.application.interfaces.search_types import (
    BoundingBox,
    FacetCount,
    Facets,
    GeoCluster,
    GpsBounds,
    Page,
    SearchQuery,
)

__all__ = [
    "AnalysisRepository",
    "BoundingBox",
    "CollectionRepository",
    "CollectionRecord",
    "Facets",
    "FacetCount",
    "GeoCluster",
    "GpsBounds",
    "ImageEmbedder",
    "ImageMetadataExtractor",
    "ImageMetadataRepository",
    "ImageRetriever",
    "Page",
    "PendingPhoto",
    "RemoteFileHandle",
    "SearchQuery",
]
