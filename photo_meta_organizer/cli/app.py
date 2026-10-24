"""The command line: global options, the commands, and the process exit code."""

import logging
import sys
from typing import Annotated

import typer

from photo_meta_organizer import __version__
from photo_meta_organizer.cli.analyze import analyze
from photo_meta_organizer.cli.common import Command, GlobalOptions, Group, LogLevel
from photo_meta_organizer.cli.index import index
from photo_meta_organizer.cli.paths import paths
from photo_meta_organizer.cli.prune import prune
from photo_meta_organizer.cli.search import search
from photo_meta_organizer.cli.stats import stats
from photo_meta_organizer.cli.sync import sync

logger = logging.getLogger(__name__)

PROG = "photo-meta-organizer"

app = typer.Typer(
    name=PROG,
    cls=Group,
    help=(
        "High-performance metadata indexing and organization system "
        "for large photo libraries (20GB+)"
    ),
    epilog="For more info: https://github.com/krishnamohan-seelam/photo_meta_organizer",
    add_completion=False,
    pretty_exceptions_enable=False,
    rich_markup_mode=None,  # plain help, as argparse printed: no boxes, safe on any console
)


def _show_version(value: bool) -> None:
    if value:
        print(f"{PROG} {__version__}")
        raise typer.Exit(0)


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_show_version,
            is_eager=True,
            help="Show the version and exit",
        ),
    ] = False,
    log_level: Annotated[
        LogLevel, typer.Option("--log-level", help="Set logging level (default: INFO)")
    ] = "INFO",
    log: Annotated[
        bool,
        typer.Option(
            "--log",
            help="Also write a rotating photo_meta_organizer.log to the per-user log folder",
        ),
    ] = False,
    log_dir: Annotated[
        str | None,
        typer.Option(
            "--log-dir",
            help=(
                "Write a rotating photo_meta_organizer.log here "
                "(default: $PMO_LOG_DIR, else none unless --log)"
            ),
        ),
    ] = None,
) -> None:
    ctx.obj = GlobalOptions(log_level=log_level, log=log, log_dir=log_dir)
    if ctx.invoked_subcommand is None:
        print(ctx.get_help())
        raise typer.Exit(0)


app.command("index", cls=Command)(index)
app.command("search", cls=Command)(search)
app.command("sync", cls=Command)(sync)
app.command("prune", cls=Command)(prune)
app.command("analyze", cls=Command)(analyze)
app.command("stats", cls=Command)(stats)
app.command("paths", cls=Command)(paths)


def run(argv: list[str] | None = None) -> int:
    """Run one command line (``sys.argv[1:]`` by default) and return its exit code.

    A usage error (a missing or invalid option) is printed and raises ``SystemExit(2)``,
    as argparse did; an unexpected error is logged, reported on stderr as
    ``Error: ...`` and returns 1.
    """
    try:
        code = app(
            args=sys.argv[1:] if argv is None else argv, prog_name=PROG, standalone_mode=False
        )
    except typer.Abort:
        print("Aborted!", file=sys.stderr)
        return 1
    except typer.TyperException as exc:  # click's usage errors derive from it
        exc.show()  # type: ignore[attr-defined]
        raise SystemExit(getattr(exc, "exit_code", 2)) from exc
    except Exception as e:  # noqa: BLE001 - the process reports it and exits 1
        logger.exception("Unexpected error: %s", e)
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return code if isinstance(code, int) else 0  # a command's exit code, or 0 after --help
