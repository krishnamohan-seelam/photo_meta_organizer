"""Contract tests for AnalysisRepository (Phase 5): embeddings and suggested tags.

Parametrized over backends like the metadata contract, so a Phase 6 store has to pass the same
bodies unchanged. Today there is one.
"""

import pytest

from photo_meta_organizer.application.interfaces.analysis_repository import (
    AnalysisRepository,
    PendingPhoto,
)
from photo_meta_organizer.application.interfaces.search_types import SearchQuery
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

M = "clip-test"


def _make_sqlite(tmp_path):
    photos = SqliteRepository(db_path=str(tmp_path / "analysis.db"))
    return photos, SqliteAnalysisRepository(photos.connection, photos.lock)


BACKENDS = [("sqlite", _make_sqlite)]


@pytest.fixture(params=BACKENDS, ids=[name for name, _ in BACKENDS])
def stores(request, tmp_path):
    return request.param[1](tmp_path)


@pytest.fixture
def photos(stores):
    return stores[0]


@pytest.fixture
def analysis(stores):
    return stores[1]


def _photo(hash_: str, *, path: str | None = None, make: str | None = None) -> ImageMetadata:
    return ImageMetadata(
        file_hash=hash_,
        file_info=ImageFileInfo(
            name=f"{hash_}.jpg",
            path=path or f"/photos/{hash_}.jpg",
            size_bytes=10,
            mime_type="image/jpeg",
        ),
        dimensions=ImageDimensions(width=10, height=10),
        exif=ImageExifData(camera_make=make),
    )


def _emb(hash_: str, *vector: float, model: str = M) -> Embedding:
    return Embedding(file_hash=hash_, model_id=model, vector=vector)


def test_satisfies_the_port(analysis):
    assert isinstance(analysis, AnalysisRepository)


class TestEmbeddings:
    def test_save_and_get_store_a_unit_vector(self, photos, analysis):
        photos.save(_photo("a"))
        assert analysis.save_embeddings([_emb("a", 3.0, 4.0)]) == 1
        stored = analysis.get_embedding("a", M)
        assert stored is not None
        assert stored.vector == pytest.approx((0.6, 0.8), abs=1e-6)  # float32 round trip
        assert stored.model_id == M

    def test_get_of_nothing_is_none(self, photos, analysis):
        photos.save(_photo("a"))
        assert analysis.get_embedding("a", M) is None
        assert analysis.get_embedding("missing", M) is None

    def test_saving_again_replaces(self, photos, analysis):
        photos.save(_photo("a"))
        analysis.save_embeddings([_emb("a", 1.0, 0.0)])
        analysis.save_embeddings([_emb("a", 0.0, 1.0)])
        assert analysis.get_embedding("a", M).vector == pytest.approx((0.0, 1.0))
        assert analysis.count_embeddings(M) == 1

    def test_models_coexist(self, photos, analysis):
        photos.save(_photo("a"))
        analysis.save_embeddings([_emb("a", 1.0, 0.0), _emb("a", 0.0, 1.0, model="other")])
        assert analysis.get_embedding("a", M).vector == pytest.approx((1.0, 0.0))
        assert analysis.get_embedding("a", "other").vector == pytest.approx((0.0, 1.0))

    def test_photos_that_no_longer_exist_are_skipped(self, photos, analysis):
        photos.save(_photo("here"))
        assert analysis.save_embeddings([_emb("here", 1.0), _emb("gone", 1.0)]) == 1
        assert analysis.count_embeddings(M) == 1

    def test_pending_photos_are_those_without_this_models_embedding(self, photos, analysis):
        photos.save_many([_photo("a", path="/p/a.jpg"), _photo("b", path="/p/b.jpg")])
        assert analysis.pending_photos(M) == [
            PendingPhoto("a", "/p/a.jpg"),
            PendingPhoto("b", "/p/b.jpg"),
        ]
        analysis.save_embeddings([_emb("a", 1.0)])
        assert analysis.pending_photos(M) == [PendingPhoto("b", "/p/b.jpg")]
        assert len(analysis.pending_photos("another-model")) == 2

    def test_pending_photos_honours_the_limit(self, photos, analysis):
        photos.save_many([_photo(h, path=f"/p/{h}.jpg") for h in "abc"])
        assert [p.file_hash for p in analysis.pending_photos(M, limit=2)] == ["a", "b"]

    def test_clear_one_model_or_all(self, photos, analysis):
        photos.save_many([_photo("a"), _photo("b")])
        analysis.save_embeddings([_emb("a", 1.0), _emb("b", 1.0), _emb("a", 1.0, model="o")])
        assert analysis.clear_embeddings(M) == 2
        assert analysis.count_embeddings(M) == 0
        assert analysis.count_embeddings("o") == 1
        assert analysis.clear_embeddings() == 1


