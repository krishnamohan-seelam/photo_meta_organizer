"""Remove from the library, with undo (ADR-003 R11, ticket 12).

Removing hides photos at once; they come back with everything for ``UNDO_SECONDS``; after that
they are purged, their paths are remembered, and scans leave the files alone until the content
changes or the user restores them. Files on disk are never touched.
"""

import os
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from tests.conftest import wait_for_job

from photo_meta_organizer.api.app import create_app
from photo_meta_organizer.application.settings import Settings
from photo_meta_organizer.domain.analysis import AiTag
from photo_meta_organizer.domain.datetimes import utc_now_naive


@pytest.fixture
def settings(tmp_path):
    return Settings(db_path=tmp_path / "removal.db", cache_dir=tmp_path / "thumbs")


@pytest.fixture
def library(tmp_path):
    folder = tmp_path / "photos"
    folder.mkdir()
    for name, colour in (("a", "red"), ("b", "blue"), ("c", "green")):
        Image.new("RGB", (8, 8), colour).save(folder / f"{name}.jpg")
    return folder


@pytest.fixture
def client(settings, library):
    with TestClient(create_app(settings=settings)) as client:
        _scan(client, library)
        yield client


def _scan(client: TestClient, folder) -> dict:
    job = client.post("/api/sync", json={"folder_path": str(folder)}).json()
    return wait_for_job(client, job)


def _hashes(client) -> dict[str, str]:
    items = client.post("/api/search", json={}).json()["items"]
    return {i["file_info"]["name"]: i["file_hash"] for i in items}


def _names(client) -> list[str]:
    return sorted(_hashes(client))


def _purge_now(client) -> int:
    """Pretend the undo window has passed."""
    trash = client.app.state.services.trash
    trash._now = lambda: utc_now_naive() + timedelta(seconds=3600)
    return trash.tick()


def test_removing_hides_the_photo_everywhere_and_leaves_the_file(client, library) -> None:
    hashes = _hashes(client)
    response = client.post(
        "/api/photos/batch", json={"photo_hashes": [hashes["a.jpg"]], "action": "delete"}
    )
    body = response.json()
    assert (body["deleted_count"], body["undo_seconds"]) == (1, 30)
    assert _names(client) == ["b.jpg", "c.jpg"]
    assert client.get(f"/api/photos/{hashes['a.jpg']}").status_code == 404
    assert client.get("/api/facets").json()["stats"]["total_count"] == 2
    assert client.get("/health").json()["photo_count"] == 2
    assert (library / "a.jpg").exists()


def test_a_single_delete_is_the_same_removal(client) -> None:
    hashes = _hashes(client)
    body = client.delete(f"/api/photos/{hashes['b.jpg']}").json()
    assert body["deleted"] is True and body["undo_seconds"] == 30
    assert _names(client) == ["a.jpg", "c.jpg"]
    assert client.delete(f"/api/photos/{hashes['b.jpg']}").status_code == 404  # already gone
    assert client.delete("/api/photos/nope").status_code == 404


def test_undo_brings_the_photo_back_with_its_curation_and_collections(client) -> None:
    hashes = _hashes(client)
    h = hashes["a.jpg"]
    client.patch(f"/api/photos/{h}", json={"rating": 4, "add_tags": ["trip"]})
    client.post("/api/collections", json={"name": "Best", "photo_hashes": [h]})
    client.post("/api/photos/batch", json={"photo_hashes": [h], "action": "delete"})

    restored = client.post("/api/photos/restore", json={"photo_hashes": [h]}).json()
    assert restored == {"restored_count": 1}
    photo = client.get(f"/api/photos/{h}").json()
    assert (photo["rating"], photo["labels"]) == (4, ["trip"])
    found = client.post("/api/search", json={"collection": "Best"}).json()
    assert [p["file_hash"] for p in found["items"]] == [h]


def test_restoring_what_was_never_removed_does_nothing(client) -> None:
    h = _hashes(client)["a.jpg"]
    assert client.post("/api/photos/restore", json={"photo_hashes": [h, "nope"]}).json() == {
        "restored_count": 0
    }


