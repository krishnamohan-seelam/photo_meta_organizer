"""What every command shares: global options, start-up, the library, output helpers."""

import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal, NoReturn

import typer
from typer.core import TyperCommand, TyperGroup, TyperOption

from photo_meta_organizer.application import settings as app_settings
from photo_meta_organizer.application.interfaces import ImageMetadataRepository
from photo_meta_organizer.application.settings import Settings
from photo_meta_organizer.domain.models import ImageExifData

logger = logging.getLogger(__name__)

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

DB_HELP = "Path to metadata database file (default: $PMO_DB, else the per-user data folder)"
DbOption = Annotated[str | None, typer.Option("--db", help=DB_HELP)]
PathOption = Annotated[str, typer.Option("--path", help="Path to photos directory")]

# The default library used to be photos.db in the working directory.
OLD_DEFAULT_DB = Path("photos.db")


def _hide_defaults(params: Sequence[object]) -> None:
    """Typer appends ``[default: X]``; our help texts already say ``(default: X)``."""
    for param in params:
        if isinstance(param, TyperOption):
            param.show_default = False


class Group(TyperGroup):
    """The top-level command: global options with argparse-style help."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _hide_defaults(self.params)


class Command(TyperCommand):
    """A command that accepts any unambiguous prefix of a long option (``--dry``), as argparse did.

    An ambiguous prefix is a usage error. A value given to an option is never expanded.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _hide_defaults(self.params)

    # ctx is the vendored click Context (typer._click is private), hence Any.
    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        takes_value = {
            name: not (getattr(param, "is_flag", False) or getattr(param, "count", False))
            for param in self.get_params(ctx)
            for name in (*param.opts, *param.secondary_opts)
            if name.startswith("--")
        }
        expanded: list[str] = []
        value_expected = False
        for position, arg in enumerate(args):
            if arg == "--":
                expanded.extend(args[position:])
                break
            if value_expected or not arg.startswith("--"):
                expanded.append(arg)
                value_expected = False
                continue
            name, equals, value = arg.partition("=")
            full = _full_option_name(ctx, name, takes_value)
            expanded.append(f"{full}{equals}{value}")
            value_expected = takes_value.get(full, False) and not equals
        return super().parse_args(ctx, expanded)


def _full_option_name(ctx: Any, name: str, options: dict[str, bool]) -> str:
    """``name`` itself if it is an option, else the one option it starts, else unchanged."""
    if name in options:
        return name
    matches = sorted(option for option in options if option.startswith(name))
    if len(matches) > 1:
        ctx.fail(f"Ambiguous option {name}: could be {', '.join(matches)}")
    return matches[0] if matches else name


@dataclass(frozen=True)
class GlobalOptions:
    """The options given before the command (``--log-level``, ``--log``, ``--log-dir``)."""

    log_level: LogLevel = "INFO"
    log: bool = False
    log_dir: str | None = None


def start(ctx: typer.Context, db: str | None = None, model_dir: str | None = None) -> Settings:
    """Settings for this run (flag > environment > default), with logging configured.

    The same precedence as the API and the desktop backend. Called by each command once
    its own options are known, before it does anything else.
    """
    options: GlobalOptions = ctx.obj or GlobalOptions()
    settings = Settings.from_env(
        db_path=db,
        log_dir=options.log_dir,
        log_to_file=options.log,
        model_dir=model_dir,
    )
    _note_library_left_behind(db, settings)

    from photo_meta_organizer.infrastructure.logging_setup import configure_logging

    configure_logging(options.log_level, settings.log_dir)
    logger.debug("Starting Photo Meta Organizer (log level: %s)", options.log_level)
    logger.debug("Executing command: %s", ctx.info_name)
    return settings


def open_library(settings: Settings) -> ImageMetadataRepository:
    """The library at ``settings.db_path`` (SQLite; a legacy ``.json`` is imported once)."""
    from photo_meta_organizer.application.composition import build_repository

    return build_repository(str(settings.db_path))


def finish(code: int) -> NoReturn:
    """End the command with ``code`` (0 = success)."""
    raise typer.Exit(code)


def print_errors(errors: Sequence[str]) -> None:
    """The per-file error list every long-running command ends with."""
    if not errors:
        return
    print(f"Errors ({len(errors)}):")
    for error in errors:
        # ASCII only: a redirected Windows console cannot encode a cross mark.
        print(f"  x {error}")


def root_unavailable(exc: OSError) -> NoReturn:
    """A scan could not read its folder: say so and end the command with 1."""
    print(f"{exc}. Nothing was changed.")
    finish(1)


def camera_label(exif: ImageExifData) -> str:
    """Make and model as one label, ``Unknown`` when neither is known."""
    return f"{exif.camera_make or ''} {exif.camera_model or ''}".strip() or "Unknown"


def fail(message: str, code: int = 1) -> NoReturn:
    """Report ``message`` on stderr as an error and end the command with ``code``."""
    print(f"Error: {message}", file=sys.stderr)
    finish(code)


def _note_library_left_behind(db_flag: str | None, settings: Settings) -> None:
    """The default library used to be photos.db in the working directory: say where it went."""
    default = app_settings.user_dirs().data / "photos.db"
    if (
        db_flag is not None
        or settings.db_path != default
        or default.exists()
        or not OLD_DEFAULT_DB.is_file()
    ):
        return
    print(
        f"Note: found {OLD_DEFAULT_DB.resolve()}, but the library now lives at {default}.\n"
        "      Move photos.db (with any photos.db-wal/-shm files) there, or pass "
        "--db photos.db to keep using it here.",
        file=sys.stderr,
    )
