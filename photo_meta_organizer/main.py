"""Entry point for Photo Meta Organizer application.

This module serves as both the CLI interface and the composition root
for dependency injection. It is responsible for:

1. Configuring logging
2. Creating concrete implementations (factory functions)
3. Parsing CLI arguments and dispatching commands
4. Managing application lifecycle and error handling

The factory functions (build_retriever, build_repository, build_extractor)
are the composition root — the ONE place that imports concrete infrastructure
classes and decides which implementation to use based on CLI args or config.

When the project adds a REST API (Phase 3+), the composition root should
be extracted to application/composition.py so both main.py and the API
entry point can share it.

Example:
    $ python -m photo_meta_organizer.main --help
    $ python -m photo_meta_organizer.main index --path /photos --db metadata.json
"""

import argparse
import logging
import sys
from datetime import datetime
from logging.config import dictConfig

from photo_meta_organizer.application.interfaces import (
    ImageMetadataExtractor,
    ImageMetadataRepository,
    ImageRetriever,
)
from photo_meta_organizer.domain.datetimes import to_naive

# Configure logging at module level
_LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        },
        "detailed": {
            "format": ("%(asctime)s [%(levelname)s] %(name)s.%(funcName)s:%(lineno)d: %(message)s"),
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "standard",
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.FileHandler",
            "level": "DEBUG",
            "formatter": "detailed",
            "filename": "photo_meta_organizer.log",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["console", "file"],
    },
    "loggers": {
        "photo_meta_organizer": {
            "level": "DEBUG",
            "handlers": ["console", "file"],
            "propagate": True,
        },
    },
}

dictConfig(_LOGGING_CONFIG)
logger = logging.getLogger(__name__)


# ============================================================================
# COMPOSITION ROOT — Factory Functions
# ============================================================================
# These factory functions are the composition root. They are the ONLY place
# that imports concrete infrastructure classes. Backend selection is driven
# by CLI args, enabling plug-and-play swapping:
#
#   Local disk + TinyDB:   python main.py index --path /photos --db meta.json
#   S3 + MongoDB (Phase 4): python main.py index --storage s3 --bucket photos --db-type mongodb
# ============================================================================


def build_retriever(args: argparse.Namespace) -> ImageRetriever:
    """Create the file retriever based on CLI arguments.

    Delegates to the shared factory so the CLI and the REST API index exactly the
    same set of files (images only).

    Phase 4: Will support S3Retriever, GoogleCloudStorageRetriever, etc.

    Args:
        args: Parsed CLI arguments containing --path.

    Returns:
        An ImageRetriever implementation.
    """
    from photo_meta_organizer.application.composition import build_local_retriever

    return build_local_retriever(args.path)


def build_extractor() -> ImageMetadataExtractor:
    """Create the metadata extractor.

    The extractor is stateless with no configuration — there's only
    one implementation needed. Phase 5 may add AI-based extractors.

    Returns:
        A stateless ImageMetadataExtractor implementation.
    """
    from photo_meta_organizer.infrastructure.extractors.disk_metadata_extractor import (
        DiskMetaDataExtractor,
    )

    return DiskMetaDataExtractor()


def build_repository(args: argparse.Namespace) -> ImageMetadataRepository:
    """Create the metadata repository based on CLI arguments.

    SQLite behind the repository port (ADR-001, PMO-08). A ``--db`` pointing at an
    existing legacy TinyDB JSON file is imported once into a sibling ``.db`` file;
    see ``application.composition.build_repository``.

    Args:
        args: Parsed CLI arguments containing --db.

    Returns:
        An ImageMetadataRepository implementation.
    """
    from photo_meta_organizer.application.composition import (
        build_repository as _build_repository,
    )

    return _build_repository(args.db)


# ============================================================================
# CLI COMMAND HANDLERS
# ============================================================================


