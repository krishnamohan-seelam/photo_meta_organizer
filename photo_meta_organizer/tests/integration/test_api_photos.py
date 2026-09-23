"""Integration tests for FastAPI photo metadata REST API endpoints."""

from datetime import UTC, datetime

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
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import (
    SqliteRepository,
)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_api.db")


@pytest.fixture
def sample_metadata():
    return [
        ImageMetadata(
            file_hash="aaaa1111",
            file_info=ImageFileInfo(
                name="beach.jpg",
                path="/photos/beach.jpg",
                size_bytes=1024,
                mime_type="image/jpeg",
            ),
            dimensions=ImageDimensions(width=1920, height=1080),
            exif=ImageExifData(
                camera_make="Sony",
                camera_model="A7IV",
                captured_at=datetime(2024, 1, 15, tzinfo=UTC),
                location=GpsCoordinates(latitude=37.7749, longitude=-122.4194),
            ),
            labels=["beach", "vacation"],
            rating=5,
            flagged=True,
        ),
        ImageMetadata(
            file_hash="bbbb2222",
            file_info=ImageFileInfo(
                name="mountain.jpg",
                path="/photos/mountain.jpg",
                size_bytes=3072,
                mime_type="image/jpeg",
            ),
            dimensions=ImageDimensions(width=4000, height=3000),
            exif=ImageExifData(
                camera_make="Canon",
                camera_model="EOS R5",
                captured_at=datetime(2024, 3, 20, tzinfo=UTC),
            ),
            labels=["mountain", "landscape"],
        ),
    ]


@pytest.fixture
def client(db_path, sample_metadata):
    repo = SqliteRepository(db_path=db_path)
    for item in sample_metadata:
        repo.save(item)
    repo.close()
    app = create_app(db_path=db_path)
    return TestClient(app)


# ============================================================
# Health check
# ============================================================


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["photo_count"] == 2


def test_prototype_route_is_gone(client):
    """The standalone HTML prototype was removed; its route must not linger."""
    assert client.get("/prototype").status_code == 404


def test_root_without_built_frontend_reports_it(client):
    """Without frontend/dist the root page says so instead of serving a prototype."""
    resp = client.get("/")
    assert resp.status_code in (200, 404)
    if resp.status_code == 404:
        assert "Frontend not built" in resp.text


# ============================================================
# GET /api/photos
# ============================================================


def test_list_photos_returns_all(client):
    resp = client.get("/api/photos")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 2
    assert len(data["items"]) == 2


def test_list_photos_pagination(client):
    resp = client.get("/api/photos?page=1&page_size=1&sort_by=size_bytes&sort_order=asc")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 2
    assert data["total_pages"] == 2
    assert len(data["items"]) == 1
    assert data["items"][0]["file_info"]["name"] == "beach.jpg"


def test_list_photos_sort_by_size_desc(client):
    resp = client.get("/api/photos?sort_by=size_bytes&sort_order=desc")
    assert resp.status_code == 200
    items = resp.json()["items"]
    sizes = [item["file_info"]["size_bytes"] for item in items]
    assert sizes == sorted(sizes, reverse=True)


# ============================================================
# GET /api/photos/{file_hash}
# ============================================================


def test_get_photo_by_hash_found(client):
    resp = client.get("/api/photos/aaaa1111")
    assert resp.status_code == 200
    data = resp.json()
    assert data["file_hash"] == "aaaa1111"
    assert data["file_info"]["name"] == "beach.jpg"
    assert data["exif"]["camera_make"] == "Sony"
    assert data["labels"] == ["beach", "vacation"]
    assert data["exif"]["location"]["latitude"] == 37.7749


def test_get_photo_by_hash_not_found(client):
    resp = client.get("/api/photos/nonexistent_hash")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ============================================================
# DELETE /api/photos/{file_hash}
# ============================================================


def test_delete_photo_success(client):
    resp = client.delete("/api/photos/aaaa1111")
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] is True
    assert data["file_hash"] == "aaaa1111"

    # Verify it's gone
    resp2 = client.get("/api/photos/aaaa1111")
    assert resp2.status_code == 404


def test_delete_photo_not_found(client):
    resp = client.delete("/api/photos/nonexistent_hash")
    assert resp.status_code == 404


# ============================================================
# GET /api/facets
# ============================================================


def test_facets_counts_cameras_tags_and_years(client):
    resp = client.get("/api/facets")
    assert resp.status_code == 200
    data = resp.json()
    camera_counts = {f["name"]: f["count"] for f in data["cameras"]}
    tag_counts = {f["name"]: f["count"] for f in data["tags"]}
    year_counts = {f["name"]: f["count"] for f in data["years"]}
    assert camera_counts == {"Sony": 1, "Canon": 1}
    assert tag_counts == {"beach": 1, "vacation": 1, "mountain": 1, "landscape": 1}
    assert year_counts == {"2024": 2}


def test_facets_gps_bounds_from_geotagged_photos(client):
    resp = client.get("/api/facets")
    assert resp.status_code == 200
    bounds = resp.json()["gps_bounds"]
    # Only beach.jpg is geotagged, so the bounds collapse to its single point.
    assert bounds == {
        "min_lat": 37.7749,
        "max_lat": 37.7749,
        "min_lon": -122.4194,
        "max_lon": -122.4194,
    }


# ============================================================
# POST /api/search
# ============================================================


def test_search_by_camera_make(client):
    resp = client.post("/api/search", json={"camera_make": "Sony"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 1
    assert data["items"][0]["exif"]["camera_make"] == "Sony"


def test_search_by_date_range(client):
    resp = client.post(
        "/api/search",
        json={
            "date_start": "2024-03-01T00:00:00Z",
            "date_end": "2024-03-31T23:59:59Z",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 1
    assert data["items"][0]["file_info"]["name"] == "mountain.jpg"


def test_search_by_tags(client):
    resp = client.post("/api/search", json={"tags": ["vacation"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 1
    assert "vacation" in data["items"][0]["labels"]


def test_search_by_location_radius(client):
    # Center is SF — beach.jpg should match, mountain.jpg should not
    resp = client.post(
        "/api/search",
        json={
            "location_lat": 37.7749,
            "location_lon": -122.4194,
            "radius_km": 5.0,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 1
    assert data["items"][0]["file_hash"] == "aaaa1111"


def test_search_by_term_matches_name(client):
    resp = client.post("/api/search", json={"search_term": "beach"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 1
    assert data["items"][0]["file_hash"] == "aaaa1111"


def test_search_by_rating(client):
    resp = client.post("/api/search", json={"rating": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 1
    assert data["items"][0]["file_hash"] == "aaaa1111"


def test_search_by_flagged(client):
    resp = client.post("/api/search", json={"flagged": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 1
    assert data["items"][0]["file_hash"] == "aaaa1111"


def test_search_ignores_unknown_city_field(client):
    """PMO-09: ``city`` was dropped from the schema (it had no data source);
    Pydantic ignores unknown fields by default, so this is a no-op filter."""
    resp = client.post("/api/search", json={"city": "Paris"})
    assert resp.status_code == 200
    assert resp.json()["total_count"] == 2


def test_search_no_filters_returns_all(client):
    resp = client.post("/api/search", json={})
    assert resp.status_code == 200
    assert resp.json()["total_count"] == 2


def test_search_with_pagination(client):
    resp = client.post(
        "/api/search",
        json={
            "page": 1,
            "page_size": 1,
            "sort_by": "size_bytes",
            "sort_order": "asc",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_pages"] == 2
    assert len(data["items"]) == 1
