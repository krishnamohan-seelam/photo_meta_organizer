"""Port for similarity search over stored embeddings (ADR-003 R6, ticket 16).

``AnalysisRepository.nearest`` turns the search filters into a set of candidate hashes and asks
the index for the closest vectors among them. Today's index is brute force; an approximate
(ANN) index can replace it behind this port without touching the use cases.
"""

from collections.abc import Sequence, Set
from typing import Protocol, runtime_checkable

from photo_meta_organizer.domain.analysis import ScoredPhoto


@runtime_checkable
class VectorIndex(Protocol):
    def nearest(
        self,
        vector: Sequence[float],
        k: int,
        model_id: str,
        allowed: Set[str] | None = None,
        exclude_hash: str | None = None,
    ) -> list[ScoredPhoto]:
        """The ``k`` stored embeddings of ``model_id`` most similar to ``vector``, best first.

        Scores are cosine similarities; ties go to the lower hash. Only hashes in ``allowed``
        compete when it is given, and ``exclude_hash`` never does. The index follows the
        stored embeddings by itself: a write is seen by the next search.
        """
        ...
