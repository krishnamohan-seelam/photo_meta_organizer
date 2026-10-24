"""ADR-003 R2: extraction never writes curation (rating, flagged, labels)."""

from dataclasses import replace
from pathlib import Path

import pytest

from photo_meta_organizer.domain.curation import AddTag, SetFlag, SetRating
from photo_meta_organizer.domain.models import ImageMetadata
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import SqliteRepository


@pytest.fixture
def repo(tmp_path: Path) -> SqliteRepository:
    repository = SqliteRepository(str(tmp_path / "photos.db"))
    yield repository
    repository.close()


def _fresh_extraction(metadata: ImageMetadata) -> ImageMetadata:
    """What the extractor produces on a re-index: default curation."""
    return replace(metadata, rating=None, flagged=False, labels=[])


def _curate(repo: SqliteRepository, file_hash: str) -> None:
    repo.apply(file_hash, SetRating(4))
    repo.apply(file_hash, SetFlag(True))
    repo.apply(file_hash, AddTag("keeper"))


def test_save_of_existing_photo_keeps_curation(
    repo: SqliteRepository, sample_image_metadata: ImageMetadata
) -> None:
    repo.save(sample_image_metadata)
    _curate(repo, sample_image_metadata.file_hash)

    repo.save(_fresh_extraction(sample_image_metadata))

    stored = repo.get_by_filehash(sample_image_metadata.file_hash)
    assert stored is not None
    assert stored.rating == 4
    assert stored.flagged is True
    assert "keeper" in stored.labels


def test_save_many_of_existing_photo_keeps_curation(
    repo: SqliteRepository, sample_image_metadata: ImageMetadata
) -> None:
    repo.save(sample_image_metadata)
    _curate(repo, sample_image_metadata.file_hash)

    repo.save_many([_fresh_extraction(sample_image_metadata)])

    stored = repo.get_by_filehash(sample_image_metadata.file_hash)
    assert stored is not None
    assert (stored.rating, stored.flagged) == (4, True)
    assert "keeper" in stored.labels


def test_save_still_updates_extracted_columns(
    repo: SqliteRepository, sample_image_metadata: ImageMetadata
) -> None:
    repo.save(sample_image_metadata)
    reextracted = replace(
        sample_image_metadata,
        exif=replace(sample_image_metadata.exif, camera_model="Re-read model"),
    )

    repo.save(reextracted)

    stored = repo.get_by_filehash(sample_image_metadata.file_hash)
    assert stored is not None
    assert stored.exif.camera_model == "Re-read model"


def test_new_photo_is_stored_with_the_curation_it_arrives_with(
    repo: SqliteRepository, sample_image_metadata: ImageMetadata
) -> None:
    repo.save(replace(sample_image_metadata, rating=3, flagged=True))

    stored = repo.get_by_filehash(sample_image_metadata.file_hash)
    assert stored is not None
    assert (stored.rating, stored.flagged) == (3, True)
    assert stored.labels == sample_image_metadata.labels


def test_save_with_overwrite_curation_replaces_it(
    repo: SqliteRepository, sample_image_metadata: ImageMetadata
) -> None:
    repo.save(sample_image_metadata)

    repo.save(replace(sample_image_metadata, rating=1, labels=["only"]), overwrite_curation=True)

    stored = repo.get_by_filehash(sample_image_metadata.file_hash)
    assert stored is not None
    assert (stored.rating, stored.labels) == (1, ["only"])
