"""``index``: a scan that records new and changed photos and never removes any."""

from typing import Annotated

import typer

from photo_meta_organizer.cli.common import (
    DbOption,
    PathOption,
    finish,
    open_library,
    print_errors,
    root_unavailable,
    start,
)


def index(
    ctx: typer.Context,
    path: PathOption,
    db: DbOption = None,
    workers: Annotated[
        int, typer.Option("--workers", help="Number of worker threads (Phase 2 - default: 4)")
    ] = 4,
) -> None:
    """Index photos and extract metadata.

    Files already in the library and unchanged are skipped, and nothing is removed.
    Exit code: 0 = success, 1 = the folder could not be read, 2 = some files failed
    (listed on stdout).
    """
    # A scan without remove_missing (ADR-003 R4).
    from photo_meta_organizer.application.composition import build_scan
    from photo_meta_organizer.application.use_cases.scan_library import (
        RootUnavailableError,
        ScanOptions,
    )
    from photo_meta_organizer.infrastructure.metrics import ProgressReporter

    settings = start(ctx, db)
    scan = build_scan(path, open_library(settings), progress_reporter=ProgressReporter())
    try:
        result = scan.execute(ScanOptions(workers=workers), scope_root=path)
    except RootUnavailableError as exc:
        root_unavailable(exc)
    print(f"Successfully indexed {result.indexed_files} photos")
    if result.unchanged_files:
        print(f"  ({result.unchanged_files} already in the library and unchanged)")
    print_errors(result.errors)
    finish(0 if not result.errors else 2)
