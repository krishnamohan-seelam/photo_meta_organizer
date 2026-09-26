"""PMO-26: with a per-launch token, only the desktop shell's own requests get in."""

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from photo_meta_organizer.api.app import create_app
from photo_meta_organizer.api.auth import TOKEN_COOKIE
from photo_meta_organizer.application.settings import Settings
from tests.conftest import wait_for_job

TOKEN = "s3cret-per-launch-token"


@pytest.fixture
def app(tmp_path):
    photos = tmp_path / "photos"
    photos.mkdir()
    Image.new("RGB", (40, 30), "blue").save(photos / "a.jpg")
    settings = Settings(db_path=tmp_path / "t.db", cache_dir=tmp_path / "c", api_token=TOKEN)
    application = create_app(settings=settings)
    with TestClient(application, cookies={TOKEN_COOKIE: TOKEN}) as authed:
        wait_for_job(authed, authed.post("/api/index", json={"folder_path": str(photos)}).json())
    return application


def _anon(app):
    return TestClient(app)


def _authed(app):
    return TestClient(app, cookies={TOKEN_COOKIE: TOKEN})


@pytest.mark.parametrize("path", ["/api/photos", "/api/jobs", "/api/facets", "/", "/docs"])
def test_requests_without_the_cookie_get_401(app, path):
    resp = _anon(app).get(path)
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Not authenticated"}


def test_writes_without_the_cookie_get_401(app, tmp_path):
    client = _anon(app)
    assert client.post("/api/index", json={"folder_path": str(tmp_path)}).status_code == 401
    assert client.post("/api/photos/batch", json={"photo_hashes": [], "action": "delete"}).status_code == 401


def test_wrong_token_gets_401(app):
    client = TestClient(app, cookies={TOKEN_COOKIE: "guess"})
    assert client.get("/api/photos").status_code == 401


def test_token_in_header_or_query_is_not_accepted(app):
    client = _anon(app)
    assert client.get(f"/api/photos?token={TOKEN}").status_code == 401
    assert client.get("/api/photos", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 401


def test_health_stays_open_for_the_shell_startup_probe(app):
    resp = _anon(app).get("/health")
    assert resp.status_code == 200 and resp.json()["status"] == "ok"
    assert "photo_count" not in resp.json()  # nothing about the library without the cookie


def test_cookie_holder_gets_everything_including_images(app):
    client = _authed(app)
    photos = client.get("/api/photos").json()
    assert photos["total_count"] == 1
    file_hash = photos["items"][0]["file_hash"]
    assert client.get(f"/api/photos/{file_hash}/thumbnail").status_code == 200
    assert client.get(f"/api/photos/{file_hash}/raw").status_code == 200
    assert client.get("/health").json()["photo_count"] == 1


def test_without_a_token_the_api_stays_open(tmp_path):
    client = TestClient(create_app(settings=Settings(db_path=tmp_path / "open.db")))
    assert client.get("/api/photos").status_code == 200
    assert client.get("/health").json()["photo_count"] == 0


def test_settings_read_the_token_from_the_environment_and_hide_it():
    s = Settings.from_env({"PMO_API_TOKEN": TOKEN})
    assert s.api_token == TOKEN
    assert TOKEN not in repr(s)
    assert Settings.from_env({"PMO_API_TOKEN": "  "}).api_token is None
