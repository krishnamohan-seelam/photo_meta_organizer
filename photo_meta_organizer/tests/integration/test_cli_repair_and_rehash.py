"""PMO-05/06/08 CLI: `dedupe` (dry run by default) and `sync --rehash`.

SQLite's ``UNIQUE(path)`` constraint (ADR-001) makes the duplicate-path bug B-01
structurally impossible for a native SQLite database: two different hashes can
no longer share a path. The scenario now only arises in a *legacy* TinyDB JSON
file, and the importer (PMO-08) merges duplicates as part of the one-time
import — so ``dedupe`` against a fresh SQLite database always finds nothing,
and the interesting case is the import itself.
"""

import sys
from datetime import datetime

import pytest

from photo_meta_organizer.domain.models import (
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import (
    SqliteRepository,
)
from photo_meta_organizer.infrastructure.repositories.tinydb_repository import (
    TinyDBRepository,
)
from photo_meta_organizer.main import main


def _rec(file_hash, path, added, rating=None):
    return ImageMetadata(
        file_hash=file_hash,
        file_info=ImageFileInfo(
            name="a.jpg", path=path, size_bytes=1, mime_type="image/jpeg"
        ),
        dimensions=ImageDimensions(width=1, height=1),
        exif=ImageExifData(),
        rating=rating,
        added_at=added,
    )


def _run(monkeypatch, *argv) -> int:
    monkeypatch.setattr(sys, "argv", ["main.py", *argv])
    return main()


def test_legacy_duplicate_paths_are_merged_on_import(tmp_path, monkeypatch):
    """A pre-SQLite JSON file with duplicate paths (the old MODIFIED bug) is merged
    once, automatically, the first time any CLI command opens it via ``--db``.
    """
    json_db = str(tmp_path / "legacy.json")
    repo = TinyDBRepository(json_db)
    repo.save(_rec("old", "/p/a.jpg", datetime(2024, 1, 1), rating=3))
    repo.save(_rec("new", "/p/a.jpg", datetime(2024, 2, 1)))
    repo.close()

    assert _run(monkeypatch, "dedupe", "--db", json_db) == 0

    imported = SqliteRepository(str(tmp_path / "legacy.db"))
    try:
        assert imported.count() == 1
        survivor = imported.get_by_filehash("new")
        assert survivor is not None
        assert survivor.rating == 3  # curation carried over from the merged duplicate
    finally:
        imported.close()


def test_dedupe_with_nothing_to_do(tmp_path, monkeypatch, capsys):
    db = str(tmp_path / "db.db")
    SqliteRepository(db).close()

    assert _run(monkeypatch, "dedupe", "--db", db) == 0
    assert "no duplicate" in capsys.readouterr().out.lower()


def test_sync_accepts_rehash_and_reports_refreshed_fingerprints(
    tmp_path, monkeypatch, capsys
):
    photos = tmp_path / "photos"
    photos.mkdir()
    (photos / "a.jpg").write_bytes(b"not a real jpeg")
    db = str(tmp_path / "db.db")

    assert _run(monkeypatch, "sync", "--path", str(photos), "--db", db) == 0
    assert _run(monkeypatch, "sync", "--path", str(photos), "--db", db, "--rehash") == 0

    out = capsys.readouterr().out
    assert "unchanged" in out
