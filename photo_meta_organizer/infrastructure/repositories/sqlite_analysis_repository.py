"""SQLite implementation of AnalysisRepository (Phase 5, ADR-002).

Shares the connection and lock of a sibling :class:`SqliteRepository` (pass ``repo.connection``
and ``repo.lock``), like the collection repository does; the tables are created by that
repository's schema. Both tables reference ``photos(file_hash)`` with ``ON DELETE CASCADE``, so
results leave with their photo, and ``replace()`` of a modified file (which deletes the old
hash) discards the stale ones.

Vectors are stored as little-endian float32 blobs of unit length. Similarity search is brute
force: the candidate vectors (restricted to the search filters in SQL) are loaded into one numpy
matrix and ranked with a single matrix-vector product, which stays fast into the low hundreds of
thousands of photos (see ADR-002 for the measured limits and the next step if that is outgrown).
"""

import sqlite3
import threading
from collections.abc import Sequence

import numpy as np

from photo_meta_organizer.application.interfaces.analysis_repository import PendingPhoto
from photo_meta_organizer.application.interfaces.search_types import SearchQuery
from photo_meta_organizer.domain.analysis import (
    AiTag,
    AiTagStatus,
    Embedding,
    ScoredPhoto,
    normalize,
)
from photo_meta_organizer.domain.datetimes import utc_now_naive
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import search_where

_FLOAT32 = np.dtype("<f4")


def _to_blob(vector: Sequence[float]) -> bytes:
    return np.asarray(normalize(vector), dtype=_FLOAT32).tobytes()


