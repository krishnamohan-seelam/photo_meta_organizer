"""SQLite-based implementation of CollectionRepository (PMO-08, ADR-001).

Shares the connection and lock of a sibling :class:`SqliteRepository` (pass
``repo.connection`` / ``repo.lock``). ``collection_photos.file_hash`` has
``ON DELETE CASCADE`` against ``photos``, so a deleted photo drops out of every
collection automatically; ``remove_photo_from_all`` still exists so callers
never have to special-case the backend.
"""

import sqlite3
import threading
from datetime import datetime

from photo_meta_organizer.application.interfaces.collection_repository import (
    CollectionRecord,
)


class SqliteCollectionRepository:
    """SQLite-backed repository for named photo collections."""

    def __init__(self, connection: sqlite3.Connection, lock: threading.RLock) -> None:
        self._conn = connection
        self._lock = lock

    def list_all(self) -> list[CollectionRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT name FROM collections ORDER BY name"
            ).fetchall()
            return [self._to_record(row["name"]) for row in rows]

    def get(self, name: str) -> CollectionRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT name FROM collections WHERE name = ?", (name,)
            ).fetchone()
            return self._to_record(row["name"]) if row else None

    def save(
        self, name: str, photo_hashes: list[str], description: str = ""
    ) -> CollectionRecord:
        updated_at = datetime.utcnow().isoformat()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO collections (name, description, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET description=excluded.description,
                    updated_at=excluded.updated_at
                """,
                (name, description, updated_at),
            )
            self._conn.execute(
                "DELETE FROM collection_photos WHERE collection = ?", (name,)
            )
            for file_hash in photo_hashes:
                self._conn.execute(
                    "INSERT OR IGNORE INTO collection_photos (collection, file_hash) "
                    "VALUES (?, ?)",
                    (name, file_hash),
                )
        return self._to_record(name)

    def delete(self, name: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM collections WHERE name = ?", (name,))
            return cur.rowcount > 0

    def remove_photo_from_all(self, file_hash: str) -> int:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM collection_photos WHERE file_hash = ?", (file_hash,)
            )
            return cur.rowcount

    def _to_record(self, name: str) -> CollectionRecord:
        row = self._conn.execute(
            "SELECT description, updated_at FROM collections WHERE name = ?", (name,)
        ).fetchone()
        hash_rows = self._conn.execute(
            "SELECT file_hash FROM collection_photos WHERE collection = ? ORDER BY rowid",
            (name,),
        ).fetchall()
        return CollectionRecord(
            name=name,
            description=row["description"] if row else "",
            photo_hashes=[r["file_hash"] for r in hash_rows],
            updated_at=row["updated_at"] if row else "",
        )
