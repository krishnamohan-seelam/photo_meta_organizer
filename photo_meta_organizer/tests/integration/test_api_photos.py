"""Integration tests for FastAPI photo metadata REST API endpoints."""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from photo_meta_organizer.api.app import create_app
from photo_meta_organizer.domain.models import (
    GpsCoordinates,
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.infrastructure.repositories.tinydb_repository import (
    TinyDBRepository,
)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_api.json")


@pytest.fixture
def sample_metadata():
    return [
        ImageMetadata(
            file_hash="aaaa1111",
            file_info=ImageFileInfo(
                name="beach.jpg", path="/photos/beach.jpg",
                size_bytes=1024, mime_type="image/jpeg",
            ),
            dimensions=ImageDimensions(width=1920, height=1080),
            exif=ImageExifData(
                camera_make="Sony", camera_model="A7IV",
                captured_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
                location=GpsCoordinates(latitude=37.7749, longitude=-122.4194),
            ),
            labels=["beach", "vacation"],
        ),
        ImageMetadata(
            file_hash="bbbb2222",
            file_info=ImageFileInfo(
                name="mountain.jpg", path="/photos/mountain.jpg",
                size_bytes=3072, mime_type="image/jpeg",
            ),
            dimensions=ImageDimensions(width=4000, height=3000),
            exif=ImageExifData(
                camera_make="Canon", camera_model="EOS R5",
                captured_at=datetime(2024, 3, 20, tzinfo=timezone.utc),
            ),
            labels=["mountain", "landscape"],
        ),
    ]


@pytest.fixture
def client(db_path, sample_metadata):
    app = create_app(db_path=db_path)
    repo = TinyDBRepository(db_path=db_path)
    for item in sample_metadata:
        repo.save(item)
    repo.close()
    # Recreate app so indexes are loaded from pre-populated db
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
# POST /api/search
# ============================================================

def test_search_by_camera_make(client):
    resp = client.post("/api/search", json={"camera_make": "Sony"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 1
    assert data["items"][0]["exif"]["camera_make"] == "Sony"


def test_search_by_date_range(client):
    resp = client.post("/api/search", json={
        "date_start": "2024-03-01T00:00:00Z",
        "date_end": "2024-03-31T23:59:59Z",
    })
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
    resp = client.post("/api/search", json={
        "location_lat": 37.7749,
        "location_lon": -122.4194,
        "radius_km": 5.0,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 1
    assert data["items"][0]["file_hash"] == "aaaa1111"


def test_search_no_filters_returns_all(client):
    resp = client.post("/api/search", json={})
    assert resp.status_code == 200
    assert resp.json()["total_count"] == 2


def test_search_with_pagination(client):
    resp = client.post("/api/search", json={
        "page": 1, "page_size": 1,
        "sort_by": "size_bytes", "sort_order": "asc",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_pages"] == 2
    assert len(data["items"]) == 1
