"""``paths``: where this library's files live. Writes nothing."""

import typer

from photo_meta_organizer.application import settings as app_settings
from photo_meta_organizer.cli.common import DbOption, finish, start


def paths(ctx: typer.Context, db: DbOption = None) -> None:
    """Show where the database, thumbnails, AI model and logs are kept."""
    settings = start(ctx, db)
    log = settings.log_dir or app_settings.user_dirs().log
    print(f" Database   : {settings.db_path}")
    print(f" Thumbnails : {settings.thumbnail_dir}")
    print(f" AI model   : {settings.models_dir}")
    print(f" Logs       : {log}{'' if settings.log_dir else '  (written only with --log)'}")
    finish(0)
