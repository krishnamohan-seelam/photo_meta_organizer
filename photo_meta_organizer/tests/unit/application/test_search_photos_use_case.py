"""Unit tests for SearchPhotosUseCase and associated DTOs."""

from datetime import datetime, timezone
import pytest
from unittest.mock import MagicMock

from photo_meta_organizer.application.use_cases.search_photos_use_case import (
    PaginatedResult,
    SearchPhotosQuery,
    SearchPhotosUseCase,
    haversine_distance_km,
)
from photo_meta_organizer.domain.models import (
    CameraProfile,
    GpsCoordinates,
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)


@pytest.fixture
def sample_metadata_list():
    dt1 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    dt2 = datetime(2024, 2, 20, 15, 30, 0, tzinfo=timezone.utc)
    dt3 = datetime(2024, 3, 10, 8, 45, 0, tzinfo=timezone.utc)

    # San Francisco: ~37.7749, -122.4194
    gps_sf = GpsCoordinates(latitude=37.7749, longitude=-122.4194)
    # Oakland: ~37.8044, -122.2712 (approx 13 km from SF)
    gps_oakland = GpsCoordinates(latitude=37.8044, longitude=-122.2712)
    # New York: ~40.7128, -74.0060 (thousands of km away)
    gps_ny = GpsCoordinates(latitude=40.7128, longitude=-74.0060)

    m1 = ImageMetadata(
        file_hash="hash1",
        file_info=ImageFileInfo(
            path="/photos/photo1.jpg",
            name="photo1.jpg",
            size_bytes=1000,
            mime_type="image/jpeg",
        ),
        dimensions=ImageDimensions(width=1920, height=1080),
        exif=ImageExifData(
            captured_at=dt1,
            camera_make="Sony",
            camera_model="A7IV",
            location=gps_sf,
        ),
        labels=["vacation", "nature"],
    )

    m2 = ImageMetadata(
        file_hash="hash2",
        file_info=ImageFileInfo(
            path="/photos/photo2.jpg",
            name="photo2.jpg",
            size_bytes=5000,
            mime_type="image/jpeg",
        ),
        dimensions=ImageDimensions(width=4000, height=3000),
        exif=ImageExifData(
            captured_at=dt2,
            camera_make="Canon",
            camera_model="EOS R5",
            location=gps_oakland,
        ),
        labels=["vacation", "city"],
    )

    m3 = ImageMetadata(
        file_hash="hash3",
        file_info=ImageFileInfo(
            path="/photos/photo3.jpg",
            name="photo3.jpg",
            size_bytes=2000,
            mime_type="image/jpeg",
        ),
        dimensions=ImageDimensions(width=1200, height=800),
        exif=ImageExifData(
            captured_at=dt3,
            camera_make="Sony",
            camera_model="RX100",
            location=gps_ny,
        ),
        labels=["portrait"],
    )

    return [m1, m2, m3]


def test_haversine_distance():
    # SF to Oakland is ~13 km
    dist = haversine_distance_km(37.7749, -122.4194, 37.8044, -122.2712)
    assert 10.0 <= dist <= 15.0

    # Same location -> 0 km
    assert haversine_distance_km(37.7749, -122.4194, 37.7749, -122.4194) == 0.0


def test_paginated_result_iterator():
    items = ["a", "b", "c"]
    res = PaginatedResult(
        items=items, total_count=3, page=1, page_size=10, total_pages=1
    )

    collected = [x for x in res]
    assert collected == ["a", "b", "c"]
    assert len(res) == 3


def test_search_use_case_no_filters(sample_metadata_list):
    repo = MagicMock()
    repo.list_all.return_value = sample_metadata_list

    use_case = SearchPhotosUseCase(repository=repo)
    query = SearchPhotosQuery()
    result = use_case.execute(query)

    assert result.total_count == 3
    assert result.total_pages == 1
    assert len(result.items) == 3


def test_search_use_case_date_filter(sample_metadata_list):
    repo = MagicMock()
    repo.list_all.return_value = sample_metadata_list

    use_case = SearchPhotosUseCase(repository=repo)
    query = SearchPhotosQuery(
        date_start=datetime(2024, 2, 1, tzinfo=timezone.utc),
        date_end=datetime(2024, 2, 28, tzinfo=timezone.utc),
    )
    result = use_case.execute(query)

    assert result.total_count == 1
    assert result.items[0].file_info.name == "photo2.jpg"


def test_search_use_case_camera_filter(sample_metadata_list):
    repo = MagicMock()
    repo.list_all.return_value = sample_metadata_list

    use_case = SearchPhotosUseCase(repository=repo)
    query = SearchPhotosQuery(camera_make="Sony")
    result = use_case.execute(query)

    assert result.total_count == 2
    names = {item.file_info.name for item in result.items}
    assert names == {"photo1.jpg", "photo3.jpg"}


