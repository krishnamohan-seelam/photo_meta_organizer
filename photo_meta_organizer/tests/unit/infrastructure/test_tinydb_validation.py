"""PMO-02: the repository enforces curation invariants itself (not just the API schema)."""

from datetime import datetime

import pytest

from photo_meta_organizer.domain.curation import validate_rating
from photo_meta_organizer.domain.models import (
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.infrastructure.repositories.tinydb_repository import TinyDBRepository


@pytest.fixture
def repo(tmp_path):
    repository = TinyDBRepository(str(tmp_path / "db.json"))
    repository.save(
        ImageMetadata(
            file_hash="h1",
            file_info=ImageFileInfo(name="a.jpg", path="/a.jpg", size_bytes=1, mime_type="image/jpeg"),
            dimensions=ImageDimensions(width=1, height=1),
            exif=ImageExifData(captured_at=datetime(2026, 1, 1)),
            rating=2,
        )
    )
    yield repository
    repository.close()


class TestValidateRating:
    @pytest.mark.parametrize("ok", [None, 1, 2, 3, 4, 5])
    def test_accepts(self, ok):
        assert validate_rating(ok) == ok

    @pytest.mark.parametrize("bad", ["abc", "3", 0, 6, -1, 2.5, True, False, [1]])
    def test_rejects(self, bad):
        with pytest.raises(ValueError):
            validate_rating(bad)


class TestRepositoryGuards:
    def test_update_metadata_rejects_bad_rating_and_keeps_old_value(self, repo):
        with pytest.raises(ValueError):
            repo.update_metadata("h1", {"rating": 9})
        assert repo.get_by_filehash("h1").rating == 2

    def test_batch_update_rejects_unknown_action(self, repo):
        with pytest.raises(ValueError):
            repo.batch_update(["h1"], {"action": "bogus", "value": 1})

    def test_batch_update_rejects_bad_rating_before_touching_anything(self, repo):
        with pytest.raises(ValueError):
            repo.batch_update(["h1"], {"action": "set_rating", "value": "abc"})
        assert repo.get_by_filehash("h1").rating == 2

    def test_batch_update_rejects_non_string_tag(self, repo):
        with pytest.raises(ValueError):
            repo.batch_update(["h1"], {"action": "add_tag", "value": 5})

    def test_batch_update_skips_unknown_hashes(self, repo):
        assert repo.batch_update(["missing"], {"action": "set_flag", "value": True}) == 0

    def test_labels_keep_insertion_order_and_are_deduplicated(self, repo):
        repo.update_metadata("h1", {"add_tags": ["b", "a", "b"]})
        assert repo.get_by_filehash("h1").labels == ["b", "a"]
        repo.update_metadata("h1", {"add_tags": ["c", "a"]})
        assert repo.get_by_filehash("h1").labels == ["b", "a", "c"]
