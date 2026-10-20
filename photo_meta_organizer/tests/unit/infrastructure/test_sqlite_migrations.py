"""ADR-003 R1: versioned schema migrations for the SQLite library."""

import os
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from photo_meta_organizer.domain.models import ImageMetadata
from photo_meta_organizer.infrastructure.repositories.migrations import (
    BASELINE_SQL,
    MIGRATIONS,
    Migration,
    SchemaTooNewError,
    latest_version,
    migrate,
)
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import SqliteRepository


def _connect(path: Path | str) -> sqlite3.Connection:
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    return connection


def _version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def _tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row["name"] for row in rows}


def test_fresh_database_is_stamped_with_the_latest_version(tmp_path: Path) -> None:
    repo = SqliteRepository(str(tmp_path / "photos.db"))
    try:
        assert _version(repo.connection) == latest_version(MIGRATIONS)
        assert {"photos", "photo_labels", "photo_embeddings", "collections"} <= _tables(
            repo.connection
        )
    finally:
        repo.close()


def test_baseline_is_migration_one() -> None:
    assert MIGRATIONS[0].version == 1
    assert MIGRATIONS[0].name == "baseline"
    assert MIGRATIONS[0].sql == BASELINE_SQL


def test_existing_unversioned_database_is_stamped_and_keeps_its_data(
    tmp_path: Path, sample_image_metadata: ImageMetadata
) -> None:
    path = tmp_path / "photos.db"
    first = SqliteRepository(str(path))
    first.save(sample_image_metadata)
    first.connection.execute("PRAGMA user_version = 0")  # a library from before migrations
    first.close()

    reopened = SqliteRepository(str(path))
    try:
        assert _version(reopened.connection) == 1
        stored = reopened.get_by_filehash(sample_image_metadata.file_hash)
        assert stored is not None
        assert stored.labels == sample_image_metadata.labels
    finally:
        reopened.close()


def test_unversioned_database_from_before_ai_analysis_gains_the_analysis_tables(
    tmp_path: Path,
) -> None:
    path = tmp_path / "photos.db"
    first = SqliteRepository(str(path))
    first.connection.executescript("DROP TABLE photo_embeddings; DROP TABLE photo_ai_tags;")
    first.connection.execute("PRAGMA user_version = 0")
    first.close()

    reopened = SqliteRepository(str(path))
    try:
        assert {"photo_embeddings", "photo_ai_tags"} <= _tables(reopened.connection)
    finally:
        reopened.close()


def test_newer_database_is_refused_and_its_file_is_released(tmp_path: Path) -> None:
    path = tmp_path / "photos.db"
    SqliteRepository(str(path)).close()
    raw = _connect(path)
    raw.execute("PRAGMA user_version = 999")
    raw.commit()
    raw.close()

    with pytest.raises(SchemaTooNewError, match="(?i)update"):
        SqliteRepository(str(path))

    check = _connect(path)
    assert _version(check) == 999  # untouched
    check.close()
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(f"{path}{suffix}"):
            os.remove(f"{path}{suffix}")  # no handle left open (matters on Windows)


def test_pending_migrations_apply_in_order_and_record_the_version() -> None:
    connection = _connect(":memory:")
    migrations = [
        Migration(1, "one", "CREATE TABLE a (x INTEGER);"),
        Migration(2, "two", "CREATE TABLE b (x INTEGER);"),
        Migration(3, "three", "CREATE TABLE c (x INTEGER);"),
    ]

    migrate(connection, ":memory:", migrations)

    assert _version(connection) == 3
    assert {"a", "b", "c"} <= _tables(connection)


def test_already_current_database_is_left_alone() -> None:
    connection = _connect(":memory:")
    migrations = [Migration(1, "one", "CREATE TABLE a (x INTEGER);")]
    migrate(connection, ":memory:", migrations)
    connection.execute("INSERT INTO a VALUES (1)")

    migrate(connection, ":memory:", migrations)

    assert connection.execute("SELECT COUNT(*) FROM a").fetchone()[0] == 1


def test_failed_migration_rolls_back_and_keeps_the_previous_version() -> None:
    connection = _connect(":memory:")
    migrate(connection, ":memory:", [Migration(1, "one", "CREATE TABLE a (x INTEGER);")])
    broken = Migration(2, "broken", "CREATE TABLE b (x INTEGER); INSERT INTO nowhere VALUES (1);")

    with pytest.raises(sqlite3.Error):
        migrate(connection, ":memory:", [Migration(1, "one", "SELECT 1;"), broken])

    assert _version(connection) == 1
    assert "b" not in _tables(connection)
    assert not connection.in_transaction


def test_rebuilding_migration_backs_up_an_existing_database_first(tmp_path: Path) -> None:
    path = tmp_path / "photos.db"
    connection = _connect(path)
    migrate(connection, str(path), [Migration(1, "one", "CREATE TABLE a (x INTEGER);")])
    connection.execute("INSERT INTO a VALUES (7)")
    connection.commit()
    rebuild = Migration(2, "rebuild", "DROP TABLE a; CREATE TABLE a (y TEXT);", rebuilds=True)

    migrate(connection, str(path), [Migration(1, "one", "SELECT 1;"), rebuild])
    connection.close()

    backup = _connect(f"{path}.pre-0002")
    try:
        assert _version(backup) == 1
        assert backup.execute("SELECT x FROM a").fetchone()[0] == 7
    finally:
        backup.close()


def test_no_backup_for_a_fresh_database_or_a_non_rebuilding_migration(tmp_path: Path) -> None:
    fresh = tmp_path / "fresh.db"
    connection = _connect(fresh)
    migrate(connection, str(fresh), [Migration(1, "one", "SELECT 1;", rebuilds=True)])
    connection.close()
    assert not Path(f"{fresh}.pre-0001").exists()

    existing = tmp_path / "existing.db"
    connection = _connect(existing)
    migrate(connection, str(existing), [Migration(1, "one", "CREATE TABLE a (x INTEGER);")])
    migrate(
        connection,
        str(existing),
        [Migration(1, "one", "SELECT 1;"), Migration(2, "two", "CREATE TABLE b (x INTEGER);")],
    )
    connection.close()
    assert not Path(f"{existing}.pre-0002").exists()


def test_migration_versions_are_consecutive_from_one() -> None:
    assert [m.version for m in MIGRATIONS] == list(range(1, len(MIGRATIONS) + 1))
    assert replace(MIGRATIONS[0]).version == 1
