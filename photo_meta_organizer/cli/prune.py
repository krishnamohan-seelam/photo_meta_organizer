"""``prune``: remove records for non-image files (left by older versions of the API)."""

from typing import Annotated

import typer

from photo_meta_organizer.cli.common import DbOption, finish, open_library, start

LISTED_AT_MOST = 50  # records listed by path; the rest are counted


def prune(
    ctx: typer.Context,
    db: DbOption = None,
    apply: Annotated[
        bool, typer.Option("--apply", help="Actually delete (default: dry run)")
    ] = False,
) -> None:
    """Remove records for non-image files from the database.

    Older versions of the REST API indexed every file in a folder. This removes records
    whose file is not an image. Dry run unless --apply is given.
    """
    from photo_meta_organizer.application.use_cases import PruneNonImagesUseCase

    settings = start(ctx, db)
    result = PruneNonImagesUseCase(open_library(settings)).execute(apply=apply)
    if not result.candidates:
        print("No non-image records found.")
        finish(0)
    label = "Removed" if apply else "Would remove (dry run; pass --apply to delete)"
    print(f"{label}: {len(result.candidates)} record(s)")
    for record in result.candidates[:LISTED_AT_MOST]:
        print(f"  {record.file_info.path}")
    if len(result.candidates) > LISTED_AT_MOST:
        print(f"  ... and {len(result.candidates) - LISTED_AT_MOST} more")
    if apply:
        print(f"Deleted {result.removed} record(s).")
    finish(0)
