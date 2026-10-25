"""Image metadata repository interface for persistent storage.

This module defines the contract for persisting and retrieving image metadata.
By using a Protocol-based interface, different storage backends (database,
file system, cloud storage, etc.) can be plugged in transparently.

The repository pattern provides:
- Abstraction of storage details from business logic
- Consistent interface for CRUD operations on metadata
- Transaction and consistency guarantees
- Query capabilities for metadata
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from photo_meta_organizer.application.interfaces.search_types import (
    BoundingBox,
    DuplicatePage,
    Facets,
    GeoCluster,
    Page,
    SearchQuery,
)
from photo_meta_organizer.domain.curation import CurationCommand
from photo_meta_organizer.domain.models import ImageMetadata, StoredFile


@runtime_checkable
class ImageMetadataRepository(Protocol):
    """Protocol defining the contract for image metadata persistence.

    Implementations of this protocol handle storing and retrieving image
    metadata. The protocol uses structural typing, allowing any class
    implementing these methods to be treated as an ImageMetadataRepository.

    Methods:
        save: Persist metadata for an image.
        get_by_filehash: Retrieve metadata by file hash.
        get_by_path: Retrieve metadata by file path.
        list_all: Retrieve all stored metadata.
        delete: Remove metadata by file hash.
        delete_by_path: Remove metadata by file path (for deleted-file cleanup).
        find_by_paths: Retrieve the records held at several paths.
        list_files: Every recorded File with its fingerprint (for sync comparison).
        count: Return total number of stored records.
    """

    def save_many(self, items: Sequence[ImageMetadata]) -> None:
        """Upsert many records in one batch (one write, one index rebuild).

        Used by parallel indexing so a run of N files costs one storage write,
        not N.
        """
        ...

    def query(self, query: SearchQuery) -> Page[ImageMetadata]:
        """Filter, sort, and page records entirely inside the repository.

        Replaces the old pattern of ``list_all()`` followed by Python-side
        filtering: an implementation may use whatever index or SQL query is
        appropriate, so a single page of results never requires deserializing
        the whole store.
        """
        ...

    def facets(self) -> Facets:
        """Return aggregate counts (cameras, tags, years, GPS bounds) for filter UIs."""
        ...

    def geo_clusters(
        self, query: SearchQuery, bbox: BoundingBox | None, cell_degrees: float
    ) -> list[GeoCluster]:
        """Group the geotagged records matching ``query`` into square grid cells.

        Only the filters of ``query`` apply (paging, sort and the radius filter are
        ignored); ``bbox`` restricts the result to a map viewport.
        """
        ...

    def apply(self, file_hash: str, command: CurationCommand) -> ImageMetadata | None:
        """Apply one typed curation command to a single record.

        Returns:
            The updated record, or ``None`` if ``file_hash`` does not exist.
        """
        ...

    def apply_batch(self, file_hashes: Sequence[str], command: CurationCommand) -> int:
        """Apply one typed curation command to many records.

        Returns:
            The number of existing records the command was applied to. Unknown
            hashes are skipped.
        """
        ...

    def batch_delete(self, file_hashes: Sequence[str]) -> int:
        """Delete many records by hash. Returns the number actually deleted."""
        ...

    def save(self, metadata: ImageMetadata, *, overwrite_curation: bool = False) -> None:
        """Persist image metadata to storage.

        Args:
            metadata: The ImageMetadata entity to store.
            overwrite_curation: Also replace the stored curation with the record's.

        Raises:
            IOError: If the metadata cannot be persisted.
            ValueError: If the metadata is invalid or incomplete.

        Note:
            Implementations should handle upsert semantics (update if exists). An
            existing record keeps its curation (rating, flagged, labels, added_at)
            unless ``overwrite_curation`` is true: extraction never writes curation.
            The record's path becomes one of the Asset's Files. If that path held other
            content before (an edit), it now holds this one, and the old content's
            curation is carried over: moved if no other File holds the old content,
            copied if one does (ADR-003 R3).
        """
        ...

    def refresh_fingerprints(self, updates: Sequence[tuple[str, int, datetime]]) -> int:
        """Record ``(path, size_bytes, modified_time)`` on existing Files.

        Sync bookkeeping only; nothing else changes. Returns the number of Files
        updated (unknown paths are skipped).
        """
        ...

    def set_missing(self, paths: Sequence[str], since: datetime | None) -> int:
        """Flag the Files at ``paths`` as missing since ``since``; ``None`` clears the flag.

        A File already flagged keeps the time it first went missing. Returns the number
        of Files updated (unknown paths are skipped).
        """
        ...

    def list_files(self) -> list[StoredFile]:
        """Every File the library has recorded, one per path (what a scan compares).

        An Asset held at several paths appears once per path.
        """
        ...

    def files_of(self, file_hashes: Sequence[str]) -> dict[str, list[StoredFile]]:
        """Every File of each Asset, primary first (a present File, then the latest seen).

        Hashes the library does not know are absent from the result. One query for all.
        """
        ...

    def duplicate_groups(self, limit: int, offset: int = 0) -> DuplicatePage:
        """Assets with more than one copy (on disk, not hidden), biggest saving first."""
        ...

    def set_file_hidden(self, path: str, hidden: bool) -> bool:
        """Hide or show one File as a copy. It stays recorded; nothing on disk changes.

        Returns False if ``path`` is not a recorded File.
        """
        ...

    def get_by_filehash(self, file_hash: str) -> ImageMetadata | None:
        """Retrieve metadata by file hash (for duplicate detection).

        Args:
            file_hash: The MD5 or SHA256 hash of the file.

        Returns:
            ImageMetadata if found, None otherwise.
        """
        ...

    def get_by_path(self, file_path: str) -> ImageMetadata | None:
        """Retrieve metadata by file path.

        Args:
            file_path: The original file path or key.

        Returns:
            ImageMetadata if found, None otherwise.
        """
        ...

    def list_all(self) -> list[ImageMetadata]:
        """Retrieve all stored image metadata.

        Returns:
            A list of all ImageMetadata entities in storage.

        Note:
            For large datasets, consider implementing pagination or
            streaming to avoid memory issues.
        """
        ...

    def delete(self, file_hash: str) -> bool:
        """Delete metadata by file hash.

        Args:
            file_hash: SHA-256 hash of the record to delete.

        Returns:
            True if a record was deleted, False if not found.
        """
        ...

    def delete_by_path(self, file_path: str) -> bool:
        """Forget the File at ``file_path`` (sync's ``--cleanup-deleted``).

        The Asset is deleted with it only when no other File holds it.

        Args:
            file_path: The path of the File to forget.

        Returns:
            True if a File was forgotten, False if the path is unknown.
        """
        ...

    def find_by_paths(self, paths: list[str]) -> list[ImageMetadata]:
        """Find multiple records by their file paths.

        Args:
            paths: List of file paths to look up.

        Returns:
            List of ImageMetadata matching the provided paths.
            Paths with no match are silently skipped.
        """
        ...

    def count(self) -> int:
        """Return the total number of stored records.

        Returns:
            Integer count of all records in storage.
        """
        ...
