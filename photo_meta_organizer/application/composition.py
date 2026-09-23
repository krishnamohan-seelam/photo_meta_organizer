"""Shared composition: the one place that decides which concrete classes to use.

The CLI (``main.py``) and the REST API both build their retrievers *and* their
repositories here, so they can never disagree about what gets indexed (flaw B-05:
the API used to index every file) or which storage engine backs a given ``--db``
path (PMO-08: SQLite behind the repository port, per ADR-001). Concrete
infrastructure is imported lazily inside the factories, so importing this module
stays cheap and the application layer keeps no import-time dependency on it.
"""

import logging
import os

from photo_meta_organizer.application.interfaces import ImageRetriever
from photo_meta_organizer.application.interfaces.collection_repository import (
    CollectionRepository,
)
from photo_meta_organizer.application.interfaces.image_repository import (
    ImageMetadataRepository,
)
from photo_meta_organizer.domain.formats import IMAGE_EXTENSIONS

logger = logging.getLogger(__name__)


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

    return ExtensionFilteredRetriever(
        LocalDiskRetriever(base_path=path), set(IMAGE_EXTENSIONS)
    )


def _is_legacy_json(db_path: str) -> bool:
    """True if ``db_path`` names an existing file that is (or was) a TinyDB JSON store.

    A brand-new path (nothing on disk yet) is never legacy: it becomes a fresh
    SQLite database. Only ``.json`` paths that already exist trigger an import,
    so a ``.db``/``.sqlite`` path is always opened directly as SQLite even if
    it does not exist yet.
    """
    return db_path.endswith(".json") and os.path.exists(db_path)


def build_repository(db_path: str) -> ImageMetadataRepository:
    """Build the repository for ``db_path`` (ADR-001: SQLite behind the port).

    An existing legacy ``.json`` file is imported once into a sibling ``.db``
    file (never modified itself); the returned repository is the SQLite one
    over that imported file. Any other path opens (or creates) a SQLite
    database directly.
    """
    from photo_meta_organizer.infrastructure.repositories.sqlite_repository import (
        SqliteRepository,
    )

    if _is_legacy_json(db_path):
        sqlite_path = os.path.splitext(db_path)[0] + ".db"
        if not os.path.exists(sqlite_path):
            from photo_meta_organizer.infrastructure.importers.legacy_json_importer import (
                import_legacy_json,
            )

            result = import_legacy_json(db_path, sqlite_path)
            logger.info(
                "Imported legacy database %s -> %s (%s photo(s), %s error(s))",
                db_path,
                sqlite_path,
                result.imported_count,
                len(result.errors),
            )
        return SqliteRepository(db_path=sqlite_path)

    return SqliteRepository(db_path=db_path)


def build_collection_repository(
    repository: ImageMetadataRepository,
) -> CollectionRepository:
    """Build the collection repository sharing storage with ``repository``.

    ``repository`` must be one built by :func:`build_repository`, since the
    collection repository shares its connection/handle rather than opening the
    file a second time.
    """
    from photo_meta_organizer.infrastructure.repositories.sqlite_collection_repository import (
        SqliteCollectionRepository,
    )
    from photo_meta_organizer.infrastructure.repositories.sqlite_repository import (
        SqliteRepository,
    )

    if isinstance(repository, SqliteRepository):
        return SqliteCollectionRepository(repository.connection, repository.lock)
    raise TypeError(
        f"unsupported repository type for collections: {type(repository)!r}"
    )
