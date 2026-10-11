"""AnalyzePhotos: embed what has no embedding yet, suggest tags, survive bad files (Phase 5)."""

from pathlib import Path

import pytest
from tests.fakes import FakeImageEmbedder

from photo_meta_organizer.application.use_cases.analyze_photos_use_case import (
    AnalyzePhotosUseCase,
    AnalyzeProgress,
)
from photo_meta_organizer.application.zero_shot_tagger import ZeroShotTagger
from photo_meta_organizer.domain.analysis import AiTagStatus
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


@pytest.fixture
def photos(tmp_path):
    repo = SqliteRepository(str(tmp_path / "a.db"))
    yield repo
    repo.close()


@pytest.fixture
def analysis(photos):
    return SqliteAnalysisRepository(photos.connection, photos.lock)


@pytest.fixture
def embedder():
    return FakeImageEmbedder()


def _add(photos, tmp_path: Path, name: str, content: bytes | None = b"pixels") -> ImageMetadata:
    """A photo record; its file is written unless ``content`` is None (a file gone missing)."""
    path = tmp_path / "lib" / name
    path.parent.mkdir(exist_ok=True)
    if content is not None:
        path.write_bytes(content + name.encode())
    meta = ImageMetadata(
        file_hash=f"hash-{name}",
        file_info=ImageFileInfo(name=name, path=str(path), size_bytes=10, mime_type="image/jpeg"),
        dimensions=ImageDimensions(width=10, height=10),
        exif=ImageExifData(),
    )
    photos.save(meta)
    return meta


def _use_case(analysis, embedder, **kwargs) -> AnalyzePhotosUseCase:
    return AnalyzePhotosUseCase(analysis=analysis, embedder=embedder, **kwargs)


class TestEmbedding:
    def test_embeds_every_photo_that_has_none(self, photos, analysis, embedder, tmp_path):
        for name in ("a.jpg", "b.jpg", "c.jpg"):
            _add(photos, tmp_path, name)
        report = _use_case(analysis, embedder).run()
        assert (report.total, report.analyzed, report.errors) == (3, 3, [])
        assert analysis.count_embeddings(embedder.model_id) == 3
        stored = analysis.get_embedding("hash-a.jpg", embedder.model_id)
        assert stored is not None and stored.dimension == embedder.dimension

    def test_a_second_run_has_nothing_to_do(self, photos, analysis, embedder, tmp_path):
        _add(photos, tmp_path, "a.jpg")
        _use_case(analysis, embedder).run()
        calls = embedder.image_calls
        report = _use_case(analysis, embedder).run()
        assert (report.total, report.analyzed) == (0, 0)
        assert embedder.image_calls == calls

    def test_reanalyze_redoes_everything(self, photos, analysis, embedder, tmp_path):
        _add(photos, tmp_path, "a.jpg")
        _add(photos, tmp_path, "b.jpg")
        _use_case(analysis, embedder).run()
        report = _use_case(analysis, embedder).run(reanalyze=True)
        assert report.analyzed == 2
        assert analysis.count_embeddings(embedder.model_id) == 2

    def test_limit_caps_one_run_and_the_next_continues(self, photos, analysis, embedder, tmp_path):
        for name in ("a.jpg", "b.jpg", "c.jpg"):
            _add(photos, tmp_path, name)
        assert _use_case(analysis, embedder).run(limit=2).analyzed == 2
        assert _use_case(analysis, embedder).run().analyzed == 1

    def test_a_new_model_analyses_everything_again_next_to_the_old_results(
        self, photos, analysis, tmp_path
    ):
        _add(photos, tmp_path, "a.jpg")
        _use_case(analysis, FakeImageEmbedder("model-1")).run()
        report = _use_case(analysis, FakeImageEmbedder("model-2")).run()
        assert report.analyzed == 1
        assert analysis.count_embeddings("model-1") == analysis.count_embeddings("model-2") == 1

    def test_a_modified_file_is_analysed_again(self, photos, analysis, embedder, tmp_path):
        old = _add(photos, tmp_path, "a.jpg", b"first")
        _use_case(analysis, embedder).run()
        # sync saw the file change: the record is replaced under its new content hash
        path = Path(old.file_info.path)
        path.write_bytes(b"second")
        new = ImageMetadata(
            file_hash="hash-new",
            file_info=old.file_info,
            dimensions=old.dimensions,
            exif=old.exif,
        )
        photos.replace(old.file_hash, new)
        report = _use_case(analysis, embedder).run()
        assert report.analyzed == 1
        assert analysis.get_embedding("hash-new", embedder.model_id) is not None
        assert analysis.get_embedding(old.file_hash, embedder.model_id) is None

    def test_threads_give_the_same_result_as_one(self, photos, analysis, tmp_path):
        for i in range(12):
            _add(photos, tmp_path, f"{i:02d}.jpg")
        single = FakeImageEmbedder()
        _use_case(analysis, single, workers=1).run()
        expected = {
            h: analysis.get_embedding(h, single.model_id).vector
            for h in (f"hash-{i:02d}.jpg" for i in range(12))
        }
        analysis.clear_embeddings()
        _use_case(analysis, single, workers=4, batch_size=3).run()
        for h, vector in expected.items():
            assert analysis.get_embedding(h, single.model_id).vector == pytest.approx(vector)


