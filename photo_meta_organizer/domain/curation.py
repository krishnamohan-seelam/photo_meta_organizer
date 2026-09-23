"""Curation rules: the user-controlled fields of a photo (rating, flag, labels).

These invariants belong to the domain, not to any one entry point, so the API
schema, the repository and the CLI all share them.
"""

from dataclasses import dataclass, field, replace
from typing import Any, List, Optional, Union

from photo_meta_organizer.domain.models import ImageMetadata

MIN_RATING = 1
MAX_RATING = 5


def validate_rating(value: Any) -> Optional[int]:
    """Return ``value`` if it is a legal rating (an int in 1..5) or ``None`` (unrated).

    ``bool`` is rejected explicitly: ``True`` is an ``int`` in Python but is not a rating.

    Raises:
        ValueError: If the value is anything else.
    """
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not MIN_RATING <= value <= MAX_RATING
    ):
        raise ValueError(
            f"rating must be an integer from {MIN_RATING} to {MAX_RATING}, or null; got {value!r}"
        )
    return value


def is_valid_rating(value: Any) -> bool:
    """Non-raising form of :func:`validate_rating`."""
    try:
        validate_rating(value)
    except ValueError:
        return False
    return True


def validate_tag(value: Any) -> str:
    """Return a stripped tag, or raise ``ValueError`` if it is not a non-empty string."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"tag must be a non-empty string; got {value!r}")
    return value.strip()


def merge_labels(current: list[str], additions: list[str]) -> list[str]:
    """Append ``additions`` to ``current``, keeping insertion order and dropping duplicates."""
    merged = list(dict.fromkeys(current))
    for tag in additions:
        if tag not in merged:
            merged.append(tag)
    return merged


def carry_over_curation(target: ImageMetadata, *sources: ImageMetadata) -> ImageMetadata:
    """Return ``target`` with the user's curation merged in from ``sources``.

    A fresh extraction always carries default curation (unrated, unflagged, no
    labels), so re-saving it would wipe what the user did. Identity and extracted
    data stay ``target``'s; only ``rating``, ``flagged`` and ``labels`` are merged.

    ``sources`` are in priority order (highest first): the rating comes from the first
    of ``target`` then the sources that has one, ``flagged`` is true if any is, and
    labels are unioned, ``target``'s first.
    """
    records = (target, *sources)
    rating = next((r.rating for r in records if r.rating is not None), None)
    labels: list[str] = []
    for record in records:
        labels = merge_labels(labels, list(record.labels))
    return replace(
        target,
        rating=rating,
        flagged=any(r.flagged for r in records),
        labels=labels,
    )


# ============================================================================
# Typed curation commands (PMO-07): a closed set replacing the old
# ``{"action": ..., "value": ...}`` dicts passed to the repository. Validation
# happens at construction time, so a repository never has to trust a caller's dict.
# ============================================================================


@dataclass(frozen=True)
class SetRating:
    """Set (or clear, with ``value=None``) a photo's rating."""

    value: Optional[int]

    def __post_init__(self) -> None:
        validate_rating(self.value)


@dataclass(frozen=True)
class SetFlag:
    """Set a photo's flagged state."""

    value: bool

    def __post_init__(self) -> None:
        if not isinstance(self.value, bool):
            raise ValueError(f"flagged must be a boolean; got {self.value!r}")


@dataclass(frozen=True)
class AddTag:
    """Add one label to a photo, if not already present."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", validate_tag(self.value))


@dataclass(frozen=True)
class RemoveTag:
    """Remove one label from a photo, if present."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", validate_tag(self.value))


@dataclass(frozen=True)
class SetLabels:
    """Replace a photo's whole label list."""

    value: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", [validate_tag(t) for t in self.value])


CurationCommand = Union[SetRating, SetFlag, AddTag, RemoveTag, SetLabels]
