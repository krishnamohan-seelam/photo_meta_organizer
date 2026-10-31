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


# ADR-003 R3: one row per Asset (content), its Files (paths) and its Curation. Lossless for a
# version-1 library, which has exactly one path per hash. The tables that referenced
# ``photos`` are rebuilt to reference ``assets`` (same shape, same rowids, so collection
# order is kept). Rows that point at no photo (only possible if written with foreign keys
# off) are dropped rather than left to fail the reference check. ``asset_view`` is what
# search filters and counts; ``photo_view`` adds each Asset's primary file, for the rows
# actually returned.
SPLIT_ASSETS_SQL = """
CREATE TABLE assets (
    file_hash TEXT PRIMARY KEY,
    size_bytes INTEGER NOT NULL, -- of the content, so the same for every File holding it
    mime_type TEXT NOT NULL,
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
    extracted_at TEXT NOT NULL
);
INSERT INTO assets
SELECT file_hash, size_bytes, mime_type, width, height, captured_at, camera_make, camera_model,
    f_stop, exposure_time, iso, focal_length, camera_profile, flash_fired, focal_length_35mm,
    white_balance_mode, exposure_program, metering_mode, orientation, gps_lat, gps_lon,
    gps_alt, gps_datum, raw_tags, added_at
FROM photos;
CREATE INDEX idx_assets_captured_at ON assets(captured_at);
CREATE INDEX idx_assets_camera_make ON assets(camera_make);
CREATE INDEX idx_assets_size_bytes ON assets(size_bytes);

CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    asset_hash TEXT NOT NULL REFERENCES assets(file_hash) ON DELETE CASCADE,
    path TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mtime TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
INSERT INTO files (asset_hash, path, name, size_bytes, mtime, first_seen, last_seen)
SELECT file_hash, path, name, size_bytes, mtime, added_at, added_at FROM photos ORDER BY rowid;
-- Covers the primary-file lookup: latest last_seen, lowest id on a tie.
CREATE INDEX idx_files_asset ON files(asset_hash, last_seen DESC, id);

CREATE TABLE curation (
    asset_hash TEXT PRIMARY KEY REFERENCES assets(file_hash) ON DELETE CASCADE,
    rating INTEGER CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
    flagged INTEGER NOT NULL DEFAULT 0,
    added_at TEXT NOT NULL
);
INSERT INTO curation SELECT file_hash, rating, flagged, added_at FROM photos;
CREATE INDEX idx_curation_flagged_rating ON curation(flagged, rating);

CREATE TABLE asset_labels (
    asset_hash TEXT NOT NULL REFERENCES assets(file_hash) ON DELETE CASCADE,
    label TEXT NOT NULL,
    PRIMARY KEY (asset_hash, label)
);
INSERT INTO asset_labels (asset_hash, label)
SELECT file_hash, label FROM photo_labels
WHERE file_hash IN (SELECT file_hash FROM photos) ORDER BY rowid;
CREATE INDEX idx_asset_labels_label ON asset_labels(label);

CREATE TABLE photo_embeddings_new (
    file_hash TEXT NOT NULL REFERENCES assets(file_hash) ON DELETE CASCADE,
    model_id TEXT NOT NULL,
    dim INTEGER NOT NULL,
    vector BLOB NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (file_hash, model_id)
);
INSERT INTO photo_embeddings_new (rowid, file_hash, model_id, dim, vector, created_at)
SELECT rowid, file_hash, model_id, dim, vector, created_at FROM photo_embeddings
WHERE file_hash IN (SELECT file_hash FROM photos);

CREATE TABLE photo_ai_tags_new (
    file_hash TEXT NOT NULL REFERENCES assets(file_hash) ON DELETE CASCADE,
    label TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    model_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'suggested'
        CHECK (status IN ('suggested', 'accepted', 'rejected')),
    PRIMARY KEY (file_hash, label)
);
INSERT INTO photo_ai_tags_new (rowid, file_hash, label, confidence, model_id, status)
SELECT rowid, file_hash, label, confidence, model_id, status FROM photo_ai_tags
WHERE file_hash IN (SELECT file_hash FROM photos);

CREATE TABLE collection_photos_new (
    collection TEXT NOT NULL REFERENCES collections(name) ON DELETE CASCADE,
    file_hash TEXT NOT NULL REFERENCES assets(file_hash) ON DELETE CASCADE,
    PRIMARY KEY (collection, file_hash)
);
INSERT INTO collection_photos_new (rowid, collection, file_hash)
SELECT rowid, collection, file_hash FROM collection_photos
WHERE file_hash IN (SELECT file_hash FROM photos)
    AND collection IN (SELECT name FROM collections);

DROP TABLE photo_embeddings;
DROP TABLE photo_ai_tags;
DROP TABLE collection_photos;
DROP TABLE photo_labels;
DROP TABLE photos;
ALTER TABLE photo_embeddings_new RENAME TO photo_embeddings;
ALTER TABLE photo_ai_tags_new RENAME TO photo_ai_tags;
ALTER TABLE collection_photos_new RENAME TO collection_photos;
CREATE INDEX idx_photo_embeddings_model ON photo_embeddings(model_id, dim);
CREATE INDEX idx_photo_ai_tags_label ON photo_ai_tags(label, status);

-- What search filters, sorts and counts: every Asset with its curation (each has a row).
CREATE VIEW asset_view AS
SELECT a.*, c.rating, c.flagged, c.added_at
FROM assets a JOIN curation c ON c.asset_hash = a.file_hash;

-- One row per Asset with its primary file: the present File seen last, lowest id on a tie.
CREATE VIEW photo_view AS
SELECT v.*, f.path, f.name, f.mtime
FROM asset_view v
JOIN files f ON f.id = (
    SELECT id FROM files WHERE asset_hash = v.file_hash ORDER BY last_seen DESC, id LIMIT 1
);
"""