def test_nothing_is_purged_inside_the_undo_window(client) -> None:
    h = _hashes(client)["a.jpg"]
    client.post("/api/photos/batch", json={"photo_hashes": [h], "action": "delete"})
    assert client.app.state.services.trash.tick() == 0
    assert (
        client.post("/api/photos/restore", json={"photo_hashes": [h]}).json()["restored_count"] == 1
    )


def test_after_the_window_the_photo_is_gone_for_good_with_everything_attached(client) -> None:
    services = client.app.state.services
    h = _hashes(client)["a.jpg"]
    services.analysis.save_ai_tags(h, [AiTag("beach", 0.9, "m")])
    client.post("/api/collections", json={"name": "Best", "photo_hashes": [h]})
    client.post("/api/photos/batch", json={"photo_hashes": [h], "action": "delete"})

    assert _purge_now(client) == 1
    assert (
        client.post("/api/photos/restore", json={"photo_hashes": [h]}).json()["restored_count"] == 0
    )
    assert services.analysis.list_ai_tags(h) == []
    assert client.get("/api/collections").json()[0]["photo_hashes"] == []
    assert services.repository.files_of([h]) == {}


def test_the_purged_file_is_listed_as_removed(client, library) -> None:
    client.post(
        "/api/photos/batch", json={"photo_hashes": [_hashes(client)["a.jpg"]], "action": "delete"}
    )
    _purge_now(client)
    [gone] = client.get("/api/removed").json()
    assert gone["name"] == "a.jpg" and gone["path"].endswith("a.jpg")
    assert os.path.samefile(gone["path"], library / "a.jpg")


def test_a_scan_does_not_bring_a_removed_photo_back(client, library) -> None:
    client.post(
        "/api/photos/batch", json={"photo_hashes": [_hashes(client)["a.jpg"]], "action": "delete"}
    )
    _purge_now(client)
    job = _scan(client, library)
    assert job["counts"]["ignored"] == 1 and job["counts"]["new"] == 0
    assert _names(client) == ["b.jpg", "c.jpg"]


def test_a_scan_in_the_undo_window_does_not_duplicate_the_photo(client, library) -> None:
    h = _hashes(client)["a.jpg"]
    client.post("/api/photos/batch", json={"photo_hashes": [h], "action": "delete"})
    job = _scan(client, library)  # the File is still recorded, so it is simply unchanged
    assert job["counts"]["new"] == 0
    client.post("/api/photos/restore", json={"photo_hashes": [h]})
    assert _names(client) == ["a.jpg", "b.jpg", "c.jpg"]


def test_a_file_whose_content_changed_is_scanned_as_a_different_photo(client, library) -> None:
    client.post(
        "/api/photos/batch", json={"photo_hashes": [_hashes(client)["a.jpg"]], "action": "delete"}
    )
    _purge_now(client)
    bigger = Image.effect_noise((64, 64), 80).convert("RGB")
    bigger.save(library / "a.jpg")  # same path, new (and larger) content
    job = _scan(client, library)
    assert job["counts"]["new"] == 1 and job["counts"]["ignored"] == 0
    assert _names(client) == ["a.jpg", "b.jpg", "c.jpg"]
    assert client.get("/api/removed").json() == []  # no longer ignored


def test_restoring_a_removed_file_forgets_it_and_scans_its_folder(client, library) -> None:
    client.post(
        "/api/photos/batch", json={"photo_hashes": [_hashes(client)["a.jpg"]], "action": "delete"}
    )
    _purge_now(client)
    [gone] = client.get("/api/removed").json()

    restored = client.post("/api/removed/restore", json={"paths": [gone["path"]]}).json()
    assert restored["restored_count"] == 1 and len(restored["job_ids"]) == 1
    wait_for_job(client, client.get(f"/api/jobs/{restored['job_ids'][0]}").json())
    assert _names(client) == ["a.jpg", "b.jpg", "c.jpg"]
    assert client.get("/api/removed").json() == []


