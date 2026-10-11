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
        # (model_id, dim) -> (signature, hashes, matrix): the embeddings of one model as one
        # matrix, so a search is a matrix-vector product, not a table read.
        self._version = 0
        self._matrices: dict[tuple[str, int], tuple[tuple[object, ...], list[str], np.ndarray]] = {}

    # =========================================================================
    # Embeddings
    # =========================================================================

    def save_embeddings(self, items: Sequence[Embedding]) -> int:
        self._version += 1
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

    def embedded_hashes(self, model_id: str) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT file_hash FROM photo_embeddings WHERE model_id = ? ORDER BY file_hash",
                (model_id,),
            ).fetchall()
        return [r["file_hash"] for r in rows]

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
        self._version += 1
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

        with self._lock:
            hashes, matrix = self._matrix(model_id, dim)
            allowed: set[str] | None = None
            where_sql, where_params = search_where(query) if query is not None else ("", [])
            if where_sql:
                allowed = {
                    r[0]
                    for r in self._conn.execute(
                        f"SELECT file_hash FROM photos {where_sql}", where_params
                    )
                }
        if not hashes:
            return []
        if allowed is None and exclude_hash is None:
            rows = np.arange(len(hashes))
        else:
            rows = np.fromiter(
                (
                    i
                    for i, h in enumerate(hashes)
                    if h != exclude_hash and (allowed is None or h in allowed)
                ),
                dtype=np.int64,
            )
        if rows.size == 0:
            return []
        scores = matrix[rows] @ unit if rows.size < len(hashes) else matrix @ unit
        # ``rows`` is in hash order, so the stable sort breaks ties by hash.
        best = np.argsort(-scores, kind="stable")[:k]
        return [ScoredPhoto(file_hash=hashes[rows[i]], score=float(scores[i])) for i in best]

    def _matrix(self, model_id: str, dim: int) -> tuple[list[str], np.ndarray]:
        """The model's embeddings as (hashes in hash order, matrix), rebuilt only on change.

        The signature is cheap: a counter bumped by this repository's own writes, SQLite's
        ``data_version`` (writes from another connection) and the row count (a cascade delete
        from the photos table). Caller holds the lock.
        """
        key = (model_id, dim)
        count = self._conn.execute(
            "SELECT COUNT(*) FROM photo_embeddings WHERE model_id = ? AND dim = ?",
            (model_id, dim),
        ).fetchone()[0]
        data_version = self._conn.execute("PRAGMA data_version").fetchone()[0]
        signature = (self._version, data_version, count)
        cached = self._matrices.get(key)
        if cached is not None and cached[0] == signature:
            return cached[1], cached[2]
        rows = self._conn.execute(
            "SELECT file_hash, vector FROM photo_embeddings WHERE model_id = ? AND dim = ?",
            (model_id, dim),
        ).fetchall()
        # Sorted here, not in SQL: with the model index the planner would sort the blobs.
        rows.sort(key=lambda r: r["file_hash"])
        hashes = [r["file_hash"] for r in rows]
        matrix = (
            np.frombuffer(b"".join(r["vector"] for r in rows), dtype=_FLOAT32).reshape(
                len(rows), dim
            )
            if rows
            else np.empty((0, dim), dtype=_FLOAT32)
        )
        self._matrices[key] = (signature, hashes, matrix)
        return hashes, matrix

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
