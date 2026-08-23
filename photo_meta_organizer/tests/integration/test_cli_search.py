"""Integration tests for CLI search and stats subcommands in main.py."""

import sys
from datetime import datetime, timezone
import pytest

from photo_meta_organizer.domain.models import (
    GpsCoordinates,
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.infrastructure.repositories.tinydb_repository import (
    TinyDBRepository,
)
from photo_meta_organizer.main import (
    handle_search_command,
    handle_stats_command,
    main,
)


@pytest.fixture
def temp_db_path(tmp_path):
    db_file = str(tmp_path / "cli_test_db.json")
    repo = TinyDBRepository(db_path=db_file)

    m1 = ImageMetadata(
        file_hash="sha1111",
        file_info=ImageFileInfo(
            name="sony_beach.jpg",
            path="/photos/sony_beach.jpg",
            size_bytes=1048576,
            mime_type="image/jpeg",
        ),
        dimensions=ImageDimensions(width=1920, height=1080),
        exif=ImageExifData(
            camera_make="Sony",
            camera_model="A7IV",
            captured_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            location=GpsCoordinates(latitude=37.7749, longitude=-122.4194),
        ),
        labels=["vacation", "beach"],
    )

    m2 = ImageMetadata(
        file_hash="sha2222",
        file_info=ImageFileInfo(
            name="canon_mountain.jpg",
            path="/photos/canon_mountain.jpg",
            size_bytes=5242880,
            mime_type="image/jpeg",
        ),
        dimensions=ImageDimensions(width=4000, height=3000),
        exif=ImageExifData(
            camera_make="Canon",
            camera_model="EOS R5",
            captured_at=datetime(2024, 3, 20, 15, 30, 0, tzinfo=timezone.utc),
        ),
        labels=["landscape"],
    )

    repo.save(m1)
    repo.save(m2)
    repo.close()
    return db_file


def test_cli_search_by_camera(temp_db_path, capsys):
    test_args = ["main.py", "search", "--db", temp_db_path, "--camera", "Sony"]
    sys_argv_backup = sys.argv
    sys.argv = test_args
    try:
        exit_code = main()
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "sony_beach.jpg" in captured.out
        assert "Sony A7IV" in captured.out
    finally:
        sys.argv = sys_argv_backup


def test_cli_search_by_date_and_sort(temp_db_path, capsys):
    test_args = [
        "main.py",
        "search",
        "--db",
        temp_db_path,
        "--date",
        "2024-01",
        "--sort",
        "size_bytes",
        "--order",
        "desc",
    ]
    sys_argv_backup = sys.argv
    sys.argv = test_args
    try:
        exit_code = main()
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "sony_beach.jpg" in captured.out
    finally:
        sys.argv = sys_argv_backup


def test_cli_stats_command(temp_db_path, capsys):
    test_args = ["main.py", "stats", "--db", temp_db_path]
    sys_argv_backup = sys.argv
    sys.argv = test_args
    try:
        exit_code = main()
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "LIBRARY STATISTICS" in captured.out
        assert "Total Photos Indexed" in captured.out
        assert "2" in captured.out
        assert "Sony A7IV" in captured.out or "Sony" in captured.out
    finally:
        sys.argv = sys_argv_backup


def test_cli_search_by_location(temp_db_path, capsys):
    test_args = [
        "main.py",
        "search",
        "--db",
        temp_db_path,
        "--location",
        "37.7749,-122.4194,10.0",
    ]
    sys_argv_backup = sys.argv
    sys.argv = test_args
    try:
        exit_code = main()
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "sony_beach.jpg" in captured.out
    finally:
        sys.argv = sys_argv_backup


def test_cli_search_by_tags(temp_db_path, capsys):
    test_args = [
        "main.py",
        "search",
        "--db",
        temp_db_path,
        "--tags",
        "landscape",
    ]
    sys_argv_backup = sys.argv
    sys.argv = test_args
    try:
        exit_code = main()
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "canon_mountain.jpg" in captured.out
    finally:
        sys.argv = sys_argv_backup


def test_cli_search_empty_results(temp_db_path, capsys):
    test_args = [
        "main.py",
        "search",
        "--db",
        temp_db_path,
        "--camera",
        "NikonUnmatchedCamera",
    ]
    sys_argv_backup = sys.argv
    sys.argv = test_args
    try:
        exit_code = main()
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "No photos found matching" in captured.out
    finally:
        sys.argv = sys_argv_backup
