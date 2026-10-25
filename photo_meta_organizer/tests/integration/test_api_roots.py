"""Roots, scan on start and the first-run suggestions (ADR-003 R11, ticket 09)."""

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from tests.conftest import wait_for_job

from photo_meta_organizer.api.app import create_app
from photo_meta_organizer.application.settings import Settings
from photo_meta_organizer.domain.models import (
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)


@pytest.fixture
def settings(tmp_path):
    return Settings(db_path=tmp_path / "roots.db", cache_dir=tmp_path / "thumbs")


@pytest.fixture
def library(tmp_path):
    folder = tmp_path / "photos"
    folder.mkdir()
    for name in ("a", "b"):
        Image.new("RGB", (8, 8), name == "a" and "red" or "blue").save(folder / f"{name}.jpg")
    return folder


def _scan_jobs(client: TestClient) -> list[dict]:
    return [j for j in client.get("/api/jobs").json() if j["kind"] == "sync"]


def test_a_new_library_has_no_roots(settings) -> None:
    with TestClient(create_app(settings=settings)) as client:
        assert client.get("/api/roots").json() == []


def test_adding_a_root_remembers_it_and_scans_it(settings, library) -> None:
    with TestClient(create_app(settings=settings)) as client:
        response = client.post("/api/roots", json={"folder_path": str(library)})
        assert response.status_code == 201
        root = response.json()
        assert root["online"] is True and root["job_id"]
        job = wait_for_job(client, client.get(f"/api/jobs/{root['job_id']}").json())
        assert job["status"] == "succeeded" and job["counts"]["new"] == 2
        assert [r["path"] for r in client.get("/api/roots").json()] == [root["path"]]
        # Adding it again is harmless and does not duplicate it.
        client.post("/api/roots", json={"folder_path": str(library), "scan": False})
        assert len(client.get("/api/roots").json()) == 1


def test_a_root_can_be_added_without_scanning(settings, library) -> None:
    with TestClient(create_app(settings=settings)) as client:
        root = client.post("/api/roots", json={"folder_path": str(library), "scan": False}).json()
        assert root["job_id"] is None and _scan_jobs(client) == []


def test_a_path_that_is_not_a_folder_is_a_400(settings, tmp_path) -> None:
    with TestClient(create_app(settings=settings)) as client:
        assert (
            client.post("/api/roots", json={"folder_path": str(tmp_path / "no")}).status_code == 400
        )
        assert client.get("/api/roots").json() == []


def test_removing_a_root_keeps_its_photos(settings, library) -> None:
    with TestClient(create_app(settings=settings)) as client:
        root = client.post("/api/roots", json={"folder_path": str(library)}).json()
        wait_for_job(client, client.get(f"/api/jobs/{root['job_id']}").json())
        assert client.delete("/api/roots", params={"path": root["path"]}).status_code == 204
        assert client.get("/api/roots").json() == []
        assert client.delete("/api/roots", params={"path": root["path"]}).status_code == 404
        assert client.get("/health").json()["photo_count"] == 2


def test_roots_are_scanned_when_the_app_starts(settings, library) -> None:
    with TestClient(create_app(settings=settings)) as client:
        client.post("/api/roots", json={"folder_path": str(library), "scan": False})
    Image.new("RGB", (8, 8), "green").save(library / "c.jpg")

    with TestClient(create_app(settings=settings)) as client:
        [job] = _scan_jobs(client)
        done = wait_for_job(client, job)
        assert done["status"] == "succeeded" and done["counts"]["new"] == 3
        assert client.get("/health").json()["photo_count"] == 3


def test_scanning_on_start_can_be_turned_off(settings, library) -> None:
    with TestClient(create_app(settings=settings)) as client:
        client.post("/api/roots", json={"folder_path": str(library), "scan": False})
    off = Settings(**{**settings.__dict__, "scan_on_start": False})
    with TestClient(create_app(settings=off)) as client:
        assert _scan_jobs(client) == []


def test_an_offline_root_is_listed_and_skipped_without_an_error(settings, library) -> None:
    with TestClient(create_app(settings=settings)) as client:
        client.post("/api/roots", json={"folder_path": str(library), "scan": False})
    for f in library.iterdir():
        f.unlink()
    library.rmdir()

    with TestClient(create_app(settings=settings)) as client:
        [root] = client.get("/api/roots").json()
        assert root["online"] is False
        assert _scan_jobs(client) == []


