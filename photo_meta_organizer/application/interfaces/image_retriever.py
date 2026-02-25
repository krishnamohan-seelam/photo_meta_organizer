"""Image retriever abstraction layer for storage-agnostic file discovery.

This module defines the interface for retrieving image files from various
storage backends (local disk, S3, FTP, etc.). By abstracting file discovery
behind a consistent interface, the system supports storage-agnostic metadata
extraction and indexing.

The retriever pattern follows the Strategy pattern combined with Protocol-based
structural typing, enabling:
- Lazy evaluation and memory-efficient processing of large datasets
- Stream-based access to files rather than loading full paths
- Pluggable implementations for different storage systems
- Dependency injection for testability and extensibility

Example:
    >>> retriever = LocalDiskRetriever(base_path="/path/to/photos")
    >>> for handle in retriever.list_files():
    ...     with retriever.get_file_stream(handle) as stream:
    ...         # Process the file stream
    ...         data = stream.read()
"""

from dataclasses import dataclass
from typing import BinaryIO, ContextManager, Generator, Protocol


@dataclass(frozen=True)
class RemoteFileHandle:
    """Metadata about a file before full download or processing.

    This value object represents lightweight metadata about a file discovered
    by a retriever, enabling lazy loading and efficient memory usage.

    Attributes:
        original_path: The full path or key identifying the file in storage.
        filename: The base filename or object key.
        size_bytes: The file size in bytes.
    """

    original_path: str
    filename: str
    size_bytes: int


class ImageRetriever(Protocol):
    """Protocol defining the contract for image file retrieval implementations.

    Implementations of this protocol are responsible for discovering and
    providing access to image files stored in various backends. The protocol
    uses structural typing (duck typing), allowing any class implementing
    these methods to be treated as an ImageRetriever.

    Methods:
        list_files: Discover all image files in the storage backend.
        get_file_stream: Retrieve a file stream for processing.
    """

    def list_files(self) -> Generator[RemoteFileHandle, None, None]:
        """Discover all files in the storage backend.

        Yields files lazily to support efficient processing of large datasets
        without loading everything into memory.

        Yields:
            RemoteFileHandle: Metadata for each discovered file.
        """
        ...

    def get_file_stream(
        self, file_handle: RemoteFileHandle
    ) -> ContextManager[BinaryIO]:
        """Retrieve a binary stream for a specific file.

        Args:
            file_handle: The file handle returned by list_files().

        Returns:
            A context manager that ensures proper resource cleanup.
            The context manager yields a BinaryIO stream for reading the file.

        Example:
            >>> with retriever.get_file_stream(handle) as stream:
            ...     content = stream.read()
        """
        ...
