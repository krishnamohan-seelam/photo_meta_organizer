"""``sync``: scan a folder and apply only what changed, with every scan option."""

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


def sync(
    ctx: typer.Context,
    path: PathOption,
    db: DbOption = None,
    cleanup_deleted: Annotated[
        bool,
        typer.Option(
            "--cleanup-deleted",
            "--remove-missing",
            help="Remove files no longer on disk (default: off; they are kept, flagged missing)",
        ),
    ] = False,
    no_reprocess: Annotated[
        bool, typer.Option("--no-reprocess", help="Skip re-extraction of modified files")
    ] = False,
    no_index: Annotated[
        bool, typer.Option("--no-index", help="Skip indexing of new files")
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Analyse changes but do NOT write anything (preview mode)"),
    ] = False,
    rehash: Annotated[
        bool,
        typer.Option(
            "--rehash",
            help=(
                "Hash every file already in the DB instead of trusting size+mtime. Slow, but "
                "catches an edit that kept both size and mtime"
            ),
        ),
    ] = False,
    reextract: Annotated[
        bool,
        typer.Option(
            "--reextract",
            help=(
                "Re-extract every file already in the DB (keeps ratings, flags and labels). "
                "Slow; repairs records from older versions, e.g. capture dates taken from "
                "the file's modification time"
            ),
        ),
    ] = False,
    workers: Annotated[
        int, typer.Option("--workers", help="Files read in parallel (default: 4)")
    ] = 4,
) -> None:
    """Incrementally sync metadata DB with disk state.

    Detect and process changes (new, modified, deleted) between the metadata DB and
    current disk contents. Much faster than a full 'index' for large libraries with few
    changes. Exit code: 0 = success, 1 = the folder could not be read, 2 = some files
    failed.
    """
    from photo_meta_organizer.application.composition import build_scan
    from photo_meta_organizer.application.use_cases.scan_library import (
        RootUnavailableError,
        ScanOptions,
    )

    settings = start(ctx, db)
    options = ScanOptions(
        remove_missing=cleanup_deleted,
        reprocess_modified=not no_reprocess,
        index_new=not no_index,
        dry_run=dry_run,
        rehash=rehash,
        reextract=reextract,
        workers=workers,
    )
    try:
        # Only files under --path take part, so --cleanup-deleted can never remove
        # photos indexed from another folder.
        result = build_scan(path, open_library(settings)).execute(options, scope_root=path)
    except RootUnavailableError as exc:
        root_unavailable(exc)

    prefix = "[DRY RUN] " if dry_run else ""
    print(
        f"{prefix}Sync complete in {result.duration_seconds:.2f}s: "
        f"+{result.new_files} new, "
        f"~{result.modified_files} modified, "
        f"-{result.deleted_entries} deleted, "
        f"{result.unchanged_files} unchanged"
    )
    if result.missing_files or result.found_again:
        print(
            f"  {result.missing_files} file(s) missing (kept; --cleanup-deleted removes them), "
            f"{result.found_again} found again"
        )
    if result.fingerprints_refreshed:
        verb = "would record" if dry_run else "recorded"
        print(f"  ({verb} size/mtime for {result.fingerprints_refreshed} unchanged file(s))")
    print_errors(result.errors)
    finish(0 if not result.errors else 2)
