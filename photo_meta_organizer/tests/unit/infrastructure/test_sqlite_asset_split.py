"""ADR-003 R3: the library stores Assets, their Files and Curation separately."""

import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from photo_meta_organizer.application.composition import build_analysis_repository
from photo_meta_organizer.application.interfaces.search_types import SearchQuery
from photo_meta_organizer.domain.curation import AddTag, SetFlag, SetRating
from photo_meta_organizer.domain.models import ImageMetadata, StoredFile
from photo_meta_organizer.infrastructure.repositories.migrations import MIGRATIONS, migrate
from photo_meta_organizer.infrastructure.repositories.sqlite_collection_repository import (
    SqliteCollectionRepository,
)
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import SqliteRepository

HASH_A = "a" * 64
HASH_B = "b" * 64


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[SqliteRepository]:
    repository = SqliteRepository(str(tmp_path / "photos.db"))
    yield repository
    repository.close()


def _photo(base: ImageMetadata, file_hash: str, path: str, **changes: object) -> ImageMetadata:
    return replace(
        base,
        file_hash=file_hash,
        file_info=replace(base.file_info, path=path, name=Path(path).name),
        **changes,
    )


def _version_one_library(path: Path) -> None:
    """A library as the baseline schema wrote it: one photos row per hash."""
    connection = sqlite3.connect(str(path))
    migrate(connection, str(path), MIGRATIONS[:1])
    connection.executescript(f"""
        INSERT INTO photos (file_hash, path, name, size_bytes, mime_type, mtime, width, height,
            captured_at, camera_make, camera_model, iso, raw_tags, rating, flagged, added_at)
        VALUES ('{HASH_A}', 'D:/p/a.jpg', 'a.jpg', 1234, 'image/jpeg', '2024-01-02T03:04:05',
            4000, 3000, '2023-06-01T10:00:00', 'Sony', 'A7', 100, '{{"Make": "Sony"}}', 4, 1,
            '2024-02-01T00:00:00');
        INSERT INTO photos (file_hash, path, name, size_bytes, mime_type, width, height,
            added_at)
        VALUES ('{HASH_B}', 'D:/p/b.jpg', 'b.jpg', 99, 'image/png', 10, 10,
            '2024-02-02T00:00:00');
        INSERT INTO photo_labels (file_hash, label) VALUES ('{HASH_A}', 'zebra');
        INSERT INTO photo_labels (file_hash, label) VALUES ('{HASH_A}', 'apple');
        INSERT INTO collections (name, description, updated_at)
            VALUES ('trip', 'Summer', '2024-03-01T00:00:00');
        INSERT INTO collection_photos (collection, file_hash) VALUES ('trip', '{HASH_B}');
        INSERT INTO collection_photos (collection, file_hash) VALUES ('trip', '{HASH_A}');
        INSERT INTO photo_embeddings (file_hash, model_id, dim, vector, created_at)
            VALUES ('{HASH_A}', 'm', 2, x'0000803f00000000', '2024-03-01T00:00:00');
        INSERT INTO photo_ai_tags (file_hash, label, confidence, model_id, status)
            VALUES ('{HASH_A}', 'beach', 0.4, 'm', 'rejected');
        """)
    connection.commit()
    connection.close()


