"""PMO-05: repair records that share a path (left behind by the old MODIFIED bug, B-01)."""

from datetime import datetime

import pytest

from photo_meta_organizer.application.use_cases.dedupe_paths_use_case import (
    DedupePathsUseCase,
)
from photo_meta_organizer.domain.models import (
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.infrastructure.repositories.tinydb_repository import TinyDBRepository


def _rec(file_hash, path, added, rating=None, flagged=False, labels=()):
    return ImageMetadata(
        file_hash=file_hash,
        file_info=ImageFileInfo(
            name=path.rsplit("/", 1)[-1], path=path, size_bytes=1, mime_type="image/jpeg"
        ),
        dimensions=ImageDimensions(width=1, height=1),
        exif=ImageExifData(),
        labels=list(labels),
        rating=rating,
        flagged=flagged,
        added_at=added,
    )


@pytest.fixture
def repo(tmp_path):
    r = TinyDBRepository(str(tmp_path / "db.json"))
    yield r
    r.close()


T1, T2, T3 = datetime(2024, 1, 1), datetime(2024, 2, 1), datetime(2024, 3, 1)


class TestDedupePaths:
    def test_no_duplicates_reports_nothing(self, repo):
        repo.save(_rec("a", "/p/a.jpg", T1))
        repo.save(_rec("b", "/p/b.jpg", T1))

        result = DedupePathsUseCase(repo).execute(apply=True)

        assert result.groups == [] and result.removed == 0
        assert repo.count() == 2

    def test_dry_run_is_the_default_and_writes_nothing(self, repo):
        repo.save(_rec("old", "/p/a.jpg", T1, rating=4))
        repo.save(_rec("new", "/p/a.jpg", T2))

        result = DedupePathsUseCase(repo).execute()

        assert len(result.groups) == 1
        assert result.removed == 0
        assert repo.count() == 2
        assert repo.get_by_filehash("new").rating is None

    def test_apply_keeps_the_newest_record_and_merges_curation(self, repo):
        repo.save(_rec("old", "/p/a.jpg", T1, rating=4, flagged=True, labels=["trip"]))
        repo.save(_rec("new", "/p/a.jpg", T2, labels=["beach"]))
        repo.save(_rec("other", "/p/b.jpg", T3))

        result = DedupePathsUseCase(repo).execute(apply=True)

        assert result.removed == 1
        assert repo.count() == 2
        assert repo.get_by_filehash("old") is None
        kept = repo.get_by_filehash("new")
        assert (kept.rating, kept.flagged) == (4, True)
        assert kept.labels == ["beach", "trip"]

    def test_group_reports_what_is_kept_and_what_goes(self, repo):
        repo.save(_rec("old", "/p/a.jpg", T1))
        repo.save(_rec("mid", "/p/a.jpg", T2))
        repo.save(_rec("new", "/p/a.jpg", T3))

        (group,) = DedupePathsUseCase(repo).execute().groups

        assert group.keep.file_hash == "new"
        assert [r.file_hash for r in group.drop] == ["mid", "old"]

    def test_newer_records_rating_wins_over_an_older_one(self, repo):
        repo.save(_rec("old", "/p/a.jpg", T1, rating=2))
        repo.save(_rec("new", "/p/a.jpg", T2, rating=5))

        DedupePathsUseCase(repo).execute(apply=True)

        assert repo.get_by_filehash("new").rating == 5

    def test_paths_that_differ_only_by_spelling_are_the_same_file(self, repo, tmp_path):
        real = tmp_path / "a.jpg"
        real.write_bytes(b"x")
        repo.save(_rec("old", str(real), T1))
        repo.save(_rec("new", str(tmp_path / "sub" / ".." / "a.jpg"), T2))

        result = DedupePathsUseCase(repo).execute(apply=True)

        assert result.removed == 1
        assert repo.count() == 1
