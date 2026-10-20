"""Contract tests for ImageMetadataRepository / CollectionRepository (PMO-07).

Parametrized over every backend so the same behavior is guaranteed regardless
of storage engine. Today that's just TinyDB; Stage 2 (PMO-08) adds the SQLite
backend to ``BACKENDS`` and these same test bodies must pass unchanged.
"""

from datetime import datetime

import pytest

from photo_meta_organizer.application.interfaces.search_types import BoundingBox, SearchQuery
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
        repository.save(_photo("h1", camera_make="Old"))
        repository.save_many([_photo("h1", camera_make="New")])
        assert repository.count() == 1
        assert repository.get_by_filehash("h1").exif.camera_make == "New"


class TestQuery:
    @pytest.mark.parametrize("order", ["asc", "desc"])
    def test_unknown_capture_dates_sort_last(self, repository, order):
        """PMO-24: a photo with no EXIF date goes after every dated one, either way."""
        repository.save_many(
            [
                _photo("undated"),
                _photo("old", captured_at=datetime(2020, 1, 1)),
                _photo("new", captured_at=datetime(2024, 1, 1)),
            ]
        )
        page = repository.query(SearchQuery(sort_by="captured_at", sort_order=order))
        dated = ["old", "new"] if order == "asc" else ["new", "old"]
        assert [m.file_hash for m in page.items] == [*dated, "undated"]

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


class TestServerSideFilters:
    """PMO-27: the filters the UI needs once it stops filtering in the browser."""

    @pytest.mark.parametrize("sort_by", ["captured_at", "size_bytes", "file_name"])
    def test_paging_through_equal_sort_keys_is_stable(self, repository, sort_by):
        """Infinite scroll asks for page after page: no photo may repeat or go missing."""
        when = datetime(2024, 1, 1)
        repository.save_many([_photo(f"h{i}", captured_at=when) for i in range(7)])
        seen = [
            m.file_hash
            for page in range(1, 5)
            for m in repository.query(SearchQuery(sort_by=sort_by, page=page, page_size=2))
        ]
        assert sorted(seen) == [f"h{i}" for i in range(7)]

    def test_camera_makes_is_any_of_exact(self, repository):
        repository.save_many(
            [
                _photo("h1", camera_make="Sony"),
                _photo("h2", camera_make="Canon"),
                _photo("h3", camera_make="SONY Corp"),
                _photo("h4"),
            ]
        )
        page = repository.query(SearchQuery(camera_makes=["Sony", "Canon"], sort_by="file_name"))
        assert sorted(m.file_hash for m in page.items) == ["h1", "h2"]

    def test_has_capture_date(self, repository):
        repository.save_many([_photo("dated", captured_at=datetime(2024, 1, 1)), _photo("undated")])
        assert [m.file_hash for m in repository.query(SearchQuery(has_capture_date=False))] == [
            "undated"
        ]
        assert [m.file_hash for m in repository.query(SearchQuery(has_capture_date=True))] == [
            "dated"
        ]

    def test_has_location(self, repository):
        repository.save_many(
            [_photo("geo", location=GpsCoordinates(latitude=1.0, longitude=2.0)), _photo("plain")]
        )
        assert [m.file_hash for m in repository.query(SearchQuery(has_location=True))] == ["geo"]
        assert [m.file_hash for m in repository.query(SearchQuery(has_location=False))] == ["plain"]

    def test_collection_membership(self, repository, collection_repository):
        repository.save_many([_photo("h1"), _photo("h2"), _photo("h3")])
        collection_repository.save("Trip", ["h1", "h3"])
        page = repository.query(SearchQuery(collection="Trip"))
        assert sorted(m.file_hash for m in page.items) == ["h1", "h3"]
        assert repository.query(SearchQuery(collection="Nope")).total_count == 0


class TestWithinFilter:
    def test_only_photos_inside_the_area(self, repository):
        repository.save_many(
            [
                _photo("in", location=GpsCoordinates(latitude=10.0, longitude=10.0)),
                _photo("out", location=GpsCoordinates(latitude=60.0, longitude=10.0)),
                _photo("nogps"),
            ]
        )
        box = BoundingBox(south=0, west=0, north=20, east=20)
        assert [m.file_hash for m in repository.query(SearchQuery(within=box))] == ["in"]

    def test_area_across_the_antimeridian(self, repository):
        repository.save_many(
            [
                _photo("e", location=GpsCoordinates(latitude=0.0, longitude=179.0)),
                _photo("w", location=GpsCoordinates(latitude=0.0, longitude=-179.0)),
                _photo("mid", location=GpsCoordinates(latitude=0.0, longitude=0.0)),
            ]
        )
        box = BoundingBox(south=-5, west=170, north=5, east=-170)
        hashes = {m.file_hash for m in repository.query(SearchQuery(within=box))}
        assert hashes == {"e", "w"}

    def test_combines_with_other_filters(self, repository):
        here = GpsCoordinates(latitude=1.0, longitude=1.0)
        repository.save_many(
            [
                _photo("a", camera_make="Sony", location=here),
                _photo("b", camera_make="Canon", location=here),
            ]
        )
        box = BoundingBox(south=0, west=0, north=2, east=2)
        query = SearchQuery(within=box, camera_make="Sony")
        assert [m.file_hash for m in repository.query(query)] == ["a"]


