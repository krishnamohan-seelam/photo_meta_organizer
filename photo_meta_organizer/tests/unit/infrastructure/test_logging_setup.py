"""PMO-32: one logging setup for the CLI and the desktop backend."""

import importlib
import io
import logging
import logging.handlers

import pytest

from photo_meta_organizer.infrastructure.logging_setup import LOG_FILE_NAME, configure_logging

PACKAGE_LOGGER = "photo_meta_organizer"


# Root handlers are restored after each test by the autouse fixture in tests/conftest.py.


@pytest.mark.unit
class TestConfigureLogging:
    def test_each_package_record_is_emitted_once(self) -> None:
        stream = io.StringIO()
        configure_logging("INFO", stream=stream)

        logging.getLogger("photo_meta_organizer.some.module").info("hello once")

        assert stream.getvalue().count("hello once") == 1

    def test_level_applies_to_the_package_logger(self) -> None:
        stream = io.StringIO()
        configure_logging("WARNING", stream=stream)
        log = logging.getLogger("photo_meta_organizer.application")

        log.info("hidden info")
        log.debug("hidden debug")
        log.warning("visible warning")

        assert "hidden" not in stream.getvalue()
        assert "visible warning" in stream.getvalue()

    def test_debug_level_shows_package_debug(self) -> None:
        stream = io.StringIO()
        configure_logging("DEBUG", stream=stream)

        logging.getLogger("photo_meta_organizer.x").debug("debug detail")

        assert "debug detail" in stream.getvalue()

    def test_no_log_dir_means_no_file(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        configure_logging("INFO", stream=io.StringIO())

        logging.getLogger("photo_meta_organizer.x").info("console only")

        assert list(tmp_path.iterdir()) == []
        assert not any(isinstance(h, logging.FileHandler) for h in logging.getLogger().handlers)

    def test_log_dir_gets_a_rotating_file(self, tmp_path) -> None:
        log_dir = tmp_path / "logs" / "nested"
        configure_logging("INFO", log_dir=log_dir, stream=io.StringIO())

        logging.getLogger("photo_meta_organizer.x").info("to the file")
        for handler in logging.getLogger().handlers:
            handler.flush()

        files = [h for h in logging.getLogger().handlers if isinstance(h, logging.FileHandler)]
        assert len(files) == 1
        assert isinstance(files[0], logging.handlers.RotatingFileHandler)
        assert "to the file" in (log_dir / LOG_FILE_NAME).read_text(encoding="utf-8")

    def test_custom_file_name(self, tmp_path) -> None:
        configure_logging("INFO", log_dir=tmp_path, file_name="backend.log", stream=io.StringIO())
        logging.getLogger("photo_meta_organizer.x").info("named")
        for handler in logging.getLogger().handlers:
            handler.flush()

        assert "named" in (tmp_path / "backend.log").read_text(encoding="utf-8")

    def test_calling_twice_replaces_the_handlers(self) -> None:
        first, second = io.StringIO(), io.StringIO()
        configure_logging("INFO", stream=first)
        configure_logging("INFO", stream=second)

        logging.getLogger("photo_meta_organizer.x").info("only in second")

        assert "only in second" not in first.getvalue()
        assert second.getvalue().count("only in second") == 1

    def test_package_logger_has_no_handlers_of_its_own(self) -> None:
        configure_logging("INFO", stream=io.StringIO())

        package = logging.getLogger(PACKAGE_LOGGER)
        assert package.handlers == []
        assert package.level == logging.NOTSET


@pytest.mark.unit
def test_importing_main_does_not_configure_logging(tmp_path, monkeypatch) -> None:
    """B-23: main.py used to call dictConfig at import time and write a log in the CWD."""
    monkeypatch.chdir(tmp_path)
    root = logging.getLogger()
    before = list(root.handlers)

    import photo_meta_organizer.main as main_module

    importlib.reload(main_module)

    assert root.handlers == before
    assert not (tmp_path / "photo_meta_organizer.log").exists()


@pytest.mark.unit
def test_cli_log_dir_and_level(tmp_path, monkeypatch, capsys) -> None:
    """--log-dir writes a rotating file; log lines go to stderr, never stdout."""
    import sys

    from photo_meta_organizer.main import main

    log_dir = tmp_path / "logs"
    db = tmp_path / "s.db"
    monkeypatch.setattr(
        sys,
        "argv",
        ["main.py", "--log-level", "DEBUG", "--log-dir", str(log_dir), "stats", "--db", str(db)],
    )

    assert main() == 0
    for handler in logging.getLogger().handlers:
        handler.flush()

    out = capsys.readouterr()
    assert "Executing command: stats" in (log_dir / LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "Executing command" in out.err
    assert "Executing command" not in out.out
    assert "Total Photos Indexed" in out.out
