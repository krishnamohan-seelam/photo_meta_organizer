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
import os
import time
from collections.abc import Callable
from pathlib import Path

from photo_meta_organizer.application.interfaces import (
    ImageMetadataExtractor,
    ImageMetadataRepository,
    ImageRetriever,
    RemoteFileHandle,
)
from photo_meta_organizer.application.orchestrators import SyncOrchestrator
from photo_meta_organizer.domain.hashing import sha256_of_stream
from photo_meta_organizer.domain.models import FileInfo, SyncResult
from photo_meta_organizer.domain.services import MetadataStateAnalyzer

logger = logging.getLogger(__name__)


def _resolve(path: str) -> str:
    """The path both sides of a sync are compared in: absolute, symlinks and case resolved."""
    return str(Path(path).resolve())


def _within(path: str, root: str) -> bool:
    """True if ``path`` is ``root`` or inside it (case-insensitive where the OS is)."""
    p = os.path.normcase(str(Path(path).resolve()))
    r = os.path.normcase(str(Path(root).resolve()))
    try:
        return os.path.commonpath([p, r]) == r
    except ValueError:  # different drives
        return False


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
        rehash: bool = False,
        scope_root: str | None = None,
        progress: Callable[[int, int], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
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
            rehash: If True, hash every file already in the DB instead of trusting
                    its (size, mtime) fingerprint. Slow (reads the whole library),
                    but the only way to catch an edit that kept both size and mtime.
            scope_root: The folder the retriever scans. Only DB records under it take
                    part, so a file elsewhere in the library is never classified as
                    DELETED (and removed by ``cleanup_deleted``) just because this scan
                    did not look there. ``None`` compares against the whole DB, which
                    is only safe when the retriever covers every indexed folder.
            progress: Called with (done, total) while changes are applied.
            should_cancel: Polled before the analysis and before each write; see
                    ``SyncOrchestrator.sync``. ``result.cancelled`` reports it.

        Returns:
            SyncResult summarising what was added, updated, deleted, and skipped.
        """
        start_time = time.monotonic()
        result = SyncResult()

        logger.info(
            "Starting metadata sync [cleanup_deleted=%s, reprocess_modified=%s, "
            "index_new=%s, dry_run=%s, rehash=%s]",
            cleanup_deleted, reprocess_modified, index_new, dry_run, rehash,
        )

        # ------------------------------------------------------------------
        # Step 1: Scan disk
        # ------------------------------------------------------------------
        # Size and mtime come from the retriever's own listing (PMO-22): no second
        # stat per file, and the use case works with any storage backend.
        disk_files: dict[str, FileInfo] = {
            handle.original_path: FileInfo(
                path=handle.original_path,
                size_bytes=handle.size_bytes,
                modified_time=handle.modified_time,
            )
            for handle in self._retriever.list_files()
        }

        logger.info("Disk scan complete: %d files found", len(disk_files))

        # ------------------------------------------------------------------
        # Step 2: Load DB entries
        # ------------------------------------------------------------------
        db_entries = self._repository.list_all()
        if scope_root is not None:
            db_entries = [e for e in db_entries if _within(e.file_info.path, scope_root)]
        logger.info("DB loaded: %d existing entries in scope", len(db_entries))

        if should_cancel is not None and should_cancel():
            result.cancelled = True
            result.duration_seconds = time.monotonic() - start_time
            return result

        # ------------------------------------------------------------------
        # Step 3: Analyze changes
        # ------------------------------------------------------------------
        file_states = self._analyzer.analyze_changes(
            disk_files=disk_files,
            db_entries=db_entries,
            compute_hash=self._hash_file,
            force_rehash=rehash,
            normalise_path=_resolve,
        )

        counts = {"NEW": 0, "MODIFIED": 0, "UNCHANGED": 0, "DELETED": 0}
        for fs in file_states:
            counts[fs.state] += 1

        logger.info(
            "Change analysis: NEW=%d, MODIFIED=%d, UNCHANGED=%d, DELETED=%d",
            counts["NEW"], counts["MODIFIED"], counts["UNCHANGED"], counts["DELETED"],
        )
        result.unchanged_files = counts["UNCHANGED"]
        stale = sum(1 for fs in file_states if fs.refresh_fingerprint)

        if dry_run:
            logger.info("Dry-run mode: no changes will be written")
            result.new_files = counts["NEW"] if index_new else 0
            result.modified_files = counts["MODIFIED"] if reprocess_modified else 0
            result.deleted_entries = counts["DELETED"] if cleanup_deleted else 0
            result.fingerprints_refreshed = stale
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
            progress=progress,
            should_cancel=should_cancel,
        )

        # Merge orchestrator result into our result
        result.new_files = sync_result.new_files
        result.modified_files = sync_result.modified_files
        result.deleted_entries = sync_result.deleted_entries
        result.fingerprints_refreshed = sync_result.fingerprints_refreshed
        result.errors.extend(sync_result.errors)
        result.cancelled = sync_result.cancelled

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

    def _hash_file(self, path: str) -> str:
        """Content hash of ``path``, read through the retriever with the shared helper."""
        handle = RemoteFileHandle(original_path=path, filename=Path(path).name, size_bytes=0)
        with self._retriever.get_file_stream(handle) as stream:
            return sha256_of_stream(stream)
