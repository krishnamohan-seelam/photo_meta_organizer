"""PMO-08: importing a legacy TinyDB metadata.json into a fresh SQLite database."""

from datetime import datetime

from photo_meta_organizer.domain.models import (
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.infrastructure.importers.legacy_json_importer import (
    import_legacy_json,
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


def _photo(
    hash_: str, path: str, added_at: datetime, rating=None, flagged=False
) -> ImageMetadata:
    return ImageMetadata(
        file_hash=hash_,
        file_info=ImageFileInfo(
            name="a.jpg", path=path, size_bytes=1, mime_type="image/jpeg"
        ),
        dimensions=ImageDimensions(width=1, height=1),
        exif=ImageExifData(camera_make="Sony"),
        rating=rating,
        flagged=flagged,
        added_at=added_at,
    )


def test_imports_records_and_matches_count(tmp_path):
    json_path = str(tmp_path / "legacy.json")
    source = TinyDBRepository(db_path=json_path)
    source.save(_photo("h1", "/a.jpg", datetime(2024, 1, 1)))
    source.save(_photo("h2", "/b.jpg", datetime(2024, 1, 2)))
    source.close()

    sqlite_path = str(tmp_path / "imported.db")
    result = import_legacy_json(json_path, sqlite_path)

    assert result.ok
    assert result.source_count == 2
    assert result.imported_count == 2
    assert result.duplicate_paths_merged == 0

    target = SqliteRepository(db_path=sqlite_path)
    assert target.count() == 2
    assert target.get_by_filehash("h1") is not None
    target.close()


def test_never_modifies_the_source_json(tmp_path):
    json_path = str(tmp_path / "legacy.json")
    source = TinyDBRepository(db_path=json_path)
    source.save(_photo("h1", "/a.jpg", datetime(2024, 1, 1)))
    source.close()

    before = (tmp_path / "legacy.json").read_text(encoding="utf-8")
    import_legacy_json(json_path, str(tmp_path / "imported.db"))
    after = (tmp_path / "legacy.json").read_text(encoding="utf-8")
    assert before == after


def test_merges_duplicate_paths_keeping_newest_and_curation(tmp_path):
    json_path = str(tmp_path / "legacy.json")
    source = TinyDBRepository(db_path=json_path)
    # Same path, two hashes (old MODIFIED bug): older curated, newer not.
    source.save(_photo("old", "/a.jpg", datetime(2024, 1, 1), rating=5, flagged=True))
    source.save(_photo("new", "/a.jpg", datetime(2024, 6, 1)))
    source.close()

    result = import_legacy_json(json_path, str(tmp_path / "imported.db"))

    assert result.ok
    assert result.source_count == 2
    assert result.duplicate_paths_merged == 1
    assert result.imported_count == 1

    target = SqliteRepository(db_path=str(tmp_path / "imported.db"))
    survivor = target.get_by_path("/a.jpg")
    assert survivor.file_hash == "new"
    assert survivor.rating == 5
    assert survivor.flagged is True
    target.close()


def test_imports_collections_dropping_hashes_that_did_not_survive(tmp_path):
    json_path = str(tmp_path / "legacy.json")
    source = TinyDBRepository(db_path=json_path)
    source.save(_photo("h1", "/a.jpg", datetime(2024, 1, 1)))
    source.save(_photo("h2", "/b.jpg", datetime(2024, 1, 1)))
    collections = TinyDBCollectionRepository(source.db)
    collections.save("Favorites", ["h1", "h2", "ghost-hash"], description="Best")
    source.close()

    sqlite_path = str(tmp_path / "imported.db")
    result = import_legacy_json(json_path, sqlite_path)

    assert result.collections_imported == 1

    from photo_meta_organizer.infrastructure.repositories.sqlite_collection_repository import (
        SqliteCollectionRepository,
    )

    target = SqliteRepository(db_path=sqlite_path)
    target_collections = SqliteCollectionRepository(target.connection, target.lock)
    record = target_collections.get("Favorites")
    assert set(record.photo_hashes) == {"h1", "h2"}
    assert record.description == "Best"
    target.close()
