"""PMO-27: the search API carries every filter the UI uses, plus stats and "all matches"."""

from datetime import datetime

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
from photo_meta_organizer.infrastructure.repositories.sqlite_collection_repository import (
    SqliteCollectionRepository,
)
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import (
    SqliteRepository,
)


def _photo(h: str, *, make=None, when=None, where=None, size=1000, flagged=False, iso=None):
    return ImageMetadata(
        file_hash=h,
        file_info=ImageFileInfo(
            name=f"{h}.jpg", path=f"/lib/{h}.jpg", size_bytes=size, mime_type="image/jpeg"
        ),
        dimensions=ImageDimensions(width=2000, height=1000),
        exif=ImageExifData(camera_make=make, captured_at=when, location=where, iso=iso),
        flagged=flagged,
    )


@pytest.fixture
def client(tmp_path):
    path = str(tmp_path / "f.db")
    repo = SqliteRepository(path)
    repo.save_many(
        [
            _photo("sony1", make="Sony", when=datetime(2024, 5, 1), size=100, iso=100),
            _photo("sony2", make="Sony", when=datetime(2025, 5, 1), size=200, flagged=True),
            _photo(
                "canon", make="Canon", where=GpsCoordinates(latitude=1.0, longitude=2.0), size=300
            ),
            _photo("nikon", make="Nikon", when=datetime(2024, 1, 1), size=400, iso=100),
        ]
    )
    SqliteCollectionRepository(repo.connection, repo.lock).save("Trip", ["sony2", "nikon"])
    repo.close()
    return TestClient(create_app(db_path=path))


def _search(client, **body) -> list[str]:
    resp = client.post("/api/search", json={"sort_by": "file_name", **body})
    assert resp.status_code == 200, resp.text
    return [p["file_hash"] for p in resp.json()["items"]]


def test_camera_makes_any_of(client):
    assert _search(client, camera_makes=["Sony", "Canon"]) == ["canon", "sony1", "sony2"]


def test_unknown_capture_date(client):
    assert _search(client, has_capture_date=False) == ["canon"]


def test_has_location(client):
    assert _search(client, has_location=True) == ["canon"]


def test_collection(client):
    assert _search(client, collection="Trip") == ["nikon", "sony2"]


def test_filters_combine(client):
    assert _search(
        client,
        camera_makes=["Sony", "Nikon"],
        date_start="2024-01-01T00:00:00",
        date_end="2024-12-31T23:59:59",
    ) == ["nikon", "sony1"]


def test_unknown_sort_field_is_422(client):
    assert client.post("/api/search", json={"sort_by": "bogus"}).status_code == 422


def test_ids_returns_every_match_with_sizes(client):
    resp = client.post("/api/search/ids", json={"camera_makes": ["Sony"], "page_size": 1})
    assert resp.status_code == 200, resp.text
    assert sorted((r["file_hash"], r["size_bytes"]) for r in resp.json()) == [
        ("sony1", 100),
        ("sony2", 200),
    ]


def test_facets_include_library_stats_and_isos(client):
    body = client.get("/api/facets").json()
    assert body["stats"] == {
        "total_count": 4,
        "flagged_count": 1,
        "geotagged_count": 1,
        "undated_count": 1,
        "total_bytes": 1000,
        "avg_megapixels": 2.0,
    }
    assert body["isos"] == [{"name": "100", "count": 2}]