# Ticket 04: a File a scan did not find is flagged, not forgotten. The primary file is now
# the present File seen last, so a photo shows as missing only when every File is.
MISSING_FILES_SQL = """
ALTER TABLE files ADD COLUMN missing_since TEXT;
DROP VIEW photo_view;
CREATE VIEW photo_view AS
SELECT v.*, f.path, f.name, f.mtime, f.missing_since
FROM asset_view v
JOIN files f ON f.id = (
    SELECT id FROM files WHERE asset_hash = v.file_hash
    ORDER BY missing_since IS NOT NULL, last_seen DESC, id LIMIT 1
);
"""

# Ticket 07 (ADR-003 R5a): background jobs outlive the process. Times are naive local
# ISO strings like the rest of the schema; counts, errors and params are JSON.
JOBS_SQL = """
CREATE TABLE jobs (
    id               TEXT PRIMARY KEY,
    kind             TEXT NOT NULL,
    folder           TEXT NOT NULL,
    status           TEXT NOT NULL,
    total            INTEGER,
    processed        INTEGER NOT NULL DEFAULT 0,
    failed           INTEGER NOT NULL DEFAULT 0,
    counts           TEXT NOT NULL DEFAULT '{}',
    errors           TEXT NOT NULL DEFAULT '[]',
    message          TEXT NOT NULL DEFAULT '',
    params           TEXT NOT NULL DEFAULT '{}',
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL,
    started_at       TEXT,
    finished_at      TEXT
);
CREATE INDEX idx_jobs_created_at ON jobs(created_at);
"""


# Ticket 09 (ADR-003 R11): the library remembers the folders it scans. ``library_state`` is a
# small key/value table for one-off answers such as "the user skipped the suggested roots".
ROOTS_SQL = """
CREATE TABLE roots (
    id       INTEGER PRIMARY KEY,
    path     TEXT NOT NULL UNIQUE,
    added_at TEXT NOT NULL
);
CREATE TABLE library_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


# Ticket 03 (ADR-003 R11): a copy can be hidden from the duplicates view. The File stays recorded
# (so a scan does not add it back) and keeps its fingerprint; it just stops counting as a copy.
HIDDEN_FILES_SQL = """
ALTER TABLE files ADD COLUMN hidden_at TEXT;
"""


# Ticket 12 (ADR-003 R11): removing photos from the library is undoable for a short while.
# ``assets.removed_at`` hides an Asset (every view and read goes through ``live_assets``,
# ``asset_view`` or ``photo_view``, which leave removed ones out); it is purged for good after
# about 30 s or on the next start. Purging remembers each file's path, size and mtime in
# ``ignored_files`` so a scan does not bring the photo straight back; a file whose size or
# mtime differs is new content and is scanned. Files on disk are never touched.
REMOVAL_SQL = """
ALTER TABLE assets ADD COLUMN removed_at TEXT;

CREATE TABLE ignored_files (
    path       TEXT PRIMARY KEY,
    file_hash  TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mtime      TEXT,
    removed_at TEXT NOT NULL
);

DROP VIEW photo_view;
DROP VIEW asset_view;

CREATE VIEW live_assets AS SELECT * FROM assets WHERE removed_at IS NULL;

CREATE VIEW asset_view AS
SELECT a.*, c.rating, c.flagged, c.added_at
FROM live_assets a JOIN curation c ON c.asset_hash = a.file_hash;