def handle_index_command(args: argparse.Namespace) -> int:
    """Handle 'index' command — scan photos and extract metadata.

    Delegates to IndexPhotosUseCase or ParallelIndexPhotosUseCase for the full pipeline:
    retrieve → extract → persist.

    Args:
        args: Parsed CLI arguments (--path, --db, etc.).

    Returns:
        Exit code (0 = success, non-zero = error).
    """
    retriever = build_retriever(args)
    extractor = build_extractor()
    repository = build_repository(args)

    workers = getattr(args, "workers", 4)
    if workers > 1:
        from photo_meta_organizer.application.use_cases import (
            ParallelIndexPhotosUseCase,
        )

        use_case = ParallelIndexPhotosUseCase(
            retriever=retriever,
            extractor=extractor,
            repository=repository,
            num_workers=workers,
        )
    else:
        from photo_meta_organizer.application.use_cases import IndexPhotosUseCase

        use_case = IndexPhotosUseCase(
            retriever=retriever,
            extractor=extractor,
            repository=repository,
        )

    results = use_case.execute()
    print(f"Successfully indexed {len(results)} photos")
    return 0


def _parse_date_arg(date_str: str | None) -> datetime | None:
    """Parse a date string into a naive local datetime (see domain/datetimes.py)."""
    if not date_str:
        return None
    date_str = date_str.strip()
    try:
        if len(date_str) == 7:  # YYYY-MM
            return datetime.strptime(date_str, "%Y-%m")
        elif len(date_str) == 10:  # YYYY-MM-DD
            return datetime.strptime(date_str, "%Y-%m-%d")
        return to_naive(datetime.fromisoformat(date_str))
    except ValueError:
        logger.warning("Failed to parse date string: %s", date_str)
        return None


def handle_search_command(args: argparse.Namespace) -> int:
    """Handle 'search' command — query indexed photos.

    Args:
        args: Parsed CLI arguments (--camera, --date, --sort, etc.).

    Returns:
        Exit code (0 = success, non-zero = error).
    """
    from tabulate import tabulate

    from photo_meta_organizer.application.use_cases import (
        SearchPhotosQuery,
        SearchPhotosUseCase,
    )

    repository = build_repository(args)

    # Date parsing logic
    date_start = _parse_date_arg(getattr(args, "date_from", None))
    date_end = _parse_date_arg(getattr(args, "date_to", None))
    single_date = getattr(args, "date", None)
    if single_date and not date_start and not date_end:
        if len(single_date.strip()) == 7:  # YYYY-MM
            dt = _parse_date_arg(single_date)
            if dt:
                date_start = dt
                # End of month
                month = dt.month
                year = dt.year + (1 if month == 12 else 0)
                next_month = 1 if month == 12 else month + 1
                date_end = datetime(year, next_month, 1)
        else:
            dt = _parse_date_arg(single_date)
            if dt:
                date_start = dt
                date_end = datetime(dt.year, dt.month, dt.day, 23, 59, 59)

    # Location radius parsing
    loc_lat = getattr(args, "lat", None)
    loc_lon = getattr(args, "lon", None)
    radius_km = getattr(args, "radius", None)

    loc_arg = getattr(args, "location", None)
    if loc_arg and (loc_lat is None or loc_lon is None or radius_km is None):
        parts = [p.strip() for p in loc_arg.split(",")]
        if len(parts) >= 3:
            try:
                loc_lat, loc_lon, radius_km = (
                    float(parts[0]),
                    float(parts[1]),
                    float(parts[2]),
                )
            except ValueError:
                pass

    # Tags parsing
    tags_arg = getattr(args, "tags", None)
    tags_list = [t.strip() for t in tags_arg.split(",")] if tags_arg else None

    # --camera used to set both camera_make and camera_model and rely on a
    # since-removed sentinel (PMO-09) that treated an equal make/model as "search
    # either field"; search_term now covers that (it also matches file name/path,
    # which --camera never claimed to search, but this CLI flag has no separate
    # "search anything" option, so the broader match is the closer fit).
    query = SearchPhotosQuery(
        date_start=date_start,
        date_end=date_end,
        search_term=getattr(args, "camera", None),
        location_lat=loc_lat,
        location_lon=loc_lon,
        radius_km=radius_km,
        tags=tags_list,
        sort_by=getattr(args, "sort", "captured_at"),
        sort_order=getattr(args, "order", "asc"),
        page=getattr(args, "page", 1),
        page_size=getattr(args, "page_size", 50),
    )

    use_case = SearchPhotosUseCase(repository=repository)
    result = use_case.execute(query)

    print(
        f"\nSearch Results (Page {result.page} of {result.total_pages} | Total: {result.total_count}):\n"
    )

    if not result.items:
        print("No photos found matching the search criteria.")
        return 0

    table_data = []
    for item in result:
        exif = item.exif
        cam = f"{exif.camera_make or ''} {exif.camera_model or ''}".strip() or "Unknown"
        dt_str = exif.captured_at.strftime("%Y-%m-%d %H:%M") if exif and exif.captured_at else "N/A"
        size_mb = (item.file_info.size_bytes or 0) / (1024 * 1024)
        size_str = f"{size_mb:.2f} MB"
        loc_str = (
            f"{exif.location.latitude:.4f}, {exif.location.longitude:.4f}"
            if exif and exif.location
            else "N/A"
        )
        labels_str = ", ".join(item.labels) if item.labels else ""

        table_data.append(
            [
                item.file_info.name,
                dt_str,
                cam,
                size_str,
                loc_str,
                labels_str,
            ]
        )

    headers = [
        "Filename",
        "Captured At",
        "Camera Make/Model",
        "Size",
        "GPS (Lat, Lon)",
        "Labels",
    ]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    print(f"\nDisplaying {len(result.items)} item(s) on Page {result.page}.\n")
    return 0


