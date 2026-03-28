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

from typing import List, Optional, Protocol, runtime_checkable

from photo_meta_organizer.domain.models import ImageMetadata


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
        find_by_paths: Retrieve multiple records by paths (for sync comparison).
        count: Return total number of stored records.
    """

    def save(self, metadata: ImageMetadata) -> None:
        """Persist image metadata to storage.

        Args:
            metadata: The ImageMetadata entity to store.

        Raises:
            IOError: If the metadata cannot be persisted.
            ValueError: If the metadata is invalid or incomplete.

        Note:
            Implementations should handle upsert semantics (update if exists).
        """
        ...

    def get_by_filehash(self, file_hash: str) -> Optional[ImageMetadata]:
        """Retrieve metadata by file hash (for duplicate detection).

        Args:
            file_hash: The MD5 or SHA256 hash of the file.

        Returns:
            ImageMetadata if found, None otherwise.
        """
        ...

    def get_by_path(self, file_path: str) -> Optional[ImageMetadata]:
        """Retrieve metadata by file path.

        Args:
            file_path: The original file path or key.

        Returns:
            ImageMetadata if found, None otherwise.
        """
        ...

    def list_all(self) -> List[ImageMetadata]:
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
        """Delete metadata by file path (for deleted-file cleanup).

        Args:
            file_path: The original file path of the record to delete.

        Returns:
            True if a record was deleted, False if not found.
        """
        ...

    def find_by_paths(self, paths: List[str]) -> List[ImageMetadata]:
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
