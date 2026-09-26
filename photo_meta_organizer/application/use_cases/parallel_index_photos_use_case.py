"""Parallel Index Photos use case — high-performance metadata extraction pipeline.

This use case coordinates the indexing workflow using multi-threading:
1. Discover image files via a retriever (Main Thread)
2. Extract metadata from each file via Extractor (Worker Pool)
3. Persist results to a repository via a buffered queue (Dedicated DB Writer Thread)

It uses ThreadPoolExecutor to parallelize I/O-bound and CPU-bound extraction tasks
while ensuring single-threaded access to the underlying storage repository.

``run`` is the full-featured entry point (progress callback, cooperative cancel, an
``IndexReport`` with every per-file error); ``execute`` keeps the old list-returning
signature for the CLI. Work is submitted a few files at a time rather than all up
front, so a cancel stops within roughly ``2 * num_workers`` files.
"""

import logging
import queue
import threading
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field

from photo_meta_organizer.application.interfaces import (
    ImageMetadataExtractor,
    ImageMetadataRepository,
    ImageRetriever,
)
from photo_meta_organizer.application.interfaces.image_retriever import RemoteFileHandle
from photo_meta_organizer.domain.models import ImageMetadata
from photo_meta_organizer.infrastructure.metrics import ProgressReporter

logger = logging.getLogger(__name__)

# Poison pill to signal the database writer thread to terminate
_POISON_PILL = object()


@dataclass(frozen=True)
class IndexProgress:
    """A progress snapshot: ``processed`` counts successes and failures alike."""

    total: int
    processed: int
    failed: int


@dataclass
class IndexReport:
    """Outcome of one indexing run."""

    indexed: list[ImageMetadata] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    total: int = 0
    cancelled: bool = False


class _Tally:
    """Thread-safe progress counter shared by the main thread and the DB writer."""

    def __init__(
        self, report: IndexReport, progress: Callable[[IndexProgress], None] | None
    ) -> None:
        self._report = report
        self._progress = progress
        self._lock = threading.Lock()
        self._processed = 0

    def succeeded(self, metadata: ImageMetadata) -> None:
        with self._lock:
            self._report.indexed.append(metadata)
            self._bump()

    def failed(self, message: str) -> None:
        with self._lock:
            self._report.errors.append(message)
            self._bump()

    def _bump(self) -> None:
        self._processed += 1
        if self._progress is not None:
            self._progress(
                IndexProgress(self._report.total, self._processed, len(self._report.errors))
            )


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

    def execute(self) -> list[ImageMetadata]:
        """Run the parallel indexing pipeline.

        Returns:
            List of ImageMetadata objects successfully processed.
        """
        return self.run().indexed

    def run(
        self,
        progress: Callable[[IndexProgress], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
        show_progress_bar: bool = True,
    ) -> IndexReport:
        """Run the pipeline and report what happened.

        Args:
            progress: Called once when the file count is known and after every file
                (from the main thread or the DB-writer thread).
            should_cancel: Polled during discovery and before each submission. Files
                already extracted when it turns true are still saved.
            show_progress_bar: Show the console progress bar (off for API jobs).
        """
        cancelled = should_cancel or (lambda: False)
        report = IndexReport()
        tally = _Tally(report, progress)
        logger.info("Starting parallel photo indexing pipeline with %d workers", self._num_workers)

        # 1. Discovery (Main Thread) - gather all to provide ETA
        files: list[RemoteFileHandle] = []
        for file_handle in self._retriever.list_files():
            if cancelled():
                break
            files.append(file_handle)
        if cancelled():
            report.cancelled = True
            return report

        report.total = len(files)
        if progress is not None:
            progress(IndexProgress(report.total, 0, 0))

        reporter = ProgressReporter(disable_bar=not show_progress_bar)
        reporter.start(total=len(files), desc="Parallel Indexing")
        db_queue: queue.Queue = queue.Queue(maxsize=100)
        writer_thread = threading.Thread(
            target=self._db_writer_worker, args=(db_queue, tally, reporter), daemon=True
        )
        writer_thread.start()

        try:
            with ThreadPoolExecutor(max_workers=self._num_workers) as executor:
                in_flight: dict[Future, RemoteFileHandle] = {}
                pending = iter(files)
                max_in_flight = self._num_workers * 2
                exhausted = False

                while True:
                    # 2. Keep a small window of extraction tasks in flight.
                    while not exhausted and len(in_flight) < max_in_flight:
                        if cancelled():
                            report.cancelled = True
                            exhausted = True
                            break
                        next_handle = next(pending, None)
                        if next_handle is None:
                            exhausted = True
                            break
                        in_flight[executor.submit(self._extract_task, next_handle)] = next_handle

                    if not in_flight:
                        break

                    done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
                    for future in done:
                        file_handle = in_flight.pop(future)
                        try:
                            metadata = future.result()
                        except Exception as e:
                            reporter.record_error(type(e).__name__)
                            reporter.update(1)
                            msg = f"Failed to extract metadata for {file_handle.filename}: {e}"
                            logger.error(msg)
                            tally.failed(msg)
                            continue
                        if metadata:
                            db_queue.put(metadata)
                        else:
                            reporter.update(1)
                            tally.failed(f"No metadata extracted for {file_handle.filename}")
        finally:
            db_queue.put(_POISON_PILL)
            writer_thread.join()
            reporter.stop()

        logger.info(
            "Parallel indexing %s. Processed: %d, Errors: %d",
            "cancelled" if report.cancelled else "complete",
            len(report.indexed),
            len(report.errors),
        )
        return report

    def _extract_task(self, file_handle: RemoteFileHandle) -> ImageMetadata | None:
        """Worker task to extract metadata for a single file."""
        try:
            with self._retriever.get_file_stream(file_handle) as stream:
                return self._extractor.extract(file_handle, stream)
        except Exception as e:
            logger.error("Error processing %s: %s", file_handle.filename, e)
            raise

    def _db_writer_worker(
        self, db_queue: queue.Queue, tally: _Tally, reporter: ProgressReporter
    ) -> None:
        """Dedicated thread task to write metadata to the repository.

        Args:
            db_queue: Queue providing extracted ImageMetadata objects.
            tally: Shared success/failure counter feeding the report.
            reporter: ProgressReporter for unified metrics updates.
        """
        while True:
            item = db_queue.get()
            if item is _POISON_PILL:
                db_queue.task_done()
                break

            try:
                self._repository.save(item)
                tally.succeeded(item)
                reporter.update(1, metadata=item)
            except Exception as e:
                reporter.record_error("db_save_error")
                reporter.update(1)
                name = getattr(item.file_info, "name", "unknown")
                msg = f"Failed to save metadata for {name}: {e}"
                logger.error(msg)
                tally.failed(msg)
            finally:
                db_queue.task_done()
