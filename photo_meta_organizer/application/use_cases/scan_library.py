"""Scan a root: the one ingest pipeline, behind both ``index`` and ``sync`` (ADR-003 R4).

1. Discover the files under the root (the retriever).
2. Classify each path against the recorded Files by (size, mtime): NEW, MODIFIED,
   UNCHANGED or DELETED (``MetadataStateAnalyzer``, pure).
3. Hash and extract NEW and MODIFIED files on a thread pool.
4. Write the results in batches from one writer thread, behind a bounded queue.

Bookkeeping that needs no file reads (flagging missing Files, recording fresh
fingerprints, removing missing Files when asked) is done by the calling thread.
"""

import logging
import os
import queue
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path, PurePath
from typing import NamedTuple

from photo_meta_organizer.application.interfaces import (
    ImageMetadataExtractor,
    ImageMetadataRepository,
    ImageRetriever,
    RemoteFileHandle,
)
from photo_meta_organizer.application.interfaces.image_retriever import RootUnavailableError
from photo_meta_organizer.application.interfaces.progress import NullProgress, ProgressSink
from photo_meta_organizer.domain.datetimes import utc_now_naive
from photo_meta_organizer.domain.hashing import sha256_of_stream
from photo_meta_organizer.domain.models import FileInfo, FileState, ImageMetadata, SyncResult
from photo_meta_organizer.domain.services import MetadataStateAnalyzer

__all__ = ["RootUnavailableError", "ScanLibrary", "ScanOptions"]

logger = logging.getLogger(__name__)

_DONE = object()  # tells the writer thread to finish


@dataclass(frozen=True)
class ScanOptions:
    """What a scan does besides recording new and changed files.

    Attributes:
        remove_missing: Remove the Files the scan did not find (an Asset goes with its
            last File). Off by default: they are kept and flagged missing.
        rehash: Hash every recorded File instead of trusting its (size, mtime)
            fingerprint. Slow, but the only way to catch an edit that kept both.
        reextract: Re-extract every recorded File, not just the changed ones (counted
            as modified; curation is kept). Repairs records from older extractors.
        dry_run: Classify and count; read no file contents and write nothing.
        workers: Threads hashing and extracting files.
        index_new: Record files not seen before.
        reprocess_modified: Re-extract files whose content changed.
    """

    remove_missing: bool = False
    rehash: bool = False
    reextract: bool = False
    dry_run: bool = False
    workers: int = 4
    index_new: bool = True
    reprocess_modified: bool = True


class _Fingerprint(NamedTuple):
    path: str
    size_bytes: int
    modified_time: datetime


@dataclass(frozen=True)
class _Parts:
    """What one run works with (the scan's collaborators, passed on explicitly)."""

    retriever: ImageRetriever
    extractor: ImageMetadataExtractor
    repository: ImageMetadataRepository
    reporter: ProgressSink
    batch_size: int


