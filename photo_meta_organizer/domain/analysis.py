"""AI analysis types (Phase 5, ADR-002): embeddings and suggested tags.

Pure values, no I/O. An :class:`Embedding` is a photo's image vector from one model;
an :class:`AiTag` is a label a model *suggests*. Suggestions live apart from the user's
own ``labels`` and only become labels when accepted, so analysis can never overwrite
curation. Both are keyed by content hash, like everything else, and carry the id of the
model that produced them so a model change is detectable and old results are never
mistaken for new ones.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from photo_meta_organizer.domain.curation import validate_tag


def normalize(vector: Sequence[float]) -> tuple[float, ...]:
    """The vector scaled to unit length, so a dot product between two is their cosine.

    Raises ``ValueError`` for a vector with no direction: empty, all zeros, or holding a
    NaN or infinity (a model that produced one is broken, and storing it would poison every
    search that ranks against it).
    """
    if len(vector) == 0:
        raise ValueError("vector must not be empty")
    if not all(math.isfinite(x) for x in vector):
        raise ValueError("vector must contain only finite numbers")
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0.0:
        raise ValueError("vector must not be all zeros")
    return tuple(x / norm for x in vector)


@dataclass(frozen=True)
class Embedding:
    """One photo's image vector from one model."""

    file_hash: str
    model_id: str
    vector: tuple[float, ...]

    def __post_init__(self) -> None:
        for name in ("file_hash", "model_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        # Validates (finite, non-zero) and freezes a list into a tuple; the direction is kept,
        # the length is the repository's business (it stores unit vectors).
        normalize(self.vector)
        object.__setattr__(self, "vector", tuple(self.vector))

    @property
    def dimension(self) -> int:
        return len(self.vector)


class AiTagStatus(StrEnum):
    """Where a suggestion stands. Rejected ones are remembered so they are not suggested again."""

    SUGGESTED = "suggested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class AiTag:
    """A label a model suggests for a photo, with how sure it is (0 to 1)."""

    label: str
    confidence: float
    model_id: str
    status: AiTagStatus = AiTagStatus.SUGGESTED

    def __post_init__(self) -> None:
        # The same rule as a user's tag, so accepting a suggestion can never produce a label
        # the rest of the app would reject.
        object.__setattr__(self, "label", validate_tag(self.label))
        if not (math.isfinite(self.confidence) and 0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be between 0 and 1; got {self.confidence!r}")
        if not self.model_id.strip():
            raise ValueError("model_id must not be empty")


@dataclass(frozen=True)
class ScoredPhoto:
    """A search hit: a photo and its similarity (cosine, -1 to 1) to the query."""

    file_hash: str
    score: float
