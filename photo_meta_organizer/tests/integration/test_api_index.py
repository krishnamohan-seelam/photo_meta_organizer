"""Integration tests for /api/index (PMO-18: a background job, not a blocking request)."""

import threading

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from photo_meta_organizer.api.app import create_app
from tests.conftest import wait_for_job


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_index_api.db")


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
    with TestClient(create_app(db_path=db_path)) as c:
        yield c


def test_index_directory_returns_a_job_that_succeeds(client, photos_dir):
    response = client.post("/api/index", json={"folder_path": photos_dir, "num_workers": 2})
    assert response.status_code == 202
    job = response.json()
    assert job["kind"] == "index"
    assert job["status"] in ("queued", "running", "succeeded")

    done = wait_for_job(client, job)
    assert done["status"] == "succeeded"
    assert done["counts"] == {"total": 2, "indexed": 2, "failed": 0}
    assert (done["total"], done["processed"], done["failed_count"]) == (2, 2, 0)
    assert "Indexed 2 photo(s)" in done["message"]
    assert client.get("/api/photos").json()["total_count"] == 2


def test_index_reports_per_file_failures(client, photos_dir, monkeypatch):
    from photo_meta_organizer.api.routes import photos_router
    from photo_meta_organizer.infrastructure.extractors.disk_metadata_extractor import (
        DiskMetaDataExtractor,
    )

    class OneBadFile(DiskMetaDataExtractor):
        def extract(self, file_handle, stream):
            if file_handle.filename == "sample_0.jpg":
                raise OSError("unreadable sector")
            return super().extract(file_handle, stream)

    monkeypatch.setattr(photos_router, "DiskMetaDataExtractor", OneBadFile)
    done = wait_for_job(client, client.post("/api/index", json={"folder_path": photos_dir}).json())

    assert done["status"] == "succeeded"
    assert done["counts"] == {"total": 2, "indexed": 1, "failed": 1}
    assert done["failed_count"] == 1
    assert len(done["errors"]) == 1
    assert "sample_0.jpg" in done["errors"][0] and "unreadable sector" in done["errors"][0]
    assert "1 file(s) failed" in done["message"]


def test_index_directory_not_found(client):
    response = client.post("/api/index", json={"folder_path": "/non/existent/path/xyz"})
    assert response.status_code == 400
    assert "does not exist or is not a directory" in response.json()["detail"]


def test_unknown_job_is_404(client):
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.post("/api/jobs/nope/cancel").status_code == 404


def test_jobs_list_includes_the_job(client, photos_dir):
    job = client.post("/api/index", json={"folder_path": photos_dir}).json()
    wait_for_job(client, job)
    assert [j["id"] for j in client.get("/api/jobs").json()] == [job["id"]]


class TestConflictAndCancel:
    """Uses a gated extractor so the job is provably still running."""

    @pytest.fixture
    def gate(self, monkeypatch):
        from photo_meta_organizer.api.routes import photos_router
        from photo_meta_organizer.infrastructure.extractors.disk_metadata_extractor import (
            DiskMetaDataExtractor,
        )

        release = threading.Event()
        entered = threading.Event()

        class GatedExtractor(DiskMetaDataExtractor):
            def extract(self, file_handle, stream):
                entered.set()
                release.wait(10)
                return super().extract(file_handle, stream)

        monkeypatch.setattr(photos_router, "DiskMetaDataExtractor", GatedExtractor)
        yield entered, release
        release.set()

    def test_second_job_on_same_folder_is_409(self, client, photos_dir, gate):
        entered, release = gate
        first = client.post("/api/index", json={"folder_path": photos_dir, "num_workers": 1})
        assert first.status_code == 202
        assert entered.wait(10)

        second = client.post("/api/index", json={"folder_path": photos_dir})
        assert second.status_code == 409
        assert first.json()["id"] in second.json()["detail"]

        release.set()
        assert wait_for_job(client, first.json())["status"] == "succeeded"

    def test_cancel_stops_a_running_job(self, client, tmp_path, gate):
        entered, release = gate
        folder = tmp_path / "many"
        folder.mkdir()
        for i in range(30):
            Image.new("RGB", (8, 8), (i, i, i)).save(folder / f"p{i}.png")

        job = client.post("/api/index", json={"folder_path": str(folder), "num_workers": 1}).json()
        assert entered.wait(10)
        cancel = client.post(f"/api/jobs/{job['id']}/cancel")
        assert cancel.status_code == 202
        assert cancel.json()["cancel_requested"] is True
        release.set()

        done = wait_for_job(client, job)
        assert done["status"] == "cancelled"
        assert done["counts"]["indexed"] < 30
        assert client.get("/api/photos").json()["total_count"] == done["counts"]["indexed"]
