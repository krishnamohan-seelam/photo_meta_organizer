"""POST /api/geo/clusters: grid clusters of geotagged photos for the Map view."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from photo_meta_organizer.api.app import create_app
from photo_meta_organizer.domain.models import (
    GpsCoordinates,
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import SqliteRepository


def _photo(h, lat=None, lon=None, make=None, when=None):
    where = GpsCoordinates(latitude=lat, longitude=lon) if lat is not None else None
    return ImageMetadata(
        file_hash=h,
        file_info=ImageFileInfo(
            name=f"{h}.jpg", path=f"/lib/{h}.jpg", size_bytes=10, mime_type="image/jpeg"
        ),
        dimensions=ImageDimensions(width=10, height=10),
        exif=ImageExifData(camera_make=make, captured_at=when, location=where),
    )


@pytest.fixture
def client(tmp_path):
    path = str(tmp_path / "geo.db")
    repo = SqliteRepository(path)
    repo.save_many(
        [
            _photo("tokyo1", 35.68, 139.65, "Sony", datetime(2026, 1, 1)),
            _photo("tokyo2", 35.682, 139.655, "Sony", datetime(2026, 1, 2)),
            _photo("kyoto", 35.01, 135.76, "Canon"),
            _photo("sf", 37.77, -122.42, "Sony"),
            _photo("nogps", make="Sony"),
        ]
    )
    repo.close()
    return TestClient(create_app(db_path=path))


def _clusters(client, **body):
    response = client.post("/api/geo/clusters", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_zoomed_out_clusters_are_labelled_by_country(client):
    body = _clusters(client, zoom=3)
    labels = sorted(c["label"] for c in body["clusters"])
    assert labels == ["Japan", "United States"]
    assert body["total_count"] == 4
    japan = next(c for c in body["clusters"] if c["label"] == "Japan")
    assert japan["count"] == 3 and japan["representative_hash"] == "tokyo2"


def test_zoomed_in_clusters_are_labelled_by_city(client):
    body = _clusters(client, zoom=10)
    labels = {c["label"]: c["count"] for c in body["clusters"]}
    assert labels == {
        "Tokyo, Japan": 2,
        "Kyoto, Japan": 1,
        "San Francisco, United States": 1,
    }


def test_bbox_and_filters_narrow_the_result(client):
    box = {"south": 30, "west": 130, "north": 40, "east": 145}
    assert _clusters(client, zoom=10, bbox=box)["total_count"] == 3
    assert _clusters(client, zoom=10, bbox=box, camera_make="Canon")["total_count"] == 1


def test_empty_result(client):
    body = _clusters(client, zoom=5, camera_make="Leica")
    assert body == {"clusters": [], "total_count": 0}


@pytest.mark.parametrize("zoom", [-1, 21])
def test_zoom_out_of_range_is_rejected(client, zoom):
    assert client.post("/api/geo/clusters", json={"zoom": zoom}).status_code == 422


def test_bbox_out_of_range_is_rejected(client):
    box = {"south": -91, "west": 0, "north": 0, "east": 0}
    assert client.post("/api/geo/clusters", json={"zoom": 3, "bbox": box}).status_code == 422


def test_search_within_a_map_area(client):
    box = {"south": 30, "west": 130, "north": 40, "east": 145}
    response = client.post("/api/search", json={"within": box, "sort_by": "file_name"})
    assert response.status_code == 200
    assert [p["file_hash"] for p in response.json()["items"]] == ["kyoto", "tokyo1", "tokyo2"]


def test_search_within_rejects_an_impossible_area(client):
    box = {"south": 0, "west": 0, "north": 95, "east": 0}
    assert client.post("/api/search", json={"within": box}).status_code == 422