def test_search_use_case_location_radius(sample_metadata_list):
    repo = MagicMock()
    repo.list_all.return_value = sample_metadata_list

    use_case = SearchPhotosUseCase(repository=repo)
    # Search within 20km of SF
    query = SearchPhotosQuery(
        location_lat=37.7749, location_lon=-122.4194, radius_km=20.0
    )
    result = use_case.execute(query)

    # Should match SF and Oakland photos, but not NY photo
    assert result.total_count == 2
    names = {item.file_info.name for item in result.items}
    assert names == {"photo1.jpg", "photo2.jpg"}


def test_search_use_case_tags_filter(sample_metadata_list):
    repo = MagicMock()
    repo.list_all.return_value = sample_metadata_list

    use_case = SearchPhotosUseCase(repository=repo)
    query = SearchPhotosQuery(tags=["vacation"])
    result = use_case.execute(query)

    assert result.total_count == 2
    names = {item.file_info.name for item in result.items}
    assert names == {"photo1.jpg", "photo2.jpg"}


def test_search_use_case_sorting(sample_metadata_list):
    repo = MagicMock()
    repo.list_all.return_value = sample_metadata_list

    use_case = SearchPhotosUseCase(repository=repo)

    # Sort by size asc
    query_size_asc = SearchPhotosQuery(sort_by="size_bytes", sort_order="asc")
    res1 = use_case.execute(query_size_asc)
    assert [x.file_info.size_bytes for x in res1.items] == [1000, 2000, 5000]

    # Sort by size desc
    query_size_desc = SearchPhotosQuery(sort_by="size_bytes", sort_order="desc")
    res2 = use_case.execute(query_size_desc)
    assert [x.file_info.size_bytes for x in res2.items] == [5000, 2000, 1000]


def test_search_use_case_pagination(sample_metadata_list):
    repo = MagicMock()
    repo.list_all.return_value = sample_metadata_list

    use_case = SearchPhotosUseCase(repository=repo)
    query = SearchPhotosQuery(page=1, page_size=2, sort_by="size_bytes", sort_order="asc")
    res1 = use_case.execute(query)

    assert res1.total_count == 3
    assert res1.total_pages == 2
    assert len(res1.items) == 2
    assert res1.items[0].file_info.size_bytes == 1000
    assert res1.items[1].file_info.size_bytes == 2000

def test_search_use_case_camera_model_and_missing_exif(sample_metadata_list):
    repo = MagicMock()
    # Add a metadata item with missing EXIF/file_info fields
    m_no_exif = ImageMetadata(
        file_hash="hash4",
        file_info=ImageFileInfo(path="/photos/noexif.jpg", name="noexif.jpg", size_bytes=100, mime_type="image/jpeg"),
        dimensions=ImageDimensions(width=100, height=100),
        exif=ImageExifData(),
    )
    repo.list_all.return_value = sample_metadata_list + [m_no_exif]

    use_case = SearchPhotosUseCase(repository=repo)

    # Filter by camera_model
    res_model = use_case.execute(SearchPhotosQuery(camera_model="A7IV"))
    assert res_model.total_count == 1
    assert res_model.items[0].file_info.name == "photo1.jpg"

    # Filter by date when EXIF is missing or out of bounds
    res_date = use_case.execute(SearchPhotosQuery(date_start=datetime(2025, 1, 1, tzinfo=timezone.utc)))
    assert res_date.total_count == 0

    # Filter by location when GPS missing
    res_loc = use_case.execute(SearchPhotosQuery(location_lat=0.0, location_lon=0.0, radius_km=10.0))
    assert res_loc.total_count == 0

    # Filter by tags with raw_tags list
    m_raw_tags = ImageMetadata(
        file_hash="hash5",
        file_info=ImageFileInfo(path="/photos/rawtags.jpg", name="rawtags.jpg", size_bytes=200, mime_type="image/jpeg"),
        dimensions=ImageDimensions(width=100, height=100),
        exif=ImageExifData(raw_tags={"tags": ["custom_tag"]}),
    )
    repo.list_all.return_value = [m_raw_tags]
    res_tags = use_case.execute(SearchPhotosQuery(tags=["custom_tag"]))
    assert res_tags.total_count == 1


def test_search_use_case_sorting_keys(sample_metadata_list):
    repo = MagicMock()
    repo.list_all.return_value = sample_metadata_list
    use_case = SearchPhotosUseCase(repository=repo)

    # Sort by camera_model asc
    res_model = use_case.execute(SearchPhotosQuery(sort_by="camera_model", sort_order="asc"))
    assert [x.exif.camera_model for x in res_model.items] == ["A7IV", "EOS R5", "RX100"]

    # Sort by file_name asc
    res_name = use_case.execute(SearchPhotosQuery(sort_by="file_name", sort_order="asc"))
    assert [x.file_info.name for x in res_name.items] == ["photo1.jpg", "photo2.jpg", "photo3.jpg"]

