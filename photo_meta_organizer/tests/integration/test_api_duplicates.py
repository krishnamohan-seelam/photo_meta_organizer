"""Duplicates: a photo kept at several paths (ADR-003 R11, ticket 03).

An Asset (one content hash) held by several Files is a Duplicate. The API lists every path,
counts duplicates, filters to them and lets the user hide a copy. Nothing on disk is touched.
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


def _photo(file_hash: str, path: str, size: int = 1000, mtime: datetime | None = None):
    return ImageMetadata(
        file_hash=file_hash,
        file_info=ImageFileInfo(
            name=path.rsplit("/", 1)[-1],
            path=path,
            size_bytes=size,
            mime_type="image/jpeg",
            modified_time=mtime,
        ),
        dimensions=ImageDimensions(width=10, height=10),
        exif=ImageExifData(),
    )


@pytest.fixture
def app(tmp_path):
    app = create_app(db_path=tmp_path / "dupes.db", cache_dir=tmp_path / "thumbs")
    repo = app.state.services.repository
    repo.save(_photo("solo", "/p/solo.jpg", 500))
    repo.save(_photo("pair", "/p/a/pair.jpg", 1000))
    repo.save(_photo("pair", "/p/b/pair-copy.jpg", 1000))
    repo.save(_photo("trio", "/p/x/trio.jpg", 300))
    repo.save(_photo("trio", "/p/y/trio.jpg", 300))
    repo.save(_photo("trio", "/p/z/trio.jpg", 300))
    return app


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


def test_a_photo_response_lists_every_path_primary_first(client) -> None:
    photo = client.get("/api/photos/pair").json()
    paths = [p["path"] for p in photo["paths"]]
    assert sorted(paths) == ["/p/a/pair.jpg", "/p/b/pair-copy.jpg"]
    assert paths[0] == photo["file_info"]["path"]
    assert all(p["missing"] is False and p["hidden"] is False for p in photo["paths"])


def test_search_results_carry_paths_too(client) -> None:
    items = client.post("/api/search", json={}).json()["items"]
    counts = {i["file_hash"]: len(i["paths"]) for i in items}
    assert counts == {"solo": 1, "pair": 2, "trio": 3}


def test_the_duplicates_list_is_biggest_saving_first_with_totals(client) -> None:
    body = client.get("/api/duplicates").json()
    assert [g["file_hash"] for g in body["groups"]] == ["pair", "trio"]
    pair, trio = body["groups"]
    assert (pair["copies"], pair["reclaimable_bytes"]) == (2, 1000)
    assert (trio["copies"], trio["reclaimable_bytes"]) == (3, 600)
    assert body["total_groups"] == 2 and body["reclaimable_bytes"] == 1600
    assert body["total_listed"] == 2


def test_the_duplicates_list_pages(client) -> None:
    body = client.get("/api/duplicates", params={"limit": 1, "offset": 1}).json()
    assert [g["file_hash"] for g in body["groups"]] == ["trio"]
    assert body["total_groups"] == 2 and body["reclaimable_bytes"] == 1600


def test_the_facets_count_duplicates_and_the_space_they_take(client) -> None:
    stats = client.get("/api/facets").json()["stats"]
    assert (stats["duplicate_count"], stats["reclaimable_bytes"]) == (2, 1600)


def test_search_can_filter_to_duplicates_or_away_from_them(client) -> None:
    def hashes(**body):
        items = client.post("/api/search", json=body).json()["items"]
        return sorted(i["file_hash"] for i in items)

    assert hashes(duplicates=True) == ["pair", "trio"]
    assert hashes(duplicates=False) == ["solo"]
    assert hashes() == ["pair", "solo", "trio"]


def test_hiding_a_copy_shrinks_the_group_and_the_saving(client) -> None:
    assert client.post("/api/files/hide", json={"path": "/p/x/trio.jpg"}).status_code == 204
    body = client.get("/api/duplicates").json()
    trio = next(g for g in body["groups"] if g["file_hash"] == "trio")
    assert trio["copies"] == 2 and trio["reclaimable_bytes"] == 300
    assert next(f for f in trio["files"] if f["path"] == "/p/x/trio.jpg")["hidden"] is True
    assert body["reclaimable_bytes"] == 1300


def test_hiding_all_but_one_copy_ends_the_duplicate_but_keeps_it_listed(client) -> None:
    client.post("/api/files/hide", json={"path": "/p/a/pair.jpg"})
    body = client.get("/api/duplicates").json()
    assert body["total_groups"] == 1 and body["total_listed"] == 2
    assert body["reclaimable_bytes"] == 600
    pair = next(g for g in body["groups"] if g["file_hash"] == "pair")
    assert (pair["copies"], pair["reclaimable_bytes"]) == (1, 0)
    assert client.get("/api/facets").json()["stats"]["duplicate_count"] == 1
    assert client.post("/api/search", json={"duplicates": True}).json()["total_count"] == 1


def test_a_two_copy_group_can_be_shown_again_after_hiding_one(client) -> None:
    client.post("/api/files/hide", json={"path": "/p/a/pair.jpg"})
    assert client.get("/api/facets").json()["stats"]["duplicate_count"] == 1
    client.post("/api/files/hide", json={"path": "/p/a/pair.jpg", "hidden": False})
    body = client.get("/api/duplicates").json()
    assert body["total_groups"] == 2 and body["total_listed"] == 2
    assert client.get("/api/facets").json()["stats"]["duplicate_count"] == 2


def test_a_file_edited_to_other_content_is_no_longer_hidden(app, client) -> None:
    client.post("/api/files/hide", json={"path": "/p/x/trio.jpg"})
    app.state.services.repository.save(_photo("edited", "/p/x/trio.jpg", 310))
    files = app.state.services.repository.files_of(["edited"])["edited"]
    assert [(f.path, f.hidden_at) for f in files] == [("/p/x/trio.jpg", None)]
    trio = next(
        g for g in client.get("/api/duplicates").json()["groups"] if g["file_hash"] == "trio"
    )
    assert trio["copies"] == 2  # the edit left the group; the two other copies remain


def test_a_hidden_copy_can_be_shown_again(client) -> None:
    client.post("/api/files/hide", json={"path": "/p/a/pair.jpg"})
    client.post("/api/files/hide", json={"path": "/p/a/pair.jpg", "hidden": False})
    pair = next(
        g for g in client.get("/api/duplicates").json()["groups"] if g["file_hash"] == "pair"
    )
    assert pair["copies"] == 2


def test_hiding_an_unknown_path_is_a_404(client) -> None:
    assert client.post("/api/files/hide", json={"path": "/nope.jpg"}).status_code == 404


def test_a_hidden_copy_stays_hidden_when_a_scan_saves_it_again(app, client) -> None:
    client.post("/api/files/hide", json={"path": "/p/x/trio.jpg"})
    app.state.services.repository.save(_photo("trio", "/p/x/trio.jpg", 300))
    trio = next(
        g for g in client.get("/api/duplicates").json()["groups"] if g["file_hash"] == "trio"
    )
    assert trio["copies"] == 2


def test_a_missing_copy_is_not_a_copy(app, client) -> None:
    app.state.services.repository.set_missing(["/p/b/pair-copy.jpg"], datetime(2026, 10, 1))
    body = client.get("/api/duplicates").json()
    assert [g["file_hash"] for g in body["groups"]] == ["trio"]
    photo = client.get("/api/photos/pair").json()
    assert {p["path"]: p["missing"] for p in photo["paths"]} == {
        "/p/a/pair.jpg": False,
        "/p/b/pair-copy.jpg": True,
    }
    assert photo["paths"][0]["path"] == "/p/a/pair.jpg"  # a present copy leads


def test_hiding_and_showing_announce_a_library_change(app, client) -> None:
    bus = app.state.services.events
    before = bus.last_id
    client.post("/api/files/hide", json={"path": "/p/a/pair.jpg"})
    assert bus.last_id == before + 1
