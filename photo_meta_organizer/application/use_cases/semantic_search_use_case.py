"""Semantic search: find photos by meaning, or by resemblance to another (Phase 5, ADR-002).

A text query is embedded by the same model that embedded the photos and ranked against their
stored vectors; "similar to this photo" ranks against that photo's own vector. Candidates are
first restricted by the usual search filters in SQL, so a query can be limited to one camera and
year. Nothing analysed yet is an error, not an empty result, so the UI can say "analyse first"
instead of "no matches".
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from photo_meta_organizer.application.interfaces.analysis_repository import AnalysisRepository
from photo_meta_organizer.application.interfaces.image_embedder import ImageEmbedder
from photo_meta_organizer.application.interfaces.image_repository import ImageMetadataRepository
from photo_meta_organizer.application.interfaces.search_types import SearchQuery
from photo_meta_organizer.domain.models import ImageMetadata

logger = logging.getLogger(__name__)


class AnalysisNotReadyError(LookupError):
    """There is nothing to rank against yet: no photo (or not this one) has been analysed."""


@dataclass(frozen=True)
class SemanticHit:
    photo: ImageMetadata
    score: float


class SemanticSearchUseCase:
    def __init__(
        self,
        analysis: AnalysisRepository,
        embedder: ImageEmbedder,
        repository: ImageMetadataRepository,
    ) -> None:
        self._analysis = analysis
        self._embedder = embedder
        self._repository = repository

    def by_text(
        self, text: str, *, query: SearchQuery | None = None, k: int = 50
    ) -> list[SemanticHit]:
        """The ``k`` photos whose meaning is closest to ``text``, best first."""
        text = text.strip()
        if not text:
            raise ValueError("text must not be empty")
        model_id = self._embedder.model_id
        if self._analysis.count_embeddings(model_id) == 0:
            raise AnalysisNotReadyError("No photos have been analyzed yet. Run the analysis first.")
        vector = self._embedder.embed_text(text)
        return self._hits(self._analysis.nearest(vector, k, model_id, query))

    def similar_to(
        self, file_hash: str, *, query: SearchQuery | None = None, k: int = 50
    ) -> list[SemanticHit]:
        """The ``k`` photos that look most like ``file_hash`` (itself excluded), best first.

        Raises ``KeyError`` for an unknown photo and :class:`AnalysisNotReadyError` for one that
        has not been analysed.
        """
        model_id = self._embedder.model_id
        embedding = self._analysis.get_embedding(file_hash, model_id)
        if embedding is None:
            if self._repository.get_by_filehash(file_hash) is None:
                raise KeyError(file_hash)
            raise AnalysisNotReadyError("This photo has not been analyzed yet.")
        nearest = self._analysis.nearest(
            embedding.vector, k, model_id, query, exclude_hash=file_hash
        )
        return self._hits(nearest)

    def _hits(self, scored: Sequence) -> list[SemanticHit]:
        hits = []
        for item in scored:
            photo = self._repository.get_by_filehash(item.file_hash)
            if photo is not None:  # deleted between the ranking and now
                hits.append(SemanticHit(photo=photo, score=item.score))
        return hits
