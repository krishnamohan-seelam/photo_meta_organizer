"""Integration tests for the /api/index directory indexing endpoint."""

import os
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from photo_meta_organizer.api.app import create_app


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_index_api.json")


@pytest.fixture
def photos_dir(tmp_path):
    folder = tmp_path / "photos"
    folder.mkdir()
    # Create 2 simple sample test images
    for i in range(2):
        img_path = folder / f"sample_{i}.jpg"
        img = Image.new("RGB", (100, 100), color=(i * 50, 100, 150))
        img.save(str(img_path))
    return str(folder)


@pytest.fixture
def client(db_path):
    app = create_app(db_path=db_path)
    return TestClient(app)


def test_index_directory_success(client, photos_dir):
    """Test successful indexing of a valid directory via POST /api/index."""
    response = client.post("/api/index", json={"folder_path": photos_dir, "num_workers": 2})
    assert response.status_code == 200
    data = response.json()
    assert data["indexed_count"] == 2
    assert "Successfully indexed 2 photo(s)" in data["message"]


def test_index_directory_not_found(client):
    """Test that a non-existent directory returns 400."""
    response = client.post("/api/index", json={"folder_path": "/non/existent/path/xyz"})
    assert response.status_code == 400
    assert "does not exist or is not a directory" in response.json()["detail"]
