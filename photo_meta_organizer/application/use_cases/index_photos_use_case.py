"""Index Photos use case — full metadata extraction pipeline.

This use case coordinates the complete indexing workflow:
1. Discover image files via a retriever
2. Extract metadata from each file via ExtractorOrchestrator
3. Persist results to a repository

It composes the ExtractorOrchestrator (retrieve → extract) with a
repository (persist) to implement the full pipeline as a single
application-level operation.

Example:
    >>> use_case = IndexPhotosUseCase(
    ...     retriever=LocalDiskRetriever(base_path="/photos"),
    ...     extractor=DiskMetaDataExtractor(),
    ...     repository=TinyDBRepository(db_path="metadata.json"),
    ... )
    >>> results = use_case.execute()
    >>> print(f"Indexed {len(results)} photos")
"""

import logging
from typing import List

from photo_meta_organizer.application.interfaces import (
    ImageMetadataExtractor,
    ImageMetadataRepository,
    ImageRetriever,
)
from photo_meta_organizer.application.orchestrators import ExtractorOrchestrator
from photo_meta_organizer.domain.models import ImageMetadata

logger = logging.getLogger(__name__)


class IndexPhotosUseCase:
    """Use case: Scan photos, extract metadata, and persist to storage.

    This class bridges ExtractorOrchestrator (which handles retrieve → extract)
    with a repository (which handles persistence), completing the full pipeline.

    All three dependencies (retriever, extractor, repository) are injected
    as interfaces — concrete implementations are selected by the composition
    root (main.py).

    Attributes:
        _orchestrator: Coordinates file discovery and metadata extraction.
        _repository: Persists extracted metadata to storage.
    """

    def __init__(
        self,
        retriever: ImageRetriever,
        extractor: ImageMetadataExtractor,
        repository: ImageMetadataRepository,
    ) -> None:
        """Initialize with injected dependencies.

        Args:
            retriever: Storage backend for file discovery and streaming.
            extractor: Stateless metadata extractor.
            repository: Persistence backend for extracted metadata.
        """
        self._orchestrator = ExtractorOrchestrator(extractor, retriever)
        self._repository = repository

    def execute(self) -> List[ImageMetadata]:
        """Run the full indexing pipeline.

        Flow:
            1. ExtractorOrchestrator discovers files and extracts metadata
            2. Results are bulk-saved to the repository
            3. Returns the list of extracted metadata for reporting

        Returns:
            List of ImageMetadata objects that were extracted and persisted.

        Raises:
            IOError: If file discovery or persistence fails.
        """
        logger.info("Starting photo indexing pipeline")
        results = self._orchestrator.extract_all()
        logger.info("Extracted metadata from %d files", len(results))

        if results:
            for metadata in results:
                self._repository.save(metadata)
            logger.info("Persisted %d metadata records", len(results))

        return results
