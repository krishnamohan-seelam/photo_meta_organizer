"""``stats``: library statistics."""

import logging
from collections import Counter

import typer

from photo_meta_organizer.cli.common import DbOption, camera_label, finish, open_library, start

logger = logging.getLogger(__name__)


def stats(ctx: typer.Context, db: DbOption = None) -> None:
    """Show library statistics (Phase 2)."""
    from tabulate import tabulate

    settings = start(ctx, db)
    try:
        all_metadata = open_library(settings).list_all()
        total_bytes = 0
        mime_counts: Counter[str] = Counter()
        camera_counts: Counter[str] = Counter()
        dates = []
        for item in all_metadata:
            total_bytes += item.file_info.size_bytes
            mime_counts[item.file_info.mime_type] += 1
            camera_counts[camera_label(item.exif)] += 1
            if item.exif.captured_at:
                dates.append(item.exif.captured_at)

        size_mb = total_bytes / (1024 * 1024)
        size_str = f"{size_mb / 1024:.2f} GB" if size_mb >= 1024 else f"{size_mb:.2f} MB"
        date_range_str = "N/A"
        if dates:
            date_range_str = f"{min(dates):%Y-%m-%d} to {max(dates):%Y-%m-%d}"

        print("\n=======================================================")
        print("       PHOTO META ORGANIZER - LIBRARY STATISTICS       ")
        print("=======================================================")
        print(f" Database File         : {settings.db_path}")
        print(f" Total Photos Indexed  : {len(all_metadata)}")
        print(f" Total Storage Size    : {size_str} ({total_bytes:,} bytes)")
        print(f" Date Range            : {date_range_str}")
        if mime_counts:
            print("\nFormat Distribution:")
            format_table = [[mime, count] for mime, count in mime_counts.most_common()]
            print(tabulate(format_table, headers=["Format", "Count"], tablefmt="simple"))
        if camera_counts:
            print("\nCamera Distribution:")
            camera_table = [[camera, count] for camera, count in camera_counts.most_common()]
            print(tabulate(camera_table, headers=["Camera Make/Model", "Count"], tablefmt="simple"))
        print("=======================================================\n")
    except Exception as e:  # noqa: BLE001 - reported, not raised, as before
        logger.error("Failed to read statistics: %s", e)
        print(f"Error reading statistics: {e}")
        finish(1)
    finish(0)