def _library_with_photos(app, *folders: str) -> None:
    repo = app.state.services.repository
    for i, folder in enumerate(folders):
        path = f"{folder}/p{i}.jpg"
        repo.save(
            ImageMetadata(
                file_hash=f"h{i}",
                file_info=ImageFileInfo(
                    name=f"p{i}.jpg", path=path, size_bytes=1, mime_type="image/jpeg"
                ),
                dimensions=ImageDimensions(width=1, height=1),
                exif=ImageExifData(),
            )
        )


def test_an_existing_library_is_offered_the_folders_found_in_its_files(settings, tmp_path) -> None:
    app = create_app(settings=settings)
    a, b = str(tmp_path / "one"), str(tmp_path / "two")
    _library_with_photos(app, a, a, b)
    with TestClient(app) as client:
        body = client.get("/api/roots/suggestions").json()
    assert [(s["path"], s["file_count"]) for s in body["suggestions"]] == [(a, 2), (b, 1)]
    assert body["dismissed"] is False


def test_nothing_is_watched_until_the_user_adds_a_root(settings, tmp_path) -> None:
    app = create_app(settings=settings)
    _library_with_photos(app, str(tmp_path / "one"))
    with TestClient(app) as client:
        client.get("/api/roots/suggestions")
        assert client.get("/api/roots").json() == []


def test_skipping_the_offer_is_remembered_and_leaves_watching_off(settings, tmp_path) -> None:
    app = create_app(settings=settings)
    _library_with_photos(app, str(tmp_path / "one"))
    with TestClient(app) as client:
        assert client.post("/api/roots/suggestions/dismiss").status_code == 204
    with TestClient(create_app(settings=settings)) as client:
        body = client.get("/api/roots/suggestions").json()
        assert body == {"suggestions": [], "dismissed": True}
        assert client.get("/api/roots").json() == []


def test_a_library_with_roots_is_not_offered_suggestions(settings, library) -> None:
    with TestClient(create_app(settings=settings)) as client:
        client.post("/api/roots", json={"folder_path": str(library), "scan": False})
        assert client.get("/api/roots/suggestions").json()["suggestions"] == []


# ---- folder watching (ticket 10)


@pytest.fixture
def watched(settings, monkeypatch):
    from tests.fakes import FakeFolderWatcher

    from photo_meta_organizer.application import composition

    fake = FakeFolderWatcher()
    monkeypatch.setattr(composition, "build_folder_watcher", lambda: fake)
    on = Settings(**{**settings.__dict__, "watch_folders": True})
    return fake, on


def test_the_app_watches_its_roots_while_it_runs(watched, library) -> None:
    fake, on = watched
    with TestClient(create_app(settings=on)) as client:
        client.post("/api/roots", json={"folder_path": str(library), "scan": False})
        assert client.post("/api/roots/recheck").status_code == 204
        assert fake.started == []  # the watcher looks at the next tick, not in the request
    assert fake.stopped == 0  # nothing was watched yet


def test_roots_stored_before_the_start_are_watched_from_the_start(watched, library) -> None:
    fake, on = watched
    with TestClient(create_app(settings=on)) as client:
        client.post("/api/roots", json={"folder_path": str(library), "scan": False})
    with TestClient(create_app(settings=on)):
        assert fake.started == [(str(library),)]
    assert fake.stopped == 1  # stopped with the app


def test_no_watcher_runs_when_folder_watching_is_off(watched, library) -> None:
    fake, _ = watched
    off = Settings(db_path=watched[1].db_path, cache_dir=watched[1].cache_dir)
    with TestClient(create_app(settings=off)) as client:
        client.post("/api/roots", json={"folder_path": str(library), "scan": False})
        assert client.post("/api/roots/recheck").status_code == 204
    assert fake.started == []


def test_watching_is_on_unless_the_environment_turns_it_off() -> None:
    assert Settings.from_env({}).watch_folders is True
    assert Settings.from_env({"PMO_WATCH_FOLDERS": "0"}).watch_folders is False
    assert Settings.from_env({"PMO_WATCH_FOLDERS": "no"}).watch_folders is False