class TestGeoClusters:
    def _geo(self, hash_, lat, lon, **kw):
        return _photo(hash_, location=GpsCoordinates(latitude=lat, longitude=lon), **kw)

    def test_nearby_photos_share_a_cluster_and_far_ones_do_not(self, repository):
        repository.save_many(
            [
                self._geo("t1", 35.68, 139.65, captured_at=datetime(2026, 1, 1)),
                self._geo("t2", 35.70, 139.70, captured_at=datetime(2026, 1, 3)),
                self._geo("l1", 51.50, -0.12),
                _photo("nogps"),
            ]
        )
        clusters = repository.geo_clusters(SearchQuery(), None, 1.0)
        by_count = sorted(clusters, key=lambda c: -c.count)
        assert [c.count for c in by_count] == [2, 1]
        assert by_count[0].latitude == pytest.approx(35.69)
        assert by_count[0].longitude == pytest.approx(139.675)

    def test_representative_is_the_most_recently_captured(self, repository):
        repository.save_many(
            [
                self._geo("old", 10.0, 10.0, captured_at=datetime(2020, 1, 1)),
                self._geo("new", 10.1, 10.1, captured_at=datetime(2026, 1, 1)),
            ]
        )
        (cluster,) = repository.geo_clusters(SearchQuery(), None, 1.0)
        assert cluster.representative_hash == "new"

    def test_honours_search_filters(self, repository):
        repository.save_many(
            [
                self._geo("a", 10.0, 10.0, camera_make="Sony"),
                self._geo("b", 10.1, 10.1, camera_make="Canon"),
            ]
        )
        (cluster,) = repository.geo_clusters(SearchQuery(camera_make="Sony"), None, 1.0)
        assert cluster.count == 1 and cluster.representative_hash == "a"

    def test_bounding_box_limits_the_result(self, repository):
        repository.save_many([self._geo("in", 10.0, 10.0), self._geo("out", 60.0, 10.0)])
        box = BoundingBox(south=0, west=0, north=20, east=20)
        assert [
            c.representative_hash for c in repository.geo_clusters(SearchQuery(), box, 1.0)
        ] == ["in"]

    def test_bounding_box_across_the_antimeridian(self, repository):
        repository.save_many(
            [
                self._geo("east", 0.0, 179.5),
                self._geo("west", 0.0, -179.5),
                self._geo("mid", 0.0, 0.0),
            ]
        )
        box = BoundingBox(south=-10, west=170, north=10, east=-170)
        hashes = {c.representative_hash for c in repository.geo_clusters(SearchQuery(), box, 1.0)}
        assert hashes == {"east", "west"}

    def test_empty_library_has_no_clusters(self, repository):
        assert repository.geo_clusters(SearchQuery(), None, 1.0) == []


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

    def test_library_stats_and_iso_counts(self, repository):
        from dataclasses import replace as dc_replace

        def with_iso(photo, iso):
            return dc_replace(photo, exif=dc_replace(photo.exif, iso=iso))

        repository.save_many(
            [
                with_iso(_photo("h1", size_bytes=100, flagged=True), 100),
                with_iso(
                    _photo(
                        "h2",
                        size_bytes=300,
                        location=GpsCoordinates(latitude=1.0, longitude=2.0),
                        captured_at=datetime(2024, 1, 1),
                    ),
                    100,
                ),
                _photo("h3", size_bytes=600),
            ]
        )
        facets = repository.facets()
        stats = facets.stats
        assert (stats.total_count, stats.flagged_count, stats.geotagged_count) == (3, 1, 1)
        assert stats.undated_count == 2
        assert stats.total_bytes == 1000
        assert stats.avg_megapixels == pytest.approx(0.01)
        assert {f.name: f.count for f in facets.isos} == {"100": 2}

    def test_stats_of_an_empty_library(self, repository):
        stats = repository.facets().stats
        assert (stats.total_count, stats.total_bytes, stats.avg_megapixels) == (0, 0, 0.0)

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

    def test_replace_keeps_collection_membership(self, repository, collection_repository):
        """An edited photo (new hash) stays in its collections, in the same position."""
        repository.save_many([_photo("h1"), _photo("old"), _photo("h3")])
        collection_repository.save("A", ["h1", "old", "h3"])
        repository.replace("old", _photo("new", path="/photos/old_photo.jpg"))
        assert collection_repository.get("A").photo_hashes == ["h1", "new", "h3"]

    def test_replace_onto_existing_member_does_not_duplicate(
        self, repository, collection_repository
    ):
        repository.save_many([_photo("old"), _photo("same")])
        collection_repository.save("A", ["old", "same"])
        collection_repository.save("B", ["old"])
        repository.replace("old", _photo("same"))
        assert collection_repository.get("A").photo_hashes == ["same"]
        assert collection_repository.get("B").photo_hashes == ["same"]
