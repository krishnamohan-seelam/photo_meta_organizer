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
from pathlib import Path
from typing import TYPE_CHECKING

from photo_meta_organizer.application.interfaces import ImageRetriever
from photo_meta_organizer.application.interfaces.analysis_repository import AnalysisRepository
from photo_meta_organizer.application.interfaces.collection_repository import (
    CollectionRepository,
)
from photo_meta_organizer.application.interfaces.folder_watcher import FolderWatcher
from photo_meta_organizer.application.interfaces.image_embedder import ImageEmbedder
from photo_meta_organizer.application.interfaces.image_repository import (
    ImageMetadataRepository,
)
from photo_meta_organizer.application.interfaces.job_store import JobStore
from photo_meta_organizer.application.interfaces.progress import ProgressSink
from photo_meta_organizer.application.interfaces.root_store import RootStore
from photo_meta_organizer.application.interfaces.state_store import StateStore
from photo_meta_organizer.application.settings import Settings
from photo_meta_organizer.application.use_cases.scan_library import ScanLibrary
from photo_meta_organizer.application.zero_shot_tagger import ZeroShotTagger
from photo_meta_organizer.domain.formats import IMAGE_EXTENSIONS

if TYPE_CHECKING:  # infrastructure is imported lazily inside the factories
    from photo_meta_organizer.infrastructure.analysis.model_store import ModelStore

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

    return ExtensionFilteredRetriever(LocalDiskRetriever(base_path=path), set(IMAGE_EXTENSIONS))


def build_scan(
    folder: str,
    repository: ImageMetadataRepository,
    progress_reporter: ProgressSink | None = None,
) -> ScanLibrary:
    """The scan of one local folder (ADR-003 R4): the CLI and the API both call this.

    Args:
        folder: The root to scan.
        repository: The library the scan records into.
        progress_reporter: Console-style progress output (the CLI's tqdm bar).

    Returns:
        A scan of ``folder``'s image files.

    Raises:
        NotADirectoryError: If ``folder`` is not an existing directory.
    """
    from photo_meta_organizer.infrastructure.extractors.disk_metadata_extractor import (
        DiskMetaDataExtractor,
    )

    return ScanLibrary(
        retriever=build_local_retriever(folder),
        extractor=DiskMetaDataExtractor(),
        repository=repository,
        progress_reporter=progress_reporter,
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

    if db_path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
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
    raise TypeError(f"unsupported repository type for collections: {type(repository)!r}")


def build_analysis_repository(
    repository: ImageMetadataRepository, models_dir: Path | None = None
) -> AnalysisRepository:
    """Build the analysis repository (embeddings, suggested tags) sharing storage with
    ``repository``, the same way :func:`build_collection_repository` does.

    With ``models_dir``, the vector index is saved under ``<models_dir>/vector-index`` so the
    first search after a restart maps it instead of reading every vector (ticket 16).
    """
    from photo_meta_organizer.infrastructure.repositories.brute_force_vector_index import (
        BruteForceVectorIndex,
    )
    from photo_meta_organizer.infrastructure.repositories.sqlite_analysis_repository import (
        SqliteAnalysisRepository,
    )
    from photo_meta_organizer.infrastructure.repositories.sqlite_repository import (
        SqliteRepository,
    )

    if isinstance(repository, SqliteRepository):
        index_dir = models_dir / "vector-index" if models_dir is not None else None
        index = BruteForceVectorIndex(repository.connection, repository.lock, index_dir)
        return SqliteAnalysisRepository(repository.connection, repository.lock, index)
    raise TypeError(f"unsupported repository type for analysis: {type(repository)!r}")


def build_job_store(repository: ImageMetadataRepository) -> JobStore:
    """Build the job history store sharing storage with ``repository`` (ADR-003 R5a)."""
    from photo_meta_organizer.infrastructure.repositories.sqlite_job_store import SqliteJobStore
    from photo_meta_organizer.infrastructure.repositories.sqlite_repository import (
        SqliteRepository,
    )

    if isinstance(repository, SqliteRepository):
        return SqliteJobStore(repository.connection, repository.lock)
    raise TypeError(f"unsupported repository type for jobs: {type(repository)!r}")


def build_root_store(repository: ImageMetadataRepository) -> RootStore:
    """Build the store of scanned folders sharing storage with ``repository`` (ticket 09)."""
    from photo_meta_organizer.infrastructure.repositories.sqlite_repository import (
        SqliteRepository,
    )
    from photo_meta_organizer.infrastructure.repositories.sqlite_root_store import SqliteRootStore

    if isinstance(repository, SqliteRepository):
        return SqliteRootStore(repository.connection, repository.lock)
    raise TypeError(f"unsupported repository type for roots: {type(repository)!r}")


def build_state_store(repository: ImageMetadataRepository) -> StateStore:
    """Build the store of small remembered values sharing storage with ``repository``."""
    from photo_meta_organizer.infrastructure.repositories.sqlite_repository import (
        SqliteRepository,
    )
    from photo_meta_organizer.infrastructure.repositories.sqlite_state_store import (
        SqliteStateStore,
    )

    if isinstance(repository, SqliteRepository):
        return SqliteStateStore(repository.connection, repository.lock)
    raise TypeError(f"unsupported repository type for state: {type(repository)!r}")


def build_folder_watcher() -> FolderWatcher:
    """The operating system's folder change notifications (ticket 10)."""
    from photo_meta_organizer.infrastructure.watching.watchfiles_watcher import (
        WatchfilesFolderWatcher,
    )

    return WatchfilesFolderWatcher()


def build_model_store(settings: Settings) -> "ModelStore":
    """The on-disk home (and downloader) of the AI model named by the manifest."""
    from photo_meta_organizer.infrastructure.analysis.model_manifest import CLIP_VIT_B32_FP16
    from photo_meta_organizer.infrastructure.analysis.model_store import ModelStore

    return ModelStore(settings.models_dir, CLIP_VIT_B32_FP16)


def build_embedder(store: "ModelStore") -> ImageEmbedder:
    """The CLIP embedder over ``store``. Cheap: nothing loads until the first vector."""
    from photo_meta_organizer.infrastructure.analysis.clip_onnx_embedder import ClipOnnxEmbedder

    return ClipOnnxEmbedder(store)


def build_tagger(settings: Settings, embedder: ImageEmbedder) -> ZeroShotTagger:
    """The zero-shot tagger over the shipped vocabulary, caching its label vectors on disk."""
    return ZeroShotTagger(embedder, cache_dir=settings.models_dir / "label-vectors")
