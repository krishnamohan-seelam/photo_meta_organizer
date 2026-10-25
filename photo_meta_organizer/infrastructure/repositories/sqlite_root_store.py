"""SQLite implementation of ``RootStore`` (ADR-003 R11, ticket 09).

Shares the connection and lock of a sibling :class:`SqliteRepository` (pass
``repo.connection`` and ``repo.lock``); the ``roots`` and ``library_state`` tables come from
that repository's migrations (0005).
"""

import os
import sqlite3
import threading
from collections import Counter
from datetime import datetime

from photo_meta_organizer.application.roots import Root

_SUGGESTIONS_DISMISSED = "root_suggestions_dismissed"


class SqliteRootStore:
    """Roots in the library's ``roots`` table."""

    def __init__(self, connection: sqlite3.Connection, lock: threading.RLock) -> None:
        self._conn = connection
        self._lock = lock

    def list_roots(self) -> list[Root]:
        with self._lock:
            rows = self._conn.execute("SELECT path, added_at FROM roots ORDER BY id").fetchall()
        return [Root(path, datetime.fromisoformat(added)) for path, added in rows]

    def add_root(self, path: str) -> Root:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO roots (path, added_at) VALUES (?, ?)",
                (path, datetime.now().isoformat()),
            )
            path_, added = self._conn.execute(
                "SELECT path, added_at FROM roots WHERE path = ?", (path,)
            ).fetchone()
        return Root(path_, datetime.fromisoformat(added))

    def remove_root(self, path: str) -> bool:
        with self._lock, self._conn:
            return self._conn.execute("DELETE FROM roots WHERE path = ?", (path,)).rowcount > 0

    def observed_folders(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT path FROM files WHERE missing_since IS NULL"
            ).fetchall()
        return dict(Counter(os.path.dirname(path) for (path,) in rows))

    def suggestions_dismissed(self) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM library_state WHERE key = ?", (_SUGGESTIONS_DISMISSED,)
            ).fetchone()
        return row is not None and row[0] == "1"

    def dismiss_suggestions(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO library_state (key, value) VALUES (?, '1')",
                (_SUGGESTIONS_DISMISSED,),
            )
