"""Parallel Index Photos use case — high-performance metadata extraction pipeline.

This use case coordinates the indexing workflow using multi-threading:
1. Discover image files via a retriever (Main Thread)
2. Extract metadata from each file via Extractor (Worker Pool)
3. Persist results to a repository via a buffered queue (Dedicated DB Writer Thread)

It uses ThreadPoolExecutor to parallelize I/O-bound and CPU-bound extraction tasks
while ensuring single-threaded access to the underlying storage repository.
"""

import logging
import queue
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from photo_meta_organizer.application.interfaces import (
    ImageMetadataExtractor,
    ImageMetadataRepository,
    ImageRetriever,
)
from photo_meta_organizer.domain.models import ImageMetadata
from photo_meta_organizer.infrastructure.metrics import ProgressReporter

logger = logging.getLogger(__name__)

# Poison pill to signal the database writer thread to terminate
_POISON_PILL = object()


class ParallelIndexPhotosUseCase:
    """Use case: Scan photos and extract metadata concurrently.

    Attributes:
        _retriever: Discovers files and provides streams.
        _extractor: Stateless metadata extractor.
        _repository: Persists extracted metadata.
        _num_workers: Number of concurrent extraction threads.
    """

    def __init__(
        self,
        retriever: ImageRetriever,
        extractor: ImageMetadataExtractor,
        repository: ImageMetadataRepository,
        num_workers: int = 4,
    ) -> None:
        """Initialize with injected dependencies.

        Args:
            retriever: Storage backend for file discovery.
            extractor: Stateless metadata extractor.
            repository: Persistence backend.
            num_workers: Number of extraction threads (default: 4).
        """
        self._retriever = retriever
        self._extractor = extractor
        self._repository = repository
        self._num_workers = num_workers

    def execute(self) -> List[ImageMetadata]:
        """Run the parallel indexing pipeline.

        Returns:
            List of ImageMetadata objects successfully processed.
        """
        logger.info("Starting parallel photo indexing pipeline with %d workers", self._num_workers)

        reporter = ProgressReporter()
        db_queue: queue.Queue = queue.Queue(maxsize=100)
        results: List[ImageMetadata] = []
        errors: List[str] = []

        writer_thread = threading.Thread(
            target=self._db_writer_worker,
            args=(db_queue, results, reporter),
            daemon=True,
        )
        writer_thread.start()

        # 1. Discovery (Main Thread) - gather all to provide ETA
        files = list(self._retriever.list_files())
        reporter.start(total=len(files), desc="Parallel Indexing")

        try:
            with ThreadPoolExecutor(max_workers=self._num_workers) as executor:
                futures = {}
                for file_handle in files:
                    # 2. Submit extraction task
                    future = executor.submit(self._extract_task, file_handle)
                    futures[future] = file_handle

                for future in as_completed(futures):
                    file_handle = futures[future]
                    try:
                        metadata = future.result()
                        if metadata:
                            db_queue.put(metadata)
                        else:
                            # Still record progress if extraction skipped it
                            reporter.update(1)
                    except Exception as e:
                        reporter.record_error(type(e).__name__)
                        reporter.update(1)
                        msg = f"Failed to extract metadata for {file_handle.filename}: {e}"
                        logger.error(msg)
                        errors.append(msg)
        finally:
            db_queue.put(_POISON_PILL)
            writer_thread.join()
            reporter.stop()

        logger.info("Parallel indexing complete. Processed: %d, Errors: %d", len(results), len(errors))
        return results

    def _extract_task(self, file_handle) -> Optional[ImageMetadata]:
        """Worker task to extract metadata for a single file."""
        try:
            with self._retriever.get_file_stream(file_handle) as stream:
                return self._extractor.extract(file_handle, stream)
        except Exception as e:
            logger.error("Error processing %s: %s", file_handle.filename, e)
            raise

    def _db_writer_worker(self, db_queue: queue.Queue, results: List[ImageMetadata], reporter: ProgressReporter) -> None:
        """Dedicated thread task to write metadata to the repository.

        Args:
            db_queue: Queue providing extracted ImageMetadata objects.
            results: Shared list to collect successfully saved metadata.
            reporter: ProgressReporter for unified metrics updates.
        """
        while True:
            item = db_queue.get()
            if item is _POISON_PILL:
                db_queue.task_done()
                break

            try:
                self._repository.save(item)
                results.append(item)
                reporter.update(1, metadata=item)
            except Exception as e:
                reporter.record_error("db_save_error")
                reporter.update(1)
                logger.error("Failed to save metadata for %s: %s", getattr(item.file_info, 'name', 'unknown'), e)
            finally:
                db_queue.task_done()
