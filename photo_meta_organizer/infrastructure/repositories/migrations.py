"""Versioned schema migrations for the SQLite library (ADR-003 R1).

``PRAGMA user_version`` records the last applied migration. ``SqliteRepository`` runs
:func:`migrate` before anything else, so the schema can change (columns, keys, new
tables) instead of only growing through ``CREATE TABLE IF NOT EXISTS``.
"""

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

BASELINE_SQL = """
CREATE TABLE IF NOT EXISTS photos (
    file_hash TEXT PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mime_type TEXT NOT NULL,
    mtime TEXT,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    captured_at TEXT,
    camera_make TEXT,
    camera_model TEXT,
    f_stop REAL,
    exposure_time TEXT,
    iso INTEGER,
    focal_length TEXT,
    camera_profile TEXT NOT NULL DEFAULT 'unknown',
    flash_fired INTEGER,
    focal_length_35mm TEXT,
    white_balance_mode TEXT,
    exposure_program TEXT,
    metering_mode TEXT,
    orientation INTEGER,
    gps_lat REAL,
    gps_lon REAL,
    gps_alt REAL,
    gps_datum TEXT,
    raw_tags TEXT NOT NULL DEFAULT '{}',
    rating INTEGER CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
    flagged INTEGER NOT NULL DEFAULT 0,
    added_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_photos_captured_at ON photos(captured_at);
CREATE INDEX IF NOT EXISTS idx_photos_size_bytes ON photos(size_bytes);
CREATE INDEX IF NOT EXISTS idx_photos_camera_make ON photos(camera_make);
CREATE INDEX IF NOT EXISTS idx_photos_flagged_rating ON photos(flagged, rating);

CREATE TABLE IF NOT EXISTS photo_labels (
    file_hash TEXT NOT NULL REFERENCES photos(file_hash) ON DELETE CASCADE,
    label TEXT NOT NULL,
    PRIMARY KEY (file_hash, label)
);
CREATE INDEX IF NOT EXISTS idx_photo_labels_label ON photo_labels(label);

CREATE TABLE IF NOT EXISTS collections (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

-- AI analysis (Phase 5, ADR-002). Keyed by content hash, so results go with a photo
-- (ON DELETE CASCADE) and survive re-saving unchanged content (the upsert is an UPDATE).
CREATE TABLE IF NOT EXISTS photo_embeddings (
    file_hash TEXT NOT NULL REFERENCES photos(file_hash) ON DELETE CASCADE,
    model_id TEXT NOT NULL,
    dim INTEGER NOT NULL,
    vector BLOB NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (file_hash, model_id)
);
-- Counting a model's embeddings must not read the vectors (the search cache checks it).
CREATE INDEX IF NOT EXISTS idx_photo_embeddings_model ON photo_embeddings(model_id, dim);

CREATE TABLE IF NOT EXISTS photo_ai_tags (
    file_hash TEXT NOT NULL REFERENCES photos(file_hash) ON DELETE CASCADE,
    label TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    model_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'suggested'
        CHECK (status IN ('suggested', 'accepted', 'rejected')),
    PRIMARY KEY (file_hash, label)
);
CREATE INDEX IF NOT EXISTS idx_photo_ai_tags_label ON photo_ai_tags(label, status);

CREATE TABLE IF NOT EXISTS collection_photos (
    collection TEXT NOT NULL REFERENCES collections(name) ON DELETE CASCADE,
    file_hash TEXT NOT NULL REFERENCES photos(file_hash) ON DELETE CASCADE,
    PRIMARY KEY (collection, file_hash)
);
"""


@dataclass(frozen=True)
class Migration:
    """One schema step. ``rebuilds`` marks steps that rewrite tables and so need a backup."""

    version: int
    name: str
    sql: str
    rebuilds: bool = False


# Append new migrations here with the next consecutive version. Never edit one that shipped.
MIGRATIONS: tuple[Migration, ...] = (
    # Idempotent (CREATE ... IF NOT EXISTS), so a library that predates versioning, or
    # predates the AI tables, is brought up to the baseline and then stamped as version 1.
    Migration(1, "baseline", BASELINE_SQL),
)


class SchemaTooNewError(RuntimeError):
    """The database was written by a newer build than this one understands."""


def latest_version(migrations: Sequence[Migration] = MIGRATIONS) -> int:
    return max((m.version for m in migrations), default=0)


def migrate(
    connection: sqlite3.Connection,
    db_path: str,
    migrations: Sequence[Migration] = MIGRATIONS,
) -> None:
    """Apply every migration newer than the database's ``user_version``.

    Each migration runs in its own transaction together with the version bump, so a
    failure leaves the previous version in place. Before a ``rebuilds`` migration on an
    existing file database, the file is copied to ``<db>.pre-NNNN`` with the SQLite
    backup API (safe under WAL). A database newer than the code is refused untouched.
    """
    current = int(connection.execute("PRAGMA user_version").fetchone()[0])
    latest = latest_version(migrations)
    if current > latest:
        raise SchemaTooNewError(
            f"This library uses schema version {current}, but this build only understands "
            f"version {latest}. Update Photo Meta Organizer to open it."
        )
    for migration in sorted(migrations, key=lambda m: m.version):
        if migration.version <= current:
            continue
        if migration.rebuilds and current > 0:
            _backup(connection, db_path, migration.version)
        _apply(connection, migration)
        current = migration.version


def _apply(connection: sqlite3.Connection, migration: Migration) -> None:
    script = f"BEGIN;\n{migration.sql}\nPRAGMA user_version = {migration.version};\nCOMMIT;"
    try:
        connection.executescript(script)
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise


def _backup(connection: sqlite3.Connection, db_path: str, version: int) -> None:
    if db_path == ":memory:":
        return
    target = Path(f"{db_path}.pre-{version:04d}")
    if target.exists():
        target.unlink()
    destination = sqlite3.connect(str(target))
    try:
        connection.backup(destination)
    finally:
        destination.close()
