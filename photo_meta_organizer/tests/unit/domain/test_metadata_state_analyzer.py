"""Unit tests for MetadataStateAnalyzer domain service.

Covers all four file state classifications (NEW, MODIFIED, UNCHANGED, DELETED),
the hybrid fingerprinting logic, path normalisation, and edge cases.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from photo_meta_organizer.domain.models import (
    FileInfo,
    FileState,
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.domain.services import MetadataStateAnalyzer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HASH_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
HASH_B = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

BASE_MTIME = datetime(2024, 1, 1, 12, 0, 0)


def _make_metadata(path: str, file_hash: str, size_bytes: int = 1000) -> ImageMetadata:
    """Build a minimal ImageMetadata for test setup."""
    return ImageMetadata(
        file_hash=file_hash,
        file_info=ImageFileInfo(
            name=Path(path).name,
            path=path,
            size_bytes=size_bytes,
            mime_type="image/jpeg",
        ),
        dimensions=ImageDimensions(width=100, height=100),
        exif=ImageExifData(),
    )


def _make_file_info(path: str, size_bytes: int = 1000) -> FileInfo:
    return FileInfo(path=path, size_bytes=size_bytes, modified_time=BASE_MTIME)


def _constant_hash(h: str):
    """Return a hash function that always returns the given hash string."""
    return lambda _path: h


# ---------------------------------------------------------------------------
# MetadataStateAnalyzer tests
# ---------------------------------------------------------------------------


@pytest.fixture
def analyzer() -> MetadataStateAnalyzer:
    return MetadataStateAnalyzer()


class TestMetadataStateAnalyzerNew:
    """Tests for NEW file detection."""

    def test_file_not_in_db_is_new(self, analyzer, tmp_path):
        photo = tmp_path / "new_photo.jpg"
        photo.write_bytes(b"fake image")

        disk_files = {"p": _make_file_info(str(photo), size_bytes=10)}
        db_entries: list[ImageMetadata] = []

        states = analyzer.analyze_changes(
            disk_files=disk_files,
            db_entries=db_entries,
            compute_hash=_constant_hash(HASH_A),
        )

        assert len(states) == 1
        assert states[0].state == "NEW"
        assert states[0].file_hash == HASH_A

    def test_new_file_records_size(self, analyzer, tmp_path):
        photo = tmp_path / "photo.jpg"
        photo.write_bytes(b"x" * 512)

        disk_files = {"p": _make_file_info(str(photo), size_bytes=512)}
        states = analyzer.analyze_changes(
            disk_files=disk_files,
            db_entries=[],
            compute_hash=_constant_hash(HASH_A),
        )
        assert states[0].size_bytes == 512

    def test_multiple_new_files(self, analyzer, tmp_path):
        files = {}
        for i in range(3):
            p = tmp_path / f"img{i}.jpg"
            p.write_bytes(b"x" * 100)
            files[str(p)] = _make_file_info(str(p), size_bytes=100)

        states = analyzer.analyze_changes(
            disk_files=files,
            db_entries=[],
            compute_hash=_constant_hash(HASH_A),
        )
        assert len(states) == 3
        assert all(s.state == "NEW" for s in states)


class TestMetadataStateAnalyzerUnchanged:
    """Tests for UNCHANGED detection (fast-path via size equality)."""

    def test_same_size_is_unchanged_no_hash(self, analyzer, tmp_path):
        photo = tmp_path / "photo.jpg"
        photo.write_bytes(b"x" * 1000)
        path_str = str(photo)

        disk_files = {path_str: _make_file_info(path_str, size_bytes=1000)}
        db_entries = [_make_metadata(path_str, HASH_A, size_bytes=1000)]

        hash_called = []

        def tracking_hash(p):
            hash_called.append(p)
            return HASH_A

        states = analyzer.analyze_changes(
            disk_files=disk_files,
            db_entries=db_entries,
            compute_hash=tracking_hash,
        )

        assert len(states) == 1
        assert states[0].state == "UNCHANGED"
        # Fast-path: hash should NOT be called when sizes match
        assert len(hash_called) == 0

    def test_size_differs_but_content_same_is_unchanged(self, analyzer, tmp_path):
        """Size changed (e.g. metadata strip) but SHA-256 identical → UNCHANGED."""
        photo = tmp_path / "photo.jpg"
        photo.write_bytes(b"x" * 800)
        path_str = str(photo)

        disk_files = {path_str: _make_file_info(path_str, size_bytes=800)}
        db_entries = [_make_metadata(path_str, HASH_A, size_bytes=1000)]

        # Return same hash as stored
        states = analyzer.analyze_changes(
            disk_files=disk_files,
            db_entries=db_entries,
            compute_hash=_constant_hash(HASH_A),
        )
        assert states[0].state == "UNCHANGED"


class TestMetadataStateAnalyzerModified:
    """Tests for MODIFIED detection."""

    def test_size_differs_and_different_hash_is_modified(self, analyzer, tmp_path):
        photo = tmp_path / "photo.jpg"
        photo.write_bytes(b"updated content")
        path_str = str(photo)

        disk_files = {path_str: _make_file_info(path_str, size_bytes=800)}
        db_entries = [_make_metadata(path_str, HASH_A, size_bytes=1000)]

        states = analyzer.analyze_changes(
            disk_files=disk_files,
            db_entries=db_entries,
            compute_hash=_constant_hash(HASH_B),
        )
        assert len(states) == 1
        fs = states[0]
        assert fs.state == "MODIFIED"
        assert fs.file_hash == HASH_B
        assert fs.previous_hash == HASH_A

    def test_modified_file_sets_previous_hash(self, analyzer, tmp_path):
        photo = tmp_path / "photo.jpg"
        photo.write_bytes(b"new data")
        path_str = str(photo)

        disk_files = {path_str: _make_file_info(path_str, size_bytes=500)}
        db_entries = [_make_metadata(path_str, HASH_A, size_bytes=1000)]

        states = analyzer.analyze_changes(
            disk_files=disk_files,
            db_entries=db_entries,
            compute_hash=_constant_hash(HASH_B),
        )
        assert states[0].previous_hash == HASH_A


class TestMetadataStateAnalyzerDeleted:
    """Tests for DELETED detection (DB entry, no disk file)."""

    def test_db_only_entry_is_deleted(self, analyzer):
        disk_files: dict = {}
        db_entries = [_make_metadata("/photos/ghost.jpg", HASH_A)]

        states = analyzer.analyze_changes(
            disk_files=disk_files,
            db_entries=db_entries,
            compute_hash=_constant_hash(HASH_A),
        )
        assert len(states) == 1
        assert states[0].state == "DELETED"

    def test_deleted_state_carries_hash(self, analyzer):
        db_entries = [_make_metadata("/photos/ghost.jpg", HASH_A)]
        states = analyzer.analyze_changes(
            disk_files={},
            db_entries=db_entries,
            compute_hash=_constant_hash(HASH_A),
        )
        assert states[0].file_hash == HASH_A

    def test_multiple_deleted(self, analyzer):
        db_entries = [
            _make_metadata("/photos/a.jpg", HASH_A),
            _make_metadata("/photos/b.jpg", HASH_B),
        ]
        states = analyzer.analyze_changes(
            disk_files={},
            db_entries=db_entries,
            compute_hash=_constant_hash(HASH_A),
        )
        deleted = [s for s in states if s.state == "DELETED"]
        assert len(deleted) == 2


class TestMetadataStateAnalyzerMixed:
    """Tests for mixed-state scenarios."""

    def test_mixed_states_all_classified(self, analyzer, tmp_path):
        """Library with 1 new, 1 modified, 1 unchanged, 1 deleted."""
        new_photo = tmp_path / "new.jpg"
        new_photo.write_bytes(b"n" * 100)

        unchanged_photo = tmp_path / "unchanged.jpg"
        unchanged_photo.write_bytes(b"u" * 200)

        modified_photo = tmp_path / "modified.jpg"
        modified_photo.write_bytes(b"m" * 300)

        disk_files = {
            str(new_photo): _make_file_info(str(new_photo), size_bytes=100),
            str(unchanged_photo): _make_file_info(str(unchanged_photo), size_bytes=200),
            str(modified_photo): _make_file_info(str(modified_photo), size_bytes=300),
        }

        db_entries = [
            _make_metadata(str(unchanged_photo), HASH_A, size_bytes=200),
            _make_metadata(str(modified_photo), HASH_A, size_bytes=999),
            _make_metadata("/photos/deleted.jpg", HASH_B),
        ]

        def mock_hash(path: str) -> str:
            if "modified" in path:
                return HASH_B  # Content actually changed
            return HASH_A

        states = analyzer.analyze_changes(
            disk_files=disk_files,
            db_entries=db_entries,
            compute_hash=mock_hash,
        )

        state_map = {s.file_path: s.state for s in states}

        assert any(s.state == "NEW" for s in states)
        assert any(s.state == "UNCHANGED" for s in states)
        assert any(s.state == "MODIFIED" for s in states)
        assert any(s.state == "DELETED" for s in states)

    def test_empty_disk_and_db_returns_empty(self, analyzer):
        states = analyzer.analyze_changes(disk_files={}, db_entries=[])
        assert states == []


class TestMetadataStateAnalyzerEdgeCases:
    """Edge case tests."""

    def test_hash_os_error_on_new_file_produces_none_hash(self, analyzer, tmp_path):
        """If hashing fails for a new file, hash is None and state is still NEW."""
        photo = tmp_path / "new.jpg"
        photo.write_bytes(b"data")
        path_str = str(photo)

        def failing_hash(p):
            raise OSError("Permission denied")

        disk_files = {path_str: _make_file_info(path_str, size_bytes=4)}
        states = analyzer.analyze_changes(
            disk_files=disk_files,
            db_entries=[],
            compute_hash=failing_hash,
        )
        assert states[0].state == "NEW"
        assert states[0].file_hash is None

    def test_hash_os_error_on_modified_file_is_skipped(self, analyzer, tmp_path):
        """If hashing fails for a candidate-modified file, it is silently skipped."""
        photo = tmp_path / "mod.jpg"
        photo.write_bytes(b"data")
        path_str = str(photo)

        def failing_hash(p):
            raise OSError("Permission denied")

        disk_files = {path_str: _make_file_info(path_str, size_bytes=9999)}
        db_entries = [_make_metadata(path_str, HASH_A, size_bytes=1)]

        states = analyzer.analyze_changes(
            disk_files=disk_files,
            db_entries=db_entries,
            compute_hash=failing_hash,
        )
        # File that can't be hashed is excluded (no crash)
        assert len(states) == 0
