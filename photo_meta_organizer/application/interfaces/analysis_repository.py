"""Storage port for AI analysis results: embeddings and suggested tags (Phase 5, ADR-002).

Split from ``ImageMetadataRepository`` the way collections are: a distinct aggregate with its
own lifecycle. Everything here is keyed by a photo's content hash and disappears with the
photo; an edit that changes the content therefore also discards its stale results, while
re-saving unchanged content keeps them.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from photo_meta_organizer.application.interfaces.search_types import SearchQuery
from photo_meta_organizer.domain.analysis import AiTag, AiTagStatus, Embedding, ScoredPhoto


@dataclass(frozen=True)
class PendingPhoto:
    """A photo that has no embedding from the current model yet: what to open and analyse."""

    file_hash: str
    path: str


@runtime_checkable
class AnalysisRepository(Protocol):
    # ---- embeddings

    def save_embeddings(self, items: Sequence[Embedding]) -> int:
        """Store (or replace) embeddings as unit vectors, so a dot product is a cosine.

        Embeddings for photos that no longer exist are skipped, not an error: a file can be
        removed while a job analyses it. Returns how many were stored.
        """
        ...

    def get_embedding(self, file_hash: str, model_id: str) -> Embedding | None:
        """The stored (unit) vector of one photo for one model, or ``None``."""
        ...

    def pending_photos(self, model_id: str, limit: int | None = None) -> list[PendingPhoto]:
        """Photos with no embedding from ``model_id``, in a stable order."""
        ...

    def count_embeddings(self, model_id: str) -> int:
        """How many photos have an embedding from ``model_id``."""
        ...

    def clear_embeddings(self, model_id: str | None = None) -> int:
        """Drop the embeddings of one model (or of every model); returns how many."""
        ...

    def nearest(
        self,
        vector: Sequence[float],
        k: int,
        model_id: str,
        query: SearchQuery | None = None,
        exclude_hash: str | None = None,
    ) -> list[ScoredPhoto]:
        """The ``k`` photos most similar to ``vector``, best first (cosine similarity).

        Only photos matching the filters of ``query`` compete (paging, sort and the radius
        filter are ignored), so "sunset on the beach" can be restricted to one camera and
        year. ``exclude_hash`` leaves one photo out, for "similar to this one".
        """
        ...

    # ---- suggested tags

    def save_ai_tags(self, file_hash: str, tags: Sequence[AiTag]) -> None:
        """Replace the photo's still-*suggested* tags with ``tags``.

        Accepted and rejected tags are never touched, and a label the user already accepted
        or rejected is not suggested again. Unknown photos are ignored.
        """
        ...

    def list_ai_tags(self, file_hash: str) -> list[AiTag]:
        """The photo's tags in every status, most confident first."""
        ...

    def set_ai_tag_status(self, file_hash: str, label: str, status: AiTagStatus) -> bool:
        """Move one tag to ``status``. Returns ``False`` if the photo has no such tag.

        Accepting does not add the label to the photo; the use case does that through the
        metadata repository, so curation stays that repository's business.
        """
        ...

    def ai_tag_counts(self, status: AiTagStatus = AiTagStatus.SUGGESTED) -> list[tuple[str, int]]:
        """Each label and how many photos carry it in ``status``, most common first."""
        ...
