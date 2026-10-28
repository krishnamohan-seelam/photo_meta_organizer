"""Search by meaning as a ranking of the filtered set (ADR-003 R9, ticket 15).

A ranked search scores the photos that pass the filters once, keeps the list under a token and
serves later pages as slices of it, so paging is cheap and stable. CLIP cosine scores are not
comparable across queries, so the cut-off is relative: the top N, or the scores within a margin
of the best, whichever is fewer.
"""

import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass

DEFAULT_TOP_N = 500
DEFAULT_MARGIN = 0.08
SNAPSHOT_TTL_SECONDS = 600
MAX_SNAPSHOTS = 32


@dataclass(frozen=True)
class RankedHit:
    file_hash: str
    score: float


def cut_off(
    hits: Sequence[RankedHit], *, top_n: int, margin: float, everything: bool = False
) -> list[RankedHit]:
    """``hits`` (best first) cut to the top ``top_n`` within ``margin`` of the best score."""
    if everything or not hits:
        return list(hits)
    floor = hits[0].score - margin
    return [h for h in hits[:top_n] if h.score >= floor]


@dataclass
class _Snapshot:
    hits: list[RankedHit]
    created: float


class RankSnapshots:
    """Ranked lists by token, each kept for ``ttl_seconds``; at most ``max_snapshots`` (LRU)."""

    def __init__(
        self,
        *,
        ttl_seconds: float = SNAPSHOT_TTL_SECONDS,
        max_snapshots: int = MAX_SNAPSHOTS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_snapshots < 1:
            raise ValueError("max_snapshots must be at least 1")
        self._ttl = ttl_seconds
        self._max = max_snapshots
        self._clock = clock
        self._lock = threading.Lock()
        self._snapshots: OrderedDict[str, _Snapshot] = OrderedDict()

    def put(self, hits: Sequence[RankedHit]) -> str:
        token = secrets.token_urlsafe(12)
        with self._lock:
            self._snapshots[token] = _Snapshot(list(hits), self._clock())
            while len(self._snapshots) > self._max:
                self._snapshots.popitem(last=False)
        return token

    def get(self, token: str) -> list[RankedHit] | None:
        """The ranked list, or ``None`` once it has expired or been dropped."""
        with self._lock:
            snapshot = self._snapshots.get(token)
            if snapshot is None:
                return None
            if self._clock() - snapshot.created > self._ttl:
                del self._snapshots[token]
                return None
            self._snapshots.move_to_end(token)
            return snapshot.hits
