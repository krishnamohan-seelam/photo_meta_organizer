"""Local file system implementation of image file retrieval.

This module provides a concrete implementation of the ImageRetriever protocol
for discovering and accessing image files stored on the local file system.
Supports recursive directory traversal for comprehensive file discovery.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Generator

from photo_meta_organizer.application.interfaces.image_retriever import (
    ImageRetriever,
    RemoteFileHandle,
)


class LocalDiskRetriever:
    """Retrieves image files from the local file system.

    This class implements the ImageRetriever protocol to discover and stream
    image files from a directory tree on the local disk. It supports recursive
    directory traversal to find all images within a specified base path.

    The implementation uses pathlib for cross-platform compatibility and
    lazy evaluation via generators for memory efficiency.

    Attributes:
        base_path: The root directory path to search for image files.

    Raises:
        NotADirectoryError: If the provided base_path is not a valid directory.

    Example:
        >>> retriever = LocalDiskRetriever("/path/to/photos")
        >>> for file_handle in retriever.list_files():
        ...     with retriever.get_file_stream(file_handle) as stream:
        ...         data = stream.read()
    """

    def __init__(self, base_path: str) -> None:
        """Initialize the local disk retriever.

        Args:
            base_path: The root directory to search for image files.

        Raises:
            NotADirectoryError: If base_path does not exist or is not a directory.
        """
        self._base_path = Path(base_path)
        if not self._base_path.is_dir():
            raise NotADirectoryError(f"{base_path} is not a valid directory.")

    def list_files(self) -> Generator[RemoteFileHandle, None, None]:
        """Discover all files in the directory tree.

        Recursively traverses the base path and yields metadata for all files
        found. Uses lazy evaluation to minimize memory usage.

        Yields:
            RemoteFileHandle: Metadata for each discovered file.
        """
        for path in self._base_path.rglob("*"):
            if path.is_file():
                yield RemoteFileHandle(
                    original_path=str(path),
                    filename=path.name,
                    size_bytes=path.stat().st_size,
                )

    @contextmanager
    def get_file_stream(
        self, file_handle: RemoteFileHandle
    ) -> Generator[BinaryIO, None, None]:
        """Retrieve a binary stream for a specific file.

        Args:
            file_handle: The file handle returned by list_files().

        Yields:
            A binary stream from which the file contents can be read.

        Example:
            >>> with retriever.get_file_stream(handle) as stream:
            ...     content = stream.read()
        """
        file_path = Path(file_handle.original_path)
        with file_path.open("rb") as f:
            yield f