class TestNearest:
    def _library(self, photos, analysis):
        photos.save_many(
            [
                _photo("east", make="Sony"),
                _photo("north", make="Canon"),
                _photo("northeast", make="Sony"),
                _photo("west", make="Sony"),
            ]
        )
        analysis.save_embeddings(
            [
                _emb("east", 1.0, 0.0),
                _emb("north", 0.0, 1.0),
                _emb("northeast", 1.0, 1.0),
                _emb("west", -1.0, 0.0),
            ]
        )

    def test_ranks_by_cosine_similarity(self, photos, analysis):
        self._library(photos, analysis)
        hits = analysis.nearest([1.0, 0.2], k=4, model_id=M)
        assert [h.file_hash for h in hits] == ["east", "northeast", "north", "west"]
        assert hits[0].score == pytest.approx(0.9806, abs=1e-3)
        assert hits[-1].score < 0

    def test_the_length_of_the_query_does_not_matter(self, photos, analysis):
        self._library(photos, analysis)
        small = analysis.nearest([0.01, 0.002], k=2, model_id=M)
        large = analysis.nearest([100.0, 20.0], k=2, model_id=M)
        assert [h.file_hash for h in small] == [h.file_hash for h in large]
        assert small[0].score == pytest.approx(large[0].score)

    def test_returns_at_most_k(self, photos, analysis):
        self._library(photos, analysis)
        assert len(analysis.nearest([1.0, 0.0], k=2, model_id=M)) == 2
        assert analysis.nearest([1.0, 0.0], k=0, model_id=M) == []

    def test_filters_decide_who_competes(self, photos, analysis):
        self._library(photos, analysis)
        hits = analysis.nearest([0.0, 1.0], k=5, model_id=M, query=SearchQuery(camera_make="Sony"))
        assert [h.file_hash for h in hits] == ["northeast", "east", "west"]

    def test_a_photo_can_be_left_out(self, photos, analysis):
        self._library(photos, analysis)
        hits = analysis.nearest([1.0, 0.0], k=2, model_id=M, exclude_hash="east")
        assert [h.file_hash for h in hits] == ["northeast", "north"]

    def test_only_the_asked_model_and_dimension_compete(self, photos, analysis):
        self._library(photos, analysis)
        photos.save(_photo("other-model"))
        photos.save(_photo("wide"))
        analysis.save_embeddings(
            [_emb("other-model", 1.0, 0.0, model="o"), _emb("wide", 1.0, 0.0, 0.0)]
        )
        hashes = {h.file_hash for h in analysis.nearest([1.0, 0.0], k=10, model_id=M)}
        assert hashes == {"east", "north", "northeast", "west"}

    def test_nothing_stored_means_no_hits(self, photos, analysis):
        photos.save(_photo("a"))
        assert analysis.nearest([1.0, 0.0], k=3, model_id=M) == []

    def test_ties_break_by_hash_so_results_are_stable(self, photos, analysis):
        photos.save_many([_photo("b"), _photo("a")])
        analysis.save_embeddings([_emb("b", 1.0, 0.0), _emb("a", 1.0, 0.0)])
        assert [h.file_hash for h in analysis.nearest([1.0, 0.0], k=2, model_id=M)] == ["a", "b"]


class TestLifecycle:
    """Results belong to a photo's content: they go with it, and only with it."""

    def test_deleting_a_photo_deletes_its_results(self, photos, analysis):
        photos.save(_photo("a"))
        analysis.save_embeddings([_emb("a", 1.0)])
        analysis.save_ai_tags("a", [AiTag("beach", 0.5, M)])
        photos.delete("a")
        assert analysis.count_embeddings(M) == 0
        assert analysis.list_ai_tags("a") == []

    def test_a_modified_file_loses_its_old_results_and_is_pending_again(self, photos, analysis):
        photos.save(_photo("old", path="/p/x.jpg"))
        analysis.save_embeddings([_emb("old", 1.0)])
        analysis.save_ai_tags("old", [AiTag("beach", 0.5, M)])
        photos.replace("old", _photo("new", path="/p/x.jpg"))
        assert analysis.count_embeddings(M) == 0
        assert analysis.list_ai_tags("new") == []
        assert analysis.pending_photos(M) == [PendingPhoto("new", "/p/x.jpg")]

    def test_saving_unchanged_content_again_keeps_its_results(self, photos, analysis):
        photos.save(_photo("a"))
        analysis.save_embeddings([_emb("a", 1.0)])
        analysis.save_ai_tags("a", [AiTag("beach", 0.5, M)])
        photos.save(_photo("a"))  # a re-run of index over the same content
        assert analysis.count_embeddings(M) == 1
        assert [t.label for t in analysis.list_ai_tags("a")] == ["beach"]