class TestMigrationFromVersionOne:
    def test_every_photo_keeps_its_metadata_path_and_curation(self, tmp_path: Path) -> None:
        path = tmp_path / "photos.db"
        _version_one_library(path)

        repo = SqliteRepository(str(path))
        try:
            a = repo.get_by_filehash(HASH_A)
            assert a is not None
            assert a.file_info.path == "D:/p/a.jpg"
            assert a.file_info.size_bytes == 1234
            assert a.file_info.modified_time == datetime(2024, 1, 2, 3, 4, 5)
            assert a.exif.camera_make == "Sony"
            assert a.exif.captured_at == datetime(2023, 6, 1, 10, 0)
            assert a.exif.raw_tags == {"Make": "Sony"}
            assert (a.dimensions.width, a.dimensions.height) == (4000, 3000)
            assert (a.rating, a.flagged) == (4, True)
            assert a.labels == ["zebra", "apple"]  # order kept
            assert a.added_at == datetime(2024, 2, 1)
            assert repo.count() == 2
        finally:
            repo.close()

    def test_collections_embeddings_and_ai_tags_survive(self, tmp_path: Path) -> None:
        path = tmp_path / "photos.db"
        _version_one_library(path)

        repo = SqliteRepository(str(path))
        try:
            collections = SqliteCollectionRepository(repo.connection, repo.lock)
            analysis = build_analysis_repository(repo)
            trip = collections.get("trip")
            assert trip is not None
            assert trip.photo_hashes == [HASH_B, HASH_A]  # order kept
            assert analysis.count_embeddings("m") == 1
            assert [t.label for t in analysis.list_ai_tags(HASH_A)] == ["beach"]

            repo.delete(HASH_A)  # the rebuilt tables still cascade from assets
            assert analysis.count_embeddings("m") == 0
            assert collections.get("trip").photo_hashes == [HASH_B]
        finally:
            repo.close()

    def test_rows_pointing_at_no_photo_are_dropped_instead_of_blocking_the_upgrade(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "photos.db"
        _version_one_library(path)
        raw = sqlite3.connect(str(path))  # foreign keys off: how such rows got in
        raw.executescript(f"""
            INSERT INTO photo_labels (file_hash, label) VALUES ('{"9" * 64}', 'ghost');
            INSERT INTO photo_embeddings (file_hash, model_id, dim, vector, created_at)
                VALUES ('{"9" * 64}', 'm', 2, x'0000803f00000000', '2024-03-01T00:00:00');
            INSERT INTO photo_ai_tags (file_hash, label, confidence, model_id)
                VALUES ('{"9" * 64}', 'sky', 0.5, 'm');
            INSERT INTO collection_photos (collection, file_hash) VALUES ('gone', '{HASH_A}');
            INSERT INTO collection_photos (collection, file_hash) VALUES ('trip', '{"9" * 64}');
            """)
        raw.commit()
        raw.close()

        repo = SqliteRepository(str(path))
        try:
            analysis = build_analysis_repository(repo)
            assert analysis.count_embeddings("m") == 1
            assert "ghost" not in [t.name for t in repo.facets().tags]
            trip = SqliteCollectionRepository(repo.connection, repo.lock).get("trip")
            assert trip.photo_hashes == [HASH_B, HASH_A]
        finally:
            repo.close()

    def test_backup_is_taken_before_the_rebuild(self, tmp_path: Path) -> None:
        path = tmp_path / "photos.db"
        _version_one_library(path)

        SqliteRepository(str(path)).close()

        backup = sqlite3.connect(f"{path}.pre-0002")
        try:
            assert backup.execute("PRAGMA user_version").fetchone()[0] == 1
            assert backup.execute("SELECT COUNT(*) FROM photos").fetchone()[0] == 2
        finally:
            backup.close()


class TestCopies:
    def test_same_content_at_two_paths_is_one_photo_with_two_files(
        self, repo: SqliteRepository, sample_image_metadata: ImageMetadata
    ) -> None:
        repo.save(_photo(sample_image_metadata, HASH_A, "/p/one.jpg"))
        repo.save(_photo(sample_image_metadata, HASH_A, "/p/copy/one.jpg"))

        assert repo.count() == 1
        assert sorted(f.path for f in repo.list_files()) == ["/p/copy/one.jpg", "/p/one.jpg"]
        assert {f.file_hash for f in repo.list_files()} == {HASH_A}
        assert repo.query(SearchQuery(page_size=10)).total_count == 1
        assert repo.facets().stats.total_count == 1

    def test_list_files_reports_each_fingerprint(
        self, repo: SqliteRepository, sample_image_metadata: ImageMetadata
    ) -> None:
        mtime = datetime(2024, 5, 6, 7, 8, 9)
        photo = _photo(sample_image_metadata, HASH_A, "/p/one.jpg")
        repo.save(replace(photo, file_info=replace(photo.file_info, modified_time=mtime)))

        assert repo.list_files() == [
            StoredFile(
                path="/p/one.jpg",
                file_hash=HASH_A,
                size_bytes=photo.file_info.size_bytes,
                modified_time=mtime,
            )
        ]

    def test_copies_share_curation(
        self, repo: SqliteRepository, sample_image_metadata: ImageMetadata
    ) -> None:
        repo.save(_photo(sample_image_metadata, HASH_A, "/p/one.jpg"))
        repo.apply(HASH_A, SetRating(5))

        repo.save(_photo(sample_image_metadata, HASH_A, "/p/copy.jpg", rating=None))

        assert repo.get_by_filehash(HASH_A).rating == 5

    def test_search_term_matches_any_path_of_the_photo(
        self, repo: SqliteRepository, sample_image_metadata: ImageMetadata
    ) -> None:
        repo.save(_photo(sample_image_metadata, HASH_A, "/p/one.jpg"))
        repo.save(_photo(sample_image_metadata, HASH_A, "/backup/holiday/one.jpg"))

        page = repo.query(SearchQuery(search_term="holiday", page_size=10))

        assert [p.file_hash for p in page.items] == [HASH_A]

    def test_forgetting_one_file_keeps_the_photo_while_another_holds_it(
        self, repo: SqliteRepository, sample_image_metadata: ImageMetadata
    ) -> None:
        repo.save(_photo(sample_image_metadata, HASH_A, "/p/one.jpg"))
        repo.save(_photo(sample_image_metadata, HASH_A, "/p/copy.jpg"))

        assert repo.delete_by_path("/p/one.jpg") is True
        assert repo.get_by_filehash(HASH_A).file_info.path == "/p/copy.jpg"

        assert repo.delete_by_path("/p/copy.jpg") is True
        assert repo.get_by_filehash(HASH_A) is None
        assert repo.count() == 0


class TestEditedFile:
    def test_edit_moves_curation_to_the_new_content(
        self, repo: SqliteRepository, sample_image_metadata: ImageMetadata
    ) -> None:
        repo.save(_photo(sample_image_metadata, HASH_A, "/p/one.jpg", labels=[]))
        repo.apply(HASH_A, SetRating(4))
        repo.apply(HASH_A, SetFlag(True))
        repo.apply(HASH_A, AddTag("keeper"))
        added_at = repo.get_by_filehash(HASH_A).added_at

        repo.save(_photo(sample_image_metadata, HASH_B, "/p/one.jpg", labels=[], rating=None))

        edited = repo.get_by_filehash(HASH_B)
        assert edited is not None
        assert (edited.rating, edited.flagged, edited.labels) == (4, True, ["keeper"])
        assert edited.added_at == added_at
        assert repo.get_by_filehash(HASH_A) is None  # no file holds the old content
        assert repo.count() == 1

    def test_edit_copies_curation_when_another_file_still_has_the_old_content(
        self, repo: SqliteRepository, sample_image_metadata: ImageMetadata
    ) -> None:
        repo.save(_photo(sample_image_metadata, HASH_A, "/p/one.jpg", labels=[]))
        repo.save(_photo(sample_image_metadata, HASH_A, "/p/copy.jpg", labels=[]))
        repo.apply(HASH_A, SetRating(3))

        repo.save(_photo(sample_image_metadata, HASH_B, "/p/one.jpg", labels=[], rating=None))

        assert repo.get_by_filehash(HASH_B).rating == 3
        old = repo.get_by_filehash(HASH_A)
        assert old is not None
        assert old.rating == 3
        assert old.file_info.path == "/p/copy.jpg"
        assert repo.count() == 2

    def test_edit_onto_content_already_in_the_library_merges_curation(
        self, repo: SqliteRepository, sample_image_metadata: ImageMetadata
    ) -> None:
        repo.save(_photo(sample_image_metadata, HASH_A, "/p/one.jpg", labels=[]))
        repo.save(_photo(sample_image_metadata, HASH_B, "/p/two.jpg", labels=[]))
        repo.apply(HASH_A, SetRating(2))
        repo.apply(HASH_A, AddTag("from-a"))
        repo.apply(HASH_B, SetRating(5))
        repo.apply(HASH_B, SetFlag(True))
        repo.apply(HASH_B, AddTag("from-b"))

        repo.save(_photo(sample_image_metadata, HASH_B, "/p/one.jpg", labels=[], rating=None))

        merged = repo.get_by_filehash(HASH_B)
        # The edited file's own curation comes first, as before R3.
        assert (merged.rating, merged.flagged) == (2, True)
        assert merged.labels == ["from-a", "from-b"]
        assert repo.get_by_filehash(HASH_A) is None

    def test_edit_drops_the_old_contents_analysis(
        self, repo: SqliteRepository, sample_image_metadata: ImageMetadata
    ) -> None:
        from photo_meta_organizer.domain.analysis import Embedding

        analysis = build_analysis_repository(repo)
        repo.save(_photo(sample_image_metadata, HASH_A, "/p/one.jpg"))
        analysis.save_embeddings([Embedding(file_hash=HASH_A, model_id="m", vector=(1.0, 0.0))])

        repo.save(_photo(sample_image_metadata, HASH_B, "/p/one.jpg"))

        assert analysis.count_embeddings("m") == 0

    def test_edit_keeps_the_photo_in_its_collections_in_place(
        self, repo: SqliteRepository, sample_image_metadata: ImageMetadata
    ) -> None:
        collections = SqliteCollectionRepository(repo.connection, repo.lock)
        first, last = "1" * 64, "3" * 64
        repo.save(_photo(sample_image_metadata, first, "/p/first.jpg"))
        repo.save(_photo(sample_image_metadata, HASH_A, "/p/one.jpg"))
        repo.save(_photo(sample_image_metadata, last, "/p/last.jpg"))
        collections.save("trip", [first, HASH_A, last])

        repo.save(_photo(sample_image_metadata, HASH_B, "/p/one.jpg"))

        assert collections.get("trip").photo_hashes == [first, HASH_B, last]

    def test_edit_onto_a_photo_already_in_the_collection_does_not_duplicate_it(
        self, repo: SqliteRepository, sample_image_metadata: ImageMetadata
    ) -> None:
        collections = SqliteCollectionRepository(repo.connection, repo.lock)
        repo.save(_photo(sample_image_metadata, HASH_A, "/p/one.jpg"))
        repo.save(_photo(sample_image_metadata, HASH_B, "/p/two.jpg"))
        collections.save("both", [HASH_A, HASH_B])
        collections.save("only-a", [HASH_A])

        repo.save(_photo(sample_image_metadata, HASH_B, "/p/one.jpg"))

        assert collections.get("both").photo_hashes == [HASH_B]
        assert collections.get("only-a").photo_hashes == [HASH_B]
