"""analyze_work: the analysis use case as a JobManager job."""

import pytest
from tests.fakes import FakeImageEmbedder

from photo_meta_organizer.application.job_work import analyze_work
from photo_meta_organizer.application.jobs import JobManager
from photo_meta_organizer.application.use_cases.analyze_photos_use_case import AnalyzePhotosUseCase
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
def setup(tmp_path):
    photos = SqliteRepository(str(tmp_path / "a.db"))
    analysis = SqliteAnalysisRepository(photos.connection, photos.lock)
    for name in ("a.jpg", "b.jpg"):
        file = tmp_path / name
        file.write_bytes(name.encode())
        photos.save(
            ImageMetadata(
                file_hash=f"h-{name}",
                file_info=ImageFileInfo(
                    name=name, path=str(file), size_bytes=1, mime_type="image/jpeg"
                ),
                dimensions=ImageDimensions(width=1, height=1),
                exif=ImageExifData(),
            )
        )
    (tmp_path / "b.jpg").unlink()  # one photo's file is gone
    yield photos, analysis, FakeImageEmbedder()
    photos.close()


def test_runs_as_a_job_and_reports_counts_and_errors(setup):
    _, analysis, embedder = setup
    manager = JobManager()
    job = manager.submit(
        "analyze", "library", analyze_work(AnalyzePhotosUseCase(analysis, embedder))
    )
    manager.wait(job.id, timeout=10)
    done = manager.get(job.id)
    assert done.status.value == "succeeded"
    assert done.counts == {"total": 2, "analyzed": 1, "tagged": 0, "failed": 1}
    assert done.failed_count == 1
    assert "Analysed 1 photo(s)" in done.message
    assert len(done.errors) == 1 and "b.jpg" in done.errors[0]
    assert done.processed == 2 and done.total == 2
