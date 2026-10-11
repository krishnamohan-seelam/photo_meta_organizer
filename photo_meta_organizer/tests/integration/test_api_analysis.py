"""Phase 5 HTTP surface: status, consent-gated model download, analysis jobs, semantic search,
AI-tag review. Everything runs on fakes (no network, no real model)."""

import hashlib

import pytest
from fastapi.testclient import TestClient
from tests.conftest import wait_for_job
from tests.fakes import FakeImageEmbedder

from photo_meta_organizer.api.app import create_app
from photo_meta_organizer.api.routes import analysis_router
from photo_meta_organizer.application.settings import Settings
from photo_meta_organizer.domain.analysis import AiTag
from photo_meta_organizer.domain.models import (
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.infrastructure.analysis.model_manifest import ModelFile, ModelManifest
from photo_meta_organizer.infrastructure.analysis.model_store import ModelStore
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import SqliteRepository

MODEL_BYTES = b"pretend-weights" * 200
PHOTOS = (("tiger", "Sony"), ("beach", "Canon"), ("city", "Sony"))


class Api:
    pass


@pytest.fixture
def api(tmp_path, monkeypatch):
    remote = tmp_path / "remote" / "model.onnx"
    remote.parent.mkdir()
    remote.write_bytes(MODEL_BYTES)
    manifest = ModelManifest(
        model_id="api-test-model",
        files=(
            ModelFile(
                name="model.onnx",
                url=remote.as_uri(),
                size=len(MODEL_BYTES),
                sha256=hashlib.sha256(MODEL_BYTES).hexdigest(),
            ),
        ),
        licence="MIT",
        source="example.test/model",
    )
    store = ModelStore(tmp_path / "models", manifest)
    embedder = FakeImageEmbedder("api-embedder")

    db = tmp_path / "photos.db"
    repo = SqliteRepository(str(db))
    for name, make in PHOTOS:
        file = tmp_path / "lib" / f"{name}.jpg"
        file.parent.mkdir(exist_ok=True)
        file.write_bytes(name.encode())  # the fake embeds a file as the vector of its bytes
        repo.save(
            ImageMetadata(
                file_hash=f"h-{name}",
                file_info=ImageFileInfo(
                    name=file.name, path=str(file), size_bytes=1, mime_type="image/jpeg"
                ),
                dimensions=ImageDimensions(width=1, height=1),
                exif=ImageExifData(camera_make=make),
            )
        )
    repo.close()

    settings = Settings(db_path=db, cache_dir=tmp_path / "thumbs", model_dir=tmp_path / "models")
    app = create_app(settings=settings, model_store=store, embedder=embedder)
    monkeypatch.setattr(analysis_router, "ai_runtime_installed", lambda: True)
    a = Api()
    a.client, a.app, a.store, a.embedder, a.tmp = TestClient(app), app, store, embedder, tmp_path
    a.analysis = app.state.services.analysis
    a.photos = app.state.services.repository
    return a


def _install(api):
    api.store.download()


def _analyze(api, **body):
    response = api.client.post("/api/analysis/run", json=body)
    assert response.status_code == 202, response.text
    return wait_for_job(api.client, response.json())


class TestStatus:
    def test_before_anything_is_set_up(self, api):
        body = api.client.get("/api/analysis/status").json()
        assert body["runtime_installed"] is True
        assert body["model_installed"] is False
        assert body["model_id"] == "api-test-model"
        assert body["model_licence"] == "MIT" and body["model_source"] == "example.test/model"
        assert body["download_bytes"] == len(MODEL_BYTES)
        assert (body["total_photos"], body["analyzed_photos"], body["pending_photos"]) == (3, 0, 3)
        assert body["active_job_id"] is None

    def test_after_the_model_is_installed_and_photos_analysed(self, api):
        _install(api)
        _analyze(api)
        body = api.client.get("/api/analysis/status").json()
        assert body["model_installed"] is True and body["download_bytes"] == 0
        assert (body["analyzed_photos"], body["pending_photos"]) == (3, 0)

    def test_reports_a_missing_runtime(self, api, monkeypatch):
        monkeypatch.setattr(analysis_router, "ai_runtime_installed", lambda: False)
        assert api.client.get("/api/analysis/status").json()["runtime_installed"] is False

    def test_names_the_running_job(self, api, monkeypatch):
        import threading

        gate = threading.Event()
        original = api.store.download

        def slow(progress=None, should_cancel=None):
            gate.wait(5)
            original(progress=progress, should_cancel=should_cancel)

        monkeypatch.setattr(api.store, "download", slow)
        job = api.client.post("/api/analysis/model/download", json={"accept": True}).json()
        try:
            body = api.client.get("/api/analysis/status").json()
            assert body["active_job_id"] == job["id"]
            assert body["active_job_kind"] == "model-download"
        finally:
            gate.set()
            wait_for_job(api.client, job)


class TestModelDownload:
    def test_needs_explicit_consent(self, api):
        assert api.client.post("/api/analysis/model/download", json={}).status_code == 422
        refused = api.client.post("/api/analysis/model/download", json={"accept": False})
        assert refused.status_code == 422
        assert not api.store.is_installed()

    def test_downloads_as_a_job_with_byte_progress(self, api):
        response = api.client.post("/api/analysis/model/download", json={"accept": True})
        assert response.status_code == 202
        job = wait_for_job(api.client, response.json())
        assert job["kind"] == "model-download" and job["status"] == "succeeded"
        assert (job["processed"], job["total"]) == (len(MODEL_BYTES), len(MODEL_BYTES))
        assert api.store.is_installed()

    def test_an_installed_model_is_not_downloaded_again(self, api):
        _install(api)
        response = api.client.post("/api/analysis/model/download", json={"accept": True})
        assert response.status_code == 409
        assert "already installed" in response.json()["detail"]

    def test_a_failed_download_is_a_failed_job_and_leaves_nothing(self, api):
        (api.tmp / "remote" / "model.onnx").write_bytes(b"x" * len(MODEL_BYTES))
        response = api.client.post("/api/analysis/model/download", json={"accept": True})
        job = wait_for_job(api.client, response.json())
        assert job["status"] == "failed" and "checksum" in job["message"]
        assert not api.store.is_installed()


class TestRunAnalysis:
    def test_needs_the_model_first(self, api):
        response = api.client.post("/api/analysis/run", json={})
        assert response.status_code == 409
        assert "model" in response.json()["detail"].lower()

    def test_needs_the_runtime(self, api, monkeypatch):
        _install(api)
        monkeypatch.setattr(analysis_router, "ai_runtime_installed", lambda: False)
        response = api.client.post("/api/analysis/run", json={})
        assert response.status_code == 503
        assert "ai" in response.json()["detail"]

    def test_analyses_the_library_as_a_job(self, api):
        _install(api)
        job = _analyze(api)
        assert job["kind"] == "analyze" and job["status"] == "succeeded"
        assert job["counts"]["analyzed"] == 3 and job["counts"]["failed"] == 0
        assert api.analysis.count_embeddings(api.embedder.model_id) == 3

    def test_a_second_run_has_nothing_to_do(self, api):
        _install(api)
        _analyze(api)
        assert _analyze(api)["counts"]["total"] == 0

    def test_reanalyze_and_limit(self, api):
        _install(api)
        assert _analyze(api, limit=2)["counts"]["analyzed"] == 2
        assert _analyze(api, reanalyze=True)["counts"]["analyzed"] == 3

    def test_files_that_fail_are_reported(self, api):
        _install(api)
        (api.tmp / "lib" / "beach.jpg").unlink()
        job = _analyze(api)
        assert job["counts"]["analyzed"] == 2 and job["failed_count"] == 1
        assert "beach.jpg" in job["errors"][0]

    def test_rejects_a_nonsense_limit(self, api):
        _install(api)
        assert api.client.post("/api/analysis/run", json={"limit": 0}).status_code == 422

    def test_a_second_job_while_one_runs_is_refused(self, api, monkeypatch):
        import threading

        _install(api)
        gate = threading.Event()
        original = api.embedder.embed_image

        def slow(stream, filename):
            gate.wait(5)
            return original(stream, filename)

        monkeypatch.setattr(api.embedder, "embed_image", slow)
        first = api.client.post("/api/analysis/run", json={}).json()
        try:
            assert api.client.post("/api/analysis/run", json={}).status_code == 409
        finally:
            gate.set()
            wait_for_job(api.client, first)


class TestSemanticSearch:
    @pytest.fixture(autouse=True)
    def analysed(self, api):
        _install(api)
        _analyze(api)

    def _search(self, api, **body):
        return api.client.post("/api/search/semantic", json=body)

    def test_text_finds_the_photo_it_describes(self, api):
        response = self._search(api, text="tiger", k=3)
        assert response.status_code == 200
        body = response.json()
        assert body["model_id"] == "api-embedder"
        assert body["items"][0]["photo"]["file_hash"] == "h-tiger"
        assert body["items"][0]["score"] == pytest.approx(1.0, abs=1e-4)
        scores = [i["score"] for i in body["items"]]
        assert scores == sorted(scores, reverse=True)

    def test_the_usual_filters_apply(self, api):
        body = self._search(api, text="tiger", camera_makes=["Canon"]).json()
        assert [i["photo"]["file_hash"] for i in body["items"]] == ["h-beach"]

    def test_similar_to_a_photo_leaves_it_out(self, api):
        body = self._search(api, like_hash="h-tiger").json()
        hashes = [i["photo"]["file_hash"] for i in body["items"]]
        assert "h-tiger" not in hashes and len(hashes) == 2

    def test_k_limits_the_hits(self, api):
        assert len(self._search(api, text="tiger", k=1).json()["items"]) == 1

    @pytest.mark.parametrize(
        "body",
        [
            {},  # neither text nor like_hash
            {"text": "a", "like_hash": "h-tiger"},  # both
            {"text": "   "},
            {"text": "x", "k": 0},
            {"text": "x", "k": 1000},
        ],
    )
    def test_bad_requests_are_422(self, api, body):
        assert self._search(api, **body).status_code == 422

    def test_an_unknown_photo_is_404(self, api):
        assert self._search(api, like_hash="nope").status_code == 404

    def test_nothing_analysed_is_409_not_an_empty_list(self, api):
        api.analysis.clear_embeddings()
        response = self._search(api, text="tiger")
        assert response.status_code == 409
        assert "analy" in response.json()["detail"].lower()

    def test_a_photo_without_an_embedding_is_409(self, api):
        api.analysis.clear_embeddings()
        api.analysis.save_embeddings([])  # nothing
        _analyze(api, limit=1)
        analysed = {
            p
            for p in ("h-tiger", "h-beach", "h-city")
            if api.analysis.get_embedding(p, "api-embedder")
        }
        missing = ({"h-tiger", "h-beach", "h-city"} - analysed).pop()
        assert self._search(api, like_hash=missing).status_code == 409

    def test_needs_the_model(self, api):
        api.store.path("model.onnx").unlink()
        assert self._search(api, text="tiger").status_code == 409

    def test_needs_the_runtime(self, api, monkeypatch):
        monkeypatch.setattr(analysis_router, "ai_runtime_installed", lambda: False)
        assert self._search(api, text="tiger").status_code == 503


class TestAiTags:
    @pytest.fixture(autouse=True)
    def suggestions(self, api):
        api.analysis.save_ai_tags("h-tiger", [AiTag("tiger", 0.9, "m"), AiTag("zoo", 0.3, "m")])
        api.analysis.save_ai_tags("h-beach", [AiTag("beach", 0.8, "m"), AiTag("zoo", 0.1, "m")])

    def _tags(self, api, h):
        response = api.client.get(f"/api/photos/{h}/ai-tags")
        assert response.status_code == 200, response.text
        return {t["label"]: t for t in response.json()}

    def test_lists_a_photos_suggestions_most_confident_first(self, api):
        response = api.client.get("/api/photos/h-tiger/ai-tags").json()
        assert [t["label"] for t in response] == ["tiger", "zoo"]
        assert response[0] == {
            "label": "tiger",
            "confidence": pytest.approx(0.9),
            "model_id": "m",
            "status": "suggested",
        }

    def test_a_photo_without_suggestions_has_an_empty_list(self, api):
        assert api.client.get("/api/photos/h-city/ai-tags").json() == []

    def test_an_unknown_photo_is_404(self, api):
        assert api.client.get("/api/photos/nope/ai-tags").status_code == 404

    def test_accepting_adds_the_label_to_the_photo(self, api):
        response = api.client.post(
            "/api/photos/h-tiger/ai-tags", json={"label": "tiger", "action": "accept"}
        )
        assert response.status_code == 200
        assert {t["label"]: t["status"] for t in response.json()} == {
            "tiger": "accepted",
            "zoo": "suggested",
        }
        assert api.client.get("/api/photos/h-tiger").json()["labels"] == ["tiger"]
        # it is an ordinary label now: searchable like any other
        found = api.client.post("/api/search", json={"tags": ["tiger"]}).json()
        assert [p["file_hash"] for p in found["items"]] == ["h-tiger"]

    def test_rejecting_does_not_touch_the_labels(self, api):
        api.client.post("/api/photos/h-tiger/ai-tags", json={"label": "zoo", "action": "reject"})
        assert self._tags(api, "h-tiger")["zoo"]["status"] == "rejected"
        assert api.client.get("/api/photos/h-tiger").json()["labels"] == []

    def test_reset_undoes_a_rejection(self, api):
        api.client.post("/api/photos/h-tiger/ai-tags", json={"label": "zoo", "action": "reject"})
        api.client.post("/api/photos/h-tiger/ai-tags", json={"label": "zoo", "action": "reset"})
        assert self._tags(api, "h-tiger")["zoo"]["status"] == "suggested"

    def test_an_unknown_label_is_404_and_a_bad_action_422(self, api):
        missing = api.client.post(
            "/api/photos/h-tiger/ai-tags", json={"label": "nope", "action": "accept"}
        )
        assert missing.status_code == 404
        bad = api.client.post(
            "/api/photos/h-tiger/ai-tags", json={"label": "tiger", "action": "delete"}
        )
        assert bad.status_code == 422

    def test_batch_accepts_every_open_suggestion_of_the_selection(self, api):
        response = api.client.post(
            "/api/ai-tags/batch",
            json={"photo_hashes": ["h-tiger", "h-beach", "h-city"], "action": "accept"},
        )
        assert response.status_code == 200
        assert response.json() == {"photos_changed": 2, "tags_changed": 4}
        assert api.client.get("/api/photos/h-beach").json()["labels"] == ["beach", "zoo"]

    def test_batch_can_name_the_labels(self, api):
        body = {"photo_hashes": ["h-tiger", "h-beach"], "labels": ["zoo"], "action": "reject"}
        assert api.client.post("/api/ai-tags/batch", json=body).json() == {
            "photos_changed": 2,
            "tags_changed": 2,
        }
        assert self._tags(api, "h-tiger")["tiger"]["status"] == "suggested"

    @pytest.mark.parametrize(
        "body",
        [
            {"photo_hashes": [], "action": "accept"},
            {"photo_hashes": ["h"], "action": "reset"},
            {"photo_hashes": ["h"], "action": "accept", "labels": [" "]},
        ],
    )
    def test_batch_validates_its_input(self, api, body):
        assert api.client.post("/api/ai-tags/batch", json=body).status_code == 422

    def test_counts_per_label(self, api):
        counts = {c["name"]: c["count"] for c in api.client.get("/api/ai-tags").json()}
        assert counts == {"zoo": 2, "tiger": 1, "beach": 1}
        api.client.post("/api/photos/h-tiger/ai-tags", json={"label": "zoo", "action": "accept"})
        accepted = api.client.get("/api/ai-tags", params={"status": "accepted"}).json()
        assert accepted == [{"name": "zoo", "count": 1}]

    def test_an_unknown_status_filter_is_422(self, api):
        assert api.client.get("/api/ai-tags", params={"status": "maybe"}).status_code == 422


def test_the_token_protects_the_new_routes(tmp_path):
    settings = Settings(db_path=tmp_path / "t.db", api_token="s3cret", model_dir=tmp_path / "m")
    client = TestClient(create_app(settings=settings))
    for method, path in (
        ("get", "/api/analysis/status"),
        ("post", "/api/analysis/run"),
        ("post", "/api/search/semantic"),
        ("get", "/api/ai-tags"),
    ):
        assert getattr(client, method)(path).status_code == 401, path
