"""PMO-23: HEIC photos index with real dimensions and get thumbnails and a preview."""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from tests.conftest import make_heic, wait_for_job

from photo_meta_organizer.api.app import create_app


@pytest.fixture
def client(tmp_path):
    folder = tmp_path / "lib"
    folder.mkdir()
    make_heic(folder / "phone.heic", size=(640, 480))
    Image.new("RGB", (3000, 2000), "green").save(folder / "big.jpg")
    app = create_app(db_path=str(tmp_path / "p.db"), cache_dir=str(tmp_path / "thumbs"))
    with TestClient(app) as c:
        done = wait_for_job(c, c.post("/api/index", json={"folder_path": str(folder)}).json())
        assert done["counts"]["indexed"] == 2
        yield c


def _photo(client, name):
    items = client.get("/api/photos").json()["items"]
    return next(p for p in items if p["file_info"]["name"] == name)


def _webp_size(resp) -> tuple[int, int]:
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "image/webp"
    with Image.open(io.BytesIO(resp.content)) as img:
        return img.size


def test_heic_is_indexed_with_real_dimensions(client):
    photo = _photo(client, "phone.heic")
    assert (photo["dimensions"]["width"], photo["dimensions"]["height"]) == (640, 480)
    assert photo["file_info"]["mime_type"] == "image/heic"


def test_heic_thumbnail_and_preview(client):
    file_hash = _photo(client, "phone.heic")["file_hash"]
    assert _webp_size(client.get(f"/api/photos/{file_hash}/thumbnail?w=64&h=64")) == (64, 48)
    assert _webp_size(client.get(f"/api/photos/{file_hash}/preview")) == (640, 480)


def test_preview_is_capped_for_large_photos(client):
    file_hash = _photo(client, "big.jpg")["file_hash"]
    assert _webp_size(client.get(f"/api/photos/{file_hash}/preview")) == (2048, 1365)


def test_preview_of_unknown_photo_is_404(client):
    assert client.get("/api/photos/nope/preview").status_code == 404
