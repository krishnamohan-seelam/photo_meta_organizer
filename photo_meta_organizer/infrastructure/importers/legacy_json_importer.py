"""Import a legacy TinyDB ``metadata.json`` file into a SQLite repository (PMO-08).

Never modifies the JSON file: it is opened, read, and left exactly as it was.
Applies the PMO-05 dedupe rule (collapse records that share a resolved path,
keeping the newest and merging curation) as it goes, since the ADR makes
``path`` ``UNIQUE`` in the SQLite schema and a pre-fix JSON file may still
contain duplicates.
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from photo_meta_organizer.domain.curation import carry_over_curation
from photo_meta_organizer.domain.models import ImageMetadata
from photo_meta_organizer.infrastructure.repositories.sqlite_collection_repository import (
    SqliteCollectionRepository,
)
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import (
    SqliteRepository,
)
from photo_meta_organizer.infrastructure.repositories.tinydb_collection_repository import (
    TinyDBCollectionRepository,
)
from photo_meta_organizer.infrastructure.repositories.tinydb_repository import (
    TinyDBRepository,
)

logger = logging.getLogger(__name__)


@dataclass
class ImportResult:
    """Outcome of a legacy-JSON import."""

    source_count: int = 0
    imported_count: int = 0
    duplicate_paths_merged: int = 0
    collections_imported: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True if the import completed with no count mismatch."""
        return not self.errors


def _path_key(path: str) -> str:
    return os.path.normcase(str(Path(path).resolve()))


def _dedupe_by_path(records: list[ImageMetadata]) -> tuple[list[ImageMetadata], int]:
    """Collapse records sharing a resolved path (PMO-05 rule): newest wins, curation merged."""
    by_path: dict[str, list[ImageMetadata]] = {}
    for record in records:
        by_path.setdefault(_path_key(record.file_info.path), []).append(record)

    survivors: list[ImageMetadata] = []
    merged_count = 0
    for group in by_path.values():
        if len(group) == 1:
            survivors.append(group[0])
            continue
        ranked = sorted(
            enumerate(group), key=lambda ir: (ir[1].added_at, ir[0]), reverse=True
        )
        ordered = [record for _, record in ranked]
        survivors.append(carry_over_curation(ordered[0], *ordered[1:]))
        merged_count += len(ordered) - 1
    return survivors, merged_count


def import_legacy_json(json_path: str, sqlite_path: str) -> ImportResult:
    """Import ``json_path`` (a legacy TinyDB file) into a fresh SQLite database at
    ``sqlite_path``. The JSON file is opened read-only in spirit: nothing is written
    back to it.
    """
    result = ImportResult()
    source = TinyDBRepository(db_path=json_path)
    try:
        records = source.list_all()
        result.source_count = len(records)
        survivors, merged = _dedupe_by_path(records)
        result.duplicate_paths_merged = merged

        target = SqliteRepository(db_path=sqlite_path)
        try:
            target.save_many(survivors)
            result.imported_count = target.count()

            source_collections = TinyDBCollectionRepository(source.db)
            target_collections = SqliteCollectionRepository(
                target.connection, target.lock
            )
            valid_hashes = {m.file_hash for m in survivors}
            for collection in source_collections.list_all():
                hashes = [h for h in collection.photo_hashes if h in valid_hashes]
                target_collections.save(collection.name, hashes, collection.description)
                result.collections_imported += 1
        finally:
            target.close()

        if result.imported_count != result.source_count - result.duplicate_paths_merged:
            result.errors.append(
                f"count mismatch: source had {result.source_count} record(s), "
                f"{result.duplicate_paths_merged} merged as duplicate paths, but "
                f"{result.imported_count} landed in the new database"
            )
    finally:
        source.close()

    logger.info(
        "Imported %s photo(s) from %s into %s (%s duplicate path(s) merged, %s error(s))",
        result.imported_count,
        json_path,
        sqlite_path,
        result.duplicate_paths_merged,
        len(result.errors),
    )
    return result
