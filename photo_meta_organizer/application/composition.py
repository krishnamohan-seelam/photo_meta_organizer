"""Shared composition: the one place that decides which concrete classes to use.

The CLI (``main.py``) and the REST API both build their retrievers here, so they can
never disagree about what gets indexed (flaw B-05: the API used to index every file).
Concrete infrastructure is imported lazily inside the factories, so importing this
module stays cheap and the application layer keeps no import-time dependency on it.
"""

from photo_meta_organizer.application.interfaces import ImageRetriever
from photo_meta_organizer.domain.formats import IMAGE_EXTENSIONS


def build_local_retriever(path: str) -> ImageRetriever:
    """Create a retriever over a local directory that yields only image files.

    Raises:
        NotADirectoryError: If ``path`` is not an existing directory.
    """
    from photo_meta_organizer.infrastructure.retriever.filtered_retriever import (
        ExtensionFilteredRetriever,
    )
    from photo_meta_organizer.infrastructure.retriever.local_disk_retriever import (
        LocalDiskRetriever,
    )

    return ExtensionFilteredRetriever(LocalDiskRetriever(base_path=path), set(IMAGE_EXTENSIONS))
