"""Logging setup shared by the CLI and the desktop backend (PMO-32).

Handlers live on the root logger only; package loggers have none of their own and
propagate, so every record is emitted once and one level setting governs them all.
Nothing is configured at import time: each entry point calls :func:`configure_logging`.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import TextIO

LOG_FILE_NAME = "photo_meta_organizer.log"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
MAX_LOG_BYTES = 5_000_000
LOG_BACKUPS = 3


def configure_logging(
    level: str | int = "INFO",
    log_dir: Path | None = None,
    *,
    file_name: str = LOG_FILE_NAME,
    stream: TextIO | None = None,
) -> None:
    """Log at ``level`` to ``stream`` (stderr by default) and, if given, a rotating file.

    ``log_dir`` comes from ``Settings.log_dir`` (``PMO_LOG_DIR`` / ``PMO_DATA_DIR``); with
    none, nothing is written to disk. Calling it again replaces the previous handlers.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler(stream or sys.stderr)]
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.handlers.RotatingFileHandler(
                log_dir / file_name,
                maxBytes=MAX_LOG_BYTES,
                backupCount=LOG_BACKUPS,
                encoding="utf-8",
            )
        )
    logging.basicConfig(level=level, format=LOG_FORMAT, handlers=handlers, force=True)
    # An older configuration may have given the package logger its own level/handlers.
    package = logging.getLogger("photo_meta_organizer")
    package.setLevel(logging.NOTSET)
    for handler in list(package.handlers):
        package.removeHandler(handler)
        handler.close()
