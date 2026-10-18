"""The CLI keeps its data in the OS per-user folders, split by kind (data, cache, logs)."""

import logging
import sys

import pytest

from photo_meta_organizer.application.settings import UserDirs
from photo_meta_organizer.infrastructure.logging_setup import LOG_FILE_NAME
from photo_meta_organizer.main import main


def run(monkeypatch, *argv: str) -> int:
    monkeypatch.setattr(sys, "argv", ["main.py", *argv])
    return main()


class TestPathsCommand:
    def test_prints_where_each_kind_of_data_lives(self, monkeypatch, capsys, user_dirs: UserDirs):
        assert run(monkeypatch, "paths") == 0
        out = capsys.readouterr().out
        assert str(user_dirs.data / "photos.db") in out
        assert str(user_dirs.cache / "thumbnails") in out
        assert str(user_dirs.data / "models") in out
        assert str(user_dirs.log) in out

    def test_follows_the_flags_and_the_environment(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setenv("PMO_CACHE_DIR", str(tmp_path / "thumbs"))
        assert run(monkeypatch, "paths", "--db", str(tmp_path / "lib.db")) == 0
        out = capsys.readouterr().out
        assert str(tmp_path / "lib.db") in out and str(tmp_path / "thumbs") in out

    def test_writes_nothing(self, monkeypatch, user_dirs: UserDirs):
        assert run(monkeypatch, "paths") == 0
        assert not user_dirs.data.exists() and not user_dirs.log.exists()


class TestLogFile:
    def test_no_log_file_by_default(self, monkeypatch, tmp_path, user_dirs: UserDirs):
        assert run(monkeypatch, "stats", "--db", str(tmp_path / "s.db")) == 0
        assert not user_dirs.log.exists()

    def test_log_flag_writes_to_the_os_log_folder(self, monkeypatch, tmp_path, user_dirs):
        argv = ("--log-level", "DEBUG", "--log", "stats", "--db", str(tmp_path / "s.db"))
        assert run(monkeypatch, *argv) == 0
        for handler in logging.getLogger().handlers:
            handler.flush()
        log = (user_dirs.log / LOG_FILE_NAME).read_text(encoding="utf-8")
        assert "Executing command: stats" in log


class TestLibraryLeftBehind:
    """Before this change the default library was photos.db in the working directory."""

    @pytest.fixture
    def old_library(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "photos.db").write_bytes(b"")
        return tmp_path / "photos.db"

    def test_says_where_the_library_now_lives(self, monkeypatch, capsys, old_library, user_dirs):
        assert run(monkeypatch, "stats") == 0
        err = capsys.readouterr().err
        assert "photos.db" in err and str(user_dirs.data / "photos.db") in err

    def test_quiet_when_a_database_is_named(self, monkeypatch, capsys, old_library):
        assert run(monkeypatch, "stats", "--db", str(old_library)) == 0
        assert "now lives" not in capsys.readouterr().err

    def test_quiet_once_the_new_library_exists(self, monkeypatch, capsys, old_library, user_dirs):
        user_dirs.data.mkdir(parents=True)
        (user_dirs.data / "photos.db").write_bytes(b"")
        assert run(monkeypatch, "stats") == 0
        assert "now lives" not in capsys.readouterr().err