class ScanLibrary:
    """Use case: bring the library in line with what is on disk under a root."""

    def __init__(
        self,
        retriever: ImageRetriever,
        extractor: ImageMetadataExtractor,
        repository: ImageMetadataRepository,
        analyzer: MetadataStateAnalyzer | None = None,
        progress_reporter: ProgressSink | None = None,
        batch_size: int = 100,
    ) -> None:
        """Initialise with injected dependencies.

        Args:
            retriever: Lists the root's files and opens them.
            extractor: Stateless metadata extractor (safe to share across threads).
            repository: Where Assets and Files are recorded.
            analyzer: Change classifier (a default instance if ``None``).
            progress_reporter: Console-style progress output (the CLI passes the tqdm
                reporter); silent by default.
            batch_size: Most records the writer thread saves in one write.
        """
        self._retriever = retriever
        self._repository = repository
        self._analyzer = analyzer or MetadataStateAnalyzer()
        self._parts = _Parts(
            retriever=retriever,
            extractor=extractor,
            repository=repository,
            reporter=progress_reporter or NullProgress(),
            batch_size=max(1, batch_size),
        )

    def execute(
        self,
        options: ScanOptions | None = None,
        scope_root: str | None = None,
        progress: Callable[[int, int], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> SyncResult:
        """Scan once and report what changed.

        Args:
            options: What to do besides recording new and changed files.
            scope_root: The folder the retriever lists. Only Files under it take part,
                so a File elsewhere in the library is never taken for missing. ``None``
                compares against every recorded File, which is only right when the
                retriever covers all of them. A root that cannot be read raises
                :class:`RootUnavailableError`.
            progress: Called with (done, total) as file states are dealt with.
            should_cancel: Polled before the analysis, before each extraction is started
                and before each removal. Work already in hand is still saved, and
                ``result.cancelled`` is set.

        Returns:
            What the scan found and did (counts, per-file errors, duration).

        Raises:
            RootUnavailableError: The retriever's root cannot be read; nothing changed.
        """
        options = options or ScanOptions()
        cancelled = should_cancel or (lambda: False)
        start = time.monotonic()
        result = SyncResult()
        logger.info("Starting scan of %s with %s", scope_root or "the library", options)

        file_states = self._classify(options, scope_root)
        if file_states is None or cancelled():
            result.cancelled = True
            result.duration_seconds = time.monotonic() - start
            return result

        if options.dry_run:
            self._count_dry_run(file_states, options, result)
        else:
            _Run(self._parts, options, result, progress, cancelled).apply(file_states)

        result.duration_seconds = time.monotonic() - start
        logger.info(
            "Scan %s in %.2fs: +%d new, ~%d modified, -%d removed, %d missing, %d unchanged, "
            "%d error(s)",
            "cancelled" if result.cancelled else "complete",
            result.duration_seconds,
            result.new_files,
            result.modified_files,
            result.deleted_entries,
            result.missing_files,
            result.unchanged_files,
            len(result.errors),
        )
        return result

    # ------------------------------------------------------------------
    # Discover and classify
    # ------------------------------------------------------------------

    def _classify(self, options: ScanOptions, scope_root: str | None) -> list[FileState] | None:
        # A root that cannot be read would list as empty and make every File under it
        # look missing: fail instead, before anything is flagged or removed.
        self._retriever.check_readable()
        # Size and mtime come from the retriever's own listing (PMO-22): no second stat.
        disk_files = {
            handle.original_path: FileInfo(
                path=handle.original_path,
                size_bytes=handle.size_bytes,
                modified_time=handle.modified_time,
            )
            for handle in self._retriever.list_files()
        }
        self._retriever.check_readable()  # still there: not unplugged half-way through
        logger.info("Disk scan complete: %d files found", len(disk_files))

        recorded = self._repository.list_files()
        if scope_root is not None:
            recorded = [f for f in recorded if _within(f.path, scope_root)]
        skipped = self._retriever.skipped_paths()
        if skipped:
            # Not looked at is not missing: Files the listing could not reach stay as they are.
            logger.warning("%d folder(s) or file(s) could not be read", len(skipped))
            recorded = [f for f in recorded if not any(_within(f.path, s) for s in skipped)]

        file_states = self._analyzer.analyze_changes(
            disk_files=disk_files,
            db_entries=recorded,
            compute_hash=self._hash_file,
            force_rehash=options.rehash,
            normalise_path=_resolve,
        )
        file_states = self._skip_removed(file_states)
        if options.reextract:
            # Unchanged content is re-extracted in place: saving it under the same hash
            # updates the extracted columns and keeps the curation.
            file_states = [
                replace(fs, state="MODIFIED") if fs.state == "UNCHANGED" else fs
                for fs in file_states
            ]
        return file_states

    def _skip_removed(self, file_states: list[FileState]) -> list[FileState]:
        """Mark new files the user removed from the library as ``IGNORED``.

        A path counts only while the file still has the size and mtime it had when it was
        removed; otherwise its content changed and it is scanned like any new photo.
        """
        ignored = {_resolve(i.path): i for i in self._repository.list_ignored()}
        if not ignored:
            return file_states
        marked = []
        for fs in file_states:
            known = ignored.get(fs.file_path) if fs.state == "NEW" else None
            if (
                known is not None
                and known.size_bytes == fs.size_bytes
                and _same_time(known.modified_time, fs.last_modified)
            ):
                fs = replace(fs, state="IGNORED")
            marked.append(fs)
        return marked

    def _hash_file(self, path: str) -> str:
        """SHA-256 of ``path``, read through the retriever (so it works for any backend)."""
        with self._retriever.get_file_stream(_handle(path, 0)) as stream:
            return sha256_of_stream(stream)

    @staticmethod
    def _count_dry_run(
        file_states: list[FileState], options: ScanOptions, result: SyncResult
    ) -> None:
        def count(state: str) -> int:
            return sum(1 for fs in file_states if fs.state == state)

        result.new_files = count("NEW") if options.index_new else 0
        result.modified_files = count("MODIFIED") if options.reprocess_modified else 0
        result.unchanged_files = count("UNCHANGED")
        result.ignored_files = count("IGNORED")
        missing = count("DELETED")
        result.deleted_entries = missing if options.remove_missing else 0
        result.missing_files = 0 if options.remove_missing else missing
        result.found_again = sum(1 for fs in file_states if fs.found_again)
        result.fingerprints_refreshed = sum(1 for fs in file_states if fs.refresh_fingerprint)


class _Run:
    """One scan's writes: bookkeeping on the calling thread, extraction on the pool.

    Order matters: new and changed files are saved before missing ones are removed, so
    a file moved within the root gains its new File before its old one goes, and its
    Asset (with the curation) survives.
    """

    def __init__(
        self,
        parts: _Parts,
        options: ScanOptions,
        result: SyncResult,
        progress: Callable[[int, int], None] | None,
        cancelled: Callable[[], bool],
    ) -> None:
        self._parts = parts
        self._options = options
        self._result = result
        self._progress = progress
        self._cancelled = cancelled
        self._lock = threading.Lock()  # the result and the progress count are shared
        self._done = 0
        self._total = 0

    def apply(self, file_states: list[FileState]) -> None:
        self._total = len(file_states)
        to_extract: list[FileState] = []
        to_remove: list[str] = []
        stale: list[_Fingerprint] = []
        missing: list[str] = []
        found_again: list[str] = []

        for fs in file_states:
            path = fs.recorded_path or fs.file_path
            if fs.found_again:
                self._result.found_again += 1
                found_again.append(path)
            if fs.state == "UNCHANGED":
                self._result.unchanged_files += 1
                if fs.refresh_fingerprint and fs.last_modified:
                    stale.append(_Fingerprint(path, fs.size_bytes or 0, fs.last_modified))
            elif fs.state == "IGNORED":
                self._result.ignored_files += 1
            elif fs.state == "DELETED" and self._options.remove_missing:
                to_remove.append(path)
                continue  # counted when it is removed
            elif fs.state == "DELETED":
                missing.append(path)
            elif (fs.state == "NEW" and self._options.index_new) or (
                fs.state == "MODIFIED" and self._options.reprocess_modified
            ):
                to_extract.append(fs)
                continue  # counted when it is saved
            self._tick()

        self._extract_all(to_extract)
        if not self._result.cancelled:
            self._remove_all(to_remove)
        self._record(stale, missing, found_again)

    def _tick(self) -> None:
        with self._lock:
            self._done += 1
            if self._progress is None:
                return
            try:  # under the lock, so (done, total) never arrives out of order
                self._progress(self._done, self._total)
            except Exception:  # noqa: BLE001 - a broken observer must not stop the scan
                logger.exception("Scan progress callback failed")

    def _error(self, message: str) -> None:
        logger.error(message)
        with self._lock:
            self._result.errors.append(message)

    def _fail(self, message: str, error_type: str) -> None:
        """One file could not be recorded: report it and count it as dealt with."""
        self._parts.reporter.record_error(error_type)
        self._parts.reporter.update(1)
        self._error(message)
        self._tick()

    def _remove_all(self, paths: list[str]) -> None:
        for path in paths:
            if self._cancelled():
                self._result.cancelled = True
                return
            try:
                if self._parts.repository.delete_by_path(path):
                    self._result.deleted_entries += 1
                else:
                    logger.warning("Could not remove %s: not in the library", path)
            except Exception as exc:  # noqa: BLE001
                self._error(f"delete error: {path}: {exc}")
            self._tick()

    def _record(
        self, stale: list[_Fingerprint], missing: list[str], found_again: list[str]
    ) -> None:
        """Fingerprints and missing flags, each in one batched write."""
        repository = self._parts.repository
        try:
            if stale:
                self._result.fingerprints_refreshed = repository.refresh_fingerprints(
                    [(f.path, f.size_bytes, f.modified_time) for f in stale]
                )
        except Exception as exc:  # noqa: BLE001
            self._error(f"fingerprint refresh error: {exc}")
        try:
            repository.set_missing(missing, utc_now_naive())
            repository.set_missing(found_again, None)
            self._result.missing_files = len(missing)
        except Exception as exc:  # noqa: BLE001
            self._error(f"missing-file flag error: {exc}")

    # ------------------------------------------------------------------
    # Extraction pool and writer thread
    # ------------------------------------------------------------------

    def _extract_all(self, file_states: list[FileState]) -> None:
        if not file_states:
            return
        workers = max(1, self._options.workers)
        self._parts.reporter.start(total=len(file_states), desc="Scanning")
        results: queue.Queue = queue.Queue(maxsize=100)
        writer = threading.Thread(target=self._write_all, args=(results,), daemon=True)
        writer.start()
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                self._run_pool(pool, workers, iter(file_states), results)
        finally:
            results.put(_DONE)
            writer.join()
            self._parts.reporter.stop()

    def _run_pool(
        self,
        pool: ThreadPoolExecutor,
        workers: int,
        pending: Iterator[FileState],
        results: queue.Queue,
    ) -> None:
        """Keep a small window of extractions in flight, so a cancel stops within it."""
        in_flight: dict[Future, FileState] = {}
        exhausted = False
        while True:
            while not exhausted and len(in_flight) < workers * 2:
                if self._cancelled():
                    self._result.cancelled = True
                    exhausted = True
                    break
                fs = next(pending, None)
                if fs is None:
                    exhausted = True
                    break
                in_flight[pool.submit(self._extract, fs)] = fs
            if not in_flight:
                return
            finished, _ = wait(in_flight, return_when=FIRST_COMPLETED)
            for future in finished:
                fs = in_flight.pop(future)
                try:
                    results.put((fs, future.result()))
                except Exception as exc:  # noqa: BLE001
                    self._fail(_extract_error(fs, exc), type(exc).__name__)

    def _extract(self, fs: FileState) -> ImageMetadata:
        """Read one file (on a pool thread) and return what to record for it."""
        handle = _handle(fs.file_path, fs.size_bytes or 0, fs.last_modified)
        with self._parts.retriever.get_file_stream(handle) as stream:
            metadata = self._parts.extractor.extract(handle, stream)
        if metadata is None:
            raise _NothingExtracted(fs.file_path)
        file_info = metadata.file_info
        if fs.recorded_path is not None:
            # Write to the File the analyzer matched, however its path was recorded, so
            # an edit repoints that File instead of adding a second one.
            file_info = replace(file_info, path=fs.recorded_path)
        if fs.last_modified is not None:
            # The mtime the analyzer saw, so the next scan compares like with like.
            file_info = replace(file_info, modified_time=fs.last_modified)
        return replace(metadata, file_info=file_info)

    def _write_all(self, results: queue.Queue) -> None:
        """The writer thread: saves whatever has arrived, up to a batch at a time.

        It never stops before ``_DONE``, whatever a batch raises, so the pool can never
        block on a full queue.
        """
        finished = False
        while not finished:
            batch = [results.get()]
            while len(batch) < self._parts.batch_size:
                try:
                    batch.append(results.get_nowait())
                except queue.Empty:
                    break
            if batch[-1] is _DONE:  # always the last item queued
                batch.pop()
                finished = True
            try:
                self._write(batch)
            except Exception as exc:  # noqa: BLE001 - keep draining the queue
                self._error(f"writer error: {exc}")

    def _write(self, batch: list[tuple[FileState, ImageMetadata]]) -> None:
        if not batch:
            return
        repository = self._parts.repository
        try:
            repository.save_many([metadata for _, metadata in batch])
            saved = batch
        except Exception:  # noqa: BLE001 - find the record at fault, save the others
            saved = []
            for fs, metadata in batch:
                try:
                    repository.save(metadata)
                    saved.append((fs, metadata))
                except Exception as exc:  # noqa: BLE001
                    self._fail(f"save error [{fs.state}]: {fs.file_path}: {exc}", "db_save_error")
        for fs, metadata in saved:
            with self._lock:
                if fs.state == "NEW":
                    self._result.new_files += 1
                else:
                    self._result.modified_files += 1
            self._parts.reporter.update(1, metadata=metadata)
            self._tick()


class _NothingExtracted(Exception):
    """The extractor returned no record for a file."""


def _extract_error(fs: FileState, exc: Exception) -> str:
    if isinstance(exc, FileNotFoundError):
        return f"race-condition (file disappeared): {fs.file_path}"
    if isinstance(exc, _NothingExtracted):
        return f"no metadata extracted: {fs.file_path}"
    return f"extract error [{fs.state}]: {fs.file_path}: {exc}"


def _handle(path: str, size_bytes: int, modified_time: datetime | None = None) -> RemoteFileHandle:
    return RemoteFileHandle(
        original_path=path,
        filename=PurePath(path).name,
        size_bytes=size_bytes,
        modified_time=modified_time,
    )


def _resolve(path: str) -> str:
    """The path both sides of a scan are compared in: absolute, symlinks and case resolved."""
    return str(Path(path).resolve())


def _within(path: str, root: str) -> bool:
    """True if ``path`` is ``root`` or inside it (case-insensitive where the OS is)."""
    p = os.path.normcase(str(Path(path).resolve()))
    r = os.path.normcase(str(Path(root).resolve()))
    try:
        return os.path.commonpath([p, r]) == r
    except ValueError:  # different drives
        return False


def _same_time(a: datetime | None, b: datetime | None) -> bool:
    """Whether two modification times are the same, to the second (file systems differ)."""
    if a is None or b is None:
        return a is b
    return abs((a - b).total_seconds()) < 1
