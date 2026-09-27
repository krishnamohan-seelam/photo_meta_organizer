"""PMO-28: ZIP and JSON export of selected photos."""

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from tests.conftest import wait_for_job

from photo_meta_organizer.api.app import create_app
from photo_meta_organizer.api.routes import export_router


@pytest.fixture
def library(tmp_path):
    folder = tmp_path / "lib"
    (folder / "sub").mkdir(parents=True)
    Image.new("RGB", (16, 16), "red").save(folder / "a.jpg")
    Image.new("RGB", (16, 16), "blue").save(folder / "b.jpg")
    Image.new("RGB", (16, 16), "green").save(folder / "sub" / "a.jpg")  # same name
    return folder


@pytest.fixture
def client(tmp_path, library):
    app = create_app(db_path=str(tmp_path / "e.db"), cache_dir=str(tmp_path / "thumbs"))
    with TestClient(app) as c:
        done = wait_for_job(c, c.post("/api/index", json={"folder_path": str(library)}).json())
        assert done["counts"]["indexed"] == 3
        yield c


def _hashes(client) -> dict[str, str]:
    """path -> hash"""
    return {
        p["file_info"]["path"]: p["file_hash"] for p in client.get("/api/photos").json()["items"]
    }


def _zip(resp) -> zipfile.ZipFile:
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/zip"
    assert resp.headers["content-disposition"].startswith("attachment; filename=")
    return zipfile.ZipFile(io.BytesIO(resp.content))


class TestZipExport:
    def test_zip_holds_the_original_bytes(self, client, library):
        by_path = _hashes(client)
        a = by_path[str((library / "a.jpg").resolve())]
        b = by_path[str((library / "b.jpg").resolve())]

        resp = client.post("/api/export/zip", json={"photo_hashes": [a, b]})

        archive = _zip(resp)
        assert sorted(archive.namelist()) == ["a.jpg", "b.jpg"]
        assert archive.read("a.jpg") == (library / "a.jpg").read_bytes()
        assert resp.headers["x-export-files"] == "2"
        assert resp.headers["x-export-skipped"] == "0"
        expected = (library / "a.jpg").stat().st_size + (library / "b.jpg").stat().st_size
        assert resp.headers["x-export-bytes"] == str(expected)

    def test_same_file_names_do_not_collide(self, client):
        archive = _zip(
            client.post("/api/export/zip", json={"photo_hashes": list(_hashes(client).values())})
        )
        assert sorted(archive.namelist()) == ["a (2).jpg", "a.jpg", "b.jpg"]

    def test_missing_and_unknown_photos_are_reported_not_fatal(self, client, library):
        by_path = _hashes(client)
        (library / "b.jpg").unlink()

        resp = client.post("/api/export/zip", json={"photo_hashes": [*by_path.values(), "nope"]})

        archive = _zip(resp)
        assert "b.jpg" not in archive.namelist()
        assert resp.headers["x-export-files"] == "2"
        assert resp.headers["x-export-skipped"] == "2"
        report = archive.read("export_report.txt").decode()
        assert "b.jpg" in report and "file is missing" in report
        assert "nope" in report and "not in the library" in report

    def test_nothing_exportable_is_404(self, client, library):
        by_path = _hashes(client)
        for f in library.rglob("*.jpg"):
            f.unlink()
        resp = client.post("/api/export/zip", json={"photo_hashes": list(by_path.values())})
        assert resp.status_code == 404
        assert "none of the selected" in resp.json()["detail"].lower()

    def test_size_guard(self, client, monkeypatch):
        monkeypatch.setattr(export_router, "MAX_ZIP_BYTES", 10)
        resp = client.post("/api/export/zip", json={"photo_hashes": list(_hashes(client).values())})
        assert resp.status_code == 413
        assert "too large" in resp.json()["detail"].lower()

    def test_empty_selection_is_422(self, client):
        assert client.post("/api/export/zip", json={"photo_hashes": []}).status_code == 422


class TestJsonExport:
    def test_selection(self, client):
        wanted = sorted(_hashes(client).values())[:2]
        resp = client.post("/api/export/json", json={"photo_hashes": wanted})
        assert resp.status_code == 200
        assert resp.headers["content-disposition"].startswith("attachment; filename=")
        records = json.loads(resp.content)
        assert sorted(r["file_hash"] for r in records) == wanted
        assert {"file_info", "exif", "dimensions", "rating", "labels"} <= set(records[0])

    def test_whole_library_when_nothing_is_selected(self, client):
        for body in ({}, {"photo_hashes": None}):
            records = json.loads(client.post("/api/export/json", json=body).content)
            assert len(records) == 3

    def test_unknown_hashes_are_left_out(self, client):
        records = json.loads(
            client.post("/api/export/json", json={"photo_hashes": ["nope"]}).content
        )
        assert records == []
