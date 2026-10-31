"""Brute-force cosine search over one model's embeddings, kept on disk between runs (ticket 16).

The embeddings of a model are one matrix of unit vectors in hash order, so a search is a single
matrix-vector product (ADR-002 measured it as adequate at 100k photos). Reading that matrix from
SQLite takes about 2 s at 100k, so it is also saved under the models directory as a pair of
``.npy`` files (``<model>-<dim>.vectors.npy`` and ``<model>-<dim>.hashes.npy``) and memory-mapped
on the next start. Both headers carry the model's ``embeddings_generation`` and the library's
id (ADR-003 R6): a file whose header does not match the database is rebuilt, never trusted.
The extra header keys mean ``np.load`` refuses the files; :func:`read_index_file` reads them.

The generation is bumped by triggers in the same transaction as any write to the embeddings
(migration 0008), so reading it is the whole freshness check, in a session and across restarts.
"""

import ast
import logging
import os
import re
import sqlite3
import struct
import threading
import uuid
from collections.abc import Sequence, Set
from pathlib import Path
from typing import Any

import numpy as np
from numpy.lib import format as npy_format

from photo_meta_organizer.domain.analysis import ScoredPhoto, normalize

logger = logging.getLogger(__name__)

_FLOAT32 = np.dtype("<f4")


class BruteForceVectorIndex:
    """The :class:`VectorIndex` over ``photo_embeddings``, sharing the library's connection.

    Without ``index_dir`` the matrix is kept in memory only. A directory that cannot be written
    is logged and otherwise ignored: search still works, the next start just reads SQLite again.
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        lock: threading.RLock,
        index_dir: Path | None = None,
    ) -> None:
        self._conn = connection
        self._lock = lock
        self._dir = index_dir
        self._library_id: str | None = None
        # (model_id, dim) -> (generation, hashes, matrix)
        self._cache: dict[tuple[str, int], tuple[int, list[str], np.ndarray]] = {}

    def nearest(
        self,
        vector: Sequence[float],
        k: int,
        model_id: str,
        allowed: Set[str] | None = None,
        exclude_hash: str | None = None,
    ) -> list[ScoredPhoto]:
        if k <= 0:
            return []
        unit = np.asarray(normalize(vector), dtype=_FLOAT32)
        hashes, matrix = self._matrix(model_id, unit.shape[0])
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
        """The model's embeddings as (hashes in hash order, matrix): from memory while the
        generation holds, else from the saved files, else from SQLite (and then saved)."""
        key = (model_id, dim)
        with self._lock:
            generation = _generation(self._conn, model_id)
            cached = self._cache.get(key)
            if cached is not None and cached[0] == generation:
                return cached[1], cached[2]
            # Drop a mapped file before it may be replaced: Windows refuses to replace it.
            self._cache.pop(key, None)
            header = {"generation": generation, "library": self._library(), "model": model_id}
            loaded = self._read_files(model_id, dim, header)
            rebuilt = loaded is None
            hashes, matrix = loaded if loaded is not None else _read_rows(self._conn, model_id, dim)
            self._cache[key] = (generation, hashes, matrix)
        if rebuilt:
            self._write_files(model_id, dim, header, hashes, matrix)
        return hashes, matrix

    def _library(self) -> str | None:
        if self._library_id is None:
            row = self._conn.execute(
                "SELECT value FROM library_state WHERE key = 'library_id'"
            ).fetchone()
            self._library_id = row[0] if row is not None else None
        return self._library_id

    def _paths(self, model_id: str, dim: int) -> tuple[Path, Path] | None:
        if self._dir is None:
            return None
        stem = f"{re.sub(r'[^A-Za-z0-9._-]+', '_', model_id)}-{dim}"
        return self._dir / f"{stem}.vectors.npy", self._dir / f"{stem}.hashes.npy"

    def _read_files(
        self, model_id: str, dim: int, header: dict[str, Any]
    ) -> tuple[list[str], np.ndarray] | None:
        paths = self._paths(model_id, dim)
        if paths is None or header["library"] is None:
            return None
        vectors = read_index_file(paths[0])
        names = read_index_file(paths[1])
        if vectors is None or names is None:
            return None
        if any(vectors[0].get(k) != v or names[0].get(k) != v for k, v in header.items()):
            return None
        matrix, encoded = vectors[1], names[1]
        if (
            matrix.dtype != _FLOAT32
            or matrix.ndim != 2
            or matrix.shape[1] != dim
            or encoded.dtype.kind != "S"
            or encoded.shape != (matrix.shape[0],)
        ):
            return None
        return [h.decode("utf-8") for h in encoded.tolist()], matrix

    def _write_files(
        self,
        model_id: str,
        dim: int,
        header: dict[str, Any],
        hashes: list[str],
        matrix: np.ndarray,
    ) -> None:
        paths = self._paths(model_id, dim)
        if paths is None or header["library"] is None or not hashes:
            return
        try:
            paths[0].parent.mkdir(parents=True, exist_ok=True)
            _write_index_file(paths[1], header, np.array([h.encode("utf-8") for h in hashes]))
            _write_index_file(paths[0], header, matrix)
        except OSError as error:
            logger.warning("Could not save the vector index under %s: %s", paths[0].parent, error)


def _generation(connection: sqlite3.Connection, model_id: str) -> int:
    row = connection.execute(
        "SELECT generation FROM embedding_generations WHERE model_id = ?", (model_id,)
    ).fetchone()
    return 0 if row is None else int(row[0])


def _read_rows(
    connection: sqlite3.Connection, model_id: str, dim: int
) -> tuple[list[str], np.ndarray]:
    """The model's vectors from SQLite, in hash order. Caller holds the lock."""
    rows = connection.execute(
        "SELECT file_hash, vector FROM photo_embeddings WHERE model_id = ? AND dim = ?",
        (model_id, dim),
    ).fetchall()
    # Sorted here, not in SQL: with the model index the planner would sort the blobs.
    rows.sort(key=lambda r: r[0])
    hashes = [r[0] for r in rows]
    matrix = (
        np.frombuffer(b"".join(r[1] for r in rows), dtype=_FLOAT32).reshape(len(rows), dim)
        if rows
        else np.empty((0, dim), dtype=_FLOAT32)
    )
    return hashes, matrix


def read_index_file(path: Path) -> tuple[dict[str, Any], np.ndarray] | None:
    """An index file's header and its array, memory-mapped read-only; ``None`` if the file is
    missing or is not a version 1.0 ``.npy`` file with a usable header."""
    try:
        with open(path, "rb") as f:
            if npy_format.read_magic(f) != (1, 0):
                return None
            (length,) = struct.unpack("<H", f.read(2))
            header = ast.literal_eval(f.read(length).decode("latin1"))
            offset = f.tell()
        if not isinstance(header, dict) or header.get("fortran_order") is not False:
            return None
        shape = tuple(header["shape"])
        if 0 in shape:
            return None
        array = np.memmap(
            path, dtype=np.dtype(header["descr"]), mode="r", shape=shape, offset=offset
        )
        return header, array
    except (OSError, ValueError, SyntaxError, KeyError, TypeError, struct.error):
        return None


def _write_index_file(path: Path, header: dict[str, Any], array: np.ndarray) -> None:
    """Write ``array`` as a version 1.0 ``.npy`` file with ``header``'s keys added, atomically."""
    array = np.ascontiguousarray(array)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(temporary, "wb") as f:
            npy_format.write_array_header_1_0(
                f, {**npy_format.header_data_from_array_1_0(array), **header}
            )
            array.tofile(f)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
