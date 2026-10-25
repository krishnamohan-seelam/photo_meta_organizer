"""SQLite implementation of ``StateStore`` on the ``library_state`` table (migration 0005).

Shares the connection and lock of a sibling :class:`SqliteRepository`.
"""

import sqlite3
import threading


class SqliteStateStore:
    def __init__(self, connection: sqlite3.Connection, lock: threading.RLock) -> None:
        self._conn = connection
        self._lock = lock

    def get(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM library_state WHERE key = ?", (key,)
            ).fetchone()
        return None if row is None else str(row[0])

    def set(self, key: str, value: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO library_state (key, value) VALUES (?, ?)", (key, value)
            )
