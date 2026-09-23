"""PMO-05/06: repository support for replace-on-modify and the mtime fingerprint."""

from datetime import datetime

import pytest

from photo_meta_organizer.domain.models import (
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.infrastructure.repositories.tinydb_repository import TinyDBRepository

MTIME = datetime(2024, 5, 4, 3, 2, 1, 500000)


def _rec(file_hash, path="/p/a.jpg", size=10, mtime=None, rating=None):
    return ImageMetadata(
        file_hash=file_hash,
        file_info=ImageFileInfo(
            name=path.rsplit("/", 1)[-1],
            path=path,
            size_bytes=size,
            mime_type="image/jpeg",
            modified_time=mtime,
        ),
        dimensions=ImageDimensions(width=1, height=1),
        exif=ImageExifData(),
        rating=rating,
    )


@pytest.fixture
def repo(tmp_path):
    r = TinyDBRepository(str(tmp_path / "db.json"))
    yield r
    r.close()


class TestReplace:
    def test_swaps_the_old_hash_for_the_new_one(self, repo):
        repo.save(_rec("old"))

        repo.replace("old", _rec("new", size=99))

        assert repo.count() == 1
        assert repo.get_by_filehash("old") is None
        assert repo.get_by_filehash("new").file_info.size_bytes == 99
        assert repo.get_by_path("/p/a.jpg").file_hash == "new"

    def test_unknown_old_hash_just_saves(self, repo):
        repo.replace("missing", _rec("new"))
        assert repo.count() == 1

    def test_same_hash_is_a_plain_update(self, repo):
        repo.save(_rec("h", size=1))
        repo.replace("h", _rec("h", size=2))
        assert repo.count() == 1
        assert repo.get_by_filehash("h").file_info.size_bytes == 2

    def test_new_hash_already_stored_elsewhere_collapses_into_one_record(self, repo):
        """Content is the identity: the edited file now equals another photo."""
        repo.save(_rec("old", path="/p/a.jpg"))
        repo.save(_rec("other", path="/p/b.jpg"))

        repo.replace("old", _rec("other", path="/p/a.jpg"))

        assert repo.count() == 1
        assert repo.get_by_filehash("other").file_info.path == "/p/a.jpg"


class TestFingerprintStorage:
    def test_mtime_round_trips(self, repo):
        repo.save(_rec("h", mtime=MTIME))
        assert repo.get_by_filehash("h").file_info.modified_time == MTIME

    def test_mtime_survives_reopening_the_file(self, tmp_path):
        path = str(tmp_path / "db.json")
        first = TinyDBRepository(path)
        first.save(_rec("h", mtime=MTIME))
        first.close()

        second = TinyDBRepository(path)
        try:
            assert second.get_by_filehash("h").file_info.modified_time == MTIME
        finally:
            second.close()

    def test_legacy_document_without_mtime_loads_as_none(self, repo):
        repo.save(_rec("h", mtime=MTIME))
        doc = repo._hash_index["h"]
        del doc["file_info"]["modified_time"]  # what a pre-PMO-06 file looks like

        assert repo.get_by_filehash("h").file_info.modified_time is None

    def test_refresh_fingerprints_updates_size_and_mtime_only(self, repo):
        repo.save(_rec("h", size=1, mtime=None, rating=4))

        assert repo.refresh_fingerprints([("h", 7, MTIME)]) == 1

        got = repo.get_by_filehash("h")
        assert (got.file_info.size_bytes, got.file_info.modified_time, got.rating) == (7, MTIME, 4)

    def test_refresh_fingerprints_unknown_hash_is_a_noop(self, repo):
        assert repo.refresh_fingerprints([("nope", 1, MTIME)]) == 0

    def test_refresh_fingerprints_persists(self, tmp_path):
        path = str(tmp_path / "db.json")
        first = TinyDBRepository(path)
        first.save(_rec("h"))
        first.refresh_fingerprints([("h", 3, MTIME)])
        first.close()

        second = TinyDBRepository(path)
        try:
            assert second.get_by_filehash("h").file_info.modified_time == MTIME
        finally:
            second.close()
