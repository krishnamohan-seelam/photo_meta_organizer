"""Backend entry point for the Electron desktop app (and its PyInstaller bundle).

The packaged app installs into a directory the user may not be able to write to, and
an update replaces it wholesale, so nothing may be written there (PMO-12). Electron
passes paths under ``app.getPath("userData")``:

    --db PATH         SQLite database           (default: <data-dir>/photos.db)
    --cache-dir PATH  thumbnail cache           (default: <data-dir>/cache/thumbnails)
    --log-dir PATH    rotating backend log      (default: <data-dir>/logs)
    --data-dir PATH   supplies the three defaults above
    --legacy-dir PATH where older builds kept their data (the install's resources dir);
                      a database found there is adopted once if --db does not exist yet

With no path arguments it keeps the development layout: ``photos.db`` and
``.cache/thumbnails`` relative to the working directory, logging to stderr only.
"""

import argparse
import logging
import logging.handlers
import shutil
import sys
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path

from photo_meta_organizer.application.settings import Settings

READY_PREFIX = "DESKTOP_BACKEND_READY:"
LEGACY_DB_NAMES = ("photos.db", "metadata.json")

logger = logging.getLogger(__name__)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Photo Meta Organizer desktop backend")
    parser.add_argument("--host", default="127.0.0.1", help="Binding host (keep it loopback)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    parser.add_argument("--data-dir", type=Path, help="Default location for db, cache and logs")
    parser.add_argument("--db", type=Path, help="SQLite database file")
    parser.add_argument("--cache-dir", type=Path, help="Thumbnail cache directory")
    parser.add_argument("--log-dir", type=Path, help="Directory for backend.log")
    parser.add_argument(
        "--legacy-dir", type=Path, help="Old data location to adopt a database from, once"
    )
    return parser.parse_args(argv)


def resolve_settings(args: argparse.Namespace) -> Settings:
    """Settings for this run: flags first, then the PMO_* environment, then the dev layout."""
    return Settings.from_env(
        data_dir=args.data_dir, db_path=args.db, cache_dir=args.cache_dir, log_dir=args.log_dir
    )


def adopt_legacy_database(target: Path, candidates: Iterable[Path]) -> Path | None:
    """Bring an older install's database to ``target``, once. Returns the source used.

    Does nothing if ``target`` already exists. A SQLite file is copied (with its WAL
    and shared-memory files, if present); a legacy TinyDB ``.json`` is imported through
    the PMO-08 importer from a temporary copy, so the original is never modified and
    nothing is written next to it.
    """
    if target.exists():
        return None
    for source in candidates:
        if not source.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix == ".json":
            from photo_meta_organizer.infrastructure.importers.legacy_json_importer import (
                import_legacy_json,
            )

            with tempfile.TemporaryDirectory() as tmp:
                copy = Path(tmp) / source.name
                shutil.copy2(source, copy)
                result = import_legacy_json(str(copy), str(target))
            logger.info(
                "Imported %s photo(s) from legacy %s into %s",
                result.imported_count,
                source,
                target,
            )
        else:
            shutil.copy2(source, target)
            for suffix in ("-wal", "-shm"):
                side = source.with_name(source.name + suffix)
                if side.is_file():
                    shutil.copy2(side, target.with_name(target.name + suffix))
            logger.info("Copied legacy database %s to %s", source, target)
        return source
    return None


def configure_logging(log_dir: Path | None) -> None:
    """INFO to stderr (Electron shows it) and, if ``log_dir`` is set, a rotating file."""
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.handlers.RotatingFileHandler(
                log_dir / "backend.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
            )
        )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def main(argv: Sequence[str] | None = None) -> None:
    import uvicorn

    from photo_meta_organizer.api.app import create_app

    args = parse_args(argv)
    settings = resolve_settings(args)
    configure_logging(settings.log_dir)

    if args.legacy_dir is not None:
        adopt_legacy_database(
            settings.db_path, [args.legacy_dir / name for name in LEGACY_DB_NAMES]
        )

    app = create_app(settings=settings)
    logger.info("Database: %s | cache: %s", settings.db_path.resolve(), settings.thumbnail_dir)

    class _Server(uvicorn.Server):
        async def startup(self, sockets: list | None = None) -> None:
            await super().startup(sockets=sockets)
            if self.started:
                # Only now is the port accepting connections: Electron may load the UI.
                print(f"{READY_PREFIX}{args.port}", flush=True)

    config = uvicorn.Config(
        app=app,
        host=args.host,
        port=args.port,
        log_config=None,  # use the logging configured above
        access_log=False,
    )
    _Server(config).run()


if __name__ == "__main__":
    main()
