"""Decorator for filtering image files by extension.

This module provides a wrapper that adds file extension filtering to any
ImageRetriever implementation. It's an example of the Decorator pattern
in action, allowing composition of retriever capabilities.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Generator

from photo_meta_organizer.application.interfaces.image_retriever import (
    ImageRetriever,
    RemoteFileHandle,
)


class ExtensionFilteredRetriever:
    """Wraps any ImageRetriever to filter files by extension.

    This decorator adds filtering capability to existing retriever
    implementations without modifying their code. It implements the
    ImageRetriever protocol, allowing transparent composition.

    Attributes:
        retriever: The underlying ImageRetriever to wrap.
        extensions: Set of file extensions to include (case-insensitive).

    Example:
        >>> base_retriever = LocalDiskRetriever("/path/to/photos")
        >>> filtered = ExtensionFilteredRetriever(
        ...     base_retriever, {".jpg", ".png", ".gif"}
        ... )
        >>> for handle in filtered.list_files():
        ...     print(handle.filename)
    """

    def __init__(self, retriever: ImageRetriever, extensions: set[str]) -> None:
        """Initialize the filtered retriever.

        Args:
            retriever: The underlying ImageRetriever to wrap.
            extensions: File extensions to include (e.g., {".jpg", ".png"}).
                       Extensions are normalized to lowercase.

        Raises:
            ValueError: If extensions set is empty.
        """
        if not extensions:
            raise ValueError("extensions set cannot be empty")
        self._retriever = retriever
        self._extensions = {ext.lower() for ext in extensions}

    def list_files(self) -> Generator[RemoteFileHandle, None, None]:
        """Discover files matching the configured extensions.

        Delegates to the underlying retriever and yields only those files
        whose extensions are in the configured set.

        Yields:
            RemoteFileHandle: Metadata for files matching the extension filter.
        """
        for handle in self._retriever.list_files():
            if Path(handle.filename).suffix.lower() in self._extensions:
                yield handle

    @contextmanager
    def get_file_stream(
        self, file_handle: RemoteFileHandle
    ) -> Generator[BinaryIO, None, None]:
        """Retrieve a file stream from the underlying retriever.

        Args:
            file_handle: The file handle returned by list_files().

        Yields:
            A binary stream for reading the file contents.

        Note:
            This method delegates directly to the underlying retriever
            without modification.
        """
        with self._retriever.get_file_stream(file_handle) as stream:
            yield stream
