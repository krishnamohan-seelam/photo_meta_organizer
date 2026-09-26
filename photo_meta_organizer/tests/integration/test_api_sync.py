"""PMO-19: POST /api/sync runs an incremental sync as a background job."""

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from photo_meta_organizer.api.app import create_app
from tests.conftest import wait_for_job


@pytest.fixture
def library(tmp_path):
    folder = tmp_path / "lib"
    folder.mkdir()
    for i in range(3):
        Image.new("RGB", (16, 16), (i * 60, 10, 10)).save(folder / f"p{i}.jpg")
    return folder


@pytest.fixture
def client(tmp_path, library):
    with TestClient(create_app(db_path=str(tmp_path / "sync.db"))) as c:
        done = wait_for_job(c, c.post("/api/index", json={"folder_path": str(library)}).json())
        assert done["counts"]["indexed"] == 3
        yield c


def _sync(client, library, **flags):
    resp = client.post("/api/sync", json={"folder_path": str(library), **flags})
    assert resp.status_code == 202, resp.text
    assert resp.json()["kind"] == "sync"
    return wait_for_job(client, resp.json())


def _hash_of(client, name):
    items = client.get("/api/photos").json()["items"]
    return next(p["file_hash"] for p in items if p["file_info"]["name"] == name)


def test_deleted_file_is_removed_and_stops_being_served(client, library):
    gone = _hash_of(client, "p1.jpg")
    assert client.get(f"/api/photos/{gone}/thumbnail").status_code == 200
    (library / "p1.jpg").unlink()

    done = _sync(client, library, cleanup_deleted=True)

    assert done["status"] == "succeeded"
    assert done["counts"]["deleted"] == 1
    assert done["counts"]["unchanged"] == 2
    assert client.get("/api/photos").json()["total_count"] == 2
    assert client.get(f"/api/photos/{gone}").status_code == 404
    assert client.get(f"/api/photos/{gone}/raw").status_code == 404
    assert client.get(f"/api/photos/{gone}/thumbnail").status_code == 404


def test_deleted_file_is_kept_without_cleanup_flag(client, library):
    (library / "p1.jpg").unlink()
    done = _sync(client, library)
    assert done["counts"]["deleted"] == 0
    assert client.get("/api/photos").json()["total_count"] == 3


def test_new_and_modified_files(client, library):
    Image.new("RGB", (16, 16), "white").save(library / "new.jpg")
    old = _hash_of(client, "p0.jpg")
    Image.new("RGB", (32, 32), "black").save(library / "p0.jpg")  # size changes

    done = _sync(client, library)

    assert (done["counts"]["new"], done["counts"]["modified"]) == (1, 1)
    assert "1 new" in done["message"] and "1 modified" in done["message"]
    assert client.get("/api/photos").json()["total_count"] == 4
    assert client.get(f"/api/photos/{old}").status_code == 404


def test_dry_run_changes_nothing(client, library):
    (library / "p2.jpg").unlink()
    Image.new("RGB", (16, 16), "white").save(library / "new.jpg")

    done = _sync(client, library, cleanup_deleted=True, dry_run=True)

    assert done["counts"]["new"] == 1 and done["counts"]["deleted"] == 1
    assert done["message"].startswith("[DRY RUN]")
    assert client.get("/api/photos").json()["total_count"] == 3


def test_sync_of_another_folder_never_deletes_this_one(client, library, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    Image.new("RGB", (8, 8), "green").save(other / "o.jpg")

    done = _sync(client, other, cleanup_deleted=True)

    assert done["counts"] == {**done["counts"], "new": 1, "deleted": 0}
    assert client.get("/api/photos").json()["total_count"] == 4


def test_missing_folder_is_400(client):
    resp = client.post("/api/sync", json={"folder_path": "/no/such/folder"})
    assert resp.status_code == 400


def test_sync_errors_are_reported(client, library, monkeypatch):
    from photo_meta_organizer.api.routes import photos_router
    from photo_meta_organizer.infrastructure.extractors.disk_metadata_extractor import (
        DiskMetaDataExtractor,
    )

    class Broken(DiskMetaDataExtractor):
        def extract(self, file_handle, stream):
            raise OSError("cannot read")

    monkeypatch.setattr(photos_router, "DiskMetaDataExtractor", Broken)
    Image.new("RGB", (8, 8), "white").save(library / "new.jpg")

    done = _sync(client, library)

    assert done["status"] == "succeeded"
    assert done["counts"]["failed"] == done["failed_count"] == 1
    assert "new.jpg" in done["errors"][0]
    assert "1 error(s)" in done["message"]
