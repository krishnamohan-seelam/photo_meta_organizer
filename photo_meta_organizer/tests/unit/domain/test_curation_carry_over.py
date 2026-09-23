"""PMO-05: user curation survives a re-extraction (flaw B-01)."""

from dataclasses import replace

from photo_meta_organizer.domain.curation import carry_over_curation
from photo_meta_organizer.domain.models import (
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)


def _rec(file_hash="h", rating=None, flagged=False, labels=()):
    return ImageMetadata(
        file_hash=file_hash,
        file_info=ImageFileInfo(name="a.jpg", path="/p/a.jpg", size_bytes=1, mime_type="image/jpeg"),
        dimensions=ImageDimensions(width=1, height=1),
        exif=ImageExifData(),
        labels=list(labels),
        rating=rating,
        flagged=flagged,
    )


def test_fresh_extraction_takes_curation_from_the_previous_record():
    fresh = _rec("new")
    old = _rec("old", rating=4, flagged=True, labels=["beach", "trip"])

    merged = carry_over_curation(fresh, old)

    assert merged.file_hash == "new"  # identity and extracted data stay the new record's
    assert (merged.rating, merged.flagged, merged.labels) == (4, True, ["beach", "trip"])


def test_no_sources_returns_the_record_unchanged():
    fresh = _rec("new", rating=2)
    assert carry_over_curation(fresh) == fresh


def test_earlier_source_wins_the_rating_and_labels_are_unioned_in_order():
    newest = _rec("a", rating=None, labels=["x"])
    older = _rec("b", rating=3, labels=["y", "x"])
    oldest = _rec("c", rating=5, flagged=True, labels=["z"])

    merged = carry_over_curation(_rec("t"), newest, older, oldest)

    assert merged.rating == 3          # first non-None in priority order
    assert merged.flagged is True      # flagged if any source was
    assert merged.labels == ["x", "y", "z"]


def test_target_curation_is_kept_when_sources_have_none():
    target = _rec("t", rating=5, labels=["keep"])
    merged = carry_over_curation(target, _rec("s"))
    assert merged.rating == 5 and merged.labels == ["keep"]


def test_result_is_a_copy_not_a_mutation_of_the_target():
    fresh = _rec("new")
    carry_over_curation(fresh, _rec("old", rating=4))
    assert fresh.rating is None
    assert replace(fresh) == fresh
