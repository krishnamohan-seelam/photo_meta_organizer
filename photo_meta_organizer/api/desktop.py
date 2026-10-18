"""Backend entry point for the Electron desktop app (and its PyInstaller bundle).

The packaged app installs into a directory the user may not be able to write to, and
an update replaces it wholesale, so nothing may be written there (PMO-12). With no path
arguments the data goes to the OS per-user folders (``application.settings.user_dirs``),
the same library the CLI and the API use, and a rotating ``backend.log`` is always kept:

    --db PATH         SQLite database           (default: <data>/photos.db)
    --cache-dir PATH  thumbnail cache           (default: <cache>/thumbnails)
    --log-dir PATH    rotating backend log      (default: <logs>)
    --data-dir PATH   one folder for all of the above (and models/)
    --legacy-dir PATH where an older build kept its data; may be repeated, first wins.
                      Its database is copied once if --db does not exist yet, and its
                      AI model (``models/`` or ``.cache/models/``) is moved once.

Electron passes ``--legacy-dir`` for its ``userData`` folder (builds before the OS
folders) and for the install's resources folder (older still).
"""

import argparse
import logging
import shutil
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
        "--legacy-dir",
        type=Path,
        action="append",
        default=[],
        help="Old data location to adopt the database and model from, once (repeatable)",
    )
    return parser.parse_args(argv)


def resolve_settings(args: argparse.Namespace) -> Settings:
    """Settings for this run: flags first, then the PMO_* environment, then the OS folders."""
    return Settings.from_env(
        data_dir=args.data_dir,
        db_path=args.db,
        cache_dir=args.cache_dir,
        log_dir=args.log_dir,
        log_to_file=True,
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


def adopt_legacy_models(target: Path, candidates: Iterable[Path]) -> Path | None:
    """Move an older install's model folder to ``target``, once. Returns the source used.

    Does nothing if ``target`` already holds anything. Moved rather than copied: the
    model can be downloaded again, and a duplicate would leave ~305 MB behind.
    """
    if target.is_dir() and any(target.iterdir()):
        return None
    for source in candidates:
        if not source.is_dir() or not any(source.iterdir()):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_dir():
            target.rmdir()  # empty, checked above; shutil.move would nest inside it
        shutil.move(str(source), str(target))
        logger.info("Moved the AI model from %s to %s", source, target)
        return source
    return None


def adopt_legacy_data(settings: Settings, legacy_dirs: Sequence[Path]) -> None:
    """Bring the database and the AI model of older builds into ``settings``' folders."""
    adopt_legacy_database(
        settings.db_path, [d / name for d in legacy_dirs for name in LEGACY_DB_NAMES]
    )
    adopt_legacy_models(
        settings.models_dir,
        [d / sub for d in legacy_dirs for sub in (Path("models"), Path(".cache") / "models")],
    )


def configure_logging(log_dir: Path | None) -> None:
    """INFO to stderr (Electron shows it) and, if ``log_dir`` is set, a rotating file."""
    from photo_meta_organizer.infrastructure.logging_setup import (
        configure_logging as _configure_logging,
    )

    _configure_logging("INFO", log_dir, file_name="backend.log")


def main(argv: Sequence[str] | None = None) -> None:
    import uvicorn

    from photo_meta_organizer.api.app import create_app

    args = parse_args(argv)
    settings = resolve_settings(args)
    configure_logging(settings.log_dir)

    adopt_legacy_data(settings, args.legacy_dir)

    app = create_app(settings=settings)
    logger.info(
        "Database: %s | cache: %s | model: %s",
        settings.db_path.resolve(),
        settings.thumbnail_dir,
        settings.models_dir,
    )

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
