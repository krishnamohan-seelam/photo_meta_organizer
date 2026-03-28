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
from logging.config import dictConfig
from typing import Optional

from photo_meta_organizer.application.interfaces import (
    ImageMetadataExtractor,
    ImageMetadataRepository,
    ImageRetriever,
)

# Configure logging at module level
_LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        },
        "detailed": {
            "format": (
                "%(asctime)s [%(levelname)s] %(name)s.%(funcName)s:%(lineno)d: %(message)s"
            ),
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

    Uses ExtensionFilteredRetriever wrapping LocalDiskRetriever to
    discover only image files (JPEG, PNG, TIFF, etc.).

    Phase 4: Will support S3Retriever, GoogleCloudStorageRetriever, etc.

    Args:
        args: Parsed CLI arguments containing --path.

    Returns:
        An ImageRetriever implementation.
    """
    from photo_meta_organizer.infrastructure.retriever.local_disk_retriever import (
        LocalDiskRetriever,
    )
    from photo_meta_organizer.infrastructure.retriever.filtered_retriever import (
        ExtensionFilteredRetriever,
    )

    IMAGE_EXTENSIONS = {
        ".jpg", ".jpeg", ".png", ".tiff", ".tif",
        ".bmp", ".gif", ".webp", ".heic", ".heif",
        ".raw", ".cr2", ".nef", ".arw", ".dng",
    }

    base_retriever = LocalDiskRetriever(base_path=args.path)
    return ExtensionFilteredRetriever(base_retriever, IMAGE_EXTENSIONS)


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

    Phase 1: TinyDBRepository (default, JSON file-based)
    Phase 4: MongoDBRepository, ElasticsearchRepository, etc.

    Args:
        args: Parsed CLI arguments containing --db.

    Returns:
        An ImageMetadataRepository implementation.
    """
    from photo_meta_organizer.infrastructure.repositories.tinydb_repository import (
        TinyDBRepository,
    )

    return TinyDBRepository(db_path=args.db)


# ============================================================================
# CLI COMMAND HANDLERS
# ============================================================================


def handle_index_command(args: argparse.Namespace) -> int:
    """Handle 'index' command — scan photos and extract metadata.

    Delegates to IndexPhotosUseCase for the full pipeline:
    retrieve → extract → persist.

    Args:
        args: Parsed CLI arguments (--path, --db, etc.).

    Returns:
        Exit code (0 = success, non-zero = error).
    """
    from photo_meta_organizer.application.use_cases import IndexPhotosUseCase

    retriever = build_retriever(args)
    extractor = build_extractor()
    repository = build_repository(args)

    use_case = IndexPhotosUseCase(
        retriever=retriever,
        extractor=extractor,
        repository=repository,
    )
    results = use_case.execute()
    print(f"Successfully indexed {len(results)} photos")
    return 0


def handle_search_command(args: argparse.Namespace) -> int:
    """Handle 'search' command — query indexed photos.

    Phase 3 deliverable.

    Args:
        args: Parsed CLI arguments (--date-from, --camera, etc.).

    Returns:
        Exit code (0 = success, non-zero = error).
    """
    logger.info("Search command received (Phase 3 — not yet implemented)")
    print("Phase 3: Search command — coming soon")
    return 0


def handle_stats_command(args: argparse.Namespace) -> int:
    """Handle 'stats' command — show library statistics.

    Phase 2 deliverable.

    Args:
        args: Parsed CLI arguments (--db, etc.).

    Returns:
        Exit code (0 = success, non-zero = error).
    """
    logger.info("Stats command received (Phase 2 — not yet implemented)")
    print("Phase 2: Stats command — coming soon")
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
    )

    prefix = "[DRY RUN] " if args.dry_run else ""
    print(
        f"{prefix}Sync complete in {result.duration_seconds:.2f}s: "
        f"+{result.new_files} new, "
        f"~{result.modified_files} modified, "
        f"-{result.deleted_entries} deleted, "
        f"{result.unchanged_files} unchanged"
    )
    if result.errors:
        print(f"Errors ({len(result.errors)}):")
        for err in result.errors:
            print(f"  ✗ {err}")
    return 0 if not result.errors else 2


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
        default="photo_metadata.json",
        help="Path to metadata database file (default: photo_metadata.json)",
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
    search_parser.add_argument("--db", default="photo_metadata.json")
    search_parser.add_argument("--date-from", help="Start date (YYYY-MM-DD)")
    search_parser.add_argument("--date-to", help="End date (YYYY-MM-DD)")
    search_parser.add_argument("--camera", help="Filter by camera model")
    search_parser.add_argument(
        "--location", help="Filter by location (lat,lon,radius_km)"
    )
    search_parser.add_argument("--tags", help="Filter by tags (comma-separated)")
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
        default="photo_metadata.json",
        help="Path to metadata database file (default: photo_metadata.json)",
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
    sync_parser.set_defaults(
        func=handle_sync_command,
        cleanup_deleted=False,
        reprocess_modified=True,
        index_new=True,
        dry_run=False,
    )

    # Stats command (Phase 2)
    stats_parser = subparsers.add_parser(
        "stats",
        help="Show library statistics (Phase 2)",
    )
    stats_parser.add_argument("--db", default="photo_metadata.json")
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
