"""``GET /api/events`` and what feeds it (ADR-003 R5b).

The server closes the bus before the stream is read, so every response is finite and the
tests need no threads: a client that reconnects to a stopping server still gets what it missed.
"""

import json

import pytest
from fastapi.testclient import TestClient
from tests.conftest import wait_for_job

from photo_meta_organizer.api.app import create_app
from photo_meta_organizer.api.routes.events_router import changes_library
from photo_meta_organizer.domain.models import (
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)


@pytest.fixture
def app(tmp_path):
    return create_app(db_path=tmp_path / "events.db", cache_dir=tmp_path / "thumbs")


def _events(client: TestClient, last_event_id: str | None = None) -> list[dict]:
    """Read the whole (closed) stream as ``[{id, event, data}]``."""
    headers = {"Last-Event-ID": last_event_id} if last_event_id is not None else {}
    with client.stream("GET", "/api/events", headers=headers) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())
    events = []
    for block in body.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in fields:
            events.append(
                {
                    "id": int(fields["id"]),
                    "event": fields["event"],
                    "data": json.loads(fields["data"]),
                }
            )
    return events


def test_a_finished_job_is_announced_with_the_job_and_a_library_change(app, tmp_path) -> None:
    folder = tmp_path / "photos"
    folder.mkdir()
    with TestClient(app) as client:
        job = client.post("/api/index", json={"folder_path": str(folder)}).json()
        wait_for_job(client, job)
        app.state.services.events.close()
        events = _events(client, "0")
    kinds = [e["event"] for e in events]
    assert kinds[0] == "job_progress" and "job_finished" in kinds and kinds[-1] == "library_changed"
    finished = next(e for e in events if e["event"] == "job_finished")
    assert finished["data"]["id"] == job["id"] and finished["data"]["status"] == "succeeded"
    ids = [e["id"] for e in events]
    assert ids == sorted(set(ids))


def test_reconnecting_replays_only_what_was_missed(app) -> None:
    bus = app.state.services.events
    for _ in range(3):
        bus.publish("library_changed", {"reason": "edit"})
    bus.close()
    with TestClient(app) as client:
        assert [e["id"] for e in _events(client, "1")] == [2, 3]


def test_a_gap_older_than_the_buffer_is_a_resync(app) -> None:
    bus = app.state.services.events
    for _ in range(250):
        bus.publish("job_progress", {})
    bus.close()
    with TestClient(app) as client:
        events = _events(client, "10")
    assert [e["event"] for e in events] == ["resync"] and events[0]["id"] == 250


def test_an_id_from_a_previous_run_is_a_resync(app) -> None:
    app.state.services.events.close()
    with TestClient(app) as client:
        events = _events(client, "99")
    assert [e["event"] for e in events] == ["resync"]


def test_editing_a_photo_announces_a_library_change_and_a_search_does_not(app) -> None:
    app.state.services.repository.save(
        ImageMetadata(
            file_hash="h1",
            file_info=ImageFileInfo(
                name="a.jpg", path="/a.jpg", size_bytes=1, mime_type="image/jpeg"
            ),
            dimensions=ImageDimensions(width=1, height=1),
            exif=ImageExifData(),
        )
    )
    bus = app.state.services.events
    with TestClient(app) as client:
        client.post("/api/search", json={})
        assert client.patch("/api/photos/nope", json={"rating": 3}).status_code == 404
        assert bus.last_id == 0  # reads and failures announce nothing
        assert client.patch("/api/photos/h1", json={"rating": 3}).status_code == 200
        assert bus.last_id == 1
        bus.close()
        [event] = _events(client, "0")
    assert event["event"] == "library_changed" and event["data"] == {"reason": "edit"}


def test_which_requests_change_the_library() -> None:
    assert changes_library("PATCH", "/api/photos/abc", 200)
    assert changes_library("POST", "/api/collections", 201)
    assert changes_library("POST", "/api/ai-tags/batch", 200)
    assert not changes_library("PATCH", "/api/photos/abc", 404)
    assert not changes_library("POST", "/api/search", 200)
    assert not changes_library("GET", "/api/photos", 200)
    assert not changes_library("POST", "/api/index", 202)


def test_the_stream_needs_the_launch_token_like_everything_else(tmp_path) -> None:
    from photo_meta_organizer.application.settings import Settings

    settings = Settings(db_path=tmp_path / "t.db", cache_dir=tmp_path / "c", api_token="s3cret")
    app = create_app(settings=settings)
    app.state.services.events.close()
    with TestClient(app) as client:
        assert client.get("/api/events").status_code == 401
        client.cookies.set("pmo_token", "s3cret")
        assert client.get("/api/events").status_code == 200
