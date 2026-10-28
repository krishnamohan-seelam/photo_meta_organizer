"""Phase 5 HTTP surface: status, consent-gated model download, analysis jobs, semantic search,
AI-tag review. Everything runs on fakes (no network, no real model)."""

import dataclasses
import hashlib

import pytest
from fastapi.testclient import TestClient
from tests.conftest import wait_for_job
from tests.fakes import FakeImageEmbedder

from photo_meta_organizer.api.app import create_app
from photo_meta_organizer.application.composition import build_job_store
from photo_meta_organizer.application.jobs import Job, JobStatus
from photo_meta_organizer.application.settings import Settings
from photo_meta_organizer.domain.analysis import AiTag
from photo_meta_organizer.domain.models import (
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.infrastructure.analysis import runtime
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
    monkeypatch.setattr(runtime, "ai_runtime_installed", lambda: True)
    a = Api()
    a.client, a.app, a.store, a.embedder, a.tmp = TestClient(app), app, store, embedder, tmp_path
    a.settings = settings
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
        monkeypatch.setattr(runtime, "ai_runtime_installed", lambda: False)
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
        monkeypatch.setattr(runtime, "ai_runtime_installed", lambda: False)
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

    def _restart_with_interrupted(self, api, **params):
        """A second app on the same library, after an analysis was left running."""
        build_job_store(api.photos).save(
            Job(
                id="left-running",
                kind="analyze",
                folder_path=str(api.settings.model_dir),
                status=JobStatus.RUNNING,
                params=params,
            )
        )
        app = create_app(settings=api.settings, model_store=api.store, embedder=api.embedder)
        return TestClient(app)

    def test_resuming_an_interrupted_analysis_takes_the_pending_photos(self, api):
        _install(api)
        _analyze(api, limit=2)
        with self._restart_with_interrupted(api, limit=None) as client:
            assert client.get("/api/jobs/left-running").json()["status"] == "interrupted"
            resumed = wait_for_job(client, client.post("/api/jobs/left-running/resume").json())
        assert resumed["status"] == "succeeded" and resumed["counts"]["analyzed"] == 1

    def test_resuming_an_interrupted_reanalysis_redoes_the_whole_library(self, api):
        _install(api)
        _analyze(api)
        with self._restart_with_interrupted(api, reanalyze=True) as client:
            resumed = wait_for_job(client, client.post("/api/jobs/left-running/resume").json())
        assert resumed["status"] == "succeeded" and resumed["counts"]["analyzed"] == 3

    def test_files_that_fail_are_reported(self, api):
        _install(api)
        (api.tmp / "lib" / "beach.jpg").unlink()
        job = _analyze(api)
        assert job["counts"]["analyzed"] == 2 and job["failed_count"] == 1
        assert "beach.jpg" in job["errors"][0]

    def test_retag_recomputes_from_stored_embeddings(self, api):
        _install(api)
        _analyze(api)
        api.analysis.save_ai_tags("h-tiger", [])  # nothing to start from
        job = _analyze(api, retag=True)
        assert job["status"] == "succeeded", job
        assert job["counts"]["analyzed"] == 3
        assert job["counts"]["total"] == 3

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


class TestRankedSearch:
    """A search by meaning is a ranking mode of POST /api/search (ADR-003 R9, ticket 15)."""

    @pytest.fixture(autouse=True)
    def analysed(self, api):
        _install(api)
        _analyze(api)

    def _search(self, api, rank, **body):
        return api.client.post("/api/search", json={"rank": rank, **body})

    def _settings(self, api, **changes):
        services = api.app.state.services
        api.app.state.services = dataclasses.replace(
            services, settings=dataclasses.replace(services.settings, **changes)
        )

    def test_text_ranks_the_photo_it_describes_first(self, api):
        response = self._search(api, {"text": "tiger", "everything": True})
        assert response.status_code == 200
        body = response.json()
        assert body["items"][0]["file_hash"] == "h-tiger"
        assert body["scores"][0] == pytest.approx(1.0, abs=1e-4)
        assert body["scores"] == sorted(body["scores"], reverse=True)
        assert body["total_count"] == 3 and body["rank_token"]

    def test_the_usual_filters_apply(self, api):
        body = self._search(api, {"text": "tiger"}, camera_makes=["Canon"]).json()
        assert [p["file_hash"] for p in body["items"]] == ["h-beach"]

    def test_similar_to_a_photo_leaves_it_out(self, api):
        body = self._search(api, {"like_hash": "h-tiger", "everything": True}).json()
        hashes = [p["file_hash"] for p in body["items"]]
        assert "h-tiger" not in hashes and len(hashes) == 2

    def test_the_cut_off_keeps_the_top_n_within_the_margin(self, api):
        self._settings(api, semantic_top_n=10, semantic_margin=0.0)
        assert [p["file_hash"] for p in self._search(api, {"text": "tiger"}).json()["items"]] == [
            "h-tiger"
        ]
        self._settings(api, semantic_top_n=2, semantic_margin=5.0)
        assert self._search(api, {"text": "tiger"}).json()["total_count"] == 2

    def test_later_pages_are_slices_of_the_snapshot(self, api):
        first = self._search(api, {"text": "tiger", "everything": True}, page_size=2).json()
        assert first["total_pages"] == 2 and len(first["items"]) == 2
        api.analysis.clear_embeddings()  # the snapshot is served without ranking again
        second = self._search(
            api,
            {"text": "tiger", "everything": True},
            page=2,
            page_size=2,
            rank_token=first["rank_token"],
        ).json()
        seen = [p["file_hash"] for p in first["items"] + second["items"]]
        assert sorted(seen) == ["h-beach", "h-city", "h-tiger"]

    def test_an_expired_token_is_410(self, api):
        response = self._search(api, {"text": "tiger"}, page=2, rank_token="gone")
        assert response.status_code == 410

    def test_select_all_returns_the_ranked_list(self, api):
        ids = api.client.post(
            "/api/search/ids", json={"rank": {"text": "tiger", "everything": True}}
        ).json()
        assert [i["file_hash"] for i in ids][0] == "h-tiger" and len(ids) == 3

    def test_a_photo_removed_meanwhile_is_left_out_of_its_page(self, api):
        first = self._search(api, {"text": "tiger", "everything": True}, page_size=1).json()
        api.client.delete("/api/photos/h-tiger")
        again = self._search(
            api, {"text": "tiger"}, page_size=1, rank_token=first["rank_token"]
        ).json()
        assert again["items"] == [] and again["scores"] == []

    @pytest.mark.parametrize(
        "rank",
        [
            {},  # neither text nor like_hash
            {"text": "a", "like_hash": "h-tiger"},  # both
            {"text": "   "},
        ],
    )
    def test_bad_requests_are_422(self, api, rank):
        assert self._search(api, rank).status_code == 422

    def test_an_unknown_photo_is_404(self, api):
        assert self._search(api, {"like_hash": "nope"}).status_code == 404

    def test_nothing_analysed_is_409_not_an_empty_list(self, api):
        api.analysis.clear_embeddings()
        response = self._search(api, {"text": "tiger"})
        assert response.status_code == 409
        assert "analy" in response.json()["detail"].lower()

    def test_a_photo_without_an_embedding_is_409(self, api):
        api.analysis.clear_embeddings()
        _analyze(api, limit=1)
        analysed = {
            p
            for p in ("h-tiger", "h-beach", "h-city")
            if api.analysis.get_embedding(p, "api-embedder")
        }
        missing = ({"h-tiger", "h-beach", "h-city"} - analysed).pop()
        assert self._search(api, {"like_hash": missing}).status_code == 409

    def test_needs_the_model(self, api):
        api.store.path("model.onnx").unlink()
        assert self._search(api, {"text": "tiger"}).status_code == 409

    def test_needs_the_runtime(self, api, monkeypatch):
        monkeypatch.setattr(runtime, "ai_runtime_installed", lambda: False)
        assert self._search(api, {"text": "tiger"}).status_code == 503

    def test_without_rank_the_search_is_unchanged(self, api):
        body = api.client.post("/api/search", json={}).json()
        assert body["scores"] is None and body["rank_token"] is None


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

    def test_search_can_filter_by_an_open_suggestion(self, api):
        found = api.client.post("/api/search", json={"ai_tag": "zoo"}).json()
        assert {p["file_hash"] for p in found["items"]} == {"h-tiger", "h-beach"}
        api.client.post("/api/photos/h-beach/ai-tags", json={"label": "zoo", "action": "reject"})
        found = api.client.post("/api/search", json={"ai_tag": "zoo"}).json()
        assert [p["file_hash"] for p in found["items"]] == ["h-tiger"]
        both = api.client.post("/api/search", json={"ai_tag": "zoo", "camera_makes": ["Canon"]})
        assert both.json()["items"] == []

    def test_an_unknown_status_filter_is_422(self, api):
        assert api.client.get("/api/ai-tags", params={"status": "maybe"}).status_code == 422


def test_the_token_protects_the_new_routes(tmp_path):
    settings = Settings(db_path=tmp_path / "t.db", api_token="s3cret", model_dir=tmp_path / "m")
    client = TestClient(create_app(settings=settings))
    for method, path in (
        ("get", "/api/analysis/status"),
        ("post", "/api/analysis/run"),
        ("get", "/api/ai-tags"),
    ):
        assert getattr(client, method)(path).status_code == 401, path


class TestReviewQueue:
    @pytest.fixture(autouse=True)
    def suggestions(self, api):
        api.analysis.save_ai_tags("h-tiger", [AiTag("tiger", 0.9, "m"), AiTag("zoo", 0.3, "m")])
        api.analysis.save_ai_tags("h-beach", [AiTag("beach", 0.8, "m"), AiTag("zoo", 0.1, "m")])
        api.analysis.save_ai_tags("h-city", [AiTag("zoo", 0.5, "m")])

    def _items(self, api, label="zoo", **params):
        response = api.client.get("/api/ai-tags/review/items", params={"label": label, **params})
        assert response.status_code == 200, response.text
        return response.json()

    def test_labels_come_most_confident_first_with_counts(self, api):
        body = api.client.get("/api/ai-tags/review").json()
        assert [(r["label"], r["count"]) for r in body] == [("tiger", 1), ("beach", 1), ("zoo", 3)]
        assert body[0]["top_confidence"] == pytest.approx(0.9)
        assert body[2]["top_confidence"] == pytest.approx(0.5)

    def test_a_labels_photos_come_best_first_with_their_names(self, api):
        body = self._items(api)
        assert [(i["file_hash"], i["name"]) for i in body["items"]] == [
            ("h-city", "city.jpg"),
            ("h-tiger", "tiger.jpg"),
            ("h-beach", "beach.jpg"),
        ]
        assert body["total"] == 3
        assert body["items"][0]["confidence"] == pytest.approx(0.5)

    def test_items_page_and_filter_by_confidence(self, api):
        assert [i["file_hash"] for i in self._items(api, limit=1, offset=1)["items"]] == ["h-tiger"]
        body = self._items(api, min_confidence=0.3)
        assert body["total"] == 2 and [i["file_hash"] for i in body["items"]] == [
            "h-city",
            "h-tiger",
        ]

    def test_a_label_with_nothing_open_is_404(self, api):
        assert (
            api.client.get("/api/ai-tags/review/items", params={"label": "nope"}).status_code == 404
        )

    def test_decided_suggestions_leave_the_queue(self, api):
        api.client.post("/api/photos/h-city/ai-tags", json={"label": "zoo", "action": "reject"})
        api.client.post("/api/photos/h-tiger/ai-tags", json={"label": "zoo", "action": "accept"})
        assert [i["file_hash"] for i in self._items(api)["items"]] == ["h-beach"]

    def test_the_count_says_what_accept_above_would_do(self, api):
        count = api.client.get(
            "/api/ai-tags/review/count", params={"label": "zoo", "min_confidence": 0.3}
        )
        assert count.json() == {"count": 2}

    def test_accept_above_accepts_only_those_at_or_above_the_confidence(self, api):
        response = api.client.post(
            "/api/ai-tags/accept-above", json={"label": "zoo", "min_confidence": 0.3}
        )
        assert response.json() == {"photos_changed": 2, "tags_changed": 2}
        assert api.client.get("/api/photos/h-city").json()["labels"] == ["zoo"]
        assert api.client.get("/api/photos/h-tiger").json()["labels"] == ["zoo"]
        assert api.client.get("/api/photos/h-beach").json()["labels"] == []
        assert [i["file_hash"] for i in self._items(api)["items"]] == ["h-beach"]

    def test_accept_above_validates_the_confidence(self, api):
        bad = api.client.post(
            "/api/ai-tags/accept-above", json={"label": "zoo", "min_confidence": 2}
        )
        assert bad.status_code == 422

    def test_accept_above_refuses_when_the_count_changed_since_it_was_confirmed(self, api):
        body = {"label": "zoo", "min_confidence": 0.3, "expected_count": 3}
        response = api.client.post("/api/ai-tags/accept-above", json=body)
        assert response.status_code == 409
        assert "2 now" in response.json()["detail"]
        assert api.client.get("/api/photos/h-city").json()["labels"] == []  # nothing happened

    def test_accept_above_applies_when_the_confirmed_count_still_holds(self, api):
        body = {"label": "zoo", "min_confidence": 0.3, "expected_count": 2}
        response = api.client.post("/api/ai-tags/accept-above", json=body)
        assert response.status_code == 200 and response.json()["photos_changed"] == 2

    def test_a_threshold_reaches_a_confidence_stored_a_hair_below_it(self, api):
        api.analysis.save_ai_tags(
            "h-beach", [AiTag("beach", 0.8, "m"), AiTag("sea", 0.6999999, "m")]
        )
        count = api.client.get(
            "/api/ai-tags/review/count", params={"label": "sea", "min_confidence": 0.7}
        )
        assert count.json() == {"count": 1}
        assert (
            api.client.get(
                "/api/ai-tags/review/items", params={"label": "sea", "min_confidence": 0.7}
            ).json()["total"]
            == 1
        )


class TestKeepAnalysed:
    def test_it_is_off_by_default_and_counts_what_waits(self, api):
        body = api.client.get("/api/analysis/keep").json()
        assert body == {"enabled": False, "threshold": 2000, "pending": 3, "state": "off"}

    def test_turning_it_on_waits_for_the_model_and_never_downloads_it(self, api):
        body = api.client.put("/api/analysis/keep", json={"enabled": True}).json()
        assert body["enabled"] is True and body["state"] == "waiting_for_model"
        assert not api.store.is_installed()

    def test_after_a_change_the_app_counts_as_busy_so_it_waits_for_quiet(self, api):
        _install(api)
        body = api.client.put("/api/analysis/keep", json={"enabled": True}).json()
        assert body["state"] == "waiting_for_idle"  # this very request was activity

    def test_everything_else_in_place_it_is_ready_once_the_user_is_still(self, api):
        _install(api)
        api.client.put("/api/analysis/keep", json={"enabled": True})
        api.app.state.services.keep_analysed._activity._last = None  # nobody has done anything
        assert api.client.get("/api/analysis/keep").json()["state"] == "ready"
        job_id = api.app.state.services.keep_analysed.tick()
        job = wait_for_job(api.client, api.client.get(f"/api/jobs/{job_id}").json())
        assert job["kind"] == "analyze" and job["status"] == "succeeded"
        assert job["counts"]["analyzed"] == 3
        assert api.client.get("/api/analysis/keep").json()["state"] == "up_to_date"

    def test_the_setting_survives_a_restart(self, api):
        api.client.put("/api/analysis/keep", json={"enabled": True})
        again = TestClient(
            create_app(settings=api.settings, model_store=api.store, embedder=api.embedder)
        )
        assert again.get("/api/analysis/keep").json()["enabled"] is True

    def test_it_asks_when_more_photos_wait_than_the_threshold(self, api):
        small = Settings(**{**api.settings.__dict__, "keep_analysed_max": 2})
        app = create_app(settings=small, model_store=api.store, embedder=api.embedder)
        _install(api)
        with TestClient(app) as client:
            client.put("/api/analysis/keep", json={"enabled": True})
            body = client.get("/api/analysis/keep").json()
        assert (body["state"], body["pending"], body["threshold"]) == ("needs_approval", 3, 2)

    def test_a_bad_body_is_422(self, api):
        assert api.client.put("/api/analysis/keep", json={"enabled": "maybe"}).status_code == 422


class TestPauseRoute:
    def test_pausing_a_running_job_leaves_it_interrupted_and_resumable(self, api):
        import threading

        from photo_meta_organizer.application.jobs import JobOutcome

        started = threading.Event()

        def work(ctx):
            started.set()
            ctx.wait_for_cancel(5)
            return JobOutcome(cancelled=True, message="stopped")

        job = api.app.state.services.jobs.submit("sync", str(api.tmp / "lib"), work)
        started.wait(5)
        response = api.client.post(f"/api/jobs/{job.id}/pause")
        assert response.status_code == 202
        done = api.app.state.services.jobs.wait(job.id, timeout=5)
        assert done.status.value == "interrupted" and done.message.startswith("Paused")
        assert api.client.get(f"/api/jobs/{job.id}").json()["status"] == "interrupted"

    def test_pausing_a_finished_or_unknown_job_is_refused(self, api):
        _install(api)
        job = _analyze(api)
        assert api.client.post(f"/api/jobs/{job['id']}/pause").status_code == 409
        assert api.client.post("/api/jobs/nope/pause").status_code == 404
