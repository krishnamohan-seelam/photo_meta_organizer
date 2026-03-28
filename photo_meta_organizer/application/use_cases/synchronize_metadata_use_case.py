"""Synchronize Metadata use case — incremental metadata sync pipeline.

This use case orchestrates the metadata synchronization workflow:
1. Scan disk to discover current files
2. Load all DB entries
3. Analyse changes (NEW / MODIFIED / UNCHANGED / DELETED)
4. Apply changes selectively based on flags
5. Return a SyncResult summary

It replaces the expensive full-reindex "index" command for incremental updates,
allowing users to run fast, change-aware synchronization after the initial import.

Example:
    >>> use_case = SynchronizeMetadataUseCase(
    ...     retriever=LocalDiskRetriever(base_path="/photos"),
    ...     extractor=DiskMetaDataExtractor(),
    ...     repository=TinyDBRepository(db_path="metadata.json"),
    ... )
    >>> result = use_case.execute(cleanup_deleted=True, reprocess_modified=True, index_new=True)
    >>> print(result)
    SyncResult(new=12, modified=5, deleted=3, unchanged=8542)
"""

import logging
import time
from pathlib import Path
from datetime import datetime

from photo_meta_organizer.application.interfaces import (
    ImageMetadataExtractor,
    ImageMetadataRepository,
    ImageRetriever,
)
from photo_meta_organizer.domain.models import FileInfo, SyncResult
from photo_meta_organizer.domain.services import MetadataStateAnalyzer
from photo_meta_organizer.application.orchestrators import SyncOrchestrator

logger = logging.getLogger(__name__)


class SynchronizeMetadataUseCase:
    """Use case: incrementally sync metadata DB with actual disk state.

    Orchestrates the full sync pipeline by composing:
    - ImageRetriever → discovery of current disk files
    - MetadataStateAnalyzer → change detection (pure domain logic)
    - SyncOrchestrator → applying changes (extract + persist + delete)

    Selective sync flags let you run targeted operations:
    - ``cleanup_deleted=True`` : Remove orphaned DB entries
    - ``reprocess_modified=True``: Re-extract and update modified files
    - ``index_new=True``       : Extract + insert brand-new files

    Attributes:
        _retriever: Discovers files and provides file streams.
        _extractor: Stateless metadata extractor.
        _repository: Persistent storage backend.
        _analyzer: Pure domain service for change detection.
        _sync_orchestrator: Coordinates retrieve → extract → persist/delete.
    """

    def __init__(
        self,
        retriever: ImageRetriever,
        extractor: ImageMetadataExtractor,
        repository: ImageMetadataRepository,
        analyzer: MetadataStateAnalyzer | None = None,
    ) -> None:
        """Initialise with injected dependencies.

        Args:
            retriever: Storage backend for file discovery and streaming.
            extractor: Stateless metadata extractor.
            repository: Persistence backend for extracted metadata.
            analyzer: Optional MetadataStateAnalyzer (default instance used if None).
        """
        self._retriever = retriever
        self._extractor = extractor
        self._repository = repository
        self._analyzer = analyzer or MetadataStateAnalyzer()
        self._sync_orchestrator = SyncOrchestrator(
            retriever=retriever,
            extractor=extractor,
            repository=repository,
        )

    def execute(
        self,
        cleanup_deleted: bool = False,
        reprocess_modified: bool = True,
        index_new: bool = True,
        dry_run: bool = False,
    ) -> SyncResult:
        """Run the incremental metadata synchronization pipeline.

        Flow:
            1. Scan disk → build (path → FileInfo) map
            2. Load all DB entries
            3. Analyze changes → list of FileState objects
            4. Apply changes (respecting flags and dry_run mode)
            5. Return SyncResult summary

        Args:
            cleanup_deleted: If True, remove DB entries for files no longer on disk.
                             Default False (safer — prevents accidental data loss).
            reprocess_modified: If True, re-extract metadata for modified files.
                                 Default True.
            index_new: If True, extract and insert metadata for new files.
                       Default True.
            dry_run: If True, analyze and log but do NOT write any changes.
                     Useful for previewing what would happen. Default False.

        Returns:
            SyncResult summarising what was added, updated, deleted, and skipped.
        """
        start_time = time.monotonic()
        result = SyncResult()

        logger.info(
            "Starting metadata sync [cleanup_deleted=%s, reprocess_modified=%s, "
            "index_new=%s, dry_run=%s]",
            cleanup_deleted, reprocess_modified, index_new, dry_run,
        )

        # ------------------------------------------------------------------
        # Step 1: Scan disk
        # ------------------------------------------------------------------
        disk_files: dict[str, FileInfo] = {}
        for file_handle in self._retriever.list_files():
            path = Path(file_handle.original_path)
            try:
                stat = path.stat()
                fi = FileInfo(
                    path=str(path),
                    size_bytes=stat.st_size,
                    modified_time=datetime.fromtimestamp(stat.st_mtime),
                )
                disk_files[str(path)] = fi
            except OSError as exc:
                logger.warning("Cannot stat file %s: %s", path, exc)
                result.errors.append(f"stat error: {path}: {exc}")

        logger.info("Disk scan complete: %d files found", len(disk_files))

        # ------------------------------------------------------------------
        # Step 2: Load DB entries
        # ------------------------------------------------------------------
        db_entries = self._repository.list_all()
        logger.info("DB loaded: %d existing entries", len(db_entries))

        # ------------------------------------------------------------------
        # Step 3: Analyze changes
        # ------------------------------------------------------------------
        file_states = self._analyzer.analyze_changes(
            disk_files=disk_files,
            db_entries=db_entries,
        )

        counts = {"NEW": 0, "MODIFIED": 0, "UNCHANGED": 0, "DELETED": 0}
        for fs in file_states:
            counts[fs.state] += 1

        logger.info(
            "Change analysis: NEW=%d, MODIFIED=%d, UNCHANGED=%d, DELETED=%d",
            counts["NEW"], counts["MODIFIED"], counts["UNCHANGED"], counts["DELETED"],
        )
        result.unchanged_files = counts["UNCHANGED"]

        if dry_run:
            logger.info("Dry-run mode: no changes will be written")
            result.new_files = counts["NEW"] if index_new else 0
            result.modified_files = counts["MODIFIED"] if reprocess_modified else 0
            result.deleted_entries = counts["DELETED"] if cleanup_deleted else 0
            result.duration_seconds = time.monotonic() - start_time
            return result

        # ------------------------------------------------------------------
        # Step 4: Apply changes via SyncOrchestrator
        # ------------------------------------------------------------------
        sync_result = self._sync_orchestrator.sync(
            file_states=file_states,
            cleanup_deleted=cleanup_deleted,
            reprocess_modified=reprocess_modified,
            index_new=index_new,
        )

        # Merge orchestrator result into our result
        result.new_files = sync_result.new_files
        result.modified_files = sync_result.modified_files
        result.deleted_entries = sync_result.deleted_entries
        result.errors.extend(sync_result.errors)

        result.duration_seconds = time.monotonic() - start_time

        logger.info(
            "Sync complete in %.2fs: +%d new, ~%d modified, -%d deleted, %d unchanged, %d errors",
            result.duration_seconds,
            result.new_files,
            result.modified_files,
            result.deleted_entries,
            result.unchanged_files,
            len(result.errors),
        )
        return result