def handle_stats_command(args: argparse.Namespace) -> int:
    """Handle 'stats' command — show library statistics.

    Args:
        args: Parsed CLI arguments (--db, etc.).

    Returns:
        Exit code (0 = success, non-zero = error).
    """
    from collections import Counter

    from tabulate import tabulate

    try:
        repository = build_repository(args)
        all_metadata = repository.list_all()
        total_photos = len(all_metadata)

        total_bytes = 0
        mime_counts = Counter()
        camera_counts = Counter()
        dates = []

        for item in all_metadata:
            if hasattr(item, "file_info") and item.file_info:
                total_bytes += getattr(item.file_info, "size_bytes", 0)
                mime_counts[getattr(item.file_info, "mime_type", "unknown")] += 1
            if hasattr(item, "exif") and item.exif:
                make = getattr(item.exif, "camera_make", "") or ""
                model = getattr(item.exif, "camera_model", "") or ""
                cam_name = f"{make} {model}".strip() or "Unknown"
                camera_counts[cam_name] += 1
                if item.exif.captured_at:
                    dates.append(item.exif.captured_at)

        # Format size in human-readable units
        size_mb = total_bytes / (1024 * 1024)
        size_str = f"{size_mb / 1024:.2f} GB" if size_mb >= 1024 else f"{size_mb:.2f} MB"

        date_range_str = "N/A"
        if dates:
            min_date = min(dates).strftime("%Y-%m-%d")
            max_date = max(dates).strftime("%Y-%m-%d")
            date_range_str = f"{min_date} to {max_date}"

        print("\n=======================================================")
        print("       PHOTO META ORGANIZER - LIBRARY STATISTICS       ")
        print("=======================================================")
        print(f" Database File         : {args.db}")
        print(f" Total Photos Indexed  : {total_photos}")
        print(f" Total Storage Size    : {size_str} ({total_bytes:,} bytes)")
        print(f" Date Range            : {date_range_str}")

        if mime_counts:
            print("\nFormat Distribution:")
            format_table = [[mime, count] for mime, count in mime_counts.most_common()]
            print(tabulate(format_table, headers=["Format", "Count"], tablefmt="simple"))

        if camera_counts:
            print("\nCamera Distribution:")
            camera_table = [[cam, count] for cam, count in camera_counts.most_common()]
            print(
                tabulate(
                    camera_table,
                    headers=["Camera Make/Model", "Count"],
                    tablefmt="simple",
                )
            )

        print("=======================================================\n")
    except Exception as e:
        logger.error("Failed to read statistics: %s", e)
        print(f"Error reading statistics: {e}")
        return 1
    return 0


