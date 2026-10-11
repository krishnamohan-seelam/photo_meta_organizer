"""Integration tests for CLI search and stats subcommands in main.py."""

import sys
from datetime import UTC, datetime

import pytest

from photo_meta_organizer.domain.models import (
    GpsCoordinates,
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import (
    SqliteRepository,
)
from photo_meta_organizer.main import (
    main,
)


@pytest.fixture
def temp_db_path(tmp_path):
    db_file = str(tmp_path / "cli_test_db.db")
    repo = SqliteRepository(db_path=db_file)

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
            captured_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
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
            captured_at=datetime(2024, 3, 20, 15, 30, 0, tzinfo=UTC),
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


def _run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["main.py", *argv])
    return main()


@pytest.mark.parametrize("command", ["index", "sync"])
def test_path_is_required(command, tmp_path, monkeypatch, capsys):
    """B-25: omitting --path used to fail later with a TypeError shown as 'Error:'."""
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, command, "--db", str(tmp_path / "x.db"))
    assert exc.value.code == 2
    assert "--path" in capsys.readouterr().err
    assert not (tmp_path / "x.db").exists()


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--date", "2024-13"], "Invalid date"),
        (["--date-from", "2024-05-01", "--date-to", "2024-03-01"], "after"),
        (["--location", "37.7,-122.4"], "Invalid location"),
        (["--lat", "37.7", "--lon", "-122.4"], "--lat, --lon and --radius"),
    ],
)
def test_bad_search_input_is_an_error_not_an_unfiltered_search(
    temp_db_path, monkeypatch, capsys, args, message
):
    assert _run(monkeypatch, "search", "--db", temp_db_path, *args) == 2
    captured = capsys.readouterr()
    assert message in captured.err
    assert "sony_beach.jpg" not in captured.out


def test_date_to_includes_the_whole_day(temp_db_path, monkeypatch, capsys):
    """The Canon photo was taken 2024-03-20 15:30; --date-to 2024-03-20 must include it."""
    assert _run(monkeypatch, "search", "--db", temp_db_path, "--date-to", "2024-03-20") == 0
    assert "canon_mountain.jpg" in capsys.readouterr().out


def test_separate_lat_lon_radius(temp_db_path, monkeypatch, capsys):
    argv = ["--lat", "37.7749", "--lon", "-122.4194", "--radius", "5"]
    assert _run(monkeypatch, "search", "--db", temp_db_path, *argv) == 0
    out = capsys.readouterr().out
    assert "sony_beach.jpg" in out and "canon_mountain.jpg" not in out
