"""Brute-force cosine search over one model's embeddings, kept on disk between runs (ticket 16).

The embeddings of a model are one matrix of unit vectors in hash order, so a search is a single
matrix-vector product (ADR-002 measured it as adequate at 100k photos). Reading that matrix from
SQLite takes 2-4 s at 100k, so it is also saved under the models directory as a pair of ``.npy``
files (``<model>-<dim>.vectors.npy`` and ``<model>-<dim>.hashes.npy``) and memory-mapped on the
next start. Both headers carry an :class:`_IndexKey`: the model's ``embeddings_generation``, the
library's id, and the model's row count and newest ``created_at`` (a copied or restored library
keeps its id and can reach the same generation with other vectors). A file whose header does not
match the database is rebuilt, never trusted (ADR-003 R6). The extra header keys mean ``np.load``
refuses the files; :func:`read_index_file` reads them.

The generation is bumped by triggers in the same transaction as any write to the embeddings
(migration 0008), so in a session reading it is the whole freshness check. A rebuild is saved at
most once per ``save_interval``: while an analysis writes, every search after a batch rebuilds,
and rewriting 200 MB each time would be waste.
"""

import ast
import dataclasses
import logging
import os
import re
import sqlite3
import struct
import threading
import time
import uuid
from collections.abc import Callable, Sequence, Set
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np
from numpy.lib import format as npy_format

from photo_meta_organizer.domain.analysis import ScoredPhoto, normalize

logger = logging.getLogger(__name__)

_FLOAT32 = np.dtype("<f4")

# A rebuild is saved when nothing was saved for this many seconds (or not yet this session).
SAVE_INTERVAL_SECONDS = 300.0


@dataclass(frozen=True)
class _IndexKey:
    """What a saved index must match to be trusted; its fields are the files' extra header keys."""

    generation: int
    library: str
    model: str
    rows: int
    newest: str | None


@dataclass(frozen=True)
class _Snapshot:
    """One model's embeddings ready to rank: hashes in hash order and their unit vectors."""

    generation: int
    hashes: list[str]
    matrix: np.ndarray


class _IndexFiles(NamedTuple):
    vectors: Path
    hashes: Path


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
        save_interval: float = SAVE_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._conn = connection
        self._lock = lock
        self._dir = index_dir
        self._save_interval = save_interval
        self._clock = clock
        self._library_id: str | None = None
        self._cache: dict[tuple[str, int], _Snapshot] = {}
        self._saved_at: dict[tuple[str, int], float] = {}

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
        snapshot = self._snapshot(model_id, unit.shape[0])
        hashes, matrix = snapshot.hashes, snapshot.matrix
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

    def _snapshot(self, model_id: str, dim: int) -> _Snapshot:
        """From memory while the generation holds, else from the saved files, else SQLite."""
        slot = (model_id, dim)
        with self._lock:
            generation = _generation(self._conn, model_id)
            cached = self._cache.get(slot)
            if cached is not None and cached.generation == generation:
                return cached
            # Drop a mapped file before it may be replaced: Windows refuses to replace it.
            self._cache.pop(slot, None)
            key = self._key(model_id, dim, generation)
            snapshot = self._read_files(key, dim) if key is not None else None
            rebuilt = snapshot is None
            if snapshot is None:
                snapshot = _Snapshot(generation, *_read_rows(self._conn, model_id, dim))
            self._cache[slot] = snapshot
        if rebuilt and key is not None and self._due_for_save(slot):
            self._write_files(key, snapshot)
        return snapshot

    def _key(self, model_id: str, dim: int, generation: int) -> _IndexKey | None:
        """The key the saved files must carry now, or ``None`` when nothing is kept on disk."""
        library = self._library_id_value()
        if self._dir is None or library is None:
            return None
        rows, newest = self._conn.execute(
            "SELECT COUNT(*), MAX(created_at) FROM photo_embeddings "
            "WHERE model_id = ? AND dim = ?",
            (model_id, dim),
        ).fetchone()
        return _IndexKey(generation, library, model_id, int(rows), newest)

    def _library_id_value(self) -> str | None:
        """The library's id from ``library_state``, read once."""
        if self._library_id is None:
            row = self._conn.execute(
                "SELECT value FROM library_state WHERE key = 'library_id'"
            ).fetchone()
            self._library_id = row[0] if row is not None else None
        return self._library_id

    def _due_for_save(self, slot: tuple[str, int]) -> bool:
        last = self._saved_at.get(slot)
        return last is None or self._clock() - last >= self._save_interval

    def _files(self, model_id: str, dim: int) -> _IndexFiles:
        assert self._dir is not None
        stem = f"{re.sub(r'[^A-Za-z0-9._-]+', '_', model_id)}-{dim}"
        return _IndexFiles(self._dir / f"{stem}.vectors.npy", self._dir / f"{stem}.hashes.npy")

    def _read_files(self, key: _IndexKey, dim: int) -> _Snapshot | None:
        files = self._files(key.model, dim)
        vectors_file = read_index_file(files.vectors)
        hashes_file = read_index_file(files.hashes)
        if vectors_file is None or hashes_file is None:
            return None
        if any(
            vectors_file[0].get(name) != value or hashes_file[0].get(name) != value
            for name, value in dataclasses.asdict(key).items()
        ):
            return None
        matrix, encoded_hashes = vectors_file[1], hashes_file[1]
        if (
            matrix.dtype != _FLOAT32
            or matrix.shape != (key.rows, dim)
            or encoded_hashes.dtype.kind != "S"
            or encoded_hashes.shape != (key.rows,)
        ):
            return None
        hashes = [h.decode("utf-8") for h in encoded_hashes.tolist()]
        return _Snapshot(key.generation, hashes, matrix)

    def _write_files(self, key: _IndexKey, snapshot: _Snapshot) -> None:
        if not snapshot.hashes:
            return
        dim = snapshot.matrix.shape[1]
        self._saved_at[(key.model, dim)] = self._clock()
        files = self._files(key.model, dim)
        header = dataclasses.asdict(key)
        try:
            files.vectors.parent.mkdir(parents=True, exist_ok=True)
            encoded_hashes = np.array([h.encode("utf-8") for h in snapshot.hashes])
            _write_index_file(files.hashes, header, encoded_hashes)
            _write_index_file(files.vectors, header, snapshot.matrix)
        except OSError as error:
            logger.warning("Could not save the vector index under %s: %s", self._dir, error)


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