def handle_sync_command(args: argparse.Namespace) -> int:
    """Handle 'sync' command — incremental metadata synchronization.

    Detects NEW, MODIFIED, DELETED, and UNCHANGED files by comparing
    the metadata DB against the current disk state.  Only changed files
    are processed, making this significantly faster than a full reindex
    for large libraries with few changes.

    Args:
        args: Parsed CLI arguments (--path, --db, sync flags).

    Returns:
        Exit code (0 = success, non-zero = error).
    """
    from photo_meta_organizer.application.use_cases import SynchronizeMetadataUseCase

    retriever = build_retriever(args)
    extractor = build_extractor()
    repository = build_repository(args)

    use_case = SynchronizeMetadataUseCase(
        retriever=retriever,
        extractor=extractor,
        repository=repository,
    )

    result = use_case.execute(
        cleanup_deleted=args.cleanup_deleted,
        reprocess_modified=args.reprocess_modified,
        index_new=args.index_new,
        dry_run=args.dry_run,
        rehash=args.rehash,
    )

    prefix = "[DRY RUN] " if args.dry_run else ""
    print(
        f"{prefix}Sync complete in {result.duration_seconds:.2f}s: "
        f"+{result.new_files} new, "
        f"~{result.modified_files} modified, "
        f"-{result.deleted_entries} deleted, "
        f"{result.unchanged_files} unchanged"
    )
    if result.fingerprints_refreshed:
        verb = "would record" if args.dry_run else "recorded"
        print(f"  ({verb} size/mtime for {result.fingerprints_refreshed} unchanged file(s))")
    if result.errors:
        print(f"Errors ({len(result.errors)}):")
        for err in result.errors:
            print(f"  ✗ {err}")
    return 0 if not result.errors else 2


def handle_dedupe_command(args: argparse.Namespace) -> int:
    """Handle 'dedupe' command — merge records that share a file path.

    Dry-run by default; pass --apply to write.
    """
    from photo_meta_organizer.application.use_cases import DedupePathsUseCase

    repository = build_repository(args)
    result = DedupePathsUseCase(repository).execute(apply=args.apply)

    if not result.groups:
        print("No duplicate paths found.")
        return 0
    extra = sum(len(g.drop) for g in result.groups)
    label = "Merged" if args.apply else "Would merge (dry run; pass --apply to write)"
    print(f"{label}: {extra} extra record(s) across {len(result.groups)} path(s)")
    for group in result.groups[:50]:
        print(f"  {group.path}  keep {group.keep.file_hash[:12]}, drop {len(group.drop)}")
    if len(result.groups) > 50:
        print(f"  ... and {len(result.groups) - 50} more")
    if args.apply:
        print(f"Removed {result.removed} record(s).")
    return 0


def handle_prune_command(args: argparse.Namespace) -> int:
    """Handle 'prune' command — remove records for non-image files.

    Dry-run by default; pass --apply to delete.
    """
    from photo_meta_organizer.application.use_cases import PruneNonImagesUseCase

    repository = build_repository(args)
    result = PruneNonImagesUseCase(repository).execute(apply=args.apply)

    if not result.candidates:
        print("No non-image records found.")
        return 0
    label = "Removed" if args.apply else "Would remove (dry run; pass --apply to delete)"
    print(f"{label}: {len(result.candidates)} record(s)")
    for record in result.candidates[:50]:
        print(f"  {record.file_info.path}")
    if len(result.candidates) > 50:
        print(f"  ... and {len(result.candidates) - 50} more")
    if args.apply:
        print(f"Deleted {result.removed} record(s).")
    return 0


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================


