"""PMO-03: the search API accepts tz-suffixed or naive bounds against naive stored times."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from photo_meta_organizer.api.app import create_app
from photo_meta_organizer.domain.models import (
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import (
    SqliteRepository,
)


@pytest.fixture
def client(tmp_path):
    path = str(tmp_path / "dt.db")
    repo = SqliteRepository(path)
    repo.save(
        ImageMetadata(
            file_hash="h1",
            file_info=ImageFileInfo(
                name="a.jpg", path="/a.jpg", size_bytes=1, mime_type="image/jpeg"
            ),
            dimensions=ImageDimensions(width=1, height=1),
            exif=ImageExifData(captured_at=datetime(2026, 3, 1, 12, 0, 0)),
        )
    )
    repo.close()
    return TestClient(create_app(db_path=path))


@pytest.mark.parametrize(
    "start",
    [
        "2026-01-01",
        "2026-01-01T00:00:00",
        "2026-01-01T00:00:00Z",
        "2026-01-01T00:00:00+02:00",
    ],
)
def test_search_accepts_any_bound_format(client, start):
    resp = client.post(
        "/api/search", json={"date_start": start, "date_end": "2026-12-31T00:00:00Z"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total_count"] == 1


def test_search_excludes_out_of_range(client):
    resp = client.post("/api/search", json={"date_start": "2027-01-01T00:00:00Z"})
    assert resp.status_code == 200
    assert resp.json()["total_count"] == 0