class SqliteAnalysisRepository:
    """SQLite-backed storage for embeddings and suggested tags."""

    def __init__(self, connection: sqlite3.Connection, lock: threading.RLock) -> None:
        self._conn = connection
        self._lock = lock

    # =========================================================================
    # Embeddings
    # =========================================================================

    def save_embeddings(self, items: Sequence[Embedding]) -> int:
        saved = 0
        now = utc_now_naive().isoformat()
        with self._lock, self._conn:
            for item in items:
                # WHERE EXISTS: a file removed while a job analysed it is skipped, not a
                # foreign-key failure that would abort the whole batch.
                cur = self._conn.execute(
                    """
                    INSERT INTO photo_embeddings (file_hash, model_id, dim, vector, created_at)
                    SELECT ?, ?, ?, ?, ?
                    WHERE EXISTS (SELECT 1 FROM photos WHERE file_hash = ?)
                    ON CONFLICT(file_hash, model_id) DO UPDATE SET
                        dim = excluded.dim, vector = excluded.vector,
                        created_at = excluded.created_at
                    """,
                    (
                        item.file_hash,
                        item.model_id,
                        item.dimension,
                        _to_blob(item.vector),
                        now,
                        item.file_hash,
                    ),
                )
                saved += max(cur.rowcount, 0)
        return saved

    def get_embedding(self, file_hash: str, model_id: str) -> Embedding | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT vector FROM photo_embeddings WHERE file_hash = ? AND model_id = ?",
                (file_hash, model_id),
            ).fetchone()
        if row is None:
            return None
        vector = np.frombuffer(row["vector"], dtype=_FLOAT32)
        return Embedding(
            file_hash=file_hash, model_id=model_id, vector=tuple(float(x) for x in vector)
        )

    def pending_photos(self, model_id: str, limit: int | None = None) -> list[PendingPhoto]:
        sql = (
            "SELECT p.file_hash, p.path FROM photos p WHERE NOT EXISTS ("
            "SELECT 1 FROM photo_embeddings e WHERE e.file_hash = p.file_hash AND e.model_id = ?"
            ") ORDER BY p.path, p.file_hash"
        )
        params: list[object] = [model_id]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(max(0, limit))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [PendingPhoto(file_hash=r["file_hash"], path=r["path"]) for r in rows]

    def count_embeddings(self, model_id: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM photo_embeddings WHERE model_id = ?", (model_id,)
            ).fetchone()
        return int(row[0])

    def clear_embeddings(self, model_id: str | None = None) -> int:
        with self._lock, self._conn:
            if model_id is None:
                return self._conn.execute("DELETE FROM photo_embeddings").rowcount
            return self._conn.execute(
                "DELETE FROM photo_embeddings WHERE model_id = ?", (model_id,)
            ).rowcount

    def nearest(
        self,
        vector: Sequence[float],
        k: int,
        model_id: str,
        query: SearchQuery | None = None,
        exclude_hash: str | None = None,
    ) -> list[ScoredPhoto]:
        if k <= 0:
            return []
        unit = np.asarray(normalize(vector), dtype=_FLOAT32)
        dim = unit.shape[0]

        sql = "SELECT file_hash, vector FROM photo_embeddings WHERE model_id = ? AND dim = ?"
        params: list[object] = [model_id, dim]
        if exclude_hash is not None:
            sql += " AND file_hash != ?"
            params.append(exclude_hash)
        where_sql, where_params = search_where(query) if query is not None else ("", [])
        if where_sql:
            # Unqualified columns inside the subquery resolve to ``photos``.
            sql += f" AND file_hash IN (SELECT file_hash FROM photos {where_sql})"
            params.extend(where_params)
        # Hash order makes the stable sort below break ties by hash.
        sql += " ORDER BY file_hash"

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        if not rows:
            return []

        matrix = np.frombuffer(b"".join(r["vector"] for r in rows), dtype=_FLOAT32).reshape(
            len(rows), dim
        )
        scores = matrix @ unit
        best = np.argsort(-scores, kind="stable")[:k]
        return [ScoredPhoto(file_hash=rows[i]["file_hash"], score=float(scores[i])) for i in best]

    # =========================================================================
    # Suggested tags
    # =========================================================================

    def save_ai_tags(self, file_hash: str, tags: Sequence[AiTag]) -> None:
        with self._lock, self._conn:
            if (
                self._conn.execute(
                    "SELECT 1 FROM photos WHERE file_hash = ?", (file_hash,)
                ).fetchone()
                is None
            ):
                return
            self._conn.execute(
                "DELETE FROM photo_ai_tags WHERE file_hash = ? AND status = ?",
                (file_hash, AiTagStatus.SUGGESTED.value),
            )
            # Most confident first, so a label given twice keeps its best score. A label
            # the user already accepted or rejected still has its row, so it is skipped.
            for tag in sorted(tags, key=lambda t: -t.confidence):
                self._conn.execute(
                    "INSERT INTO photo_ai_tags (file_hash, label, confidence, model_id, status) "
                    "VALUES (?, ?, ?, ?, ?) ON CONFLICT(file_hash, label) DO NOTHING",
                    (file_hash, tag.label, tag.confidence, tag.model_id, tag.status.value),
                )

    def list_ai_tags(self, file_hash: str) -> list[AiTag]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT label, confidence, model_id, status FROM photo_ai_tags "
                "WHERE file_hash = ? ORDER BY confidence DESC, label",
                (file_hash,),
            ).fetchall()
        return [
            AiTag(
                label=r["label"],
                confidence=r["confidence"],
                model_id=r["model_id"],
                status=AiTagStatus(r["status"]),
            )
            for r in rows
        ]

    def set_ai_tag_status(self, file_hash: str, label: str, status: AiTagStatus) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE photo_ai_tags SET status = ? WHERE file_hash = ? AND label = ?",
                (status.value, file_hash, label),
            )
            return cur.rowcount > 0

    def ai_tag_counts(self, status: AiTagStatus = AiTagStatus.SUGGESTED) -> list[tuple[str, int]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT label, COUNT(*) AS n FROM photo_ai_tags WHERE status = ? "
                "GROUP BY label ORDER BY n DESC, label",
                (status.value,),
            ).fetchall()
        return [(r["label"], r["n"]) for r in rows]
