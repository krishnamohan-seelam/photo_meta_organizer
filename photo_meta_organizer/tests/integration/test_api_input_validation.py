"""PMO-02: mutation endpoints must reject bad input and never poison the library.

Regression coverage for design flaw B-03: an unvalidated batch ``set_rating`` value
was persisted and then made every listing fail while building the response.
"""

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
from photo_meta_organizer.infrastructure.repositories.tinydb_repository import TinyDBRepository


def _photo(file_hash: str, name: str) -> ImageMetadata:
    return ImageMetadata(
        file_hash=file_hash,
        file_info=ImageFileInfo(
            name=name, path=f"/photos/{name}", size_bytes=10, mime_type="image/jpeg"
        ),
        dimensions=ImageDimensions(width=10, height=10),
        exif=ImageExifData(captured_at=datetime(2026, 1, 1, 12, 0, 0)),
        labels=["a"],
        rating=3,
    )


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "validation.json")
    repo = TinyDBRepository(path)
    repo.save(_photo("h1", "one.jpg"))
    repo.save(_photo("h2", "two.jpg"))
    repo.close()
    return path


@pytest.fixture
def client(db_path):
    return TestClient(create_app(db_path=db_path))


def _batch(client, action, value=None, hashes=("h1", "h2")):
    return client.post(
        "/api/photos/batch",
        json={"photo_hashes": list(hashes), "action": action, "value": value},
    )


class TestBatchValidation:
    def test_unknown_action_is_rejected(self, client):
        resp = _batch(client, "bogus", 1)
        assert resp.status_code == 422

    @pytest.mark.parametrize("bad", ["abc", 0, 6, -1, 3.5, True, [4]])
    def test_set_rating_rejects_invalid_values(self, client, bad):
        resp = _batch(client, "set_rating", bad)
        assert resp.status_code == 422
        # Nothing was stored: the library is still listable and unchanged.
        listing = client.get("/api/photos")
        assert listing.status_code == 200
        assert {p["rating"] for p in listing.json()["items"]} == {3}

    def test_set_rating_accepts_bounds_and_null(self, client):
        assert _batch(client, "set_rating", 1).status_code == 200
        assert _batch(client, "set_rating", 5).status_code == 200
        assert _batch(client, "set_rating", None).status_code == 200
        assert client.get("/api/photos/h1").json()["rating"] is None

    @pytest.mark.parametrize("bad", ["yes", 1, 0, None])
    def test_set_flag_requires_a_boolean(self, client, bad):
        assert _batch(client, "set_flag", bad).status_code == 422

    @pytest.mark.parametrize("action", ["add_tag", "remove_tag"])
    @pytest.mark.parametrize("bad", [5, "", "   ", None, ["x"]])
    def test_tag_actions_require_a_non_empty_string(self, client, action, bad):
        assert _batch(client, action, bad).status_code == 422

    def test_empty_hash_list_is_rejected(self, client):
        assert _batch(client, "set_flag", True, hashes=()).status_code == 422

    def test_unknown_hashes_are_not_counted(self, client):
        resp = _batch(client, "set_flag", True, hashes=("h1", "nope"))
        assert resp.status_code == 200
        assert resp.json()["updated_count"] == 1

    def test_delete_is_reported_as_deleted_not_updated(self, client):
        resp = _batch(client, "delete", None, hashes=("h1",))
        assert resp.status_code == 200
        body = resp.json()
        assert body["updated_count"] == 0
        assert body["deleted_count"] == 1
        assert client.get("/api/photos/h1").status_code == 404


class TestPatchValidation:
    def test_explicit_null_lists_do_not_crash(self, client):
        for field in ("labels", "add_tags", "remove_tags"):
            resp = client.patch("/api/photos/h1", json={field: None})
            assert resp.status_code == 200, field
        assert client.get("/api/photos/h1").json()["labels"] == ["a"]

    def test_explicit_null_rating_clears_it(self, client):
        resp = client.patch("/api/photos/h1", json={"rating": None})
        assert resp.status_code == 200
        assert resp.json()["rating"] is None

    def test_out_of_range_rating_is_rejected(self, client):
        assert client.patch("/api/photos/h1", json={"rating": 9}).status_code == 422

    def test_tag_order_is_stable_and_deduplicated(self, client):
        client.patch("/api/photos/h1", json={"add_tags": ["zeta", "alpha", "a"]})
        assert client.get("/api/photos/h1").json()["labels"] == ["a", "zeta", "alpha"]


class TestPoisonedStoreIsTolerated:
    """Records already damaged on disk (by an older version) must not break listings."""

    def test_listing_survives_a_corrupt_stored_rating(self, db_path):
        repo = TinyDBRepository(db_path)
        from tinydb import Query

        repo._table.update({"rating": "abc"}, Query().file_hash == "h1")
        repo.close()

        client = TestClient(create_app(db_path=db_path))
        listing = client.get("/api/photos")
        assert listing.status_code == 200
        ratings = {p["file_hash"]: p["rating"] for p in listing.json()["items"]}
        assert ratings["h1"] is None
        assert ratings["h2"] == 3
        assert client.get("/api/photos/h1").status_code == 200