class TestTags:
    def test_suggested_tags_are_saved_for_each_new_embedding(
        self, photos, analysis, embedder, tmp_path
    ):
        _add(photos, tmp_path, "a.jpg")
        tagger = ZeroShotTagger(embedder, ["alpha", "beta", "gamma"])
        report = _use_case(analysis, embedder, tagger=tagger, tag_threshold=0.0).run()
        assert report.tagged == 1
        tags = analysis.list_ai_tags("hash-a.jpg")
        assert tags and {t.label for t in tags} <= {"alpha", "beta", "gamma"}
        assert all(
            t.status is AiTagStatus.SUGGESTED and t.model_id == embedder.model_id for t in tags
        )

    def test_no_tagger_means_no_tags(self, photos, analysis, embedder, tmp_path):
        _add(photos, tmp_path, "a.jpg")
        report = _use_case(analysis, embedder).run()
        assert report.tagged == 0
        assert analysis.list_ai_tags("hash-a.jpg") == []

    def test_reanalysis_keeps_what_the_user_decided(self, photos, analysis, embedder, tmp_path):
        _add(photos, tmp_path, "a.jpg")
        tagger = ZeroShotTagger(embedder, ["alpha", "beta", "gamma"])
        use_case = _use_case(analysis, embedder, tagger=tagger, tag_threshold=0.0)
        use_case.run()
        first = analysis.list_ai_tags("hash-a.jpg")[0].label
        analysis.set_ai_tag_status("hash-a.jpg", first, AiTagStatus.REJECTED)
        use_case.run(reanalyze=True)
        statuses = {t.label: t.status for t in analysis.list_ai_tags("hash-a.jpg")}
        assert statuses[first] is AiTagStatus.REJECTED


class TestFailures:
    def test_a_missing_file_is_reported_and_the_rest_continue(
        self, photos, analysis, embedder, tmp_path
    ):
        _add(photos, tmp_path, "a.jpg")
        _add(photos, tmp_path, "gone.jpg", content=None)
        _add(photos, tmp_path, "c.jpg")
        report = _use_case(analysis, embedder).run()
        assert (report.total, report.analyzed) == (3, 2)
        assert len(report.errors) == 1 and "gone.jpg" in report.errors[0]
        assert analysis.get_embedding("hash-gone.jpg", embedder.model_id) is None

    def test_an_undecodable_file_is_reported(self, photos, analysis, embedder, tmp_path):
        meta = _add(photos, tmp_path, "empty.jpg", content=None)
        Path(meta.file_info.path).write_bytes(b"")  # the fake cannot decode an empty image
        _add(photos, tmp_path, "ok.jpg")
        report = _use_case(analysis, embedder).run()
        assert report.analyzed == 1
        assert "empty.jpg" in report.errors[0]

    def test_a_failed_photo_is_tried_again_next_time(self, photos, analysis, embedder, tmp_path):
        _add(photos, tmp_path, "later.jpg", content=None)
        assert _use_case(analysis, embedder).run().analyzed == 0
        (tmp_path / "lib" / "later.jpg").write_bytes(b"now it exists")
        assert _use_case(analysis, embedder).run().analyzed == 1


class TestProgressAndCancel:
    def test_progress_counts_every_photo_including_failures(
        self, photos, analysis, embedder, tmp_path
    ):
        _add(photos, tmp_path, "a.jpg")
        _add(photos, tmp_path, "gone.jpg", content=None)
        _add(photos, tmp_path, "c.jpg")
        seen: list[AnalyzeProgress] = []
        _use_case(analysis, embedder).run(progress=seen.append)
        assert seen[-1] == AnalyzeProgress(total=3, processed=3, failed=1)
        assert [p.processed for p in seen] == sorted(p.processed for p in seen)

    def test_cancelling_keeps_what_was_done_and_says_so(self, photos, analysis, embedder, tmp_path):
        for i in range(10):
            _add(photos, tmp_path, f"{i}.jpg")
        done = []

        def stop_after_first_batch() -> bool:
            return analysis.count_embeddings(embedder.model_id) >= 2

        report = _use_case(analysis, embedder, workers=1, batch_size=2).run(
            progress=done.append, should_cancel=stop_after_first_batch
        )
        assert report.cancelled is True
        assert 2 <= report.analyzed < 10
        assert analysis.count_embeddings(embedder.model_id) == report.analyzed
        # ...and a later run finishes the rest
        assert _use_case(analysis, embedder).run().analyzed == 10 - report.analyzed
