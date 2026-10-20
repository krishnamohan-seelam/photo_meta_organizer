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
    moved = replace(
        sample_image_metadata,
        file_info=replace(sample_image_metadata.file_info, path="/photos/moved.jpg"),
    )

    repo.save(moved)

    stored = repo.get_by_filehash(sample_image_metadata.file_hash)
    assert stored is not None
    assert stored.file_info.path == "/photos/moved.jpg"


def test_new_photo_is_stored_with_the_curation_it_arrives_with(
    repo: SqliteRepository, sample_image_metadata: ImageMetadata
) -> None:
    repo.save(replace(sample_image_metadata, rating=3, flagged=True))

    stored = repo.get_by_filehash(sample_image_metadata.file_hash)
    assert stored is not None
    assert (stored.rating, stored.flagged) == (3, True)
    assert stored.labels == sample_image_metadata.labels


def test_replace_writes_carried_over_curation(
    repo: SqliteRepository, sample_image_metadata: ImageMetadata
) -> None:
    repo.save(sample_image_metadata)
    edited = replace(
        sample_image_metadata,
        file_hash="f" * 64,
        rating=5,
        flagged=True,
        labels=["carried"],
    )

    repo.replace(sample_image_metadata.file_hash, edited)

    stored = repo.get_by_filehash("f" * 64)
    assert stored is not None
    assert (stored.rating, stored.flagged, stored.labels) == (5, True, ["carried"])


def test_replace_onto_existing_content_takes_the_merged_curation(
    repo: SqliteRepository, sample_image_metadata: ImageMetadata
) -> None:
    other = replace(sample_image_metadata, file_hash="e" * 64)
    other = replace(other, file_info=replace(other.file_info, path="/photos/other.jpg"), labels=[])
    repo.save(sample_image_metadata)
    repo.save(other)
    merged = replace(other, rating=2, flagged=True, labels=["merged"])

    repo.replace(sample_image_metadata.file_hash, merged)

    stored = repo.get_by_filehash(other.file_hash)
    assert stored is not None
    assert (stored.rating, stored.flagged, stored.labels) == (2, True, ["merged"])


def test_save_with_overwrite_curation_replaces_it(
    repo: SqliteRepository, sample_image_metadata: ImageMetadata
) -> None:
    repo.save(sample_image_metadata)

    repo.save(replace(sample_image_metadata, rating=1, labels=["only"]), overwrite_curation=True)

    stored = repo.get_by_filehash(sample_image_metadata.file_hash)
    assert stored is not None
    assert (stored.rating, stored.labels) == (1, ["only"])
