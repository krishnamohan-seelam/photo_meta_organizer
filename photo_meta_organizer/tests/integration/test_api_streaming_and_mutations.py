"""Integration tests for photo streaming, thumbnail caching, batch mutations, and collections endpoints."""

import os
from datetime import datetime, timezone
from PIL import Image
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
from photo_meta_organizer.infrastructure.thumbnail_service import ThumbnailService


@pytest.fixture
def test_image_file(tmp_path):
    """Create a real test image file on disk using Pillow."""
    img_path = str(tmp_path / "sample_test_image.jpg")
    img = Image.new("RGB", (800, 600), color=(100, 150, 200))
    img.save(img_path, format="JPEG")
    return img_path


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_api_streaming.db")


@pytest.fixture
def sample_metadata(test_image_file):
    return [
        ImageMetadata(
            file_hash="hash1111",
            file_info=ImageFileInfo(
                name="sample_test_image.jpg",
                path=test_image_file,
                size_bytes=os.path.getsize(test_image_file),
                mime_type="image/jpeg",
            ),
            dimensions=ImageDimensions(width=800, height=600),
            exif=ImageExifData(
                camera_make="Sony",
                camera_model="A7IV",
                captured_at=datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc),
                location=GpsCoordinates(latitude=35.6895, longitude=139.6917),
            ),
            labels=["travel", "tokyo"],
            rating=4,
            flagged=True,
        ),
        ImageMetadata(
            file_hash="hash2222",
            file_info=ImageFileInfo(
                name="missing.jpg",
                path="/nonexistent/path/missing.jpg",
                size_bytes=2048,
                mime_type="image/jpeg",
            ),
            dimensions=ImageDimensions(width=1920, height=1080),
            exif=ImageExifData(
                camera_make="Canon",
                camera_model="EOS R5",
                captured_at=datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
            ),
            labels=["landscape"],
            rating=2,
            flagged=False,
        ),
    ]


@pytest.fixture
def client(db_path, sample_metadata):
    repo = SqliteRepository(db_path=db_path)
    for m in sample_metadata:
        repo.save(m)
    repo.close()
    app = create_app(db_path=db_path)
    return TestClient(app)


class TestThumbnailAndRawStreaming:
    """Tests for thumbnail generation and raw image streaming."""

    def test_get_photo_thumbnail_success(self, client):
        resp = client.get("/api/photos/hash1111/thumbnail?w=200&h=200")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/webp"
        assert len(resp.content) > 0
        assert "Cache-Control" in resp.headers

    def test_get_photo_thumbnail_not_found_hash(self, client):
        resp = client.get("/api/photos/nonexistent_hash/thumbnail")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_photo_thumbnail_missing_source_file(self, client):
        resp = client.get("/api/photos/hash2222/thumbnail")
        assert resp.status_code == 404
        assert "could not be generated" in resp.json()["detail"].lower()

    def test_get_photo_raw_success(self, client):
        resp = client.get("/api/photos/hash1111/raw")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/jpeg"
        assert len(resp.content) > 0

    def test_get_photo_raw_not_found_hash(self, client):
        resp = client.get("/api/photos/nonexistent_hash/raw")
        assert resp.status_code == 404

    def test_get_photo_raw_missing_source_file(self, client):
        resp = client.get("/api/photos/hash2222/raw")
        assert resp.status_code == 404
        assert "does not exist" in resp.json()["detail"].lower()


class TestPatchAndBatchMutations:
    """Tests for metadata mutation endpoints."""

    def test_patch_photo_ratings_and_flags(self, client):
        resp = client.patch(
            "/api/photos/hash1111",
            json={"rating": 5, "flagged": False, "add_tags": ["favorite"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["rating"] == 5
        assert data["flagged"] is False
        assert "favorite" in data["labels"]

    def test_patch_photo_remove_tags(self, client):
        resp = client.patch(
            "/api/photos/hash1111",
            json={"remove_tags": ["travel"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "travel" not in data["labels"]

    def test_patch_photo_not_found(self, client):
        resp = client.patch(
            "/api/photos/unknown_hash",
            json={"rating": 3},
        )
        assert resp.status_code == 404

    def test_batch_update_set_rating(self, client):
        resp = client.post(
            "/api/photos/batch",
            json={
                "photo_hashes": ["hash1111", "hash2222"],
                "action": "set_rating",
                "value": 5,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["updated_count"] == 2

        # Verify
        p1 = client.get("/api/photos/hash1111").json()
        p2 = client.get("/api/photos/hash2222").json()
        assert p1["rating"] == 5
        assert p2["rating"] == 5

    def test_batch_update_add_tag(self, client):
        resp = client.post(
            "/api/photos/batch",
            json={
                "photo_hashes": ["hash1111", "hash2222"],
                "action": "add_tag",
                "value": "curated-2026",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["updated_count"] == 2

        p1 = client.get("/api/photos/hash1111").json()
        assert "curated-2026" in p1["labels"]

    def test_batch_update_set_flag(self, client):
        resp = client.post(
            "/api/photos/batch",
            json={
                "photo_hashes": ["hash1111", "hash2222"],
                "action": "set_flag",
                "value": True,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["updated_count"] == 2


class TestCollectionsApi:
    """Tests for collection CRUD endpoints."""

    def test_create_and_list_collections(self, client):
        create_resp = client.post(
            "/api/collections",
            json={
                "name": "Japan Trip 2026",
                "description": "Photos from Tokyo and Kyoto",
                "photo_hashes": ["hash1111"],
            },
        )
        assert create_resp.status_code == 200
        created = create_resp.json()
        assert created["name"] == "Japan Trip 2026"
        assert created["photo_hashes"] == ["hash1111"]

        list_resp = client.get("/api/collections")
        assert list_resp.status_code == 200
        items = list_resp.json()
        assert len(items) >= 1
        assert any(c["name"] == "Japan Trip 2026" for c in items)


class TestThumbnailServiceUnit:
    """Unit tests for ThumbnailService methods."""

    def test_thumbnail_service_clear_cache(self, tmp_path, test_image_file):
        service = ThumbnailService(cache_dir=str(tmp_path / "thumbs"))
        thumb = service.generate_thumbnail(test_image_file, "testhash", 100, 100)
        assert thumb is not None
        assert len(thumb) > 0

        cleared = service.clear_cache()
        assert cleared >= 1