def main() -> int:
    """Main entry point for the application.

    Parses CLI arguments and dispatches to the appropriate command handler.

    Returns:
        Exit code passed to sys.exit().
    """
    parser = argparse.ArgumentParser(
        prog="photo-meta-organizer",
        description=(
            "High-performance metadata indexing and organization system "
            "for large photo libraries (20GB+)"
        ),
        epilog="For more info: https://github.com/krishnamohan-seelam/photo_meta_organizer",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0 (Phase 0 Foundation)",
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level (default: INFO)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Index command (Phase 1)
    index_parser = subparsers.add_parser(
        "index",
        help="Index photos and extract metadata",
    )
    index_parser.add_argument(
        "--path",
        required=False,
        help="Path to photos directory",
    )
    index_parser.add_argument(
        "--db",
        default="photos.db",
        help="Path to metadata database file (default: photos.db)",
    )
    index_parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of worker threads (Phase 2 — default: 4)",
    )
    index_parser.set_defaults(func=handle_index_command)

    # Search command (Phase 3)
    search_parser = subparsers.add_parser(
        "search",
        help="Search indexed photos (Phase 3)",
    )
    search_parser.add_argument("--db", default="photos.db", help="Path to metadata database file")
    search_parser.add_argument("--date", help="Date filter (YYYY-MM or YYYY-MM-DD)")
    search_parser.add_argument("--date-from", help="Start date (YYYY-MM-DD)")
    search_parser.add_argument("--date-to", help="End date (YYYY-MM-DD)")
    search_parser.add_argument("--camera", help="Filter by camera make/model")
    search_parser.add_argument("--location", help="Filter by location (lat,lon,radius_km)")
    search_parser.add_argument("--lat", type=float, help="Latitude for radius search")
    search_parser.add_argument("--lon", type=float, help="Longitude for radius search")
    search_parser.add_argument("--radius", type=float, help="Radius in km for location search")
    search_parser.add_argument("--tags", help="Filter by tags (comma-separated)")
    search_parser.add_argument(
        "--sort",
        default="captured_at",
        choices=["captured_at", "size_bytes", "camera_model", "file_name"],
        help="Field to sort by (default: captured_at)",
    )
    search_parser.add_argument(
        "--order",
        default="asc",
        choices=["asc", "desc"],
        help="Sort order (default: asc)",
    )
    search_parser.add_argument("--page", type=int, default=1, help="Page number (default: 1)")
    search_parser.add_argument(
        "--page-size", type=int, default=50, help="Results per page (default: 50)"
    )
    search_parser.set_defaults(func=handle_search_command)

    # Sync command (Phase 1.5 — Metadata Sync)
    sync_parser = subparsers.add_parser(
        "sync",
        help="Incrementally sync metadata DB with disk state",
        description=(
            "Detect and process changes (new, modified, deleted) between "
            "the metadata DB and current disk contents. Much faster than "
            "a full 'index' for large libraries with few changes."
        ),
    )
    sync_parser.add_argument(
        "--path",
        required=False,
        help="Path to photos directory",
    )
    sync_parser.add_argument(
        "--db",
        default="photos.db",
        help="Path to metadata database file (default: photos.db)",
    )
    sync_parser.add_argument(
        "--cleanup-deleted",
        action="store_true",
        default=False,
        help="Remove DB entries for files no longer on disk (default: off)",
    )
    sync_parser.add_argument(
        "--no-reprocess",
        dest="reprocess_modified",
        action="store_false",
        default=True,
        help="Skip re-extraction of modified files",
    )
    sync_parser.add_argument(
        "--no-index",
        dest="index_new",
        action="store_false",
        default=True,
        help="Skip indexing of new files",
    )
    sync_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Analyse changes but do NOT write anything (preview mode)",
    )
    sync_parser.add_argument(
        "--rehash",
        action="store_true",
        default=False,
        help=(
            "Hash every file already in the DB instead of trusting size+mtime. Slow, but "
            "catches an edit that kept both size and mtime"
        ),
    )
    sync_parser.set_defaults(
        func=handle_sync_command,
        cleanup_deleted=False,
        reprocess_modified=True,
        index_new=True,
        dry_run=False,
        rehash=False,
    )

    # Prune command (PMO-04)
    prune_parser = subparsers.add_parser(
        "prune",
        help="Remove records for non-image files from the database",
        description=(
            "Older versions of the REST API indexed every file in a folder. This removes "
            "records whose file is not an image. Dry run unless --apply is given."
        ),
    )
    prune_parser.add_argument("--db", default="photos.db", help="Path to metadata database file")
    prune_parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Actually delete (default: dry run)",
    )
    prune_parser.set_defaults(func=handle_prune_command)

    # Dedupe command (PMO-05)
    dedupe_parser = subparsers.add_parser(
        "dedupe",
        help="Merge records that share a file path (left by older versions of sync)",
        description=(
            "Before PMO-05 an edited file was saved under its new hash and the old record "
            "stayed behind. This keeps the newest record per path and merges the rating, "
            "flag and labels of the others into it. Dry run unless --apply is given."
        ),
    )
    dedupe_parser.add_argument("--db", default="photos.db", help="Path to metadata database file")
    dedupe_parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Actually merge (default: dry run)",
    )
    dedupe_parser.set_defaults(func=handle_dedupe_command)

    # Stats command (Phase 2)
    stats_parser = subparsers.add_parser(
        "stats",
        help="Show library statistics (Phase 2)",
    )
    stats_parser.add_argument("--db", default="photos.db")
    stats_parser.set_defaults(func=handle_stats_command)

    try:
        args = parser.parse_args()

        # Update log level based on argument
        logging.getLogger().setLevel(args.log_level)
        logger.info("Starting Photo Meta Organizer (log level: %s)", args.log_level)

        # If no command specified, print help
        if not hasattr(args, "func"):
            parser.print_help()
            return 0

        # Dispatch to command handler
        logger.debug("Executing command: %s", args.command)
        return args.func(args)

    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