class TestAiTags:
    def test_lists_most_confident_first_with_the_model(self, photos, analysis):
        photos.save(_photo("a"))
        analysis.save_ai_tags(
            "a", [AiTag("sky", 0.2, M), AiTag("beach", 0.7, M), AiTag("sea", 0.4, M)]
        )
        tags = analysis.list_ai_tags("a")
        assert [t.label for t in tags] == ["beach", "sea", "sky"]
        assert all(t.status is AiTagStatus.SUGGESTED and t.model_id == M for t in tags)
        assert tags[0].confidence == pytest.approx(0.7)

    def test_unknown_photos_are_ignored(self, analysis):
        analysis.save_ai_tags("nobody", [AiTag("beach", 0.5, M)])
        assert analysis.list_ai_tags("nobody") == []

    def test_saving_again_replaces_what_is_still_suggested(self, photos, analysis):
        photos.save(_photo("a"))
        analysis.save_ai_tags("a", [AiTag("beach", 0.7, M), AiTag("sky", 0.2, M)])
        analysis.save_ai_tags("a", [AiTag("city", 0.6, M)])
        assert [t.label for t in analysis.list_ai_tags("a")] == ["city"]

    def test_accepted_and_rejected_tags_survive_a_re_analysis(self, photos, analysis):
        photos.save(_photo("a"))
        analysis.save_ai_tags(
            "a", [AiTag("beach", 0.7, M), AiTag("sky", 0.6, M), AiTag("sea", 0.5, M)]
        )
        analysis.set_ai_tag_status("a", "beach", AiTagStatus.ACCEPTED)
        analysis.set_ai_tag_status("a", "sky", AiTagStatus.REJECTED)
        # The new run suggests all three again (and a new one).
        analysis.save_ai_tags(
            "a",
            [
                AiTag("beach", 0.9, "m2"),
                AiTag("sky", 0.9, "m2"),
                AiTag("sea", 0.9, "m2"),
                AiTag("dog", 0.3, "m2"),
            ],
        )
        by_label = {t.label: t for t in analysis.list_ai_tags("a")}
        assert by_label["beach"].status is AiTagStatus.ACCEPTED
        assert by_label["sky"].status is AiTagStatus.REJECTED  # never suggested again
        assert by_label["sea"].status is AiTagStatus.SUGGESTED
        assert by_label["sea"].model_id == "m2"
        assert by_label["dog"].status is AiTagStatus.SUGGESTED
        assert len(by_label) == 4

    def test_set_status(self, photos, analysis):
        photos.save(_photo("a"))
        analysis.save_ai_tags("a", [AiTag("beach", 0.7, M)])
        assert analysis.set_ai_tag_status("a", "beach", AiTagStatus.ACCEPTED) is True
        assert analysis.list_ai_tags("a")[0].status is AiTagStatus.ACCEPTED
        assert analysis.set_ai_tag_status("a", "nope", AiTagStatus.ACCEPTED) is False
        assert analysis.set_ai_tag_status("missing", "beach", AiTagStatus.ACCEPTED) is False

    def test_counts_per_label_by_status(self, photos, analysis):
        photos.save_many([_photo("a"), _photo("b"), _photo("c")])
        analysis.save_ai_tags("a", [AiTag("beach", 0.7, M), AiTag("sky", 0.2, M)])
        analysis.save_ai_tags("b", [AiTag("beach", 0.6, M)])
        analysis.save_ai_tags("c", [AiTag("sky", 0.6, M), AiTag("city", 0.5, M)])
        analysis.set_ai_tag_status("c", "sky", AiTagStatus.ACCEPTED)
        assert analysis.ai_tag_counts() == [("beach", 2), ("city", 1), ("sky", 1)]
        assert analysis.ai_tag_counts(AiTagStatus.ACCEPTED) == [("sky", 1)]
        assert analysis.ai_tag_counts(AiTagStatus.REJECTED) == []


def test_an_existing_database_gains_the_analysis_tables(tmp_path):
    """Opening a database from before Phase 5 must just work: the tables are added in place."""
    path = str(tmp_path / "old.db")
    first = SqliteRepository(path)
    first.save(_photo("a"))
    with first.lock, first.connection:
        first.connection.executescript("DROP TABLE photo_embeddings; DROP TABLE photo_ai_tags;")
    first.close()

    reopened = SqliteRepository(path)
    analysis = SqliteAnalysisRepository(reopened.connection, reopened.lock)
    assert analysis.save_embeddings([_emb("a", 1.0, 0.0)]) == 1
    assert [p.file_hash for p in reopened.query(SearchQuery())] == ["a"]