def test_restoring_scans_only_the_folders_of_files_that_were_removed(
    client, library, tmp_path
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    Image.new("RGB", (8, 8), "white").save(elsewhere / "x.jpg")
    restored = client.post(
        "/api/removed/restore", json={"paths": [str(elsewhere / "x.jpg")]}
    ).json()
    assert restored == {"restored_count": 0, "job_ids": []}
    assert str(elsewhere) not in [j["folder_path"] for j in client.get("/api/jobs").json()]
    assert _names(client) == ["a.jpg", "b.jpg", "c.jpg"]


def test_a_copy_found_in_the_undo_window_comes_back_and_the_removed_path_stays_removed(
    client, library, tmp_path
) -> None:
    h = _hashes(client)["a.jpg"]
    client.post("/api/photos/batch", json={"photo_hashes": [h], "action": "delete"})
    other = tmp_path / "other"
    other.mkdir()
    (other / "copy.jpg").write_bytes((library / "a.jpg").read_bytes())

    job = _scan(client, other)
    assert job["counts"]["new"] == 1
    assert _names(client) == ["b.jpg", "c.jpg", "copy.jpg"]
    assert _purge_now(client) == 0  # nothing hidden is left to purge with the copy
    assert _names(client) == ["b.jpg", "c.jpg", "copy.jpg"]
    assert _scan(client, library)["counts"]["ignored"] == 1
    assert [r["name"] for r in client.get("/api/removed").json()] == ["a.jpg"]


def test_removed_photos_labels_are_not_counted_in_the_facets(client) -> None:
    hashes = _hashes(client)
    client.patch(f"/api/photos/{hashes['a.jpg']}", json={"add_tags": ["trip"]})
    client.patch(f"/api/photos/{hashes['b.jpg']}", json={"add_tags": ["trip"]})
    client.post("/api/photos/batch", json={"photo_hashes": [hashes["a.jpg"]], "action": "delete"})
    tags = client.get("/api/facets").json()["tags"]
    assert tags == [{"name": "trip", "count": 1}]


def test_a_removed_photo_on_a_missing_drive_stays_removed_when_it_returns(
    client, library, tmp_path
) -> None:
    h = _hashes(client)["a.jpg"]
    parked = tmp_path / "a.jpg"
    os.replace(library / "a.jpg", parked)  # unplugged: the File is flagged missing
    _scan(client, library)
    client.post("/api/photos/batch", json={"photo_hashes": [h], "action": "delete"})
    _purge_now(client)
    os.replace(parked, library / "a.jpg")  # plugged back in, unchanged

    job = _scan(client, library)
    assert job["counts"]["ignored"] == 1 and job["counts"]["new"] == 0
    assert _names(client) == ["b.jpg", "c.jpg"]


def test_what_was_removed_before_the_app_stopped_is_final_when_it_starts_again(
    settings, library
) -> None:
    with TestClient(create_app(settings=settings)) as first:
        _scan(first, library)
        h = _hashes(first)["a.jpg"]
        first.post("/api/photos/batch", json={"photo_hashes": [h], "action": "delete"})
    with TestClient(create_app(settings=settings)) as second:
        assert _names(second) == ["b.jpg", "c.jpg"]
        assert (
            second.post("/api/photos/restore", json={"photo_hashes": [h]}).json()["restored_count"]
            == 0
        )
        assert [r["name"] for r in second.get("/api/removed").json()] == ["a.jpg"]


def test_removed_photos_do_not_count_as_duplicates_or_suggestions(client, library) -> None:
    services = client.app.state.services
    h = _hashes(client)["a.jpg"]
    services.analysis.save_ai_tags(h, [AiTag("beach", 0.9, "m")])
    assert client.get("/api/ai-tags/review").json()[0]["label"] == "beach"
    client.post("/api/photos/batch", json={"photo_hashes": [h], "action": "delete"})
    assert client.get("/api/ai-tags/review").json() == []
    assert client.get("/api/ai-tags").json() == []


def test_removing_announces_a_library_change(client) -> None:
    bus = client.app.state.services.events
    before = bus.last_id
    client.post(
        "/api/photos/batch", json={"photo_hashes": [_hashes(client)["a.jpg"]], "action": "delete"}
    )
    assert bus.last_id > before