CREATE VIEW photo_view AS
SELECT v.*, f.path, f.name, f.mtime, f.missing_since
FROM asset_view v
JOIN files f ON f.id = (
    SELECT id FROM files WHERE asset_hash = v.file_hash
    ORDER BY missing_since IS NOT NULL, last_seen DESC, id LIMIT 1
);
"""


# Ticket 16 (ADR-003 R6): the vector index is saved next to the model as a memory-mapped .npy
# pair, so it must be able to tell whether a saved index still matches the library. Each model's
# ``generation`` is bumped by triggers, so every write to its embeddings (cascade deletes from
# ``assets`` included) bumps it in the same transaction. ``library_id`` tells two libraries that
# share a models directory apart.
EMBEDDINGS_GENERATION_SQL = """
CREATE TABLE embedding_generations (
    model_id   TEXT PRIMARY KEY,
    generation INTEGER NOT NULL
);
INSERT INTO embedding_generations (model_id, generation)
SELECT DISTINCT model_id, 1 FROM photo_embeddings;

INSERT OR IGNORE INTO library_state (key, value) VALUES ('library_id', lower(hex(randomblob(16))));

CREATE TRIGGER photo_embeddings_inserted AFTER INSERT ON photo_embeddings BEGIN
    INSERT INTO embedding_generations (model_id, generation) VALUES (NEW.model_id, 1)
    ON CONFLICT (model_id) DO UPDATE SET generation = generation + 1;
END;
CREATE TRIGGER photo_embeddings_updated AFTER UPDATE ON photo_embeddings BEGIN
    INSERT INTO embedding_generations (model_id, generation) VALUES (NEW.model_id, 1)
    ON CONFLICT (model_id) DO UPDATE SET generation = generation + 1;
    INSERT INTO embedding_generations (model_id, generation) VALUES (OLD.model_id, 1)
    ON CONFLICT (model_id) DO UPDATE SET generation = generation + 1;
END;
CREATE TRIGGER photo_embeddings_deleted AFTER DELETE ON photo_embeddings BEGIN
    INSERT INTO embedding_generations (model_id, generation) VALUES (OLD.model_id, 1)
    ON CONFLICT (model_id) DO UPDATE SET generation = generation + 1;
END;
"""


# Ticket 16 review: a copied or restored library keeps its id and can reach a saved index's
# generation with other content, so the saved index is also keyed by the model's row count and
# newest ``created_at``. This index answers both without reading a single vector.
EMBEDDINGS_STAMP_INDEX_SQL = """
DROP INDEX idx_photo_embeddings_model;
CREATE INDEX idx_photo_embeddings_model ON photo_embeddings(model_id, dim, created_at);
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
    Migration(2, "split_assets", SPLIT_ASSETS_SQL, rebuilds=True),
    Migration(3, "missing_files", MISSING_FILES_SQL),
    Migration(4, "jobs", JOBS_SQL),
    Migration(5, "roots", ROOTS_SQL),
    Migration(6, "hidden_files", HIDDEN_FILES_SQL),
    Migration(7, "removal", REMOVAL_SQL),
    Migration(8, "embeddings_generation", EMBEDDINGS_GENERATION_SQL),
    Migration(9, "embeddings_stamp_index", EMBEDDINGS_STAMP_INDEX_SQL),
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
    # A fresh database has nothing worth backing up; an unversioned one with tables does.
    existing = current > 0 or (
        connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' LIMIT 1").fetchone()
        is not None
    )
    for migration in sorted(migrations, key=lambda m: m.version):
        if migration.version <= current:
            continue
        if migration.rebuilds and existing:
            _backup(connection, db_path, migration.version)
        _apply(connection, migration)
        current = migration.version


def _apply(connection: sqlite3.Connection, migration: Migration) -> None:
    # A rebuild drops and recreates referenced tables, which with foreign keys on would
    # cascade-delete the children. SQLite's procedure: keys off outside the transaction,
    # rebuild, check every reference, commit, keys back on.
    foreign_keys = int(connection.execute("PRAGMA foreign_keys").fetchone()[0])
    if migration.rebuilds:
        connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.executescript(f"BEGIN;\n{migration.sql}")
        if migration.rebuilds:
            broken = connection.execute("PRAGMA foreign_key_check").fetchall()
            if broken:
                raise sqlite3.IntegrityError(
                    f"migration {migration.version:04d} left {len(broken)} broken references"
                )
        connection.execute(f"PRAGMA user_version = {migration.version}")
        connection.commit()
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.execute(f"PRAGMA foreign_keys = {'ON' if foreign_keys else 'OFF'}")


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
