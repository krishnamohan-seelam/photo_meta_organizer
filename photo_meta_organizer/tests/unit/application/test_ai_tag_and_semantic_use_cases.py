"""ResolveAiTags and SemanticSearch: the application logic behind the Phase 5 endpoints."""

import io

import pytest
from tests.fakes import FakeImageEmbedder

from photo_meta_organizer.application.interfaces.search_types import SearchQuery
from photo_meta_organizer.application.use_cases.resolve_ai_tags_use_case import (
    ResolveAiTagsUseCase,
)
from photo_meta_organizer.application.use_cases.semantic_search_use_case import (
    AnalysisNotReadyError,
    SemanticSearchUseCase,
)
from photo_meta_organizer.domain.analysis import AiTag, AiTagStatus, Embedding
from photo_meta_organizer.domain.models import (
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.infrastructure.repositories.sqlite_analysis_repository import (
    SqliteAnalysisRepository,
)
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import SqliteRepository

M = "fake-embedder-v1"


@pytest.fixture
def photos(tmp_path):
    repo = SqliteRepository(str(tmp_path / "a.db"))
    yield repo
    repo.close()


@pytest.fixture
def analysis(photos):
    return SqliteAnalysisRepository(photos.connection, photos.lock)


def _add(photos, name: str, make: str | None = None, labels: list[str] | None = None) -> str:
    h = f"h-{name}"
    photos.save(
        ImageMetadata(
            file_hash=h,
            file_info=ImageFileInfo(
                name=name, path=f"/lib/{name}", size_bytes=1, mime_type="image/jpeg"
            ),
            dimensions=ImageDimensions(width=1, height=1),
            exif=ImageExifData(camera_make=make),
            labels=labels or [],
        )
    )
    return h


class TestResolveAiTags:
    @pytest.fixture
    def use_case(self, photos, analysis):
        return ResolveAiTagsUseCase(analysis, photos)

    def test_accepting_adds_the_label_through_curation_and_marks_the_tag(
        self, photos, analysis, use_case
    ):
        h = _add(photos, "a.jpg", labels=["mine"])
        analysis.save_ai_tags(h, [AiTag("beach", 0.7, M)])
        assert use_case.resolve(h, "beach", "accept") is True
        assert photos.get_by_filehash(h).labels == ["mine", "beach"]
        assert analysis.list_ai_tags(h)[0].status is AiTagStatus.ACCEPTED

    def test_accepting_twice_does_not_duplicate_the_label(self, photos, analysis, use_case):
        h = _add(photos, "a.jpg")
        analysis.save_ai_tags(h, [AiTag("beach", 0.7, M)])
        use_case.resolve(h, "beach", "accept")
        use_case.resolve(h, "beach", "accept")
        assert photos.get_by_filehash(h).labels == ["beach"]

    def test_rejecting_marks_the_tag_and_leaves_the_labels_alone(self, photos, analysis, use_case):
        h = _add(photos, "a.jpg", labels=["mine"])
        analysis.save_ai_tags(h, [AiTag("beach", 0.7, M)])
        assert use_case.resolve(h, "beach", "reject") is True
        assert photos.get_by_filehash(h).labels == ["mine"]
        assert analysis.list_ai_tags(h)[0].status is AiTagStatus.REJECTED

    def test_reset_brings_a_rejected_tag_back_without_touching_labels(
        self, photos, analysis, use_case
    ):
        h = _add(photos, "a.jpg")
        analysis.save_ai_tags(h, [AiTag("beach", 0.7, M)])
        use_case.resolve(h, "beach", "reject")
        assert use_case.resolve(h, "beach", "reset") is True
        assert analysis.list_ai_tags(h)[0].status is AiTagStatus.SUGGESTED
        assert photos.get_by_filehash(h).labels == []

    def test_unknown_photo_or_tag_changes_nothing(self, photos, analysis, use_case):
        h = _add(photos, "a.jpg")
        analysis.save_ai_tags(h, [AiTag("beach", 0.7, M)])
        assert use_case.resolve("missing", "beach", "accept") is False
        assert use_case.resolve(h, "nope", "accept") is False
        assert photos.get_by_filehash(h).labels == []

    def test_an_invalid_action_is_refused(self, photos, analysis, use_case):
        with pytest.raises(ValueError, match="action"):
            use_case.resolve("h", "beach", "delete")  # type: ignore[arg-type]

    def test_batch_accept_takes_every_suggestion_of_every_photo(self, photos, analysis, use_case):
        a, b, c = (_add(photos, f"{n}.jpg") for n in "abc")
        analysis.save_ai_tags(a, [AiTag("beach", 0.7, M), AiTag("sea", 0.2, M)])
        analysis.save_ai_tags(b, [AiTag("beach", 0.6, M)])
        analysis.save_ai_tags(c, [AiTag("dog", 0.9, M)])
        result = use_case.resolve_many([a, b], None, "accept")
        assert (result.photos_changed, result.tags_changed) == (2, 3)
        assert photos.get_by_filehash(a).labels == ["beach", "sea"]
        assert photos.get_by_filehash(b).labels == ["beach"]
        assert photos.get_by_filehash(c).labels == []  # not in the batch

    def test_batch_with_labels_only_touches_those(self, photos, analysis, use_case):
        a = _add(photos, "a.jpg")
        analysis.save_ai_tags(a, [AiTag("beach", 0.7, M), AiTag("sea", 0.2, M)])
        result = use_case.resolve_many([a], ["sea"], "reject")
        assert result.tags_changed == 1
        statuses = {t.label: t.status for t in analysis.list_ai_tags(a)}
        assert statuses == {"beach": AiTagStatus.SUGGESTED, "sea": AiTagStatus.REJECTED}

    def test_batch_without_labels_skips_tags_already_decided(self, photos, analysis, use_case):
        a = _add(photos, "a.jpg")
        analysis.save_ai_tags(a, [AiTag("beach", 0.7, M), AiTag("sea", 0.2, M)])
        use_case.resolve(a, "sea", "reject")
        result = use_case.resolve_many([a], None, "accept")
        assert result.tags_changed == 1
        assert photos.get_by_filehash(a).labels == ["beach"]

    def test_batch_ignores_unknown_hashes(self, photos, analysis, use_case):
        a = _add(photos, "a.jpg")
        analysis.save_ai_tags(a, [AiTag("beach", 0.7, M)])
        result = use_case.resolve_many(["missing", a], None, "accept")
        assert (result.photos_changed, result.tags_changed) == (1, 1)


class TestSemanticSearch:
    @pytest.fixture
    def embedder(self):
        return FakeImageEmbedder()

    @pytest.fixture
    def library(self, photos, analysis, embedder):
        """Photos whose 'image' is the bytes of their own name, so embed_text(name) matches."""
        for name, make in (("tiger", "Sony"), ("beach", "Canon"), ("city", "Sony")):
            h = _add(photos, name, make=make)
            vector = embedder.embed_image(io.BytesIO(name.encode()), f"{name}.jpg")
            analysis.save_embeddings([Embedding(h, embedder.model_id, tuple(vector))])
        return photos

    def _use_case(self, analysis, embedder, photos):
        return SemanticSearchUseCase(analysis, embedder, photos)

    def test_text_finds_the_photo_it_describes_first(self, library, analysis, embedder):
        hits = self._use_case(analysis, embedder, library).by_text("tiger", k=3)
        assert hits[0].photo.file_hash == "h-tiger"
        assert hits[0].score == pytest.approx(1.0, abs=1e-5)
        assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)

    def test_filters_decide_who_competes(self, library, analysis, embedder):
        query = SearchQuery(camera_make="Canon")
        hits = self._use_case(analysis, embedder, library).by_text("tiger", query=query, k=5)
        assert [h.photo.file_hash for h in hits] == ["h-beach"]

    def test_k_limits_the_hits(self, library, analysis, embedder):
        assert len(self._use_case(analysis, embedder, library).by_text("tiger", k=2)) == 2

    def test_similar_to_leaves_the_photo_itself_out(self, library, analysis, embedder):
        hits = self._use_case(analysis, embedder, library).similar_to("h-tiger", k=5)
        assert "h-tiger" not in [h.photo.file_hash for h in hits]
        assert len(hits) == 2

    def test_nothing_analysed_yet_is_not_an_empty_result(self, photos, analysis, embedder):
        _add(photos, "a.jpg")
        with pytest.raises(AnalysisNotReadyError):
            self._use_case(analysis, embedder, photos).by_text("anything")

    def test_similar_to_a_photo_that_has_no_embedding(self, library, analysis, embedder):
        _add(library, "late")
        with pytest.raises(AnalysisNotReadyError, match="not been analyzed"):
            self._use_case(analysis, embedder, library).similar_to("h-late")

    def test_similar_to_an_unknown_photo(self, library, analysis, embedder):
        with pytest.raises(KeyError):
            self._use_case(analysis, embedder, library).similar_to("nope")

    def test_blank_text_is_refused(self, library, analysis, embedder):
        with pytest.raises(ValueError, match="text"):
            self._use_case(analysis, embedder, library).by_text("   ")

    def test_hits_for_photos_deleted_meanwhile_are_dropped(self, library, analysis, embedder):
        use_case = self._use_case(analysis, embedder, library)
        library.connection.execute("PRAGMA foreign_keys = OFF")
        library.connection.execute("DELETE FROM photos WHERE file_hash = 'h-tiger'")
        library.connection.commit()
        assert "h-tiger" not in [h.photo.file_hash for h in use_case.by_text("tiger", k=5)]
