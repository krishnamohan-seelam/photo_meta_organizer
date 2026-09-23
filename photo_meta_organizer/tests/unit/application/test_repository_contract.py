"""Contract tests for ImageMetadataRepository / CollectionRepository (PMO-07).

Parametrized over every backend so the same behavior is guaranteed regardless
of storage engine. Today that's just TinyDB; Stage 2 (PMO-08) adds the SQLite
backend to ``BACKENDS`` and these same test bodies must pass unchanged.
"""

from datetime import datetime

import pytest
from photo_meta_organizer.application.interfaces.search_types import SearchQuery
from photo_meta_organizer.domain.curation import AddTag, RemoveTag, SetFlag, SetLabels, SetRating
from photo_meta_organizer.domain.models import (
    GpsCoordinates,
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.infrastructure.repositories.sqlite_collection_repository import (
    SqliteCollectionRepository,
)
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import SqliteRepository
from photo_meta_organizer.infrastructure.repositories.tinydb_collection_repository import (
    TinyDBCollectionRepository,
)
from photo_meta_organizer.infrastructure.repositories.tinydb_repository import TinyDBRepository


def _make_tinydb(tmp_path):
    repo = TinyDBRepository(db_path=str(tmp_path / "contract.json"))
    collections = TinyDBCollectionRepository(repo.db)
    return repo, collections


def _make_sqlite(tmp_path):
    repo = SqliteRepository(db_path=str(tmp_path / "contract.db"))
    collections = SqliteCollectionRepository(repo.connection, repo.lock)
    return repo, collections


BACKENDS = [("tinydb", _make_tinydb), ("sqlite", _make_sqlite)]


@pytest.fixture(params=BACKENDS, ids=[name for name, _ in BACKENDS])
def repo_pair(request, tmp_path):
    _, factory = request.param
    return factory(tmp_path)


@pytest.fixture
def repository(repo_pair):
    return repo_pair[0]


@pytest.fixture
def collection_repository(repo_pair):
    return repo_pair[1]


def _photo(
    hash_: str,
    *,
    name: str = "photo.jpg",
    path: str | None = None,
    camera_make: str | None = None,
    camera_model: str | None = None,
    captured_at: datetime | None = None,
    labels: list[str] | None = None,
    rating: int | None = None,
    flagged: bool = False,
    location: GpsCoordinates | None = None,
    size_bytes: int = 1_000,
) -> ImageMetadata:
    return ImageMetadata(
        file_hash=hash_,
        file_info=ImageFileInfo(
            name=name,
            path=path or f"/photos/{hash_}_{name}",
            size_bytes=size_bytes,
            mime_type="image/jpeg",
        ),
        dimensions=ImageDimensions(width=100, height=100),
        exif=ImageExifData(
            camera_make=camera_make,
            camera_model=camera_model,
            captured_at=captured_at,
            location=location,
        ),
        labels=labels or [],
        rating=rating,
        flagged=flagged,
    )


class TestSaveMany:
    def test_batch_upsert(self, repository):
        repository.save_many([_photo("h1"), _photo("h2")])
        assert repository.count() == 2
        assert repository.get_by_filehash("h1") is not None
        assert repository.get_by_filehash("h2") is not None

    def test_batch_upsert_updates_existing(self, repository):
        repository.save(_photo("h1", rating=1))
        repository.save_many([_photo("h1", rating=5)])
        assert repository.count() == 1
        assert repository.get_by_filehash("h1").rating == 5


class TestQuery:
    def test_pages_and_counts(self, repository):
        repository.save_many([_photo(f"h{i}") for i in range(5)])
        page = repository.query(SearchQuery(page=1, page_size=2))
        assert page.total_count == 5
        assert page.total_pages == 3
        assert len(page.items) == 2

    def test_camera_make_filter(self, repository):
        repository.save_many([_photo("h1", camera_make="Sony"), _photo("h2", camera_make="Canon")])
        page = repository.query(SearchQuery(camera_make="Sony"))
        assert [m.file_hash for m in page.items] == ["h1"]

    def test_tags_are_and_semantics(self, repository):
        repository.save_many(
            [
                _photo("h1", labels=["beach", "sunset"]),
                _photo("h2", labels=["beach"]),
            ]
        )
        page = repository.query(SearchQuery(tags=["beach", "sunset"]))
        assert [m.file_hash for m in page.items] == ["h1"]

    def test_rating_and_flagged_filters(self, repository):
        repository.save_many(
            [
                _photo("h1", rating=5, flagged=True),
                _photo("h2", rating=3, flagged=False),
            ]
        )
        assert [m.file_hash for m in repository.query(SearchQuery(rating=5)).items] == ["h1"]
        assert [m.file_hash for m in repository.query(SearchQuery(flagged=True)).items] == ["h1"]

    def test_search_term_matches_name_and_camera(self, repository):
        repository.save_many(
            [
                _photo("h1", name="vacation.jpg", camera_make="Sony"),
                _photo("h2", name="work.jpg", camera_make="Canon"),
            ]
        )
        page = repository.query(SearchQuery(search_term="vacation"))
        assert [m.file_hash for m in page.items] == ["h1"]

    def test_date_range_filter(self, repository):
        repository.save_many(
            [
                _photo("h1", captured_at=datetime(2024, 1, 1)),
                _photo("h2", captured_at=datetime(2025, 1, 1)),
            ]
        )
        page = repository.query(
            SearchQuery(date_start=datetime(2024, 6, 1), date_end=datetime(2025, 6, 1))
        )
        assert [m.file_hash for m in page.items] == ["h2"]

    def test_sort_by_size_desc(self, repository):
        repository.save_many([_photo("h1", size_bytes=100), _photo("h2", size_bytes=999)])
        page = repository.query(SearchQuery(sort_by="size_bytes", sort_order="desc"))
        assert [m.file_hash for m in page.items] == ["h2", "h1"]


class TestFacets:
    def test_camera_and_tag_and_year_counts(self, repository):
        repository.save_many(
            [
                _photo(
                    "h1", camera_make="Sony", labels=["beach"], captured_at=datetime(2024, 5, 1)
                ),
                _photo(
                    "h2",
                    camera_make="Sony",
                    labels=["beach", "sunset"],
                    captured_at=datetime(2024, 6, 1),
                ),
                _photo(
                    "h3", camera_make="Canon", labels=["portrait"], captured_at=datetime(2025, 1, 1)
                ),
            ]
        )
        facets = repository.facets()
        camera_counts = {f.name: f.count for f in facets.cameras}
        tag_counts = {f.name: f.count for f in facets.tags}
        year_counts = {f.name: f.count for f in facets.years}
        assert camera_counts == {"Sony": 2, "Canon": 1}
        assert tag_counts == {"beach": 2, "sunset": 1, "portrait": 1}
        assert year_counts == {"2024": 2, "2025": 1}

    def test_gps_bounds(self, repository):
        repository.save_many(
            [
                _photo("h1", location=GpsCoordinates(latitude=10.0, longitude=20.0)),
                _photo("h2", location=GpsCoordinates(latitude=30.0, longitude=40.0)),
            ]
        )
        bounds = repository.facets().gps_bounds
        assert bounds is not None
        assert (bounds.min_lat, bounds.max_lat) == (10.0, 30.0)
        assert (bounds.min_lon, bounds.max_lon) == (20.0, 40.0)


class TestCurationCommands:
    def test_set_rating(self, repository):
        repository.save(_photo("h1"))
        updated = repository.apply("h1", SetRating(4))
        assert updated.rating == 4

    def test_set_flag(self, repository):
        repository.save(_photo("h1"))
        updated = repository.apply("h1", SetFlag(True))
        assert updated.flagged is True

    def test_add_and_remove_tag(self, repository):
        repository.save(_photo("h1", labels=["beach"]))
        after_add = repository.apply("h1", AddTag("sunset"))
        assert set(after_add.labels) == {"beach", "sunset"}
        after_remove = repository.apply("h1", RemoveTag("beach"))
        assert after_remove.labels == ["sunset"]

    def test_set_labels_replaces_all(self, repository):
        repository.save(_photo("h1", labels=["beach", "sunset"]))
        updated = repository.apply("h1", SetLabels(["portrait"]))
        assert updated.labels == ["portrait"]

    def test_apply_unknown_hash_returns_none(self, repository):
        assert repository.apply("nope", SetRating(3)) is None

    def test_apply_batch_skips_unknown_hashes(self, repository):
        repository.save(_photo("h1"))
        count = repository.apply_batch(["h1", "nope"], SetRating(2))
        assert count == 1
        assert repository.get_by_filehash("h1").rating == 2

    def test_batch_delete(self, repository):
        repository.save_many([_photo("h1"), _photo("h2"), _photo("h3")])
        deleted = repository.batch_delete(["h1", "h2", "nope"])
        assert deleted == 2
        assert repository.count() == 1


class TestCollectionRepository:
    """SQLite enforces the FK from collection_photos to photos (ADR-001), so every
    hash a collection references must already exist as a photo record.
    """

    def test_save_and_get(self, repository, collection_repository):
        repository.save_many([_photo("h1"), _photo("h2")])
        collection_repository.save("Favorites", ["h1", "h2"], description="Best shots")
        record = collection_repository.get("Favorites")
        assert record.photo_hashes == ["h1", "h2"]
        assert record.description == "Best shots"

    def test_save_upserts(self, repository, collection_repository):
        repository.save_many([_photo("h1"), _photo("h2")])
        collection_repository.save("Favorites", ["h1"])
        collection_repository.save("Favorites", ["h1", "h2"])
        record = collection_repository.get("Favorites")
        assert record.photo_hashes == ["h1", "h2"]

    def test_list_all(self, repository, collection_repository):
        repository.save_many([_photo("h1"), _photo("h2")])
        collection_repository.save("A", ["h1"])
        collection_repository.save("B", ["h2"])
        names = {c.name for c in collection_repository.list_all()}
        assert names == {"A", "B"}

    def test_delete(self, repository, collection_repository):
        repository.save(_photo("h1"))
        collection_repository.save("A", ["h1"])
        assert collection_repository.delete("A") is True
        assert collection_repository.get("A") is None
        assert collection_repository.delete("A") is False

    def test_remove_photo_from_all(self, repository, collection_repository):
        repository.save_many([_photo("h1"), _photo("h2"), _photo("h3")])
        collection_repository.save("A", ["h1", "h2"])
        collection_repository.save("B", ["h2", "h3"])
        touched = collection_repository.remove_photo_from_all("h2")
        assert touched == 2
        assert collection_repository.get("A").photo_hashes == ["h1"]
        assert collection_repository.get("B").photo_hashes == ["h3"]
