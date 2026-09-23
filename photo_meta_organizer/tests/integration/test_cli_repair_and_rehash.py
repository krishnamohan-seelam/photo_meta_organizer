"""PMO-05/06 CLI: `dedupe` (dry run by default) and `sync --rehash`."""

import sys
from datetime import datetime

import pytest

from photo_meta_organizer.domain.models import (
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.infrastructure.repositories.tinydb_repository import TinyDBRepository
from photo_meta_organizer.main import main


def _rec(file_hash, path, added, rating=None):
    return ImageMetadata(
        file_hash=file_hash,
        file_info=ImageFileInfo(name="a.jpg", path=path, size_bytes=1, mime_type="image/jpeg"),
        dimensions=ImageDimensions(width=1, height=1),
        exif=ImageExifData(),
        rating=rating,
        added_at=added,
    )


def _run(monkeypatch, *argv) -> int:
    monkeypatch.setattr(sys, "argv", ["main.py", *argv])
    return main()


@pytest.fixture
def db_with_duplicate_path(tmp_path):
    db = str(tmp_path / "db.json")
    repo = TinyDBRepository(db)
    repo.save(_rec("old", "/p/a.jpg", datetime(2024, 1, 1), rating=3))
    repo.save(_rec("new", "/p/a.jpg", datetime(2024, 2, 1)))
    repo.close()
    return db


def _count(db) -> int:
    repo = TinyDBRepository(db)
    try:
        return repo.count()
    finally:
        repo.close()


def test_dedupe_is_a_dry_run_by_default(db_with_duplicate_path, monkeypatch, capsys):
    assert _run(monkeypatch, "dedupe", "--db", db_with_duplicate_path) == 0

    out = capsys.readouterr().out
    assert "dry run" in out.lower()
    assert "1 path" in out
    assert _count(db_with_duplicate_path) == 2


def test_dedupe_apply_collapses_the_duplicates(db_with_duplicate_path, monkeypatch, capsys):
    assert _run(monkeypatch, "dedupe", "--db", db_with_duplicate_path, "--apply") == 0

    assert _count(db_with_duplicate_path) == 1
    repo = TinyDBRepository(db_with_duplicate_path)
    try:
        assert repo.get_by_filehash("new").rating == 3  # curation merged into the survivor
    finally:
        repo.close()


def test_dedupe_with_nothing_to_do(tmp_path, monkeypatch, capsys):
    db = str(tmp_path / "db.json")
    TinyDBRepository(db).close()

    assert _run(monkeypatch, "dedupe", "--db", db) == 0
    assert "no duplicate" in capsys.readouterr().out.lower()


def test_sync_accepts_rehash_and_reports_refreshed_fingerprints(tmp_path, monkeypatch, capsys):
    photos = tmp_path / "photos"
    photos.mkdir()
    (photos / "a.jpg").write_bytes(b"not a real jpeg")
    db = str(tmp_path / "db.json")

    assert _run(monkeypatch, "sync", "--path", str(photos), "--db", db) == 0
    assert _run(monkeypatch, "sync", "--path", str(photos), "--db", db, "--rehash") == 0

    out = capsys.readouterr().out
    assert "unchanged" in out
